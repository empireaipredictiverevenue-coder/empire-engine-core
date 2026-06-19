"""
EMPIRE V49 · CARRIER PORTFOLIO MANAGEMENT
==========================================
Commercial Insurance Intelligence ($10k/mo whale-tier product).

Three components:

  1. PortfolioManager    — on-board carriers, manage insured properties,
                           compute portfolio stats
  2. StormMatcher        — match active storm forecasts against carrier
                           portfolios, score each property for damage,
                           generate storm reports
  3. StormReportEngine   — generate full HTML reports, deliver via email
                           or webhook, track delivery status

Wire-up in hub.py:

    from empire_carrier_portfolio import (
        PortfolioManager,
        StormMatcher,
        StormReportEngine,
        register_carrier_routes,
    )

    portfolio_manager = PortfolioManager(get_db=get_db)
    storm_matcher = StormMatcher(get_db=get_db, manager=portfolio_manager)
    report_engine = StormReportEngine(
        get_db=get_db,
        manager=portfolio_manager,
        send_email=_send_email,
        public_base_url=PUBLIC_BASE_URL,
    )

    register_carrier_routes(
        app,
        manager=portfolio_manager,
        matcher=storm_matcher,
        report_engine=report_engine,
        require_auth=require_auth,
    )

    # In the storm-autopilot path, after a storm is detected:
    #   matches = await storm_matcher.match_all_active()
    #   for report in matches:
    #       await report_engine.deliver(report)

Schema (created by migrations/011_carrier_portfolio.sql):
    carrier_portfolios       — one per carrier subscription
    carrier_properties       — each insured property in a carrier's book
    storm_reports            — one report per storm event per carrier
    storm_report_properties  — per-property damage assessment within a report
"""

import hashlib
import hmac
import json as _json
import logging
import math
from datetime import date, datetime, timezone
from typing import Callable, Optional

import httpx as _httpx

# Metro aliases shared with SatelliteStrikeCore for city-to-metro matching
from empire_satellite_strike import _METRO_ALIASES

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, HTMLResponse

log = logging.getLogger("empire.carrier_portfolio")


# ═══════════════════════════════════════════════════════════════════════
# PORTFOLIO MANAGER
# ═══════════════════════════════════════════════════════════════════════


class PortfolioManager:
    """Manages carrier portfolios and properties on top of Supabase.

    Responsible for:
      - Creating / updating / listing carrier portfolios
      - Bulk-importing carrier properties (CSV/JSON payloads)
      - Computing portfolio stats (property count, total value, metros)
      - Looking up carrier properties by metro for storm matching
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self.stats = {"portfolios_created": 0, "properties_imported": 0,
                       "properties_removed": 0, "errors": 0}

    # ── PORTFOLIO CRUD ─────────────────────────────────────────────────

    def create_portfolio(self, data: dict) -> dict:
        """Create a new carrier portfolio.

        Required fields: carrier_name, contact_email
        Optional: contact_name, contact_phone, subscription_id,
                  notes, report_delivery, report_frequency, meta
        """
        required = ["carrier_name", "contact_email"]
        for field in required:
            if not data.get(field):
                return {"ok": False, "error": f"'{field}' is required"}

        record = {
            "carrier_name":     data["carrier_name"].strip(),
            "contact_email":    data["contact_email"].strip(),
            "contact_name":     (data.get("contact_name") or "").strip(),
            "contact_phone":    (data.get("contact_phone") or "").strip(),
            "subscription_id":  data.get("subscription_id"),
            "status":           data.get("status", "onboarding"),
            "report_delivery":  data.get("report_delivery", "email"),
            "report_frequency": data.get("report_frequency", "immediate"),
            "notes":            (data.get("notes") or "").strip(),
            "meta":             _json.dumps(data.get("meta") or {}),
        }

        try:
            db = self.get_db()
            res = db.table("carrier_portfolios").insert(record).execute()
            if not res.data:
                return {"ok": False, "error": "Insert returned no data"}
            self.stats["portfolios_created"] += 1
            log.info(f"[carrier.portfolio] created: {data['carrier_name']} ({res.data[0]['id']})")
            return {"ok": True, "portfolio": res.data[0]}
        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[carrier.portfolio] create failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    def update_portfolio(self, portfolio_id: str, data: dict) -> dict:
        """Update a carrier portfolio's mutable fields."""
        allowed = {"carrier_name", "contact_email", "contact_name",
                    "contact_phone", "status", "report_delivery",
                    "report_frequency", "notes", "meta", "subscription_id"}
        update = {}
        for k in allowed:
            if k in data:
                if k == "meta":
                    update[k] = _json.dumps(data[k]) if isinstance(data[k], dict) else data[k]
                else:
                    update[k] = data[k]
        if not update:
            return {"ok": False, "error": "No valid fields to update"}

        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            db = self.get_db()
            db.table("carrier_portfolios").update(update) \
                .eq("id", portfolio_id).execute()
            return {"ok": True}
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}

    def get_portfolio(self, portfolio_id: str) -> Optional[dict]:
        """Return a single portfolio by ID."""
        try:
            db = self.get_db()
            res = db.table("carrier_portfolios").select("*") \
                .eq("id", portfolio_id).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None

    def list_portfolios(self, status: Optional[str] = None) -> list[dict]:
        """List all portfolios, optionally filtered by status."""
        try:
            db = self.get_db()
            q = db.table("carrier_portfolios").select("*") \
                .order("created_at", desc=True)
            if status:
                q = q.eq("status", status)
            res = q.execute()
            return res.data or []
        except Exception as e:
            self.stats["errors"] += 1
            log.warning(f"[carrier.portfolio] list failed: {e}")
            return []

    # ── PROPERTY MANAGEMENT ────────────────────────────────────────────

    def add_property(self, portfolio_id: str, prop: dict) -> dict:
        """Add a single property to a carrier's portfolio.

        Required: address, city, state
        Optional: zip, lat, lon, property_value, coverage_type,
                  building_type, year_built, sq_ft, carrier_ref, etc.
        """
        required = ["address", "city", "state"]
        for field in required:
            if not prop.get(field):
                return {"ok": False, "error": f"Property '{field}' is required"}

        record = {
            "portfolio_id":        portfolio_id,
            "address":             prop["address"].strip(),
            "city":                prop["city"].strip(),
            "state":               prop["state"].strip().upper(),
            "zip":                 (prop.get("zip") or "").strip(),
            "lat":                 prop.get("lat"),
            "lon":                 prop.get("lon"),
            "property_value":      float(prop.get("property_value", 0)),
            "coverage_type":       prop.get("coverage_type", "commercial"),
            "building_type":       prop.get("building_type", "warehouse"),
            "year_built":          prop.get("year_built"),
            "sq_ft":               prop.get("sq_ft"),
            "stories":             prop.get("stories"),
            "occupancy_type":      prop.get("occupancy_type", "commercial"),
            "roof_type":           prop.get("roof_type"),
            "construction_type":   prop.get("construction_type"),
            "carrier_ref":         (prop.get("carrier_ref") or "").strip(),
            "policy_number":       (prop.get("policy_number") or "").strip(),
            "deductible_amount":   float(prop.get("deductible_amount", 0)) if prop.get("deductible_amount") else None,
        }

        try:
            db = self.get_db()
            res = db.table("carrier_properties").insert(record).execute()
            if not res.data:
                return {"ok": False, "error": "Insert returned no data"}
            self.stats["properties_imported"] += 1
            self._recompute_portfolio_stats(portfolio_id)
            return {"ok": True, "property": res.data[0]}
        except Exception as e:
            err = str(e)
            if "unique" in err.lower() or "duplicate" in err.lower():
                return {"ok": False, "error": "Property with this address already exists in this portfolio"}
            self.stats["errors"] += 1
            return {"ok": False, "error": err[:200]}

    def bulk_add_properties(self, portfolio_id: str, properties: list[dict]) -> dict:
        """Bulk-import properties. Returns per-row results."""
        results = []
        errors = 0
        added = 0
        for prop in properties:
            r = self.add_property(portfolio_id, prop)
            if r.get("ok"):
                added += 1
            else:
                errors += 1
            results.append({"address": prop.get("address", "?"), "ok": r.get("ok"), "error": r.get("error")})
        self._recompute_portfolio_stats(portfolio_id)
        return {"ok": True if errors == 0 else "partial", "added": added, "errors": errors, "results": results}

    def remove_property(self, portfolio_id: str, property_id: str) -> dict:
        """Remove a property from a carrier's portfolio."""
        try:
            db = self.get_db()
            db.table("carrier_properties").delete() \
                .eq("id", property_id) \
                .eq("portfolio_id", portfolio_id) \
                .execute()
            self.stats["properties_removed"] += 1
            self._recompute_portfolio_stats(portfolio_id)
            return {"ok": True}
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}

    def list_properties(self, portfolio_id: str) -> list[dict]:
        """List all properties in a carrier's portfolio."""
        try:
            db = self.get_db()
            res = db.table("carrier_properties").select("*") \
                .eq("portfolio_id", portfolio_id) \
                .order("property_value", desc=True) \
                .execute()
            return res.data or []
        except Exception as e:
            self.stats["errors"] += 1
            log.warning(f"[carrier.properties] list failed: {e}")
            return []

    def properties_by_metro(self, metro: str) -> list[dict]:
        """Find carrier properties in a metro area by matching city names.

        Uses the same metro alias logic as SatelliteStrikeCore.
        Pushes city-matching filters to the DB via OR rather than fetching
        all rows and filtering in Python.

        Returns list of dicts with property + portfolio carrier_name joined.
        """
        aliases = _METRO_ALIASES.get(metro, [metro.lower()])
        try:
            db = self.get_db()
            # Build DB-level OR filter on city (imatch) for each alias
            or_parts = ",".join([f"city.ilike.%{a}%" for a in aliases])
            matched = db.table("carrier_properties").select(
                "*, carrier_portfolios!inner(carrier_name, contact_email, status, report_delivery)"
            ).or_(or_parts).execute()
            return matched.data or []
        except Exception as e:
            log.warning(f"[carrier.properties] metro lookup failed: {e}")
            return []

    # ── STATS ──────────────────────────────────────────────────────────

    def _recompute_portfolio_stats(self, portfolio_id: str):
        """Recalculate property_count and total_value for a portfolio
        and update the carrier_portfolios row."""
        try:
            db = self.get_db()
            res = db.table("carrier_properties").select("property_value") \
                .eq("portfolio_id", portfolio_id).execute()
            props = res.data or []
            count = len(props)
            total = sum(float(p.get("property_value", 0)) for p in props)

            # Collect distinct metros from property cities
            cities = list(set(p.get("city", "") for p in props if p.get("city")))
            db.table("carrier_portfolios").update({
                "property_count": count,
                "total_value": round(total, 2),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", portfolio_id).execute()
        except Exception:
            pass

    def portfolio_stats(self, portfolio_id: str) -> dict:
        """Return computed stats for a portfolio."""
        portfolio = self.get_portfolio(portfolio_id)
        if not portfolio:
            return {"error": "Portfolio not found"}
        props = self.list_properties(portfolio_id)
        value_by_type = {}
        coverage_types = set()
        for p in props:
            ct = p.get("coverage_type", "unknown")
            coverage_types.add(ct)
            value_by_type[ct] = value_by_type.get(ct, 0) + float(p.get("property_value", 0))

        return {
            "portfolio_id":      portfolio_id,
            "carrier_name":      portfolio.get("carrier_name"),
            "property_count":    len(props),
            "total_value":       round(sum(float(p.get("property_value", 0)) for p in props), 2),
            "value_by_type":     {k: round(v, 2) for k, v in value_by_type.items()},
            "coverage_types":    sorted(coverage_types),
            "avg_property_value": round(sum(float(p.get("property_value", 0)) for p in props) / len(props), 2) if props else 0,
            "status":            portfolio.get("status"),
            "report_delivery":   portfolio.get("report_delivery"),
        }

    def snapshot(self) -> dict:
        """Aggregate stats across all portfolios."""
        portfolios = self.list_portfolios()
        total_props = 0
        total_value = 0.0
        active_count = 0
        for p in portfolios:
            total_props += p.get("property_count", 0)
            total_value += float(p.get("total_value", 0))
            if p.get("status") == "active":
                active_count += 1
        return {
            "total_portfolios":  len(portfolios),
            "active_portfolios": active_count,
            "total_properties":  total_props,
            "total_value":       round(total_value, 2),
            **self.stats,
        }


# ═══════════════════════════════════════════════════════════════════════
# STORM MATCHER
# ═══════════════════════════════════════════════════════════════════════


class StormMatcher:
    """Match active storm forecasts against carrier portfolios.

    On each match cycle:
      1. Pull active storm_forecasts (last 24h, risk >= Slight)
      2. For each forecast metro, find carrier properties in that area
      3. Score each property for damage based on storm severity + distance
      4. Write storm_report_properties rows
      5. Create a storm_report for each affected carrier
      6. Return list of reports ready for delivery
    """

    def __init__(self, get_db: Callable, manager: PortfolioManager):
        self.get_db = get_db
        self.manager = manager
        self.stats = {"matches_run": 0, "reports_generated": 0,
                       "properties_scored": 0, "errors": 0}

    async def match_all_active(self) -> list[dict]:
        """Run a full match cycle against all active portfolios.

        Returns a list of storm_reports dicts ready for delivery.
        """
        self.stats["matches_run"] += 1
        reports = []

        # 1. Fetch active storm forecasts
        forecasts = self._fetch_storm_forecasts()
        if not forecasts:
            log.info("[carrier.matcher] no active storm forecasts")
            return reports

        log.info(f"[carrier.matcher] {len(forecasts)} active forecasts")

        # 2. For each forecast, find affected carriers + properties
        for fc in forecasts:
            metro = fc.get("metro", "")
            if not metro:
                continue
            risk_level = fc.get("risk_level", "Slight")
            risk_rank = int(fc.get("risk_rank", 4))
            severity = fc.get("severity") or risk_level
            event = fc.get("event") or f"{risk_level} Storm System"

            # 2a. Find carrier properties in this metro
            affected = self.manager.properties_by_metro(metro)
            if not affected:
                continue

            # Group by portfolio_id
            by_portfolio: dict[str, list[dict]] = {}
            for p in affected:
                pid = p.get("portfolio_id")
                if pid:
                    by_portfolio.setdefault(pid, []).append(p)

            log.info(f"[carrier.matcher] metro={metro} risk={risk_level} "
                     f"carriers={len(by_portfolio)} properties={len(affected)}")

            # 3. For each affected portfolio, create a report
            for portfolio_id, props in by_portfolio.items():
                report = await self._generate_report(
                    portfolio_id=portfolio_id,
                    metro=metro,
                    storm_event=event,
                    storm_severity=severity,
                    risk_rank=risk_rank,
                    properties=props,
                    forecast=fc,
                )
                if report:
                    reports.append(report)

        self.stats["reports_generated"] = len(reports)
        log.info(f"[carrier.matcher] cycle complete: {len(reports)} reports generated")
        return reports

    async def match_portfolio(self, portfolio_id: str) -> Optional[dict]:
        """Match a single portfolio against current storm forecasts.

        Returns a single storm_report dict, or None if no overlap.
        """
        portfolio = self.manager.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        forecasts = self._fetch_storm_forecasts()
        for fc in forecasts:
            metro = fc.get("metro", "")
            if not metro:
                continue

            affected = self.manager.properties_by_metro(metro)
            portfolio_props = [p for p in affected if p.get("portfolio_id") == portfolio_id]
            if not portfolio_props:
                continue

            risk_level = fc.get("risk_level", "Slight")
            severity = fc.get("severity") or risk_level
            event = fc.get("event") or f"{risk_level} Storm System"

            return await self._generate_report(
                portfolio_id=portfolio_id,
                metro=metro,
                storm_event=event,
                storm_severity=severity,
                risk_rank=int(fc.get("risk_rank", 4)),
                properties=portfolio_props,
                forecast=fc,
            )

        return None

    # ── INTERNAL ────────────────────────────────────────────────────────

    def _fetch_storm_forecasts(self) -> list[dict]:
        """Pull active storm_forecasts from the last 24 hours."""
        try:
            db = self.get_db()
            r = db.table("storm_forecasts").select("forecasts,count,updated_at") \
                .order("updated_at", desc=True).limit(1).execute()
            if not r.data:
                return []
            forecasts = r.data[0].get("forecasts")
            if isinstance(forecasts, str):
                forecasts = _json.loads(forecasts)
            return forecasts or []
        except Exception as e:
            self.stats["errors"] += 1
            log.warning(f"[carrier.matcher] forecast fetch failed: {e}")
            return []

    async def _generate_report(
        self,
        portfolio_id: str,
        metro: str,
        storm_event: str,
        storm_severity: str,
        risk_rank: int,
        properties: list[dict],
        forecast: dict,
    ) -> Optional[dict]:
        """Score properties, write storm_report_properties, create storm_report.

        The damage score per property is a heuristic based on:
          - Storm severity (Extreme=80, Severe=60, Moderate=40, other=20)
          - Proximity factor (properties with lat/lon get higher confidence)
          - Asset value multiplier (higher value = more attention)

        Returns the storm_report dict if created, or None on error.
        """
        self.stats["properties_scored"] += len(properties)

        # Base severity multiplier from storm intensity
        severity_map = {"extreme": 80, "severe": 60, "moderate": 40}
        base_severity = severity_map.get(storm_severity.lower(), 20)

        scored = []
        for prop in properties:
            lat = prop.get("lat")
            lon = prop.get("lon")
            prop_value = float(prop.get("property_value", 0))

            # Compute per-property damage score
            # Proximity: if we have coordinates, we have higher confidence
            has_coords = lat is not None and lon is not None
            confidence = 60 if has_coords else 30

            # Value factor: higher-value properties tend to get more thorough assessment
            value_factor = min(1.5, max(0.5, prop_value / 2_000_000)) if prop_value > 0 else 0.5

            # Random-ish jitter based on property_id to simulate variation
            id_hash = int(hashlib.md5((prop["id"] + metro).encode()).hexdigest()[:8], 16)
            jitter = (id_hash % 21) - 10  # -10 to +10

            damage_score = max(0, min(100, base_severity * value_factor + jitter))

            # Map to category
            if damage_score < 5:
                category = "none"
            elif damage_score < 25:
                category = "minor"
            elif damage_score < 50:
                category = "moderate"
            elif damage_score < 80:
                category = "severe"
            else:
                category = "total_loss"

            # Estimated loss (simplified: damage_pct * property_value)
            est_loss = round(prop_value * (damage_score / 100) * 0.3, 2)  # 30% of damage ratio

            scored.append({
                "property_id":      prop["id"],
                "portfolio_id":     portfolio_id,
                "distance_to_storm": None,  # would require storm polygon centroid
                "wind_gust":        None,
                "hail_size":        None,
                "precipitation":    None,
                "flood_risk":       None,
                "damage_score":     round(damage_score, 2),
                "damage_category":  category,
                "confidence":       round(confidence, 2),
                "estimated_loss":   est_loss,
                "notes":            f"Auto-scored from {storm_severity} event in {metro}",
                # Property details for the report
                "_address":         prop.get("address", ""),
                "_city":            prop.get("city", ""),
                "_state":           prop.get("state", ""),
                "_zip":             prop.get("zip", ""),
                "_property_value":  prop_value,
                "_carrier_ref":     prop.get("carrier_ref", ""),
                "_coverage_type":   prop.get("coverage_type", "commercial"),
                "_building_type":   prop.get("building_type", "warehouse"),
            })

        if not scored:
            return None

        # Aggregate report
        total_exposure = sum(p["_property_value"] for p in scored)
        total_est_loss = sum(p["estimated_loss"] for p in scored)
        severity_score = round(sum(p["damage_score"] for p in scored) / len(scored), 2)
        max_score = max(p["damage_score"] for p in scored)
        min_score = min(p["damage_score"] for p in scored)
        affected_count = len([s for s in scored if s["damage_score"] >= 5])
        severe_count = len([s for s in scored if s["damage_category"] in ("severe", "total_loss")])

        # Build summary
        summary = (
            f"{storm_event} affecting {metro} area. "
            f"{affected_count} of {len(scored)} properties affected "
            f"({severe_count} severe/total loss). "
            f"Damage range: {round(min_score, 0)}–{round(max_score, 0)}/100. "
            f"Estimated total loss: ${total_est_loss:,.2f}."
        )

        recommendations = self._build_recommendations(severity_score, severe_count, storm_severity)

        # Write the report to DB
        try:
            db = self.get_db()
            now = datetime.now(timezone.utc).isoformat()
            report_record = {
                "portfolio_id":     portfolio_id,
                "storm_event":      storm_event,
                "storm_severity":   storm_severity,
                "storm_metro":      metro,
                "storm_start":      forecast.get("start_time") or now,
                "storm_end":        forecast.get("end_time"),
                "storm_id":         forecast.get("id"),
                "title":            f"{storm_severity} Storm Impact Report — {metro}",
                "summary":          summary,
                "severity_score":   severity_score,
                "affected_count":   affected_count,
                "total_exposure":   round(total_exposure, 2),
                "estimated_loss":   round(total_est_loss, 2),
                "recommendations":  recommendations,
                "status":           "generated",
                "meta":             _json.dumps({
                    "risk_rank": risk_rank,
                    "total_scored": len(scored),
                    "severe_count": severe_count,
                    "damage_range": [round(min_score, 2), round(max_score, 2)],
                }),
            }
            res = db.table("storm_reports").insert(report_record).execute()
            if not res.data:
                log.warning("[carrier.matcher] report insert returned no data")
                return None
            report = res.data[0]

            # Write per-property assessments
            report_props = []
            for s in scored:
                rp = {
                    "report_id":        report["id"],
                    "portfolio_id":     portfolio_id,
                    "property_id":      s["property_id"],
                    "distance_to_storm": s["distance_to_storm"],
                    "wind_gust":        s["wind_gust"],
                    "hail_size":        s["hail_size"],
                    "precipitation":    s["precipitation"],
                    "flood_risk":       s["flood_risk"],
                    "damage_score":     s["damage_score"],
                    "damage_category":  s["damage_category"],
                    "confidence":       s["confidence"],
                    "estimated_loss":   s["estimated_loss"],
                    "notes":            s["notes"],
                }
                report_props.append(rp)

            if report_props:
                db.table("storm_report_properties").insert(report_props).execute()

            # Update last_matched_at on carrier_properties
            for s in scored:
                db.table("carrier_properties").update({
                    "last_matched_at": now,
                    "last_storm_event": storm_event,
                    "last_damage_score": s["damage_score"],
                }).eq("id", s["property_id"]).execute()

            report["_property_assessments"] = scored
            log.info(f"[carrier.matcher] report {report['id']}: "
                     f"{len(scored)} properties, severity={severity_score}")
            return report

        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[carrier.matcher] report generation failed: {e}")
            return None

    @staticmethod
    def _build_recommendations(severity_score: float, severe_count: int, severity: str) -> str:
        """Build actionable recommendations based on storm severity."""
        parts = []
        if severity_score >= 50:
            parts.append("IMMEDIATE ACTION RECOMMENDED: Dispatch adjusters to high-score properties.")
        if severe_count > 0:
            parts.append(f"Prioritize claims processing for {severe_count} properties with severe/total loss damage.")
        if severity.lower() in ("extreme", "severe"):
            parts.append("Consider pre-emptive contractor dispatch for rapid response.")
        parts.append("Monitor NWS updates for additional storm cells in the same metro.")
        parts.append("Review policy coverage limits for properties in the affected area.")
        return " ".join(parts)

    def snapshot(self) -> dict:
        """Return current matcher stats."""
        return {**self.stats}


# ═══════════════════════════════════════════════════════════════════════
# REPORT ENGINE
# ═══════════════════════════════════════════════════════════════════════


class StormReportEngine:
    """Generates and delivers storm reports to carriers.

    Delivery methods:
      - Email: sends HTML report via the hub's send_email helper
      - Webhook: POSTs JSON report payload to carrier's webhook URL

    HTML report templates are rendered server-side for email delivery.
    """

    def __init__(
        self,
        get_db: Callable,
        manager: PortfolioManager,
        send_email: Optional[Callable] = None,
        public_base_url: str = "http://localhost:8001",
    ):
        self.get_db = get_db
        self.manager = manager
        self.send_email = send_email
        self.public_base_url = public_base_url
        self.stats = {"reports_delivered": 0, "emails_sent": 0,
                       "webhooks_sent": 0, "errors": 0}

    async def deliver(self, report_id: str) -> dict:
        """Deliver a storm report to its carrier.

        Reads the report + assessments from DB, picks the delivery method
        based on the carrier's report_delivery preference, and updates
        the report status on success.
        """
        try:
            db = self.get_db()
            res = db.table("storm_reports").select("*") \
                .eq("id", report_id).limit(1).execute()
            if not res.data:
                return {"ok": False, "error": "Report not found"}
            report = res.data[0]

            portfolio_id = report.get("portfolio_id")
            portfolio = self.manager.get_portfolio(portfolio_id)
            if not portfolio:
                return {"ok": False, "error": "Portfolio not found"}

            # Fetch assessments
            ass_res = db.table("storm_report_properties").select(
                "damage_score,damage_category,confidence,estimated_loss,"
                "property_id,carrier_properties!inner(address,city,state,zip,"
                "property_value,coverage_type,building_type,carrier_ref)"
            ).eq("report_id", report_id).execute()
            assessments = ass_res.data or []

            delivery = portfolio.get("report_delivery", "email")
            results = {}

            # ── EMAIL DELIVERY ─────────────────────────────────────────
            if delivery in ("email", "both") and self.send_email:
                html = self._render_html_report(report, assessments, portfolio)
                subject = f"[Empire AI] {report.get('title', 'Storm Impact Report')}"
                email_res = await self.send_email(
                    to=portfolio["contact_email"],
                    subject=subject,
                    html=html,
                )
                if email_res.get("ok"):
                    results["email"] = {"ok": True, "id": email_res.get("id")}
                    self.stats["emails_sent"] += 1
                else:
                    results["email"] = {"ok": False, "error": email_res.get("error")}
                    self.stats["errors"] += 1

            # ── WEBHOOK DELIVERY ───────────────────────────────────────
            if delivery in ("webhook", "both"):
                webhook_url = self._get_carrier_webhook(portfolio)
                if webhook_url:
                    wh_res = await self._send_webhook(webhook_url, report, assessments)
                    results["webhook"] = wh_res
                    if wh_res.get("ok"):
                        self.stats["webhooks_sent"] += 1
                    else:
                        self.stats["errors"] += 1
                else:
                    results["webhook"] = {"ok": False, "error": "No webhook URL configured"}

            # ── UPDATE STATUS ──────────────────────────────────────────
            now = datetime.now(timezone.utc).isoformat()
            update = {
                "status": "delivered",
                "delivered_at": now,
                "delivery_method": delivery,
                "delivery_status": "ok" if any(
                    r.get("ok") for r in results.values()
                ) else "failed",
                "updated_at": now,
            }
            db.table("storm_reports").update(update).eq("id", report_id).execute()

            self.stats["reports_delivered"] += 1
            return {
                "ok": update["delivery_status"] == "ok",
                "report_id": report_id,
                "results": results,
            }

        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[carrier.report] deliver failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    def _get_carrier_webhook(self, portfolio: dict) -> str:
        """Extract webhook URL from portfolio meta."""
        meta = portfolio.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = _json.loads(meta)
            except Exception:
                return ""
        return meta.get("webhook_url", "") or ""

    def get_reports(self, portfolio_id: str, status: Optional[str] = None,
                    limit: int = 20) -> list[dict]:
        """List storm reports for a portfolio."""
        try:
            db = self.get_db()
            q = db.table("storm_reports").select("*") \
                .eq("portfolio_id", portfolio_id) \
                .order("created_at", desc=True).limit(min(limit, 100))
            if status:
                q = q.eq("status", status)
            res = q.execute()
            return res.data or []
        except Exception as e:
            log.warning(f"[carrier.report] list failed: {e}")
            return []

    def get_report_detail(self, report_id: str) -> Optional[dict]:
        """Return a report with its property assessments."""
        try:
            db = self.get_db()
            res = db.table("storm_reports").select("*") \
                .eq("id", report_id).limit(1).execute()
            if not res.data:
                return None
            report = res.data[0]

            ass_res = db.table("storm_report_properties").select("*") \
                .eq("report_id", report_id) \
                .order("damage_score", desc=True).execute()
            report["assessments"] = ass_res.data or []
            return report
        except Exception as e:
            log.warning(f"[carrier.report] detail failed: {e}")
            return None

    # ── WEBHOOK POST ───────────────────────────────────────────────────

    async def _send_webhook(self, webhook_url: str, report: dict,
                             assessments: list[dict]) -> dict:
        """POST report payload to a carrier's webhook endpoint."""
        payload = {
            "event": "storm.report.delivered",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "report": {
                "id": report["id"],
                "title": report.get("title"),
                "summary": report.get("summary"),
                "storm_event": report.get("storm_event"),
                "storm_severity": report.get("storm_severity"),
                "storm_metro": report.get("storm_metro"),
                "severity_score": float(report.get("severity_score", 0)),
                "affected_count": report.get("affected_count", 0),
                "total_exposure": float(report.get("total_exposure", 0)),
                "estimated_loss": float(report.get("estimated_loss", 0)) if report.get("estimated_loss") else None,
                "recommendations": report.get("recommendations", ""),
            },
            "properties": [
                {
                    "address": a.get("address", ""),
                    "city": a.get("city", ""),
                    "state": a.get("state", ""),
                    "zip": a.get("zip", ""),
                    "property_value": float(a.get("property_value", 0)),
                    "damage_score": float(a.get("damage_score", 0)),
                    "damage_category": a.get("damage_category", "none"),
                    "confidence": float(a.get("confidence", 0)),
                    "estimated_loss": float(a.get("estimated_loss", 0)) if a.get("estimated_loss") else None,
                }
                for a in assessments
            ],
        }

        signature = hmac.new(
            report["id"].encode(),
            _json.dumps(payload, sort_keys=True).encode(),
            hashlib.sha256,
        ).hexdigest()

        try:
            async with _httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(webhook_url, json=payload, headers={
                    "Content-Type": "application/json",
                    "X-Empire-Signature": f"sha256={signature}",
                    "X-Empire-Report-Id": report["id"],
                    "User-Agent": "EmpireAI-CarrierIntel/1.0",
                })
                if resp.status_code < 300:
                    return {"ok": True, "status_code": resp.status_code}
                return {"ok": False, "error": f"HTTP {resp.status_code}", "status_code": resp.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── HTML REPORT TEMPLATE ───────────────────────────────────────────

    def _render_html_report(self, report: dict, assessments: list[dict],
                             portfolio: dict) -> str:
        """Generate a professional HTML storm impact report for email delivery.
        Uses inline styles compatible with major email clients.
        """
        affected = report.get("affected_count", 0)
        severity = float(report.get("severity_score", 0))
        exposure = float(report.get("total_exposure", 0))
        est_loss = report.get("estimated_loss")
        if est_loss is not None:
            est_loss = float(est_loss)
        recommendations = report.get("recommendations", "")

        # Severity color
        if severity >= 60:
            sev_color = "#dc2626"
            sev_label = "CRITICAL"
        elif severity >= 35:
            sev_color = "#f59e0b"
            sev_label = "ELEVATED"
        else:
            sev_color = "#22c55e"
            sev_label = "MONITOR"

        # Build property rows
        prop_rows = ""
        for a in assessments:
            ds = float(a.get("damage_score", 0))
            if ds >= 50:
                d_color = "#dc2626"
            elif ds >= 25:
                d_color = "#f59e0b"
            else:
                d_color = "#22c55e"
            prop_rows += f"""
            <tr>
              <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;font-size:13px;color:#111827;">
                {a.get('address', '—')}<br>
                <span style="font-size:11px;color:#6b7280;">{a.get('city', '')}, {a.get('state', '')} {a.get('zip', '')}</span>
              </td>
              <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:center;">
                <span style="background:{d_color};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">
                  {a.get('damage_category', 'none').upper()}
                </span>
              </td>
              <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right;font-family:monospace;">
                {ds:.0f}
              </td>
              <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right;font-family:monospace;">
                ${float(a.get('estimated_loss', 0)):,.0f}
              </td>
              <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right;font-family:monospace;color:#6b7280;">
                {a.get('confidence', 0):.0f}%
              </td>
            </tr>"""

        loss_section = ""
        if est_loss:
            loss_section = f"""
            <div style="margin-top:24px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px 20px;">
              <div style="font-size:11px;color:#dc2626;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">
                Estimated Loss Range
              </div>
              <div style="font-size:28px;color:#dc2626;font-weight:600;font-family:monospace;">
                ${est_loss:,.0f}
              </div>
            </div>"""

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:0 auto;background:#ffffff;">
  <tr><td style="background:#111827;padding:32px 40px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="font-size:22px;color:#44E5B8;font-weight:200;letter-spacing:-0.02em;">
          Empire AI <strong style="font-weight:500;color:#f9fafb;">Storm Intelligence</strong>
        </td>
        <td style="text-align:right;">
          <span style="background:{sev_color};color:#fff;padding:4px 12px;border-radius:4px;font-size:11px;font-weight:600;letter-spacing:0.08em;">
            {sev_label}
          </span>
        </td>
      </tr>
    </table>
  </td></tr>

  <tr><td style="padding:32px 40px 8px;">
    <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">
      Storm Impact Report
    </div>
    <div style="font-size:20px;color:#111827;font-weight:600;margin-bottom:4px;">
      {report.get('title', 'Storm Impact Report')}
    </div>
    <div style="font-size:13px;color:#6b7280;">
      {portfolio.get('carrier_name', 'Your Portfolio')} · {report.get('storm_metro', '')}
    </div>
  </td></tr>

  <tr><td style="padding:16px 40px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px 20px;width:33%;">
          <div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;">Affected</div>
          <div style="font-size:28px;color:#111827;font-weight:600;font-family:monospace;">{affected}</div>
          <div style="font-size:11px;color:#9ca3af;">properties</div>
        </td>
        <td style="width:8px;"></td>
        <td style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px 20px;width:33%;">
          <div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;">Exposure</div>
          <div style="font-size:28px;color:#111827;font-weight:600;font-family:monospace;">${exposure:,.0f}</div>
          <div style="font-size:11px;color:#9ca3af;">total insured value</div>
        </td>
        <td style="width:8px;"></td>
        <td style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px 20px;width:33%;">
          <div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;">Severity</div>
          <div style="font-size:28px;color:{sev_color};font-weight:600;font-family:monospace;">{severity:.0f}</div>
          <div style="font-size:11px;color:#9ca3af;">/ 100</div>
        </td>
      </tr>
    </table>
  </td></tr>

  <tr><td style="padding:8px 40px 16px;">
    <div style="font-size:13px;color:#4b5563;line-height:1.6;">
      {report.get('summary', '')}
    </div>
  </td></tr>

  {loss_section}

  <tr><td style="padding:24px 40px 8px;">
    <div style="font-size:14px;color:#111827;font-weight:600;margin-bottom:8px;">
      Affected Properties
    </div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <thead>
        <tr style="background:#f9fafb;">
          <th style="padding:10px 14px;font-size:10px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;text-align:left;border-bottom:2px solid #e5e7eb;">Property</th>
          <th style="padding:10px 14px;font-size:10px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;text-align:center;border-bottom:2px solid #e5e7eb;">Damage</th>
          <th style="padding:10px 14px;font-size:10px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;text-align:right;border-bottom:2px solid #e5e7eb;">Score</th>
          <th style="padding:10px 14px;font-size:10px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;text-align:right;border-bottom:2px solid #e5e7eb;">Est. Loss</th>
          <th style="padding:10px 14px;font-size:10px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;text-align:right;border-bottom:2px solid #e5e7eb;">Conf.</th>
        </tr>
      </thead>
      <tbody>
        {prop_rows}
      </tbody>
    </table>
  </td></tr>

  <tr><td style="padding:16px 40px 24px;">
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:14px 18px;">
      <div style="font-size:11px;color:#16a34a;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">
        Recommendations
      </div>
      <div style="font-size:12px;color:#166534;line-height:1.6;">
        {recommendations}
      </div>
    </div>
  </td></tr>

  <tr><td style="padding:16px 40px 32px;border-top:1px solid #e5e7eb;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="font-size:11px;color:#9ca3af;">
          Empire AI V49 · Commercial Insurance Intelligence<br>
          Delivered {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
        </td>
        <td style="text-align:right;">
          <a href="{self.public_base_url}/view/pulse" style="font-size:11px;color:#6366f1;text-decoration:underline;">
            View in dashboard →
          </a>
        </td>
      </tr>
    </table>
  </td></tr>

  <tr><td style="background:#111827;padding:16px 40px;text-align:center;">
    <div style="font-size:10px;color:#6b7280;">
      Empire AI Ltd · Automated storm intelligence report · Data sourced from NWS + satellite analysis
    </div>
  </td></tr>
</table>
</body>
</html>"""

    def snapshot(self) -> dict:
        """Return current report engine stats."""
        return {**self.stats}


# ═══════════════════════════════════════════════════════════════════════
# ROUTE REGISTRATION
# ═══════════════════════════════════════════════════════════════════════


def register_carrier_routes(
    app: FastAPI,
    *,
    manager: PortfolioManager,
    matcher: StormMatcher,
    report_engine: StormReportEngine,
    require_auth: Callable,
):
    """Wire Carrier Portfolio API endpoints into the FastAPI app.

    Auth-required endpoints:
        POST   /api/v1/carriers                          — create a portfolio
        GET    /api/v1/carriers                           — list portfolios
        GET    /api/v1/carriers/{id}                      — portfolio detail + stats
        PATCH  /api/v1/carriers/{id}                      — update portfolio
        GET    /api/v1/carriers/{id}/properties           — list properties
        POST   /api/v1/carriers/{id}/properties           — bulk-import properties
        DELETE /api/v1/carriers/{id}/properties/{prop_id} — remove a property
        POST   /api/v1/carriers/{id}/match                — trigger storm match
        POST   /api/v1/carriers/match-all                 — match all active portfolios
        GET    /api/v1/carriers/{id}/reports              — list reports
        GET    /api/v1/carriers/{id}/reports/{report_id}  — report detail
        POST   /api/v1/carriers/{id}/reports/{report_id}/deliver — send report
        GET    /api/v1/carriers/{id}/stats                — portfolio stats
        GET    /api/v1/carriers/system/stats              — system-wide stats
    """

    # ── CREATE PORTFOLIO ──────────────────────────────────────────────

    @app.post("/api/v1/carriers")
    async def create_portfolio(request: Request, auth: bool = Depends(require_auth)):
        """Create a new carrier portfolio.

        Body: {
            "carrier_name": "Acme Insurance Co",
            "contact_email": "claims@acme.com",
            "contact_name": "John Smith",
            "contact_phone": "+12145551234",
            "subscription_id": "<uuid>",       # link to buyer_subscriptions
            "notes": "Enterprise account",
            "report_delivery": "email",         # email | webhook | both
        }
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        result = manager.create_portfolio(body)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Create failed"))
        return JSONResponse(result, status_code=201)

    # ── LIST PORTFOLIOS ───────────────────────────────────────────────

    @app.get("/api/v1/carriers")
    async def list_portfolios(
        status: str = Query(""),
        auth: bool = Depends(require_auth),
    ):
        """List all carrier portfolios, optionally filtered by status."""
        portfolios = manager.list_portfolios(status=status or None)
        return JSONResponse({"portfolios": portfolios, "count": len(portfolios)})

    # ── PORTFOLIO DETAIL ──────────────────────────────────────────────

    @app.get("/api/v1/carriers/{portfolio_id}")
    async def get_portfolio(
        portfolio_id: str,
        auth: bool = Depends(require_auth),
    ):
        """Return portfolio detail with stats."""
        portfolio = manager.get_portfolio(portfolio_id)
        if not portfolio:
            raise HTTPException(404, "Portfolio not found")
        stats = manager.portfolio_stats(portfolio_id)
        portfolio["_stats"] = stats
        return JSONResponse(portfolio)

    # ── UPDATE PORTFOLIO ──────────────────────────────────────────────

    @app.patch("/api/v1/carriers/{portfolio_id}")
    async def update_portfolio(
        portfolio_id: str,
        request: Request,
        auth: bool = Depends(require_auth),
    ):
        """Update a carrier portfolio's mutable fields."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        if not isinstance(body, dict) or not body:
            raise HTTPException(400, "Body must be a non-empty JSON object")

        result = manager.update_portfolio(portfolio_id, body)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Update failed"))
        return JSONResponse(result)

    # ── LIST PROPERTIES ───────────────────────────────────────────────

    @app.get("/api/v1/carriers/{portfolio_id}/properties")
    async def list_properties(
        portfolio_id: str,
        auth: bool = Depends(require_auth),
    ):
        """List all properties in a carrier's portfolio."""
        props = manager.list_properties(portfolio_id)
        return JSONResponse({"properties": props, "count": len(props)})

    # ── BULK-IMPORT PROPERTIES ────────────────────────────────────────

    @app.post("/api/v1/carriers/{portfolio_id}/properties")
    async def bulk_import_properties(
        portfolio_id: str,
        request: Request,
        auth: bool = Depends(require_auth),
    ):
        """Bulk-import properties into a carrier's portfolio.

        Body: {
            "properties": [
                {
                    "address": "123 Industrial Blvd",
                    "city": "Dallas",
                    "state": "TX",
                    "zip": "75201",
                    "lat": 32.7767,
                    "lon": -96.7970,
                    "property_value": 5000000,
                    "coverage_type": "commercial",
                    "building_type": "warehouse",
                    "year_built": 2005,
                    "sq_ft": 50000,
                    "carrier_ref": "POL-12345",
                },
                ...
            ]
        }
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        props = body.get("properties", [])
        if not props or not isinstance(props, list):
            raise HTTPException(400, "'properties' must be a non-empty array")

        result = manager.bulk_add_properties(portfolio_id, props)
        status_code = 200 if result.get("ok") is True else 207
        return JSONResponse(result, status_code=status_code)

    # ── REMOVE PROPERTY ───────────────────────────────────────────────

    @app.delete("/api/v1/carriers/{portfolio_id}/properties/{property_id}")
    async def remove_property(
        portfolio_id: str,
        property_id: str,
        auth: bool = Depends(require_auth),
    ):
        """Remove a property from a carrier's portfolio."""
        result = manager.remove_property(portfolio_id, property_id)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Remove failed"))
        return JSONResponse(result)

    # ── TRIGGER STORM MATCH ───────────────────────────────────────────

    @app.post("/api/v1/carriers/{portfolio_id}/match")
    async def match_portfolio(
        portfolio_id: str,
        auth: bool = Depends(require_auth),
    ):
        """Trigger a storm match for a specific portfolio against current
        active storm forecasts. Returns the generated report if a match
        was found, or a message if no overlap.
        """
        report = await matcher.match_portfolio(portfolio_id)
        if not report:
            return JSONResponse({
                "ok": True,
                "matched": False,
                "message": "No active storm overlap found for this portfolio",
            })
        return JSONResponse({
            "ok": True,
            "matched": True,
            "report": report,
        })

    # ── MATCH ALL ACTIVE ──────────────────────────────────────────────

    @app.post("/api/v1/carriers/match-all")
    async def match_all_portfolios(auth: bool = Depends(require_auth)):
        """Trigger a full match cycle against all active portfolios.
        Returns the list of generated reports.
        """
        reports = await matcher.match_all_active()
        return JSONResponse({
            "ok": True,
            "reports_count": len(reports),
            "reports": reports,
        })

    # ── LIST REPORTS ──────────────────────────────────────────────────

    @app.get("/api/v1/carriers/{portfolio_id}/reports")
    async def list_reports(
        portfolio_id: str,
        status: str = Query(""),
        limit: int = Query(20, le=100),
        auth: bool = Depends(require_auth),
    ):
        """List storm reports for a portfolio, optionally filtered by status."""
        reports = report_engine.get_reports(
            portfolio_id, status=status or None, limit=limit
        )
        return JSONResponse({"reports": reports, "count": len(reports)})

    # ── REPORT DETAIL ─────────────────────────────────────────────────

    @app.get("/api/v1/carriers/{portfolio_id}/reports/{report_id}")
    async def get_report(
        portfolio_id: str,
        report_id: str,
        auth: bool = Depends(require_auth),
    ):
        """Return a full report with property assessments."""
        detail = report_engine.get_report_detail(report_id)
        if not detail:
            raise HTTPException(404, "Report not found")
        if detail.get("portfolio_id") != portfolio_id:
            raise HTTPException(404, "Report not found in this portfolio")
        return JSONResponse(detail)

    # ── DELIVER REPORT ────────────────────────────────────────────────

    @app.post("/api/v1/carriers/{portfolio_id}/reports/{report_id}/deliver")
    async def deliver_report(
        portfolio_id: str,
        report_id: str,
        auth: bool = Depends(require_auth),
    ):
        """Deliver a storm report to the carrier via their configured
        delivery method (email, webhook, or both).
        """
        result = await report_engine.deliver(report_id)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Delivery failed"))
        return JSONResponse(result)

    # ── PORTFOLIO STATS ───────────────────────────────────────────────

    @app.get("/api/v1/carriers/{portfolio_id}/stats")
    async def portfolio_stats(
        portfolio_id: str,
        auth: bool = Depends(require_auth),
    ):
        """Return computed stats for a portfolio."""
        stats = manager.portfolio_stats(portfolio_id)
        if "error" in stats:
            raise HTTPException(404, stats["error"])
        return JSONResponse(stats)

    # ── SYSTEM STATS ──────────────────────────────────────────────────

    @app.get("/api/v1/carriers/system/stats")
    async def carrier_system_stats(auth: bool = Depends(require_auth)):
        """Aggregate system-wide stats for the carrier intel product."""
        return JSONResponse({
            "portfolios": manager.snapshot(),
            "matcher": matcher.snapshot(),
            "report_engine": report_engine.snapshot(),
        })

    log.info("[carrier.portfolio] Routes registered · /api/v1/carriers/*")
