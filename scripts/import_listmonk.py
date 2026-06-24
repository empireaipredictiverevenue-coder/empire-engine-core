"""
Empire AI · Import Contractors into ListMonk
=============================================
Imports all active contractors with valid emails into ListMonk as
subscribers with metadata (metro, wallet status, phone), then creates
segment lists for each metro and for wallet pending/completed status.

Run:
  python3 scripts/import_listmonk.py          # full import
  python3 scripts/import_listmonk.py --dry-run # preview only

Requirements:
  - ListMonk running on localhost:9000
  - ListMonk PostgreSQL accessible via docker exec (listmonk-db)
"""

import os
import re
import sys
import uuid
import json
import logging
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/root/empire-v49").resolve()
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client

log = logging.getLogger("import_listmonk")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# ListMonk DB access via docker exec
PSQL_EXEC = ['docker', 'exec', '-t', 'listmonk-db', 'psql', '-U', 'listmonk', '-d', 'listmonk', '-c']


def _sql(query: str) -> str:
    """Run a SQL query on the ListMonk database. Returns stdout."""
    try:
        result = subprocess.run(PSQL_EXEC + [query], capture_output=True, text=True, timeout=15)
        return result.stdout
    except subprocess.TimeoutExpired:
        log.warning(f"SQL query timed out: {query[:60]}...")
        return ""
    except Exception as e:
        log.warning(f"SQL query failed: {e}")
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


def _ensure_list(name: str, list_type: str = "public", description: str = "") -> int:
    """Create a list if it doesn't exist. Returns the list ID."""
    list_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"empire-list-{name}"))
    safe_name = name.replace("'", "''")
    safe_desc = description.replace("'", "''")

    # Try to find existing list by name
    check = _sql(f"SELECT id FROM lists WHERE name = '{safe_name}';")
    for line in check.split("\n"):
        line = line.strip()
        if line.isdigit():
            return int(line)

    # Create the list
    _sql(
        f"INSERT INTO lists (uuid, name, type, optin, status, tags, description, created_at, updated_at) "
        f"VALUES ('{list_uuid}', '{safe_name}', '{list_type}', 'single', 'active', '{{\"imported\"}}', "
        f"'{safe_desc}', NOW(), NOW());"
    )
    # Get the new ID
    check = _sql(f"SELECT id FROM lists WHERE name = '{safe_name}';")
    for line in check.split("\n"):
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def _ensure_subscriber(email: str, name: str, attribs: dict) -> int:
    """Create a subscriber if they don't exist. Returns the subscriber ID."""
    sub_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"empire-sub-{email}"))
    safe_email = email.replace("'", "''")
    safe_name = name.replace("'", "''")
    attribs_json = json.dumps(attribs).replace("'", "''")

    # Check if subscriber already exists
    check = _sql(f"SELECT id FROM subscribers WHERE email = '{safe_email}';")
    for line in check.split("\n"):
        line = line.strip()
        if line.isdigit():
            # Update attribs
            _sql(
                f"UPDATE subscribers SET name = '{safe_name}', attribs = '{attribs_json}'::jsonb, "
                f"updated_at = NOW() WHERE id = {line};"
            )
            return int(line)

    # Create subscriber
    _sql(
        f"INSERT INTO subscribers (uuid, email, name, attribs, status, created_at, updated_at) "
        f"VALUES ('{sub_uuid}', '{safe_email}', '{safe_name}', '{attribs_json}'::jsonb, "
        f"'enabled', NOW(), NOW());"
    )
    # Get the new ID
    check = _sql(f"SELECT id FROM subscribers WHERE email = '{safe_email}';")
    for line in check.split("\n"):
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def _subscribe_to_list(subscriber_id: int, list_id: int) -> None:
    """Associate a subscriber with a list."""
    _sql(
        f"INSERT INTO subscriber_lists (subscriber_id, list_id, status, created_at, updated_at) "
        f"VALUES ({subscriber_id}, {list_id}, 'confirmed', NOW(), NOW()) "
        f"ON CONFLICT (subscriber_id, list_id) DO NOTHING;"
    )


def _bulk_import(candidates: list, metro_ids: dict, all_list_id: int, wallet_pending_id: int, wallet_set_id: int) -> dict:
    """Bulk-import all subscribers and their list subscriptions via a single SQL script.

    Uses a multi-row INSERT with ON CONFLICT to handle duplicates, then bulk-inserts
    subscriber_lists associations. This is MUCH faster than one docker exec per row.
    """
    if not candidates:
        return {"imported": 0, "errors": 0}

    # Build subscriber VALUES
    now = datetime.now(timezone.utc).isoformat()
    sub_values = []
    sl_values = []

    for c in candidates:
        email = c["email"]
        name = c.get("name", email.split("@")[0]).strip()
        if not name:
            name = email.split("@")[0]
        metro = c.get("metro", "unknown")
        has_wallet = bool(c.get("solana_wallet"))
        phone = c.get("phone", "")

        sub_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"empire-sub-{email}"))
        attribs = json.dumps({
            "metro": metro,
            "has_wallet": has_wallet,
            "phone": phone,
            "source": "supabase_import",
            "imported_at": now,
        })

        # Escape for SQL
        safe_email = email.replace("'", "''")
        safe_name = name.replace("'", "''")
        safe_attribs = attribs.replace("'", "''")

        sub_values.append(f"('{sub_uuid}', '{safe_email}', '{safe_name}', '{safe_attribs}'::jsonb, 'enabled', NOW(), NOW())")

    # Execute bulk subscriber INSERT
    sub_batch = ",\n".join(sub_values)
    batch_size = 100
    total_imported = 0

    for i in range(0, len(sub_values), batch_size):
        batch = sub_values[i:i + batch_size]
        chunk = ",\n".join(batch)
        sql = (
            f"INSERT INTO subscribers (uuid, email, name, attribs, status, created_at, updated_at) "
            f"VALUES {chunk} "
            f"ON CONFLICT (email) DO UPDATE SET "
            f"name = EXCLUDED.name, attribs = EXCLUDED.attribs, updated_at = NOW();"
        )
        out = _sql(sql)
        if "INSERT" in out or "DO UPDATE" in out or out == "":
            total_imported += len(batch)
        else:
            log.warning(f"Batch insert failed at offset {i}: {out[:100]}")

    log.info(f"Bulk subscriber insert: {total_imported} rows")

    # Now insert subscriber_lists associations in bulk
    # Use a subquery to match email → id
    sl_parts = []
    for c in candidates:
        email = c["email"]
        safe_email = email.replace("'", "''")
        metro = c.get("metro", "unknown")
        has_wallet = bool(c.get("solana_wallet"))

        # Subscribe to master list + metro list + wallet list
        lists_to_join = [all_list_id]
        if metro in metro_ids:
            lists_to_join.append(metro_ids[metro])
        lists_to_join.append(wallet_set_id if has_wallet else wallet_pending_id)

        for lid in lists_to_join:
            sl_parts.append(f"((SELECT id FROM subscribers WHERE email = '{safe_email}'), {lid}, 'confirmed', NOW(), NOW())")

    # Bulk insert subscriber_lists in batches
    for i in range(0, len(sl_parts), 200):
        batch = sl_parts[i:i + 200]
        chunk = ",\n".join(batch)
        sql = (
            f"INSERT INTO subscriber_lists (subscriber_id, list_id, status, created_at, updated_at) "
            f"VALUES {chunk} "
            f"ON CONFLICT (subscriber_id, list_id) DO NOTHING;"
        )
        _sql(sql)

    log.info(f"Bulk subscriber_lists insert: {len(sl_parts)} associations")
    return {"imported": total_imported, "associations": len(sl_parts)}


def run(dry_run: bool = False) -> dict:
    """Main import routine."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # 0) Pre-flight: check ListMonk DB is reachable
    if not dry_run:
        health = _sql("SELECT 1;")
        if "1" not in health:
            log.error("ListMonk DB unreachable — aborting")
            print("ERROR: Cannot connect to ListMonk PostgreSQL. Is listmonk-db running?")
            return {"status": "error", "message": "ListMonk DB unreachable"}

    # 1) Fetch contractors
    r = sb.table("contractors").select("id,name,email,phone,metro,solana_wallet,active").limit(7000).execute()
    all_cont = r.data or []
    candidates = [c for c in all_cont if c.get("active") and _is_valid_email(c.get("email", ""))]
    log.info(f"Found {len(candidates)} active contractors with valid email")

    # Count metros and wallet status
    metros = {}
    wallet_pending = 0
    wallet_set = 0
    for c in candidates:
        m = c.get("metro", "unknown")
        metros[m] = metros.get(m, 0) + 1
        if c.get("solana_wallet"):
            wallet_set += 1
        else:
            wallet_pending += 1

    if dry_run:
        print(f"\n{'='*50}")
        print(f"DRY RUN: Would import {len(candidates)} subscribers")
        print(f"  Metros: {len(metros)}")
        for m, n in sorted(metros.items(), key=lambda x: -x[1]):
            print(f"    {m}: {n}")
        print(f"  Wallet set:     {wallet_set}")
        print(f"  Wallet pending: {wallet_pending}")
        print(f"\n  Would create {len(metros) + 3} lists:")
        print(f"    - 'All Contractors' (master list)")
        for m in sorted(metros.keys()):
            print(f"    - '{m}' (metro segment)")
        print(f"    - 'Wallet: Pending' (no wallet set)")
        print(f"    - 'Wallet: Set' (has wallet)")
        print(f"{'='*50}\n")
        return {"status": "dry_run", "total": len(candidates), "metros": len(metros)}

    # 2) Create all lists first
    log.info("Creating lists...")
    all_list_id = _ensure_list("All Contractors", "public", "All active Empire AI contractors")

    metro_ids = {}
    for m in sorted(metros.keys()):
        metro_ids[m] = _ensure_list(m, "public", f"Contractors in {m} metro area")
    log.info(f"Created/verified {len(metro_ids)} metro lists")

    wallet_pending_id = _ensure_list("Wallet: Pending", "public", "Contractors who haven't set a Solana wallet")
    wallet_set_id = _ensure_list("Wallet: Set", "public", "Contractors who have set a Solana wallet")

    # 3) Bulk import subscribers
    log.info("Starting bulk import...")
    result = _bulk_import(candidates, metro_ids, all_list_id, wallet_pending_id, wallet_set_id)

    log.info(f"Import complete: {result['imported']} imported")
    return {
        "status": "ok",
        "total": len(candidates),
        "imported": result.get("imported", 0),
        "errors": len(candidates) - result.get("imported", 0),
        "metro_lists": len(metro_ids),
    }


def main():
    p = argparse.ArgumentParser(description="Import contractors into ListMonk")
    p.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    args = p.parse_args()

    if args.dry_run:
        log.info("=== DRY RUN MODE ===")

    result = run(dry_run=args.dry_run)

    if args.dry_run:
        print(f"\nDry run shows {result['total']} contractors across {result['metros']} metros")
    else:
        print(f"\nImport results:")
        print(f"  Total candidates: {result['total']}")
        print(f"  Imported:         {result['imported']}")
        print(f"  Errors:           {result['errors']}")
        print(f"  Metro lists:      {result['metro_lists']}")

    sys.exit(0 if result.get("errors", 0) == 0 else 1)


if __name__ == "__main__":
    main()
