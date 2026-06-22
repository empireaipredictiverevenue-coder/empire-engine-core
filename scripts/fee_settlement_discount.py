"""
Empire AI · Fee Settlement Discount Engine
==========================================

Applies a one-time settlement discount to pending fee_events.

Strategy (operator-style, from /root/.hermes/skills/empire-ai-operator-style):
  - 20% off if paid within 7 days
  - Reasons contractors haven't paid: copy too long, ENS wallet too hard,
    no urgency, no "why now" reason. Discount + short URL solves both.
  - Tone: human, direct, slightly conversational. NOT AI-polished.

Usage:
  python3 scripts/fee_settlement_discount.py --offer --days 7 --percent 20
      # Applies 20% off, expires in 7 days, to ALL pending fee_events.
  python3 scripts/fee_settlement_discount.py --offer --fee-id <uuid> --days 7 --percent 20
      # Single fee only.
  python3 scripts/fee_settlement_discount.py --clear
      # Removes discount from all pending fees (rare).
  python3 scripts/fee_settlement_discount.py --status
      # Report on current discount state.

Once a discount is offered, the /pay/<claim_id> page will show the discounted
amount and the SMS body will lead with the savings.
"""
import os
import sys
import json
import uuid
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env")

from supabase import create_client

log = logging.getLogger("fee_settlement_discount")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

DEFAULT_DAYS = 7
DEFAULT_PERCENT = 20  # 20% off


def _normalize_pct(p: float) -> float:
    """Accept 0.20 or 20 and normalize to 0-1."""
    if p > 1.0:
        return p / 100.0
    return p


def apply_discount(sb, fee_id: str, percent: float, days: int) -> dict:
    """Apply a discount to a single fee_event. Idempotent: overwrites existing discount."""
    r = sb.table("fee_events").select("*").eq("id", fee_id).limit(1).execute()
    if not r.data:
        return {"ok": False, "error": "fee_event not found"}
    fee = r.data[0]
    if fee["status"] == "paid":
        return {"ok": False, "error": "already paid"}

    fee_amount = float(fee["fee_amount"])
    pct = _normalize_pct(percent)
    discount_amount = round(fee_amount * pct, 2)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    offered_at = datetime.now(timezone.utc).isoformat()

    upd = {
        "discount_percent": pct,
        "discount_amount": discount_amount,
        "discount_expires_at": expires_at,
        "discount_offered_at": offered_at,
        "meta": {**(fee.get("meta") or {}), "discount_history": [
            *((fee.get("meta") or {}).get("discount_history") or []),
            {
                "percent": pct,
                "amount": discount_amount,
                "expires_at": expires_at,
                "offered_at": offered_at,
            }
        ]},
    }
    sb.table("fee_events").update(upd).eq("id", fee_id).execute()
    return {
        "ok": True,
        "fee_id": fee_id,
        "claim_id": fee.get("claim_id"),
        "original_fee": fee_amount,
        "discount_percent": pct,
        "discount_amount": discount_amount,
        "discounted_fee": round(fee_amount - discount_amount, 2),
        "expires_at": expires_at,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--offer", action="store_true", help="apply discount")
    p.add_argument("--clear", action="store_true", help="remove discount from all pending fees")
    p.add_argument("--fee-id", type=str, help="apply to a single fee_event id")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS, help="days until expiry")
    p.add_argument("--percent", type=float, default=DEFAULT_PERCENT, help="discount percent (0-100 or 0-1)")
    p.add_argument("--status", action="store_true", help="print current discount state")
    args = p.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    if args.status:
        r = sb.table("fee_events").select(
            "id,claim_id,status,fee_amount,discount_percent,discount_amount,discount_expires_at"
        ).eq("status", "pending").execute()
        print(f"\n=== DISCOUNT STATE (pending fees) ===")
        if not r.data:
            print("(no pending fees)")
            return
        total_orig = 0
        total_disc = 0
        for x in r.data:
            orig = float(x.get("fee_amount") or 0)
            disc = float(x.get("discount_amount") or 0)
            pct = x.get("discount_percent")
            exp = x.get("discount_expires_at")
            claim = (x.get("claim_id") or "")[:24]
            label = f"${orig:,.0f}"
            if disc:
                label += f" -> ${orig-disc:,.0f} ({float(pct)*100:.0f}% off)"
            print(f"  {claim:24} {label:30} expires={exp or '-'}")
            total_orig += orig
            total_disc += disc
        print(f"\n  TOTALS: ${total_orig:,.2f} original | ${total_disc:,.2f} discount | ${total_orig-total_disc:,.2f} if all settle")
        return

    if args.clear:
        r = sb.table("fee_events").update({
            "discount_percent": None,
            "discount_amount": None,
            "discount_expires_at": None,
            "discount_offered_at": None,
        }).eq("status", "pending").execute()
        print(f"cleared discount on {len(r.data or [])} pending fees")
        return

    if not args.offer:
        p.error("--offer or --status or --clear required")

    pct = _normalize_pct(args.percent)
    if args.fee_id:
        r = sb.table("fee_events").select("id").eq("id", args.fee_id).limit(1).execute()
        if not r.data:
            print(f"fee not found: {args.fee_id}")
            sys.exit(1)
        ids = [args.fee_id]
    else:
        r = sb.table("fee_events").select("id").eq("status", "pending").execute()
        ids = [x["id"] for x in (r.data or [])]
        if not ids:
            print("no pending fees to discount")
            return

    print(f"applying {pct*100:.0f}% off (expires in {args.days}d) to {len(ids)} fee_events")
    print("-" * 70)
    results = []
    for fid in ids:
        r = apply_discount(sb, fid, pct, args.days)
        if r.get("ok"):
            print(f"  {r['claim_id'][:24]:24} ${r['original_fee']:,.0f} -> ${r['discounted_fee']:,.0f}  (saved ${r['discount_amount']:,.0f})  expires {r['expires_at'][:10]}")
        else:
            print(f"  {fid[:8]}: {r.get('error')}")
        results.append(r)

    paid = sum(1 for x in results if x.get("ok"))
    skipped = sum(1 for x in results if not x.get("ok"))
    print(f"\n{paid} offered, {skipped} skipped")
    print("\nNext: push the SMS + email + AI call so contractors see the offer before it expires.")


if __name__ == "__main__":
    main()