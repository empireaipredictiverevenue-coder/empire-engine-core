"""
EMPIRE V49 - PROSPECTOR
=======================
Finds roofing CONTRACTORS (lead BUYERS, not homeowners) in a storm-active metro.
Uses the existing enricher (Google Places) and ranks by buy-signal:
  review_count (size proxy) + has_website + has_phone.
Writes ranked prospects to the 'prospects' table for human outreach.
This finds businesses to SELL TO, distinct from radar_targets (homeowner leads).
"""
import os, asyncio, logging
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/root/.env")
from supabase import create_client
import sys; sys.path.insert(0, "/root/empire-v49")
import enricher_sniper
from bots.places_helper import places_search as _places_roofing

log = logging.getLogger("empire.prospector")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# Metro centroids for the Places search
METROS = {
    "Wichita": (37.6872, -97.3301),
    "Oklahoma City": (35.4676, -97.5164),
    "Kansas City": (39.0997, -94.5786),
    "Dallas-Fort Worth": (32.7767, -96.7970),
    "Tulsa": (36.1540, -95.9928),
}

def buy_signal(place):
    """Score a contractor by likelihood they buy leads. 0-100."""
    score = 0
    reviews = place.get("review_count") or place.get("user_ratings_total") or 0
    # More reviews = bigger established operation = more likely to buy leads
    if reviews >= 100: score += 40
    elif reviews >= 50: score += 30
    elif reviews >= 20: score += 20
    elif reviews >= 5: score += 10
    if place.get("website"): score += 25
    if place.get("phone") or place.get("formatted_phone_number"): score += 20
    rating = place.get("rating") or 0
    if rating >= 4.0: score += 15  # established, takes reputation seriously
    return min(score, 100)

async def find_prospects(metro="Wichita", niche="roofing"):
    if metro not in METROS:
        print(f"[PROSPECT] Unknown metro {metro}; options: {list(METROS)}")
        return []
    lat, lon = METROS[metro]
    print(f"[PROSPECT] Searching {niche} contractors in {metro}...")

    leads = await _places_roofing(f"{niche} contractors in {metro}", lat, lon)
    print(f"[PROSPECT] Places returned {len(leads)} businesses")

    prospects = []
    for p in leads:
        name = p.get("name") or p.get("warehouse_name")
        if not name:
            continue
        score = buy_signal(p)
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
            "status": "new",
        })

    prospects.sort(key=lambda x: x["buy_signal_score"], reverse=True)
    return prospects

async def save_prospects(prospects):
    saved = 0
    for p in prospects:
        try:
            # dedupe by business_name + metro
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

async def run(metro="Wichita", niche="roofing"):
    prospects = await find_prospects(metro, niche)
    saved = await save_prospects(prospects)
    print(f"[PROSPECT] {len(prospects)} found, {saved} new saved")
    print(f"\n=== TOP 10 PROSPECTS ({metro} {niche}) ===")
    for i, p in enumerate(prospects[:10], 1):
        print(f"{i}. {p['business_name']} | score {p['buy_signal_score']} | "
              f"{p['review_count'] or 0} reviews | {'web' if p['website'] else 'no-web'} | {p['phone'] or 'no-phone'}")
    return prospects

if __name__ == "__main__":
    import sys
    metro = sys.argv[1] if len(sys.argv) > 1 else "Wichita"
    asyncio.run(run(metro))
