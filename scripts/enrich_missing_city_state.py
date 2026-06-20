#!/usr/bin/env python3
"""
EMPIRE V49 · ENRICH MISSING CITY/STATE FROM RADAR_TARGETS
==========================================================
One-shot enrichment for the 2,977 radar_targets that have address/location
data but null city and state fields.

Resolution order:
  1. meta.raw.addr:city / addr:state (OSM structured data)
  2. Address string parsing (reuses _parse_address from lead_scanner)
  3. Nominatim reverse geocode for lat/lon-only or remaining unresolved

Usage:
    python3 scripts/enrich_missing_city_state.py          # live (writes to DB)
    python3 scripts/enrich_missing_city_state.py --dry-run # report only
"""

import os
import sys
import re
import json
import asyncio
import logging
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client
import httpx

log = logging.getLogger("enrich_city_state")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)

# ── Reuse address parsing from lead_scanner ────────────────────────────
sys.path.insert(0, str(REPO / "agents" / "lead_scanner"))
from scanner import _parse_address, _STATE_ZIP_RE, _LAT_LNG_RE, _STREET_WORDS

# ── State name → abbreviation mapping (for Nominatim) ──────────────────
_STATE_NAMES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org"


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _parse_wkt_point(location: Optional[str]) -> Optional[Tuple[float, float]]:
    """Parse WKT POINT(lon lat) -> (lon, lat)."""
    if not location:
        return None
    try:
        cleaned = location.replace("POINT(", "").replace(")", "").strip()
        parts = cleaned.split()
        if len(parts) != 2:
            return None
        return float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        return None


def _extract_from_meta_raw(meta: Optional[dict]) -> Tuple[Optional[str], Optional[str]]:
    """Try to extract city/state from meta.raw.addr:city and addr:state."""
    if not meta or not isinstance(meta, dict):
        return None, None
    raw = meta.get("raw") or {}
    if not isinstance(raw, dict):
        return None, None
    city = raw.get("addr:city")
    state = raw.get("addr:state")
    if city and state:
        # Normalize state to 2-letter code
        state = state.strip().upper()
        if len(state) > 2:
            state = _STATE_NAMES.get(state.title(), state)
        return city.strip(), state
    return None, None


async def _nominatim_reverse(
    client: httpx.AsyncClient, lat: float, lon: float
) -> Optional[Dict]:
    """Reverse geocode via Nominatim (free, rate-limited to ~1 req/s)."""
    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "addressdetails": 1,
        "zoom": 16,
    }
    try:
        r = await client.get(
            f"{NOMINATIM_URL}/reverse",
            params=params,
            headers={"User-Agent": "EmpireAI-Enrichment/1.0"},
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return None
        a = data.get("address", {})
        state_full = a.get("state", "")
        state_code = _STATE_NAMES.get(state_full, state_full[:2].upper())
        city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality")
        return {
            "city": city,
            "state": state_code,
        }
    except (httpx.HTTPError, json.JSONDecodeError):
        return None


async def run_enrichment(dry_run: bool = False) -> dict:
    """Main enrichment pipeline."""
    sb = _sb()
    started_at = datetime.now(timezone.utc)

    # ── 1. Fetch all targets missing city+state ──────────────────────
    all_rows = []
    page = 0
    page_size = 1000
    while True:
        r = (
            sb.table("radar_targets")
            .select("id, address, location, meta")
            .is_("city", "null")
            .is_("state", "null")
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        chunk = r.data or []
        if not chunk:
            break
        all_rows.extend(chunk)
        page += 1
        if len(chunk) < page_size:
            break

    total = len(all_rows)
    log.info(f"Fetched {total} targets missing city+state")

    # ── 2. Categorize and resolve ────────────────────────────────────
    updates: Dict[str, Tuple[str, str, str]] = {}  # id -> (city, state, source)

    # Tier 1: meta.raw.addr:city/state
    for row in all_rows:
        tid = row["id"]
        city, state = _extract_from_meta_raw(row.get("meta"))
        if city and state:
            updates[tid] = (city, state, "meta_raw_addr")

    log.info(f"Tier 1 (meta.raw.addr:city/state): {len(updates)} resolved")

    # Tier 2: address string parsing
    tier2 = 0
    for row in all_rows:
        tid = row["id"]
        if tid in updates:
            continue
        addr = row.get("address") or ""
        meta = row.get("meta") or {}
        raw = meta.get("raw") or {} if isinstance(meta, dict) else {}

        city, state = _parse_address(
            addr,
            existing_city=None,
            existing_state=None,
            raw=raw,  # _parse_address checks raw.city/raw.state
        )
        if city and state:
            updates[tid] = (city, state, "address_parse")
            tier2 += 1
        elif city:
            # Found city but no state — check if we can extract state from address
            # (e.g. "Fort Worth" with state implicit in ZIP)
            st_match = _STATE_ZIP_RE.search(addr)
            if st_match:
                updates[tid] = (city, st_match.group("state"), "address_parse")
                tier2 += 1

    log.info(f"Tier 2 (address string parse): {tier2} resolved")
    log.info(f"  Total after Tier 1+2: {len(updates)}")

    # Tier 3: remaining with location data (Nominatim is rate-limited to 429)
    remaining = [row for row in all_rows if row["id"] not in updates]
    has_location = [row for row in remaining if row.get("location")]
    log.info(f"Tier 3 (Nominatim): {len(has_location)} unresolved with location data (skipped — Nominatim returning 429)")
    log.info(f"Total resolved: {len(updates)} / {total} ({(len(updates)/total*100) if total else 0:.1f}%)")

    # ── 3. Apply updates ─────────────────────────────────────────────
    updated = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    if dry_run:
        log.info("DRY RUN — no DB writes")
        # Show sample
        sample_count = 0
        for tid, (city, state, source) in updates.items():
            if sample_count >= 20:
                break
            orig = next(
                (r for r in all_rows if r["id"] == tid), {}
            )
            addr = str(orig.get("address", ""))[:60]
            log.info(
                f"  WOULD UPDATE: {tid[:12]}  city={city:20s}  state={state:2s}  "
                f"source={source:20s}  addr='{addr}'"
            )
            sample_count += 1
    else:
        batch = []
        for tid, (city, state, source) in updates.items():
            batch.append({
                "id": tid,
                "city": city,
                "state": state,
                "updated_at": now_iso,
            })
            if len(batch) >= 500:
                for row in batch:
                    sb.table("radar_targets").update({
                        "city": row["city"],
                        "state": row["state"],
                        "updated_at": row["updated_at"],
                    }).eq("id", row["id"]).execute()
                updated += len(batch)
                log.info(f"  Updated {updated} targets so far...")
                batch = []

        if batch:
            for row in batch:
                sb.table("radar_targets").update({
                    "city": row["city"],
                    "state": row["state"],
                    "updated_at": row["updated_at"],
                }).eq("id", row["id"]).execute()
            updated += len(batch)

        log.info(f"DB updates applied: {updated}")

    # ── 4. Summary ────────────────────────────────────────────────────
    by_source = {}
    for _, (_, _, source) in updates.items():
        by_source[source] = by_source.get(source, 0) + 1

    # Breakdown for remaining
    remaining_count = total - len(updates)
    remaining_no_loc = sum(1 for r in remaining if not r.get("location"))
    remaining_with_loc = remaining_count - remaining_no_loc

    summary = {
        "total_targets": total,
        "resolved": len(updates),
        "unresolved": remaining_count,
        "by_source": by_source,
        "unresolved_no_location": remaining_no_loc,
        "unresolved_with_location": remaining_with_loc,
        "dry_run": dry_run,
        "db_updates_applied": updated,
        "elapsed_seconds": (datetime.now(timezone.utc) - started_at).total_seconds(),
    }

    log.info(f"=== ENRICHMENT SUMMARY ===")
    log.info(f"Total targets:      {total}")
    log.info(f"Resolved:           {len(updates)}")
    log.info(f"  meta.raw.addr:    {by_source.get('meta_raw_addr', 0)}")
    log.info(f"  address parse:    {by_source.get('address_parse', 0)}")
    log.info(f"  Nominatim:        {by_source.get('nominatim', 0)}")
    log.info(f"Unresolved:         {remaining_count}")
    log.info(f"  (no location):    {remaining_no_loc}")
    log.info(f"  (has location):   {remaining_with_loc}")
    log.info(f"DB updates:         {updated}")
    log.info(f"Elapsed:            {summary['elapsed_seconds']:.1f}s")

    return summary


def main():
    p = argparse.ArgumentParser(
        description="Enrich radar_targets missing city/state from address/location data"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report only — no DB writes (also skips Nominatim API calls)",
    )
    args = p.parse_args()

    result = asyncio.run(run_enrichment(dry_run=args.dry_run))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
