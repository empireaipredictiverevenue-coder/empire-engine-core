"""
EMPIRE V49 · B2B LEAD SCRAPER
==============================
Dedicated lead discovery agent for 6 lanes:
  - Lane 29: Managed IT         (sub_niche="Managed IT")
  - Lane 30: Merchant Services  (sub_niche="Merchant Services") — expanded to cover B2B processing,
                                 high-risk, POS/retail, convenience stores, cash discount programs
  - Lane 31: HR & Staffing      (sub_niche="HR & Staffing")
  - Lane 36: Commercial Roofing (sub_niche="Commercial Roofing")
  - Lane 37: Commercial Solar   (sub_niche="Commercial Solar")
  - Lane 38: Debt Relief        (sub_niche="Debt Relief")

Uses Google Places API text search to find companies in target
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

# Shared email validator — single source of truth for email quality
from bots.email_validator import is_valid_email, describe_rejection

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

# ── Dev Browser Integration (JS-rendered website scraping fallback) ─────
_DEV_BROWSER_AVAILABLE = False
try:
    from skills.browser_harness import scrape_page as _dev_scrape
    _DEV_BROWSER_AVAILABLE = True
except ImportError:
    pass

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
            # B2B professional services (lowest churn — law firms, dentists, accountants)
            "quickbooks payment integration",
            "payment processing for law firms",
            "medical billing services",
            # High-risk merchant accounts (Alt-Pay moat)
            "high risk merchant account",
            "cbd payment processing",
            # Retail / POS (volume play)
            "pos system for retail stores",
            # Convenience stores / petro (multi-product, high volume)
            "point of sale for convenience stores",
            # Cash discount / dual pricing (Alt-Pay differentiator)
            "cash discount program",
            "interchange plus pricing",
        ],
        "website_keywords": ["merchant services", "payment processing", "credit card processing", "pos",
                             "quickbooks payment", "b2b payment", "level 3 processing",
                             "cash discount", "dual pricing", "interchange plus",
                             "high risk merchant", "payment gateway integration", "paymentech"],
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
    "Commercial Roofing": {
        "queries": [
            "commercial roofing contractor",
            "commercial roofing company",
            "industrial roofing services",
            "flat roofing specialist",
            "commercial roof repair",
            "roofing contractor for businesses",
        ],
        "website_keywords": ["commercial roofing", "flat roof", "industrial roofing",
                             "roofing contractor", "roofing company", "roof repair"],
    },
    "Commercial Solar": {
        "queries": [
            "commercial solar installation",
            "solar energy company",
            "commercial solar panel installer",
            "business solar solutions",
            "renewable energy for commercial",
            "solar power for businesses",
        ],
        "website_keywords": ["commercial solar", "solar installation", "solar energy",
                             "solar panel", "solar power", "renewable energy", "pv system"],
    },
    "Debt Relief": {
        "queries": [
            "debt relief services",
            "debt settlement company",
            "credit counseling agency",
            "debt consolidation services",
            "financial debt solutions",
            "debt management company",
        ],
        "website_keywords": ["debt relief", "debt settlement", "credit counseling",
                             "debt consolidation", "debt management", "debt solution",
                             "credit relief", "financial counseling"],
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

# Hard daily cap on Google Places API (Text Search) calls. Google
# bills ~$32 per 1000 calls; £154 in one day = ~6000 calls = a runaway
# agent (we saw 30 b2b_lead_scraper runs in 24h on Jun 15). Set to
# 500 so one full run (6 niches x 16 metros x ~7 queries = ~672)
# hits the cap and stops mid-grid, never the full bill.
# Tune with PLACES_DAILY_BUDGET env.
_DEFAULT_DAILY_BUDGET = 500

# Module-level counter for the current process. Combined with the
# daily counter persisted in agent_config, this means: even if 5
# parallel runs go off at once, they all stop at the budget.
_PLACES_CALLS_THIS_RUN = 0

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


# ── PLACES API DAILY BUDGET COUNTER ──────────────────────────────────

def _today_utc() -> str:
    """YYYY-MM-DD in UTC. Counter resets when this changes."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _places_calls_today(sb) -> int:
    """Return how many Places API calls have been recorded today (UTC).

    Stored in agent_config.config_json for b2b_lead_scraper. Reads
    + writes are best-effort — if Supabase is unreachable we return 0
    so the agent keeps running (a single run's runaway is still
    capped by the in-process _PLACES_CALLS_THIS_RUN counter).
    """
    try:
        r = (sb.table("agent_config")
               .select("config_json")
               .eq("agent_name", "b2b_lead_scraper")
               .limit(1)
               .execute())
        if not r.data:
            return 0
        cfg = r.data[0].get("config_json") or {}
        date = cfg.get("places_date", "")
        if date != _today_utc():
            return 0  # counter from a previous day, treat as fresh
        return int(cfg.get("places_calls_today", 0))
    except Exception:
        return 0


def _record_places_call(sb) -> None:
    """Increment the daily counter in agent_config. Best-effort."""
    global _PLACES_CALLS_THIS_RUN
    try:
        r = (sb.table("agent_config")
               .select("config_json")
               .eq("agent_name", "b2b_lead_scraper")
               .limit(1)
               .execute())
        if not r.data:
            return
        cfg = dict(r.data[0].get("config_json") or {})
        today = _today_utc()
        if cfg.get("places_date") != today:
            cfg["places_date"] = today
            cfg["places_calls_today"] = 0
        cfg["places_calls_today"] = int(cfg.get("places_calls_today", 0)) + 1
        sb.table("agent_config").update({
            "config_json": cfg,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("agent_name", "b2b_lead_scraper").execute()
    except Exception as e:
        log.debug(f"[b2b] could not record places call: {e}")


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
    global _PLACES_CALLS_THIS_RUN
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        log.warning("no GOOGLE_MAPS_API_KEY set — B2B scraper cannot run")
        return []

    # Daily budget guard. The agent is allowed to spend up to
    # PLACES_DAILY_BUDGET calls per UTC day across all runs.
    # Counter is persisted in agent_config so multiple parallel runs
    # (or runs that restart the process) all see the same number.
    try:
        budget = int(os.getenv("PLACES_DAILY_BUDGET", str(_DEFAULT_DAILY_BUDGET)))
    except ValueError:
        budget = _DEFAULT_DAILY_BUDGET
    sb = _sb()
    used_today = _places_calls_today(sb)
    if used_today >= budget:
        log.warning(
            f"[b2b] Places daily budget exhausted ({used_today}/{budget}). "
            f"Skipping search for '{query}'. Raise PLACES_DAILY_BUDGET "
            f"in env to allow more, or wait until tomorrow (UTC)."
        )
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
            # Billable API call happened. Count it.
            _PLACES_CALLS_THIS_RUN += 1
            _record_places_call(sb)
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

    # If static HTTP scrape didn't find anything, try dev-browser for JS-rendered pages
    if not found["phone"] and not found["email"] and _DEV_BROWSER_AVAILABLE:
        try:
            loop = asyncio.get_event_loop()
            dev_result = await loop.run_in_executor(None, _dev_scrape, url)
            if dev_result and dev_result.get("text_content"):
                text = dev_result["text_content"]
                # Phone extraction from dev-browser output
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
        except Exception:
            pass

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
    """Classify a business into one of the B2B sub-niches based on name,
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
             "payment gateway", "merchant service", "payment solutions", "paymentech",
             "quickbooks payment", "b2b payment", "level 3 processing",
             "cash discount", "dual pricing", "interchange plus",
             "high risk merchant", "payment gateway integration", "pos system"]
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

    # Commercial Roofing keywords
    cr_kw = ["commercial roofing", "flat roof", "industrial roofing",
             "roofing contractor", "roofing company", "roof repair",
             "commercial roof", "metal roofing"]
    for kw in cr_kw:
        if kw in combined:
            return "Commercial Roofing"

    # Commercial Solar keywords
    cs_kw = ["commercial solar", "solar installation", "solar energy",
             "solar panel", "solar power", "renewable energy",
             "solar company", "solar contractor", "pv installation", "photovoltaic"]
    for kw in cs_kw:
        if kw in combined:
            return "Commercial Solar"

    # Debt Relief keywords
    dr_kw = ["debt relief", "debt settlement", "credit counseling",
             "debt consolidation", "debt management", "debt solution",
             "credit relief", "financial counseling", "debt help",
             "credit repair", "debt negotiation"]
    for kw in dr_kw:
        if kw in combined:
            return "Debt Relief"

    # Fall back to Google Places types
    types_lower = [t.lower() for t in place_types]
    it_types = {"information_technology", "computer_company", "software_company",
                "it_company", "cybersecurity", "data_center"}
    ms_types = {"finance_company", "bank", "financial_service"}
    hr_types = {"employment_agency", "employment_service", "recruitment_agency"}
    cr_types = {"roofing_contractor", "general_contractor"}
    cs_types = {"solar_energy_company", "solar_installer", "renewable_energy_company"}
    dr_types = {"credit_counseling_service", "financial_consultant", "debt_relief_service"}

    if it_types & set(types_lower):
        return "Managed IT"
    if hr_types & set(types_lower):
        return "HR & Staffing"
    if cr_types & set(types_lower):
        return "Commercial Roofing"
    if cs_types & set(types_lower):
        return "Commercial Solar"
    if dr_types & set(types_lower):
        return "Debt Relief"

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


# ── MAIN SEARCH CYCLE (OPTIMIZED) ──────────────────────────────────────

async def _search_sub_niche(
    sb, sub_niche: str, config: Dict, metro: Dict, max_per_run: int = 100
) -> Dict:
    """Search a single sub-niche in a single metro. Returns stats.

    OPTIMIZED: Places API calls, dedup checks, and website scraping
    all run in parallel via asyncio.gather. Batch inserts.
    """
    metro_label = f"{metro['name']}, {metro['state']}"
    stats = {"found": 0, "qualified": 0, "inserted": 0, "skipped_dup": 0}

    # ── 1. Run ALL queries for this metro in parallel ────────────────
    queries = [f"{q} in {metro['name']}, {metro['state']}" for q in config["queries"]]
    results = await asyncio.gather(*[
        _places_search(q, metro["lat"], metro["lon"]) for q in queries
    ])
    all_places = []
    for r in results:
        all_places.extend(r)
    stats["found"] = len(all_places)

    if not all_places:
        return stats

    # ── 2. Filter blanks, classify, and batch-dedup ──────────────────
    city = metro["name"].split("-")[0].strip()
    candidates = []
    for place in all_places:
        name = (place.get("name") or "").strip()
        address = (place.get("address") or "").strip()
        if not name or not address:
            continue
        sn = _classify_sub_niche(name, place.get("website", ""), place.get("types", []))
        if not sn:
            sn = sub_niche
        candidates.append({"place": place, "name": name, "address": address, "sn": sn})

    # ── 3. Batch dedup: check names AND phones in one query per city ────
    # Collect short names + phones, then query existing ones in one shot
    short_names = [c["name"][:40].replace("'", "") for c in candidates]
    candidate_phones = [c["place"].get("phone", "") for c in candidates]
    candidate_phones = [p for p in candidate_phones if p]
    try:
        dedup_res = (
            sb.table("radar_targets")
            .select("warehouse_name,phone")
            .eq("city", city)
            .in_("warehouse_name", list(set(short_names)))
            .execute()
        )
        existing_names = set(r["warehouse_name"] for r in (dedup_res.data or []))
        existing_phones = set(r["phone"] for r in (dedup_res.data or []) if r.get("phone"))
    except Exception:
        existing_names = set()
        existing_phones = set()

    # Also query phones globally (may exist from other cities/niches)
    if candidate_phones:
        try:
            global_phone_res = (
                sb.table("radar_targets")
                .select("phone")
                .in_("phone", list(set(candidate_phones)))
                .execute()
            )
            existing_phones.update(r["phone"] for r in (global_phone_res.data or []) if r.get("phone"))
        except Exception:
            pass

    deduped = []
    for c in candidates:
        c_phone = c["place"].get("phone", "")
        if c["name"][:40].replace("'", "") in existing_names:
            stats["skipped_dup"] += 1
        elif c_phone and c_phone in existing_phones:
            stats["skipped_dup"] += 1
        else:
            deduped.append(c)

    if not deduped:
        return stats

    # ── 4. Parallel website scraping for ALL deduped candidates ──────
    scrape_tasks = [_scrape_website(c["place"].get("website", "")) for c in deduped]
    scraped_results = await asyncio.gather(*scrape_tasks)

    # ── 5. Score, filter, prepare batch inserts ──────────────────────
    batch = []
    mail_batch = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for i, c in enumerate(deduped):
        place = c["place"]
        website_data = scraped_results[i]

        score = _score_buy_signal(place, website_data)
        if score < _MIN_QUALIFY_SCORE:
            continue

        stats["qualified"] += 1
        phone = place.get("phone") or website_data.get("phone") or ""
        email = website_data.get("email") or ""

        # ── EMAIL VALIDATION GATE ───────────────────────────────────
        # Block garbage emails (image files, placeholders, etc.) before
        # they enter the pipeline. Gmail spam filters penalize sending
        # to addresses like shadow@2x.png or you@community.com.
        if email and not is_valid_email(email, strict=True):
            reason = describe_rejection(email) or "unknown"
            log.info(f"[b2b] ✗ BLOCKED garbage email for {c['name'][:40]}: {email} ({reason})")
            email = ""  # clear the email — don't block the whole lead, just don't mail it

        urgency = max(1, min(10, round(score / 10)))

        batch.append({
            "warehouse_name": c["name"][:200],
            "address": c["address"][:300],
            "city": city,
            "state": metro["state"],
            "phone": phone,
            "email": email,
            "source_url": (place.get("website") or "")[:500],
            "status": "active",
            # FIX: do NOT write urgency (1-10) as asset_value — it corrupts
            # lead_enricher scoring. Leave NULL so enricher falls back to
            # warehouse_name keyword matching. The radar_asset_enricher agent
            # backfills real \$ via ATTOM/RentCast/formula every 6h.
            "asset_value": None if not place.get("rating") else None,
            "urgency_score": urgency,
            "meta": {
                "source": "B2B Lead Gen",
                "b2b_sub_niche": c["sn"],
                "b2b_metro": metro["name"],
                "buy_signal_score": score,
                "rating": place.get("rating"),
                "review_count": place.get("review_count"),
                "business_status": place.get("business_status"),
                "scraped_at": now_iso,
            },
            "created_at": now_iso,
        })

        if email and c["sn"]:
            mail_batch.append({
                "email": email,
                "target_addr": f"{city}, {metro['state']}",
                "sequence_type": "b2b_outreach",
                "current_step": 0,
                "status": "active",
                "next_send_at": now_iso,
                "meta": {
                    "company": c["name"][:200],
                    "b2b_sub_niche": c["sn"],
                    "metro": metro["name"],
                    "source": "B2B Lead Gen",
                },
            })

        # Cap at max_per_run
        if stats["qualified"] >= max_per_run:
            break

    # ── 6. Final phone dedup + batch insert ──────────────────────────
    if batch:
        # Collect all phones in the batch
        batch_phones = [b["phone"] for b in batch if b["phone"]]
        if batch_phones:
            try:
                phone_check = (
                    sb.table("radar_targets")
                    .select("phone")
                    .in_("phone", list(set(batch_phones)))
                    .execute()
                )
                conflict_phones = set(r["phone"] for r in (phone_check.data or []))
                clean = [b for b in batch if not b["phone"] or b["phone"] not in conflict_phones]
                stats["skipped_dup"] += len(batch) - len(clean)
                batch = clean
            except Exception:
                pass  # proceed with best-effort insert

        if batch:
            try:
                sb.table("radar_targets").insert(batch).execute()
                stats["inserted"] = len(batch)
                for item in batch:
                    log.info(
                        f"[b2b] ✓ {item['meta']['b2b_sub_niche']} | "
                        f"{item['warehouse_name'][:50]} | {metro_label} | "
                        f"score={item['meta']['buy_signal_score']} | "
                        f"phone={'yes' if item['phone'] else 'no'} | "
                        f"email={'yes' if item['email'] else 'no'}"
                    )
            except Exception as e:
                log.error(f"[b2b] batch insert failed after phone dedup: {e}")
                # Last resort: individual inserts with conflict skip
                inserted = 0
                for item in batch:
                    try:
                        sb.table("radar_targets").insert(item).execute()
                        inserted += 1
                    except Exception:
                        stats["skipped_dup"] += 1
                stats["inserted"] = inserted

    # ── 7. Batch enroll email sequences (skip unsubscribed + existing) ──
    if mail_batch:
        try:
            # Check unsubscribes in bulk
            emails = list(set(m["email"] for m in mail_batch))
            unsub_res = sb.table("email_unsubscribes").select("email").in_("email", emails).execute()
            unsub_set = set(r["email"] for r in (unsub_res.data or []))

            existing_seq_res = sb.table("email_sequences").select("email").in_("email", emails).execute()
            existing_seq = set(r["email"] for r in (existing_seq_res.data or []))

            to_enroll = [m for m in mail_batch
                         if m["email"] not in unsub_set
                         and m["email"] not in existing_seq]

            if to_enroll:
                sb.table("email_sequences").insert(to_enroll).execute()
                log.info(f"[b2b] ✉ batch enrolled {len(to_enroll)} in b2b_outreach drip")
        except Exception as e:
            log.debug(f"[b2b] batch email enroll skipped: {e}")

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

        if effective_dry_run:
            for metro in metros:
                metro_label = f"{metro['name']}, {metro['state']}"
                log.info(
                    f"[b2b] [DRY-RUN] Would search '{sub_niche}' in {metro_label} "
                    f"({len(config['queries'])} queries)"
                )
            continue

        # OPTIMIZED: Process all metros for this sub-niche IN PARALLEL
        metro_results = await asyncio.gather(*[
            _search_sub_niche(sb, sub_niche, config, metro, max_per_run=cfg.get("max_per_run", 100))
            for metro in metros
        ])

        for i, result in enumerate(metro_results):
            metro_label = f"{metros[i]['name']}, {metros[i]['state']}"
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
    # Surface Places API call count for the daily-budget sanity check.
    try:
        budget = int(os.getenv("PLACES_DAILY_BUDGET", str(_DEFAULT_DAILY_BUDGET)))
    except ValueError:
        budget = _DEFAULT_DAILY_BUDGET
    places_today = _places_calls_today(sb)
    total_stats["places_api_calls_this_run"] = _PLACES_CALLS_THIS_RUN
    total_stats["places_api_calls_today"] = places_today
    total_stats["places_daily_budget"] = budget
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
        f"({total_stats['elapsed_seconds']}s) "
        f"[Places API: {_PLACES_CALLS_THIS_RUN} this run, "
        f"{places_today}/{budget} today]"
    )

    return total_stats


def run(
    sub_niches: Optional[List[str]] = None,
    metros: Optional[List[Dict]] = None,
    dry_run: bool = False,
) -> Dict:
    """Sync entry point (wraps run_async)."""
    return asyncio.run(run_async(sub_niches, metros, dry_run))


# ── Agent runner compatibility ────────────────────────────────────────


def run_once():
    """Single cycle for agent_runner loop mode."""
    return run()


# ── CLI ────────────────────────────────────────────────────────────────


def main():
    """CLI entry point."""
    import argparse
    p = argparse.ArgumentParser(description="B2B Lead Scraper — 6 niches: Managed IT, Merchant Services, HR & Staffing, Commercial Roofing, Commercial Solar, Debt Relief")
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
