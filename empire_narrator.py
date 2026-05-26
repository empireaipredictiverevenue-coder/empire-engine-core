"""
EMPIRE V49 · NARRATOR
======================
Subscribes to LiveBroadcaster events, summarizes them into plain English,
re-broadcasts narrative events that the dashboard can stream via SSE.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

log = logging.getLogger("empire.narrator")


class Narrator:
    """
    Listens to broadcaster events. Converts to short English lines.
    No LLM needed for most events - templated text is faster and cleaner.
    """

    def __init__(self, broadcaster=None):
        self.broadcaster = broadcaster
        self.recent: list = []  # last 50 narrated lines
        self.max_recent = 50

    def add_line(self, line: str, kind: str = "info"):
        item = {
            "t": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "line": line,
        }
        self.recent.append(item)
        self.recent = self.recent[-self.max_recent:]
        if self.broadcaster:
            asyncio.create_task(self._safe_broadcast(item))

    async def _safe_broadcast(self, item: Dict):
        try:
            await self.broadcaster.broadcast({"type": "narrate.event", **item})
        except Exception as e:
            log.debug(f"[narrator] broadcast failed: {e}")

    def narrate_storm_event(self, event: Dict):
        kind = event.get("type")
        if kind == "storm.tick":
            self.add_line(f"Polled NWS - {event.get('new_alerts', 0)} new alerts in TX zones",
                          kind="poll")
        elif kind == "storm.strike":
            alert = event.get("alert") or {}
            self.add_line(
                f"{alert.get('event', 'Storm')} in {alert.get('area', 'TX')} - "
                f"{event.get('targets', 0)} targets found, "
                f"{event.get('enrolled', 0)} enrolled, {event.get('skipped', 0)} skipped",
                kind="strike",
            )
        elif kind == "storm.paused":
            self.add_line(
                f"AUTO-PAUSED: bounce rate {event.get('rate', 0):.1f}% exceeded breaker",
                kind="alert",
            )

    def snapshot(self) -> Dict:
        return {"recent": list(reversed(self.recent[-30:]))}
