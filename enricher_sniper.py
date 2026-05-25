import os
import re
import json
import asyncio
import httpx
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote

# ---------- Config ----------
GOOGLE_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
GOOGLE_KG_KEY = os.environ.get("GOOGLE_KG_API_KEY", GOOGLE_KEY)   # reuses Maps key if KG enabled on it
USER_AGENT = "EmpireAI-RevenuePulse/2.0 (flavag83@gmail.com)"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org"
GOOGLE_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
WIKIDATA_URL = "https://query.wikidata.org/sparql"
USPTO_URL = "https://tsdrapi.uspto.gov/ts/cd/casestatus"
GOOGLE_KG_URL = "https://kgsearch.googleapis.com/v1/entities:search"
TX_SOS_URL = "https://comptroller.texas.gov/taxes/franchise/account-status/search"

# Cache SEC company list for the whole run
_sec_cache: Optional[Dict] = None


# ---------- Google Places ----------
async def google_places_search(
    client: httpx.AsyncClient, lat: float, lon: float, radius_m: int = 8000
) -> List[Dict]:
    if not GOOGLE_KEY:
        print("[Google] Skipped — no GOOGLE_MAPS_API_KEY")
        return []

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,places.location,"
            "places.nationalPhoneNumber,places.websiteUri,places.businessStatus,places.types"
        ),
    }
    leads: List[Dict] = []
    for query in ["warehouse", "distribution center", "logistics center", "cold storage", "fulfillment center"]:
        body = {
            "textQuery": query,
            "locationBias": {
                "circle": {"center": {"latitude": lat, "longitude": lon}, "radius": radius_m}
            },
            "maxResultCount": 20,
        }
        try:
            r = await client.post(GOOGLE_TEXT_URL, headers=headers, json=body)
            r.raise_for_status()
            for p in r.json().get("places", []):
                addr = p.get("formattedAddress", "")
                leads.append({
                    "source": "google",
                    "external_id": p.get("id"),
                    "name": p.get("displayName", {}).get("text"),
                    "address": addr,
                    "lat": p.get("location", {}).get("latitude"),
                    "lon": p.get("location", {}).get("longitude"),
                    "phone": p.get("nationalPhoneNumber"),
                    "website": p.get("websiteUri"),
                    "business_status": p.get("businessStatus"),
                    "types": p.get("types", []),
                    "state": _extract_state(addr),
                    "search_query": query,
                })
        except httpx.HTTPError as e:
            print(f"[Google] {query} failed: {e}")
    return leads


def _extract_state(address: Optional[str]) -> Optional[str]:
    """Pull 2-letter US state code from a formatted address."""
    if not address:
        return None
    m = re.search(r",\s*([A-Z]{2})\s+\d{5}", address)
    return m.group(1) if m else None


# ---------- OSM Overpass ----------
async def overpass_search(
    client: httpx.AsyncClient, south: float, west: float, north: float, east: float
) -> List[Dict]:
    query = f"""
    [out:json][timeout:25];
    (
      node["building"~"warehouse|industrial"]({south},{west},{north},{east});
      way["building"~"warehouse|industrial"]({south},{west},{north},{east});
      node["landuse"="industrial"]({south},{west},{north},{east});
      way["landuse"="industrial"]({south},{west},{north},{east});
    );
    out center tags;
    """
    try:
        r = await client.post(OVERPASS_URL, data={"data": query})
        r.raise_for_status()
        elements = r.json().get("elements", [])
    except httpx.HTTPError as e:
        print(f"[Overpass] failed: {e}")
        return []

    leads = []
    for el in elements:
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center", {})
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue

        street_parts = [tags.get("addr:housenumber"), tags.get("addr:street")]
        street = " ".join(p for p in street_parts if p) or None
        full_addr = ", ".join(p for p in [street, tags.get("addr:city"), tags.get("addr:state")] if p) or None

        leads.append({
            "source": "osm",
            "external_id": f"{el['type']}/{el['id']}",
            "name": tags.get("name") or tags.get("operator") or "Unnamed industrial site",
            "address": full_addr,
            "lat": lat,
            "lon": lon,
            "state": tags.get("addr:state"),
            "operator": tags.get("operator"),
            "building": tags.get("building"),
            "landuse": tags.get("landuse"),
            "needs_reverse_geocode": full_addr is None,
        })
    return leads


# ---------- Nominatim ----------
class NominatimLimiter:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()
            delta = 1.1 - (now - self._last)
            if delta > 0:
                await asyncio.sleep(delta)
            self._last = asyncio.get_event_loop().time()


async def nominatim_reverse(client: httpx.AsyncClient, limiter: NominatimLimiter, lat: float, lon: float) -> Optional[Dict]:
    await limiter.wait()
    params = {"lat": lat, "lon": lon, "format": "jsonv2", "addressdetails": 1, "zoom": 18}
    try:
        r = await client.get(f"{NOMINATIM_URL}/reverse", params=params)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return None
        a = data.get("address", {})
        # State name → 2-letter code
        state_full = a.get("state", "")
        state_code = _STATE_NAMES.get(state_full)
        return {
            "address": data.get("display_name"),
            "city": a.get("city") or a.get("town") or a.get("village"),
            "state": state_code or state_full,
            "postcode": a.get("postcode"),
        }
    except httpx.HTTPError:
        return None


_STATE_NAMES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
    "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


async def enrich_osm_addresses(client: httpx.AsyncClient, leads: List[Dict]) -> None:
    limiter = NominatimLimiter()
    for lead in leads:
        if lead.get("source") == "osm" and lead.get("needs_reverse_geocode"):
            enriched = await nominatim_reverse(client, limiter, lead["lat"], lead["lon"])
            if enriched:
                lead["address"] = enriched["address"]
                lead["state"] = enriched["state"] or lead.get("state")
                lead["city"] = enriched["city"]
                lead["postcode"] = enriched["postcode"]


# ---------- SEC EDGAR ----------
async def _load_sec_cache(client: httpx.AsyncClient) -> Dict:
    global _sec_cache
    if _sec_cache is not None:
        return _sec_cache
    try:
        r = await client.get(SEC_TICKERS_URL)
        r.raise_for_status()
        _sec_cache = r.json()
    except httpx.HTTPError:
        _sec_cache = {}
    return _sec_cache


async def sec_match(client: httpx.AsyncClient, name: str) -> Optional[Dict]:
    if not name:
        return None
    companies = await _load_sec_cache(client)
    name_norm = re.sub(r"[^a-z0-9 ]", "", name.lower())
    for entry in companies.values():
        title_norm = re.sub(r"[^a-z0-9 ]", "", entry["title"].lower())
        if name_norm in title_norm or title_norm in name_norm:
            cik = str(entry["cik_str"]).zfill(10)
            return {
                "source": "sec_edgar",
                "entity_name": entry["title"],
                "ticker": entry["ticker"],
                "cik": cik,
                "filings_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
            }
    return None


# ---------- Wikidata ----------
async def wikidata_match(client: httpx.AsyncClient, name: str) -> Optional[Dict]:
    if not name:
        return None
    # Escape quotes for SPARQL
    safe_name = name.replace('"', '\\"')
    query = f"""
    SELECT ?company ?companyLabel ?hqLabel ?websiteUrl ?ceoLabel WHERE {{
      ?company rdfs:label "{safe_name}"@en;
               wdt:P31/wdt:P279* wd:Q4830453.
      OPTIONAL {{ ?company wdt:P159 ?hq. }}
      OPTIONAL {{ ?company wdt:P856 ?websiteUrl. }}
      OPTIONAL {{ ?company wdt:P169 ?ceo. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 1
    """
    try:
        r = await client.get(WIKIDATA_URL, params={"query": query, "format": "json"})
        r.raise_for_status()
        bindings = r.json().get("results", {}).get("bindings", [])
        if not bindings:
            return None
        b = bindings[0]
        return {
            "source": "wikidata",
            "entity_name": b.get("companyLabel", {}).get("value"),
            "wikidata_id": b.get("company", {}).get("value", "").split("/")[-1],
            "headquarters": b.get("hqLabel", {}).get("value"),
            "website": b.get("websiteUrl", {}).get("value"),
            "ceo": b.get("ceoLabel", {}).get("value"),
        }
    except httpx.HTTPError:
        return None


# ---------- Google Knowledge Graph ----------
async def kg_match(client: httpx.AsyncClient, name: str) -> Optional[Dict]:
    if not name or not GOOGLE_KG_KEY:
        return None
    params = {
        "query": name,
        "key": GOOGLE_KG_KEY,
        "limit": 1,
        "types": "Corporation",
    }
    try:
        r = await client.get(GOOGLE_KG_URL, params=params)
        r.raise_for_status()
        items = r.json().get("itemListElement", [])
        if not items:
            return None
        result = items[0]["result"]
        return {
            "source": "google_kg",
            "entity_name": result.get("name"),
            "kg_id": result.get("@id"),
            "description": result.get("description"),
            "detailed_description": result.get("detailedDescription", {}).get("articleBody"),
            "url": result.get("url"),
        }
    except httpx.HTTPError:
        return None


# ---------- USPTO Trademark ----------
async def uspto_match(client: httpx.AsyncClient, name: str) -> Optional[Dict]:
    """USPTO Trademark Status & Document Retrieval — surfaces brand owner."""
    if not name:
        return None
    try:
        r = await client.get(
            f"{USPTO_URL}",
            params={"searchText": name},
            headers={"USPTO-API-KEY": ""},  # public read works without key for basic search
        )
        if r.status_code == 200 and r.text.strip():
            # USPTO returns XML by default — minimal parse
            owner_match = re.search(r"<OwnerName>([^<]+)</OwnerName>", r.text)
            mark_match = re.search(r"<MarkVerbalElementText>([^<]+)</MarkVerbalElementText>", r.text)
            if owner_match:
                return {
                    "source": "uspto",
                    "trademark_owner": owner_match.group(1),
                    "mark_text": mark_match.group(1) if mark_match else None,
                }
    except httpx.HTTPError:
        pass
    return None


# ---------- Texas Secretary of State / Comptroller ----------
async def texas_sos_match(client: httpx.AsyncClient, name: str) -> Optional[Dict]:
    """
    Texas Comptroller Franchise Tax Account Status search.
    Returns entity name, taxpayer number, status, registered agent if available.
    Free, public, no key.
    """
    if not name:
        return None
    try:
        r = await client.get(
            TX_SOS_URL,
            params={"Submit": "Search", "searchValue": name, "Page": "taxpayer"},
            timeout=20.0,
        )
        if r.status_code != 200:
            return None
        html = r.text

        # Parse first result row
        row_match = re.search(
            r'<tr[^>]*>\s*<td[^>]*>\s*<a[^>]*>([^<]+)</a>.*?'
            r'<td[^>]*>([^<]+)</td>.*?'
            r'<td[^>]*>([^<]+)</td>',
            html, re.DOTALL
        )
        if not row_match:
            return None

        return {
            "source": "tx_sos",
            "entity_name": row_match.group(1).strip(),
            "taxpayer_number": row_match.group(2).strip(),
            "status": row_match.group(3).strip(),
        }
    except httpx.HTTPError:
        return None


# ---------- Master entity match: chain all free sources ----------
async def entity_match(client: httpx.AsyncClient, lead: Dict) -> Optional[Dict]:
    """Try every free source in priority order. Merge richest data."""
    name = lead.get("name")
    state = lead.get("state")

    sources = []
    # SEC first — fastest, highest signal for public companies
    sec = await sec_match(client, name)
    if sec:
        sources.append(sec)

    # Wikidata for known private companies
    wd = await wikidata_match(client, name)
    if wd:
        sources.append(wd)

    # Google Knowledge Graph as cross-check / fallback
    kg = await kg_match(client, name)
    if kg:
        sources.append(kg)

    # USPTO for brand → owner mapping
    uspto = await uspto_match(client, name)
    if uspto:
        sources.append(uspto)

    # Texas SoS for TX leads specifically
    if state == "TX":
        tx = await texas_sos_match(client, name)
        if tx:
            sources.append(tx)

    if not sources:
        return None

    merged = {"sources_matched": [s["source"] for s in sources]}
    for s in sources:
        for k, v in s.items():
            if v and k != "source" and not merged.get(k):
                merged[k] = v
    return merged


# ---------- Dedup ----------
def dedup_leads(leads: List[Dict]) -> List[Dict]:
    rank = {"google": 0, "osm": 1}

    def key(l):
        lat_g = round(l["lat"], 3) if l.get("lat") else None
        lon_g = round(l["lon"], 3) if l.get("lon") else None
        n = (l.get("name") or "").lower().split()[0] if l.get("name") else ""
        return (lat_g, lon_g, n)

    merged: Dict[Tuple, Dict] = {}
    for l in leads:
        if not l.get("lat") or not l.get("lon"):
            continue
        k = key(l)
        existing = merged.get(k)
        if not existing:
            merged[k] = l
        elif rank.get(l["source"], 99) < rank.get(existing["source"], 99):
            merged[k] = {**existing, **{kk: vv for kk, vv in l.items() if vv}}
        else:
            for field, value in l.items():
                if value and not existing.get(field):
                    existing[field] = value
    return list(merged.values())


# ---------- Master pipeline ----------
async def find_leads_in_storm_zone(
    center_lat: float, center_lon: float, bbox: Tuple[float, float, float, float]
) -> List[Dict]:
    south, west, north, east = bbox
    async with httpx.AsyncClient(timeout=60.0, headers={"User-Agent": USER_AGENT}) as client:
        google_task = google_places_search(client, center_lat, center_lon)
        osm_task = overpass_search(client, south, west, north, east)
        google_leads, osm_leads = await asyncio.gather(google_task, osm_task)
        print(f"[Pulse] Raw — Google: {len(google_leads)}, OSM: {len(osm_leads)}")

        # Filter OSM: keep all named hits + sample of 50 unnamed (Nominatim is slow)
        named_osm = [l for l in osm_leads if l.get("name") and not l["name"].startswith("Unnamed")]
        unnamed_osm = [l for l in osm_leads if not l.get("name") or l["name"].startswith("Unnamed")][:50]
        osm_leads = named_osm + unnamed_osm
        print(f"[Pulse] OSM filtered to {len(osm_leads)} (named + 50 unnamed sample)")
        all_leads = google_leads + osm_leads
        await enrich_osm_addresses(client, all_leads)
        deduped = dedup_leads(all_leads)
        print(f"[Pulse] After dedup: {len(deduped)}")

        # Entity-match top named leads
        named = [l for l in deduped if l.get("name") and not l["name"].startswith("Unnamed")][:25]
        for lead in named:
            entity = await entity_match(client, lead)
            if entity:
                lead["entity"] = entity
            await asyncio.sleep(0.4)  # gentle on free APIs

    return deduped


# ---------- Entry point ----------
if __name__ == "__main__":
    leads = asyncio.run(find_leads_in_storm_zone(
        center_lat=32.78, center_lon=-96.90,
        bbox=(32.65, -97.10, 32.95, -96.70),
    ))
    print(f"\n=== {len(leads)} FINAL LEADS ===\n")
    for l in leads[:15]:
        print(f"[{l['source']}] {l['name']}")
        print(f"   {l.get('address') or '(no address)'}")
        if l.get("phone"):    print(f"   📞 {l['phone']}")
        if l.get("website"):  print(f"   🌐 {l['website']}")
        if l.get("entity"):
            e = l["entity"]
            srcs = ", ".join(e.get("sources_matched", []))
            print(f"   🏢 {e.get('entity_name')}  [{srcs}]")
            if e.get("ticker"):           print(f"      Ticker: {e['ticker']}")
            if e.get("taxpayer_number"):  print(f"      TX#: {e['taxpayer_number']}")
            if e.get("ceo"):              print(f"      CEO: {e['ceo']}")
        print()
