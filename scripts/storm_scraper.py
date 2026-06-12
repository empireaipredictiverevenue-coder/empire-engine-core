"""
EMPIRE V49 · NWS STORM ALERT SCRAPER
=====================================
Polls the public National Weather Service active alerts feed
(api.weather.gov/alerts/active) and persists any alert whose
geographic area intersects one of the target zip codes in
config/target_zips.json into a local SQLite table for daily
human review.

Free, no API key, no paid subscription. Requires a User-Agent
header (NWS policy, see: https://api.weather.gov/contact).

Filters:
  - Only events with severity in {Severe, Extreme, Moderate} for
    the warning/emergency class (SVR, TOR, FFW, etc.). Advisory-
    level events are skipped to keep the review queue focused on
    real damage potential.
  - Dedup by event id (NWS-assigned). Re-pulling the same event
    updates the row, doesn't create a duplicate.

Output: /root/empire-v49/data/storm_alerts.sqlite
Logs:   /root/empire-v49/logs/storm_scraper.log
"""

import json
import logging
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────────────────────
ROOT = Path("/root/empire-v49")
CONFIG_PATH = ROOT / "config" / "target_zips.json"
DB_PATH = ROOT / "data" / "storm_alerts.sqlite"
LOG_PATH = ROOT / "logs" / "storm_scraper.log"

NWS_FEED = "https://api.weather.gov/alerts/active"
USER_AGENT = "(empire-v49-storm-scraper, ops@empire-ai.local)"

# Severity filter. Adjust if the queue is too noisy / too quiet.
ACCEPTED_SEVERITY = {"Extreme", "Severe", "Moderate"}
# We accept all event types except pure advisories.
ADVISORY_KEYWORDS = ("Advisory", "Watch", "Statement", "Air Quality")

# ── LOGGING ─────────────────────────────────────────────────────────────
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("storm_scraper")


# ── DB ──────────────────────────────────────────────────────────────────
def init_db() -> sqlite3.Connection:
    """Create the alerts table if it doesn't exist, return a connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS storm_alerts (
            event_id        TEXT PRIMARY KEY,
            event_type      TEXT NOT NULL,
            severity        TEXT,
            certainty       TEXT,
            urgency         TEXT,
            headline        TEXT,
            description     TEXT,
            area_desc       TEXT,
            effective       TEXT,
            expires         TEXT,
            sender          TEXT,
            zip_codes       TEXT,        -- JSON array, joined against target_zips
            matched_zips    TEXT,        -- JSON array of zips that hit
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'NEW',  -- NEW | VERIFIED | REJECTED
            notes           TEXT,
            processed       INTEGER NOT NULL DEFAULT 0    -- 0=unprocessed, 1=bridge has consumed it
        )
    """)
    # Migration: add processed column to pre-existing databases that
    # were created before this column existed.
    try:
        conn.execute("ALTER TABLE storm_alerts ADD COLUMN processed INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    return conn


# ── NWS FETCH ───────────────────────────────────────────────────────────
def fetch_alerts() -> list[dict]:
    """Fetch the active alerts feed. Returns the list of feature dicts."""
    req = urllib.request.Request(
        NWS_FEED,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/geo+json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            log.error(f"NWS returned status {resp.status}")
            return []
        body = json.loads(resp.read().decode("utf-8"))
    return body.get("features", [])


# ── ZIP MATCHING ────────────────────────────────────────────────────────
def load_target_zips() -> list[dict]:
    """Load target zip codes from config. Returns a list of dicts."""
    if not CONFIG_PATH.exists():
        log.warning(f"Config not found at {CONFIG_PATH}, using empty list")
        return []
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    return cfg.get("zips", [])


def build_ugc_index(target_zips: list[dict]) -> dict[str, list[str]]:
    """Build UGC code → [zip_code, ...] index for fast county-level matching.

    NWS alerts carry 'geocode.UGC' arrays with county codes like 'TXC113'.
    This index maps each UGC code to all target zip codes in that county,
    so an alert tagged for 'Dallas County' (TXC113) matches all Dallas zips
    even when individual zip codes aren't mentioned in the alert text.
    """
    ugc_index: dict[str, set[str]] = {}
    for entry in target_zips:
        ugc = entry.get("ugc", "")
        zip_code = entry.get("zip", "")
        if ugc and zip_code:
            ugc_index.setdefault(ugc, set()).add(zip_code)
    return {ugc: sorted(zips) for ugc, zips in ugc_index.items()}


def build_county_index(target_zips: list[dict]) -> dict[str, list[str]]:
    """Build county name → [zip_code, ...] index for county-name text matching.

    NWS areaDesc often contains strings like 'Dallas County' or
    'Harris County'. This index maps county names to their target zips
    so the scraper catches county-scoped alerts even when city/zip text
    isn't present.
    """
    county_index: dict[str, set[str]] = {}
    for entry in target_zips:
        county = entry.get("county", "")
        zip_code = entry.get("zip", "")
        if county and zip_code:
            key = f"{county} County"
            county_index.setdefault(key, set()).add(zip_code)
    return {cn: sorted(zips) for cn, zips in county_index.items()}


def match_zips(
    area_desc: str,
    target_zips: list[dict],
    description: str = "",
    ugc_codes: list[str] | None = None,
    ugc_index: dict[str, list[str]] | None = None,
    county_index: dict[str, list[str]] | None = None,
) -> list[str]:
    """
    Multi-pass match against NWS alert data. Priority order (widest → most specific):
      1. UGC county code match — alert geocode.UGC contains e.g. 'TXC113'
         → matches ALL zip codes in Dallas County (broad, reliable)
      2. County name match — areaDesc contains 'Dallas County'
         → matches all zips in that county (text-based fallback)
      3. City name match — areaDesc contains 'Dallas'
         → matches zips for that city
      4. Raw zip code match — alert text literally contains '75201'
         → highest-confidence, narrowest signal

    NWS area_desc is usually counties/regions, not zip codes, so UGC + county
    matching is the primary signal. Raw zip codes sometimes appear in the
    description body — this is a secondary, higher-confidence signal.
    """
    if not area_desc:
        return []
    haystack = (area_desc + " " + description).lower()
    matched: set[str] = set()

    # Pass 1: UGC code match (broadest, most reliable)
    if ugc_codes and ugc_index:
        for ugc in ugc_codes:
            zips = ugc_index.get(ugc)
            if zips:
                matched.update(zips)

    # Pass 2: County name match (e.g. "Dallas County")
    if county_index:
        for county_name, zips in county_index.items():
            if county_name.lower() in haystack:
                matched.update(zips)

    # Pass 3: City name match
    for entry in target_zips:
        city = entry.get("city", "").lower()
        zip_code = entry.get("zip", "")
        if city and city in haystack:
            matched.add(zip_code)

    # Pass 4: Raw zip code match (highest confidence)
    for entry in target_zips:
        zip_code = entry.get("zip", "")
        if zip_code and zip_code in haystack:
            matched.add(zip_code)

    return sorted(matched)


def is_advisory(event_type: str) -> bool:
    """Skip pure advisories. Watches still pass through (they predate warnings)."""
    return any(kw in event_type for kw in ADVISORY_KEYWORDS if kw != "Watch")


# ── INGEST ──────────────────────────────────────────────────────────────
def ingest(
    conn: sqlite3.Connection,
    target_zips: list[dict],
    ugc_index: dict[str, list[str]] | None = None,
    county_index: dict[str, list[str]] | None = None,
) -> tuple[int, int]:
    """
    Pull alerts, filter, match, upsert. Returns (new_count, updated_count).
    """
    features = fetch_alerts()
    log.info(f"Pulled {len(features)} active alerts from NWS")

    now = datetime.now(timezone.utc).isoformat()
    new_count = 0
    updated_count = 0

    for feat in features:
        props = feat.get("properties", {})
        event_id = props.get("@id") or feat.get("id")
        if not event_id:
            continue
        event_type = props.get("event", "") or ""
        severity = props.get("severity", "") or ""

        # Filter
        if is_advisory(event_type):
            continue
        if severity not in ACCEPTED_SEVERITY:
            continue

        area_desc = props.get("areaDesc", "") or ""
        description = props.get("description", "") or ""
        ugc_codes = (props.get("geocode") or {}).get("UGC") or []
        matched = match_zips(
            area_desc, target_zips, description,
            ugc_codes=ugc_codes,
            ugc_index=ugc_index,
            county_index=county_index,
        )
        if not matched:
            continue  # We only care about alerts in our target zones

        # Build target_zips column (all zips for that city, in case a
        # single alert covers multiple zips in our config). Uses the same
        # combined haystack as match_zips for consistency.
        # Build target_zips column: all zips that match on ANY criterion
        # (UGC, county, city, or raw zip).
        combined_text = (area_desc + " " + description).lower()
        all_zips: set[str] = set()
        # UGC match
        if ugc_codes and ugc_index:
            for ugc in ugc_codes:
                zips = ugc_index.get(ugc)
                if zips:
                    all_zips.update(zips)
        # County name match
        if county_index:
            for county_name, zips in county_index.items():
                if county_name.lower() in combined_text:
                    all_zips.update(zips)
        # City / raw zip match
        for z in target_zips:
            city = z.get("city", "").lower()
            zip_code = z.get("zip", "")
            if (city and city in combined_text) or (zip_code and zip_code in combined_text):
                all_zips.add(zip_code)
        zip_codes_json = json.dumps(sorted(all_zips))
        matched_json = json.dumps(matched)

        # Upsert
        existing = conn.execute(
            "SELECT 1 FROM storm_alerts WHERE event_id = ?", (event_id,)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE storm_alerts SET last_seen = ? WHERE event_id = ?
            """, (now, event_id))
            updated_count += 1
        else:
            conn.execute("""
                INSERT INTO storm_alerts (
                    event_id, event_type, severity, certainty, urgency,
                    headline, description, area_desc,
                    effective, expires, sender,
                    zip_codes, matched_zips, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id, event_type, severity,
                props.get("certainty", ""), props.get("urgency", ""),
                (props.get("headline") or "")[:500],
                (props.get("description") or "")[:4000],
                (area_desc)[:1000],
                props.get("effective", ""), props.get("expires", ""),
                props.get("senderName", ""),
                zip_codes_json, matched_json, now, now,
            ))
            new_count += 1

    conn.commit()
    return new_count, updated_count


# ── MAIN ────────────────────────────────────────────────────────────────
def main() -> int:
    log.info("=" * 60)
    log.info("NWS storm scraper starting")
    start = time.time()

    target_zips = load_target_zips()
    ugc_index = build_ugc_index(target_zips)
    county_index = build_county_index(target_zips)
    log.info(f"Loaded {len(target_zips)} target zips from {CONFIG_PATH}")
    log.info(f"UGC index: {len(ugc_index)} counties, County index: {len(county_index)} counties")

    conn = init_db()
    new_count, updated_count = ingest(conn, target_zips, ugc_index, county_index)

    elapsed = round(time.time() - start, 2)
    log.info(f"Done in {elapsed}s. new={new_count} updated={updated_count}")
    log.info(f"DB: {DB_PATH}")
    log.info("=" * 60)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
