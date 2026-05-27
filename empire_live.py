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

# Set lazily by register_live_routes — gives the WS endpoint access to the
# operator_sessions table so per-operator session tokens can authenticate.
_AUTH_ENGINE = None


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
        # SSE fallback: each subscriber owns an asyncio.Queue we push events into.
        self._sse_queues: Set[asyncio.Queue] = set()
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
            "connected":     len(self._connections),
            "sse_connected": len(self._sse_queues),
        }

    # ── SSE subscribe / unsubscribe ─────────────────────────────────────
    def subscribe_sse(self) -> asyncio.Queue:
        """Register an SSE subscriber and return its queue. Caller awaits queue.get()."""
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._sse_queues.add(q)
        self._stats["total_connections"] += 1
        # Hello frame, same shape as WS
        try:
            q.put_nowait({
                "type": "hello",
                "ts":   datetime.now(timezone.utc).isoformat(),
                "stats": self.stats,
            })
        except asyncio.QueueFull:
            pass
        return q

    def unsubscribe_sse(self, q: asyncio.Queue) -> None:
        self._sse_queues.discard(q)

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
        Fan an event out to every connected client (WS + SSE).
        Dead connections are pruned silently.
        """
        if not self._connections and not self._sse_queues:
            return

        # Stamp the event with a server timestamp
        payload = {
            **event,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        # WS fan-out
        dead_ws: list[WebSocket] = []
        for ws in list(self._connections):
            ok = await self._safe_send(ws, payload)
            if not ok:
                dead_ws.append(ws)
        for ws in dead_ws:
            self.disconnect(ws)

        # SSE fan-out — non-blocking put; if a subscriber is too slow we drop
        # rather than backing up the broadcaster.
        for q in list(self._sse_queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop oldest, push newest — backpressure-tolerant
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                except Exception:
                    pass

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
    Operator WebSocket. Authenticates via:
      1. ?token=<session_token> query param (per-operator session)
      2. empire_session cookie (per-operator session, browser default)
      3. ?token=<HUB_TOKEN> (legacy cron / backwards compat)
    Streams Subconscious Mind events as they happen.
    """
    # Resolve a token from query or cookie
    if not token:
        token = websocket.cookies.get("empire_session", "")

    authorized = False
    if token:
        # Legacy hub token check (constant-time-ish)
        if HUB_TOKEN and token == HUB_TOKEN:
            authorized = True
        else:
            # Per-operator session lookup
            ae = globals().get("_AUTH_ENGINE")
            if ae is not None:
                try:
                    import hashlib
                    from datetime import datetime, timezone
                    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                    db = ae.get_db()
                    res = db.table("operator_sessions").select(
                        "operator_id, expires_at, revoked_at"
                    ).eq("token_hash", token_hash).limit(1).execute()
                    if res.data:
                        s = res.data[0]
                        if not s.get("revoked_at"):
                            exp = s["expires_at"]
                            if isinstance(exp, str):
                                from empire_auth import parse_pg_timestamptz
                                exp = parse_pg_timestamptz(exp)
                            if exp >= datetime.now(timezone.utc):
                                authorized = True
                except Exception:
                    authorized = False

    if not authorized:
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
  // Token is optional — server also accepts the empire_session cookie. The
  // cookie is HttpOnly and travels with the WebSocket handshake automatically.
  const TOKEN = window.EMPIRE_TOKEN || localStorage.getItem('hub_token') || '';

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const WS_URL = TOKEN
    ? `${protocol}//${location.host}/ws/live?token=${encodeURIComponent(TOKEN)}`
    : `${protocol}//${location.host}/ws/live`;

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


# ─────────────────────────────────────────────────────────────────────────────
# COMPATIBILITY SHIMS for hub.py
# hub.py imports `LiveBroadcaster` (singleton instance) and `register_live_routes`.
# These wire the existing live_broadcaster + websocket_endpoint to those names.
# ─────────────────────────────────────────────────────────────────────────────

# Alias: hub.py does `LiveBroadcaster()` expecting it to return an instance.
# The real LiveBroadcaster class is defined above; this lets `LiveBroadcaster()`
# return the existing singleton so we don't fragment state.
_LiveBroadcasterClass = LiveBroadcaster

def LiveBroadcaster():  # noqa: F811  — intentional shadow
    """Factory that returns the module-level singleton."""
    return live_broadcaster


def register_live_routes(app, broadcaster=None, hub_token: str = "", auth_engine=None):
    """Register WebSocket route + (optional) HTTP stats endpoint."""
    global HUB_TOKEN, _AUTH_ENGINE
    if hub_token:
        HUB_TOKEN = hub_token
    elif not HUB_TOKEN:
        # Pull from env as fallback
        import os
        HUB_TOKEN = os.environ.get("HUB_TOKEN", "")
    if auth_engine is not None:
        _AUTH_ENGINE = auth_engine

    app.add_api_websocket_route("/ws/live", websocket_endpoint)

    @app.get("/api/v1/live/stats")
    async def _live_stats():
        return live_broadcaster.stats

    # ── SSE fallback for environments where WebSocket Upgrade is blocked ────
    # EventSource in the browser can't set custom headers, so auth uses
    # the same ?token=<session_token|HUB_TOKEN> contract as the WS endpoint.
    from fastapi import Request, HTTPException
    from fastapi.responses import StreamingResponse
    import hashlib

    def _authorize_live_token(token: str) -> bool:
        if not token:
            return False
        if HUB_TOKEN and token == HUB_TOKEN:
            return True
        ae = _AUTH_ENGINE
        if ae is None:
            return False
        try:
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            res = ae.get_db().table("operator_sessions").select(
                "operator_id, expires_at, revoked_at"
            ).eq("token_hash", token_hash).limit(1).execute()
            if not res.data:
                return False
            s = res.data[0]
            if s.get("revoked_at"):
                return False
            exp = s["expires_at"]
            if isinstance(exp, str):
                from empire_auth import parse_pg_timestamptz
                exp = parse_pg_timestamptz(exp)
            return exp >= datetime.now(timezone.utc)
        except Exception:
            return False

    @app.get("/api/v1/live/stream")
    async def _live_stream(request: Request, token: str = ""):
        if not _authorize_live_token(token):
            raise HTTPException(401, "Authentication required")

        q = live_broadcaster.subscribe_sse()

        async def event_source():
            # SSE retry hint — browser auto-reconnects after 3s on drop
            yield "retry: 3000\n\n"
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        payload = await asyncio.wait_for(q.get(), timeout=20.0)
                    except asyncio.TimeoutError:
                        # Heartbeat — keeps proxies from idle-closing the stream
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {json.dumps(payload)}\n\n"
            finally:
                live_broadcaster.unsubscribe_sse(q)

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={
                "Cache-Control":     "no-cache, no-transform",
                "X-Accel-Buffering": "no",   # nginx-style: disable proxy buffering
                "Connection":        "keep-alive",
            },
        )
