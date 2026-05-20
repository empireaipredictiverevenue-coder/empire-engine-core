"""
Empire V49 · Live Broadcast Layer
==================================
WebSocket pub/sub for real-time dashboard updates. Instead of every operator's
browser polling /api/subconscious every 12 seconds, the Subconscious Mind pushes
events to all connected dashboards instantly when something happens.

Wire-up in hub.py:

    from empire_live import live_broadcaster, websocket_endpoint

    # Register the WebSocket endpoint
    app.add_api_websocket_route("/ws/live", websocket_endpoint)

    # Inside _subconscious_cycle(), broadcast events as they fire:
    await live_broadcaster.broadcast({
        "type": "strike",
        "target": p["address"],
        "severity": severity,
        "event": alert["event"],
        "distance": round(dist, 1),
    })

Event types:
- "strike"        Storm centroid within radius of a target
- "brain"         Empire Brain returned a decision
- "manus"         Manus operator fired
- "settlement"    USDC received on Solana wallet
- "dispatch"      Contractor dispatch created
- "outcome"       Claim outcome recorded
- "stats"         Periodic stats snapshot (every 10s)
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — WebSocket connections authenticate via ?token=... query parameter.
# This matches the existing HUB_TOKEN scheme used by HTTP endpoints.
# ─────────────────────────────────────────────────────────────────────────────
# Import HUB_TOKEN lazily to avoid circular import. Set this from hub.py:
#   import empire_live
#   empire_live.HUB_TOKEN = HUB_TOKEN
HUB_TOKEN: str = ""


class LiveBroadcaster:
    """
    Thread-safe broadcaster. Holds a set of connected WebSockets and
    fans out events to all of them. Auto-prunes dead connections.

    Designed for FastAPI's single-event-loop model — no locking needed
    for the asyncio code path, but we still defensively copy the set
    before iterating in case a connection drops mid-broadcast.
    """

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._stats = {
            "connected":         0,
            "total_connections": 0,
            "messages_sent":     0,
            "started_at":        datetime.now(timezone.utc).isoformat(),
        }

    @property
    def stats(self) -> dict:
        return {
            **self._stats,
            "connected": len(self._connections),
        }

    async def connect(self, ws: WebSocket):
        """Register a new client. Caller must have already accepted the WS."""
        self._connections.add(ws)
        self._stats["total_connections"] += 1
        # Send a hello frame so the client knows we're alive
        await self._safe_send(ws, {
            "type": "hello",
            "ts":   datetime.now(timezone.utc).isoformat(),
            "stats": self.stats,
        })

    def disconnect(self, ws: WebSocket):
        """Remove a client (idempotent)."""
        self._connections.discard(ws)

    async def broadcast(self, event: dict):
        """
        Fan an event out to every connected client. Dead connections are
        pruned silently — they're already disconnected, no need to alarm.
        """
        if not self._connections:
            return

        # Stamp the event with a server timestamp
        payload = {
            **event,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        # Copy the set so disconnects during iteration don't blow up
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            ok = await self._safe_send(ws, payload)
            if not ok:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

        self._stats["messages_sent"] += 1

    async def _safe_send(self, ws: WebSocket, payload: dict) -> bool:
        """Send to one client. Returns False if the connection is dead."""
        try:
            if ws.client_state != WebSocketState.CONNECTED:
                return False
            await ws.send_text(json.dumps(payload))
            return True
        except Exception:
            return False


# Singleton — import this everywhere
live_broadcaster = LiveBroadcaster()


# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────
async def websocket_endpoint(websocket: WebSocket, token: str = Query("")):
    """
    Operator WebSocket. Authenticates via ?token= query parameter.
    Streams Subconscious Mind events as they happen.

    Wire-up in hub.py:
        app.add_api_websocket_route("/ws/live", websocket_endpoint)
    """
    # Auth check before accepting the connection
    if not HUB_TOKEN or token != HUB_TOKEN:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    await live_broadcaster.connect(websocket)

    try:
        while True:
            # The client doesn't need to send anything, but we listen for
            # pings or future commands. await receive_text() blocks until
            # the client sends a message or disconnects.
            msg = await websocket.receive_text()
            # Echo a pong for keep-alive
            if msg == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        live_broadcaster.disconnect(websocket)


# ─────────────────────────────────────────────────────────────────────────────
# PERIODIC STATS BROADCAST — pushes a snapshot every 10 seconds so dashboards
# stay current even without strike events firing.
# Wire-up in hub.py startup:
#   asyncio.create_task(stats_heartbeat(lambda: SUBCONSCIOUS_STATE, lambda: SOLANA_STATE))
# ─────────────────────────────────────────────────────────────────────────────
async def stats_heartbeat(
    get_subconscious_state,
    get_solana_state,
    interval: int = 10,
):
    """
    Background task: every `interval` seconds, push a stats snapshot to
    all connected clients. Lets dashboards stay live without polling.
    """
    while True:
        try:
            if live_broadcaster.stats["connected"] > 0:
                sub = get_subconscious_state() or {}
                rev = get_solana_state() or {}
                await live_broadcaster.broadcast({
                    "type":   "stats",
                    "agi": {
                        "running":       sub.get("running", False),
                        "status":        sub.get("last_status", "idle"),
                        "cycles":        sub.get("cycles", 0),
                        "strikes_total": sub.get("strikes_total", 0),
                        "brain_calls":   sub.get("brain_calls", 0),
                        "brain_go":      sub.get("brain_go", 0),
                        "brain_no_go":   sub.get("brain_no_go", 0),
                        "manus_fired":   sub.get("manus_fired", 0),
                    },
                    "revenue": {
                        "total_usdc":      rev.get("total_usdc", 0),
                        "transfers_seen":  rev.get("transfers_seen", 0),
                        "last_transfer":   rev.get("last_transfer"),
                    },
                })
        except Exception as e:
            print(f"[live] heartbeat error: {e}")
        await asyncio.sleep(interval)


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT-SIDE JS — drop this into base_layout() or any view that wants live
# updates. Auto-reconnects on disconnect. Exposes a global window.EMPIRE_LIVE
# event bus that other scripts can subscribe to.
# ─────────────────────────────────────────────────────────────────────────────
LIVE_CLIENT_JS = """
<script>
(function() {
  const TOKEN = window.EMPIRE_TOKEN || localStorage.getItem('hub_token') || '';
  if (!TOKEN) return; // No auth = no live

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const WS_URL = `${protocol}//${location.host}/ws/live?token=${encodeURIComponent(TOKEN)}`;

  // Event bus — other scripts can subscribe via:
  //   window.EMPIRE_LIVE.on('strike', e => { ... });
  const handlers = {};
  const bus = {
    on(type, fn)  { (handlers[type] = handlers[type] || []).push(fn); },
    off(type, fn) { handlers[type] = (handlers[type] || []).filter(f => f !== fn); },
    emit(type, e) { (handlers[type] || []).forEach(f => { try { f(e); } catch {} });
                    (handlers['*']   || []).forEach(f => { try { f(e); } catch {} }); },
  };
  window.EMPIRE_LIVE = bus;

  let ws = null;
  let pingInterval = null;
  let reconnectDelay = 1000;
  let manualClose = false;

  function connect() {
    try {
      ws = new WebSocket(WS_URL);
    } catch (e) {
      console.warn('[empire-live] WebSocket construction failed:', e);
      return scheduleReconnect();
    }

    ws.addEventListener('open', () => {
      console.log('[empire-live] connected');
      reconnectDelay = 1000; // reset on successful connect
      bus.emit('connect', {});
      // Keep-alive ping every 25s
      pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
      }, 25000);
    });

    ws.addEventListener('message', evt => {
      let data;
      try { data = JSON.parse(evt.data); } catch { return; }
      if (!data || !data.type) return;
      bus.emit(data.type, data);
    });

    ws.addEventListener('close', () => {
      console.log('[empire-live] disconnected');
      clearInterval(pingInterval);
      bus.emit('disconnect', {});
      if (!manualClose) scheduleReconnect();
    });

    ws.addEventListener('error', () => {
      // close event will fire too — reconnect handled there
    });
  }

  function scheduleReconnect() {
    setTimeout(connect, reconnectDelay);
    // Exponential backoff capped at 30s
    reconnectDelay = Math.min(reconnectDelay * 1.6, 30000);
  }

  window.addEventListener('beforeunload', () => {
    manualClose = true;
    if (ws) ws.close();
  });

  connect();
})();
</script>
"""
