"""
EMPIRE V49 · EVENT BUS
=======================
Centralized event system for the entire fleet. Replaces ad-hoc agent_activity
inserts with a unified pub/sub bus that:

  - emit(event_type, **data) — fire an event from anywhere
  - on(event_type, handler)  — subscribe a handler
  - Persists to Supabase agent_activity table (async, best-effort)
  - Broadcasts to WebSocket clients via empire_live.py's LiveBroadcaster
  - Forwards to configured webhook URLs for external integration
  - Emits standard fleet event types with consistent schema

Usage:
    from empire_event_bus import bus

    # Fire an event
    await bus.emit("brain.decision", decision="GO", confidence=0.8, ...)

    # Subscribe (e.g. in hub.py startup)
    bus.on("brain.decision", my_handler)

    # Get a snapshot for dashboards
    events = bus.recent(limit=10)
"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

log = logging.getLogger("empire.event_bus")

# ── Config ──────────────────────────────────────────────────────────────
MAX_RECENT_EVENTS = 500       # In-memory rolling window
MAX_EVENT_DATA_CHARS = 4000   # Truncate event data for memory
PERSIST_BATCH_SEC = 5.0       # Batch persistence writes every N seconds
WEBHOOK_TIMEOUT_SEC = 10.0
DEFAULT_WEBHOOK_URLS: List[str] = []  # Set via env EMPIRE_EVENT_WEBHOOKS

# ── Standard Event Types ────────────────────────────────────────────────
# These are the canonical event types the fleet should use.
# Any agent can emit custom types, but these are guaranteed to have
# subscribers on the bus.

STD_EVENT_TYPES: Set[str] = {
    # LLM & Brain
    "llm.call",              # LLM call completed (cached or fresh)
    "brain.decision",        # Brain GO/NO_GO decision
    "brain.memory.retrieve", # Brain memory retrieval
    "brain.memory.record",   # Brain memory recording
    "brain.learning.tune",   # Brain learning urgency tuning
    # Pipeline
    "pipeline.stage",        # Pipeline stage transition
    "pipeline.outreach",     # Outreach sent
    "pipeline.dispatch",     # Dispatch to contractor
    "pipeline.enroll",       # Lead enrolled
    # Agents
    "agent.status",          # Agent online/offline/error
    "agent.cycle",           # Agent cycle complete
    "agent.error",           # Agent error
    # System
    "system.boot",           # Hub startup
    "system.shutdown",       # Hub shutdown
    "system.error",          # System-level error
    "storm.alert",           # Storm alert processed
    "storm.strike",          # Storm strike dispatched
    # Events from event bus itself
    "bus.overflow",          # Recent events buffer overflow
    "bus.webhook_failed",    # Webhook delivery failure
}

# ── Event Schema ────────────────────────────────────────────────────────
# Every event has this shape:
#   {
#       "id": str(uuid),
#       "event_type": str,
#       "source": str,          # agent/hub/module name
#       "timestamp": str,       # ISO 8601
#       "data": dict,           # Event-specific payload
#       "severity": str,        # info, warn, error, critical
#   }


class EventBus:
    """
    Singleton in-memory event bus with:

      - Async pub/sub (emit / on / off)
      - Rolling window of recent events (MAX_RECENT_EVENTS)
      - Background batch persistence to Supabase agent_activity
      - WebSocket broadcast via LiveBroadcaster
      - Webhook forwarding
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._recent: deque = deque(maxlen=MAX_RECENT_EVENTS)
        self._persist_queue: asyncio.Queue = asyncio.Queue()
        self._persist_task: Optional[asyncio.Task] = None
        self._broadcaster: Any = None  # LiveBroadcaster instance
        self._get_db: Optional[Callable] = None
        self._webhook_urls: List[str] = list(DEFAULT_WEBHOOK_URLS)
        self._started = False
        self._emit_count = 0
        self._error_count = 0

        # Parse webhook URLs from env
        env_webhooks = os.environ.get("EMPIRE_EVENT_WEBHOOKS", "")
        if env_webhooks:
            self._webhook_urls = [u.strip() for u in env_webhooks.split(",") if u.strip()]

    # ── Lifecycle ───────────────────────────────────────────────────────

    def start(
        self,
        *,
        get_db: Optional[Callable] = None,
        broadcaster: Optional[Any] = None,
    ) -> None:
        """Start the background persistence loop. Call once at hub boot."""
        if self._started:
            return
        self._get_db = get_db
        self._broadcaster = broadcaster
        self._started = True

        loop = asyncio.get_event_loop()
        self._persist_task = loop.create_task(
            self._persist_loop(),
            name="event-bus-persist",
        )
        log.info("[event_bus] started — persistence loop online")

    async def stop(self) -> None:
        """Flush remaining events and stop the persistence loop."""
        self._started = False
        if self._persist_task:
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass
        # Flush any remaining events
        await self._flush_persist_queue()
        log.info("[event_bus] stopped — queue flushed")

    # ── Pub/Sub ─────────────────────────────────────────────────────────

    def on(self, event_type: str, handler: Callable) -> None:
        """
        Subscribe *handler* to *event_type*.

        Handler signature: async def handler(event: dict) -> None
        """
        self._subscribers[event_type].append(handler)
        log.debug(f"[event_bus] subscriber added for '{event_type}'")

    def off(self, event_type: str, handler: Callable) -> None:
        """Unsubscribe *handler* from *event_type*."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    async def emit(
        self,
        event_type: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        source: str = "unknown",
        severity: str = "info",
    ) -> None:
        """
        Fire an event into the bus.

        This is non-blocking — subscribers run concurrently, persistence is
        batched, and failures are logged but never raised.

        Args:
            event_type: Canonical type (e.g. 'brain.decision', 'agent.status')
            data: Event-specific payload dict
            source: Module/agent name that emitted the event
            severity: info, warn, error, critical
        """
        event = {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": self._truncate_data(data or {}),
            "severity": severity,
        }

        self._emit_count += 1

        # ── 1. Store in rolling window ────────────────────────────────
        try:
            self._recent.append(event)
        except Exception:
            pass

        # ── 2. Notify subscribers (concurrent, best-effort) ───────────
        handlers = list(self._subscribers.get(event_type, []))
        # Also notify wildcard subscribers
        handlers.extend(self._subscribers.get("*", []))
        if handlers:
            loop = asyncio.get_event_loop()
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        loop.create_task(self._safe_call(handler, event))
                    else:
                        handler(event)  # sync handler
                except Exception as e:
                    log.debug(f"[event_bus] handler error for '{event_type}': {e}")

        # ── 3. Queue for persistence (batched) ────────────────────────
        if self._get_db:
            try:
                self._persist_queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("[event_bus] persist queue full — dropping event")

        # ── 4. WebSocket broadcast ────────────────────────────────────
        if self._broadcaster is not None:
            try:
                self._broadcaster.broadcast({
                    "type": f"event.{event_type}",
                    "event_type": event_type,
                    "severity": severity,
                    "data": data,
                    "timestamp": event["timestamp"],
                })
            except Exception as e:
                log.debug(f"[event_bus] broadcast error: {e}")

        # ── 5. Webhook forwarding (only warn/error/critical) ──────────
        if self._webhook_urls and severity in ("warn", "error", "critical"):
            loop = asyncio.get_event_loop()
            for url in self._webhook_urls:
                loop.create_task(self._send_webhook(url, event))

    # ── Queries ─────────────────────────────────────────────────────────

    def recent(self, event_type: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Return recent events, optionally filtered by type."""
        if event_type:
            filtered = [e for e in self._recent if e["event_type"] == event_type]
            return filtered[:limit]
        return list(self._recent)[-limit:]

    def count_by_type(self, since_sec: int = 300) -> Dict[str, int]:
        """Count events by type in the last N seconds."""
        cutoff = time.time() - since_sec
        counts: Dict[str, int] = {}
        for event in self._recent:
            try:
                ts = datetime.fromisoformat(event["timestamp"]).timestamp()
                if ts >= cutoff:
                    counts[event["event_type"]] = counts.get(event["event_type"], 0) + 1
            except Exception:
                pass
        return counts

    def metrics(self) -> Dict[str, Any]:
        """Return event bus metrics."""
        return {
            "total_emitted": self._emit_count,
            "errors": self._error_count,
            "recent_count": len(self._recent),
            "subscriber_count": sum(len(v) for v in self._subscribers.values()),
            "subscriber_types": len(self._subscribers),
            "persist_queue_size": self._persist_queue.qsize(),
            "webhooks_configured": len(self._webhook_urls),
        }

    # ── Internals ───────────────────────────────────────────────────────

    async def _safe_call(self, handler: Callable, event: Dict) -> None:
        """Call a subscriber handler, logging but never raising errors."""
        try:
            await handler(event)
        except Exception as e:
            self._error_count += 1
            log.debug(f"[event_bus] subscriber error: {e}")

    async def _persist_loop(self) -> None:
        """Background loop: batch-persist events to agent_activity."""
        while self._started:
            try:
                await asyncio.sleep(PERSIST_BATCH_SEC)
                await self._flush_persist_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(f"[event_bus] persist loop error: {e}")

    async def _flush_persist_queue(self) -> None:
        """Flush all queued events to Supabase agent_activity."""
        if not self._get_db:
            return
        batch: List[Dict] = []
        while not self._persist_queue.empty():
            try:
                batch.append(self._persist_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if not batch:
            return
        try:
            db = self._get_db()
            rows = []
            for event in batch:
                rows.append({
                    "agent_name": f"event.{event['event_type']}",
                    "run_id": event["id"],
                    "started_at": event["timestamp"],
                    "finished_at": event["timestamp"],
                    "status": event["severity"],
                    "rows_seen": 0,
                    "rows_processed": 0,
                    "rows_errored": 0,
                    "summary": json.dumps({
                        "event_type": event["event_type"],
                        "source": event["source"],
                        "data": event.get("data", {}),
                    }, default=str)[:4000],
                })
            db.table("agent_activity").insert(rows).execute()
        except Exception as e:
            self._error_count += 1
            log.debug(f"[event_bus] batch persist failed ({len(batch)} events): {e}")

    async def _send_webhook(self, url: str, event: Dict) -> None:
        """Forward a warn/error/critical event to a webhook URL."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SEC) as client:
                r = await client.post(
                    url,
                    json={
                        "event_type": event["event_type"],
                        "severity": event["severity"],
                        "source": event["source"],
                        "timestamp": event["timestamp"],
                        "data": event.get("data", {}),
                    },
                    headers={"User-Agent": "EmpireAI-EventBus/1.0"},
                )
                if r.status_code >= 300:
                    log.debug(f"[event_bus] webhook {url} returned {r.status_code}")
        except Exception as e:
            log.debug(f"[event_bus] webhook {url} failed: {e}")
            # Emit a bus event about the failure
            await self.emit(
                "bus.webhook_failed",
                data={"url": url, "event_type": event["event_type"], "error": str(e)[:200]},
                source="event_bus",
                severity="warn",
            )

    @staticmethod
    def _truncate_data(data: Dict) -> Dict:
        """Truncate long string values in event data."""
        if not data:
            return data
        result = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > MAX_EVENT_DATA_CHARS:
                result[k] = v[:MAX_EVENT_DATA_CHARS] + "...[truncated]"
            elif isinstance(v, dict):
                result[k] = EventBus._truncate_data(v)
            else:
                result[k] = v
        return result


# ── Singleton ───────────────────────────────────────────────────────────
bus: EventBus = EventBus()


# ── Hub Route Registration ──────────────────────────────────────────────

def register_event_bus_routes(
    app,
    require_auth: Callable,
    event_bus: Optional[EventBus] = None,
) -> None:
    """Wire event bus query + emit endpoints into the hub."""
    eb = event_bus or bus
    from fastapi import Depends, Query, Request

    @app.get("/api/v1/events/recent")
    async def get_recent_events(
        event_type: Optional[str] = Query(None),
        limit: int = Query(20, ge=1, le=200),
        auth: bool = Depends(require_auth),
    ):
        return {"events": eb.recent(event_type=event_type, limit=limit)}

    @app.get("/api/v1/events/stats")
    async def get_event_stats(
        since_sec: int = Query(300, ge=60, le=86400),
        auth: bool = Depends(require_auth),
    ):
        return {
            "counts_by_type": eb.count_by_type(since_sec=since_sec),
            "metrics": eb.metrics(),
        }

    @app.post("/api/v1/events/emit")
    async def emit_event(
        request: Request,
        auth: bool = Depends(require_auth),
    ):
        """Emit an event into the hub's event bus from an external caller.

        Body: {
          event_type: str (required),
          data: dict (optional),
          source: str (optional, default "api"),
          severity: str (optional, default "info")
        }
        """
        try:
            body = await request.json()
        except Exception:
            return {"ok": False, "error": "invalid_json"}

        event_type = body.get("event_type", "").strip()
        if not event_type:
            return {"ok": False, "error": "event_type is required"}

        await eb.emit(
            event_type,
            data=body.get("data", {}),
            source=body.get("source", "api"),
            severity=body.get("severity", "info"),
        )
        return {"ok": True, "event_type": event_type}

    log.info("[event_bus] routes registered · /api/v1/events/{recent,stats,emit}")


# ── Convenience Helpers ─────────────────────────────────────────────────

def emit_sync(event_type: str, **data) -> None:
    """
    Fire an event from a synchronous context.

    Creates a task in the running event loop. If no loop is running,
    the event is silently dropped (logged at debug).
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(bus.emit(event_type, data=data, source="sync"))
    except RuntimeError:
        log.debug(f"[event_bus] sync emit skipped (no running loop): {event_type}")
