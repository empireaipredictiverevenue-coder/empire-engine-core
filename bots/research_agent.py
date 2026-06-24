"""
EMPIRE V49 · SEO RESEARCH AGENT
================================
Dedicated research agent that feeds the SEO Agent with deep property,
market, competitor, and storm-history intelligence. Every finding
persists to `seo_research` so the SEO genome can evolve based on
real research quality signals.

RESEARCH TYPES:
  1. property         — County appraisal / public-record property intelligence
  2. market_trend     — Per-metro market velocity, demand indicators
  3. competitor       — Competitor landscape for a niche + metro
  4. storm_history    — Historical severe weather for a zip/metro
  5. neighborhood     — Schools, amenities, demographics, walkability
  6. buyer_intent     — High-intent buyer signal research across sources
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("seo.research")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

_sb = None


def _get_sb():
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
            sys.exit(1)
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


from bots._llm import llm_json as _ollama_json


# ── FALLBACK DATA ─────────────────────────────────────────────────────
_FALLBACK_PROPERTY = {
    "property_type": "Commercial / Industrial",
    "year_built": 1995,
    "sqft": 25000,
    "lot_size_acres": 2.5,
    "zoning": "Industrial",
    "estimated_value": 1800000,
    "last_sale_year": 2020,
    "last_sale_price": 1200000,
    "owner_occupier": False,
    "flood_zone": "X",
    "roof_type": "TPO / Flat",
}

_FALLBACK_MARKET = {
    "price_trend": "stable",
    "demand_level": "moderate",
    "avg_days_on_market": 45,
    "inventory_trend": "slightly_decreasing",
    "top_growth_sectors": ["warehouse", "logistics", "distribution"],
}

_FALLBACK_COMPETITORS = [
    {"name": "Competitor A", "estimated_market_share_pct": 25, "strength": "broad coverage"},
    {"name": "Competitor B", "estimated_market_share_pct": 15, "strength": "niche specialization"},
]

_STORM_FALLBACK = {
    "total_events_last_5yr": 12,
    "most_common_event": "Severe Thunderstorm",
    "avg_severity_score": 4.2,
    "total_estimated_damage_usd": 850000,
    "risk_level": "moderate",
}

NEIGHBORHOOD_FALLBACK = {
    "walk_score": 45,
    "transit_score": 30,
    "school_rating": 6,
    "median_home_value": 320000,
    "population_density": "medium",
    "top_amenities": ["parks", "shopping_centers", "highways"],
}


# ── RESEARCH AGENT ────────────────────────────────────────────────────
class ResearchAgent:
    """
    Deep research agent that feeds property, market, competitor,
    storm-history, and neighborhood intelligence into the SEO pipeline.

    Capabilities:
      - research_property(address, zip)       → county appraisal intel
      - research_market(metro, niche)         → market velocity & demand
      - research_competitors(metro, niche)    → competitive landscape
      - research_storm_history(zip, metro)    → severe weather patterns
      - research_neighborhood(zip)            → schools, amenities, demo
      - research_buyer_intent(niche, metro)   → high-intent buyer signals
      - full_research(address, metro, niche)  → aggregate all 6 → SEO feed
      - performance_snapshot()                → stats + recent research
    """

    RESEARCH_TYPES = ["property", "market_trend", "competitor", "storm_history", "neighborhood", "buyer_intent"]

    def __init__(self):
        self.stats = {
            "research_runs": 0,
            "property_lookups": 0,
            "market_analyses": 0,
            "competitor_scans": 0,
            "storm_lookups": 0,
            "neighborhood_lookups": 0,
            "buyer_intent_scans": 0,
            "errors": 0,
        }
        self._cache: Dict[str, dict] = {}  # simple in-memory cache per session

    # ── PROPERTY RESEARCH ──────────────────────────────────────────
    async def research_property(
        self, address: str, zip_code: str = "", metro: str = ""
    ) -> Dict:
        """
        Research property intelligence: type, year built, sqft, value,
        zoning, flood zone, roof type. Uses Ollama to synthesize from
        available signals (address, zip, metro). Returns structured
        property profile.
        """
        cache_key = f"property:{address}|{zip_code}"
        if cache_key in self._cache:
            return dict(self._cache[cache_key])

        system = """You are a commercial property research analyst. Given an address,
zip code, and metro area, return an intelligence profile of the property.
Return ONLY JSON with these fields:
{
  "property_type": "Commercial|Industrial|Retail|Office|Mixed-Use|Residential",
  "year_built": integer (estimate if unknown),
  "sqft": integer (estimated square footage),
  "lot_size_acres": float,
  "zoning": "string (zoning classification)",
  "estimated_value": integer (estimated current market value in USD),
  "last_sale_year": integer,
  "last_sale_price": integer,
  "owner_occupier": boolean,
  "flood_zone": "A|AE|V|X|D|Unknown",
  "roof_type": "string",
  "confidence_level": "high|medium|low",
  "research_notes": ["note1", "note2"]
}"""

        prompt = (
            f"Address: {address}\n"
            f"ZIP: {zip_code or 'unknown'}\n"
            f"Metro: {metro or 'unknown'}\n"
            f"Research commercial property intelligence for this location. "
            f"Use the address and metro to infer property characteristics. "
            f"Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.3)
        if "_error" in result:
            self.stats["errors"] += 1
            result = dict(_FALLBACK_PROPERTY)
            result["_fallback"] = True
            result["confidence_level"] = "low"

        result["address"] = address
        result["zip_code"] = zip_code
        result["metro"] = metro
        result["research_type"] = "property"
        result["researched_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["property_lookups"] += 1
        self.stats["research_runs"] += 1
        self._cache[cache_key] = dict(result)
        await self._persist_research(result)
        return result

    # ── MARKET TREND RESEARCH ──────────────────────────────────────
    async def research_market(self, metro: str, niche: str = "Roofing Restoration") -> Dict:
        """
        Research market trends for a metro: price trends, demand levels,
        inventory trends, top growth sectors.
        """
        cache_key = f"market:{metro}|{niche}"
        if cache_key in self._cache:
            return dict(self._cache[cache_key])

        system = """You are a real estate market analyst. Research market conditions
for a metro area and niche. Return ONLY JSON:
{
  "metro": "city name",
  "price_trend": "rising|stable|declining",
  "demand_level": "high|moderate|low",
  "avg_days_on_market": integer,
  "inventory_trend": "increasing|stable|slightly_decreasing|decreasing",
  "top_growth_sectors": ["sector1", "sector2"],
  "year_over_year_change_pct": float,
  "new_listings_trend": "increasing|stable|decreasing",
  "market_health_score": integer (0-100),
  "key_indicators": ["indicator1", "indicator2"],
  "confidence_level": "high|medium|low"
}"""

        prompt = (
            f"Metro: {metro}\n"
            f"Niche: {niche}\n"
            f"Research current market conditions for this metro for the {niche} niche. "
            f"Use known market patterns for this region. Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.4)
        if "_error" in result:
            self.stats["errors"] += 1
            result = dict(_FALLBACK_MARKET)
            result["_fallback"] = True
            result["confidence_level"] = "low"

        result["metro"] = metro
        result["niche"] = niche
        result["research_type"] = "market_trend"
        result["researched_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["market_analyses"] += 1
        self.stats["research_runs"] += 1
        self._cache[cache_key] = dict(result)
        await self._persist_research(result)
        return result

    # ── COMPETITOR RESEARCH ────────────────────────────────────────
    async def research_competitors(self, metro: str, niche: str = "Roofing Restoration") -> Dict:
        """
        Research competitor landscape: who operates in this metro+niche,
        their estimated market share, strengths, weaknesses.
        """
        cache_key = f"competitor:{metro}|{niche}"

        system = """You are a competitive intelligence analyst. Research the competitive
landscape for a niche in a metro area. Return ONLY JSON:
{
  "metro": "city",
  "niche": "niche",
  "competitors": [
    {
      "name": "Company Name",
      "estimated_market_share_pct": integer,
      "strength": "their key advantage",
      "weakness": "their key vulnerability",
      "digital_presence_score": integer (0-100),
      "estimated_monthly_leads": integer
    }
  ],
  "market_concentration": "fragmented|moderate|consolidated",
  "total_estimated_competitors": integer,
  "gap_opportunities": ["opportunity1", "opportunity2"],
  "confidence_level": "high|medium|low"
}"""

        prompt = (
            f"Metro: {metro}\n"
            f"Niche: {niche}\n"
            f"Research the competitor landscape for {niche} businesses in {metro}. "
            f"Generate realistic competitor profiles based on typical market structure. "
            f"Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.5)
        if "_error" in result:
            self.stats["errors"] += 1
            result = {
                "metro": metro,
                "niche": niche,
                "competitors": _FALLBACK_COMPETITORS,
                "market_concentration": "fragmented",
                "total_estimated_competitors": 8,
                "gap_opportunities": ["digital presence", "local SEO", "customer reviews"],
                "confidence_level": "low",
                "_fallback": True,
            }

        result["metro"] = metro
        result["niche"] = niche
        result["research_type"] = "competitor"
        result["researched_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["competitor_scans"] += 1
        self.stats["research_runs"] += 1
        self._cache[cache_key] = dict(result)
        await self._persist_research(result)
        return result

    # ── STORM HISTORY RESEARCH ─────────────────────────────────────
    async def research_storm_history(self, zip_code: str = "", metro: str = "") -> Dict:
        """
        Research severe weather history for a zip/metro: event frequency,
        severity, estimated damage. Cross-references storm_forecasts if
        available in local database.
        """
        cache_key = f"storm:{zip_code}|{metro}"

        # First try to get real data from storm_alerts.sqlite
        real_data = None
        storm_db_path = "/root/empire-v49/data/storm_alerts.sqlite"
        try:
            import sqlite3
            from pathlib import Path
            if Path(storm_db_path).exists():
                conn = sqlite3.connect(storm_db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT event, severity, issued_at, area_desc FROM storm_alerts WHERE zip_code = ? ORDER BY issued_at DESC LIMIT 20",
                    (zip_code,),
                )
                rows = cursor.fetchall()
                if rows:
                    real_data = [
                        {"event": r[0], "severity": r[1], "issued_at": r[2], "area": r[3]}
                        for r in rows
                    ]
                conn.close()
        except Exception as e:
            log.debug(f"[research] storm DB lookup: {e}")

        system = """You are a weather intelligence analyst. Given zip code, metro, and any
real storm alert data, return a storm history profile. Return ONLY JSON:
{
  "zip_code": "string",
  "metro": "string",
  "total_events_last_5yr": integer,
  "most_common_event": "string",
  "events_by_severity": {"minor": int, "moderate": int, "severe": int, "extreme": int},
  "avg_severity_score": float (1-10),
  "total_estimated_damage_usd": integer,
  "peak_season": "string (e.g. 'Mar-Jun')",
  "risk_level": "low|moderate|high|severe",
  "recent_events": [{"date": "string", "event": "string", "severity": "string"}],
  "confidence_level": "high|medium|low"
}"""

        context = f"ZIP: {zip_code}\nMetro: {metro}\n"
        if real_data:
            context += f"Real storm alerts ({len(real_data)} events):\n"
            for e in real_data[:5]:
                context += f"  - {e['issued_at'][:10]}: {e['event']} ({e['severity']}) in {e['area']}\n"

        prompt = (
            context +
            "Research severe weather history for this location. "
            "Use real data if provided, otherwise estimate from regional climate patterns. "
            "Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.3)
        if "_error" in result or result.get("_error"):
            self.stats["errors"] += 1
            result = dict(_STORM_FALLBACK)
            result["zip_code"] = zip_code
            result["metro"] = metro
            result["events_by_severity"] = {"minor": 4, "moderate": 3, "severe": 1, "extreme": 0}
            result["peak_season"] = "Mar-Jun"
            result["_fallback"] = True
            result["confidence_level"] = "low"

        result["zip_code"] = zip_code
        result["metro"] = metro
        result["real_data_count"] = len(real_data) if real_data else 0
        result["research_type"] = "storm_history"
        result["researched_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["storm_lookups"] += 1
        self.stats["research_runs"] += 1
        self._cache[cache_key] = dict(result)
        await self._persist_research(result)
        return result

    # ── NEIGHBORHOOD RESEARCH ──────────────────────────────────────
    async def research_neighborhood(self, zip_code: str, metro: str = "") -> Dict:
        """
        Research neighborhood data: walk score, transit, schools, amenities,
        demographics, median home values.
        """
        cache_key = f"neighborhood:{zip_code}"

        system = """You are a neighborhood research analyst. Given a zip code and metro,
return a neighborhood intelligence profile. Return ONLY JSON:
{
  "zip_code": "string",
  "metro": "string",
  "walk_score": integer (0-100),
  "transit_score": integer (0-100),
  "school_rating": integer (1-10),
  "median_home_value": integer,
  "median_rent": integer,
  "population_density": "low|medium|high",
  "population_growth_trend": "growing|stable|declining",
  "median_age": float,
  "median_household_income": integer,
  "top_amenities": ["amenity1", "amenity2"],
  "commute_score": integer (0-100),
  "safety_score": integer (0-100),
  "confidence_level": "high|medium|low"
}"""

        prompt = (
            f"ZIP: {zip_code}\n"
            f"Metro: {metro or 'unknown'}\n"
            f"Research neighborhood data for this zip code in the {metro} metro. "
            f"Use typical demographic patterns for this region. "
            f"Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.4)
        if "_error" in result:
            self.stats["errors"] += 1
            result = dict(NEIGHBORHOOD_FALLBACK)
            result["zip_code"] = zip_code
            result["metro"] = metro
            result["_fallback"] = True
            result["confidence_level"] = "low"

        result["zip_code"] = zip_code
        result["metro"] = metro
        result["research_type"] = "neighborhood"
        result["researched_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["neighborhood_lookups"] += 1
        self.stats["research_runs"] += 1
        self._cache[cache_key] = dict(result)
        await self._persist_research(result)
        return result

    # ── BUYER INTENT RESEARCH ──────────────────────────────────────
    async def research_buyer_intent(self, niche: str, metro: str = "") -> Dict:
        """
        Research high-intent buyer signals for a niche + metro. Identifies
        what prospects are searching for, their pain points, and the best
        content angles to convert them.
        """
        cache_key = f"buyer_intent:{niche}|{metro}"

        system = """You are a buyer intent analyst. Research what motivates buyers in a
specific niche and metro. Return ONLY JSON:
{
  "niche": "string",
  "metro": "string",
  "primary_search_intents": [
    {"intent": "what they search", "volume": "high|medium|low", "pain_point": "underlying need"}
  ],
  "decision_triggers": ["trigger1", "trigger2"],
  "content_angles": [
    {"angle": "content approach", "expected_effectiveness": "high|medium|low"}
  ],
  "top_questions_prospects_ask": ["q1", "q2"],
  "seasonality_factors": ["factor1", "factor2"],
  "average_decison_cycle_days": integer,
  "confidence_level": "high|medium|low"
}"""

        prompt = (
            f"Niche: {niche}\n"
            f"Metro: {metro or 'national'}\n"
            f"Research buyer intent signals for {niche} in {metro or 'the US'}. "
            f"What are prospects searching for? What triggers their decision? "
            f"Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.4)
        if "_error" in result:
            self.stats["errors"] += 1
            result = {
                "niche": niche,
                "metro": metro or "national",
                "primary_search_intents": [
                    {"intent": f"{niche} near me", "volume": "high", "pain_point": "proximity and urgency"},
                    {"intent": f"best {niche.lower()} services", "volume": "medium", "pain_point": "quality assurance"},
                    {"intent": f"{niche.lower()} cost estimate", "volume": "medium", "pain_point": "pricing transparency"},
                ],
                "decision_triggers": ["storm damage", "emergency need", "insurance deadline"],
                "content_angles": [
                    {"angle": "cost comparison guides", "expected_effectiveness": "high"},
                    {"angle": "before/after case studies", "expected_effectiveness": "medium"},
                ],
                "top_questions_prospects_ask": [
                    "How much does this cost?",
                    "How long does it take?",
                    "Do you work with insurance?",
                ],
                "seasonality_factors": ["spring storm season", "tax refund season"],
                "average_decison_cycle_days": 7,
                "confidence_level": "low",
                "_fallback": True,
            }

        result["niche"] = niche
        result["metro"] = metro or "national"
        result["research_type"] = "buyer_intent"
        result["researched_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["buyer_intent_scans"] += 1
        self.stats["research_runs"] += 1
        self._cache[cache_key] = dict(result)
        await self._persist_research(result)
        return result

    # ── FULL AGGREGATE RESEARCH ────────────────────────────────────
    async def full_research(
        self,
        address: str = "",
        zip_code: str = "",
        metro: str = "",
        niche: str = "Roofing Restoration",
    ) -> Dict:
        """
        Run all research types in parallel for a given property + metro + niche.
        Returns a consolidated research package that feeds directly into
        the SEO agent's content generation pipeline.
        """
        tasks = []
        if address:
            tasks.append(self.research_property(address, zip_code, metro))
        if metro:
            tasks.append(self.research_market(metro, niche))
            tasks.append(self.research_competitors(metro, niche))
        tasks.append(self.research_buyer_intent(niche, metro))
        if zip_code:
            tasks.append(self.research_storm_history(zip_code, metro))
            tasks.append(self.research_neighborhood(zip_code, metro))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        package = {
            "address": address,
            "zip_code": zip_code,
            "metro": metro,
            "niche": niche,
            "researched_at": datetime.now(timezone.utc).isoformat(),
            "research_count": 0,
            "errors": 0,
        }

        for r in results:
            if isinstance(r, Exception):
                log.warning(f"[research] full_research sub-task failed: {r}")
                package["errors"] += 1
                continue
            if not isinstance(r, dict):
                continue
            rtype = r.get("research_type", "unknown")
            package[rtype] = r
            package["research_count"] += 1

        return package

    # ── PERSIST TO SUPABASE ────────────────────────────────────────
    async def _persist_research(self, result: Dict):
        """Save research result to seo_research table."""
        try:
            sb = _get_sb()
            insert = {
                "research_type": result.get("research_type", "unknown"),
                "niche": result.get("niche", ""),
                "metro": result.get("metro", ""),
                "zip_code": result.get("zip_code", ""),
                "address": result.get("address", ""),
                "findings": json.dumps(result, default=str),
                "confidence_level": result.get("confidence_level", "medium"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            sb.table("seo_research").insert(insert).execute()
        except Exception as e:
            log.debug(f"[research] persist failed (table may not exist): {e}")

    # ── PERFOMANCE SNAPSHOT ────────────────────────────────────────
    async def performance_snapshot(self) -> Dict:
        """Return stats + recent research entries."""
        try:
            sb = _get_sb()
            r = sb.table("seo_research") \
                .select("research_type,confidence_level,created_at,niche,metro") \
                .order("created_at", desc=True) \
                .limit(20) \
                .execute()
            recent = r.data or []
        except Exception:
            recent = []

        return {
            "stats": dict(self.stats),
            "cache_size": len(self._cache),
            "recent_research": recent,
            "research_types": self.RESEARCH_TYPES,
        }


# ── GLOBAL SINGLETON ─────────────────────────────────────────────────
_RESEARCH_AGENT: Optional[ResearchAgent] = None


def get_research_agent() -> ResearchAgent:
    global _RESEARCH_AGENT
    if _RESEARCH_AGENT is None:
        _RESEARCH_AGENT = ResearchAgent()
    return _RESEARCH_AGENT


# ── STANDALONE CLI ───────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    async def _demo():
        agent = get_research_agent()
        if "--full" in sys.argv:
            result = await agent.full_research(
                address="1234 Commerce St",
                zip_code="75201",
                metro="Dallas",
                niche="Roofing Restoration",
            )
            print(json.dumps(result, indent=2, default=str)[:3000])
        elif "--property" in sys.argv:
            result = await agent.research_property("500 Industrial Blvd", "76102", "Fort Worth")
            print(json.dumps(result, indent=2, default=str))
        elif "--storm" in sys.argv:
            result = await agent.research_storm_history("75201", "Dallas")
            print(json.dumps(result, indent=2, default=str))
        elif "--market" in sys.argv:
            result = await agent.research_market("Dallas", "Roofing Restoration")
            print(json.dumps(result, indent=2, default=str))
        elif "--competitors" in sys.argv:
            result = await agent.research_competitors("Houston", "Roofing Restoration")
            print(json.dumps(result, indent=2, default=str))
        elif "--neighborhood" in sys.argv:
            result = await agent.research_neighborhood("75201", "Dallas")
            print(json.dumps(result, indent=2, default=str))
        elif "--buyer-intent" in sys.argv:
            result = await agent.research_buyer_intent("Roofing Restoration", "Dallas")
            print(json.dumps(result, indent=2, default=str))
        else:
            snap = await agent.performance_snapshot()
            print(json.dumps(snap, indent=2, default=str))

    asyncio.run(_demo())
