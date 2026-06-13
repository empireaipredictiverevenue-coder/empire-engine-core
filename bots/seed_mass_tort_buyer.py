"""
EMPIRE V49 · MASS TORT BUYER SEEDER (idempotent)
================================================
Seeds the canonical Mass Tort Legal buyer (Apex Mass Tort Group) into
the buyers table.

Patched 2026-06-12: the original seeder had no dedup guard and ran
~35 times, leaving 35 identical rows. The seeder is now idempotent:
  - If an active buyer with the same (niche, buyer_name) already exists,
    it UPDATEs the existing row in place with the current config.
  - If no row exists, it INSERTs one.
  - The destination_phone placeholder "+18555550220" is replaced with
    a clear PLACEHOLDER value (None) so routing logic doesn't dial a
    fake number. The real number must be set via the dashboard or a
    separate script.

Real numbers must be set per state/buyer from the vonage dashboard
once they are provisioned. This script does NOT make up numbers.
"""

import os
import sys


# Manual .env loader (sniper_env may not have python-dotenv).
ENV_PATH = "/root/.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _v = _v.strip()
            if (_v.startswith('"') and _v.endswith('"')) or (_v.startswith("'") and _v.endswith("'")):
                _v = _v[1:-1]
            os.environ[_k.strip()] = _v


from supabase import create_client


if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
    print("[ERROR] SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


NICHE = "Mass Tort Legal"
BUYER_NAME = "Apex Mass Tort Group"


buyer_payload = {
    "buyer_name": BUYER_NAME,
    "niche": NICHE,
    # destination_phone is intentionally None. Real vonage numbers are
    # provisioned per state/buyer from the dashboard and set via a
    # separate update. Dialling a placeholder (555 prefix) is illegal
    # under NANPA reservation rules AND would never be accepted by a
    # real buyer.
    "destination_phone": None,
    "is_active": True,
    "state_coverage": ["TX", "NY", "FL", "CA", "IL"],
    "base_payout": 400.00,
    "fee_rate": 0.03,
    "per_call_fee": 0,
    "monthly_retainer": 2000,
    "daily_cap": 50,
    "hours_open": 8,
    "hours_close": 20,
    "calls_today": 0,
    "calls_accepted": 0,
    "calls_offered": 0,
}


# Step 1: check for existing active row.
existing = (
    sb.table("buyers")
    .select("id, destination_phone, is_active")
    .eq("niche", NICHE)
    .eq("buyer_name", BUYER_NAME)
    .eq("is_active", True)
    .execute()
)


if existing.data:
    row_id = existing.data[0]["id"]
    print(f"[INFO] Existing active row found (id={row_id}). Updating in place.")
    try:
        sb.table("buyers").update(buyer_payload).eq("id", row_id).execute()
        print(f"[SUCCESS] {BUYER_NAME} updated in place. destination_phone={buyer_payload['destination_phone']!r}")
    except Exception as e:
        err = str(e).lower()
        if "per_call_fee" in err or "monthly_retainer" in err:
            print("[WARN] New fee columns not in DB — retrying without them")
            safe = {k: v for k, v in buyer_payload.items()
                    if k not in ("per_call_fee", "monthly_retainer")}
            sb.table("buyers").update(safe).eq("id", row_id).execute()
            print(f"[SUCCESS] {BUYER_NAME} updated in place (without new fee columns).")
        else:
            print(f"[ERROR] Update failed: {e}")
            sys.exit(1)
else:
    print(f"[INFO] No active row for {BUYER_NAME!r} in {NICHE!r}. Inserting.")
    try:
        sb.table("buyers").insert(buyer_payload).execute()
        print(f"[SUCCESS] {BUYER_NAME} seeded. destination_phone={buyer_payload['destination_phone']!r} (must be set from dashboard)")
    except Exception as e:
        err = str(e).lower()
        if "per_call_fee" in err or "monthly_retainer" in err:
            print("[WARN] New fee columns not in DB — retrying without them")
            safe = {k: v for k, v in buyer_payload.items()
                    if k not in ("per_call_fee", "monthly_retainer")}
            sb.table("buyers").insert(safe).execute()
            print(f"[SUCCESS] {BUYER_NAME} seeded (without new fee columns).")
        else:
            print(f"[ERROR] Insert failed: {e}")
            sys.exit(1)
