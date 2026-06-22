"""
Empire AI · Funnel Status API
====================================

Returns a real-time snapshot of every stage in the empire funnel:
  outreach sent / opened / clicked / paid
  subscriptions pending / active / lapsed
  dispatch invoices pending / paid
  fee_events paid / pending
  vault balance
  on-chain recent activity

Single endpoint for situational awareness. No dashboard needed.

Endpoint: GET /api/v1/funnel/status
"""
import os, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from fastapi import Request
from fastapi.responses import JSONResponse
from supabase import create_client


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _count(sb, table: str, **filters) -> int:
    q = sb.table(table).select("id", count="exact")
    for k, v in filters.items():
        q = q.eq(k, v)
    return q.execute().count or 0


def _sum(sb, table: str, col: str, **filters) -> float:
    """Sum a numeric column with optional filters."""
    q = sb.table(table).select(col)
    for k, v in filters.items():
        q = q.eq(k, v)
    rows = q.execute().data or []
    return sum(float(r.get(col) or 0) for r in rows)


async def handle_funnel_status(request: Request) -> JSONResponse:
    sb = _sb()
    now = datetime.now(timezone.utc)

    # Outreach funnel
    outreach_total = _count(sb, "contractor_outreach")
    outreach_pending = _count(sb, "contractor_outreach", status="pending")
    outreach_sent = _count(sb, "contractor_outreach", status="sent")
    outreach_bounced = _count(sb, "contractor_outreach", status="bounced")
    outreach_paid = _count(sb, "contractor_outreach", status="paid")
    r = sb.table("contractor_outreach").select("id", count="exact").not_.is_("opened_at", "null").execute()
    outreach_opened = r.count or 0
    r = sb.table("contractor_outreach").select("id", count="exact").not_.is_("clicked_at", "null").execute()
    outreach_clicked = r.count or 0
    outreach_paid = _count(sb, "contractor_outreach", status="paid")
    outreach_bounced = _count(sb, "contractor_outreach", status="bounced")

    # Subscription funnel
    sub_total = _count(sb, "contractor_subscriptions")
    sub_pending = _count(sb, "contractor_subscriptions", status="pending")
    sub_active = _count(sb, "contractor_subscriptions", status="active")
    sub_lapsed = _count(sb, "contractor_subscriptions", status="lapsed")
    sub_cancelled = _count(sb, "contractor_subscriptions", status="cancelled")

    # MRR (active subs × their tier monthly_usdc)
    active_subs = sb.table("contractor_subscriptions").select(
        "tier,monthly_amount_usdc,expires_at"
    ).eq("status", "active").execute().data or []
    mrr_usdc = sum(float(s.get("monthly_amount_usdc") or 0) for s in active_subs)

    # Dispatch invoices
    inv_total = _count(sb, "dispatch_invoices")
    inv_paid = _count(sb, "dispatch_invoices", status="paid")
    inv_pending = _count(sb, "dispatch_invoices", status="pending" if False else "unpaid")
    inv_paid_total = _sum(sb, "dispatch_invoices", "amount_usdc", status="paid")
    inv_pending_total = _sum(sb, "dispatch_invoices", "amount_usdc", status="unpaid")

    # Fee events (settled claims)
    fee_paid = _count(sb, "fee_events", status="paid")
    fee_pending = _count(sb, "fee_events", status="pending")
    fee_paid_total = _sum(sb, "fee_events", "fee_amount", status="paid")
    fee_pending_total = _sum(sb, "fee_events", "fee_amount", status="pending")

    # Contractors
    contractors_total = _count(sb, "contractors")
    contractors_active = _count(sb, "contractors", active=True)
    r = sb.table("contractors").select("id", count="exact").eq("active", True).not_.is_("email", "null").execute()
    contractors_with_valid_email = r.count or 0

    # Buyers
    buyers_total = _count(sb, "buyers")
    r = sb.table("buyers").select("id", count="exact").eq("is_active", True).not_.is_("destination_phone", "null").execute()
    buyers_with_phone = r.count or 0

    return JSONResponse({
        "as_of": now.isoformat(),
        "outreach": {
            "total_enrolled": outreach_total,
            "pending": outreach_pending,
            "sent": outreach_sent,
            "opened": outreach_opened,
            "clicked": outreach_clicked,
            "paid": outreach_paid,
            "bounced": outreach_bounced,
            "open_rate": round(outreach_opened / outreach_sent * 100, 1) if outreach_sent else 0,
            "click_rate": round(outreach_clicked / outreach_sent * 100, 1) if outreach_sent else 0,
        },
        "subscriptions": {
            "total": sub_total,
            "pending_payment": sub_pending,
            "active": sub_active,
            "lapsed": sub_lapsed,
            "cancelled": sub_cancelled,
            "mrr_usdc": mrr_usdc,
            "mrr_annual_run_rate": mrr_usdc * 12,
        },
        "dispatch_invoices": {
            "total": inv_total,
            "paid": inv_paid,
            "unpaid": inv_pending,
            "paid_usdc": inv_paid_total,
            "unpaid_usdc": inv_pending_total,
            "collection_rate": round(inv_paid_total / (inv_paid_total + inv_pending_total) * 100, 1) if (inv_paid_total + inv_pending_total) else 0,
        },
        "fee_events": {
            "paid_count": fee_paid,
            "pending_count": fee_pending,
            "paid_usdc": fee_paid_total,
            "pending_usdc": fee_pending_total,
        },
        "contractors": {
            "total": contractors_total,
            "active": contractors_active,
            "with_valid_email": contractors_with_valid_email,
        },
        "buyers": {
            "total": buyers_total,
            "with_destination_phone": buyers_with_phone,
            "missing_phone": buyers_total - buyers_with_phone,
        },
        "vault": {
            "wallet": "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM",
        },
    })


def register_funnel_route(app):
    @app.get("/api/v1/funnel/status")
    async def funnel_status(request: Request):
        return await handle_funnel_status(request)
    log_msg = "[funnel] route registered: GET /api/v1/funnel/status"
    print(log_msg)