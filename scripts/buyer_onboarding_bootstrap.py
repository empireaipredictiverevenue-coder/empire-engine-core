#!/usr/bin/env python3
"""
Buyer Onboarding Bootstrap
==========================

Updates destination_phone and email for the 11 buyer lanes that are
blocking B2B outreach. Use this when you've purchased Vonage toll-free
numbers and have the buyer contact details.

Usage:
  1) Buy toll-free numbers in the Vonage dashboard (~$1-2/mo each).
     Required scopes: SMS, Voice. No 10DLC registration needed for TF.
  2) Email each buyer's contact to find their direct intake address.
     Or use the buyer_company_name + "@gmail.com" pattern.
  3) Create buyer_update.csv with this header + 11 rows:
        buyer_id,niche,sub_niche,destination_phone,email
        c7a45461-...,Mass Tort Legal,?,+18008675309,ops@firm.com
        ...
  4) Run:  python3 scripts/buyer_onboarding_bootstrap.py --dry-run
     Then: python3 scripts/buyer_onboarding_bootstrap.py --apply
  5) The next fee_collection cycle will route calls/SMS to the new numbers.

List of buyer_ids to update (11 lanes):
  c7a45461  Mass Tort Legal            / Class Action
  97480522  Insurance / Debt Consolidation
  f534b69e  Insurance / Medicare Advantage
  21d8471f  auto insurance
  75c3f2af  medical claims
  22d3805f  Insurance / Life Insurance
  6c887259  Insurance / Final Expense
  32dd5330  Legal / Class Action
  594c0df8  Legal / Consumer Product
  01836f40  Legal / Medical Device
  319d6da3  Legal / Pharma Liability
"""
import os, sys, csv, argparse
from pathlib import Path
sys.path.insert(0, str(Path("/root/empire-v49").resolve()))
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass
from supabase import create_client

CSV_PATH = "/root/empire-v49/data/buyer_update.csv"
EMAIL_ONLY_BUYER_IDS = [
    # 5 active buyers that we can't provision a phone for (Vonage 420).
    # They'll get email-only outreach via Resend. The hub will skip
    # SMS dispatch when destination_phone is null + email is set.
    "f534b69e-cb4d-455c-be29-4d169e1f0e1f",  # Insurance / Medicare Advantage
    "21d8471f-3308-485e-b0e1-7ad6d7b45034",  # auto insurance
    "75c3f2af-4d26-4a84-95f2-1c0a3a0b8c38",  # medical claims
    "22d3805f-9e33-4af0-933c-647529d72877",  # Insurance / Life Insurance
    "6c887259-2d60-401f-b9da-d7631ef96178",  # Insurance / Final Expense
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--list", action="store_true", help="print all 11 buyer_ids + current state")
    p.add_argument("--email-only", action="store_true", help="set Resend email on the 5 active buyers that can't get a phone (Vonage 420)")
    p.add_argument("--csv", default=CSV_PATH, help=f"path to CSV (default: {CSV_PATH})")
    args = p.parse_args()

    c = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    if args.email_only:
        # Set the Resend email fallback on buyers we couldn't provision
        # phones for. Uses a single ops inbox; Phil can forward manually
        # or set up email routing rules to the actual buyers later.
        # 2026-06-24: now dynamic — finds ALL active buyers with no phone
        # and no email, not just the hard-coded 5. Future placeholders
        # auto-activate without manual list maintenance.
        ops_email = os.environ.get("EMPIRE_OPS_EMAIL", "ops@empire-ai.co.uk")
        # Build the dynamic target list
        r = c.table("buyers").select("id,buyer_name,niche,sub_niche").eq("is_active", True).is_("destination_phone", "null").is_("email", "null").execute()
        targets = r.data or []
        # Combine with the legacy hard-coded list (covers any that became
        # inactive-then-reactivated)
        legacy_ids = set(EMAIL_ONLY_BUYER_IDS)
        legacy = c.table("buyers").select("id,buyer_name,niche,sub_niche").in_("id", list(legacy_ids)).execute()
        seen = set()
        combined = []
        for row in (targets + (legacy.data or [])):
            if row["id"] in seen: continue
            seen.add(row["id"])
            combined.append(row)
        if not combined:
            print("  no buyers need email-only mode")
            return
        for row in combined:
            c.table("buyers").update({"email": ops_email, "notes": "email-only mode (no 10DLC registration); for SMS route via toll-free number; see buyer_onboarding_bootstrap.py"}).eq("id", row["id"]).execute()
            print(f"  set email={ops_email} on {row['id'][:8]}  ({row.get('buyer_name','-')[:30]})")
        print(f"\n{len(combined)} buyers set to email-only mode")

    if args.list or (not args.dry_run and not args.apply):
        # List all buyers missing contact info
        r = c.table("buyers").select("id,buyer_name,niche,sub_niche,is_active,destination_phone,email,daily_cap").is_("destination_phone", "null").limit(20).execute()
        print("Buyers missing destination_phone:")
        for row in r.data or []:
            print(f"  {row['id']}  {row.get('niche','?')!r:25s} {row.get('sub_niche','?')!r:25s}  active={row.get('is_active')}  cap={row.get('daily_cap','?')}")
        return

    if not os.path.exists(args.csv):
        print(f"ERROR: {args.csv} not found")
        print(f"Create the CSV with header: buyer_id,niche,sub_niche,destination_phone,email")
        sys.exit(1)

    updated = 0
    with open(args.csv) as f:
        for row in csv.DictReader(f):
            bid = row["buyer_id"].strip()
            phone = row["destination_phone"].strip()
            email = row["email"].strip() or None
            update = {"destination_phone": phone}
            if email: update["email"] = email
            if args.dry_run:
                print(f"  WOULD update {bid[:8]}: phone={phone} email={email}")
            else:
                c.table("buyers").update(update).eq("id", bid).execute()
                print(f"  UPDATED {bid[:8]}: phone={phone} email={email}")
                updated += 1
    if not args.dry_run:
        print(f"\n{updated} buyers updated. Next fee_collection cycle will route to new numbers.")

if __name__ == "__main__":
    main()
