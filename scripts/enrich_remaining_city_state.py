#!/usr/bin/env python3
"""
EMPIRE V49 · ENRICH REMAINING CITY/STATE (FAST PATH)
=====================================================
Dedicated runner for the remaining ~2,541 radar_targets with null
city+state. Resolves all addresses locally first (no API calls), then
batches DB updates efficiently.

Usage:
    python3 scripts/enrich_remaining_city_state.py          # live
    python3 scripts/enrich_remaining_city_state.py --dry-run # report only
"""

import os
import sys
import json
import logging
import argparse
import asyncio
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

log = logging.getLogger("enrich_city_state")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

sys.path.insert(0, str(REPO / "agents" / "lead_scanner"))
from scanner import _parse_address, _STATE_ZIP_RE


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _extract_from_meta_raw(meta: Optional[dict]) -> Tuple[Optional[str], Optional[str]]:
    if not meta or not isinstance(meta, dict):
        return None, None
    raw = meta.get("raw") or {}
    if not isinstance(raw, dict):
        return None, None
    city = raw.get("addr:city")
    state = raw.get("addr:state")
    if city and state:
        return city.strip(), state.strip().upper()
    return None, None


def enrich(dry_run: bool = False) -> dict:
    """Resolve city/state from address data and update DB."""
    sb = _sb()
    started_at = datetime.now(timezone.utc)

    # Fetch all targets still missing city+state
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

    # Resolve all locally (no API calls)
    updates: Dict[str, Tuple[str, str]] = {}  # id -> (city, state)

    for row in all_rows:
        tid = row["id"]

        # Tier 1: meta.raw.addr:city/state
        city, state = _extract_from_meta_raw(row.get("meta"))
        if city and state:
            updates[tid] = (city, state)
            continue

        # Tier 2: address string parsing
        addr = row.get("address") or ""
        meta = row.get("meta") or {}
        raw = meta.get("raw") or {} if isinstance(meta, dict) else {}

        city, state = _parse_address(addr, raw=raw)
        if city and state:
            updates[tid] = (city, state)
        elif city and not state:
            st_match = _STATE_ZIP_RE.search(addr)
            if st_match:
                updates[tid] = (city, st_match.group("state"))

    log.info(f"Resolved: {len(updates)} / {total} locally")

    # Apply DB updates in batches
    updated = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    BATCH = 200

    if dry_run:
        log.info("DRY RUN — no DB writes")
        for i, (tid, (city, state)) in enumerate(updates.items()):
            if i >= 20:
                break
            log.info(f"  WOULD UPDATE: {tid[:12]}  city={city:20s}  state={state}")
        return {"total": total, "resolved": len(updates), "updated": 0, "dry_run": True}

    items = list(updates.items())
    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        batch_count = 0
        for tid, (city, state) in batch:
            try:
                sb.table("radar_targets").update({
                    "city": city,
                    "state": state,
                    "updated_at": now_iso,
                }).eq("id", tid).execute()
                batch_count += 1
            except Exception as e:
                log.warning(f"Failed to update {tid[:12]}: {e}")
        updated += batch_count
        if (i + BATCH) % 1000 == 0 or (i + BATCH) >= len(items):
            log.info(f"  Updated {updated}/{len(updates)} targets")

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    summary = {
        "total_missing": total,
        "resolved": len(updates),
        "updated": updated,
        "unresolved": total - len(updates),
        "elapsed_seconds": round(elapsed, 1),
    }

    log.info(f"=== DONE ===")
    log.info(f"Total missing:  {total}")
    log.info(f"Resolved:       {len(updates)}")
    log.info(f"DB updated:     {updated}")
    log.info(f"Unresolved:     {total - len(updates)}")
    log.info(f"Elapsed:        {elapsed:.1f}s")

    return summary


def main():
    p = argparse.ArgumentParser(description="Enrich remaining null city/state targets")
    p.add_argument("--dry-run", action="store_true", help="Report only — no DB writes")
    args = p.parse_args()
    result = enrich(dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
