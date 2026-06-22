"""
BBB Search + Profile extractor (uses camofox-browser)
=====================================================

The previous BBB scraper hit /category/ pages, which only render the
category titles ("Painting Contractors") instead of real business names.

This scraper:
  1. Hits /search?find_text=<niche>&find_loc=<city>,+<state>&find_type=Category
  2. Extracts /us/<state>/<city>/profile/<niche>/<slug>-<id> links (real businesses)
  3. Visits up to N profile pages to extract phone, address, website

Output: list of dicts with name, phone, address, website, url, niche, metro.
"""
import os
import sys
import re
import json
import asyncio
import logging
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env")

from config.metros import METROS
from bots.predictive_camofox_scraper import PredictiveCamofoxScraper

log = logging.getLogger("bbb_search")

CAMOFOX_URL = os.environ.get("CAMOFOX_URL", "http://localhost:9377")
USER_ID = "empire"

# Map our niche slugs to BBB category slugs (they're similar but not identical)
NICHE_TO_BBB_CATEGORY = {
    "roofing": "roofing-contractors",
    "hvac": "air-conditioning-contractors",
    "solar": "solar-energy-contractors",
    "restoration": "fire-and-water-damage-restoration",
    "water mitigation": "fire-and-water-damage-restoration",
    "general contractor": "general-contractors",
    "public_adjuster": "public-adjusters",
    "gutter": "gutter-contractors",
    "tree removal": "tree-service",
    "plumbing": "plumbing-contractors",
    "electrical": "electrical-contractors",
    "paving": "paving-contractors",
    "commercial roofing": "roofing-contractors",
    "commercial solar": "solar-energy-contractors",
}

# BBB profile URL pattern. The camofox a11y snapshot embeds paths like:
#   /url: /us/tx/fort-worth/profile/roofing-contractors/usa-roofing-construction-0825-235973508
# rather than HTML href="..." attributes.
PROFILE_URL_RE = re.compile(
    r'(?:href="|/url:\s*)(/us/([a-z]{2})/([a-z0-9\-]+)/profile/([^/\s]+)/([a-z0-9\-]+))',
    re.IGNORECASE,
)


def _metro_to_state_lower(metro: str) -> Optional[str]:
    if metro in METROS:
        return METROS[metro].get("state", "").lower()
    return None


def _metro_to_city_slug(metro: str) -> str:
    return metro.lower().replace(" ", "-").replace("/", "-")


async def _search_bbb(scraper: PredictiveCamofoxScraper, niche: str, metro: str, max_pages: int = 2) -> List[Dict]:
    """
    Hit BBB /search and return a list of profile URLs + names found.
    """
    category = NICHE_TO_BBB_CATEGORY.get(niche, niche.replace(" ", "-"))
    city = metro.split("/")[0].strip()
    state_lower = _metro_to_state_lower(metro)
    if not state_lower:
        log.warning(f"[bbb] no state for metro '{metro}'")
        return []

    # Build /search URL
    params = {
        "find_text": category.replace("-", " "),
        "find_loc": f"{city}, {state_lower.upper()}",
        "find_type": "Category",
    }
    search_url = "https://www.bbb.org/search?" + urllib.parse.urlencode(params)
    log.info(f"[bbb] searching: {search_url}")

    # Open a tab in camofox
    tab = await scraper.create_tab("https://www.google.com", user_id=USER_ID, session_key=f"bbb-search-{niche}-{metro}")
    tab_id = tab.get("id") or tab.get("tabId")
    if not tab_id:
        log.warning("[bbb] create_tab returned no id")
        return []

    found: List[Dict] = []
    seen_urls: set = set()

    for attempt in range(3):
        try:
            # Always start with a fresh tab on retry so a previous page crash is gone
            tab = await scraper.create_tab("https://www.google.com", user_id=USER_ID, session_key=f"bbb-search-{niche}-{metro}-{attempt}")
            new_id = tab.get("id") or tab.get("tabId")
            if not new_id:
                log.warning(f"[bbb] create_tab returned no id on attempt {attempt+1}")
                await asyncio.sleep(2)
                continue
            tab_id = new_id

            nav = await scraper.client.post(
                f"{CAMOFOX_URL}/tabs/{tab_id}/navigate",
                json={"userId": USER_ID, "url": search_url},
            )
            if nav.status_code >= 400 or "Page crashed" in nav.text:
                log.warning(f"[bbb] navigate attempt {attempt+1} failed {nav.status_code}")
                continue

            try:
                await scraper.client.post(
                    f"{CAMOFOX_URL}/tabs/{tab_id}/wait",
                    json={"userId": USER_ID, "condition": "networkidle", "timeoutMs": 8000},
                )
            except Exception:
                pass

            snap_resp = await scraper.client.get(
                f"{CAMOFOX_URL}/tabs/{tab_id}/snapshot",
                params={"userId": USER_ID},
            )
            if snap_resp.status_code != 200:
                log.warning(f"[bbb] snapshot fetch failed: {snap_resp.status_code} (attempt {attempt+1})")
                continue

            snap_text = snap_resp.text or ""
            for m in PROFILE_URL_RE.finditer(snap_text):
                path, state, city_slug, cat_slug, slug = m.groups()
                full_url = "https://www.bbb.org" + path
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                name = slug.rsplit("-", 1)[0].replace("-", " ").title()
                ctx_pattern = re.compile(
                    r'link\s+"([^"]+)"[^\n]*\n\s*-?\s*/url:\s*' + re.escape(path) + r'',
                    re.IGNORECASE,
                )
                ctx = ctx_pattern.search(snap_text)
                if ctx:
                    candidate = ctx.group(1).strip()
                    if candidate.lower().startswith("advertisement:"):
                        candidate = candidate.split(":", 1)[1].strip()
                    if len(candidate) >= 4 and not candidate.isdigit():
                        name = candidate[:120]

                found.append({
                    "name": name,
                    "url": full_url,
                    "niche": niche,
                    "metro": metro,
                    "state": state.upper(),
                    "city_slug": city_slug,
                    "cat_slug": cat_slug,
                    "source": "bbb-search",
                })
                if len(found) >= 30:
                    break

            log.info(f"[bbb] {search_url} -> {len(found)} profile links")
            break  # success — exit retry loop

        except Exception as e:
            log.warning(f"[bbb] attempt {attempt+1} exception: {e}")
            await asyncio.sleep(2)
            continue
        finally:
            try:
                await scraper.client.request("DELETE", f"{CAMOFOX_URL}/tabs/{tab_id}", json={"userId": USER_ID})
            except Exception:
                pass

    return found


async def _scrape_profile(scraper: PredictiveCamofoxScraper, profile: Dict) -> Dict:
    """
    Visit a single BBB profile page and extract phone, address, website.
    Returns profile dict with phone/address/website filled in.
    """
    tab = await scraper.create_tab("https://www.google.com", user_id=USER_ID, session_key=f"bbb-prof-{profile['url'][-10:]}")
    tab_id = tab.get("id") or tab.get("tabId")
    if not tab_id:
        return profile

    try:
        nav = await scraper.client.post(
            f"{CAMOFOX_URL}/tabs/{tab_id}/navigate",
            json={"userId": USER_ID, "url": profile["url"]},
        )
        if nav.status_code >= 400:
            return profile

        try:
            await scraper.client.post(
                f"{CAMOFOX_URL}/tabs/{tab_id}/wait",
                json={"userId": USER_ID, "condition": "networkidle", "timeoutMs": 6000},
            )
        except Exception:
            pass

        snap_resp = await scraper.client.get(f"{CAMOFOX_URL}/tabs/{tab_id}/snapshot", params={"userId": USER_ID})
        if snap_resp.status_code != 200:
            return profile

        snap_text = snap_resp.text or ""

        # Phone: BBB profile pages have tel: links
        tel_match = re.search(r'tel:\+?1?(\d{10})', snap_text)
        if not tel_match:
            # fallback: look for "(XXX) XXX-XXXX" or "XXX-XXX-XXXX"
            tel_match = re.search(r'\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}', snap_text)
        if tel_match:
            digits = re.sub(r'\D', '', tel_match.group(0))
            if len(digits) == 10:
                profile["phone"] = f"+1{digits}"
            elif len(digits) == 11 and digits.startswith("1"):
                profile["phone"] = f"+{digits}"

        # Address: lines like "123 Main St, Dallas, TX 75201"
        addr_match = re.search(r'(\d{1,5}\s+[A-Z][a-zA-Z\s\.]+(?:St|Ave|Blvd|Rd|Dr|Ln|Way|Plaza|Court|Ct)[^\n,]*),\s*([A-Z][a-zA-Z\s]+),\s*([A-Z]{2})\s+(\d{5})', snap_text)
        if addr_match:
            profile["address"] = f"{addr_match.group(1).strip()}, {addr_match.group(2).strip()}, {addr_match.group(3)} {addr_match.group(4)}"
        else:
            # looser fallback
            addr_match = re.search(r'(\d{1,5}[^,\n]+,\s*[A-Z][a-zA-Z\s]+,\s*[A-Z]{2}\s+\d{5})', snap_text)
            if addr_match:
                profile["address"] = addr_match.group(1).strip()

        # Website: BBB sometimes links to the business website
        site_match = re.search(r'href="(https?://(?!bbb\.org|facebook\.com|instagram\.com|twitter\.com|linkedin\.com|youtube\.com)[^"]+)"', snap_text)
        if site_match:
            profile["website"] = site_match.group(1)

    finally:
        try:
            await scraper.client.request("DELETE", f"{CAMOFOX_URL}/tabs/{tab_id}", json={"userId": USER_ID})
        except Exception:
            pass

    return profile


async def search_niche(niche: str, metro: str, max_profiles: int = 15, deep_scrape: bool = True) -> List[Dict]:
    """
    Search BBB for a niche in a metro. If deep_scrape=True, visits each
    profile to extract phone/address. max_profiles caps the deep scrape
    so we don't spend forever in camofox.
    """
    scraper = PredictiveCamofoxScraper()
    profiles = await _search_bbb(scraper, niche, metro)
    if not profiles:
        return []

    if not deep_scrape:
        return profiles

    # Deep-scrape up to max_profiles
    out = []
    for i, p in enumerate(profiles[:max_profiles]):
        try:
            p2 = await _scrape_profile(scraper, p)
        except Exception as e:
            log.warning(f"[bbb] profile scrape error: {e}")
            p2 = p
        out.append(p2)
        # Small delay between tabs to avoid overwhelming camofox pool
        await asyncio.sleep(0.3)
    # Fill remaining with shallow entries
    out.extend(profiles[max_profiles:])
    return out


# CLI: python bbb_search.py <niche> <metro>
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    niche = sys.argv[1] if len(sys.argv) > 1 else "roofing"
    metro = sys.argv[2] if len(sys.argv) > 2 else "Dallas-Fort Worth"
    max_n = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    results = asyncio.run(search_niche(niche, metro, max_profiles=max_n, deep_scrape=True))
    print(f"\n=== BBB RESULTS ({niche} in {metro}) ===")
    for r in results:
        print(f"  {r.get('name','?')[:40]:42}  phone={r.get('phone','-')}  addr={r.get('address','-')[:50]}")