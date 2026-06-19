"""
EMPIRE V49 · IDLE ASSET DETECTOR
==================================
Detects idle trailers and parked assets in logistics/trucking compounds
using open data (OSM Overpass API) + configurable satellite imagery hooks.

Revenue models:
  1. Lead generation — find idle trailers → generate leads for logistics brokers
  2. Consulting/audit — sell waste reports to companies with idle assets
  3. Marketplace — match idle trailer owners with companies that need capacity

Pipeline:
  1. Discover compounds via OSM Overpass API (free)
  2. Store in logistics_compounds table
  3. Score each compound for "waste potential" (size, location, trailer count est.)
  4. Generate leads for logistics brokers, freight companies, trailer rental
  5. Satellite imagery detection hook (SkyFi / Maxar — plug in when credentialed)

Target metros (expanding from Texas base):
  - DFW, Houston, San Antonio, Austin (initial)
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

log = logging.getLogger("empire.idle_asset")

# ── Metro search configs (lat, lon, radius_km) ────────────────────
METRO_SEARCH_ZONES = {
    "DFW":          (32.7767, -96.7970, 80),
    "Houston":      (29.7604, -95.3698, 80),
    "San Antonio":  (29.4241, -98.4936, 60),
    "Austin":       (30.2672, -97.7431, 50),
    "Oklahoma City":(35.4676, -97.5164, 50),
    "Kansas City":  (39.0997, -94.5786, 50),
    "Memphis":      (35.1495, -90.0490, 50),
    "Atlanta":      (33.7490, -84.3880, 60),
    "Nashville":    (36.1627, -86.7816, 50),
}

# ── OSM Overpass tags for logistics / trucking compounds ──────────
# Each tag category maps to a compound type
COMPOUND_TAGS = {
    "truck_yard": [
        'industrial=trucking',
        'industrial=logistics',
        'amenity=truck_parking',
        'landuse=industrial + industrial=logistics',
    ],
    "warehouse": [
        'building=warehouse',
        'industrial=warehouse',
        'landuse=industrial + building=warehouse',
        'abandoned:building=warehouse',
        'disused:building=warehouse',
    ],
    "distribution": [
        'office=logistics',
        'industrial=distribution',
        'building=industrial + industrial=distribution',
    ],
    "loading_dock": [
        'amenity=loading_dock',
    ],
}

# ── Data classes ──────────────────────────────────────────────────
@dataclass
class CompoundTarget:
    """One logistics compound with its metadata and waste score."""
    compound_id: str = ""
    name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    metro: str = ""
    lat: float = 0.0
    lon: float = 0.0
    compound_type: str = ""       # truck_yard, warehouse, distribution, loading_dock
    area_sq_meters: float = 0.0   # estimated from OSM polygon area
    trailer_capacity_est: int = 0  # rough estimate: area / 60sqm per trailer
    idle_score: float = 0.0       # 0-1 waste probability score
    idle_indicators: List[str] = field(default_factory=list)
    source: str = "osm_overpass"
    meta: Dict = field(default_factory=dict)


class IdleAssetDetector:
    """
    Detects idle trailers and parked assets in logistics compounds.

    MVP: Uses OSM Overpass API to discover compounds. Hooks for SkyFi /
    Maxar satellite imagery when API credentials are available.
    """

    def __init__(
        self,
        get_db: Optional[Callable[[], Client]] = None,
        scan_interval_hours: int = 6,
        max_compounds_per_metro: int = 50,
        overpass_url: str = "https://overpass.openstreetmap.fr/api/interpreter",
        satellite_api_key: str = "",
    ):
        self.get_db = get_db
        self.scan_interval_hours = scan_interval_hours
        self.max_compounds_per_metro = max_compounds_per_metro
        self.overpass_url = overpass_url
        self.satellite_api_key = satellite_api_key
        self.last_scan_at: Optional[datetime] = None
        self.last_compound_count: int = 0
        self.running: bool = False

    # ── PUBLIC SURFACE ────────────────────────────────────────────
    async def scan(self) -> List[CompoundTarget]:
        """
        Run a full scan cycle across all metros.
        Returns discovered compounds sorted by idle_score (highest first).
        """
        self.last_scan_at = datetime.now(timezone.utc)
        all_compounds: List[CompoundTarget] = []
        seen: set = set()

        for metro, (lat, lon, radius_km) in METRO_SEARCH_ZONES.items():
            log.info(f"[idle_asset] scanning {metro} ({radius_km}km radius)")

            for tag_category, queries in COMPOUND_TAGS.items():
                for query in queries:
                    try:
                        compounds = await self._query_overpass(
                            lat, lon, radius_km * 1000,  # convert to meters
                            query, tag_category, metro,
                        )
                        for c in compounds:
                            key = (round(c.lat, 4), round(c.lon, 4))
                            if key in seen:
                                continue
                            seen.add(key)

                            # Score the compound
                            c.idle_score = self._score_compound(c)
                            c.trailer_capacity_est = self._estimate_capacity(c)

                            all_compounds.append(c)

                            if len([x for x in all_compounds
                                    if x.metro == metro]) >= self.max_compounds_per_metro:
                                break
                    except Exception as e:
                        log.debug(f"[idle_asset] overpass query failed for {metro}/{tag_category}: {e}")

                if len([x for x in all_compounds
                        if x.metro == metro]) >= self.max_compounds_per_metro:
                    break

        # Sort by idle_score descending
        all_compounds.sort(key=lambda c: c.idle_score, reverse=True)
        self.last_compound_count = len(all_compounds)

        # Persist to DB
        if self.get_db:
            await self._persist_compounds(all_compounds)

        log.info(f"[idle_asset] scan complete: {len(all_compounds)} compounds discovered")
        return all_compounds

    async def run_loop(self):
        """Background scan loop. Runs every scan_interval_hours."""
        log.info(f"[idle_asset] scan loop starting (interval={self.scan_interval_hours}h)")
        self.running = True

        # Register in agent_registry
        await self._heartbeat()

        # Run initial scan
        try:
            await self.scan()
        except Exception as e:
            log.error(f"[idle_asset] initial scan failed: {e}")

        while self.running:
            await asyncio.sleep(self.scan_interval_hours * 3600)
            try:
                await self._heartbeat()
                await self.scan()
            except Exception as e:
                log.error(f"[idle_asset] scan tick error: {e}")

    # ── OSM OVERPASS QUERIES ──────────────────────────────────────
    async def _query_overpass(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        osm_query: str,
        tag_category: str,
        metro: str,
    ) -> List[CompoundTarget]:
        """Query OSM Overpass for logistics compounds in an area."""
        # Build the Overpass QL query
        overpass_ql = f"""
        [out:json][timeout:20];
        (
          node[{osm_query}](around:{radius_m},{lat},{lon});
          way[{osm_query}](around:{radius_m},{lat},{lon});
          relation[{osm_query}](around:{radius_m},{lat},{lon});
        );
        out center 50;
        """

        async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": "EmpireAI-v49/1.0 (B2B logistics intelligence)"}) as client:
            r = await client.post(self.overpass_url, data={"data": overpass_ql})
            r.raise_for_status()
            data = r.json()

        compounds = []
        for element in data.get("elements", []):
            tags = element.get("tags", {})
            name = tags.get("name") or tags.get("operator") or tags.get("brand") or "Unknown Compound"
            addr_parts = [
                tags.get("addr:street", ""),
                tags.get("addr:housenumber", ""),
            ]
            addr = " ".join(p for p in addr_parts if p).strip() or tags.get("addr:full", "")
            city = tags.get("addr:city", "")
            state = tags.get("addr:state", "TX")

            # Get coordinates
            if element["type"] == "node":
                el_lat = element.get("lat", 0)
                el_lon = element.get("lon", 0)
            else:
                center = element.get("center", {})
                el_lat = center.get("lat", lat)
                el_lon = center.get("lon", lon)

            # Estimate area from OSM bounds if available
            area_sqm = 0.0
            bounds = element.get("bounds", {})
            if bounds:
                minlat = bounds.get("minlat", 0)
                maxlat = bounds.get("maxlat", 0)
                minlon = bounds.get("minlon", 0)
                maxlon = bounds.get("maxlon", 0)
                # Approximate: 1 degree lat ≈ 111km, 1 degree lon ≈ 111km * cos(lat)
                lat_span = (maxlat - minlat) * 111_000
                lon_span = (maxlon - minlon) * 111_000 * 0.85  # cos(32°) ≈ 0.85
                area_sqm = abs(lat_span * lon_span)

            # Building area from OSM tags
            if not area_sqm:
                area_str = tags.get("building:area") or tags.get("area") or ""
                try:
                    area_sqm = float(area_str)
                except (ValueError, TypeError):
                    area_sqm = 1000.0  # default for a small compound

            compound = CompoundTarget(
                compound_id=str(element.get("id", "")),
                name=name,
                address=addr or f"{city}, {state}",
                city=city,
                state=state,
                metro=metro,
                lat=el_lat,
                lon=el_lon,
                compound_type=tag_category,
                area_sq_meters=area_sqm,
                source="osm_overpass",
                idle_indicators=self._build_waste_indicators(tag_category, tags),
                meta={
                    "osm_type": element["type"],
                    "osm_tags": tags,
                },
            )
            compounds.append(compound)

        return compounds

    # ── SCORING ────────────────────────────────────────────────────
    @staticmethod
    def _build_waste_indicators(tag_category: str, tags: Dict) -> List[str]:
        """Build a list of waste indicator tags from OSM metadata."""
        indicators = []

        # Abandoned/disused detection
        if tag_category == "warehouse" and any(k.startswith("abandoned:") or k.startswith("disused:") for k in tags):
            indicators.append("abandoned_or_disused")

        # No operator/brand = potentially underutilized / owner-operated
        if not tags.get("operator") and not tags.get("brand") and not tags.get("name"):
            indicators.append("no_identity")

        # Warehouse-specific: few loading docks = underutilized
        if tag_category == "warehouse":
            dock_count = tags.get("loading_dock:count") or tags.get("dock:count") or ""
            if dock_count:
                try:
                    if int(dock_count) <= 2:
                        indicators.append("low_dock_count")
                except (ValueError, TypeError):
                    pass

        # Large building with no further subdivision = potentially vacant
        if tag_category == "warehouse" and not tags.get("shop") and not tags.get("office"):
            indicators.append("raw_warehouse_space")

        return indicators

    # ── SCORING ────────────────────────────────────────────────────
    def _score_compound(self, c: CompoundTarget) -> float:
        """
        Score 0-1 for "waste potential" — idle trailers + warehouse underutilization.
        Higher = more likely to have idle assets worth monetizing.

        Factors:
          - Abandoned/disused warehouses → maximum waste (0.95+)
          - Area: larger compounds → more idle potential
          - Type: truck_yards highest potential; abandoned warehouses beat active ones
          - Waste indicators: abandoned, no_identity, low_dock_count, raw_warehouse_space
          - Compound density in metro (lots of compounds = competitive logistics hub)
        """
        score = 0.0

        # ── Abandoned / disused detection → maximum waste ──────
        if "abandoned_or_disused" in c.idle_indicators:
            return 0.95  # abandoned = guaranteed waste

        # ── Type factor ─────────────────────────────────────────
        type_weights = {
            "truck_yard": 0.9,
            "distribution": 0.7,
            "warehouse": 0.6,     # bumped from 0.5 — warehouse waste is now a primary signal
            "loading_dock": 0.3,
        }
        score += type_weights.get(c.compound_type, 0.3) * 0.4

        # ── Warehouse-specific waste indicators ──────────────────
        if c.compound_type == "warehouse":
            if "no_identity" in c.idle_indicators:
                score += 0.20  # no name/operator/brand → high underutilization
            if "low_dock_count" in c.idle_indicators:
                score += 0.15  # few loading docks for size → underutilized
            if "raw_warehouse_space" in c.idle_indicators:
                score += 0.10  # no subdivision = likely vacant shell

        # ── Area factor — larger compounds can hold more idle assets ──
        if c.area_sq_meters > 50000:
            score += 0.3
        elif c.area_sq_meters > 10000:
            score += 0.2
        elif c.area_sq_meters > 2000:
            score += 0.1

        # ── Known logistics hubs ─────────────────────────────────
        high_traffic_metros = {"DFW", "Houston", "Atlanta", "Memphis"}
        if c.metro in high_traffic_metros:
            score += 0.1

        # ── Entity name contains key logistics terms ──────────────
        entity_lower = c.name.lower()
        logistics_terms = ["logistics", "trucking", "freight", "transport",
                          "distribution", "warehouse", "fulfillment", "terminal",
                          "carrier", "fleet", "depot", "yard"]
        match_count = sum(1 for term in logistics_terms if term in entity_lower)
        score += min(match_count * 0.05, 0.2)

        return min(score, 1.0)

    def _estimate_capacity(self, c: CompoundTarget) -> int:
        """Estimate how many trailers could fit in this compound."""
        sqm_per_trailer = 60.0  # ~12m trailer + maneuvering space
        if c.compound_type == "truck_yard":
            sqm_per_trailer = 40.0  # tighter packing in dedicated yards
        return max(1, int(c.area_sq_meters / sqm_per_trailer))

    # ── PERSISTENCE ───────────────────────────────────────────────
    async def _persist_compounds(self, compounds: List[CompoundTarget]):
        """Store discovered compounds in the logistics_compounds table."""
        if not self.get_db:
            return

        db = self.get_db()
        now = datetime.now(timezone.utc).isoformat()
        upserted = 0

        for c in compounds:
            try:
                db.table("logistics_compounds").upsert({
                    "compound_id": c.compound_id,
                    "name": c.name,
                    "address": c.address,
                    "city": c.city,
                    "state": c.state,
                    "metro": c.metro,
                    "lat": c.lat,
                    "lon": c.lon,
                    "compound_type": c.compound_type,
                    "area_sq_meters": c.area_sq_meters,
                    "trailer_capacity_est": c.trailer_capacity_est,
                    "idle_score": c.idle_score,
                    "idle_indicators": c.idle_indicators,
                    "source": c.source,
                    "last_scanned_at": now,
                    "meta": c.meta,
                }, on_conflict="compound_id").execute()
                upserted += 1
            except Exception as e:
                log.debug(f"[idle_asset] persist error for {c.compound_id}: {e}")

        if upserted > 0:
            log.info(f"[idle_asset] persisted {upserted} compounds to DB")

    async def _heartbeat(self):
        """Register/ping in agent_registry with role waste_detector."""
        if not self.get_db:
            return
        try:
            db = self.get_db()
            db.table("agent_registry").upsert({
                "agent_name": "idle_asset_detector",
                "role_name": "waste_detector",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": [
                    "detect_idle_assets", "osm_compound_discovery",
                    "waste_scoring", "logistics_intelligence",
                    "satellite_hook", "trailer_capacity_estimate",
                    "warehouse_waste_detection", "abandoned_building_detection",
                ],
                "task_types": [
                    "idle.scan", "idle.score", "idle.report",
                    "idle.discover_compounds", "idle.estimate_waste",
                    "idle.detect_abandoned_warehouse", "idle.underutilization_check",
                ],
            }, on_conflict="agent_name").execute()
        except Exception:
            pass

    # ── SNAPSHOT ──────────────────────────────────────────────────
    def snapshot(self) -> Dict:
        return {
            "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "last_compound_count": self.last_compound_count,
            "scan_interval_hours": self.scan_interval_hours,
            "metros_configured": len(METRO_SEARCH_ZONES),
            "compound_tags_configured": sum(len(v) for v in COMPOUND_TAGS.values()),
            "satellite_enabled": bool(self.satellite_api_key),
            "running": self.running,
        }


# ═════════════════════════════════════════════════════════════════════
# IDLE ASSET ENRICHER — matches OSM compounds to real businesses
# ═════════════════════════════════════════════════════════════════════

@dataclass
class EnrichedCompound:
    """A logistics compound enriched with business identity + 3-model scores."""
    compound_id: str = ""
    business_name: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    industry: str = ""              # logistics, trucking, warehousing, distribution
    employee_est: str = ""          # small / medium / large
    enrichment_source: str = "ai_inference"
    enrichment_confidence: float = 0.0
    lead_gen_score: float = 0.0      # value to logistics brokers
    consulting_score: float = 0.0    # waste audit value
    marketplace_score: float = 0.0   # idle capacity match value
    best_model: str = ""             # lead_gen / consulting / marketplace
    outreach_status: str = ""        # pending / enrolled / contacted / converted
    enriched_at: str = ""
    meta: Dict = field(default_factory=dict)


class IdleAssetEnricher:
    """
    Enriches OSM-discovered compounds with business identity.

    Uses OSM metadata (name, operator, brand tags) + local LLM inference
    to infer real business names, guess email/website patterns, and
    classify industry. No external API keys required.
    """

    def __init__(self, router=None):
        """
        Args:
            router: an AIRouter-compatible object with a .ask(prompt) method.
                    If None, enrichment uses OSM tags only (no LLM).
        """
        self.router = router
        self.enriched_count: int = 0
        self.last_enriched_at: Optional[datetime] = None

    async def enrich(self, compound: CompoundTarget) -> EnrichedCompound:
        """Enrich one compound with business identity + contact info."""
        # Start with OSM metadata
        osm_tags = compound.meta.get("osm_tags", {})
        business_name = (
            osm_tags.get("name")
            or osm_tags.get("operator")
            or osm_tags.get("brand")
            or compound.name
        )
        website = osm_tags.get("website") or osm_tags.get("contact:website") or ""
        phone = osm_tags.get("phone") or osm_tags.get("contact:phone") or ""
        email = osm_tags.get("email") or osm_tags.get("contact:email") or ""
        industry = self._infer_industry(compound, business_name)

        # Try LLM enrichment if router is available and data is sparse
        confidence = 0.5
        if self.router and (not email or not phone or not website):
            try:
                llm_result = await self._llm_enrich(business_name, compound)
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
                log.debug(f"[idle_asset] LLM enrichment failed for {compound.compound_id}: {e}")

        # Generate email if still missing (pattern guess from business name)
        if not email and business_name and business_name != "Unknown Compound":
            email = self._guess_email(business_name, website)

        self.enriched_count += 1
        self.last_enriched_at = datetime.now(timezone.utc)

        return EnrichedCompound(
            compound_id=compound.compound_id,
            business_name=business_name,
            phone=phone,
            email=email,
            website=website,
            industry=industry,
            enrichment_source="ai_inference" if self.router else "osm_metadata",
            enrichment_confidence=confidence,
            enriched_at=datetime.now(timezone.utc).isoformat(),
            meta={
                "compound_type": compound.compound_type,
                "metro": compound.metro,
                "city": compound.city,
                "state": compound.state,
                "trailer_capacity_est": compound.trailer_capacity_est,
                "idle_score": compound.idle_score,
                "osm_tags": osm_tags,
            },
        )

    async def _llm_enrich(self, business_name: str, compound: CompoundTarget) -> Optional[Dict]:
        """Use the AI router to infer missing contact info."""
        prompt = (
            f"You are a logistics business data assistant. "
            f"Given a logistics compound called '{business_name}' located in "
            f"{compound.city}, {compound.state} (metro: {compound.metro}), "
            f"type: {compound.compound_type}, area: {compound.area_sq_meters:.0f} sqm. "
            f"Respond ONLY with a JSON object containing any of these keys you can "
            f"reasonably infer: {{business_name, email, phone, website, confidence}}. "
            f"If you cannot infer something, omit the key. "
            f"Do not invent fake data. If the business name is clearly known (e.g. "
            f"'Amazon', 'FedEx', 'UPS', 'XPO Logistics'), you may include known domains. "
            f"confidence should be 0.0-1.0 based on how sure you are. JSON only."
        )

        try:
            response = await self.router.generate(prompt)
            # Extract JSON from response
            text = response.strip()
            # Find JSON object boundaries
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                json_str = text[start:end + 1]
                return json.loads(json_str)
        except Exception:
            pass
        return None

    @staticmethod
    def _infer_industry(compound: CompoundTarget, business_name: str) -> str:
        """Classify the compound's industry from type and name."""
        name_lower = business_name.lower()
        if compound.compound_type == "truck_yard":
            return "Trucking & Freight"
        if "logistics" in name_lower or compound.compound_type == "distribution":
            return "Logistics & Distribution"
        if "warehouse" in name_lower or compound.compound_type == "warehouse":
            return "Warehousing & Storage"
        if "dock" in name_lower or compound.compound_type == "loading_dock":
            return "Freight Terminal"
        return "Transportation & Logistics"

    @staticmethod
    def _guess_email(business_name: str, website: str) -> str:
        """Return email from website domain, or empty if no real domain available."""
        if website:
            domain = website.replace("https://", "").replace("http://", "").split("/")[0]
            if "." in domain and len(domain) > 5:
                return f"info@{domain}"
        # Don't generate fake emails from business names — they will bounce
        return ""

    def snapshot(self) -> Dict:
        return {
            "enriched_count": self.enriched_count,
            "last_enriched_at": self.last_enriched_at.isoformat() if self.last_enriched_at else None,
            "router_available": self.router is not None,
        }


# ═════════════════════════════════════════════════════════════════════
# MULTI-MODEL SCORER — scores each compound for 3 business models
# ═════════════════════════════════════════════════════════════════════

class IdleAssetMultiScorer:
    """
    Scores each enriched compound for 3 revenue models:
      1. Lead Gen — selling idle trailer leads to logistics brokers
      2. Consulting — selling waste audit reports to compound owners
      3. Marketplace — matching idle capacity with demand

    Each score is 0.0-1.0. The best_model is the highest score.
    """

    def score(self, enriched: EnrichedCompound, compound: CompoundTarget) -> Dict[str, float]:
        """Return {lead_gen_score, consulting_score, marketplace_score, best_model}."""
        meta = enriched.meta or {}
        idle_score = float(meta.get("idle_score", 0) or 0)
        capacity = int(meta.get("trailer_capacity_est", 0) or 0)
        ctype = meta.get("compound_type", "")
        metro = meta.get("metro", "")
        has_contact = bool(enriched.email or enriched.phone)

        scores = {
            "lead_gen_score": round(self._score_lead_gen(idle_score, capacity, ctype, has_contact), 3),
            "consulting_score": round(self._score_consulting(idle_score, capacity, ctype, has_contact), 3),
            "marketplace_score": round(self._score_marketplace(idle_score, capacity, ctype, metro, has_contact), 3),
        }
        scores["best_model"] = max(
            (k for k in scores if k != "best_model"),
            key=lambda k: scores[k],
        )
        return scores

    def _score_lead_gen(self, idle_score: float, capacity: int, ctype: str, has_contact: bool) -> float:
        """Lead gen score: value of idle trailer leads to logistics brokers."""
        score = 0.0
        # Truck yards + distribution centers are highest value for broker leads
        if ctype in ("truck_yard",):
            score += 0.35
        elif ctype == "distribution":
            score += 0.25
        elif ctype == "warehouse":
            score += 0.15
        # Capacity matters — more trailers = more leads
        if capacity > 100:
            score += 0.30
        elif capacity > 30:
            score += 0.20
        elif capacity > 10:
            score += 0.10
        # Idle score from discovery
        score += idle_score * 0.20
        # Contact info available = actionable lead
        if has_contact:
            score += 0.15
        return min(score, 1.0)

    def _score_consulting(self, idle_score: float, capacity: int, ctype: str, has_contact: bool) -> float:
        """Consulting score: likelihood compound owner buys a waste audit."""
        score = 0.0
        # Larger compounds have more to gain from efficiency audits
        if capacity > 100:
            score += 0.35
        elif capacity > 30:
            score += 0.25
        elif capacity > 10:
            score += 0.15
        # High idle score = visible waste = strong audit pitch
        score += idle_score * 0.30
        # Warehouses and distribution centers are most receptive to audits
        if ctype in ("warehouse", "distribution"):
            score += 0.15
        # Contact info critical for consulting outreach
        if has_contact:
            score += 0.20
        else:
            score *= 0.5  # no-contact compounds are much harder to pitch
        return min(score, 1.0)

    def _score_marketplace(self, idle_score: float, capacity: int, ctype: str, metro: str, has_contact: bool) -> float:
        """Marketplace score: idle capacity matching value."""
        score = 0.0
        # Capacity is the product — more trailers = more listings
        if capacity > 100:
            score += 0.30
        elif capacity > 30:
            score += 0.20
        elif capacity > 10:
            score += 0.10
        # Truck yards are the core marketplace supply
        if ctype == "truck_yard":
            score += 0.25
        elif ctype == "distribution":
            score += 0.15
        # High-traffic metros have more demand for capacity
        high_traffic = {"DFW", "Houston", "Atlanta", "Memphis", "Kansas City"}
        if metro in high_traffic:
            score += 0.15
        # Idle score relevance
        score += idle_score * 0.15
        # Contact optional for marketplace (self-serve listings)
        if has_contact:
            score += 0.15
        return min(score, 1.0)


# ═════════════════════════════════════════════════════════════════════
# IDLE ASSET OUTREACH — enrolls compounds into email/SMS sequences
# ═════════════════════════════════════════════════════════════════════

# Email templates per business model
OUTREACH_TEMPLATES = {
    "lead_gen": {
        "subject": "Idle trailer leads for {metro} — {company}",
        "email_body": (
            "We've identified {capacity_est} estimated trailer slots at {compound_name} "
            "in {city}, {state} — with high idle potential (score: {idle_score:.1%}). "
            "These compounds represent lead opportunities for logistics brokers seeking "
            "idle trailer capacity to match with demand. Reply to learn more or visit "
            "{public_url}/ppl to browse available leads in {metro}."
        ),
    },
    "consulting": {
        "subject": "Asset efficiency audit — {company} ({metro})",
        "email_body": (
            "Your facility at {address} in {metro} shows idle asset indicators "
            "(estimated {capacity_est} trailer slots, waste score: {idle_score:.1%}). "
            "Empire AI offers a no-cost waste audit report identifying underutilized "
            "capacity and revenue recovery opportunities. Reply YES to request your audit."
        ),
    },
    "marketplace": {
        "subject": "List your idle capacity — {company} ({metro})",
        "email_body": (
            "{company} in {metro} has an estimated {capacity_est} trailer slots. "
            "List your idle capacity on Empire's marketplace and connect with companies "
            "that need short-term trailer space. No listing fee. Visit {public_url}/ppl "
            "to get started."
        ),
    },
    # ── Warehouse-Specific Templates ────────────────────────────
    # Used when compound_type == "warehouse" — targets abandoned restoration
    # and underutilized space leasing opportunities.
    "warehouse_lead_gen": {
        "subject": "Idle warehouse restoration opportunity — {metro}",
        "email_body": (
            "We've identified an abandoned/disused warehouse at {address} in {city}, {state} "
            "(estimated {area_sq_m}m², waste score: {idle_score:.1%}). "
            "This property represents a lead for restoration contractors, environmental "
            "remediation, or adaptive reuse developers. Our detection flagged it as high-priority "
            "warehouse waste — idle indicators: {indicators}. "
            "Reply to receive the full asset report. Visit {public_url}/ppl for details."
        ),
    },
    "warehouse_consulting": {
        "subject": "Warehouse underutilization audit — {company} ({metro})",
        "email_body": (
            "Your warehouse facility at {address} in {metro} shows strong underutilization signals "
            "({area_sq_m}m² space, waste score: {idle_score:.1%}). "
            "Empire AI offers a no-cost warehouse efficiency audit covering: vacant square footage, "
            "loading dock utilization, subdivision opportunities, and revenue-per-square-foot "
            "benchmarks against {metro} peers. Indicators detected: {indicators}. "
            "Reply YES to schedule your free warehouse audit report."
        ),
    },
    "warehouse_marketplace": {
        "subject": "Monetize your underutilized warehouse space — {company} ({metro})",
        "email_body": (
            "{company}'s warehouse at {address} has an estimated {area_sq_m}m² of space "
            "with underutilization signals (score: {idle_score:.1%}). "
            "List your idle square footage on Empire's marketplace to connect with businesses "
            "seeking short-term warehouse/sublease space in {metro}. No listing fee — only pay "
            "when you lease. Visit {public_url}/ppl to activate your warehouse listing today."
        ),
    },
}


class IdleAssetOutreach:
    """
    Enrolls enriched + scored compounds into email/SMS outreach sequences
    based on their best business model.
    """

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
            "enrolled_email": 0,
            "enrolled_sms": 0,
            "skipped_no_contact": 0,
            "skipped_low_score": 0,
            "errors": 0,
        }

    async def dispatch(
        self,
        enriched: EnrichedCompound,
        compound: CompoundTarget,
        scores: Dict[str, float],
    ) -> Dict:
        """Dispatch outreach for one compound using its best business model."""
        best_model = scores.get("best_model", "")
        result = {
            "compound_id": enriched.compound_id,
            "best_model": best_model,
            "email_sent": False,
            "sms_sent": False,
            "skipped_reason": "",
        }

        # Minimum score threshold — don't outreach for low scores
        min_threshold = 0.4
        model_score_key = {"lead_gen": "lead_gen_score", "consulting": "consulting_score", "marketplace": "marketplace_score"}
        actual_score = scores.get(model_score_key.get(best_model, "lead_gen_score"), 0)
        if actual_score < min_threshold:
            result["skipped_reason"] = f"low_score_{actual_score:.2f}"
            self.stats["skipped_low_score"] += 1
            return result

        # Need at least one contact method
        if not enriched.email and not enriched.phone:
            result["skipped_reason"] = "no_contact"
            self.stats["skipped_no_contact"] += 1
            return result

        # Build template context
        is_warehouse = compound.compound_type == "warehouse"
        indicators_str = ", ".join(compound.idle_indicators) if compound.idle_indicators else "none"
        template_ctx = {
            "company": enriched.business_name or compound.name,
            "compound_name": compound.name,
            "metro": compound.metro,
            "city": compound.city,
            "state": compound.state,
            "address": compound.address,
            "capacity_est": compound.trailer_capacity_est,
            "area_sq_m": int(compound.area_sq_meters),
            "indicators": indicators_str,
            "idle_score": compound.idle_score,
            "public_url": self.public_base_url,
        }

        # ── Email outreach ──────────────────────────────────
        if enriched.email and self.email_engine:
            try:
                # Use warehouse-specific templates when compound_type is "warehouse"
                if is_warehouse:
                    warehouse_key = f"warehouse_{best_model}"
                    tmpl = OUTREACH_TEMPLATES.get(warehouse_key, OUTREACH_TEMPLATES.get(best_model, OUTREACH_TEMPLATES["lead_gen"]))
                else:
                    tmpl = OUTREACH_TEMPLATES.get(best_model, OUTREACH_TEMPLATES["lead_gen"])
                subject = tmpl["subject"].format(**template_ctx)

                await self.email_engine.enroll(
                    email=enriched.email,
                    target_addr=compound.address or f"{compound.city}, {compound.state}",
                    sequence_type=f"idle_{best_model}",
                    meta={
                        "compound_id": enriched.compound_id,
                        "business_name": enriched.business_name,
                        "best_model": best_model,
                        "scores": scores,
                        "capacity_est": compound.trailer_capacity_est,
                        "body_hint": tmpl["email_body"].format(**template_ctx),
                    },
                )
                result["email_sent"] = True
                self.stats["enrolled_email"] += 1
            except Exception as e:
                log.debug(f"[idle_asset] email enroll failed for {enriched.compound_id}: {e}")
                self.stats["errors"] += 1

        # ── SMS outreach ────────────────────────────────────
        if enriched.phone and self.sms_engine:
            try:
                await self.sms_engine.enroll(
                    phone=enriched.phone,
                    target_addr=compound.address or f"{compound.city}, {compound.state}",
                    sequence_type=f"idle_{best_model}",
                    meta={
                        "compound_id": enriched.compound_id,
                        "business_name": enriched.business_name,
                        "best_model": best_model,
                        "scores": scores,
                    },
                )
                result["sms_sent"] = True
                self.stats["enrolled_sms"] += 1
            except Exception as e:
                log.debug(f"[idle_asset] sms enroll failed for {enriched.compound_id}: {e}")
                self.stats["errors"] += 1

        # ── Log outreach to DB ─────────────────────────────
        if self.get_db and (result["email_sent"] or result["sms_sent"]):
            template_variant = "warehouse" if is_warehouse else "generic"
            await self._log_outreach(enriched.compound_id, best_model, result, template_variant)

        return result

    async def _log_outreach(self, compound_id: str, model: str, result: Dict, template_variant: str = "generic"):
        """Persist outreach attempt to idle_asset_outreach."""
        try:
            db = self.get_db()
            channels = []
            if result.get("email_sent"):
                channels.append("email")
            if result.get("sms_sent"):
                channels.append("sms")
            for ch in channels:
                db.table("idle_asset_outreach").upsert({
                    "compound_id": compound_id,
                    "channel": ch,
                    "business_model": model,
                    "template_variant": template_variant,
                    "status": "enrolled",
                }, on_conflict="compound_id,channel,business_model").execute()
        except Exception as e:
            log.debug(f"[idle_asset] outreach log failed: {e}")

    def snapshot(self) -> Dict:
        return {
            **self.stats,
            "email_engine_available": self.email_engine is not None,
            "sms_engine_available": self.sms_engine is not None,
        }


# ═════════════════════════════════════════════════════════════════════
# IDLE ASSET PIPELINE — orchestrates discovery → enrich → score → outreach
# ═════════════════════════════════════════════════════════════════════

class IdleAssetPipeline:
    """
    Full end-to-end pipeline for idle asset detection + monetization.

    Lifecycle per tick:
      1. Discover compounds via OSM Overpass (IdleAssetDetector.scan)
      2. Pull unscored compounds from logistics_compounds
      3. Enrich each with business identity (IdleAssetEnricher.enrich)
      4. Score each for 3 business models (IdleAssetMultiScorer.score)
      5. Persist enrichment + scores to idle_asset_enriched
      6. Dispatch outreach for top-scoring compounds (IdleAssetOutreach.dispatch)
    """

    def __init__(
        self,
        detector: IdleAssetDetector,
        enricher: IdleAssetEnricher,
        scorer: IdleAssetMultiScorer,
        outreach: IdleAssetOutreach,
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
        self.tick_stats: Dict = {
            "discovered": 0,
            "enriched": 0,
            "outreach_sent": 0,
            "skipped": 0,
            "errors": 0,
        }

    # ── PUBLIC SURFACE ────────────────────────────────────────────
    async def run_cycle(self) -> Dict:
        """Run one full pipeline cycle."""
        self.last_tick_at = datetime.now(timezone.utc)
        stats = {"discovered": 0, "enriched": 0, "scored": 0, "outreach_sent": 0, "skipped": 0}

        # 1. Discovery — scan for new compounds
        try:
            compounds = await self.detector.scan()
            stats["discovered"] = len(compounds)
        except Exception as e:
            log.error(f"[idle_pipeline] discovery failed: {e}")
            return {"status": "discovery_error", "error": str(e)[:200], **stats}

        if not compounds:
            return {"status": "no_compounds", **stats}

        # 2. Pull compounds not yet enriched (from DB)
        try:
            db = self.get_db()
            existing_enriched = db.table("idle_asset_enriched").select("compound_id").execute()
            enriched_ids = {r["compound_id"] for r in (existing_enriched.data or [])}
        except Exception:
            enriched_ids = set()

        to_enrich = [c for c in compounds if c.compound_id not in enriched_ids]
        if not to_enrich:
            stats["skipped"] = len(compounds)
            self.tick_stats = stats
            return {"status": "all_already_enriched", **stats}

        # 3. Enrich + Score + Outreach (serially for safety)
        outreach_count = 0
        for c in to_enrich[:50]:  # cap per tick
            try:
                enriched = await self.enricher.enrich(c)
                scores = self.scorer.score(enriched, c)

                # Stamp scores onto enriched
                enriched.lead_gen_score = scores["lead_gen_score"]
                enriched.consulting_score = scores["consulting_score"]
                enriched.marketplace_score = scores["marketplace_score"]
                enriched.best_model = scores["best_model"]

                # Persist
                await self._persist_enriched(enriched)
                stats["enriched"] += 1
                stats["scored"] += 1

                # Outreach for top-scoring compounds
                if outreach_count < self.max_outreach_per_tick:
                    result = await self.outreach.dispatch(enriched, c, scores)
                    if result.get("email_sent") or result.get("sms_sent"):
                        outreach_count += 1
                        stats["outreach_sent"] += 1

            except Exception as e:
                log.debug(f"[idle_pipeline] enrich/score/outreach failed for {c.compound_id}: {e}")
                stats["skipped"] += 1

        self.tick_stats = stats
        log.info(
            f"[idle_pipeline] cycle complete: "
            f"{stats['discovered']} discovered, {stats['enriched']} enriched, "
            f"{stats['outreach_sent']} outreach, {stats['skipped']} skipped"
        )
        return {"status": "ok", **stats}

    async def run_loop(self):
        """Background pipeline loop. Runs every interval_hours."""
        log.info(f"[idle_pipeline] starting (interval={self.interval_hours}h)")
        self.running = True

        # Register as waste_detector role (reuse the role)
        await self._heartbeat()

        # Run initial cycle
        try:
            await self.run_cycle()
        except Exception as e:
            log.error(f"[idle_pipeline] initial cycle failed: {e}")

        while self.running:
            await asyncio.sleep(self.interval_hours * 3600)
            try:
                await self._heartbeat()
                await self.run_cycle()
            except Exception as e:
                log.error(f"[idle_pipeline] tick error: {e}")

    async def _persist_enriched(self, enriched: EnrichedCompound):
        """Store enriched compound in idle_asset_enriched table."""
        try:
            db = self.get_db()
            db.table("idle_asset_enriched").upsert({
                "compound_id": enriched.compound_id,
                "business_name": enriched.business_name,
                "phone": enriched.phone,
                "email": enriched.email,
                "website": enriched.website,
                "industry": enriched.industry,
                "lead_gen_score": enriched.lead_gen_score,
                "consulting_score": enriched.consulting_score,
                "marketplace_score": enriched.marketplace_score,
                "best_model": enriched.best_model,
                "enrichment_source": enriched.enrichment_source,
                "enrichment_confidence": enriched.enrichment_confidence,
                "status": "enriched",
                "meta": enriched.meta,
            }, on_conflict="compound_id").execute()
        except Exception as e:
            log.debug(f"[idle_pipeline] persist enriched failed: {e}")

    async def _heartbeat(self):
        """Register pipeline in agent_registry."""
        try:
            db = self.get_db()
            db.table("agent_registry").upsert({
                "agent_name": "idle_asset_detector",
                "role_name": "waste_detector",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": [
                    "detect_idle_assets", "enrich_compounds",
                    "multi_model_scoring", "outreach_dispatch",
                    "pipeline_orchestration", "logistics_intelligence",
                    "warehouse_waste_detection", "abandoned_building_detection",
                ],
                "task_types": [
                    "idle.pipeline", "idle.scan", "idle.enrich",
                    "idle.score", "idle.outreach", "idle.report",
                    "idle.detect_abandoned_warehouse", "idle.underutilization_check",
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
# HUB BOT RUN LOOP (compatible with hub.py asyncio pattern)
# ─────────────────────────────────────────────────────────────────────
_detector_instance: Optional[IdleAssetDetector] = None
_pipeline_instance: Optional[IdleAssetPipeline] = None


def get_detector() -> IdleAssetDetector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = IdleAssetDetector(get_db=None, scan_interval_hours=6)
    return _detector_instance


def set_detector_db(get_db_fn):
    """Wire the Supabase get_db function after instantiation."""
    detector = get_detector()
    detector.get_db = get_db_fn


def get_pipeline() -> Optional[IdleAssetPipeline]:
    global _pipeline_instance
    return _pipeline_instance


def set_pipeline(pipeline: IdleAssetPipeline):
    global _pipeline_instance
    _pipeline_instance = pipeline


async def run_loop(interval_hours: int = 6):
    """Entry point for hub.py asyncio.create_task(). Uses pipeline if available."""
    pipeline = get_pipeline()
    if pipeline:
        pipeline.interval_hours = interval_hours
        await pipeline.run_loop()
    else:
        detector = get_detector()
        detector.scan_interval_hours = interval_hours
        await detector.run_loop()


# ─────────────────────────────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────────────────────────────
def register_idle_asset_routes(
    app,
    detector: IdleAssetDetector,
    require_auth=None,
    pipeline: Optional[IdleAssetPipeline] = None,
):
    """Register Idle Asset Detector API routes on a FastAPI app."""

    from fastapi import Depends, HTTPException, Query

    @app.post("/api/v1/idle-asset/scan")
    async def idle_asset_scan(auth=Depends(require_auth) if require_auth else None):
        """Trigger a full scan cycle across all metros. Returns discovered compounds."""
        try:
            compounds = await detector.scan()
            return {
                "ok": True,
                "compounds": [
                    {
                        "compound_id": c.compound_id,
                        "name": c.name,
                        "address": c.address,
                        "city": c.city,
                        "state": c.state,
                        "metro": c.metro,
                        "lat": c.lat,
                        "lon": c.lon,
                        "compound_type": c.compound_type,
                        "area_sq_m": c.area_sq_meters,
                        "trailer_capacity_est": c.trailer_capacity_est,
                        "idle_score": c.idle_score,
                    }
                    for c in compounds
                ],
                "count": len(compounds),
                "snapshot": detector.snapshot(),
            }
        except Exception as e:
            raise HTTPException(500, f"Scan failed: {str(e)[:200]}")

    @app.get("/api/v1/idle-asset/compounds")
    async def idle_asset_compounds(
        metro: str = Query(""),
        min_score: float = Query(0.0),
        limit: int = Query(50),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List discovered compounds with optional metro/score filters."""
        if not detector.get_db:
            raise HTTPException(500, "No DB connection")
        try:
            db = detector.get_db()
            q = db.table("logistics_compounds").select("*")
            if metro:
                q = q.eq("metro", metro)
            if min_score > 0:
                q = q.gte("idle_score", min_score)
            r = q.order("idle_score", desc=True).limit(min(limit, 200)).execute()
            return {
                "compounds": r.data or [],
                "count": len(r.data or []),
            }
        except Exception as e:
            raise HTTPException(500, str(e)[:200])

    @app.get("/api/v1/idle-asset/stats")
    async def idle_asset_stats(auth=Depends(require_auth) if require_auth else None):
        """Aggregate stats: compounds per metro, average idle score, top opportunities."""
        if not detector.get_db:
            return {"compounds_total": 0, "by_metro": {}, "top_opportunities": []}
        try:
            db = detector.get_db()
            all_r = db.table("logistics_compounds").select("metro,idle_score,name,compound_type").execute()
            rows = all_r.data or []

            by_metro = {}
            for r in rows:
                m = r.get("metro", "Unknown")
                if m not in by_metro:
                    by_metro[m] = {"count": 0, "total_score": 0.0, "high_waste": 0}
                by_metro[m]["count"] += 1
                by_metro[m]["total_score"] += float(r.get("idle_score", 0) or 0)
                if float(r.get("idle_score", 0) or 0) >= 0.7:
                    by_metro[m]["high_waste"] += 1

            for m in by_metro:
                c = by_metro[m]["count"]
                by_metro[m]["avg_score"] = round(by_metro[m]["total_score"] / c, 3) if c else 0
                del by_metro[m]["total_score"]

            # Top 10 highest-score compounds
            sorted_rows = sorted(rows, key=lambda r: float(r.get("idle_score", 0) or 0), reverse=True)
            top = [
                {
                    "name": r.get("name"),
                    "metro": r.get("metro"),
                    "type": r.get("compound_type"),
                    "idle_score": r.get("idle_score"),
                }
                for r in sorted_rows[:10]
            ]

            return {
                "compounds_total": len(rows),
                "by_metro": by_metro,
                "top_opportunities": top,
                "snapshot": detector.snapshot(),
            }
        except Exception as e:
            return {"error": str(e)[:200]}

    @app.get("/api/v1/idle-asset/snapshot")
    async def idle_asset_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Quick detector status snapshot."""
        return detector.snapshot()

    # ── Pipeline Routes ────────────────────────────────────────────
    if pipeline:
        @app.post("/api/v1/idle-asset/pipeline/run")
        async def idle_pipeline_run(auth=Depends(require_auth) if require_auth else None):
            """Trigger a full pipeline cycle: discover → enrich → score → outreach."""
            try:
                result = await pipeline.run_cycle()
                return {"ok": True, "result": result}
            except Exception as e:
                raise HTTPException(500, f"Pipeline run failed: {str(e)[:200]}")

        @app.get("/api/v1/idle-asset/pipeline/stats")
        async def idle_pipeline_stats(auth=Depends(require_auth) if require_auth else None):
            """Full pipeline snapshot: detector + enricher + outreach stats."""
            db_stats = {"enriched_total": 0, "outreach_total": 0}
            try:
                db = detector.get_db()
                if db:
                    r = db.table("idle_asset_enriched").select("compound_id", count="exact").execute()
                    db_stats["enriched_total"] = r.count if hasattr(r, "count") else len(r.data or [])
                    r2 = db.table("idle_asset_outreach").select("compound_id", count="exact").execute()
                    db_stats["outreach_total"] = r2.count if hasattr(r2, "count") else len(r2.data or [])
            except Exception:
                pass
            return {
                "pipeline": pipeline.snapshot(),
                "db": db_stats,
            }

        @app.get("/api/v1/idle-asset/pipeline/leads")
        async def idle_pipeline_leads(
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
                q = db.table("idle_asset_enriched").select("*")
                if best_model:
                    q = q.eq("best_model", best_model)
                if min_score > 0:
                    q = q.gte(
                        f"{best_model or 'lead_gen'}_score" if best_model else "lead_gen_score",
                        min_score,
                    )
                r = q.order("lead_gen_score", desc=True).limit(min(limit, 200)).execute()
                return {"leads": r.data or [], "count": len(r.data or [])}
            except Exception as e:
                raise HTTPException(500, str(e)[:200])

        @app.get("/api/v1/idle-asset/pipeline/outreach")
        async def idle_pipeline_outreach(
            status: str = Query(""),
            limit: int = Query(50),
            auth=Depends(require_auth) if require_auth else None,
        ):
            """List outreach records with opt-in status filter."""
            if not detector.get_db:
                raise HTTPException(500, "No DB connection")
            try:
                db = detector.get_db()
                q = db.table("idle_asset_outreach").select("*")
                if status:
                    q = q.eq("status", status)
                r = q.order("enrolled_at", desc=True).limit(min(limit, 200)).execute()
                return {"outreach": r.data or [], "count": len(r.data or [])}
            except Exception as e:
                raise HTTPException(500, str(e)[:200])

    log.info("[idle_asset] routes registered: /api/v1/idle-asset/{scan,compounds,stats,snapshot"
             + (",pipeline/run,pipeline/stats,pipeline/leads,pipeline/outreach}" if pipeline else "}"))
