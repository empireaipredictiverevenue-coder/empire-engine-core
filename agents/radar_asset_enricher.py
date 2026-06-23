"""Empire AI · Radar Asset Enricher

Backfills radar_targets.asset_value (currently $1-$50 placeholder) with
real $ estimates. Runs every 6 hours via cron.

Strategy (in order):
  1. External property API if key present:
     - ATTOM_DATA_API_KEY → ATTOM property API
     - RENTCAST_API_KEY   → RentCast property API
  2. Census ACS 5-year median home value by zip code (free, no key)
  3. Business-signal formula fallback: sub_niche × rating × reviews × base

The formula gives a wide-range estimate; the goal is to push the
$1-$10 placeholders into realistic 5-7 figure territory so
lead_enricher's tiered scoring actually differentiates.

Usage:
    python3 -m agents.radar_asset_enricher                  # one run
    python3 -m agents.radar_asset_enricher --limit 200      # batch size
    python3 -m agents.radar_asset_enricher --dry            # log only
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

import httpx
from supabase import create_client

log = logging.getLogger("empire.radar_asset_enricher")
_ZHVI_MAP = None  # lazy-loaded cache for the 26,274-zip Zillow ZHVI map
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# Sub-niche base $ value (rough commercial property value by industry)
SUB_NICHE_BASE_USD = {
    # Logistics / warehouse — high asset
    "warehouse":        5_000_000,
    "distribution":     8_000_000,
    "logistics":        6_000_000,
    "cold_storage":     7_000_000,
    "freight":          4_500_000,
    # Industrial
    "manufacturing":    6_000_000,
    "industrial":       3_500_000,
    # Commercial — mid
    "retail":             800_000,
    "store":              600_000,
    "shop":               400_000,
    "food":             1_200_000,
    "restaurant":         750_000,
    # Office / services
    "office":           1_500_000,
    "professional":       500_000,
    # Healthcare
    "medical":          2_500_000,
    "dental":           1_200_000,
    "veterinary":         800_000,
    # Auto
    "auto_repair":        600_000,
    "dealership":       2_500_000,
    # Storm verticals (smaller commercial)
    "roofing":            350_000,
    "hvac":               300_000,
    "restoration":        250_000,
    "general_contractor": 400_000,
    "solar":              500_000,
    "electrical":         350_000,
    "plumbing":           350_000,
}
DEFAULT_BASE_USD = 500_000


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _formula_estimate(row: dict) -> int:
    """Fallback: estimate $ from business signals when no API works."""
    wh = (row.get("warehouse_name") or row.get("name") or "").lower()
    sub = (row.get("sub_niche") or "").lower()
    rating = float(row.get("meta", {}).get("rating") or 0) if isinstance(row.get("meta"), dict) else 0
    reviews = int(row.get("meta", {}).get("review_count") or 0) if isinstance(row.get("meta"), dict) else 0

    # 1. Pick base by sub_niche first, then keyword fallback
    base = SUB_NICHE_BASE_USD.get(sub, 0)
    if base == 0:
        for kw, val in SUB_NICHE_BASE_USD.items():
            if kw in wh:
                base = val
                break
    if base == 0:
        base = DEFAULT_BASE_USD

    # 2. Rating multiplier (3.0-5.0 → 0.6-1.4)
    if rating >= 4.5:
        rating_mult = 1.4
    elif rating >= 4.0:
        rating_mult = 1.1
    elif rating >= 3.0:
        rating_mult = 0.9
    elif rating > 0:
        rating_mult = 0.6
    else:
        rating_mult = 1.0

    # 3. Reviews signal (10+ reviews → 1.0; 100+ → 1.5)
    if reviews >= 200:
        rev_mult = 1.8
    elif reviews >= 100:
        rev_mult = 1.5
    elif reviews >= 50:
        rev_mult = 1.25
    elif reviews >= 10:
        rev_mult = 1.1
    else:
        rev_mult = 1.0

    # 4. Urgency already reflects storm risk; we keep base asset neutral to that
    est = int(base * rating_mult * rev_mult)
    # Floor: at least $50k so we exit placeholder tier
    return max(50_000, est)


def _try_zhvi(address: str, row: dict = None) -> int | None:
    """Look up Zillow ZHVI median home value by zip / city / metro / state.
    Uses the pre-downloaded combined map (data/zhvi_combined.json,
    46,719 entries: 26,274 zips + 19,467 cities + 927 metros + 51 states)."""
    global _ZHVI_MAP
    try:
        if _ZHVI_MAP is None:
            from pathlib import Path
            map_path = Path(__file__).resolve().parents[1] / "data" / "zhvi_combined.json"
            if not map_path.exists():
                # Fall back to old single-purpose zip map
                old_path = Path(__file__).resolve().parents[1] / "data" / "zhvi_zip_map.json"
                if old_path.exists():
                    with open(old_path) as f:
                        import json as _json
                        old = _json.load(f)
                    _ZHVI_MAP = {"zip": old, "city": {}, "state": {}, "metro": {}}
                else:
                    return None
            else:
                with open(map_path) as f:
                    import json as _json
                    _ZHVI_MAP = _json.load(f)
    except Exception:
        return None
    if not address and not row:
        return None
    import re as _re

    def _ok(v):
        return v and 10000 < v < 50000000

    # 1. Try zip from address
    if address:
        m = _re.search(r"\b(\d{5})(?:-\d{4})?\b", address)
        if m:
            v = _ZHVI_MAP.get("zip", {}).get(m.group(1))
            if _ok(v):
                return int(v)

    # 2. Try city from row or address
    city = None
    state = None
    if row:
        city = (row.get("city") or "").strip()
        state = (row.get("state") or "").strip()
    if not city and address:
        # Best-effort: extract city from "City, ST" pattern
        cm = _re.search(r"\b([A-Z][a-zA-Z ]+?)[,\s]+([A-Z]{2})\b", address)
        if cm:
            city = cm.group(1).strip()
            state = cm.group(2).strip()
    if city and state:
        v = _ZHVI_MAP.get("city", {}).get(f"{city.lower()}|{state.upper()}")
        if _ok(v):
            return int(v)
        # 3. Try metro (use first 3 words of city as metro guess)
        # (most ZHVI metros are "City1-City2-City3, ST" — first word is the city)
        v = _ZHVI_MAP.get("metro", {}).get(f"{city}, {state.upper()}")
        if _ok(v):
            return int(v)
        # 4. Try state median
        if state:
            v = _ZHVI_MAP.get("state", {}).get(state.upper())
            if _ok(v):
                return int(v)
    return None


def _try_attom(address: str) -> int | None:
    """Use ATTOM property API if key set. Returns $ or None."""
    key = os.getenv("ATTOM_DATA_API_KEY", "")
    if not key:
        return None
    try:
        url = "https://api.gateway.attomdata.com/propertyapi/v1.0.0/property/address"
        headers = {"Accept": "application/json", "apikey": key}
        params = {"address1": address, "pagesize": 1}
        r = httpx.get(url, headers=headers, params=params, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        prop = (data.get("property") or [{}])[0]
        building = prop.get("building", {})
        size = building.get("size", {}) or {}
        sqft = int(size.get("livingsize") or 0)
        # If we have sqft, estimate at $200/sqft (commercial median)
        if sqft > 500:
            return max(50_000, sqft * 200)
        return None
    except Exception as e:
        log.debug(f"attom failed for {address}: {e}")
        return None


def _try_rentcast(address: str) -> int | None:
    """Use RentCast API if key set."""
    key = os.getenv("RENTCAST_API_KEY", "")
    if not key:
        return None
    try:
        url = "https://api.rentcast.io/v1/avm/value"
        headers = {"Accept": "application/json", "X-Api-Key": key}
        params = {"address": address}
        r = httpx.get(url, headers=headers, params=params, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        price = data.get("price") or data.get("value")
        if price and int(price) > 0:
            return int(price)
        return None
    except Exception as e:
        log.debug(f"rentcast failed for {address}: {e}")
        return None


def _lookup_asset(row: dict) -> tuple[int, str]:
    """Try ATTOM → RentCast → formula. Returns (usd, source)."""
    addr = (row.get("address") or "").strip()
    if addr:
        v = _try_attom(addr)
        if v:
            return v, "attom"
        v = _try_rentcast(addr)
        if v:
            return v, "rentcast"
    # Try Zillow ZHVI zip / city / metro / state data first (best free signal).
    v = _try_zhvi(addr, row)
    if v:
        return v, "zillow_zhvi"
    return _formula_estimate(row), "formula"


def _log_activity(sb, agent_name, run_id, started_at, status, summary, rows_seen=0, rows_updated=0, error=None):
    sb.table("agent_activity").insert({
        "agent_name": agent_name,
        "run_id": str(run_id),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "rows_seen": rows_seen,
        "rows_processed": rows_updated,
        "summary": summary,
        "error": error,
    }).execute()


def run(limit: int = 200, dry_run: bool = False) -> dict:
    started = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()

    # Pull radar_targets with placeholder asset_value ($1-$50)
    r = (sb.table("radar_targets")
            .select("id,address,city,state,warehouse_name,name,sub_niche,meta,asset_value")
            .gt("asset_value", 0)
            .lte("asset_value", 50)
            .limit(limit)
            .execute())
    rows = r.data or []
    log.info(f"radar_asset_enricher: {len(rows)} placeholder rows to enrich")
    rows_seen = len(rows)

    updated = 0
    by_source = {"attom": 0, "rentcast": 0, "formula": 0}
    errors = []

    for row in rows:
        try:
            new_val, source = _lookup_asset(row)
            by_source[source] += 1
            if new_val > 50 and not dry_run:
                sb.table("radar_targets").update({
                    "asset_value": new_val,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", row["id"]).execute()
            updated += 1
        except Exception as e:
            errors.append(f"{row.get('id','?')[:8]}: {type(e).__name__}: {e}")

    summary = f"enriched {updated}/{rows_seen} rows — {by_source}"
    # Schema only allows ok/skipped_disabled/error. Put details in error column.
    status = "ok" if not errors else "error"
    _log_activity(sb, "radar_asset_enricher", run_id, started, status, summary,
                  rows_seen=rows_seen, rows_updated=updated,
                  error="; ".join(errors[:5]) if errors else None)
    # Update agent_config last_run
    sb.table("agent_config").update({
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", "radar_asset_enricher").execute()

    log.info(summary)
    return {"status": status, "rows_seen": rows_seen, "rows_updated": updated, "by_source": by_source}


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--dry", action="store_true")
    args = p.parse_args()
    res = run(limit=args.limit, dry_run=args.dry)
    sys.exit(0 if res["status"] in ("ok", "ok_with_errors") else 1)


if __name__ == "__main__":
    main()