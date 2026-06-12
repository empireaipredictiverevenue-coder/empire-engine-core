"""
EMPIRE V49 · MASS TORT BUYER DEDUP (STEP 1)
=============================================
The bots/seed_mass_tort_buyer.py seeder has no dedup guard and was run
~35 times, leaving 35 identical "Apex Mass Tort Group" rows in the
buyers table. This script:

  1. Identifies the canonical (newest) row.
  2. Marks all 34 others is_active = false.
  3. Preserves the row's created_at + id by leaving it untouched.

Reversible. No DELETE. The 34 inactive rows stay in the table so the
agent can re-verify before any destructive cleanup (Step 6).

After this, the routing query
  SELECT * FROM buyers WHERE is_active = true AND niche = 'Mass Tort Legal'
returns 1 row.

This is step 1 of the "sort the mass tort lane" plan approved 2026-06-12.
"""

import os
import sys

# Load .env manually (sniper_env may not have python-dotenv).
ENV_PATH = "/root/.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            # Strip surrounding quotes if present
            _v = _v.strip()
            if (_v.startswith('"') and _v.endswith('"')) or (_v.startswith("'") and _v.endswith("'")):
                _v = _v[1:-1]
            os.environ[_k.strip()] = _v

from supabase import create_client

if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
    print("[ERROR] SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Find all Mass Tort Legal rows, ordered newest first
res = sb.table("buyers") \
    .select("id, buyer_name, niche, is_active, created_at") \
    .eq("niche", "Mass Tort Legal") \
    .order("created_at", desc=True) \
    .execute()

rows = res.data
print(f"Found {len(rows)} Mass Tort Legal rows")

if not rows:
    print("Nothing to do.")
    sys.exit(0)

# All rows should be Apex — confirm
unique_names = {r["buyer_name"] for r in rows}
print(f"Unique buyer names: {unique_names}")
if len(unique_names) > 1:
    print("[WARN] Multiple distinct buyer names found. Review manually before continuing.")
    sys.exit(2)

canonical = rows[0]
duplicates = rows[1:]

print(f"\nCanonical (newest):")
print(f"  id:         {canonical['id']}")
print(f"  created_at: {canonical['created_at']}")
print(f"  is_active:  {canonical['is_active']}")

print(f"\nWill deactivate {len(duplicates)} duplicate rows.")

if not duplicates:
    print("Nothing to deactivate.")
    sys.exit(0)

# Deactivate in batches of 10 (supabase row limit per update is generous
# but batching keeps the API call bounded).
ids_to_kill = [d["id"] for d in duplicates]
deactivated = 0
for i in range(0, len(ids_to_kill), 10):
    batch = ids_to_kill[i:i+10]
    sb.table("buyers") \
        .update({"is_active": False}) \
        .in_("id", batch) \
        .execute()
    deactivated += len(batch)
    print(f"  Deactivated batch {i//10 + 1}: {len(batch)} rows")

print(f"\nDone. {deactivated} rows set to is_active=false.")

# Verify
verify = sb.table("buyers") \
    .select("id, is_active") \
    .eq("niche", "Mass Tort Legal") \
    .eq("is_active", True) \
    .execute()
print(f"\nVerification: {len(verify.data)} active Mass Tort Legal rows (expected 1).")
if len(verify.data) == 1 and verify.data[0]["id"] == canonical["id"]:
    print("  OK — canonical row is the only active one.")
else:
    print("  [WARN] State mismatch. Review manually.")
    sys.exit(3)
