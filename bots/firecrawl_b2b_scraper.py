"""
EMPIRE V49 · FIRECRAWL B2B SCRAPER
====================================
Drop-in replacement for b2b_lead_scraper.py that uses firecrawl
(self-hosted at :3005) instead of Google Places (which has been
REQUEST_DENIED since 2026-06-20 due to key not having Places API
enabled).

Sources per niche + metro (URL templates that firecrawl scrapes):
  - yellowpages.com/{city}/{state}/{niche}         — primary (no JS)
  - manta.com/search?search={niche}&location={city} — backup
  - yelp.com/search?find_desc={niche}&find_loc={city}+{state} — cloudflare
    (will return 403, skip if so)
  - bbb.org/us/{state_lower}/{city_lower}/category/{niche-cats}
    — camofox fallback (cloudflare, but camofox gets through)

Falls back to camofox-browser for cloudflare-blocked sites.

Writes directly to radar_targets with source='firecrawl-b2b'.
Logs to agent_activity.
"""
import os
import re
import sys
import json
import time
import asyncio
import logging
import httpx
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass

try:
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
except Exception as e:
    sb = None
    print(f"[firecrawl_b2b] Supabase init failed: {e}")

log = logging.getLogger("empire.firecrawl_b2b")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [firecrawl-b2b] %(levelname)s %(message)s")

FIRECRAWL_URL = os.getenv("FIRECRAWL_URL", "http://localhost:3005")
CAMOFOX_URL = os.getenv("CAMOFOX_URL", "http://localhost:9377")

# Each B2B sub-niche + metro → URL templates
# (state, metro_slug, niche, niche_slug, search_query)
B2B_TARGETS = [
    # Texas metros — 6 B2B lanes
    ("TX", "dallas", "Managed IT", "managed-it", "managed it services"),
    ("TX", "dallas", "Merchant Services", "merchant-services", "merchant services"),
    ("TX", "dallas", "HR & Staffing", "hr-staffing", "staffing agency"),
    ("TX", "dallas", "Commercial Roofing", "commercial-roofing", "commercial roofing"),
    ("TX", "dallas", "Commercial Solar", "commercial-solar", "commercial solar"),
    ("TX", "dallas", "Debt Relief", "debt-relief", "debt relief"),
    ("TX", "houston", "Managed IT", "managed-it", "managed IT services"),
    ("TX", "houston", "Merchant Services", "merchant-services", "merchant services"),
    ("TX", "austin", "HR & Staffing", "hr-staffing", "staffing agency"),
    ("TX", "austin", "Commercial Solar", "commercial-solar", "commercial solar"),
    ("FL", "miami", "Managed IT", "managed-it", "managed IT services"),
    ("FL", "miami", "Commercial Roofing", "commercial-roofing", "commercial roofing"),
    ("CA", "los-angeles", "HR & Staffing", "hr-staffing", "staffing agency"),
    ("CA", "los-angeles", "Merchant Services", "merchant-services", "merchant services"),
    ("AZ", "phoenix", "Commercial Solar", "commercial-solar", "commercial solar"),
]

# Phone regex
PHONE_RE = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
# Email regex (loose)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# URL regex for websites
URL_RE = re.compile(r"https?://[A-Za-z0-9.-]+\.[a-z]{2,}[/\w\-.]*")
# Business name heuristic: line in markdown, 3-60 chars, mixed case, not a nav phrase
SKIP_PHRASES = {
    # nav
    "home", "about", "contact", "contact us", "login", "sign in", "sign up",
    "search", "menu", "privacy", "privacy policy", "terms", "terms of service",
    "cookie", "cookies", "advertisement", "sponsored", "results",
    "next", "previous", "filter", "sort by", "view all", "view more",
    "loading", "show more", "see more", "read more", "learn more",
    "skip to", "skip to content",
    # biz listing CTAs (not biz names)
    "claim this business", "be the first to review", "write a review",
    "request a quote", "get directions", "call now", "send email",
    "visit website", "book now", "schedule now", "free estimate",
    "get a free quote", "hours", "open now", "closed now",
    "add your business", "create a free company profile",
    "update listing information", "respond to reviews",
    "add business hours", "filter by distance", "within 1 miles",
    "within 5 miles", "within 10 miles", "within 20 miles",
    # Manta/YellowPages empty-state text
    "we encountered an error",
    "the business you are searching for may have closed",
    "what now", "check the spelling", "try a different search term",
    "try a more general search", "change your search location",
    "increase the search radius", "you can also search by category",
    "not here", "tell us what we are missing", "tell us what we're missing",
    # Cloudflare block page
    "please enable cookies", "sorry, you have been blocked",
    "you are unable to access", "why have i been blocked",
    "this website is using a security service",
    "what can i do to resolve this", "you can email the site owner",
    "cloudflare ray id", "performing your search", "search radius",
    "the action you just performed", "unusual traffic",
    # Google reCAPTCHA / consent
    "i'm not a robot", "before you continue", "recaptcha",
    "verify you are human", "checking your browser",
}


async def _camofox_scrape(url: str, session_key: str = "b2b", timeout_ms: int = 12000) -> str:
    """Scrape via camofox-browser (gets past cloudflare). Returns a11y snapshot text."""
    import httpx
    async with httpx.AsyncClient(timeout=60.0) as c:
        try:
            tab = await c.post(f"{CAMOFOX_URL}/tabs", json={
                "userId": "empire", "sessionKey": session_key, "url": url
            })
            tab_id = (tab.json() or {}).get("tabId")
            if not tab_id:
                return ""
            await c.post(f"{CAMOFOX_URL}/tabs/{tab_id}/navigate", json={"userId": "empire", "url": url})
            try:
                await c.post(f"{CAMOFOX_URL}/tabs/{tab_id}/wait", json={
                    "userId": "empire", "condition": "networkidle", "timeoutMs": timeout_ms
                })
            except Exception:
                pass
            # also fetch links — camofox returns real links when a11y snapshot is empty
            snap = await c.get(f"{CAMOFOX_URL}/tabs/{tab_id}/snapshot", params={"userId": "empire"})
            links = await c.get(f"{CAMOFOX_URL}/tabs/{tab_id}/links",
                                 params={"userId": "empire", "limit": 200})
            await c.request("DELETE", f"{CAMOFOX_URL}/tabs/{tab_id}", json={"userId": "empire"})
            text = ((snap.json() or {}).get("snapshot", "") or "")
            # concat biz-name-shaped link labels
            link_texts = []
            for l in (links.json() or {}).get("links", []) or []:
                t = (l.get("text") or "").strip()
                u = (l.get("url") or "")
                if t and len(t) >= 5 and len(t) <= 80 and "bbb.org" in u and ("/profile/" in u or "/business/" in u):
                    link_texts.append(t)
            if link_texts:
                text = text + chr(10) + chr(10).join(link_texts)
            return text
        except Exception as e:
            log.debug(f"camofox err: {e}")
            return ""


def _bbb_urls(state: str, city: str, niche_slug: str) -> str:
    city_pretty = city.replace("-", " ").title()
    return f"https://www.bbb.org/us/{state.lower()}/{city_pretty}/category/{niche_slug}"


def _is_skipped(line: str, skip_phrases: set) -> bool:
    """Substring match: skip if the normalized line CONTAINS any skip phrase.

    This catches full YP/Manta error sentences where only a fragment
    of the sentence is in skip_phrases."""
    norm = re.sub(r"[,;:!?\.\(\)]+", " ", line.lower()).strip()
    norm = re.sub(r"\s+", " ", norm)
    for phrase in skip_phrases:
        if phrase in norm:
            return True
    return False


def _record_activity(agent_name: str, status: str, rows: int, summary: str):
    if not sb:
        return
    try:
        import uuid as _uuid
        sb.table("agent_activity").insert({
            "run_id": str(_uuid.uuid4()),
            "agent_name": agent_name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "rows_processed": rows,
            "summary": summary[:500],
        }).execute()
    except Exception as e:
        log.debug(f"agent_activity insert failed: {e}")


def _firecrawl_scrape(url: str, timeout: int = 60) -> Optional[str]:
    """Call firecrawl /v1/scrape, return markdown or None on failure."""
    try:
        r = httpx.post(
            f"{FIRECRAWL_URL}/v1/scrape",
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True,
                  "timeout": timeout * 1000},
            timeout=timeout + 10,
        )
        if r.status_code != 200:
            log.debug(f"firecrawl {r.status_code} for {url}")
            return None
        data = r.json()
        if not data.get("success"):
            return None
        return (data.get("data") or {}).get("markdown") or ""
    except Exception as e:
        log.debug(f"firecrawl err {e}")
        return None


def _extract_businesses(markdown: str, source: str) -> List[Dict]:
    """Pull business-name + phone + email from markdown.

    For directory pages (yellowpages etc.), names appear as link text
    or list items. Heuristic: lines 5-80 chars, contains uppercase letter
    and not in SKIP_PHRASES.
    """
    if not markdown:
        return []

    out = []
    seen_names = set()

    for raw_line in markdown.split("\n"):
        line = raw_line.strip()
        # strip markdown link syntax
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        # strip leading bullets/numbers
        line = re.sub(r"^[\s\-\*•·\d\.\)]+", "", line).strip()

        if not line or len(line) < 5 or len(line) > 80:
            continue
        if line.lower() in SKIP_PHRASES:
            continue
        if not re.search(r"[A-Z]", line):  # must have at least one uppercase
            continue
        if line.startswith("(") or line.endswith(":"):
            continue
        # skip lines that are just punctuation or numbers
        if not re.search(r"[A-Za-z]{3,}", line):
            continue
        # require 2+ words (filters out "Cancel", "Back", etc.)
        if len(line.split()) < 2:
            continue
        # reject lines that are mostly common-words (filter nav text)
        _common = {"the","a","an","of","for","to","in","on","and","or","with","at",
                   "by","from","is","it","this","that","we","you","our","your","be","as"}
        words = re.findall(r"[A-Za-z]+", line.lower())
        if words and sum(1 for w in words if w in _common) / len(words) > 0.6:
            continue
        # require: phone OR (title-case pattern AND length 8+) OR biz keyword
        has_phone = bool(PHONE_RE.search(line))
        # title case: 2+ consecutive words starting with capital letter
        title_case_words = re.findall(r"\b[A-Z][a-zA-Z&]+\b", line)
        has_title = len(title_case_words) >= 2
        # 3+ consecutive all-caps tokens = abbreviation (LLC, USA, TX) — too noisy
        # 1 capital start per word is fine
        _biz = {"inc","llc","corp","co","company","group","services","service",
                "solutions","systems","technologies","tech","agency","associates",
                "enterprises","industries","partners","consulting",
                "roofing","hvac","solar","staffing","it","managed",
                "debt","relief","commercial","merchant","processing","network"}
        has_biz = any(b in line.lower() for b in _biz)
        if not (has_phone or (has_title and len(line) >= 8) or has_biz):
            continue

        # skip if line contains any SKIP_PHRASES fragment (substring)
        if _is_skipped(line, SKIP_PHRASES):
            continue
        # dedup
        key = re.sub(r"[,;:!?\.\(\)]+", " ", line.lower())
        key = re.sub(r"\s+", " ", key).strip()
        if key in seen_names:
            continue
        seen_names.add(key)

        phones = PHONE_RE.findall(line)
        emails = EMAIL_RE.findall(line)
        # phones/emails may be in surrounding text too — collect whole block
        # for now keep it simple, single line

        out.append({
            "business_name": line[:120],
            "phone": phones[0] if phones else "",
            "email": emails[0] if emails else "",
            "source": source,
        })

    return out


def _yellowpages_urls(state: str, city: str, niche_slug: str) -> List[str]:
    """Build yellowpages search URL."""
    return [f"https://www.yellowpages.com/{city}-{state.lower()}/{niche_slug}"]


def _manta_urls(state: str, city: str, niche_slug: str, query: str) -> List[str]:
    """Build manta.com search URL."""
    return [f"https://www.manta.com/search?search={query.replace(' ', '+')}&location={city.replace('-', '+')}+{state}"]


async def _scrape_target_async(state: str, city: str, niche: str, niche_slug: str, query: str) -> List[Dict]:
    """Try firecrawl first (fast, no anti-bot), fall back to camofox BBB."""
    results = []

    # 1) firecrawl on yellowpages + manta (fast but cloudflare-blocked)
    for url in _yellowpages_urls(state, city, niche_slug):
        md = _firecrawl_scrape(url)
        if md and "blocked" not in md.lower() and "cloudflare" not in md.lower() and len(md) > 500:
            results.extend(_extract_businesses(md, source="firecrawl-yellowpages"))
            if len(results) >= 3:
                break
        time.sleep(0.3)

    # 2) camofox on BBB (gets through cloudflare, real biz data)
    if len(results) < 3:
        bbb_url = _bbb_urls(state, city, niche_slug)
        md = await _camofox_scrape(bbb_url, session_key=f"b2b-{niche_slug}-{city}")
        if md and len(md) > 200:
            results.extend(_extract_businesses(md, source="camofox-bbb"))

    return results


def _scrape_target(state: str, city: str, niche: str, niche_slug: str, query: str) -> List[Dict]:
    """Sync wrapper for the async scrape path."""
    import asyncio
    return asyncio.run(_scrape_target_async(state, city, niche, niche_slug, query))


def _dedup(results: List[Dict]) -> List[Dict]:
    """Dedupe by business_name (case-insensitive)."""
    seen = set()
    out = []
    for r in results:
        k = r["business_name"].lower().strip()
        if k in seen or len(k) < 5:
            continue
        seen.add(k)
        out.append(r)
    return out


def _persist(results: List[Dict], niche: str, metro: str, state: str, city_for_dedup: str = "") -> int:
    """Write to radar_targets."""
    if not sb or not results:
        return 0
    inserted = 0
    for r in results:
        try:
            name = r["business_name"]
            existing = sb.table("radar_targets").select("id").eq("name", name).eq("city", city_for_dedup).limit(1).execute()
            if existing.data:
                continue
            row = {
                "source": r.get("source", "firecrawl-b2b"),
                "niche": niche,
                "city": city_for_dedup,
                "state": state,
                "name": name[:200],
                "phone": (r.get("phone") or "")[:30],
                "email": (r.get("email") or "")[:200],
                "address": f"{city_for_dedup}, {state}",  # NOT NULL — default to city/state
                "meta": json.dumps(r)[:2000],
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "status": "active",  # enum value
            }
            sb.table("radar_targets").insert(row).execute()
            inserted += 1
        except Exception as e:
            log.debug(f"radar_targets insert failed: {e}")
    return inserted


def run_once(targets: Optional[List] = None) -> Dict:
    """Single cycle: scrape configured B2B targets via firecrawl."""
    started = datetime.now(timezone.utc)
    targets = targets or B2B_TARGETS
    log.info(f"[firecrawl-b2b] starting cycle: {len(targets)} targets")

    total_scraped = 0
    total_inserted = 0
    by_niche = {}

    for state, city, niche, niche_slug, query in targets:
        log.info(f"[firecrawl-b2b] target: {niche} in {city}/{state}")
        try:
            results = _scrape_target(state, city, niche, niche_slug, query)
            results = _dedup(results)
            by_niche[niche] = by_niche.get(niche, 0) + len(results)
            total_scraped += len(results)
            inserted = _persist(results, niche, f"{city}-{state.lower()}", state,
                              city_for_dedup=city.replace("-", " ").title())
            total_inserted += inserted
            log.info(f"  → {len(results)} found, {inserted} inserted")
        except Exception as e:
            log.warning(f"target {niche}/{city} failed: {e}")
        time.sleep(1)

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    summary = json.dumps({
        "targets": len(targets),
        "scraped": total_scraped,
        "inserted": total_inserted,
        "by_niche": by_niche,
        "duration_s": round(duration, 1),
    })
    status = "ok" if total_scraped > 0 else "error"
    _record_activity("firecrawl_b2b", status, total_inserted, summary)
    log.info(f"[firecrawl-b2b] cycle complete: {summary}")
    return {"scraped": total_scraped, "inserted": total_inserted, "by_niche": by_niche}


def run_loop(interval_seconds: int = 21600):
    import asyncio
    async def _run():
        while True:
            try:
                run_once()
            except Exception as e:
                log.error(f"firecrawl-b2b loop err: {e}")
            await asyncio.sleep(max(60, interval_seconds))
    asyncio.run(_run())


if __name__ == "__main__":
    print(json.dumps(run_once(), indent=2))