import os
from supabase import create_client

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")

if not url or not key:
    print("[ERROR] Missing Supabase environment variables!")
    exit(1)

sb = create_client(url, key)

buyer_payload = {
    "buyer_name": "Apex Mass Tort Group",
    "niche": "Mass Tort Legal",
    "destination_phone": "+18555550220",
    "is_active": True,
    "state_coverage": ["TX", "NY", "FL", "CA", "IL"],
    "base_payout": 400.00,
    "fee_rate": 0.01,
    "per_call_fee": 0,
    "monthly_retainer": 2000,
    "daily_cap": 50,
    "hours_open": 8,
    "hours_close": 20,
    "calls_today": 0,
    "calls_accepted": 0,
    "calls_offered": 0
}

try:
    res = sb.table("buyers").insert(buyer_payload).execute()
    print(f"[SUCCESS] Mass Tort Legal Buyer Seeded! Base Payout: ${buyer_payload['base_payout']}")
except Exception as e:
    err_msg = str(e).lower()
    if "per_call_fee" in err_msg or "monthly_retainer" in err_msg:
        print("[WARN] New fee columns not in DB — retrying without them")
        safe = {k: v for k, v in buyer_payload.items()
                if k not in ("per_call_fee", "monthly_retainer")}
        try:
            res = sb.table("buyers").insert(safe).execute()
            print(f"[SUCCESS] Mass Tort Legal Buyer Seeded! (without new fee columns)")
        except Exception as e2:
            print(f"[ERROR] Database injection failed (fallback): {e2}")
    else:
        print(f"[ERROR] Database injection failed: {e}")
