"""
Empire AI · Insurance / Finance Niche Buyer Seeder
====================================================

Seeds placeholder buyers for the 4 finance/insurance sub-niches the
prospector supports. Same pattern as seed_legal_lane_buyers.py — but
newly added because that seeder only covered Legal.

Idempotent: dedups on (niche, buyer_name). Phone=None by default —
real numbers must be set per-buyer from the vonage dashboard.

Sub_niches seeded:
  - Debt Consolidation
  - Life Insurance Agent
  - Medicare Advantage Agent
  - Final Expense Insurance

CLI:
    python3 scripts/seed_insurance_buyers.py
"""
import os, sys
from pathlib import Path
from datetime import datetime, timezone

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client

BUYERS = [
    {"niche": "Insurance", "sub_niche": "Debt Consolidation", "buyer_name": "Debt Consolidation Lead Buyer #1", "priority": 70},
    {"niche": "Insurance", "sub_niche": "Life Insurance Agent", "buyer_name": "Life Insurance Lead Buyer #1", "priority": 70},
    {"niche": "Insurance", "sub_niche": "Medicare Advantage Agent", "buyer_name": "Medicare Advantage Lead Buyer #1", "priority": 70},
    {"niche": "Insurance", "sub_niche": "Final Expense Insurance", "buyer_name": "Final Expense Lead Buyer #1", "priority": 70},
]


def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    inserted = 0
    updated = 0
    for b in BUYERS:
        # dedup: check existing by (niche, buyer_name)
        r = sb.table("buyers").select("id,is_active").eq("niche", b["niche"]).eq("buyer_name", b["buyer_name"]).limit(1).execute()
        if r.data:
            # reactivate + update
            sb.table("buyers").update({
                "sub_niche": b["sub_niche"],
                "is_active": True,
                "priority": b["priority"],
                "notes": f"Auto-seeded {datetime.now(timezone.utc).isoformat()}. Set destination_phone from vonage dashboard to activate routing.",
            }).eq("id", r.data[0]["id"]).execute()
            updated += 1
            print(f"  updated: {b['buyer_name']}")
        else:
            row = {
                **b,
                "destination_phone": None,
                "is_active": True,
                "base_payout": 0,
                "fee_rate": 0,
                "notes": f"Auto-seeded {datetime.now(timezone.utc).isoformat()}. Set destination_phone from vonage dashboard to activate routing.",
            }
            sb.table("buyers").insert(row).execute()
            inserted += 1
            print(f"  inserted: {b['buyer_name']}")

    print(f"\nresult: {inserted} inserted, {updated} updated")
    print("next: set destination_phone from vonage dashboard for each active buyer.")


if __name__ == "__main__":
    main()