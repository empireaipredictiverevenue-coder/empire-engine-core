#!/usr/bin/env python3
"""
EMPIRE V49 · ENRICH WITH NOMINATIM (1 REQ/SEC)
================================================
Reverse geocode remaining radar_targets with null city+state using
Nominatim (OpenStreetMap) at exactly 1 request per second to avoid
the 429 rate limit that the previous concurrent approach hit.

Usage:
    python3 scripts/enrich_with_nominatim.py          # live
    python3 scripts/enrich_with_nominatim.py --dry-run # report only

WARNING: At 1 req/sec, this will take ~18 minutes for 1,078 targets.
"""

import os
import sys
import json
import asyncio
import logging
import argparse
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

log = logging.getLogger("enrich_nominatim")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

NOMINATIM_URL = "https://nominatim.openstreetmap.org"

# Strict: 1 request per second (Nominatim's ToS limit for free tier)
REQUEST_DELAY = 1.0

# State name → abbreviation mapping
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


async def _nominatim_reverse(
    client: httpx.AsyncClient, lat: float, lon: float
) -> Optional[Dict]:
    """Reverse geocode via Nominatim at 1 req/sec."""
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
            headers={"User-Agent": "EmpireAI-Enrichment/1.0 (phil@empire-ai.co.uk)"},
        )
        if r.status_code == 429:
            log.warning("Nominatim 429 — backing off 60s then retrying once")
            await asyncio.sleep(60)
            r = await client.get(
                f"{NOMINATIM_URL}/reverse",
                params=params,
                headers={"User-Agent": "EmpireAI-Enrichment/1.0 (phil@empire-ai.co.uk)"},
            )
            if r.status_code == 429:
                log.warning("Nominatim 429 after backoff — giving up on this target")
                return None
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return None
        a = data.get("address", {})
        state_full = a.get("state", "")
        state_code = _STATE_NAMES.get(state_full, state_full[:2].upper())
        city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality")
        if city and state_code:
            return {"city": city, "state": state_code}
        return None
    except (httpx.HTTPError, json.JSONDecodeError):
        return None


async def run_enrichment(dry_run: bool = False) -> dict:
    """Nominatim enrichment pipeline at 1 req/sec."""
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
    log.info(f"Fetched {total} targets still missing city+state")

    # ── 2. Filter to those with parseable location data ──────────────
    to_geocode: List[Tuple[str, float, float]] = []
    for row in all_rows:
        tid = row["id"]
        coords = _parse_wkt_point(row.get("location"))
        if coords:
            lon, lat = coords
            to_geocode.append((tid, lon, lat))

    log.info(f"Targets with location coordinates: {len(to_geocode)} / {total}")

    if not to_geocode:
        return {"total_targets": total, "resolved": 0, "note": "no targets with location data"}

    # ── 3. Reverse geocode via Nominatim at 1 req/sec ────────────────
    results: Dict[str, Tuple[str, str]] = {}
    estimated_minutes = len(to_geocode) * REQUEST_DELAY / 60
    log.info(f"Starting Nominatim geocoding (~{estimated_minutes:.0f} minutes for {len(to_geocode)} targets)")

    async with httpx.AsyncClient(timeout=15) as client:
        for idx, (tid, lon, lat) in enumerate(to_geocode):
            result = await _nominatim_reverse(client, lat, lon)
            if result:
                results[tid] = (result["city"], result["state"])

            # 1 req/sec — sleep even if we skip (stays compliant with ToS)
            await asyncio.sleep(REQUEST_DELAY)

            # Progress every 100
            if (idx + 1) % 100 == 0:
                elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                rate = (idx + 1) / elapsed if elapsed > 0 else 0
                pct = (idx + 1) / len(to_geocode) * 100
                log.info(
                    f"  {idx+1}/{len(to_geocode)} ({pct:.0f}%)  "
                    f"resolved={len(results)}  "
                    f"rate={rate:.1f} req/s  "
                    f"elapsed={elapsed:.0f}s"
                )

    log.info(
        f"Nominatim complete: {len(results)} resolved / {len(to_geocode)} attempted"
    )

    # ── 4. Apply DB updates ───────────────────────────────────────────
    updated = 0
    errors = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    BATCH = 200

    if dry_run:
        log.info("DRY RUN — no DB writes")
        sample_count = 0
        for tid, (city, state) in results.items():
            if sample_count >= 20:
                break
            orig = next((r for r in all_rows if r["id"] == tid), {})
            addr = str(orig.get("address", ""))[:60]
            log.info(f"  WOULD UPDATE: {tid[:12]}  city={city:20s}  state={state}  addr='{addr}'")
            sample_count += 1
    else:
        items = list(results.items())
        for i in range(0, len(items), BATCH):
            batch = items[i : i + BATCH]
            for tid, (city, state) in batch:
                try:
                    sb.table("radar_targets").update(
                        {"city": city, "state": state, "updated_at": now_iso}
                    ).eq("id", tid).execute()
                    updated += 1
                except Exception as e:
                    log.warning(f"Failed to update {tid[:12]}: {e}")
                    errors += 1
            if (i + BATCH) % 600 == 0 or (i + BATCH) >= len(items):
                log.info(f"  DB updates: {updated}/{len(results)}  errors={errors}")

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    summary = {
        "total_missing": total,
        "had_location_coords": len(to_geocode),
        "nominatim_resolved": len(results),
        "db_updated": updated,
        "db_errors": errors,
        "unresolved_remaining": total - len(results),
        "elapsed_seconds": round(elapsed, 1),
        "dry_run": dry_run,
    }

    log.info("=== NOMINATIM ENRICHMENT SUMMARY ===")
    log.info(f"Total missing city+state:  {total}")
    log.info(f"Had location coords:       {len(to_geocode)}")
    log.info(f"Nominatim resolved:        {len(results)}")
    log.info(f"DB updated:                {updated}")
    log.info(f"Errors:                    {errors}")
    log.info(f"Still unresolved:          {total - len(results)}")
    log.info(f"Elapsed:                   {elapsed:.1f}s")

    return summary


def main():
    p = argparse.ArgumentParser(
        description="Reverse geocode remaining radar_targets via Nominatim (1 req/sec)"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report only — no DB writes",
    )
    args = p.parse_args()

    result = asyncio.run(run_enrichment(dry_run=args.dry_run))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
