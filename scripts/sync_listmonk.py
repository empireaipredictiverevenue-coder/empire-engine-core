"""
EMPIRE V49 · LISTMONK SYNC CRON
=================================
Incremental sync: pulls new/updated contractors from Supabase and
adds them to ListMonk. Designed to run via cron (every 6 hours).

Unlike scripts/import_listmonk.py (which does a full bulk import),
this script only syncs contractors created/updated since the last run.

Run:
    python3 scripts/sync_listmonk.py           # incremental sync
    python3 scripts/sync_listmonk.py --full    # full re-import
    python3 scripts/sync_listmonk.py --dry-run # preview only

Requirements:
    - ListMonk running (listmonk-db + listmonk-q containers)
    - /root/.env with SUPABASE_URL, SUPABASE_SERVICE_KEY
"""

import os
import re
import sys
import json
import uuid
import logging
import argparse
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path("/root/empire-v49").resolve()
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client

log = logging.getLogger("sync_listmonk")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PSQL_EXEC = ["docker", "exec", "-t", "listmonk-db", "psql", "-U", "listmonk", "-d", "listmonk", "-c"]
STATE_FILE = Path("/root/.listmonk_sync_state")


def _sql(query: str) -> str:
    try:
        result = subprocess.run(PSQL_EXEC + [query], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=15)
        return result.stdout
    except Exception:
        return ""


def _is_valid_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    bad = ["__quarantine__", "pending.real-email", "@placeholder", "@example",
           "@empire-ai", "noreply@", "test@"]
    el = email.lower()
    if any(b in el for b in bad):
        return False
    return bool(EMAIL_RE.match(email))


def _ensure_subscriber(email: str, name: str, attribs: dict) -> int:
    """Create or update a subscriber. Returns subscriber ID."""
    sub_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"empire-sub-{email}"))
    safe_email = email.replace("'", "''")
    safe_name = name.replace("'", "''")
    attribs_json = json.dumps(attribs).replace("'", "''")

    check = _sql(f"SELECT id FROM subscribers WHERE email = '{safe_email}';")
    for line in check.split("\n"):
        line = line.strip()
        if line.isdigit():
            _sql(
                f"UPDATE subscribers SET name = '{safe_name}', attribs = '{attribs_json}'::jsonb, "
                f"updated_at = NOW() WHERE id = {line};"
            )
            return int(line)

    _sql(
        f"INSERT INTO subscribers (uuid, email, name, attribs, status, created_at, updated_at) "
        f"VALUES ('{sub_uuid}', '{safe_email}', '{safe_name}', '{attribs_json}'::jsonb, "
        f"'enabled', NOW(), NOW());"
    )
    check2 = _sql(f"SELECT id FROM subscribers WHERE email = '{safe_email}';")
    for line in check2.split("\n"):
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def _get_list_id(name: str) -> int:
    safe = name.replace("'", "''")
    out = _sql(f"SELECT id FROM lists WHERE name = '{safe}';")
    for line in out.split("\n"):
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def _subscribe(sub_id: int, list_id: int) -> None:
    if not sub_id or not list_id:
        return
    _sql(
        f"INSERT INTO subscriber_lists (subscriber_id, list_id, status, created_at, updated_at) "
        f"VALUES ({sub_id}, {list_id}, 'confirmed', NOW(), NOW()) "
        f"ON CONFLICT (subscriber_id, list_id) DO NOTHING;"
    )


def _load_state() -> str:
    """Load last sync timestamp from state file."""
    if STATE_FILE.exists():
        try:
            return STATE_FILE.read_text().strip()
        except Exception:
            pass
    return (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()


def _save_state(ts: str) -> None:
    STATE_FILE.write_text(ts)


def run(dry_run: bool = False, full: bool = False) -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # Pre-flight
    if not dry_run:
        health = _sql("SELECT 1;")
        if "1" not in health:
            log.error("ListMonk DB unreachable")
            return {"status": "error", "message": "ListMonk DB unreachable"}

    # Fetch contractors — incremental or full
    if full:
        r = sb.table("contractors").select("id,name,email,phone,metro,solana_wallet,active").limit(7000).execute()
    else:
        since = _load_state()
        log.info(f"Incremental sync since: {since}")
        r = sb.table("contractors").select("id,name,email,phone,metro,solana_wallet,active").gte("created_at", since).limit(7000).execute()

    all_cont = r.data or []
    candidates = [c for c in all_cont if c.get("active") and _is_valid_email(c.get("email", ""))]
    log.info(f"Candidates: {len(candidates)} (from {len(all_cont)} total)")

    if dry_run:
        print(f"\nDRY RUN: Would sync {len(candidates)} contractors")
        metros = {}
        for c in candidates:
            metros[c.get("metro", "?")] = metros.get(c.get("metro", "?"), 0) + 1
        for m, n in sorted(metros.items(), key=lambda x: -x[1]):
            print(f"  {m}: {n}")
        return {"status": "dry_run", "total": len(candidates)}

    # Get list IDs
    all_list_id = _get_list_id("All Contractors")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    imported = 0
    errors = 0

    for c in candidates:
        try:
            email = c["email"]
            name = c.get("name", email.split("@")[0]).strip() or email.split("@")[0]
            metro = c.get("metro", "unknown")
            has_wallet = bool(c.get("solana_wallet"))
            phone = c.get("phone", "")

            attribs = {
                "metro": metro,
                "has_wallet": has_wallet,
                "phone": phone,
                "source": "supabase_sync",
                "synced_at": now_iso,
            }

            sub_id = _ensure_subscriber(email, name, attribs)
            if sub_id:
                if all_list_id:
                    _subscribe(sub_id, all_list_id)
                metro_list_id = _get_list_id(metro)
                if metro_list_id:
                    _subscribe(sub_id, metro_list_id)
                wallet_list_name = "Wallet: Set" if has_wallet else "Wallet: Pending"
                wallet_list_id = _get_list_id(wallet_list_name)
                if wallet_list_id:
                    _subscribe(sub_id, wallet_list_id)
                imported += 1
            else:
                errors += 1
        except Exception as e:
            log.warning(f"Sync error for {c.get('email', '?')}: {e}")
            errors += 1

    _save_state(now_iso)
    log.info(f"Sync complete: {imported} imported, {errors} errors")
    return {"status": "ok", "imported": imported, "errors": errors, "synced_at": now_iso}


def main():
    p = argparse.ArgumentParser(description="Incremental ListMonk sync")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--full", action="store_true", help="Full re-import (ignore last sync time)")
    args = p.parse_args()

    result = run(dry_run=args.dry_run, full=args.full)
    print(f"\nSync: {result.get('imported', 0)} imported, {result.get('errors', 0)} errors")
    sys.exit(0 if result.get("errors", 0) == 0 else 1)


if __name__ == "__main__":
    main()
