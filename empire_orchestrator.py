"""
EMPIRE V49 · STORM ORCHESTRATOR
================================
The closed loop:
  NWS poll → filter → enrich → strike_log → brain gate → email enroll
Replaces the stub orchestrator.
"""
import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable, Any

from empire_weather_scout import StormTracker
from empire_sniper_satellite import SniperSatellite
from empire_state_manager import StateManager
from empire_cinematic_engine import launch_3d_render
from empire_lane_controller import LaneController

log = logging.getLogger("empire.orchestrator")


class StormOrchestrator:
    """
    Main async loop. Wires the scout → satellite → state → activator chain.
    Lives as a background task on the FastAPI app.
    """

    def __init__(
        self,
        get_db: Callable,
        email_engine,
        brain=None,
        drafter=None,
        enricher=None,
        narrator=None,
        broadcaster=None,
        zones: Optional[List[str]] = None,
        poll_interval_sec: int = 300,
        lane_count: int = 6,
        max_sends_hour: int = 50,
        max_sends_day: int = 200,
        bounce_breaker_pct: float = 5.0,
        autonomy_default: bool = True,
    ):
        self.get_db = get_db
        self.email_engine = email_engine
        self.brain = brain
        self.drafter = drafter
        self.enricher = enricher
        self.narrator = narrator
        self.broadcaster = broadcaster
        self.poll_interval = poll_interval_sec
        self.max_sends_hour = max_sends_hour
        self.max_sends_day = max_sends_day
        self.bounce_breaker_pct = bounce_breaker_pct
        self.autonomy_default = autonomy_default

        self.scout = StormTracker(zones=zones)
        self.satellite = SniperSatellite()
        self.state = StateManager(get_db=get_db)
        self.lanes = LaneController(lane_count=lane_count)

        self._stop = asyncio.Event()
        self._processed_alerts: set = set()  # de-dup within process lifetime
        self.last_poll_at: Optional[datetime] = None
        self.last_alert_at: Optional[datetime] = None

    # ── public surface ─────────────────────────────────────────────
    async def poll_loop(self):
        """Run forever — poll NWS, process new alerts."""
        log.info(f"[orchestrator] ONLINE · {self.poll_interval}s interval · {self.lanes.lane_count} lanes")
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception as e:
                log.exception(f"[orchestrator] tick error: {e}")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass

    def stop(self):
        self._stop.set()

    async def tick(self) -> Dict:
        """One full poll cycle. Returns summary dict."""
        self.last_poll_at = datetime.now(timezone.utc)
        self.state.update_state({"last_poll_at": self.last_poll_at.isoformat()})

        # 1. Autonomy gate
        if self.state.is_paused():
            log.info("[orchestrator] autonomy PAUSED, skipping tick")
            return {"status": "paused"}

        # 2. Bounce-rate circuit breaker
        breaker = self._check_bounce_rate()
        if breaker:
            self.state.pause(f"bounce_rate {breaker:.1f}% > {self.bounce_breaker_pct}%")
            await self._broadcast({"type": "storm.paused", "reason": "bounce_breaker", "rate": breaker})
            return {"status": "paused_breaker", "rate": breaker}

        # 3. Poll NWS
        alerts = await self.scout.get_active_alerts()
        relevant = self.scout.filter_relevant(alerts)
        log.info(f"[orchestrator] poll: {len(alerts)} total alerts, {len(relevant)} relevant to TX zones")

        if not relevant:
            return {"status": "ok", "alerts_total": len(alerts), "alerts_relevant": 0}

        # 4. Dedup against in-process cache + dispatch lanes
        new_alerts = []
        for alert in relevant:
            summary = self.scout.alert_summary(alert)
            aid = summary.get("id")
            if aid and aid in self._processed_alerts:
                continue
            new_alerts.append(alert)
            if aid:
                self._processed_alerts.add(aid)

        if not new_alerts:
            return {"status": "ok", "alerts_total": len(alerts), "alerts_relevant": len(relevant), "new": 0}

        self.last_alert_at = datetime.now(timezone.utc)
        self.state.update_state({"last_alert_at": self.last_alert_at.isoformat()})

        # 5. Process each new alert in parallel (bounded by lane_count)
        results = await self.lanes.gather([self.process_alert(a) for a in new_alerts])
        await self._broadcast({"type": "storm.tick", "new_alerts": len(new_alerts), "results": [r if not isinstance(r, Exception) else str(r) for r in results][:5]})

        return {"status": "ok", "alerts_relevant": len(relevant), "new": len(new_alerts), "results": len(results)}

    async def process_alert(self, alert: Dict) -> Dict:
        """Process one NWS alert end-to-end."""
        summary = self.scout.alert_summary(alert)
        log.info(f"[orchestrator] processing alert {summary.get('event')} in {summary.get('area')}")

        centroid = self.scout.extract_centroid(alert)
        if not centroid:
            log.warning(f"[orchestrator] alert {summary.get('id')} has no polygon, skipping")
            return {"alert_id": summary.get("id"), "status": "no_polygon"}
        lat, lon = centroid
        polygon = self.scout.extract_polygon(alert)
        polygon_coords = polygon["coords"] if polygon else None

        # Satellite scan for warehouses in the polygon
        intel = await self.satellite.scan_and_identify(
            lat=lat, lon=lon,
            storm_name=summary.get("event", "Storm"),
            polygon_coords=polygon_coords,
        )

        if intel.get("status") != "STRIKE":
            log.info(f"[orchestrator] no warehouses in alert area {summary.get('area')}")
            return {"alert_id": summary.get("id"), "status": "no_targets"}

        targets = intel.get("targets") or []
        log.info(f"[orchestrator] {len(targets)} candidate targets for {summary.get('event')}")

        enrolled = 0
        skipped = 0
        for target in targets:
            outcome = await self._dispatch_target(target, summary)
            if outcome == "enrolled":
                enrolled += 1
            else:
                skipped += 1
            # Per-target rate-limit check
            if self._hit_send_limit():
                log.warning("[orchestrator] hit send limit, stopping this alert's dispatch")
                break

        await self._broadcast({"type": "storm.strike", "alert": summary, "targets": len(targets), "enrolled": enrolled, "skipped": skipped})
        return {"alert_id": summary.get("id"), "status": "processed", "enrolled": enrolled, "skipped": skipped, "targets": len(targets)}

    async def _dispatch_target(self, target: Dict, alert_summary: Dict) -> str:
        """
        Stage target, log strike, decide GO/NO_GO, enroll.
        Returns dispatch_status string.
        """
        target_id = self.state.stage_target(target, source="storm_trigger")
        strike_id = self.state.log_strike(target_id, alert_summary)

        # Rate gate
        if self._hit_send_limit():
            if strike_id:
                self.state.update_strike_status(strike_id, "skipped_rate")
            return "skipped_rate"

        # Brain gate (real)
        if self.brain:
            decision = await self.brain.decide(target, alert_summary)
            log.info(f"[orchestrator] brain {decision.get('decision')} ({decision.get('confidence', 0):.2f}) for {target.get('warehouse_name')}: {decision.get('reasoning')}")
            if decision.get("decision") != "GO":
                if strike_id:
                    self.state.update_strike_status(strike_id, "skipped_brain")
                return "skipped_brain"
            if decision.get("confidence", 0) < 0.6:
                if strike_id:
                    self.state.update_strike_status(strike_id, "skipped_brain")
                return "skipped_brain_lowconf"

        # Try to enrich email if missing
        target_email = target.get("email")
        if not target_email and target.get("website") and self.enricher:
            try:
                found = await self.enricher.find_email(target["website"], target.get("warehouse_name"))
                if found:
                    target_email = found["email"]
                    target["email"] = target_email
                    log.info(f"[orchestrator] enriched email for {target.get('warehouse_name')}: {target_email} ({found.get('source')})")
            except Exception as e:
                log.warning(f"[orchestrator] enrich failed for {target.get('warehouse_name')}: {e}")

        if not target_email:
            if strike_id:
                self.state.update_strike_status(strike_id, "skipped_dup")
            return "no_email"

        # If we have a drafter, generate a draft instead of direct enrolling
        if self.drafter:
            decision_for_draft = decision if self.brain else {"decision": "GO", "confidence": 0.7, "reasoning": "default"}
            draft = await self.drafter.draft_for_target(
                target=target,
                alert_summary=alert_summary,
                brain_decision=decision_for_draft,
                target_id=target_id,
                strike_id=strike_id,
            )
            if draft:
                if strike_id:
                    self.state.update_strike_status(strike_id, "enrolled")
                return "draft_created"
            else:
                if strike_id:
                    self.state.update_strike_status(strike_id, "error")
                return "draft_failed"

        success = await launch_3d_render(
            details={
                "warehouse_name": target.get("warehouse_name"),
                "address": target.get("address"),
                "lat": target.get("lat"),
                "lon": target.get("lon"),
            },
            email_engine=self.email_engine,
            target_email=target_email,
            storm=alert_summary.get("event"),
        )
        if success:
            if strike_id:
                self.state.update_strike_status(strike_id, "enrolled")
            return "enrolled"
        else:
            if strike_id:
                self.state.update_strike_status(strike_id, "error")
            return "error"

    # ── rate limiting & circuit breaker ────────────────────────
    def _hit_send_limit(self) -> bool:
        """Check email_log against hour/day caps."""
        try:
            db = self.get_db()
            now = datetime.now(timezone.utc)
            hour_ago = (now - timedelta(hours=1)).isoformat()
            day_ago = (now - timedelta(days=1)).isoformat()

            hr = db.table("email_log").select("id", count="exact").gte("created_at", hour_ago).eq("direction", "outbound").execute()
            dy = db.table("email_log").select("id", count="exact").gte("created_at", day_ago).eq("direction", "outbound").execute()
            hr_count = hr.count if hasattr(hr, "count") else len(hr.data or [])
            dy_count = dy.count if hasattr(dy, "count") else len(dy.data or [])

            self.state.update_state({"enrolls_this_hour": hr_count, "enrolls_today": dy_count})
            return hr_count >= self.max_sends_hour or dy_count >= self.max_sends_day
        except Exception as e:
            log.error(f"[orchestrator] rate check failed: {e}")
            return False  # fail-open

    def _check_bounce_rate(self) -> Optional[float]:
        """Return bounce-rate percent if it exceeds breaker, else None."""
        try:
            db = self.get_db()
            day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            total = db.table("email_log").select("id", count="exact").gte("created_at", day_ago).eq("direction", "outbound").execute()
            bounced = db.table("email_log").select("id", count="exact").gte("created_at", day_ago).eq("direction", "bounce").execute()
            t = total.count if hasattr(total, "count") else len(total.data or [])
            b = bounced.count if hasattr(bounced, "count") else len(bounced.data or [])
            if t < 20:
                return None  # too small to judge
            rate = (b / t) * 100
            self.state.update_state({"bounce_rate_pct": round(rate, 2)})
            if rate >= self.bounce_breaker_pct:
                return rate
            return None
        except Exception as e:
            log.error(f"[orchestrator] bounce check failed: {e}")
            return None

    async def _broadcast(self, event: Dict):
        if not self.broadcaster:
            return
        try:
            await self.broadcaster.broadcast(event)
        except Exception:
            pass

    # ── status snapshot ────────────────────────────────────────
    def snapshot(self) -> Dict:
        state = self.state.get_state() or {}
        return {
            "autonomy_enabled": state.get("autonomy_enabled", self.autonomy_default),
            "paused_reason": state.get("paused_reason"),
            "last_poll_at": state.get("last_poll_at"),
            "last_alert_at": state.get("last_alert_at"),
            "enrolls_this_hour": state.get("enrolls_this_hour", 0),
            "enrolls_today": state.get("enrolls_today", 0),
            "bounce_rate_pct": float(state.get("bounce_rate_pct", 0) or 0),
            "max_sends_hour": self.max_sends_hour,
            "max_sends_day": self.max_sends_day,
            "bounce_breaker_pct": self.bounce_breaker_pct,
            "lanes_active": self.lanes.active,
            "lanes_completed": self.lanes.completed,
            "lanes_failed": self.lanes.failed,
            "processed_alerts_session": len(self._processed_alerts),
        }


# ─────────────────────────────────────────────────────────────────────
# Route registration — mount on FastAPI app
# ─────────────────────────────────────────────────────────────────────
def register_storm_routes(app, orchestrator: StormOrchestrator, require_auth):
    from fastapi import Depends, Body

    @app.get("/api/v1/storm/status")
    async def storm_status(auth: bool = Depends(require_auth)):
        return orchestrator.snapshot()

    @app.post("/api/v1/storm/pause")
    async def storm_pause(reason: str = "operator pause", auth: bool = Depends(require_auth)):
        orchestrator.state.pause(reason)
        return {"ok": True, "paused": True, "reason": reason}

    @app.post("/api/v1/storm/resume")
    async def storm_resume(auth: bool = Depends(require_auth)):
        orchestrator.state.resume()
        return {"ok": True, "paused": False}

    @app.post("/api/v1/storm/tick")
    async def storm_tick(auth: bool = Depends(require_auth)):
        result = await orchestrator.tick()
        return {"ok": True, "result": result}

    @app.post("/api/v1/storm/fire-test")
    async def storm_fire_test(auth: bool = Depends(require_auth)):
        """Synthetic alert — exercises full pipeline against Dallas centroid."""
        fake_alert = {
            "id": f"test-{datetime.now(timezone.utc).isoformat()}",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-97.0, 32.6], [-96.5, 32.6], [-96.5, 33.0], [-97.0, 33.0], [-97.0, 32.6],
                ]],
            },
            "properties": {
                "id": f"test-{datetime.now(timezone.utc).isoformat()}",
                "event": "Severe Thunderstorm Warning",
                "severity": "Severe",
                "urgency": "Immediate",
                "headline": "TEST FIRE — synthetic alert",
                "areaDesc": "Dallas County, TX (TEST)",
                "geocode": {"UGC": ["TXC113"]},
                "senderName": "EmpireAI-v49-test",
            },
        }
        result = await orchestrator.process_alert(fake_alert)
        return {"ok": True, "result": result}

    log.info("[orchestrator] Routes registered · /api/v1/storm/{status,pause,resume,tick,fire-test}")

from empire_analytics import log_event

def finalize_dispatch_and_log(lead, storm_type):
    # 1. Trigger the dispatch
    dispatch_result = initiate_storm_call(lead['phone'], storm_type)
    
    # 2. Log to the Analytics Engine for the dashboard
    log_event(
        event_type="DISPATCH_SENT",
        dispatch_id=lead['id'], # Assuming this maps to your dispatch/lead ID
        metadata={
            "storm_type": storm_type,
            "estimated_value": 500,
            "conversion_probability": 0.85
        }
    )
    print(f"[SUCCESS] Dispatch logged to Empire Analytics.")

def track_radar_strike(lat, lon, storm_intensity):
    # Log the strike to your radar_targets table for visual mapping
    log_event(
        event_type="RADAR_STRIKE",
        dispatch_id="SYSTEM_EVENT",
        metadata={
            "lat": lat,
            "lon": lon,
            "intensity": storm_intensity,
            "timestamp": "2026-05-27T01:21:00Z"
        }
    )
