"""
EMPIRE V49 · PPC DISPATCHER
============================
Always-on PPC (pay-per-call) lead dispatch for emergency-triggered niches.

Unlike StormDispatchBridge (which waits for NWS weather alerts), this
dispatcher polls the enriched_leads pipeline for pending leads in
PPC-ready niches and routes them through the AI Closer for voice dispatch.

Designed as the Plumbing PPC proof of concept — no storm correlation
required, just "Emergency, burst pipe" = 24/7 dispatch trigger.

Runs as a background loop within the hub.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

sys.path.insert(0, "/root/empire-v49")

log = logging.getLogger("empire.ppc.dispatch")


# Niches eligible for always-on PPC dispatch (no storm correlation needed)
# Each entry: niche_name → list of sub_niches
# Water Damage Restoration is always-on for non-storm events (burst pipes,
# sewer backup, etc.); storm-triggered water damage goes through StormDispatchBridge.
_EMERGENCY_PPC_NICHES = {
    "Home Services": ["Plumbing", "Water Damage Restoration"],
}

# Sub-niche → niche mapping for PPC dispatch routing
_SUB_NICHE_TO_NICHE = {
    "Plumbing": "Home Services",
    "Water Damage Restoration": "Home Services",
}


class PpcDispatcher:
    """
    Always-on PPC lead dispatch for emergency-triggered niches.

    On each tick:
      1. Poll enriched_leads for pending leads in PPC-ready niches
      2. Score + route each through the AI Closer for voice dispatch
      3. Track dispatched leads to prevent duplicate calls

    Separate from StormDispatchBridge — this doesn't wait for weather.
    """

    def __init__(
        self,
        ai_closer=None,
        get_db=None,
        dispatch_interval: int = 120,  # 2 min — emergency niches need speed
        min_score_threshold: float = 0.35,
        max_per_cycle: int = 20,
    ):
        self.ai_closer = ai_closer
        self._get_db = get_db
        self.dispatch_interval = dispatch_interval
        self.min_score_threshold = min_score_threshold
        self.max_per_cycle = max_per_cycle
        self._dispatched_ids: Set[str] = set()  # IDs called this session
        self._last_run: Optional[datetime] = None
        self.stats = {
            "cycles": 0,
            "leads_found": 0,
            "leads_routed": 0,
            "calls_placed": 0,
            "errors": 0,
        }

    @property
    def get_db(self):
        if self._get_db is None:
            from supabase import create_client
            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_SERVICE_KEY", "")
            if url and key:
                self._get_db = lambda: create_client(url, key)
        return self._get_db

    async def run_cycle(self) -> Dict:
        """Run one full PPC dispatch cycle."""
        self.stats["cycles"] += 1
        self._last_run = datetime.now(timezone.utc)

        if not self.get_db:
            log.warning("[ppc.dispatch] no DB connection — skipping cycle")
            return {"status": "no_db", "leads": 0, "routed": 0}

        try:
            db = self.get_db()
        except Exception:
            log.warning("[ppc.dispatch] DB init failed — skipping")
            return {"status": "no_db", "leads": 0, "routed": 0}

        # 1. Poll for pending leads in PPC-ready niches
        leads = await self._fetch_pending_leads(db)
        self.stats["leads_found"] += len(leads)

        if not leads:
            return {"status": "no_leads", "leads": 0, "routed": 0}

        log.info(f"[ppc.dispatch] {len(leads)} pending PPC leads — routing")

        # 2. Route each lead through the closer
        routed = 0
        calls_placed = 0

        for lead in leads:
            lead_id = str(lead.get("id") or lead.get("lead_id") or "")
            if lead_id in self._dispatched_ids:
                continue
            self._dispatched_ids.add(lead_id)

            try:
                result = await self._route_lead(lead, db)
                if result:
                    routed += 1
                    if result.get("action") in ("agi_stream_call", "static_call"):
                        calls_placed += 1
            except Exception as e:
                log.warning(f"[ppc.dispatch] lead {lead_id[:8]} routing failed: {e}")
                self.stats["errors"] += 1

        self.stats["leads_routed"] += routed
        self.stats["calls_placed"] += calls_placed

        return {
            "status": "ok",
            "leads": len(leads),
            "routed": routed,
            "calls_placed": calls_placed,
        }

    async def _fetch_pending_leads(self, db) -> List[Dict]:
        """Fetch pending leads for PPC-ready niches from enriched_leads."""
        try:
            # Flatten all sub-niches across all PPC niches
            target_sub_niches = []
            for niche, sub_niches in _EMERGENCY_PPC_NICHES.items():
                target_sub_niches.extend(sub_niches)

            r = db.table("enriched_leads") \
                .select("id,radar_target_id,warehouse_name,address,city,state,phone,email,niche,sub_niche,created_at") \
                .eq("status", "pending_outreach") \
                .in_("sub_niche", target_sub_niches) \
                .order("created_at", desc=False) \
                .limit(self.max_per_cycle) \
                .execute()
            return r.data or []
        except Exception as e:
            log.debug(f"[ppc.dispatch] fetch error: {e}")
            return []

    async def _route_lead(self, lead: Dict, db) -> Optional[Dict]:
        """Route a single lead through the AI Closer for voice dispatch."""
        phone = lead.get("phone") or ""
        if not phone:
            return None

        # Determine the correct niche from the lead's sub_niche
        sub_niche = lead.get("sub_niche") or ""
        niche = _SUB_NICHE_TO_NICHE.get(sub_niche, "Home Services")

        if self.ai_closer:
            try:
                result = await self.ai_closer.close(
                    lead=lead,
                    niche=niche,
                )
                action = result.get("action", "")
                log.info(
                    f"[ppc.dispatch] {lead.get('warehouse_name', '?')} → "
                    f"{action}"
                )
                return result
            except Exception as e:
                log.error(f"[ppc.dispatch] closer failed: {e}")
                return None
        else:
            # Dry-run mode — log without changing lead status
            # Uses meta flag so the lead stays in the pipeline if dispatcher restarts
            log.info(
                f"[ppc.dispatch] DRY-RUN: would call "
                f"{lead.get('warehouse_name', '?')} at {phone[:6]}****"
            )
            # Just tag in meta — don't change status (avoids orphaned leads)
            try:
                existing = lead.get("meta") or {}
                existing["ppc_dispatched_at"] = datetime.now(timezone.utc).isoformat()
                existing["ppc_dispatch_mode"] = "dry_run"
                db.table("enriched_leads").update({
                    "meta": existing,
                }).eq("id", lead["id"]).execute()
            except Exception:
                pass
            return {"action": "dry_run"}

    def snapshot(self) -> Dict:
        """Return stats for dashboard display."""
        return {
            **self.stats,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "interval_seconds": self.dispatch_interval,
            "min_score_threshold": self.min_score_threshold,
            "dispatched_ids_tracked": len(self._dispatched_ids),
            "ai_closer_wired": self.ai_closer is not None,
        }


# ── CLI ENTRY POINT (standalone test) ───────────────────────────────

async def main_loop():
    """Run the PPC dispatcher on a loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )
    dispatcher = PpcDispatcher()
    log.info("[ppc.dispatch] starting main loop (interval=120s)")

    while True:
        try:
            result = await dispatcher.run_cycle()
            if result.get("leads", 0) > 0:
                log.info(f"[ppc.dispatch] cycle complete: {result}")
        except Exception as e:
            log.error(f"[ppc.dispatch] cycle failed: {e}")

        await asyncio.sleep(dispatcher.dispatch_interval)


if __name__ == "__main__":
    asyncio.run(main_loop())
