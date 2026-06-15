"""
EMPIRE V49 · B2B LEAD SCRAPER
==============================
Dedicated lead discovery agent for the 3 Business Services lanes:
  - Lane 29: Managed IT         (sub_niche="Managed IT")
  - Lane 30: Merchant Services  (sub_niche="Merchant Services")
  - Lane 31: HR & Staffing      (sub_niche="HR & Staffing")

Uses Google Places API text search to find B2B companies in target
metros, scrapes websites for contact info, scores by buy signal,
and inserts qualified leads into radar_targets with the correct
niche/sub_niche metadata so the lead-gen pipeline (scanner →
enricher → converter) picks them up downstream.

Designed to run as a cron job or background daemon (every 6-12h).

Requires:
  - SUPABASE_URL + SUPABASE_SERVICE_KEY in env
  - GOOGLE_MAPS_API_KEY in env (free tier: 1000 calls/month)
"""

import os
import sys
import json
import re
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO.parent / ".env")

import httpx
from supabase import create_client

log = logging.getLogger("empire.b2b_lead_scraper")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)

# ── CONFIG ─────────────────────────────────────────────────────────────

_DEFAULT_CONFIG = {
    "enabled": True,
    "dry_run": True,
    "max_per_run": 100,
    "min_score_threshold": 30,
}

# Google Places field mask for B2B searches
_GOOGLE_FIELDS = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.nationalPhoneNumber,places.websiteUri,places.rating,"
    "places.userRatingCount,places.businessStatus,places.types"
)

# Each B2B sub-niche has specific search queries optimized for Google Places
B2B_NICHES = {
    "Managed IT": {
        "queries": [
            "managed IT services",
            "IT support company",
            "MSP managed service provider",
            "IT consulting firm",
            "cybersecurity company",
            "cloud services provider",
        ],
        "website_keywords": ["managed it", "it services", "it support", "msp", "technology solutions"],
    },
    "Merchant Services": {
        "queries": [
            "merchant services",
            "credit card processing",
            "payment processing company",
            "payment gateway",
            "point of sale provider",
        ],
        "website_keywords": ["merchant services", "payment processing", "credit card processing", "pos"],
    },
    "HR & Staffing": {
        "queries": [
            "staffing agency",
            "recruitment agency",
            "HR consulting",
            "talent acquisition",
            "employment agency",
            "human resources outsourcing",
            "temp agency",
            "temporary staffing",
            "executive search firm",
            "professional employer organization",
            "PEO services",
            "workforce management",
            "IT staffing",
            "healthcare staffing",
            "contract staffing",
            "manpower services",
            "employee leasing",
            "labor staffing",
        ],
        "website_keywords": ["staffing", "recruitment", "hr ", "talent", "employment",
                             "temp", "personnel", "workforce", "executive search",
                             "placement", "peo ", "employee leasing", "manpower"],
    },
}

# Target metros with location bias coordinates
TARGET_METROS: List[Dict] = [
    {"name": "Dallas-Fort Worth", "lat": 32.7767, "lon": -96.7970, "state": "TX"},
    {"name": "Houston",           "lat": 29.7604, "lon": -95.3698, "state": "TX"},
    {"name": "Austin",            "lat": 30.2672, "lon": -97.7431, "state": "TX"},
    {"name": "San Antonio",       "lat": 29.4252, "lon": -98.4946, "state": "TX"},
    {"name": "Oklahoma City",     "lat": 35.4676, "lon": -97.5164, "state": "OK"},
    {"name": "Tulsa",             "lat": 36.1540, "lon": -95.9928, "state": "OK"},
    {"name": "Kansas City",       "lat": 39.0997, "lon": -94.5786, "state": "MO"},
    {"name": "Denver",            "lat": 39.7392, "lon": -104.9903, "state": "CO"},
    {"name": "Wichita",           "lat": 37.6872, "lon": -97.3301, "state": "KS"},
    {"name": "St. Louis",         "lat": 38.6270, "lon": -90.1994, "state": "MO"},
    {"name": "Phoenix",           "lat": 33.4484, "lon": -112.0740, "state": "AZ"},
    {"name": "Atlanta",           "lat": 33.7490, "lon": -84.3880, "state": "GA"},
    {"name": "Chicago",           "lat": 41.8781, "lon": -87.6298, "state": "IL"},
    {"name": "Nashville",         "lat": 36.1627, "lon": -86.7816, "state": "TN"},
    {"name": "Charlotte",         "lat": 35.2271, "lon": -80.8431, "state": "NC"},
    {"name": "Tampa",             "lat": 27.9506, "lon": -82.4572, "state": "FL"},
]

# Maximum results per query (Google Places limits vary by key tier)
_MAX_RESULTS_PER_QUERY = 20

# Min buy-signal score to qualify as a lead (0-100)
_MIN_QUALIFY_SCORE = 30

# Contact info regexes (shared with contact_discovery)
_PHONE_RE = re.compile(r"(\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


# ── SUPABASE CLIENT + CONFIG ────────────────────────────────────────────

def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb, default_max=100, default_threshold=30):
    """Read agent config from Supabase. Falls back to defaults."""
    try:
        r = sb.table("agent_config").select("*").eq("agent_name", "b2b_lead_scraper").limit(1).execute()
        if not r.data:
            return _DEFAULT_CONFIG.copy()
        row = r.data[0]
        cfg = row.get("config_json") or {}
        return {
            "enabled": row.get("enabled", True),
            "dry_run": row.get("dry_run", True),
            "max_per_run": cfg.get("max_per_run", default_max),
            "min_score_threshold": cfg.get("min_score_threshold", default_threshold),
        }
    except Exception:
        return _DEFAULT_CONFIG.copy()


def _log_activity(sb, run_id, started_at, status, **kwargs):
    """Log a run to agent_activity table."""
    finished_at = datetime.now(timezone.utc).isoformat()
    try:
        sb.table("agent_activity").insert({
            "agent_name": "b2b_lead_scraper",
            "run_id": str(run_id),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at,
            "status": status,
            **kwargs,
        }).execute()
    except Exception as e:
        log.warning(f"[b2b] activity log error: {e}")
    return finished_at


def _update_config(sb, status, finished_at):
    """Update last run timestamp in agent_config."""
    try:
        sb.table("agent_config").update({
            "last_run_at": finished_at,
            "last_run_status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("agent_name", "b2b_lead_scraper").execute()
    except Exception as e:
        log.debug(f"[b2b] config update error: {e}")


# ── GOOGLE PLACES TEXT SEARCH ──────────────────────────────────────────

async def _places_search(query: str, lat: float, lon: float) -> List[Dict]:
    """Search Google Places for businesses matching a query near a location."""
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        log.warning("no GOOGLE_MAPS_API_KEY set — B2B scraper cannot run")
        return []

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": _GOOGLE_FIELDS,
    }
    body = {
        "textQuery": query,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": 40000,  # 40km radius
            }
        },
        "maxResultCount": _MAX_RESULTS_PER_QUERY,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            out = []
            for p in data.get("places", []):
                out.append({
                    "name": (p.get("displayName") or {}).get("text", ""),
                    "address": p.get("formattedAddress", ""),
                    "phone": p.get("nationalPhoneNumber", ""),
                    "website": p.get("websiteUri", ""),
                    "rating": p.get("rating"),
                    "review_count": p.get("userRatingCount", 0),
                    "business_status": p.get("businessStatus", ""),
                    "types": p.get("types", []),
                })
            return out
    except httpx.HTTPError as e:
        log.debug(f"[b2b] Places API error for '{query}': {e}")
        return []


# ── WEBSITE SCRAPING FOR CONTACT INFO ─────────────────────────────────

_SCRAPE_PATHS = ["/contact", "/contact-us", "/about", "/about-us"]

async def _scrape_website(url: str) -> Dict[str, str]:
    """Fetch website pages and extract phone + email. Returns {phone, email}."""
    if not url:
        return {"phone": "", "email": ""}

    found = {"phone": "", "email": ""}
    async with httpx.AsyncClient(
        timeout=8, follow_redirects=True,
        headers={"User-Agent": "EmpireAI-v49 (B2B lead discovery)"},
    ) as client:
        # Always try the homepage first
        paths = [""] + _SCRAPE_PATHS
        for path in paths:
            try:
                r = await client.get(url.rstrip("/") + path)
                if r.status_code != 200:
                    continue
                text = r.text
                # Phone extraction
                if not found["phone"]:
                    m = _PHONE_RE.search(text)
                    if m:
                        cleaned = _clean_phone(m.group(1))
                        if cleaned:
                            found["phone"] = cleaned
                # Email extraction
                if not found["email"]:
                    emails = _EMAIL_RE.findall(text)
                    non_generic = [e for e in emails
                                   if e.split("@")[0] not in
                                   {"info", "hello", "support", "noreply", "admin", "webmaster"}]
                    if non_generic:
                        found["email"] = non_generic[0].lower()
                    elif emails:
                        found["email"] = emails[0].lower()
                if found["phone"] and found["email"]:
                    break
            except Exception:
                continue

    return found


def _clean_phone(raw: str) -> str:
    """Normalize phone to E.164."""
    if not raw:
        return ""
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return ""


# ── BUY SIGNAL SCORING ────────────────────────────────────────────────

def _score_buy_signal(place: Dict, website_data: Dict) -> int:
    """Score a B2B company by likelihood to buy leads/services. 0-100.

    Signals:
      - Has website: 15 pts
      - Has phone (from Places): 15 pts
      - Phone found via website scrape: 10 pts (bonus)
      - Has email: 10 pts
      - Review count ≥ 20 (established business): 15 pts
      - Review count ≥ 5 (some presence): 5 pts
      - Rating ≥ 4.0: 10 pts
      - Business status OPERATIONAL: 10 pts
      - Has website AND phone: 10 pts (confidence bonus)
    """
    score = 0

    # Website presence
    if place.get("website"):
        score += 15

    # Phone presence
    if place.get("phone"):
        score += 15
    if website_data.get("phone"):
        score += 10  # bonus for phone found on website

    # Email (only from website scrape)
    if website_data.get("email"):
        score += 10

    # Review count (size proxy)
    reviews = int(place.get("review_count") or 0)
    if reviews >= 20:
        score += 15
    elif reviews >= 5:
        score += 5

    # Rating (reputation proxy)
    rating = float(place.get("rating") or 0)
    if rating >= 4.0:
        score += 10

    # Verified operational
    status = (place.get("business_status") or "").upper()
    if status == "OPERATIONAL":
        score += 10

    # Confidence bonus: has both website and phone
    if place.get("website") and (place.get("phone") or website_data.get("phone")):
        score += 10

    return min(score, 100)


# ── CLASSIFY B2B SUB-NICHE ────────────────────────────────────────────

def _classify_sub_niche(name: str, website: str, place_types: List[str]) -> Optional[str]:
    """Classify a business into one of the 3 B2B sub-niches based on name,
    website URL, and Google Places types. Returns sub_niche string or None."""
    combined = (name + " " + (website or "")).lower()

    # Managed IT keywords
    it_kw = ["managed it", "it services", "it support", "msp ", "technology solutions",
             "cybersecurity", "cloud services", "it consulting", "technology group"]
    for kw in it_kw:
        if kw in combined:
            return "Managed IT"

    # Merchant Services keywords
    ms_kw = ["merchant services", "payment processing", "credit card processing",
             "payment gateway", "merchant service", "payment solutions", "paymentech"]
    for kw in ms_kw:
        if kw in combined:
            return "Merchant Services"

    # HR & Staffing keywords
    hr_kw = ["staffing", "recruitment", "employment agency", "talent acquisition",
             "hr consulting", "human resources", "temp agency", "personnel",
             "executive search", "workforce", "placement", "peo",
             "employee leasing", "manpower", "labor staffing"]
    for kw in hr_kw:
        if kw in combined:
            return "HR & Staffing"

    # Fall back to Google Places types
    types_lower = [t.lower() for t in place_types]
    it_types = {"information_technology", "computer_company", "software_company",
                "it_company", "cybersecurity", "data_center"}
    ms_types = {"finance_company", "bank", "financial_service"}
    hr_types = {"employment_agency", "employment_service", "recruitment_agency"}

    if it_types & set(types_lower):
        return "Managed IT"
    if hr_types & set(types_lower):
        return "HR & Staffing"

    return None  # couldn't confidently classify


def _classify_by_queries(search_queries: List[str]) -> Optional[str]:
    """Determine which sub-niche a set of search queries targets."""
    # Flatten: look at the first query's keywords
    first = search_queries[0].lower() if search_queries else ""
    if "it " in first or "msp" in first or "cyber" in first or "cloud" in first:
        return "Managed IT"
    if "merchant" in first or "payment" in first or "credit card" in first:
        return "Merchant Services"
    if "staffing" in first or "recruitment" in first or "hr " in first or "talent" in first:
        return "HR & Staffing"
    return None


# ── DEDUP: Check radar_targets for existing entry ──────────────────────

def _already_exists(sb, name: str, address: str, metro: Dict) -> bool:
    """Check if this business is already in radar_targets (by name + city).
    Uses city filter to narrow the search scope and avoid full table scans."""
    try:
        city = metro["name"].split("-")[0].strip()
        # Use the first 40 chars of name only for ilike, and narrow by city
        name_short = name[:40].replace("'", "")
        r = (sb.table("radar_targets")
             .select("id")
             .ilike("warehouse_name", f"%{name_short}%")
             .eq("city", city)
             .limit(1)
             .execute())
        return bool(r.data)
    except Exception:
        return False


# ── MAIN SEARCH CYCLE ─────────────────────────────────────────────────

async def _search_sub_niche(
    sb, sub_niche: str, config: Dict, metro: Dict, max_per_run: int = 100
) -> Dict:
    """Search a single sub-niche in a single metro. Returns stats."""
    metro_label = f"{metro['name']}, {metro['state']}"
    stats = {"found": 0, "qualified": 0, "inserted": 0, "skipped_dup": 0}

    for query in config["queries"]:
        full_query = f"{query} in {metro['name']}, {metro['state']}"
        places = await _places_search(full_query, metro["lat"], metro["lon"])
        stats["found"] += len(places)

        for place in places:
            name = (place.get("name") or "").strip()
            address = (place.get("address") or "").strip()
            if not name or not address:
                continue

            # Dedup against radar_targets (narrowed by city to avoid full scans)
            if _already_exists(sb, name, address, metro):
                stats["skipped_dup"] += 1
                continue

            # Classify sub-niche (prefer the known sub-niche from search context)
            sn = _classify_sub_niche(name, place.get("website", ""), place.get("types", []))
            if not sn:
                sn = sub_niche  # fall back to the context we're searching from

            # Scrape website for additional contact info
            website_data = await _scrape_website(place.get("website", ""))

            # Score buy signal
            score = _score_buy_signal(place, website_data)
            if score < _MIN_QUALIFY_SCORE:
                continue

            stats["qualified"] += 1

            # Build phone: prefer Places phone, fall back to scraped
            phone = place.get("phone") or website_data.get("phone") or ""
            email = website_data.get("email") or ""

            # Insert into radar_targets
            # Normalize buy signal score (0-100) → urgency_score (0-10 int)
            urgency = max(1, min(10, round(score / 10)))
            try:
                sb.table("radar_targets").insert({
                    "warehouse_name": name[:200],
                    "address": address[:300],
                    "city": metro["name"].split("-")[0].strip(),
                    "state": metro["state"],
                    "phone": phone,
                    "email": email,
                    "source_url": (place.get("website") or "")[:500],
                    "status": "active",
                    "asset_value": urgency,
                    "urgency_score": urgency,
                    "meta": {
                        "source": "B2B Lead Gen",
                        "b2b_sub_niche": sn,
                        "b2b_query": query,
                        "b2b_metro": metro["name"],
                        "buy_signal_score": score,
                        "rating": place.get("rating"),
                        "review_count": place.get("review_count"),
                        "business_status": place.get("business_status"),
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                    },
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
                stats["inserted"] += 1
                log.info(
                    f"[b2b] ✓ {sn} | {name[:50]} | {metro_label} | "
                    f"score={score} | phone={'yes' if phone else 'no'} | "
                    f"email={'yes' if email else 'no'}"
                )
                # Limit per run
                if stats["inserted"] >= max_per_run:
                    return stats
            except Exception as e:
                log.debug(f"[b2b] insert failed for {name}: {e}")

        # Rate-limit: small delay between queries to avoid Places API throttling
        await asyncio.sleep(0.3)

    return stats


# ── RUN ────────────────────────────────────────────────────────────────

async def run_async(
    sub_niches: Optional[List[str]] = None,
    metros: Optional[List[Dict]] = None,
    dry_run: bool = False,
    cfg: Optional[Dict] = None,
) -> Dict:
    """Execute a full B2B lead discovery cycle.

    Args:
        sub_niches: Which B2B sub-niches to search (default: all 3).
        metros: Which metros to search (default: all TARGET_METROS).
        dry_run: If True, log discoveries but don't insert to DB.

    Returns:
        Summary dict with per-sub-niche and total stats.
    """
    import uuid

    run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)

    if sub_niches is None:
        sub_niches = list(B2B_NICHES.keys())
    if metros is None:
        metros = TARGET_METROS

    sb = _sb()
    if cfg is None:
        cfg = _read_config(sb)

    if not cfg["enabled"]:
        _log_activity(sb, run_id, started_at, "skipped_disabled",
                      summary="disabled in agent_config")
        _update_config(sb, "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    effective_dry_run = cfg["dry_run"] if not dry_run else dry_run
    min_score = cfg["min_score_threshold"]

    total_stats = {
        "total_found": 0, "total_qualified": 0,
        "total_inserted": 0, "total_skipped_dup": 0,
        "by_sub_niche": {},
        "by_metro": {},
        "total_errored": 0,
        "dry_run": effective_dry_run,
        "started_at": started_at.isoformat(),
    }

    log.info(
        f"[b2b] Starting B2B lead discovery: "
        f"{len(sub_niches)} sub-niches × {len(metros)} metros "
        f"({'DRY RUN' if effective_dry_run else 'LIVE'}) "
        f"(min_score={min_score})"
    )

    for sub_niche in sub_niches:
        config = B2B_NICHES.get(sub_niche)
        if not config:
            log.warning(f"[b2b] Unknown sub-niche: {sub_niche}")
            continue

        niche_stats = {"found": 0, "qualified": 0, "inserted": 0, "skipped_dup": 0}

        for metro in metros:
            metro_label = f"{metro['name']}, {metro['state']}"
            if effective_dry_run:
                log.info(
                    f"[b2b] [DRY-RUN] Would search '{sub_niche}' in {metro_label} "
                    f"({len(config['queries'])} queries)"
                )
                continue

            result = await _search_sub_niche(sb, sub_niche, config, metro, max_per_run=cfg.get("max_per_run", 100))
            for k in niche_stats:
                niche_stats[k] += result[k]

            # Track metro stats
            if metro_label not in total_stats["by_metro"]:
                total_stats["by_metro"][metro_label] = 0
            total_stats["by_metro"][metro_label] += result["inserted"]

        total_stats["by_sub_niche"][sub_niche] = niche_stats
        total_stats["total_found"] += niche_stats["found"]
        total_stats["total_qualified"] += niche_stats["qualified"]
        total_stats["total_inserted"] += niche_stats["inserted"]
        total_stats["total_skipped_dup"] += niche_stats["skipped_dup"]

        log.info(
            f"[b2b] {sub_niche}: {niche_stats['found']} found, "
            f"{niche_stats['qualified']} qualified, "
            f"{niche_stats['inserted']} inserted, "
            f"{niche_stats['skipped_dup']} dups skipped"
        )

    total_stats["finished_at"] = datetime.now(timezone.utc).isoformat()
    elapsed = (
        datetime.fromisoformat(total_stats["finished_at"]) -
        datetime.fromisoformat(total_stats["started_at"])
    )
    total_stats["elapsed_seconds"] = round(elapsed.total_seconds(), 1)

    # Log activity to Supabase
    status = "ok" if total_stats["total_errored"] == 0 else "partial"
    _log_activity(sb, run_id, started_at, status,
                  rows_seen=total_stats["total_found"],
                  rows_processed=total_stats["total_inserted"],
                  rows_blocked=total_stats["total_skipped_dup"],
                  rows_errored=total_stats.get("total_errored", 0),
                  summary=json.dumps(total_stats, default=str)[:1000])
    _update_config(sb, status, total_stats["finished_at"])

    log.info(
        f"[b2b] Complete: {total_stats['total_found']} found, "
        f"{total_stats['total_qualified']} qualified, "
        f"{total_stats['total_inserted']} inserted, "
        f"{total_stats['total_skipped_dup']} dups skipped "
        f"({total_stats['elapsed_seconds']}s)"
    )

    return total_stats


def run(
    sub_niches: Optional[List[str]] = None,
    metros: Optional[List[Dict]] = None,
    dry_run: bool = False,
) -> Dict:
    """Sync entry point (wraps run_async)."""
    return asyncio.run(run_async(sub_niches, metros, dry_run))


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    """CLI entry point."""
    import argparse
    p = argparse.ArgumentParser(description="B2B Lead Scraper — Managed IT, Merchant Services, HR & Staffing")
    p.add_argument("--dry-run", action="store_true", help="Log discoveries without inserting to DB")
    p.add_argument("--sub-niche", choices=list(B2B_NICHES.keys()), help="Limit to one sub-niche")
    p.add_argument("--metro", help="Limit to one metro (e.g. 'Dallas-Fort Worth')")
    p.add_argument("--status", action="store_true", help="Print last run summary and exit")
    args = p.parse_args()

    if args.status:
        try:
            sb = _sb()
            r = (sb.table("agent_activity")
                 .select("*")
                 .eq("agent_name", "b2b_lead_scraper")
                 .order("started_at", desc=True)
                 .limit(1).execute())
            if r.data:
                print(json.dumps(r.data[0], indent=2, default=str))
            else:
                print("No previous runs found.")
        except Exception as e:
            print(f"Status check failed: {e}")
        return

    # Filter sub-niches
    niches = [args.sub_niche] if args.sub_niche else None

    # Filter metros
    metros = None
    if args.metro:
        metros = [m for m in TARGET_METROS if args.metro.lower() in m["name"].lower()]
        if not metros:
            print(f"Unknown metro: {args.metro}")
            return

    result = run(sub_niches=niches, metros=metros, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
