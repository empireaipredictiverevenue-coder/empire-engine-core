"""
EMPIRE AI · MASTER PIPELINE V49
================================
The single-file weapon. Four phases:
  1. EXTRACT  — concurrent scrape with retries
  2. CLEAN    — dedup by phone, normalize
  3. RADAR    — wind + hail check via Open-Meteo
  4. VAULT    — CSV + Supabase + ntfy push

Run modes:
    python pipeline.py                  # Full pipeline
    python pipeline.py --dry-run        # Phases 1-3 only, no writes
    python pipeline.py --since-last     # Skip URLs already processed
    python pipeline.py --notify-only    # Only ntfy + Supabase, no CSV

Environment (all optional — degrades gracefully):
    EMPIRE_OUTPUT_PATH    where to write CSV (default: ./verified_storm_targets.csv)
    EMPIRE_INPUT_FILE     URL list file      (default: ./master_whales.txt)
    EMPIRE_STATE_FILE     processed-URL cache (default: ./.pipeline_state.json)
    EMPIRE_CONCURRENCY    parallel scrapes    (default: 8)
    EMPIRE_TIMEOUT        per-request seconds (default: 12)
    EMPIRE_MIN_WIND_KMH   global wind floor   (default: 40)
    EMPIRE_MIN_HAIL_CM    hail floor          (default: 1.0)
    SUPABASE_URL          Supabase project URL
    SUPABASE_SERVICE_KEY  Supabase service-role key
    NTFY_TOPIC            ntfy topic for alerts
    NTFY_TOKEN            ntfy auth token (optional)
"""

import os
import re
import json
import time
import asyncio
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
INPUT_FILE      = Path(os.environ.get("EMPIRE_INPUT_FILE", "master_whales.txt"))
OUTPUT_CSV      = Path(os.environ.get("EMPIRE_OUTPUT_PATH", "verified_storm_targets.csv"))
STATE_FILE      = Path(os.environ.get("EMPIRE_STATE_FILE", ".pipeline_state.json"))
CONCURRENCY     = int(os.environ.get("EMPIRE_CONCURRENCY", "8"))
TIMEOUT         = float(os.environ.get("EMPIRE_TIMEOUT", "12"))
MIN_WIND_KMH    = float(os.environ.get("EMPIRE_MIN_WIND_KMH", "40"))
MIN_HAIL_CM     = float(os.environ.get("EMPIRE_MIN_HAIL_CM", "1.0"))

SUPABASE_URL    = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY    = os.environ.get("SUPABASE_SERVICE_KEY", "")
NTFY_TOPIC      = os.environ.get("NTFY_TOPIC", "empire_private_alerts")
NTFY_TOKEN      = os.environ.get("NTFY_TOKEN", "")

UA = "Mozilla/5.0 (Empire-AI/1.0 · Storm Verification Engine)"
PHONE_RX = re.compile(r"\(?(\d{3})\)?[-.\s](\d{3})[-.\s](\d{4})")

# Per-city severity floors. Some cities are naturally windier — adjust the
# threshold so we don't waste calls on "ordinary" gusts.
CITY_GPS = {
    "Dallas":      {"lat": 32.7767, "lon": -96.7970, "wind_floor": 45},
    "Houston":     {"lat": 29.7604, "lon": -95.3698, "wind_floor": 60},
    "San Antonio": {"lat": 29.4241, "lon": -98.4936, "wind_floor": 45},
    "Austin":      {"lat": 30.2672, "lon": -97.7431, "wind_floor": 50},
    "Mobile":      {"lat": 30.6954, "lon": -88.0399, "wind_floor": 35},
    "Fort Worth":  {"lat": 32.7555, "lon": -97.3308, "wind_floor": 45},
    "Plano":       {"lat": 33.0198, "lon": -96.6989, "wind_floor": 45},
}

# Area code → city. Expanded coverage. Add new ones here.
AREA_CODE_MAP = {
    # Dallas / Fort Worth metro
    "214": "Dallas", "469": "Dallas", "972": "Dallas",
    "817": "Fort Worth", "682": "Fort Worth",
    "945": "Plano",
    # Houston metro
    "713": "Houston", "281": "Houston", "832": "Houston", "346": "Houston",
    # San Antonio
    "210": "San Antonio", "726": "San Antonio",
    # Austin
    "512": "Austin", "737": "Austin",
    # Mobile (AL)
    "251": "Mobile",
}


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s · %(levelname)s · %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("empire")


# ─────────────────────────────────────────────────────────────────────────────
# STATE CACHE — skip URLs we've already scraped successfully
# ─────────────────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"processed": [], "last_run": None}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"processed": [], "last_run": None}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.warning(f"State save failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 · EXTRACT — concurrent scrape with retries
# ─────────────────────────────────────────────────────────────────────────────
def normalize_phone(raw_match: re.Match) -> Optional[str]:
    """Build a clean 10-digit phone from a regex match. Drops obvious junk."""
    digits = raw_match.group(1) + raw_match.group(2) + raw_match.group(3)
    if len(digits) != 10:
        return None
    # Reject obvious garbage
    if digits in {"0000000000", "1234567890", "1111111111"}:
        return None
    if digits.startswith("0") or digits.startswith("1"):
        return None
    return digits


def city_from_area_code(phone: str) -> str:
    """Map area code to known city. 'Unknown' if not in our coverage."""
    if not phone or len(phone) < 3:
        return "Unknown"
    return AREA_CODE_MAP.get(phone[:3], "Unknown")


def extract_company_name(soup: BeautifulSoup, url: str) -> str:
    """Best-effort company name from <title> with fallback to og:site_name."""
    try:
        if soup.title and soup.title.string:
            title = soup.title.string
            # Take the part before common separators
            for sep in ("|", "-", "—", "·", "::", "  "):
                if sep in title:
                    title = title.split(sep)[0]
                    break
            title = title.strip()
            if title and len(title) < 100:
                return title
    except Exception:
        pass

    # Fallback to og:site_name meta
    try:
        og = soup.find("meta", property="og:site_name")
        if og and og.get("content"):
            return og["content"].strip()
    except Exception:
        pass

    # Last resort: domain
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return "Unknown"


async def scrape_one(client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore) -> Optional[dict]:
    """Scrape one URL with retries. Returns lead dict or None."""
    async with semaphore:
        for attempt in (1, 2, 3):
            try:
                r = await client.get(url, follow_redirects=True)
                if r.status_code != 200:
                    if attempt < 3:
                        await asyncio.sleep(0.8 * attempt)
                        continue
                    return None

                soup = BeautifulSoup(r.text, "html.parser")
                title = extract_company_name(soup, url)

                # Find the FIRST valid phone (typically the main line, top of page)
                phone = None
                for match in PHONE_RX.finditer(r.text):
                    normalized = normalize_phone(match)
                    if normalized:
                        phone = normalized
                        break

                if not phone:
                    return None

                city = city_from_area_code(phone)

                # Also grab a contact email if it's right there — cheap win
                email = None
                email_match = re.search(
                    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", r.text
                )
                if email_match:
                    candidate = email_match.group(0)
                    # Skip obvious junk
                    if not any(j in candidate.lower() for j in
                               ("example.com", "sentry", "wixpress", "noreply")):
                        email = candidate.lower()

                return {
                    "Company Name": title,
                    "Phone":        phone,
                    "City":         city,
                    "URL":          url,
                    "Email":        email or "",
                }
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt < 3:
                    await asyncio.sleep(0.8 * attempt)
                    continue
                return None
            except Exception as e:
                log.debug(f"Scrape error {url}: {e}")
                return None
        return None


async def phase_1_extract(urls: list[str]) -> list[dict]:
    """Concurrently scrape all URLs. Returns list of lead dicts."""
    log.info(f"━━━ PHASE 1 · EXTRACTING {len(urls)} WHALES (concurrency={CONCURRENCY}) ━━━")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    headers   = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

    raw_leads: list[dict] = []
    async with httpx.AsyncClient(headers=headers, timeout=TIMEOUT) as client:
        tasks = [scrape_one(client, url, semaphore) for url in urls]
        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed += 1
            if result:
                raw_leads.append(result)
                log.info(f"  [{completed}/{len(urls)}] ✓ {result['Company Name'][:40]} · {result['Phone']} · {result['City']}")
            else:
                if completed % 5 == 0:
                    log.info(f"  [{completed}/{len(urls)}] progress · {len(raw_leads)} leads so far")

    log.info(f"Phase 1 complete: {len(raw_leads)} raw leads from {len(urls)} URLs")
    return raw_leads


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 · CLEAN — dedup by phone
# ─────────────────────────────────────────────────────────────────────────────
def phase_2_clean(raw_leads: list[dict]) -> pd.DataFrame:
    log.info("━━━ PHASE 2 · CLEANING DUPLICATES ━━━")
    if not raw_leads:
        return pd.DataFrame()
    df = pd.DataFrame(raw_leads)
    before = len(df)
    df = df.drop_duplicates(subset=["Phone"]).reset_index(drop=True)
    log.info(f"Deduped: {before} → {len(df)} unique whales")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 · RADAR — wind + hail check via Open-Meteo
# ─────────────────────────────────────────────────────────────────────────────
async def check_weather(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    """Pull 3-day wind + hail history. Returns max values."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=wind_gusts_10m_max,precipitation_hours"
        f"&hourly=wind_gusts_10m,precipitation"
        f"&past_days=3&forecast_days=0"
        f"&timezone=America%2FChicago"
    )
    try:
        r = await client.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        daily = data.get("daily", {})
        hourly = data.get("hourly", {})

        winds = [w for w in daily.get("wind_gusts_10m_max", []) if w is not None]
        max_wind = max(winds) if winds else 0

        # Hail proxy: heavy precipitation hours during high wind (storm cells)
        precip = [p for p in hourly.get("precipitation", []) if p is not None]
        max_precip_mm = max(precip) if precip else 0
        # Open-Meteo doesn't directly return hail size; we approximate by
        # precipitation intensity during high-wind periods. >5mm/hr + high wind
        # is a strong hail-storm signal.
        likely_hail = (max_precip_mm > 5 and max_wind > 50)

        return {
            "max_wind_kmh": round(max_wind, 1),
            "max_precip_mm": round(max_precip_mm, 1),
            "likely_hail": likely_hail,
        }
    except Exception as e:
        log.debug(f"Weather fetch failed for {lat},{lon}: {e}")
        return {"max_wind_kmh": 0, "max_precip_mm": 0, "likely_hail": False}


async def phase_3_radar(df: pd.DataFrame) -> list[dict]:
    """For each lead, check weather. Verified hits returned."""
    log.info("━━━ PHASE 3 · THE STORM RADAR ━━━")
    verified: list[dict] = []
    if df.empty:
        return verified

    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        # Cache weather by city — many leads share the same city
        weather_cache: dict[str, dict] = {}

        for _, row in df.iterrows():
            city = row["City"]
            if city not in CITY_GPS:
                continue

            if city not in weather_cache:
                gps = CITY_GPS[city]
                weather_cache[city] = await check_weather(client, gps["lat"], gps["lon"])
                await asyncio.sleep(0.3)  # be polite to Open-Meteo

            w = weather_cache[city]
            city_floor = CITY_GPS[city].get("wind_floor", MIN_WIND_KMH)

            wind_hit = w["max_wind_kmh"] >= city_floor
            hail_hit = w["likely_hail"]

            if wind_hit or hail_hit:
                verdict_parts = []
                if wind_hit:
                    verdict_parts.append(f"wind {w['max_wind_kmh']} km/h")
                if hail_hit:
                    verdict_parts.append(f"likely hail (precip {w['max_precip_mm']}mm)")

                lead = dict(row)
                lead["Storm_Status"]   = "VERIFIED HIT"
                lead["Peak_Wind_KMH"]  = w["max_wind_kmh"]
                lead["Peak_Precip_MM"] = w["max_precip_mm"]
                lead["Likely_Hail"]    = hail_hit
                lead["Verdict"]        = " · ".join(verdict_parts)
                lead["Verified_At"]    = datetime.now(timezone.utc).isoformat()

                verified.append(lead)
                log.info(f"  🎯 LOCK · {lead['Company Name'][:40]} · {city} · {lead['Verdict']}")

    log.info(f"Phase 3 complete: {len(verified)} verified hits")
    return verified


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 · VAULT — CSV + Supabase + ntfy
# ─────────────────────────────────────────────────────────────────────────────
def push_to_supabase(verified: list[dict]) -> int:
    """Upsert verified leads into radar_targets. Returns rows written."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("Supabase not configured — skipping push")
        return 0
    try:
        from supabase import create_client
        db = create_client(SUPABASE_URL, SUPABASE_KEY)

        rows = []
        for lead in verified:
            city = lead.get("City", "Unknown")
            gps = CITY_GPS.get(city, {"lat": 0, "lon": 0})
            urgency = 10 if lead.get("Likely_Hail") else 7
            severity = "extreme" if lead.get("Likely_Hail") else "severe"

            rows.append({
                "address":         lead.get("Company Name", "")[:200],
                "phone":           lead.get("Phone"),
                "email":           lead.get("Email") or None,
                "source_url":      lead.get("URL"),
                "city":            city,
                "location":        f"POINT({gps['lon']} {gps['lat']})",
                "status":          "active",
                "damage_severity": severity,
                "urgency_score":   urgency,
                "meta": {
                    "source":         "empire_pipeline",
                    "peak_wind_kmh":  lead.get("Peak_Wind_KMH"),
                    "peak_precip_mm": lead.get("Peak_Precip_MM"),
                    "verdict":        lead.get("Verdict"),
                    "verified_at":    lead.get("Verified_At"),
                },
            })

        # Upsert by phone (assumes phone is a unique key on radar_targets)
        result = db.table("radar_targets").upsert(rows, on_conflict="phone").execute()
        n = len(result.data or [])
        log.info(f"Supabase: {n} rows upserted into radar_targets")
        return n
    except Exception as e:
        log.error(f"Supabase push failed: {e}")
        return 0


def push_to_ntfy(verified: list[dict]) -> bool:
    """Send a digest ntfy alert summarizing today's locks."""
    if not NTFY_TOPIC or not verified:
        return False
    try:
        import requests
        top = verified[:5]
        body = "\n".join(
            f"• {l['Company Name'][:30]} · {l['City']} · {l['Verdict']}"
            for l in top
        )
        if len(verified) > 5:
            body += f"\n+{len(verified) - 5} more locks"

        headers = {
            "Title": f"🎯 EMPIRE PIPELINE · {len(verified)} LOCKS",
            "Priority": "high",
            "Tags": "dart,fire",
        }
        if NTFY_TOKEN:
            headers["Authorization"] = f"Bearer {NTFY_TOKEN}"

        r = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=5,
        )
        log.info(f"Ntfy push: HTTP {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        log.warning(f"Ntfy push failed: {e}")
        return False


def phase_4_vault(verified: list[dict], dry_run: bool = False, notify_only: bool = False) -> None:
    log.info("━━━ PHASE 4 · SECURING THE VAULT ━━━")
    if not verified:
        log.info("No verified hits. Vault stays quiet.")
        return

    if dry_run:
        log.info(f"DRY RUN · would persist {len(verified)} verified hits")
        for v in verified:
            log.info(f"  · {v['Company Name']} · {v['City']} · {v['Verdict']}")
        return

    # Write CSV unless notify-only
    if not notify_only:
        try:
            OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(verified).to_csv(OUTPUT_CSV, index=False)
            log.info(f"CSV saved → {OUTPUT_CSV}")
        except Exception as e:
            log.error(f"CSV write failed: {e}")

    # Supabase push
    push_to_supabase(verified)

    # Ntfy digest
    push_to_ntfy(verified)


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────
async def run_pipeline(dry_run: bool = False, since_last: bool = False, notify_only: bool = False) -> None:
    started = time.time()

    if not INPUT_FILE.exists():
        log.error(f"Input file not found: {INPUT_FILE}")
        return

    # Load URLs
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        urls = sorted({line.strip() for line in f if "http" in line})

    if not urls:
        log.error("No URLs in input file.")
        return

    # Skip already-processed if requested
    state = load_state()
    if since_last:
        already = set(state.get("processed", []))
        urls = [u for u in urls if u not in already]
        log.info(f"--since-last: {len(urls)} new URLs to process")
        if not urls:
            log.info("All URLs already processed. Use without --since-last to re-run.")
            return

    # Phase 1
    raw = await phase_1_extract(urls)

    # Phase 2
    df = phase_2_clean(raw)

    # Phase 3
    verified = await phase_3_radar(df)

    # Phase 4
    phase_4_vault(verified, dry_run=dry_run, notify_only=notify_only)

    # Update state
    if not dry_run:
        state["processed"] = sorted(set(state.get("processed", []) + urls))
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        state["last_locks"] = len(verified)
        save_state(state)

    elapsed = time.time() - started
    log.info(f"━━━ PIPELINE COMPLETE · {elapsed:.1f}s · {len(verified)} locks ━━━")


def main():
    parser = argparse.ArgumentParser(description="Empire Master Pipeline")
    parser.add_argument("--dry-run",      action="store_true", help="Run phases 1-3 only, no writes")
    parser.add_argument("--since-last",   action="store_true", help="Skip URLs already processed")
    parser.add_argument("--notify-only",  action="store_true", help="Push to Supabase + ntfy but no CSV")
    args = parser.parse_args()

    asyncio.run(run_pipeline(
        dry_run=args.dry_run,
        since_last=args.since_last,
        notify_only=args.notify_only,
    ))


if __name__ == "__main__":
    main()
