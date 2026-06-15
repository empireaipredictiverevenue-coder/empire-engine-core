"""
EMPIRE V49 · STORM DISPATCH BRIDGE
====================================
Connects StormTracker alerts to the AI Closer pipeline.

On each tick:
  1. Poll NWS for active severe weather alerts in TX metro zones
  2. For each relevant alert (severe thunderstorm, tornado, hail)
     that matches the Roofing Restoration trigger keywords,
  3. Find warehouse targets in the affected zone from radar_targets
  4. Route each target through the AI Closer for PPC voice dispatch

Runs as a background loop within the hub or as a standalone cron.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

sys.path.insert(0, "/root/empire-v49")

log = logging.getLogger("empire.storm.dispatch")


# Event keyword → niche map for the storm dispatch bridge.
# Mirrors empire_orchestrator._NICHE_MAP so the bridge can infer
# the correct niche from NWS alert types without importing the
# orchestrator (avoids circular dependencies).
_STORM_NICHE_MAP = (
    (("tornado",),                         "Tornado Damage Repair"),
    (("hurricane",),                       "Hurricane Damage Restoration"),
    (("hail",),                            "Hail Damage Repair"),
    (("flood", "flash flood", "water", "heavy rain"),  "Water Damage Restoration"),
    (("thunderstorm", "severe storm", "wind"), "Storm Damage Restoration"),
)
_DEFAULT_STORM_NICHE = "Roofing Restoration"
_GENERIC_STORM_KW = ("storm", "warning", "watch", "advisory")


class StormDispatchBridge:
    """
    Storm alert → AI Closer pipeline for Roofing Restoration and Water Damage Restoration PPC.

    Polls NWS, finds warehouse targets in storm zones, and dispatches
    them through the AI Closer's voice pipeline for live pay-per-call.
    """

    def __init__(
        self,
        storm_tracker=None,
        ai_closer=None,
        get_db=None,
        dispatch_interval: int = 900,  # 15 min between full cycles
    ):
        self.storm_tracker = storm_tracker
        self.ai_closer = ai_closer
        self.get_db = get_db
        self.dispatch_interval = dispatch_interval
        self._last_run: Optional[datetime] = None
        self._seen_alerts: set = set()
        self._dispatched_targets: set = set()  # phone numbers already called this cycle
        self.stats = {
            "cycles": 0,
            "alerts_detected": 0,
            "targets_found": 0,
            "calls_dispatched": 0,
            "errors": 0,
        }

    async def run_cycle(self) -> Dict:
        """
        Run one full storm dispatch cycle:
          1. Fetch active NWS alerts
          2. Filter for roofing-relevant (hail, severe thunderstorm, tornado)
          3. Find warehouse targets in affected zones
          4. Dispatch each through AI Closer
        """
        self.stats["cycles"] += 1
        self._last_run = datetime.now(timezone.utc)

        if not self.storm_tracker:
            from empire_weather_scout import StormTracker
            self.storm_tracker = StormTracker()

        if not self.get_db:
            from supabase import create_client
            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_SERVICE_KEY", "")
            if url and key:
                self.get_db = lambda: create_client(url, key)

        # 1. Fetch alerts
        alerts = await self.storm_tracker.get_active_alerts()
        relevant = self.storm_tracker.filter_relevant(alerts)
        self.stats["alerts_detected"] += len(relevant)

        if not relevant:
            log.info("[storm.dispatch] no relevant alerts — skipping cycle")
            return {"status": "no_alerts", "alerts": 0, "targets": 0, "dispatched": 0}

        log.info(f"[storm.dispatch] {len(relevant)} relevant alerts active")

        # 2. Track which alerts we've already dispatched (dedup across cycles)
        new_alerts = [a for a in relevant if a.get("id") not in self._seen_alerts]
        for a in relevant:
            self._seen_alerts.add(a.get("id"))

        # 2. Find warehouse targets in affected zones
        targets = await self._find_targets(new_alerts or relevant)
        self.stats["targets_found"] += len(targets)

        if not targets:
            log.info("[storm.dispatch] no warehouse targets in affected zones")
            return {"status": "no_targets", "alerts": len(relevant), "targets": 0, "dispatched": 0}

        log.info(f"[storm.dispatch] {len(targets)} warehouse targets found — dispatching")

        # 3. Dispatch each target
        dispatched = 0
        for target in targets:
            try:
                result = await self._dispatch_target(target, relevant)
                if result:
                    dispatched += 1
            except Exception as e:
                log.error(f"[storm.dispatch] target dispatch failed: {e}")
                self.stats["errors"] += 1

        self.stats["calls_dispatched"] += dispatched

        return {
            "status": "ok",
            "alerts": len(relevant),
            "targets": len(targets),
            "dispatched": dispatched,
        }

    async def _find_targets(self, alerts: List[Dict]) -> List[Dict]:
        """
        Find warehouse targets (radar_targets) in the UGC zones affected
        by the current storm alerts. Returns targets with enriched context.
        """
        # Collect all affected UGC zones
        affected_zones = set()
        for alert in alerts:
            props = alert.get("properties") or {}
            geocode = (props.get("geocode") or {}).get("UGC") or []
            affected_zones.update(geocode)

        if not affected_zones or not self.get_db:
            return []

        try:
            db = self.get_db()
            # Query radar_targets for warehouses in TX (skip already-dispatched) (the primary focus zone)
            r = db.table("radar_targets") \
                .select("id,warehouse_name,address,city,state,phone,email,created_at") \
                .in_("state", ["TX", "OK", "LA", "AR", "NM"]) \
                .is_("phone", "neq", None) \
                .limit(50) \
                .execute()
            return r.data or []
        except Exception as e:
            log.warning(f"[storm.dispatch] target query failed: {e}")
            return []

    async def _dispatch_target(self, target: Dict, alerts: List[Dict]) -> bool:
        """Dispatch a single warehouse target through the AI Closer."""
        phone = target.get("phone") or target.get("phone2") or ""
        if phone in self._dispatched_targets:
            log.debug(f"[storm.dispatch] skipping {phone} — already dispatched this cycle")
            return False
        self._dispatched_targets.add(phone)
        if not self.ai_closer:
            # Import lazily — the closer is heavy
            from empire_ai_closer import AICloser
            # Simplified dispatch if closer not wired
            log.info(
                f"[storm.dispatch] would call {target.get('warehouse_name')} "
                f"at {target.get('phone')} — closer not wired yet"
            )
            return False

        # Build a rich alert summary for the closer
        alert_summary = self._build_alert_summary(alerts, target)

        # Infer the correct niche from alert type (Roofing Restoration,
        # Water Damage Restoration, Storm Damage Restoration, etc.)
        niche = self._infer_niche(alert_summary)

        try:
            result = await self.ai_closer.close(
                lead=target,
                alert_summary=alert_summary,
                niche=niche,
            )
            log.info(
                f"[storm.dispatch] {target.get('warehouse_name')}: "
                f"{result.get('action', 'no_action')}"
            )
            return result.get("action") in (
                "agi_stream_call", "static_call", "nurture"
            )
        except Exception as e:
            log.error(f"[storm.dispatch] closer failed for {target.get('id')}: {e}")
            return False

    @staticmethod
    def _build_alert_summary(alerts: List[Dict], target: Dict) -> Dict:
        """Build a concise alert summary for the AI Closer."""
        if not alerts:
            return {
                "event": "Inbound Lead",
                "severity": "Moderate",
                "urgency": "Normal",
                "area": f"{target.get('city', '')}, {target.get('state', '')}".strip(", "),
            }

        # Use the most severe alert
        severity_order = {"Extreme": 3, "Severe": 2, "Moderate": 1, "Minor": 0}
        worst = max(alerts, key=lambda a: severity_order.get(
            (a.get("properties") or {}).get("severity", ""), 0
        ))
        props = worst.get("properties") or {}

        return {
            "event": props.get("event", "Storm Alert"),
            "severity": props.get("severity", "Moderate"),
            "urgency": props.get("urgency", "Expected"),
            "headline": (props.get("headline") or "")[:200],
            "area": props.get("areaDesc", f"{target.get('city', '')}, TX"),
            "sender": props.get("senderName", "NWS"),
        }

    @staticmethod
    def _infer_niche(alert_summary: Dict) -> str:
        """
        Infer the niche from an alert summary event name.
        Matches event keywords against _STORM_NICHE_MAP. Falls back
        to Roofing Restoration (default for storm-triggered leads).
        """
        event = (alert_summary.get("event") or "").lower()
        for keywords, niche in _STORM_NICHE_MAP:
            if any(kw in event for kw in keywords):
                return niche
        if any(kw in event for kw in _GENERIC_STORM_KW):
            return _DEFAULT_STORM_NICHE
        return _DEFAULT_STORM_NICHE

    @staticmethod
    def get_roofing_zones() -> list:
        """Return the UGC zones most relevant for Roofing Restoration PPC.
        These are the DFW metro + surrounding storm corridors."""
        return [
            "TXC113", "TXC121", "TXC439", "TXC085",  # DFW core
            "TXC257", "TXC397", "TXC367", "TXC251",  # DFW outer
            "TXC497", "TXC181", "TXC231", "TXC379",  # North TX
            "TXC201", "TXC157", "TXC339",             # Houston
            "TXC453", "TXC491", "TXC209",             # Austin
            "TXC029", "TXC091", "TXC187",             # San Antonio
        ]

    def snapshot(self) -> Dict:
        """Return stats for dashboard display."""
        return {
            **self.stats,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "interval_seconds": self.dispatch_interval,
            "storm_tracker_wired": self.storm_tracker is not None,
            "ai_closer_wired": self.ai_closer is not None,
        }


# ── CLI ENTRY POINT ─────────────────────────────────────────────────────

async def main_loop():
    """Run the storm dispatch bridge on a loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )
    bridge = StormDispatchBridge()
    log.info("[storm.dispatch] starting main loop (interval=900s)")

    while True:
        try:
            result = await bridge.run_cycle()
            log.info(f"[storm.dispatch] cycle complete: {result}")
        except Exception as e:
            log.error(f"[storm.dispatch] cycle failed: {e}")

        await asyncio.sleep(bridge.dispatch_interval)


if __name__ == "__main__":
    asyncio.run(main_loop())
