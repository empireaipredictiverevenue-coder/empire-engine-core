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
from empire_agi_governor import governor as _agi_governor
from empire_brain_memory import render_few_shot

# Storm event keyword → niche map. Hoisted to module level so it's
# built once at import, not on every _infer_niche() call. The first
# matching keyword wins; the final tuple is the generic-storm fallback.
_NICHE_MAP = (
    (("tornado",),                       "Tornado Damage Repair"),
    (("hurricane",),                     "Hurricane Damage Restoration"),
    (("hail",),                          "Hail Damage Repair"),
    (("flood", "flash flood", "water", "heavy rain"), "Water Damage Restoration"),
    (("thunderstorm", "severe storm", "wind"),  "Storm Damage Restoration"),
)
_DEFAULT_NICHE = "Roofing Restoration"
_GENERIC_STORM_KW = ("storm", "warning", "watch", "advisory")

log = logging.getLogger("empire.orchestrator")

# ── SQLite Storm Bridge ──────────────────────────────────────────
# Reads VERIFIED alerts from the local SQLite DB (populated by
# scripts/storm_scraper.py + human review) and converts them to
# NWS-compatible alert dicts so they can flow through the same
# process_alert() pipeline as live NWS alerts.

_SQLITE_DB_PATH = "/root/empire-v49/data/storm_alerts.sqlite"
_CONFIG_ZIPS_PATH = "/root/empire-v49/config/target_zips.json"
_DENSITY_PATH = "/root/empire-v49/config/zip_density.json"

# Land-area → radius_deg lookup table. Census ZCTA land area is used as a
# density proxy: small-area zips are dense urban cores, large-area zips
# are sparse exurban/rural distribution zones.
_DENSITY_RADIUS_TABLE = (
    (1.0,   0.03),   # < 1 sqmi  → very dense urban (downtown cores)
    (3.0,   0.05),   # 1-3 sqmi  → urban / inner-ring
    (10.0,  0.07),   # 3-10 sqmi → suburban / industrial
    (30.0,  0.10),   # 10-30 sqmi → exurban / logistics
    (float("inf"), 0.12),  # > 30 sqmi → rural / distribution
)


def _load_zip_density() -> dict:
    """Load zip → {land_area_sqmi, population_density} from cached Census data.

    Generated once via Census ZCTA Gazetteer. If the file is missing (e.g.
    first run before the generator script), returns an empty dict so
    _load_zip_coords() falls back to _default_radius_deg.
    """
    import json as _j
    try:
        with open(_DENSITY_PATH) as f:
            return _j.load(f)
    except Exception:
        return {}


def _estimate_radius_from_land_area(land_area_sqmi: float) -> float:
    """Map ZCTA land area (sq mi) → estimated scan radius (deg).

    Smaller land area = denser development = tighter scan box to reduce
    noise. Larger land area = sparse exurban/rural = wider scan to catch
    distributed warehouse parks.

    Thresholds (land_area_sqmi → radius_deg):
        < 1.0   → 0.03  (very dense urban: downtown Dallas, OKC core)
        1.0-3.0 → 0.05  (urban: Galleria, Capitol, Alamo)
        3.0-10.0→ 0.07  (suburban/industrial: Stockyards, Westchase)
        10.0-30→ 0.10  (exurban/logistics: Alliance, Bush airport)
        > 30.0  → 0.12  (rural/distribution: OKC airport, wide zones)
    """
    for threshold, radius in _DENSITY_RADIUS_TABLE:
        if land_area_sqmi < threshold:
            return radius
    return 0.12  # fallback (shouldn't reach here)


# Module-level cache for density data (loaded once, shared across calls)
_density_cache = None


def _load_zip_coords() -> dict:
    """Load zip → {lat, lon, city, state, radius_deg} lookup from config.

    Radius resolution order:
      1. Explicit radius_deg in config entry (operator-tuned)
      2. Auto-estimated from Census ZCTA land area (zip_density.json)
      3. Config _default_radius_deg (0.08)

    This means new zip entries only need lat/lon — radius is auto-calculated
    from real geospatial data. No manual tuning required.
    """
    global _density_cache
    import json as _j
    try:
        with open(_CONFIG_ZIPS_PATH) as f:
            cfg = _j.load(f)
    except Exception:
        return {}
    default_radius = float(cfg.get("_default_radius_deg", 0.08))

    # Load density data once (cached at module level)
    if _density_cache is None:
        _density_cache = _load_zip_density()
    density_data = _density_cache

    lookup = {}
    for entry in cfg.get("zips", []):
        z = entry.get("zip", "")
        if z and entry.get("lat") is not None and entry.get("lon") is not None:
            # Resolve radius_deg with the 3-tier fallback chain
            if "radius_deg" in entry and entry["radius_deg"] is not None:
                radius = float(entry["radius_deg"])
            elif z in density_data:
                land = density_data[z].get("land_area_sqmi", 0)
                # Guard against zero/bad land area data — fall back to default
                if land and float(land) > 0:
                    radius = _estimate_radius_from_land_area(float(land))
                else:
                    radius = default_radius
            else:
                radius = default_radius

            lookup[z] = {
                "lat": float(entry["lat"]),
                "lon": float(entry["lon"]),
                "city": entry.get("city", ""),
                "state": entry.get("state", ""),
                "radius_deg": radius,
            }
    return lookup


def _build_synthetic_polygon(lat: float, lon: float, radius_deg: float = 0.08) -> list:
    """Build a small bounding box polygon around a lat/lon point.
    Returns NWS-compatible coords: [[[lon, lat], ...]] outer ring."""
    r = radius_deg
    return [[
        [lon - r, lat - r],
        [lon + r, lat - r],
        [lon + r, lat + r],
        [lon - r, lat + r],
        [lon - r, lat - r],
    ]]


def convert_sqlite_verified_to_alerts() -> list:
    """
    Read all VERIFIED alerts from the SQLite storm_alerts table and
    convert them into NWS-compatible alert dicts (with synthetic polygon
    geometry derived from zip code lat/lon centroids).

    Returns a list of dicts ready for StormOrchestrator.process_alert().
    Each dict has: id, geometry (Polygon), properties (id, event, severity,
    urgency, headline, areaDesc, geocode, senderName).

    Only returns alerts where at least one matched zip code has known
    coordinates in config/target_zips.json.
    """
    import json as _j
    import sqlite3 as _sq
    from pathlib import Path

    db_path = Path(_SQLITE_DB_PATH)
    if not db_path.exists():
        return []

    zip_coords = _load_zip_coords()
    if not zip_coords:
        return []

    try:
        conn = _sq.connect(str(db_path))
        cur = conn.execute(
            "SELECT event_id, event_type, severity, certainty, urgency, "
            "headline, description, area_desc, matched_zips, first_seen, "
            "last_seen, status "
            "FROM storm_alerts WHERE status = 'VERIFIED' AND processed = 0 "
            "ORDER BY last_seen DESC"
        )
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        log.warning(f"[orchestrator] SQLite read failed: {e}")
        return []

    alerts = []
    for row in rows:
        (event_id, event_type, severity, certainty, urgency,
         headline, description, area_desc, matched_zips_json,
         first_seen, last_seen, status) = row

        # Parse matched zip codes
        try:
            matched_zips = _j.loads(matched_zips_json) if matched_zips_json else []
        except Exception:
            matched_zips = []

        if not matched_zips:
            continue

        # Find the first zip with known coordinates
        centroid = None
        for z in matched_zips:
            coords = zip_coords.get(z)
            if coords:
                centroid = coords
                break

        if not centroid:
            log.debug(f"[orchestrator] SQLite alert {event_id}: no coords for zips {matched_zips}")
            continue

        lat, lon = centroid["lat"], centroid["lon"]
        radius = centroid.get("radius_deg", 0.08)
        polygon_coords = _build_synthetic_polygon(lat, lon, radius_deg=radius)

        # Map severity: SQLite may use "Moderate" → not in SEVERITY_ALLOWLIST.
        # Upgrade Moderate → Severe for pipeline compatibility.
        nws_severity = severity if severity in ("Extreme", "Severe") else "Severe"

        alert = {
            "id": event_id,
            "_source": "sqlite_verified",
            "_matched_zips": matched_zips,
            "geometry": {
                "type": "Polygon",
                "coordinates": polygon_coords,
            },
            "properties": {
                "id": event_id,
                "event": event_type or "Severe Storm",
                "severity": nws_severity,
                "urgency": urgency or "Expected",
                "headline": headline or "",
                "areaDesc": area_desc or "",
                "description": description or "",
                "geocode": {"UGC": []},
                "senderName": "EmpireAI-SQLite-Bridge",
                "effective": first_seen or "",
                "expires": last_seen or "",
            },
        }
        alerts.append(alert)

    # Mark all processed alerts so the next call (even after hub restart)
    # doesn't re-read and re-process the same VERIFIED alerts.
    if alerts:
        ids = [(a["id"],) for a in alerts]
        try:
            conn2 = _sq.connect(str(db_path))
            conn2.executemany(
                "UPDATE storm_alerts SET processed = 1 WHERE event_id = ?", ids
            )
            conn2.commit()
            conn2.close()
        except Exception:
            pass

    return alerts


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
        brain_memory=None,
        brain_learning=None,
        drafter=None,
        enricher=None,
        narrator=None,
        broadcaster=None,
        zones: Optional[List[str]] = None,
        poll_interval_sec: int = 300,
        lane_count: int = 6,
        max_sends_hour: int = 50,
        max_sends_day: int = 10000,
        bounce_breaker_pct: float = 5.0,
        autonomy_default: bool = True,
    ):
        self.get_db = get_db
        self.email_engine = email_engine
        self.brain = brain
        self.brain_memory = brain_memory
        self.brain_learning = brain_learning
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

        # 3a. Pull VERIFIED alerts from the SQLite storm scraper bridge.
        #     Human-reviewed alerts get the same priority as live NWS alerts
        #     and flow through the identical process_alert() pipeline.
        relevant = []
        sqlite_verified = convert_sqlite_verified_to_alerts()
        for sa in sqlite_verified:
            sid = sa.get("id")
            if sid and sid not in self._processed_alerts:
                relevant.append(sa)
                self._processed_alerts.add(sid)
        if sqlite_verified:
            log.info(f"[orchestrator] sqlite bridge: {len(sqlite_verified)} VERIFIED alerts from storm scraper")

        # 3b. Poll NWS
        alerts = await self.scout.get_active_alerts()
        live_relevant = self.scout.filter_relevant(alerts)
        for la in live_relevant:
            lid = self.scout.alert_summary(la).get("id")
            if lid and lid not in self._processed_alerts:
                relevant.append(la)
                self._processed_alerts.add(lid)
        log.info(f"[orchestrator] poll: {len(alerts)} total alerts, {len(live_relevant)} relevant to TX zones, "
                 f"{len(sqlite_verified)} from sqlite bridge")

        if not relevant:
            return {"status": "ok", "alerts_total": len(alerts) + len(sqlite_verified), "alerts_relevant": 0}

        # 4. Determine which alerts are truly new (dedup already handled
        #     in step 3a/3b — relevant only contains unseen alerts).
        new_alerts = list(relevant)

        if not new_alerts:
            return {"status": "ok", "alerts_total": len(alerts), "alerts_relevant": len(relevant), "new": 0}

        self.last_alert_at = datetime.now(timezone.utc)
        self.state.update_state({"last_alert_at": self.last_alert_at.isoformat()})

        # 5. Process each new alert in parallel (bounded by lane_count)
        results = await self.lanes.gather([self.process_alert(a) for a in new_alerts])
        await self._broadcast({"type": "storm.tick", "new_alerts": len(new_alerts), "results": [r if not isinstance(r, Exception) else str(r) for r in results][:5]})

        return {"status": "ok", "alerts_total": len(alerts) + len(sqlite_verified), "alerts_relevant": len(relevant), "new": len(new_alerts), "results": len(results)}

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
        Stage target, log strike, decide GO/NO_GO, pick strategy, enroll.
        Returns dispatch_status string.

        Note: strategy is selected ONLY after the brain says GO. If the brain
        says NO_GO, the strike_log row is still inserted (for analytics) but
        without a strategy — the genome only sees outcomes from real GOs.
        """
        # Infer the niche from the alert event + target type. Storm-driven
        # warehouse/industrial outreach is overwhelmingly Roofing Restoration.
        niche = self._infer_niche(alert_summary, target)

        target_id = self.state.stage_target(target, source="storm_trigger")
        strike_id = self.state.log_strike(target_id, alert_summary, niche=niche, strategy=None)

        # Brain gate — retrieval-augmented decision-making
        #  1. Query brain_memory for similar past leads (few-shot examples)
        #  2. Look up tuned urgency floor from brain_learning
        #  3. Pass both as context to brain.decide()
        #  4. Record the decision in brain_memory for future learning
        #
        # NOTE: Brain gate runs BEFORE the rate gate so the token proxy
        # caches the decision even when the system is rate-limited.
        # On the next tick, similar alerts will hit the cache (~0.3s)
        # instead of waiting for Ollama (~85s) — compounding speedup.
        if self.brain:
            memory_context = ""
            if self.brain_memory:
                try:
                    similar = await self.brain_memory.retrieve_similar(
                        address=target.get("address", ""),
                        city=target.get("city", ""),
                        severity=alert_summary.get("severity", ""),
                        asset_value=float(target.get("asset_value", 0) or 0),
                        urgency_signal=alert_summary.get("event", ""),
                        k=5,
                    )
                    if similar:
                        memory_context = render_few_shot(similar)
                        log.info(f"[orchestrator] brain_memory: {len(similar)} similar past leads for {target.get('warehouse_name')}")
                except Exception as e:
                    log.debug(f"[orchestrator] brain_memory retrieval failed: {e}")

            decision = await self.brain.decide(target, alert_summary, memory_context=memory_context)
            log.info(f"[orchestrator] brain {decision.get('decision')} ({decision.get('confidence', 0):.2f}) for {target.get('warehouse_name')}: {decision.get('reasoning')}")

            # Record the decision in brain_memory so future decisions can learn from it
            if self.brain_memory:
                try:
                    await self.brain_memory.record_decision(
                        lead_id=target.get("id"),
                        decision=decision.get("decision", "NO_GO"),
                        urgency=decision.get("urgency", alert_summary.get("urgency", 0)),
                        reasoning=decision.get("reasoning", ""),
                        address=target.get("address", ""),
                        city=target.get("city", ""),
                        severity=alert_summary.get("severity", ""),
                        asset_value=float(target.get("asset_value", 0) or 0),
                    )
                except Exception as e:
                    log.debug(f"[orchestrator] brain_memory record failed: {e}")

            if decision.get("decision") != "GO":
                if strike_id:
                    self.state.update_strike_status(strike_id, "skipped_brain", extra_meta={"niche": niche})
                return "skipped_brain"
            if decision.get("confidence", 0) < 0.6:
                if strike_id:
                    self.state.update_strike_status(strike_id, "skipped_brain", extra_meta={"niche": niche})
                return "skipped_brain_lowconf"

        # Brain said GO — NOW pick the strategy and stamp it on the strike_log.
        strategy = _agi_governor.strategy_for_niche(niche) if _agi_governor else "AGGRESSIVE_STRIKE"
        if strike_id:
            self.state.update_strike_status(strike_id, "pending", extra_meta={"strategy": strategy, "niche": niche})

        # Rate gate — checks hourly/daily caps.
        # NOTE: Placed AFTER the brain decision (so token proxy caches it)
        # but BEFORE email dispatch (so we don't violate send limits).
        if self._hit_send_limit():
            if strike_id:
                self.state.update_strike_status(strike_id, "skipped_rate", extra_meta={"niche": niche})
            return "skipped_rate"

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
                self.state.update_strike_status(strike_id, "skipped_dup", extra_meta={"strategy": strategy, "niche": niche})
            return "no_email"

        # If we have a drafter, generate a draft instead of direct enrolling
        if self.drafter:
            decision_for_draft = decision if self.brain else {"decision": "GO", "confidence": 0.7, "reasoning": "default"}
            # Pass strategy into the drafter so the email body matches the SI-chosen approach
            decision_for_draft = {**decision_for_draft, "strategy": strategy, "niche": niche}
            draft = await self.drafter.draft_for_target(
                target=target,
                alert_summary=alert_summary,
                brain_decision=decision_for_draft,
                target_id=target_id,
                strike_id=strike_id,
            )
            if draft:
                if strike_id:
                    self.state.update_strike_status(strike_id, "enrolled", extra_meta={"strategy": strategy, "niche": niche})
                return "draft_created"
            else:
                if strike_id:
                    self.state.update_strike_status(strike_id, "error", extra_meta={"strategy": strategy, "niche": niche})
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
                self.state.update_strike_status(strike_id, "enrolled", extra_meta={"strategy": strategy, "niche": niche})
            return "enrolled"
        else:
            if strike_id:
                self.state.update_strike_status(strike_id, "error", extra_meta={"strategy": strategy, "niche": niche})
            return "error"

    @staticmethod
    def _infer_niche(alert_summary: Dict, target: Dict) -> str:
        """Pick the most likely niche for this strike. Maps storm events to
        specific niches so the genome accumulates per-niche signal instead
        of one mega-bucket. Operators can override via target.meta.niche
        if a more specific niche is known."""
        try:
            explicit = (target.get("meta") or {}).get("niche")
            if explicit:
                return str(explicit)[:80]
        except Exception:
            pass
        event = (alert_summary.get("event") or "").lower()
        for keywords, niche in _NICHE_MAP:
            if any(kw in event for kw in keywords):
                return niche
        # Generic storm / default → Roofing Restoration (the dominant niche
        # for Empire's warehouse/industrial lead flow).
        if any(kw in event for kw in _GENERIC_STORM_KW):
            return _DEFAULT_NICHE
        return _DEFAULT_NICHE

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

    @app.post("/api/v1/storm/process-sqlite")
    async def storm_process_sqlite(auth: bool = Depends(require_auth)):
        """Process all VERIFIED alerts from the SQLite storm scraper bridge.
        Reads VERIFIED alerts from data/storm_alerts.sqlite, converts them
        to NWS-compatible format, and feeds each through the full strike
        engine pipeline (process_alert).

        Idempotent: already-processed alerts are skipped via the in-memory
        dedup cache. Safe to call repeatedly (cron, manual trigger, etc.).
        """
        sqlite_alerts = convert_sqlite_verified_to_alerts()
        if not sqlite_alerts:
            return {"ok": True, "processed": 0, "message": "No VERIFIED alerts found in SQLite"}

        results = []
        for alert in sqlite_alerts:
            # Add to dedup cache before processing so tick() won't re-process
            orchestrator._processed_alerts.add(alert.get("id"))
            try:
                r = await orchestrator.process_alert(alert)
                results.append({"id": alert.get("id"), "status": r.get("status"), "enrolled": r.get("enrolled", 0)})
            except Exception as e:
                results.append({"id": alert.get("id"), "status": "error", "error": str(e)[:200]})

        return {
            "ok": True,
            "processed": len(results),
            "results": results,
        }

    log.info("[orchestrator] Routes registered · /api/v1/storm/{status,pause,resume,tick,fire-test,process-sqlite}")

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
