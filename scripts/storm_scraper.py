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
            notes           TEXT
        )
    """)
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


def match_zips(area_desc: str, target_zips: list[dict]) -> list[str]:
    """
    Naive match: does the area description string contain any of the target
    city names? NWS area_desc is usually a list of counties / regions, not
    zip codes, so we match by city for week 1. The zip column still records
    the zips we *would* check; this is a known limitation.
    """
    if not area_desc:
        return []
    haystack = area_desc.lower()
    matched = []
    for entry in target_zips:
        city = entry.get("city", "").lower()
        if city and city in haystack:
            matched.append(entry["zip"])
    return matched


def is_advisory(event_type: str) -> bool:
    """Skip pure advisories. Watches still pass through (they predate warnings)."""
    return any(kw in event_type for kw in ADVISORY_KEYWORDS if kw != "Watch")


# ── INGEST ──────────────────────────────────────────────────────────────
def ingest(conn: sqlite3.Connection, target_zips: list[dict]) -> tuple[int, int]:
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
        matched = match_zips(area_desc, target_zips)
        if not matched:
            continue  # We only care about alerts in our target zones

        # Build target_zips column (all zips for that city, in case a
        # single alert covers multiple zips in our config)
        zip_codes_json = json.dumps(
            sorted({z["zip"] for z in target_zips
                    if z.get("city", "").lower() in area_desc.lower()})
        )
        matched_json = json.dumps(sorted(matched))

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
    log.info(f"Loaded {len(target_zips)} target zips from {CONFIG_PATH}")

    conn = init_db()
    new_count, updated_count = ingest(conn, target_zips)

    elapsed = round(time.time() - start, 2)
    log.info(f"Done in {elapsed}s. new={new_count} updated={updated_count}")
    log.info(f"DB: {DB_PATH}")
    log.info("=" * 60)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
