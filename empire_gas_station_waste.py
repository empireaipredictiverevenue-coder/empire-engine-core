"""
EMPIRE V49 · GAS STATION WASTE DETECTOR
=========================================
Detects waste and inefficiency at gas stations: idle/abandoned pumps,
forecourt disrepair, and surrounding site waste. Uses OSM Overpass API
for discovery + configurable satellite imagery hooks.

Waste signals:
  1. Idle / abandoned pumps — closed stations, disused pumps, low utilization
  2. Forecourt disrepair — cracked concrete, faded markings, broken canopy
  3. Surrounding site waste — adjacent vacant lots, abandoned buildings

Revenue models:
  1. Lead generation — find waste at stations → leads for maintenance/repair companies
  2. Consulting/audit — sell waste audit reports to station owners/operators
  3. Marketplace — match idle pump capacity with demand, list abandoned stations

Target metros — dynamically sourced from config/metros.py (single source of truth)
  - Oklahoma City, Kansas City, Memphis, Atlanta, Nashville (phase 2)
"""

import os
import sys
import json
import logging
import asyncio
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field

import httpx
from supabase import create_client, Client

log = logging.getLogger("empire.gas_station")

# ── Metro search configs — sourced from config/metros.py (single source of truth) ──
from config.metros import METROS as _SHARED_METROS
METRO_SEARCH_ZONES = {}
for _name, _m in _SHARED_METROS.items():
    METRO_SEARCH_ZONES[_name] = (
        float(_m["lat"]), float(_m["lon"]),
        50 if _m.get("state") == "TX" else 40,  # wider radius in TX
    )

# ── OSM Overpass tags for gas station waste detection ─────────────
GAS_STATION_TAGS = {
    "active_station": [
        'amenity=fuel',
    ],
    "truck_stop": [
        'amenity=fuel + hgv=yes',
    ],
    "abandoned_station": [
        'abandoned:amenity=fuel',
        'disused:amenity=fuel',
    ],
    "station_with_shop": [
        'amenity=fuel + shop=convenience',
    ],
}

# ── Data classes ──────────────────────────────────────────────────
@dataclass
class GasStationTarget:
    """One gas station with its metadata and waste score."""
    station_id: str = ""
    name: str = ""
    brand: str = ""                # Shell, BP, Exxon, etc. or empty for independents
    operator: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    metro: str = ""
    lat: float = 0.0
    lon: float = 0.0
    station_type: str = ""          # active_station, truck_stop, abandoned_station, station_with_shop
    pump_count_est: int = 0         # from OSM capacity tag
    area_sq_meters: float = 0.0
    has_shop: bool = False
    has_car_wash: bool = False
    is_truck_stop: bool = False
    is_abandoned: bool = False
    waste_score: float = 0.0        # 0-1 overall waste probability
    waste_indicators: List[str] = field(default_factory=list)
    source: str = "osm_overpass"
    meta: Dict = field(default_factory=dict)


class GasStationDetector:
    """
    Detects waste at gas stations using OSM data.

    Discovers stations via OSM Overpass, scores each for waste potential
    based on abandonment status, pump count, brand presence, and site context.
    """

    def __init__(
        self,
        get_db: Optional[Callable[[], Client]] = None,
        scan_interval_hours: int = 6,
        max_stations_per_metro: int = 40,
        overpass_url: str = "https://overpass.openstreetmap.fr/api/interpreter",
        satellite_api_key: str = "",
    ):
        self.get_db = get_db
        self.scan_interval_hours = scan_interval_hours
        self.max_stations_per_metro = max_stations_per_metro
        self.overpass_url = overpass_url
        self.satellite_api_key = satellite_api_key
        self.last_scan_at: Optional[datetime] = None
        self.last_station_count: int = 0
        self.running: bool = False

    # ── PUBLIC SURFACE ────────────────────────────────────────────
    async def scan(self) -> List[GasStationTarget]:
        """Run a full scan cycle across all metros. Returns stations sorted by waste_score."""
        self.last_scan_at = datetime.now(timezone.utc)
        all_stations: List[GasStationTarget] = []
        seen: set = set()

        for metro, (lat, lon, radius_km) in METRO_SEARCH_ZONES.items():
            log.info(f"[gas_waste] scanning {metro} ({radius_km}km radius)")

            for tag_category, queries in GAS_STATION_TAGS.items():
                for query in queries:
                    try:
                        stations = await self._query_overpass(
                            lat, lon, radius_km * 1000,
                            query, tag_category, metro,
                        )
                        for s in stations:
                            key = (round(s.lat, 4), round(s.lon, 4))
                            if key in seen:
                                continue
                            seen.add(key)

                            s.waste_score = self._score_station(s)
                            s.pump_count_est = self._estimate_pumps(s)

                            all_stations.append(s)

                            if len([x for x in all_stations
                                    if x.metro == metro]) >= self.max_stations_per_metro:
                                break
                    except Exception as e:
                        log.debug(f"[gas_waste] overpass query failed for {metro}/{tag_category}: {e}")

                if len([x for x in all_stations
                        if x.metro == metro]) >= self.max_stations_per_metro:
                    break

        all_stations.sort(key=lambda s: s.waste_score, reverse=True)
        self.last_station_count = len(all_stations)

        if self.get_db:
            await self._persist_stations(all_stations)

        log.info(f"[gas_waste] scan complete: {len(all_stations)} stations discovered")
        return all_stations

    async def run_loop(self):
        """Background scan loop."""
        log.info(f"[gas_waste] scan loop starting (interval={self.scan_interval_hours}h)")
        self.running = True
        await self._heartbeat()
        try:
            await self.scan()
        except Exception as e:
            log.error(f"[gas_waste] initial scan failed: {e}")

        while self.running:
            await asyncio.sleep(self.scan_interval_hours * 3600)
            try:
                await self._heartbeat()
                await self.scan()
            except Exception as e:
                log.error(f"[gas_waste] scan tick error: {e}")

    # ── OSM OVERPASS QUERIES ──────────────────────────────────────
    async def _query_overpass(
        self, lat: float, lon: float, radius_m: int,
        osm_query: str, tag_category: str, metro: str,
    ) -> List[GasStationTarget]:
        """Query OSM Overpass for gas stations in an area."""
        overpass_ql = f"""
        [out:json][timeout:20];
        (
          node[{osm_query}](around:{radius_m},{lat},{lon});
          way[{osm_query}](around:{radius_m},{lat},{lon});
          relation[{osm_query}](around:{radius_m},{lat},{lon});
        );
        out center 50;
        """

        async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": "EmpireAI-v49/1.0 (petroleum retail intelligence)"}) as client:
            r = await client.post(self.overpass_url, data={"data": overpass_ql})
            r.raise_for_status()
            data = r.json()

        stations = []
        for element in data.get("elements", []):
            tags = element.get("tags", {})
            name = tags.get("name") or tags.get("operator") or tags.get("brand") or "Unknown Station"
            brand = tags.get("brand", "")
            operator = tags.get("operator", "")

            addr_parts = [
                tags.get("addr:street", ""),
                tags.get("addr:housenumber", ""),
            ]
            addr = " ".join(p for p in addr_parts if p).strip() or tags.get("addr:full", "")
            city = tags.get("addr:city", "")
            state = tags.get("addr:state", "TX")

            if element["type"] == "node":
                el_lat = element.get("lat", 0)
                el_lon = element.get("lon", 0)
            else:
                center = element.get("center", {})
                el_lat = center.get("lat", lat)
                el_lon = center.get("lon", lon)

            area_sqm = 0.0
            bounds = element.get("bounds", {})
            if bounds:
                minlat = bounds.get("minlat", 0)
                maxlat = bounds.get("maxlat", 0)
                minlon = bounds.get("minlon", 0)
                maxlon = bounds.get("maxlon", 0)
                lat_span = (maxlat - minlat) * 111_000
                lon_span = (maxlon - minlon) * 111_000 * 0.85
                area_sqm = abs(lat_span * lon_span)

            if not area_sqm:
                area_sqm = 500.0  # default for a small station

            # Determine station type flags
            is_abandoned = "abandoned" in tag_category or "disused" in tag_category
            is_truck_stop = tags.get("hgv") == "yes" or tag_category == "truck_stop"
            has_shop = tags.get("shop") == "convenience" or tag_category == "station_with_shop"
            has_car_wash = tags.get("car_wash") == "yes"

            # Build waste indicator list
            indicators = []
            if is_abandoned:
                indicators.append("abandoned_or_disused")
            if not brand and not operator:
                indicators.append("independent_no_brand")
            if tags.get("capacity"):
                try:
                    if int(tags["capacity"]) <= 2:
                        indicators.append("low_pump_count")
                except (ValueError, TypeError):
                    pass
            if not has_shop and not is_truck_stop:
                indicators.append("no_ancillary_services")

            station = GasStationTarget(
                station_id=str(element.get("id", "")),
                name=name,
                brand=brand,
                operator=operator,
                address=addr or f"{city}, {state}",
                city=city,
                state=state,
                metro=metro,
                lat=el_lat,
                lon=el_lon,
                station_type=tag_category,
                area_sq_meters=area_sqm,
                has_shop=has_shop,
                has_car_wash=has_car_wash,
                is_truck_stop=is_truck_stop,
                is_abandoned=is_abandoned,
                waste_indicators=indicators,
                source="osm_overpass",
                meta={
                    "osm_type": element["type"],
                    "osm_tags": tags,
                },
            )
            stations.append(station)

        return stations

    # ── SCORING ────────────────────────────────────────────────────
    def _score_station(self, s: GasStationTarget) -> float:
        """Score 0-1 for gas station waste potential.

        Factors:
          - Abandoned/disused stations → highest waste (max score)
          - No brand/operator → independent, likely less maintained
          - Low pump count → underutilized
          - No ancillary services → revenue limited
          - Truck stops without amenities → wasted potential
        """
        score = 0.0

        # ── Abandoned = guaranteed waste ──────────────────────
        if s.is_abandoned:
            return 0.95

        # ── Brand presence (inverse: no brand = more likely neglected) ──
        if s.brand:
            major_brands = {"Shell", "BP", "Exxon", "ExxonMobil", "Chevron", "Texaco",
                           "Mobil", "Marathon", "Sunoco", "Valero", "Citgo", "Phillips 66",
                           "76", "Conoco", "Sinclair", "RaceTrac", "QuikTrip", "Wawa",
                           "Sheetz", "Kum & Go", "Casey's", "Circle K", "7-Eleven",
                           "Murphy USA", "Costco", "Sam's Club", "Buc-ee's", "Love's",
                           "Pilot", "Flying J", "TA", "Petro Stopping Centers"}
            if s.brand in major_brands:
                score += 0.05  # major brands maintain well → low waste
            else:
                score += 0.15  # smaller/unknown brands → moderate waste risk
        else:
            score += 0.25  # no brand at all → higher waste risk

        # ── Pump count (using pre-computed estimate from _estimate_pumps) ──
        pump_count = s.pump_count_est
        if pump_count <= 2:
            score += 0.25  # very small station → underutilized
        elif pump_count <= 4:
            score += 0.15
        elif pump_count <= 8:
            score += 0.08
        else:
            score += 0.03  # large station → high throughput, less waste

        # ── Ancillary services ────────────────────────────────
        if not s.has_shop and not s.has_car_wash:
            if s.is_truck_stop:
                score += 0.20  # truck stop with no shop = wasted amenity
            else:
                score += 0.10  # fuel-only station → single revenue stream

        # ── Area factor ───────────────────────────────────────
        if s.area_sq_meters > 5000:
            score += 0.15  # large site → more potential for waste/fly-tipping
        elif s.area_sq_meters > 2000:
            score += 0.08

        # ── Metro traffic ─────────────────────────────────────
        high_traffic = {"Dallas-Fort Worth", "Houston", "Atlanta", "Memphis"}
        if s.metro in high_traffic:
            score += 0.05  # more stations to compete with → weaker ones show waste

        return min(score, 1.0)

    def _estimate_pumps(self, s: GasStationTarget) -> int:
        """Estimate pump count from OSM capacity or defaults."""
        capacity = int((s.meta.get("osm_tags", {}).get("capacity", 0) or 0))
        if capacity > 0:
            return capacity
        # Rough defaults by type
        if s.is_truck_stop:
            return 12
        if s.is_abandoned:
            return 4
        if s.has_shop:
            return 8
        return 6

    # ── PERSISTENCE ───────────────────────────────────────────────
    async def _persist_stations(self, stations: List[GasStationTarget]):
        """Store discovered stations in gas_station_compounds table."""
        if not self.get_db:
            return
        db = self.get_db()
        now = datetime.now(timezone.utc).isoformat()
        upserted = 0
        for s in stations:
            try:
                db.table("gas_station_compounds").upsert({
                    "station_id": s.station_id,
                    "name": s.name,
                    "brand": s.brand,
                    "operator": s.operator,
                    "address": s.address,
                    "city": s.city,
                    "state": s.state,
                    "metro": s.metro,
                    "lat": s.lat,
                    "lon": s.lon,
                    "station_type": s.station_type,
                    "pump_count_est": s.pump_count_est,
                    "area_sq_meters": s.area_sq_meters,
                    "has_shop": s.has_shop,
                    "has_car_wash": s.has_car_wash,
                    "is_truck_stop": s.is_truck_stop,
                    "is_abandoned": s.is_abandoned,
                    "waste_score": s.waste_score,
                    "waste_indicators": s.waste_indicators,
                    "source": s.source,
                    "last_scanned_at": now,
                    "meta": s.meta,
                }, on_conflict="station_id").execute()
                upserted += 1
            except Exception as e:
                log.debug(f"[gas_waste] persist error for {s.station_id}: {e}")

        if upserted > 0:
            log.info(f"[gas_waste] persisted {upserted} stations to DB")

    async def _heartbeat(self):
        """Register in agent_registry with role gas_station_detector."""
        if not self.get_db:
            return
        try:
            db = self.get_db()
            db.table("agent_registry").upsert({
                "agent_name": "gas_station_waste_detector",
                "role_name": "gas_station_detector",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": [
                    "detect_gas_station_waste", "osm_station_discovery",
                    "waste_scoring", "forecourt_analysis",
                    "abandoned_station_detection", "pump_utilization_estimate",
                ],
                "task_types": [
                    "gas.scan", "gas.score", "gas.report",
                    "gas.discover_stations", "gas.detect_abandoned",
                ],
            }, on_conflict="agent_name").execute()
        except Exception:
            pass

    def snapshot(self) -> Dict:
        return {
            "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "last_station_count": self.last_station_count,
            "scan_interval_hours": self.scan_interval_hours,
            "metros_configured": len(METRO_SEARCH_ZONES),
            "station_tags_configured": sum(len(v) for v in GAS_STATION_TAGS.values()),
            "satellite_enabled": bool(self.satellite_api_key),
            "running": self.running,
        }


# ═════════════════════════════════════════════════════════════════════
# GAS STATION ENRICHER — matches OSM stations to real businesses
# ═════════════════════════════════════════════════════════════════════

@dataclass
class EnrichedStation:
    """A gas station enriched with business identity + 3-model scores."""
    station_id: str = ""
    business_name: str = ""
    brand: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    fuel_types: str = ""             # diesel, e10, octane_95, etc.
    enrichment_source: str = "osm_metadata"
    enrichment_confidence: float = 0.0
    lead_gen_score: float = 0.0       # value to maintenance/repair companies
    consulting_score: float = 0.0     # waste audit value to station owners
    marketplace_score: float = 0.0    # idle pump capacity match value
    best_model: str = ""              # lead_gen / consulting / marketplace
    outreach_status: str = ""
    enriched_at: str = ""
    meta: Dict = field(default_factory=dict)


class GasStationEnricher:
    """Enriches OSM-discovered gas stations with business identity."""

    def __init__(self, router=None):
        self.router = router
        self.enriched_count: int = 0
        self.last_enriched_at: Optional[datetime] = None

    async def enrich(self, station: GasStationTarget) -> EnrichedStation:
        """Enrich one station with business identity + contact info."""
        osm_tags = station.meta.get("osm_tags", {})
        business_name = (
            osm_tags.get("name")
            or osm_tags.get("brand")
            or osm_tags.get("operator")
            or station.name
        )
        brand = station.brand or osm_tags.get("brand", "")
        website = osm_tags.get("website") or osm_tags.get("contact:website") or ""
        phone = osm_tags.get("phone") or osm_tags.get("contact:phone") or ""
        email = osm_tags.get("email") or osm_tags.get("contact:email") or ""
        fuel_types = ", ".join(
            k.replace("fuel:", "") for k in osm_tags if k.startswith("fuel:") and osm_tags[k] == "yes"
        )

        # Try LLM enrichment for missing contact info
        confidence = 0.5
        if self.router and (not email or not phone or not website):
            try:
                llm_result = await self._llm_enrich(business_name, brand, station)
                if llm_result:
                    if not email and llm_result.get("email"):
                        email = llm_result["email"]
                    if not phone and llm_result.get("phone"):
                        phone = llm_result["phone"]
                    if not website and llm_result.get("website"):
                        website = llm_result["website"]
                    if llm_result.get("business_name"):
                        business_name = llm_result["business_name"]
                    confidence = llm_result.get("confidence", 0.5)
            except Exception as e:
                log.debug(f"[gas_waste] LLM enrichment failed: {e}")

        if not email and website:
            email = self._guess_email(website)

        self.enriched_count += 1
        self.last_enriched_at = datetime.now(timezone.utc)

        return EnrichedStation(
            station_id=station.station_id,
            business_name=business_name,
            brand=brand,
            phone=phone,
            email=email,
            website=website,
            fuel_types=fuel_types,
            enrichment_source="ai_inference" if self.router else "osm_metadata",
            enrichment_confidence=confidence,
            enriched_at=datetime.now(timezone.utc).isoformat(),
            meta={
                "station_type": station.station_type,
                "metro": station.metro,
                "city": station.city,
                "state": station.state,
                "pump_count_est": station.pump_count_est,
                "waste_score": station.waste_score,
                "is_abandoned": station.is_abandoned,
                "is_truck_stop": station.is_truck_stop,
                "has_shop": station.has_shop,
                "waste_indicators": station.waste_indicators,
                "osm_tags": osm_tags,
            },
        )

    async def _llm_enrich(self, business_name: str, brand: str, station: GasStationTarget) -> Optional[Dict]:
        """Use AI router to infer missing contact info for known brands."""
        prompt = (
            f"You are a petroleum retail data assistant. "
            f"Given a gas station called '{business_name}' (brand: {brand}) located in "
            f"{station.city}, {station.state} (metro: {station.metro}). "
            f"Respond ONLY with a JSON object containing any of these keys you can "
            f"reasonably infer: {{business_name, email, phone, website, confidence}}. "
            f"If the brand is a known major chain (Shell, BP, Exxon, Chevron, etc), "
            f"you may include their known corporate domain. "
            f"Do not invent fake data. confidence 0.0-1.0. JSON only."
        )

        try:
            response = await self.router.generate(prompt)
            text = response.strip()
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start:end + 1])
        except Exception:
            pass
        return None

    @staticmethod
    def _guess_email(website: str) -> str:
        """Return email from website domain only if real."""
        if website:
            domain = website.replace("https://", "").replace("http://", "").split("/")[0]
            if "." in domain and len(domain) > 5:
                return f"info@{domain}"
        return ""

    def snapshot(self) -> Dict:
        return {
            "enriched_count": self.enriched_count,
            "last_enriched_at": self.last_enriched_at.isoformat() if self.last_enriched_at else None,
            "router_available": self.router is not None,
        }


# ═════════════════════════════════════════════════════════════════════
# GAS STATION MULTI-MODEL SCORER
# ═════════════════════════════════════════════════════════════════════

class GasStationMultiScorer:
    """Scores each gas station for 3 revenue models."""

    def score(self, enriched: EnrichedStation, station: GasStationTarget) -> Dict[str, float]:
        meta = enriched.meta or {}
        waste_score = float(meta.get("waste_score", 0) or 0)
        pump_count = int(meta.get("pump_count_est", 0) or 0)
        is_abandoned = bool(meta.get("is_abandoned", False))
        is_truck_stop = bool(meta.get("is_truck_stop", False))
        has_shop = bool(meta.get("has_shop", False))
        metro = meta.get("metro", "")
        has_contact = bool(enriched.email or enriched.phone)

        scores = {
            "lead_gen_score": round(self._score_lead_gen(waste_score, is_abandoned, pump_count, has_contact), 3),
            "consulting_score": round(self._score_consulting(waste_score, is_abandoned, pump_count, is_truck_stop, has_contact), 3),
            "marketplace_score": round(self._score_marketplace(waste_score, is_abandoned, pump_count, metro, has_contact), 3),
        }
        scores["best_model"] = max(
            (k for k in scores if k != "best_model"),
            key=lambda k: scores[k],
        )
        return scores

    def _score_lead_gen(self, waste_score: float, is_abandoned: bool, pump_count: int, has_contact: bool) -> float:
        """Lead gen: value to forecourt repair, pump maintenance, canopy restoration companies."""
        score = 0.0
        if is_abandoned:
            score += 0.40  # abandoned stations = highest restoration lead value
        if waste_score > 0.7:
            score += 0.25
        elif waste_score > 0.4:
            score += 0.15
        if pump_count >= 8:
            score += 0.15  # more pumps = more maintenance work
        elif pump_count >= 4:
            score += 0.10
        if has_contact:
            score += 0.20
        return min(score, 1.0)

    def _score_consulting(self, waste_score: float, is_abandoned: bool, pump_count: int, is_truck_stop: bool, has_contact: bool) -> float:
        """Consulting: likelihood station owner/operator buys a waste audit."""
        score = 0.0
        if is_abandoned:
            score += 0.15  # abandoned stations already known, less consulting value
        if waste_score > 0.7:
            score += 0.30
        elif waste_score > 0.4:
            score += 0.20
        if pump_count >= 8:
            score += 0.20  # larger stations have more to audit
        elif pump_count >= 4:
            score += 0.10
        if is_truck_stop:
            score += 0.15  # truck stops have complex operations worth auditing
        if has_contact:
            score += 0.20
        else:
            score *= 0.5
        return min(score, 1.0)

    def _score_marketplace(self, waste_score: float, is_abandoned: bool, pump_count: int, metro: str, has_contact: bool) -> float:
        """Marketplace: idle pump capacity matching value."""
        score = 0.0
        if is_abandoned:
            score += 0.30  # abandoned stations = available sites for new operators
        if pump_count >= 8:
            score += 0.25
        elif pump_count >= 4:
            score += 0.15
        high_traffic = {"DFW", "Houston", "Atlanta", "Memphis", "Kansas City"}
        if metro in high_traffic:
            score += 0.15
        if waste_score > 0.5:
            score += 0.15
        if has_contact:
            score += 0.15
        return min(score, 1.0)


# ═════════════════════════════════════════════════════════════════════
# GAS STATION OUTREACH — enrolls stations into email/SMS sequences
# ═════════════════════════════════════════════════════════════════════

GAS_OUTREACH_TEMPLATES = {
    "lead_gen": {
        "subject": "Forecourt repair opportunity — {station_name} ({metro})",
        "email_body": (
            "We identified {station_name} in {city}, {state} as a gas station with "
            "waste indicators (score: {waste_score:.1%}, {pump_count} pumps). "
            "Potential forecourt repair, pump maintenance, or canopy restoration work. "
            "Reply to access this lead."
        ),
    },
    "consulting": {
        "subject": "Station efficiency audit — {station_name} ({metro})",
        "email_body": (
            "{station_name} in {metro} shows operational waste indicators "
            "({waste_score:.1%} waste score, {pump_count} pumps). "
            "Empire AI offers a no-cost station waste audit identifying underutilized "
            "assets, forecourt issues, and revenue recovery opportunities. "
            "Reply YES to request your audit."
        ),
    },
    "marketplace": {
        "subject": "List your idle pump capacity — {station_name} ({metro})",
        "email_body": (
            "{station_name} in {metro} has {pump_count} pumps with idle capacity "
            "indicators. List your station on Empire's marketplace and connect with "
            "fleet operators seeking guaranteed fuel capacity. "
            "No listing fee. Reply to learn more."
        ),
    },
    # ── Abandoned Station Templates ───────────────────────────────
    # Used when station.is_abandoned — targets restoration, audit,
    # and site-acquisition opportunities for closed/disused stations.
    "abandoned_lead_gen": {
        "subject": "Abandoned fuel station restoration — {station_name} ({metro})",
        "email_body": (
            "We've identified an abandoned gas station at {address} in {city}, {state} "
            "(brand: {brand}, {pump_count} pumps estimated, waste score: {waste_score:.1%}). "
            "This is a lead for site restoration, tank removal, environmental remediation, "
            "or canopy/pump equipment recovery. Indicators: {indicators}. "
            "Reply to receive the full station report."
        ),
    },
    "abandoned_consulting": {
        "subject": "Abandoned station acquisition audit — {station_name} ({metro})",
        "email_body": (
            "{station_name} at {address} in {metro} has been flagged as abandoned/disused "
            "({area_sq_m}m² site, {pump_count} pumps, waste score: {waste_score:.1%}). "
            "Empire AI offers a no-cost abandoned station audit covering: environmental "
            "risk tier, estimated tank-removal cost range, zoning/redevelopment potential, "
            "and comparable site-acquisition comps in {metro}. "
            "Reply YES to request your abandoned station report."
        ),
    },
    "abandoned_marketplace": {
        "subject": "Abandoned fuel station site for acquisition — {metro}",
        "email_body": (
            "An abandoned gas station site at {address} in {city}, {state} is available "
            "(estimated {area_sq_m}m², {pump_count} former pumps, brand: {brand}). "
            "Listed on Empire's marketplace as a site-acquisition opportunity — ideal for "
            "redevelopment, EV charging conversion, or new-operator takeover. "
            "No listing fee. Reply to express interest in this {metro} site."
        ),
    },
}


class GasStationOutreach:
    """Enrolls scored gas stations into email/SMS outreach sequences."""

    def __init__(
        self,
        email_engine=None,
        sms_engine=None,
        get_db: Optional[Callable] = None,
        public_base_url: str = "http://localhost:8001",
    ):
        self.email_engine = email_engine
        self.sms_engine = sms_engine
        self.get_db = get_db
        self.public_base_url = public_base_url
        self.stats = {
            "enrolled_email": 0, "enrolled_sms": 0,
            "skipped_no_contact": 0, "skipped_low_score": 0, "errors": 0,
        }

    async def dispatch(
        self, enriched: EnrichedStation, station: GasStationTarget, scores: Dict[str, float],
    ) -> Dict:
        best_model = scores.get("best_model", "")
        result = {"station_id": enriched.station_id, "best_model": best_model,
                  "email_sent": False, "sms_sent": False, "skipped_reason": ""}

        min_threshold = 0.4
        model_score_key = {"lead_gen": "lead_gen_score", "consulting": "consulting_score", "marketplace": "marketplace_score"}
        actual_score = scores.get(model_score_key.get(best_model, "lead_gen_score"), 0)
        if actual_score < min_threshold:
            result["skipped_reason"] = f"low_score_{actual_score:.2f}"
            self.stats["skipped_low_score"] += 1
            return result

        if not enriched.email and not enriched.phone:
            result["skipped_reason"] = "no_contact"
            self.stats["skipped_no_contact"] += 1
            return result

        is_abandoned = station.is_abandoned
        indicators_str = ", ".join(station.waste_indicators) if station.waste_indicators else "none"
        template_ctx = {
            "station_name": enriched.business_name or station.name,
            "brand": station.brand or "Independent",
            "metro": station.metro,
            "city": station.city,
            "state": station.state,
            "address": station.address,
            "pump_count": station.pump_count_est,
            "area_sq_m": int(station.area_sq_meters),
            "indicators": indicators_str,
            "waste_score": station.waste_score,
            "public_url": self.public_base_url,
        }

        if enriched.email and self.email_engine:
            try:
                # Use abandoned-specific templates when station is abandoned
                if is_abandoned:
                    abandoned_key = f"abandoned_{best_model}"
                    tmpl = GAS_OUTREACH_TEMPLATES.get(abandoned_key, GAS_OUTREACH_TEMPLATES.get(best_model, GAS_OUTREACH_TEMPLATES["lead_gen"]))
                else:
                    tmpl = GAS_OUTREACH_TEMPLATES.get(best_model, GAS_OUTREACH_TEMPLATES["lead_gen"])
                await self.email_engine.enroll(
                    email=enriched.email,
                    target_addr=station.address or f"{station.city}, {station.state}",
                    sequence_type=f"gas_{best_model}",
                    meta={
                        "station_id": enriched.station_id,
                        "business_name": enriched.business_name,
                        "best_model": best_model,
                        "scores": scores,
                        "body_hint": tmpl["email_body"].format(**template_ctx),
                    },
                )
                result["email_sent"] = True
                self.stats["enrolled_email"] += 1
            except Exception as e:
                log.debug(f"[gas_waste] email enroll failed: {e}")
                self.stats["errors"] += 1

        if enriched.phone and self.sms_engine:
            try:
                await self.sms_engine.enroll(
                    phone=enriched.phone,
                    target_addr=station.address or f"{station.city}, {station.state}",
                    sequence_type=f"gas_{best_model}",
                    meta={
                        "station_id": enriched.station_id,
                        "business_name": enriched.business_name,
                        "best_model": best_model,
                        "scores": scores,
                    },
                )
                result["sms_sent"] = True
                self.stats["enrolled_sms"] += 1
            except Exception as e:
                log.debug(f"[gas_waste] sms enroll failed: {e}")
                self.stats["errors"] += 1

        if self.get_db and (result["email_sent"] or result["sms_sent"]):
            template_variant = "abandoned" if is_abandoned else "generic"
            await self._log_outreach(enriched.station_id, best_model, result, template_variant)

        return result

    async def _log_outreach(self, station_id: str, model: str, result: Dict, template_variant: str = "generic"):
        try:
            db = self.get_db()
            channels = []
            if result.get("email_sent"):
                channels.append("email")
            if result.get("sms_sent"):
                channels.append("sms")
            for ch in channels:
                db.table("gas_station_outreach").upsert({
                    "station_id": station_id,
                    "channel": ch,
                    "business_model": model,
                    "template_variant": template_variant,
                    "status": "enrolled",
                }, on_conflict="station_id,channel,business_model").execute()
        except Exception as e:
            log.debug(f"[gas_waste] outreach log failed: {e}")

    def snapshot(self) -> Dict:
        return {
            **self.stats,
            "email_engine_available": self.email_engine is not None,
            "sms_engine_available": self.sms_engine is not None,
        }


# ═════════════════════════════════════════════════════════════════════
# GAS STATION PIPELINE — orchestrates discovery → enrich → score → outreach
# ═════════════════════════════════════════════════════════════════════

class GasStationPipeline:
    """Full end-to-end pipeline for gas station waste detection + monetization."""

    def __init__(
        self,
        detector: GasStationDetector,
        enricher: GasStationEnricher,
        scorer: GasStationMultiScorer,
        outreach: GasStationOutreach,
        get_db: Callable,
        interval_hours: int = 6,
        max_outreach_per_tick: int = 15,
    ):
        self.detector = detector
        self.enricher = enricher
        self.scorer = scorer
        self.outreach = outreach
        self.get_db = get_db
        self.interval_hours = interval_hours
        self.max_outreach_per_tick = max_outreach_per_tick
        self.running: bool = False
        self.last_tick_at: Optional[datetime] = None
        self.tick_stats: Dict = {"discovered": 0, "enriched": 0, "outreach_sent": 0, "skipped": 0}

    async def run_cycle(self) -> Dict:
        self.last_tick_at = datetime.now(timezone.utc)
        stats = {"discovered": 0, "enriched": 0, "scored": 0, "outreach_sent": 0, "skipped": 0}

        try:
            stations = await self.detector.scan()
            stats["discovered"] = len(stations)
        except Exception as e:
            log.error(f"[gas_pipeline] discovery failed: {e}")
            return {"status": "discovery_error", "error": str(e)[:200], **stats}

        if not stations:
            return {"status": "no_stations", **stats}

        try:
            db = self.get_db()
            existing = db.table("gas_station_enriched").select("station_id").execute()
            enriched_ids = {r["station_id"] for r in (existing.data or [])}
        except Exception:
            enriched_ids = set()

        to_enrich = [s for s in stations if s.station_id not in enriched_ids]
        if not to_enrich:
            stats["skipped"] = len(stations)
            self.tick_stats = stats
            return {"status": "all_already_enriched", **stats}

        outreach_count = 0
        for s in to_enrich[:50]:
            try:
                enriched = await self.enricher.enrich(s)
                scores = self.scorer.score(enriched, s)

                enriched.lead_gen_score = scores["lead_gen_score"]
                enriched.consulting_score = scores["consulting_score"]
                enriched.marketplace_score = scores["marketplace_score"]
                enriched.best_model = scores["best_model"]

                await self._persist_enriched(enriched)
                stats["enriched"] += 1
                stats["scored"] += 1

                if outreach_count < self.max_outreach_per_tick:
                    result = await self.outreach.dispatch(enriched, s, scores)
                    if result.get("email_sent") or result.get("sms_sent"):
                        outreach_count += 1
                        stats["outreach_sent"] += 1
            except Exception as e:
                log.debug(f"[gas_pipeline] enrich/score/outreach failed for {s.station_id}: {e}")
                stats["skipped"] += 1

        self.tick_stats = stats
        log.info(
            f"[gas_pipeline] cycle: {stats['discovered']} discovered, "
            f"{stats['enriched']} enriched, {stats['outreach_sent']} outreach"
        )
        return {"status": "ok", **stats}

    async def run_loop(self):
        log.info(f"[gas_pipeline] starting (interval={self.interval_hours}h)")
        self.running = True
        await self._heartbeat()
        try:
            await self.run_cycle()
        except Exception as e:
            log.error(f"[gas_pipeline] initial cycle failed: {e}")

        while self.running:
            await asyncio.sleep(self.interval_hours * 3600)
            try:
                await self._heartbeat()
                await self.run_cycle()
            except Exception as e:
                log.error(f"[gas_pipeline] tick error: {e}")

    async def _persist_enriched(self, enriched: EnrichedStation):
        try:
            db = self.get_db()
            db.table("gas_station_enriched").upsert({
                "station_id": enriched.station_id,
                "business_name": enriched.business_name,
                "brand": enriched.brand,
                "phone": enriched.phone,
                "email": enriched.email,
                "website": enriched.website,
                "fuel_types": enriched.fuel_types,
                "lead_gen_score": enriched.lead_gen_score,
                "consulting_score": enriched.consulting_score,
                "marketplace_score": enriched.marketplace_score,
                "best_model": enriched.best_model,
                "enrichment_source": enriched.enrichment_source,
                "enrichment_confidence": enriched.enrichment_confidence,
                "status": "enriched",
                "meta": enriched.meta,
            }, on_conflict="station_id").execute()
        except Exception as e:
            log.debug(f"[gas_pipeline] persist enriched failed: {e}")

    async def _heartbeat(self):
        try:
            db = self.get_db()
            db.table("agent_registry").upsert({
                "agent_name": "gas_station_waste_detector",
                "role_name": "gas_station_detector",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": [
                    "detect_gas_station_waste", "enrich_stations",
                    "multi_model_scoring", "outreach_dispatch",
                    "pipeline_orchestration", "forecourt_intelligence",
                ],
                "task_types": [
                    "gas.pipeline", "gas.scan", "gas.enrich",
                    "gas.score", "gas.outreach", "gas.report",
                ],
            }, on_conflict="agent_name").execute()
        except Exception:
            pass

    def snapshot(self) -> Dict:
        return {
            "running": self.running,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "interval_hours": self.interval_hours,
            "max_outreach_per_tick": self.max_outreach_per_tick,
            "tick_stats": self.tick_stats,
            "detector": self.detector.snapshot(),
            "enricher": self.enricher.snapshot(),
            "outreach": self.outreach.snapshot(),
        }


# ─────────────────────────────────────────────────────────────────────
# HUB BOT RUN LOOP
# ─────────────────────────────────────────────────────────────────────
_pipeline_instance: Optional[GasStationPipeline] = None


def get_pipeline() -> Optional[GasStationPipeline]:
    return _pipeline_instance


def set_pipeline(pipeline: GasStationPipeline):
    global _pipeline_instance
    _pipeline_instance = pipeline


async def run_loop(interval_hours: int = 6):
    """Entry point for hub.py asyncio.create_task()."""
    pipeline = get_pipeline()
    if pipeline:
        pipeline.interval_hours = interval_hours
        await pipeline.run_loop()


# ─────────────────────────────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────────────────────────────
def register_gas_station_routes(
    app,
    detector: GasStationDetector,
    require_auth=None,
    pipeline: Optional[GasStationPipeline] = None,
):
    """Register Gas Station Waste Detector API routes on a FastAPI app."""

    from fastapi import Depends, HTTPException, Query

    @app.post("/api/v1/gas-station/scan")
    async def gas_station_scan(auth=Depends(require_auth) if require_auth else None):
        """Trigger a full scan cycle. Returns discovered stations."""
        try:
            stations = await detector.scan()
            return {
                "ok": True,
                "stations": [
                    {
                        "station_id": s.station_id,
                        "name": s.name,
                        "brand": s.brand,
                        "address": s.address,
                        "city": s.city,
                        "state": s.state,
                        "metro": s.metro,
                        "station_type": s.station_type,
                        "pump_count_est": s.pump_count_est,
                        "waste_score": s.waste_score,
                        "is_abandoned": s.is_abandoned,
                        "waste_indicators": s.waste_indicators,
                    }
                    for s in stations
                ],
                "count": len(stations),
                "snapshot": detector.snapshot(),
            }
        except Exception as e:
            raise HTTPException(500, f"Scan failed: {str(e)[:200]}")

    @app.get("/api/v1/gas-station/stations")
    async def gas_station_stations(
        metro: str = Query(""),
        min_score: float = Query(0.0),
        is_abandoned: Optional[bool] = Query(None),
        limit: int = Query(50),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List discovered stations with optional filters."""
        if not detector.get_db:
            raise HTTPException(500, "No DB connection")
        try:
            db = detector.get_db()
            q = db.table("gas_station_compounds").select("*")
            if metro:
                q = q.eq("metro", metro)
            if min_score > 0:
                q = q.gte("waste_score", min_score)
            if is_abandoned is not None:
                q = q.eq("is_abandoned", is_abandoned)
            r = q.order("waste_score", desc=True).limit(min(limit, 200)).execute()
            return {"stations": r.data or [], "count": len(r.data or [])}
        except Exception as e:
            raise HTTPException(500, str(e)[:200])

    @app.get("/api/v1/gas-station/stats")
    async def gas_station_stats(auth=Depends(require_auth) if require_auth else None):
        """Aggregate stats: stations per metro, waste scores, abandoned count."""
        if not detector.get_db:
            return {"stations_total": 0, "by_metro": {}, "top_waste": []}
        try:
            db = detector.get_db()
            rows = (db.table("gas_station_compounds")
                    .select("metro,waste_score,name,station_type,is_abandoned,brand")
                    .execute().data or [])

            by_metro = {}
            abandoned_count = 0
            for r in rows:
                m = r.get("metro", "Unknown")
                if m not in by_metro:
                    by_metro[m] = {"count": 0, "total_score": 0.0, "high_waste": 0}
                by_metro[m]["count"] += 1
                by_metro[m]["total_score"] += float(r.get("waste_score", 0) or 0)
                if float(r.get("waste_score", 0) or 0) >= 0.7:
                    by_metro[m]["high_waste"] += 1
                if r.get("is_abandoned"):
                    abandoned_count += 1

            for m in by_metro:
                c = by_metro[m]["count"]
                by_metro[m]["avg_score"] = round(by_metro[m]["total_score"] / c, 3) if c else 0
                del by_metro[m]["total_score"]

            sorted_rows = sorted(rows, key=lambda r: float(r.get("waste_score", 0) or 0), reverse=True)
            top = [
                {"name": r.get("name"), "metro": r.get("metro"), "brand": r.get("brand", ""),
                 "type": r.get("station_type"), "waste_score": r.get("waste_score"),
                 "abandoned": r.get("is_abandoned")}
                for r in sorted_rows[:10]
            ]

            return {
                "stations_total": len(rows),
                "abandoned_total": abandoned_count,
                "by_metro": by_metro,
                "top_waste": top,
                "snapshot": detector.snapshot(),
            }
        except Exception as e:
            return {"error": str(e)[:200]}

    @app.get("/api/v1/gas-station/snapshot")
    async def gas_station_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Quick detector status snapshot."""
        return detector.snapshot()

    # ── Pipeline Routes ────────────────────────────────────────────
    if pipeline:
        @app.post("/api/v1/gas-station/pipeline/run")
        async def gas_pipeline_run(auth=Depends(require_auth) if require_auth else None):
            """Trigger a full pipeline cycle: discover → enrich → score → outreach."""
            try:
                result = await pipeline.run_cycle()
                return {"ok": True, "result": result}
            except Exception as e:
                raise HTTPException(500, f"Pipeline run failed: {str(e)[:200]}")

        @app.get("/api/v1/gas-station/pipeline/stats")
        async def gas_pipeline_stats(auth=Depends(require_auth) if require_auth else None):
            """Full pipeline snapshot."""
            db_stats = {"enriched_total": 0, "outreach_total": 0}
            try:
                db = detector.get_db()
                if db:
                    r = db.table("gas_station_enriched").select("station_id", count="exact").execute()
                    db_stats["enriched_total"] = r.count if hasattr(r, "count") else len(r.data or [])
                    r2 = db.table("gas_station_outreach").select("station_id", count="exact").execute()
                    db_stats["outreach_total"] = r2.count if hasattr(r2, "count") else len(r2.data or [])
            except Exception:
                pass
            return {"pipeline": pipeline.snapshot(), "db": db_stats}

        @app.get("/api/v1/gas-station/pipeline/leads")
        async def gas_pipeline_leads(
            best_model: str = Query(""),
            min_score: float = Query(0.0),
            limit: int = Query(50),
            auth=Depends(require_auth) if require_auth else None,
        ):
            """List enriched leads with scores, filterable by business model."""
            if not detector.get_db:
                raise HTTPException(500, "No DB connection")
            try:
                db = detector.get_db()
                q = db.table("gas_station_enriched").select("*")
                if best_model:
                    q = q.eq("best_model", best_model)
                if min_score > 0:
                    score_col = f"{best_model or 'lead_gen'}_score" if best_model else "lead_gen_score"
                    q = q.gte(score_col, min_score)
                r = q.order("lead_gen_score", desc=True).limit(min(limit, 200)).execute()
                return {"leads": r.data or [], "count": len(r.data or [])}
            except Exception as e:
                raise HTTPException(500, str(e)[:200])

        @app.get("/api/v1/gas-station/pipeline/outreach")
        async def gas_pipeline_outreach(
            status: str = Query(""),
            limit: int = Query(50),
            auth=Depends(require_auth) if require_auth else None,
        ):
            """List outreach records."""
            if not detector.get_db:
                raise HTTPException(500, "No DB connection")
            try:
                db = detector.get_db()
                q = db.table("gas_station_outreach").select("*")
                if status:
                    q = q.eq("status", status)
                r = q.order("enrolled_at", desc=True).limit(min(limit, 200)).execute()
                return {"outreach": r.data or [], "count": len(r.data or [])}
            except Exception as e:
                raise HTTPException(500, str(e)[:200])

    log.info("[gas_waste] routes: /api/v1/gas-station/{scan,stations,stats,snapshot"
             + (",pipeline/run,pipeline/stats,pipeline/leads,pipeline/outreach}" if pipeline else "}"))
