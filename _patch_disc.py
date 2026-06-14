#!/usr/bin/env python3
"""replace the DDG-based search with Google Places text search.
this is a more reliable, free-tier-friendly backend (we have the key).
the existing enricher_sniper.py uses the same pattern."""
import os, sys
from pathlib import Path
REPO = Path("/root/empire-v49")
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))
from dotenv import load_dotenv
load_dotenv("/root/.env")
p = Path("/root/empire-v49/agents/contact_discovery/discovery.py")
src = p.read_text()

old = '''def _search_duckduckgo(query: str, max_results: int = 3) -> list:
    """Use DuckDuckGo's HTML search (no API key needed) to get results.
    Returns a list of (title, snippet, url) tuples.
    Falls back silently on any error."""
    try:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({
            "q": query, "kl": "us-en"
        })
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Empire-AI/1.0 (contact-discovery)",
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode("utf-8", errors="ignore")
        # extract result snippets
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        urls = re.findall(r'class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL)
        out = []
        for i in range(min(max_results, len(snippets))):
            snip = re.sub(r"<[^>]+>", " ", snippets[i]).strip()
            url = urls[i].strip() if i < len(urls) else ""
            out.append((snip, url))
        return out
    except Exception as e:
        log.debug(f"ddg search failed: {e}")
        return []'''

new = '''def _google_places_search(query: str, lat: float = None, lon: float = None) -> list:
    """Use Google Places text search to find a business and its phone/website.
    Returns a list of dicts with {name, address, phone, website, types}.
    Requires GOOGLE_MAPS_API_KEY (free tier: 1000 calls/month).
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        log.debug("no GOOGLE_MAPS_API_KEY — skipping places search")
        return []
    try:
        body = {
            "textQuery": query,
            "maxResultCount": 5,
        }
        if lat is not None and lon is not None:
            body["locationBias"] = {
                "circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 8000}
            }
        req = urllib.request.Request(
            "https://places.googleapis.com/v1/places:searchText",
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.types",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        results = []
        for p in data.get("places", []):
            results.append({
                "name": p.get("displayName", {}).get("text", ""),
                "address": p.get("formattedAddress", ""),
                "phone": p.get("nationalPhoneNumber", ""),
                "website": p.get("websiteUri", ""),
                "types": p.get("types", []),
            })
        return results
    except Exception as e:
        log.debug(f"google places search failed: {e}")
        return []


def _scrape_contact_page(url: str) -> dict:
    """If Google Places gives us a website, scrape the contact/about page
    for a phone or email. Returns {phone, email}."""
    if not url:
        return {"phone": "", "email": ""}
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Empire-AI/1.0 (contact-discovery)",
            "Accept": "text/html",
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode("utf-8", errors="ignore")
        # try common contact-page patterns
        for contact_path in ["/contact", "/contact-us", "/contact.html", "/about", "/about-us", "/locations"]:
            req2 = urllib.request.Request(url.rstrip("/") + contact_path, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Empire-AI/1.0"})
            try:
                with urllib.request.urlopen(req2, timeout=6) as r2:
                    html += "\n" + r2.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
        phone = _clean_phone(PHONE_RE.search(html).group(1) if PHONE_RE.search(html) else "")
        m = EMAIL_RE.search(html)
        email = _normalize_email(m.group(0)) if m else ""
        return {"phone": phone, "email": email}
    except Exception as e:
        log.debug(f"scrape_contact_page failed for {url}: {e}")
        return {"phone": "", "email": ""}'''

src = src.replace(old, new)
p.write_text(src)
print("replaced _search_duckduckgo with _google_places_search + _scrape_contact_page")
print("now updating _discover_one to use them")
