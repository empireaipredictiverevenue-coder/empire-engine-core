#!/usr/bin/env python3
"""
EMPIRE V49 · ENRICH WITH GOOGLE MAPS REVERSE GEOCODING
========================================================
Reverse geocode remaining radar_targets with null city+state using
Google Maps Geocoding API. Free tier includes $200/mo credit —
~1,078 requests will cost ~$5.39, well within the free allowance.

Google Maps allows up to 50 req/sec, so this finishes in under 30s.

Usage:
    python3 scripts/enrich_with_google_maps.py          # live
    python3 scripts/enrich_with_google_maps.py --dry-run # report only

Env vars:
    GOOGLE_MAPS_API_KEY  — Google Maps API key (required)
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

log = logging.getLogger("enrich_google_maps")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

GOOGLE_MAPS_BASE = "https://maps.googleapis.com/maps/api/geocode/json"

# Google allows 50 req/sec — we use 10 concurrent workers with ~5ms delay.
# At 10 concurrency * (1000ms / 10 + 5ms) ≈ 100 req/sec, still safe.
CONCURRENCY = 10
REQUEST_DELAY = 0.01  # 10ms between requests


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _get_google_maps_key() -> str:
    """Get Google Maps API key from env."""
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY not set. Get one at "
            "https://console.cloud.google.com/apis/credentials"
        )
    return key


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


async def _google_maps_reverse(
    client: httpx.AsyncClient, api_key: str, lon: float, lat: float
) -> Optional[Dict]:
    """Reverse geocode a coordinate pair via Google Maps Geocoding API.

    Returns: {"city": str, "state": str} or None on failure.

    Google Maps response shape:
    {
      "results": [{
        "address_components": [
          {"long_name": "Fort Worth", "types": ["locality", "political"]},
          {"long_name": "Texas", "types": ["administrative_area_level_1", "political"]},
          {"long_name": "TX", "types": ["administrative_area_level_1", "political"]},
          ...
        ]
      }],
      "status": "OK"
    }
    """
    params = {
        "latlng": f"{lat},{lon}",
        "key": api_key,
        "language": "en",
    }
    try:
        r = await client.get(GOOGLE_MAPS_BASE, params=params, timeout=10)
        if r.status_code == 429:
            log.warning("Google Maps rate limited — consider reducing concurrency")
            return None
        if r.status_code == 403:
            log.warning(
                "Google Maps API returned 403 — API key may be restricted or "
                "Geocoding API not enabled. Enable at: "
                "https://console.cloud.google.com/apis/library/geocoding-backend.googleapis.com"
            )
            return None
        r.raise_for_status()
        data = r.json()

        if data.get("status") != "OK":
            if data.get("status") == "OVER_DAILY_LIMIT":
                log.warning("Google Maps daily quota exceeded")
            elif data.get("status") == "OVER_QUERY_LIMIT":
                log.warning("Google Maps query rate limit hit")
            elif data.get("status") == "ZERO_RESULTS":
                return None  # Not an error — no results for this coord
            else:
                log.debug(f"Google Maps status: {data.get('status')}")
            return None

        results = data.get("results", [])
        if not results:
            return None

        # Parse address_components from the first (most specific) result
        components = results[0].get("address_components", [])
        city = None
        state_code = None

        for comp in components:
            types = comp.get("types", [])
            if "locality" in types or "sublocality" in types:
                city = comp.get("long_name", "")
            elif "administrative_area_level_1" in types:
                # Prefer short name (e.g. "TX" over "Texas")
                state_code = comp.get("short_name", "").upper()

        if city and state_code:
            return {"city": city, "state": state_code}

        return None
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        log.debug(f"Google Maps reverse geocode failed ({lon},{lat}): {e}")
        return None


async def run_enrichment(dry_run: bool = False) -> dict:
    """Main enrichment pipeline using Google Maps Geocoding API."""
    sb = _sb()
    api_key = _get_google_maps_key()
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

    # ── 3. Reverse geocode via Google Maps ───────────────────────────
    sem = asyncio.Semaphore(CONCURRENCY)
    results: Dict[str, Tuple[str, str]] = {}  # id -> (city, state)

    async def _geocode_one(tid: str, lon: float, lat: float, client: httpx.AsyncClient):
        async with sem:
            await asyncio.sleep(REQUEST_DELAY)
            result = await _google_maps_reverse(client, api_key, lon, lat)
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
        f"Google Maps geocoding complete: {len(results)} resolved / "
        f"{len(to_geocode)} attempted"
    )

    # ── 4. Apply DB updates ──────────────────────────────────────────
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

    # ── 5. Summary ───────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    summary = {
        "total_missing": total,
        "had_location_coords": len(to_geocode),
        "google_maps_resolved": len(results),
        "db_updated": updated,
        "db_errors": errors,
        "unresolved_remaining": total - len(results),
        "elapsed_seconds": round(elapsed, 1),
        "google_maps_key_configured": bool(api_key),
        "dry_run": dry_run,
    }

    log.info("=== GOOGLE MAPS ENRICHMENT SUMMARY ===")
    log.info(f"Total missing city+state:  {total}")
    log.info(f"Had location coords:       {len(to_geocode)}")
    log.info(f"Google Maps resolved:      {len(results)}")
    log.info(f"DB updated:                {updated}")
    log.info(f"Errors:                    {errors}")
    log.info(f"Still unresolved:          {total - len(results)}")
    log.info(f"Elapsed:                   {elapsed:.1f}s")

    return summary


def main():
    p = argparse.ArgumentParser(
        description="Reverse geocode remaining radar_targets via Google Maps"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report only — no DB writes (still calls Google Maps API for count)",
    )
    args = p.parse_args()

    result = asyncio.run(run_enrichment(dry_run=args.dry_run))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
