#!/usr/bin/env python3
"""
EMPIRE V49 · ENRICH WITH MAPBOX REVERSE GEOCODING
===================================================
Reverse geocode remaining radar_targets with null city+state using
Mapbox's Geocoding API (100K free requests/month).

Resolves WKT POINT(lon lat) coordinates from the `location` column to
city and state, then updates the DB in batches.

Usage:
    python3 scripts/enrich_with_mapbox.py          # live
    python3 scripts/enrich_with_mapbox.py --dry-run # report only

Env vars:
    MAPBOX_TOKEN  — Mapbox access token (required)
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

log = logging.getLogger("enrich_mapbox")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

MAPBOX_BASE = "https://api.mapbox.com/geocoding/v5/mapbox.places"

# Concurrency: Mapbox free tier allows ~600 req/min, but we're well within
# that at 1,078 targets. Using 5 concurrent workers with a small delay.
CONCURRENCY = 5
REQUEST_DELAY = 0.05  # 50ms between requests


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _get_mapbox_token() -> str:
    """Get Mapbox access token from env."""
    token = os.getenv("MAPBOX_TOKEN", "")
    if not token:
        raise RuntimeError(
            "MAPBOX_TOKEN not set. Get one at https://account.mapbox.com/access-tokens/"
        )
    return token


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


async def _mapbox_reverse(
    client: httpx.AsyncClient, token: str, lon: float, lat: float
) -> Optional[Dict]:
    """Reverse geocode a coordinate pair via Mapbox.

    Returns: {"city": str, "state": str} or None on failure.

    Mapbox response shape:
    {
      "features": [{
        "place_type": ["place"],
        "text": "Fort Worth",           # city name
        "context": [
          {"id": "region.123", "short_code": "US-TX", "text": "Texas"},
          ...
        ]
      }]
    }
    """
    url = f"{MAPBOX_BASE}/{lon},{lat}.json"
    params = {
        "access_token": token,
        "types": "place,region",
        "limit": 1,
        "language": "en",
    }
    try:
        r = await client.get(url, params=params, timeout=10)
        if r.status_code == 429:
            log.warning("Mapbox rate limited — consider reducing concurrency")
            return None
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])
        if not features:
            return None

        city = None
        state = None

        for feat in features:
            types = feat.get("place_type", [])
            if "place" in types:
                city = feat.get("text", "")
            if "region" in types:
                short_code = feat.get("short_code", "") or ""
                if short_code.startswith("US-"):
                    state = short_code[3:]  # "US-TX" → "TX"
                else:
                    state = feat.get("text", "")[:2].upper()

        # If city and state came in separate features, combine them
        if not city or not state:
            # Try extracting from context
            for feat in features:
                if not city:
                    city = feat.get("text", "")
                ctx = feat.get("context", [])
                for c in ctx:
                    cid = c.get("id", "")
                    if cid.startswith("region."):
                        sc = c.get("short_code", "")
                        if sc.startswith("US-"):
                            state = sc[3:]
                    if cid.startswith("place.") and not city:
                        city = c.get("text", "")

        if city and state:
            return {"city": city, "state": state}

        return None
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        log.debug(f"Mapbox reverse geocode failed ({lon},{lat}): {e}")
        return None


async def run_enrichment(dry_run: bool = False) -> dict:
    """Main enrichment pipeline using Mapbox."""
    sb = _sb()
    token = _get_mapbox_token()
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
    to_geocode: List[Tuple[str, float, float]] = []  # (id, lon, lat)
    for row in all_rows:
        tid = row["id"]
        coords = _parse_wkt_point(row.get("location"))
        if coords:
            lon, lat = coords
            to_geocode.append((tid, lon, lat))

    log.info(
        f"Targets with location coordinates: {len(to_geocode)} / {total}"
    )

    if not to_geocode:
        log.info("No targets with parseable location data — nothing to do")
        return {
            "total_targets": total,
            "resolved": 0,
            "unresolved": total,
            "note": "no targets with location data",
        }

    # ── 3. Reverse geocode via Mapbox ────────────────────────────────
    sem = asyncio.Semaphore(CONCURRENCY)
    results: Dict[str, Tuple[str, str]] = {}  # id -> (city, state)

    async def _geocode_one(tid: str, lon: float, lat: float, client: httpx.AsyncClient):
        async with sem:
            await asyncio.sleep(REQUEST_DELAY)
            result = await _mapbox_reverse(client, token, lon, lat)
            if result:
                return tid, result["city"], result["state"]
            return tid, None, None

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [_geocode_one(tid, lon, lat, client) for tid, lon, lat in to_geocode]
        completed = 0
        for coro in asyncio.as_completed(tasks):
            tid, city, state = await coro
            if city and state:
                results[tid] = (city, state)
            completed += 1
            if completed % 200 == 0 or completed == len(tasks):
                log.info(
                    f"  Geocoded {completed}/{len(tasks)}  "
                    f"resolved={len(results)}  "
                    f"({completed/len(tasks)*100:.0f}%)"
                )

    log.info(
        f"Mapbox geocoding complete: {len(results)} resolved / {len(to_geocode)} attempted"
    )

    # ── 4. Fetch remaining targets that have street addresses
    # but no location coords — we already resolved those tiers earlier.
    # This Mapbox pass is for the coords-only targets.
    # ── 5. Apply DB updates ───────────────────────────────────────────
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
            log.info(
                f"  WOULD UPDATE: {tid[:12]}  city={city:20s}  state={state}  "
                f"addr='{addr}'"
            )
            sample_count += 1
    else:
        items = list(results.items())
        for i in range(0, len(items), BATCH):
            batch = items[i : i + BATCH]
            for tid, (city, state) in batch:
                try:
                    sb.table("radar_targets").update(
                        {
                            "city": city,
                            "state": state,
                            "updated_at": now_iso,
                        }
                    ).eq("id", tid).execute()
                    updated += 1
                except Exception as e:
                    log.warning(f"Failed to update {tid[:12]}: {e}")
                    errors += 1
            if (i + BATCH) % 600 == 0 or (i + BATCH) >= len(items):
                log.info(f"  DB updates: {updated}/{len(results)}  errors={errors}")

        log.info(f"DB updates applied: {updated}  errors: {errors}")

    # ── 6. Summary ────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    summary = {
        "total_missing": total,
        "had_location_coords": len(to_geocode),
        "mapbox_resolved": len(results),
        "db_updated": updated,
        "db_errors": errors,
        "unresolved_remaining": total - len(results),
        "elapsed_seconds": round(elapsed, 1),
        "mapbox_token_configured": bool(token),
        "dry_run": dry_run,
    }

    log.info("=== MAPBOX ENRICHMENT SUMMARY ===")
    log.info(f"Total missing city+state:  {total}")
    log.info(f"Had location coords:       {len(to_geocode)}")
    log.info(f"Mapbox resolved:           {len(results)}")
    log.info(f"DB updated:                {updated}")
    log.info(f"Errors:                    {errors}")
    log.info(f"Still unresolved:          {total - len(results)}")
    log.info(f"Elapsed:                   {elapsed:.1f}s")

    return summary


def main():
    p = argparse.ArgumentParser(
        description="Reverse geocode remaining radar_targets via Mapbox"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report only — no DB writes (still calls Mapbox API for count)",
    )
    args = p.parse_args()

    result = asyncio.run(run_enrichment(dry_run=args.dry_run))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
