"""
EMPIRE V49 - PROSPECTOR (UPGRADED)
==================================
Finds contractors (lead BUYERS, not homeowners) in storm-active metros.
Uses Google Places text search (via places_helper) and ranks by buy-signal.
Supports multiple niches, uses shared METROS config from config/metros.py.

This finds businesses TO SELL TO (contractors who buy leads), distinct from
radar_targets (property-owner leads).

Writes ranked prospects to the 'prospects' table for human outreach.
Module-level IO eliminated — Supabase client is lazy-init per call.
"""
import os
import sys
import asyncio
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv("/root/.env")

sys.path.insert(0, "/root/empire-v49")
from config.metros import METROS, metro_coords
from bots.places_helper import places_search as _places_search

log = logging.getLogger("empire.prospector")


# Supported prospecting niches (mirrors empire_contractors.TRADE_ENUM)
NICHES: List[str] = [
    "roofing",
    "general contractor",
    "restoration",
    "water mitigation",
    "electrical",
    "plumbing",
    "hvac",
    "solar",
    "paving",
    "fencing",
]


def _sb() -> Any:
    """Lazy Supabase client — no module-level IO."""
    from supabase import create_client
    url: str = os.getenv("SUPABASE_URL", "")
    key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    return create_client(url, key)


def buy_signal(place: Dict[str, Any]) -> int:
    """Score a contractor by likelihood they buy leads. 0-100.

    Signals:
      - Review count (size proxy): 0-40 pts
      - Has website: 25 pts
      - Has phone: 20 pts
      - Rating >= 4.0  (reputation-conscious): 15 pts
      - business_status == OPERATIONAL: 5 pts bonus
    """
    score: int = 0
    reviews: int = int(place.get("review_count") or place.get("user_ratings_total") or 0)
    if reviews >= 100:
        score += 40
    elif reviews >= 50:
        score += 30
    elif reviews >= 20:
        score += 20
    elif reviews >= 5:
        score += 10

    if place.get("website"):
        score += 25
    if place.get("phone") or place.get("formatted_phone_number"):
        score += 20

    rating: float = float(place.get("rating") or 0)
    if rating >= 4.0:
        score += 15

    # Bonus for verified operational businesses
    status: str = str(place.get("business_status", "") or "")
    if status.upper() == "OPERATIONAL":
        score += 5

    return min(score, 100)


async def find_prospects(
    metro: str = "Wichita",
    niche: str = "roofing",
) -> List[Dict[str, Any]]:
    """Find contractor prospects in a metro for a given niche.

    Uses Google Places text search, scores each result with buy_signal(),
    and returns a sorted list (highest score first).
    """
    lat, lon = metro_coords(metro)
    if lat is None or lon is None:
        print(f"[PROSPECT] Unknown metro {metro}; options: {list(METROS.keys())}")
        return []

    print(f"[PROSPECT] Searching {niche} contractors in {metro}...")
    # Convert niche like "general contractor" to safe search query
    query_niche: str = niche.replace("_", " ")
    leads: List[Dict[str, Any]] = await _places_search(
        f"{query_niche} contractors in {metro}", lat, lon
    )
    print(f"[PROSPECT] Places returned {len(leads)} businesses")

    prospects: List[Dict[str, Any]] = []
    for p in leads:
        name: Optional[str] = p.get("name") or p.get("warehouse_name")
        if not name:
            continue
        score: int = buy_signal(p)
        prospects.append({
            "business_name": name,
            "niche": niche,
            "metro": metro,
            "phone": p.get("phone") or p.get("formatted_phone_number"),
            "website": p.get("website") or p.get("url"),
            "address": p.get("address") or p.get("formatted_address"),
            "rating": p.get("rating"),
            "review_count": p.get("review_count") or p.get("user_ratings_total"),
            "buy_signal_score": score,
            "business_status": p.get("business_status", ""),
            "status": "new",
        })

    prospects.sort(key=lambda x: int(x["buy_signal_score"]), reverse=True)
    return prospects


async def save_prospects(prospects: List[Dict[str, Any]]) -> int:
    """Insert prospects into the DB, dedup by business_name + metro.

    Returns the count of new rows inserted.
    """
    sb = _sb()
    saved: int = 0
    for p in prospects:
        try:
            existing = (sb.table("prospects").select("id")
                        .eq("business_name", p["business_name"])
                        .eq("metro", p["metro"]).execute())
            if existing.data:
                continue
            sb.table("prospects").insert(p).execute()
            saved += 1
        except Exception as e:
            log.error(f"[PROSPECT] save error: {e}")
    return saved


async def run(
    metro: str = "Wichita",
    niche: str = "roofing",
) -> List[Dict[str, Any]]:
    """Run the full prospector pipeline: find + save + print top 10.

    Returns the full list of prospects (found, not just saved).
    """
    prospects: List[Dict[str, Any]] = await find_prospects(metro, niche)
    saved: int = await save_prospects(prospects)
    print(f"[PROSPECT] {len(prospects)} found, {saved} new saved")
    print(f"\n=== TOP 10 PROSPECTS ({metro} {niche}) ===")
    for i, p in enumerate(prospects[:10], 1):
        print(f"{i}. {p['business_name']} | score {p['buy_signal_score']} | "
              f"{p['review_count'] or 0} reviews | {'web' if p['website'] else 'no-web'} | "
              f"{p['phone'] or 'no-phone'} | {p.get('business_status', '?')}")
    return prospects


async def run_multi(
    metros: Optional[List[str]] = None,
    niches: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run prospector across multiple metros and niches.

    Args:
        metros: List of metro names (default: all from METROS config)
        niches: List of niches (default: all from NICHES)

    Returns:
        Summary dict with totals per metro and per niche.
    """
    if metros is None:
        metros = list(METROS.keys())
    if niches is None:
        niches = NICHES

    results: Dict[str, Any] = {
        "total_found": 0, "total_saved": 0, "by_metro": {}, "by_niche": {}
    }
    for metro in metros:
        metro_found: int = 0
        for niche in niches:
            prospects: List[Dict[str, Any]] = await find_prospects(metro, niche)
            saved: int = await save_prospects(prospects)
            results["total_found"] += len(prospects)
            results["total_saved"] += saved
            metro_found += len(prospects)
            results["by_niche"][niche] = (
                results["by_niche"].get(niche, 0) + len(prospects)
            )
            await asyncio.sleep(0.5)  # Rate limit between niche queries
        results["by_metro"][metro] = metro_found
        print(f"[PROSPECT] {metro}: {metro_found} prospects found across {len(niches)} niches")
    results["metros_scanned"] = len(metros)
    results["niches_scanned"] = len(niches)
    return results


if __name__ == "__main__":
    metro: str = sys.argv[1] if len(sys.argv) > 1 else "Wichita"
    niche: str = sys.argv[2] if len(sys.argv) > 2 else "roofing"
    multi: bool = "--multi" in sys.argv
    if multi:
        results = asyncio.run(run_multi())
        print(f"\n=== MULTI SCAN COMPLETE ===")
        print(f"Total found: {results['total_found']}, saved: {results['total_saved']}")
    else:
        asyncio.run(run(metro, niche))
