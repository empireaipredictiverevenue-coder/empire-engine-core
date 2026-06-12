"""
EMPIRE V49 · SATELLITE STRIKE CORE
===================================
Scans Storm Tracking Logs & Filters Warehouse Targets.

The entry-point data pipeline for the Swarm Gate. Queries:
  - storm_forecasts  → active metro-risk forecasts from the storm predictor
  - radar_targets     → warehouse/industrial targets in affected metros
  - strike_log        → de-dup: don't re-target already-dispatched leads

Returns `StrikePackage` objects ready for the God Mode Swarm Gate.
Each package has: {target, storm_context, niche, script_context}
"""

import os
import json as _json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field

log = logging.getLogger("empire.satellite")

# ── Metro name normalisation (DB records may use full or short names) ──
_METRO_ALIASES = {
    "Dallas-Fort Worth": ["dallas", "fort worth", "dfw", "arlington", "plano", "irving"],
    "Dallas":            ["dallas", "dfw"],
    "Fort Worth":        ["fort worth", "ft worth"],
    "Houston":           ["houston"],
    "Austin":            ["austin"],
    "San Antonio":       ["san antonio", "sa"],
    "Wichita":           ["wichita"],
    "Oklahoma City":     ["oklahoma city", "okc"],
    "Kansas City":       ["kansas city", "kc"],
    "New Orleans":       ["new orleans", "nola"],
    "Memphis":           ["memphis"],
    "Atlanta":           ["atlanta"],
    "Nashville":         ["nashville"],
}


@dataclass
class StrikePackage:
    """One target + its storm context — ready for a Swarm Gate lane."""
    target_id: str
    warehouse_name: str
    address: str = ""
    city: str = ""
    state: str = ""
    phone: str = ""
    email: str = ""
    asset_value: float = 0.0
    damage_severity: str = ""
    metro: str = ""
    storm_event: str = ""
    storm_severity: str = ""
    storm_urgency: str = "Immediate"
    risk_level: str = ""
    risk_rank: int = 0
    niche: str = "Storm Damage Restoration"
    source: str = "satellite_strike"
    meta: Dict = field(default_factory=dict)


class SatelliteStrikeCore:
    """
    Scans storm tracking data and cross-references warehouse targets.

    Lifecycle per scan:
      1. Pull active storm_forecasts (last 24h, risk >= Slight)
      2. For each forecast metro, query radar_targets in that area
      3. De-duplicate against strike_log (already dispatched)
      4. Return StrikePackage list.
    """

    def __init__(
        self,
        get_db: Optional[Callable] = None,
        lookback_hours: int = 24,
        min_risk_rank: int = 4,  # Slight (4) or higher
        max_packages: int = 32,
    ):
        self.get_db = get_db
        self.lookback_hours = lookback_hours
        self.min_risk_rank = min_risk_rank
        self.max_packages = max_packages
        self.last_scan_at: Optional[datetime] = None
        self.last_package_count: int = 0

    # ── PUBLIC SURFACE ──────────────────────────────────────────
    async def scan(self) -> List[StrikePackage]:
        """
        Run a full scan cycle. Returns strike packages sorted by
        risk_rank (highest risk first) then asset_value (highest first).
        """
        self.last_scan_at = datetime.now(timezone.utc)
        packages = []

        if not self.get_db:
            log.warning("[satellite] no get_db wired — returning empty scan")
            return packages

        # 1. Pull active storm forecasts
        forecasts = self._fetch_storm_forecasts()
        if not forecasts:
            log.info("[satellite] scan: no active storm forecasts in lookback window")
            return packages

        log.info(f"[satellite] scan: {len(forecasts)} metro-risk forecasts found")

        # 2. For each forecast, query warehouse targets
        seen_targets: set = set()
        for fc in forecasts:
            metro = fc.get("metro", "")
            if not metro:
                continue
            risk_level = fc.get("risk_level", "Slight")
            risk_rank = int(fc.get("risk_rank", self.min_risk_rank))
            day = fc.get("day", 1)

            # Skip below threshold
            if risk_rank < self.min_risk_rank:
                continue

            targets = self._fetch_targets_for_metro(metro)
            log.debug(
                f"[satellite] metro={metro} risk={risk_level} rank={risk_rank} "
                f"day={day} targets={len(targets)}"
            )

            for t in targets:
                tid = t.get("id")
                if tid in seen_targets:
                    continue
                seen_targets.add(tid)

                # Dedup against strike_log
                if self._already_dispatched(tid):
                    continue

                # Infer niche from asset type + storm context
                niche = self._infer_niche(t, fc)

                packages.append(StrikePackage(
                    target_id=tid,
                    warehouse_name=t.get("warehouse_name") or t.get("name") or "Unknown",
                    address=t.get("address", ""),
                    city=t.get("city", ""),
                    state=t.get("state", ""),
                    phone=t.get("phone") or t.get("phone2", ""),
                    email=t.get("email", ""),
                    asset_value=float(t.get("asset_value") or 0),
                    damage_severity=t.get("damage_severity", ""),
                    metro=metro,
                    storm_event=fc.get("event") or f"{risk_level} Storm Risk",
                    storm_severity=fc.get("severity") or risk_level,
                    storm_urgency="Immediate" if risk_rank >= 5 else "Normal",
                    risk_level=risk_level,
                    risk_rank=risk_rank,
                    niche=niche,
                    meta={
                        "forecast_day": day,
                        "forecast_risk_rank": risk_rank,
                        "source": t.get("source", "radar"),
                    },
                ))

                if len(packages) >= self.max_packages:
                    break
            if len(packages) >= self.max_packages:
                break

        # Sort: highest risk first, then highest asset_value
        packages.sort(key=lambda p: (p.risk_rank, p.asset_value), reverse=True)
        self.last_package_count = len(packages)
        log.info(f"[satellite] scan complete: {len(packages)} strike packages")
        return packages

    # ── DB QUERIES ──────────────────────────────────────────────
    def _fetch_storm_forecasts(self) -> List[Dict]:
        """Pull active storm_forecasts from the last N hours."""
        try:
            db = self.get_db()
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)).isoformat()
            r = db.table("storm_forecasts") \
                .select("forecasts,count,updated_at") \
                .order("updated_at", desc=True) \
                .limit(1) \
                .execute()
            if not r.data:
                return []
            row = r.data[0]
            forecasts_str = row.get("forecasts")
            if not forecasts_str:
                return []
            if isinstance(forecasts_str, str):
                forecasts = _json.loads(forecasts_str)
            else:
                forecasts = forecasts_str
            return forecasts
        except Exception as e:
            log.warning(f"[satellite] storm_forecasts fetch failed: {e}")
            return []

    def _fetch_targets_for_metro(self, metro: str) -> List[Dict]:
        """Query radar_targets for warehouse targets in a given metro area."""
        try:
            db = self.get_db()
            aliases = _METRO_ALIASES.get(metro, [metro.lower()])

            # Build an OR filter across city field matching any metro alias
            # Supabase PostgREST `or` filter
            or_parts = ",".join([f"city.ilike.%{a}%" for a in aliases])
            r = db.table("radar_targets") \
                .select("id,warehouse_name,name,address,city,state,phone,phone2,email,asset_value,damage_severity,source,meta") \
                .or_(or_parts) \
                .order("asset_value", desc=True) \
                .limit(50) \
                .execute()
            return r.data or []
        except Exception as e:
            log.warning(f"[satellite] radar_targets fetch for {metro} failed: {e}")
            return []

    def _already_dispatched(self, target_id: str) -> bool:
        """Check strike_log for recent dispatches to this target."""
        try:
            db = self.get_db()
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours * 2)).isoformat()
            r = db.table("strike_log") \
                .select("id", count="exact") \
                .eq("target_id", target_id) \
                .gte("created_at", cutoff) \
                .execute()
            count = r.count if hasattr(r, "count") else len(r.data or [])
            return count > 0
        except Exception:
            return False

    # ── NICHE INFERENCE ─────────────────────────────────────────
    @staticmethod
    def _infer_niche(target: Dict, forecast: Dict) -> str:
        """Map storm risk level + target asset type to the most likely niche."""
        risk = (forecast.get("risk_level") or "").lower()
        damage = (target.get("damage_severity") or "").lower()

        # Tornado/nado → Tornado Damage Repair
        if "tornado" in risk or "nado" in risk:
            return "Tornado Damage Repair"
        if "hurricane" in risk:
            return "Hurricane Damage Restoration"
        if "hail" in risk:
            return "Hail Damage Repair"
        if "flood" in risk:
            return "Flood Damage Restoration"
        if "thunderstorm" in risk or "wind" in risk:
            return "Storm Damage Restoration"

        # Fallback: asset-type-based
        av = float(target.get("asset_value") or 0)
        if av > 10_000_000:
            return "Commercial Property Restoration"
        if av > 2_000_000:
            return "Industrial Storm Response"
        return "Roofing Restoration"

    # ── SNAPSHOT ────────────────────────────────────────────────
    def snapshot(self) -> Dict:
        return {
            "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "last_package_count": self.last_package_count,
            "lookback_hours": self.lookback_hours,
            "min_risk_rank": self.min_risk_rank,
            "max_packages": self.max_packages,
        }
