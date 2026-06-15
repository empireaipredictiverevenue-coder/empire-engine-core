"""
Empire AI · Predictive Revenue
Fee Watcher — Manual Trigger
==============================

Manual way to push a settled-claim event through the fee pipeline.
Used until a real claim event source (webhook or polling) is wired.

In production, a real carrier or operator would call this with the actual
claim data. For now, this lets us prove the chain end-to-end.

Usage:
    python3 -m agents.fee_watcher.trigger --claim-amount 50000 --contractor-id <uuid> --lead-id <uuid>
    python3 -m agents.fee_watcher.trigger --claim-amount 50000 --contractor-id <uuid>  # lead optional
"""
import os, sys, argparse
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from supabase import create_client


def main():
    p = argparse.ArgumentParser(description="Manually trigger a settled-claim fee event")
    p.add_argument("--claim-amount", type=float, required=True, help="Total claim amount in USD")
    p.add_argument("--contractor-id", help="UUID of the contractor (optional)")
    p.add_argument("--lead-id", help="UUID of the enriched_lead (optional)")
    p.add_argument("--claim-id", help="External claim reference (default: synthetic)")
    p.add_argument("--dry-run", action="store_true", help="Don't write, just compute and show")
    args = p.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    fee = round(args.claim_amount * 0.03, 2)
    claim = {
        "id": args.claim_id or f"synth-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "contractor_id": args.contractor_id,
        "lead_id": args.lead_id,
        "amount": args.claim_amount,
        "settled_at": datetime.now(timezone.utc).isoformat(),
    }
    fee_event = {
        "claim_id": claim["id"],
        "contractor_id": claim["contractor_id"],
        "lead_id": claim["lead_id"],
        "claim_amount": claim["amount"],
        "fee_amount": fee,
        "fee_percent": 0.03,
        "currency": "USD",
        "settled_at": claim["settled_at"],
        "source": "fee_watcher_trigger",
        "status": "pending",
    }
    if args.dry_run:
        print("[DRY-RUN] would create fee_event:")
        print("  " + str(fee_event))
        return
    r = sb.table("fee_events").insert(fee_event).execute()
    print("fee_event created:")
    print("  id: " + (r.data[0].get("id","") if r.data else "?"))
    print("  claim_id: " + fee_event["claim_id"])
    print("  claim_amount: $" + str(fee_event["claim_amount"]))
    print("  fee_amount: $" + str(fee_event["fee_amount"]))
    print("  status: " + fee_event["status"])


if __name__ == "__main__":
    main()
