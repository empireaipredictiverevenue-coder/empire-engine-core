"""
EMPIRE V49 · ROI CALCULATOR
============================
Live ROI estimates based on real contractor data from Supabase.
Queries contractors, carrier_claims, fee_events, dispatches,
and empire_revenue_ledger to compute actionable ROI metrics.

Used by the /api/v1/calculator/roi endpoint.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

log = logging.getLogger("empire.roi")


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


async def roi_calculator_json(get_db) -> Dict:
    """Query live Supabase data and return a comprehensive ROI snapshot.

    Returns dict with:
      - summary: high-level KPI cards
      - fees: fee collection metrics
      - claims: claim lifecycle metrics
      - dispatches: dispatch pipeline metrics
      - contractors: contractor network stats
      - revenue_ledger: revenue-by-source breakdown
      - metro_breakdown: contractors per metro
      - monthly_fees: fee time series
      - timestamp: ISO timestamp
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    result: Dict[str, Any] = {
        "summary": {},
        "fees": {},
        "claims": {},
        "dispatches": {},
        "contractors": {},
        "revenue_ledger": {},
        "metro_breakdown": [],
        "monthly_fees": [],
        "timestamp": now.isoformat(),
    }

    # ── CONTRACTORS ─────────────────────────────────────────────────
    contractors = []
    try:
        r = db.table("contractors").select("id,active,trust_score,completed_jobs,metro,specialties,niche").execute()
        contractors = r.data or []
        total_contractors = len(contractors)
        active_count = sum(1 for c in contractors if c.get("active") is True)
        avg_trust = 0.0
        total_completed = 0
        metro_map: Dict[str, int] = defaultdict(int)
        if contractors:
            scores = [_safe_float(c.get("trust_score")) for c in contractors]
            avg_trust = round(sum(scores) / len(scores), 2)
            total_completed = sum(_safe_int(c.get("completed_jobs")) for c in contractors)
            for c in contractors:
                m = (c.get("metro") or "").strip()
                if m:
                    metro_map[m] += 1

        # Top 15 metros
        metro_sorted = sorted(metro_map.items(), key=lambda x: -x[1])[:15]
        metro_breakdown = [{"metro": m, "count": c} for m, c in metro_sorted]

        result["contractors"] = {
            "total": total_contractors,
            "active": active_count,
            "inactive": total_contractors - active_count,
            "avg_trust_score": avg_trust,
            "total_completed_jobs": total_completed,
            "onboarded_with_email": sum(1 for c in contractors if c.get("email")),
            "onboarded_with_phone": sum(1 for c in contractors if c.get("phone")),
        }
        result["metro_breakdown"] = metro_breakdown
    except Exception as e:
        log.warning(f"[roi] contractors query failed: {e}")

    # ── CARRIER CLAIMS ──────────────────────────────────────────────
    try:
        r = db.table("carrier_claims").select("id,status,asset_value,settled_amount,filed_at,settled_at,created_at").execute()
        claims = r.data or []
        total_claims = len(claims)
        settled = [c for c in claims if c.get("status") == "settled"]
        pending = [c for c in claims if c.get("status") in ("open", "filed", "processing")]
        closed_lost = [c for c in claims if c.get("status") in ("closed", "lost", "denied")]

        settled_amounts = [_safe_float(c.get("settled_amount")) for c in settled]
        total_settled_amount = sum(settled_amounts)
        avg_settled = round(total_settled_amount / len(settled_amounts), 2) if settled_amounts else 0.0

        asset_values = [_safe_float(c.get("asset_value")) for c in claims if c.get("asset_value")]
        avg_asset_value = round(sum(asset_values) / len(asset_values), 2) if asset_values else 0.0

        # Claims filed in last 30 days
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        recent_claims = [c for c in claims if (c.get("created_at") or "") >= thirty_days_ago]

        # Settlement rate (settled / (settled + closed_lost))
        resolvable = len(settled) + len(closed_lost)
        settlement_rate = round(len(settled) / resolvable, 3) if resolvable > 0 else 0.0

        result["claims"] = {
            "total": total_claims,
            "settled": len(settled),
            "pending": len(pending),
            "closed_lost": len(closed_lost),
            "recent_30d": len(recent_claims),
            "total_settled_amount": round(total_settled_amount, 2),
            "avg_settled_amount": avg_settled,
            "avg_asset_value": avg_asset_value,
            "settlement_rate": settlement_rate,
        }
    except Exception as e:
        log.warning(f"[roi] claims query failed: {e}")

    # ── FEE EVENTS ──────────────────────────────────────────────────
    try:
        r = db.table("fee_events").select("id,claim_id,contractor_id,claim_amount,fee_amount,fee_percent,status,created_at,settled_at").execute()
        fees = r.data or []
        total_fees = len(fees)
        collected = [f for f in fees if f.get("status") == "collected"]
        pending_fees = [f for f in fees if f.get("status") in ("pending", "offered")]
        discounted = [f for f in fees if f.get("status") == "discounted"]
        voided = [f for f in fees if f.get("status") == "voided"]

        fee_amounts = [_safe_float(f.get("fee_amount")) for f in fees]
        total_fee_amount = sum(fee_amounts)
        collected_amount = sum(_safe_float(f.get("fee_amount")) for f in collected)
        pending_amount = sum(_safe_float(f.get("fee_amount")) for f in pending_fees)

        collection_rate = round(len(collected) / total_fees, 3) if total_fees > 0 else 0.0

        # Monthly fee time series
        monthly_buckets: Dict[str, Dict] = defaultdict(lambda: {"month": "", "fees": 0, "count": 0, "collected": 0, "collected_amount": 0.0})
        for f in fees:
            created = (f.get("created_at") or "")[:7]
            if created:
                b = monthly_buckets[created]
                b["month"] = created
                b["fees"] += _safe_float(f.get("fee_amount"))
                b["count"] += 1
                if f.get("status") == "collected":
                    b["collected"] += 1
                    b["collected_amount"] += _safe_float(f.get("fee_amount"))

        monthly_fees = sorted(monthly_buckets.values(), key=lambda x: x["month"])
        for m in monthly_fees:
            m["fees"] = round(m["fees"], 2)
            m["collected_amount"] = round(m["collected_amount"], 2)

        avg_fee_pct = 0.0
        if fee_amounts and total_fee_amount > 0:
            pcts = [_safe_float(f.get("fee_percent")) for f in fees if f.get("fee_percent") is not None]
            avg_fee_pct = round(sum(pcts) / len(pcts), 2) if pcts else 3.0

        result["fees"] = {
            "total": total_fees,
            "collected": len(collected),
            "pending": len(pending_fees),
            "discounted": len(discounted),
            "voided": len(voided),
            "total_fee_amount": round(total_fee_amount, 2),
            "collected_amount": round(collected_amount, 2),
            "pending_amount": round(pending_amount, 2),
            "collection_rate": collection_rate,
            "avg_fee_percent": avg_fee_pct,
            "fee_events_per_contractor": round(total_fees / max(len(contractors), 1), 4),
        }
        result["monthly_fees"] = monthly_fees
    except Exception as e:
        log.warning(f"[roi] fee_events query failed: {e}")

    # ── DISPATCHES ──────────────────────────────────────────────────
    try:
        r = db.table("dispatches").select("id,contractor_id,status,match_score,created_at,accepted_at,completed_at,payout_amount").execute()
        dispatches = r.data or []
        total_dispatches = len(dispatches)
        sent = [d for d in dispatches if d.get("status") == "sent"]
        accepted = [d for d in dispatches if d.get("status") == "accepted"]
        completed = [d for d in dispatches if d.get("status") == "completed"]
        ghosted = [d for d in dispatches if d.get("status") == "ghosted"]
        rejected = [d for d in dispatches if d.get("status") == "rejected"]

        accept_rate = round(len(accepted) / total_dispatches, 3) if total_dispatches > 0 else 0.0
        completion_rate = round(len(completed) / len(accepted), 3) if accepted else 0.0
        ghost_rate = round(len(ghosted) / total_dispatches, 3) if total_dispatches > 0 else 0.0

        payout_amounts = [_safe_float(d.get("payout_amount")) for d in dispatches if d.get("payout_amount")]
        total_payouts = sum(payout_amounts)
        avg_payout = round(total_payouts / len(payout_amounts), 2) if payout_amounts else 0.0

        # Dispatches in last 30 days
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        recent_dispatches = [d for d in dispatches if (d.get("created_at") or "") >= thirty_days_ago]

        # Dispatch-to-claim conversion
        dispatch_claim_ratio = 0.0
        if total_claims > 0 and total_dispatches > 0:
            dispatch_claim_ratio = round(total_claims / total_dispatches, 3)

        result["dispatches"] = {
            "total": total_dispatches,
            "sent": len(sent),
            "accepted": len(accepted),
            "completed": len(completed),
            "ghosted": len(ghosted),
            "rejected": len(rejected),
            "recent_30d": len(recent_dispatches),
            "acceptance_rate": accept_rate,
            "completion_rate": completion_rate,
            "ghost_rate": ghost_rate,
            "total_payouts": round(total_payouts, 2),
            "avg_payout_per_dispatch": avg_payout,
            "dispatch_to_claim_ratio": dispatch_claim_ratio,
        }
    except Exception as e:
        log.warning(f"[roi] dispatches query failed: {e}")

    # ── REVENUE LEDGER ──────────────────────────────────────────────
    try:
        r = db.table("empire_revenue_ledger").select("source_type,amount,usdc_amount,cost_category,description,logged_at,status").execute()
        ledger = r.data or []
        total_ledger_amount = sum(_safe_float(l.get("amount")) for l in ledger)
        total_ledger_usdc = sum(_safe_float(l.get("usdc_amount")) for l in ledger)

        # Revenue vs cost
        revenue_entries = [l for l in ledger if not l.get("cost_category")]
        cost_entries = [l for l in ledger if l.get("cost_category")]

        total_revenue = sum(_safe_float(l.get("amount")) for l in revenue_entries)
        total_costs = sum(_safe_float(l.get("amount")) for l in cost_entries)

        # Accrued vs settled breakdown
        settled_revenue = sum(_safe_float(l.get("amount")) for l in revenue_entries if (l.get("status") or "").strip() == "settled")
        accrued_revenue = sum(_safe_float(l.get("amount")) for l in revenue_entries if (l.get("status") or "").strip() != "settled")

        # By source type
        source_buckets: Dict[str, Dict] = {}
        for l in ledger:
            st = (l.get("source_type") or "unknown").strip()
            amt = _safe_float(l.get("amount"))
            if st not in source_buckets:
                source_buckets[st] = {"source_type": st, "count": 0, "total_amount": 0.0}
            source_buckets[st]["count"] += 1
            source_buckets[st]["total_amount"] += amt

        sources = sorted(source_buckets.values(), key=lambda x: -x["total_amount"])
        for s in sources:
            s["total_amount"] = round(s["total_amount"], 2)

        # Monthly revenue from ledger
        monthly_ledger: Dict[str, Dict] = defaultdict(lambda: {"month": "", "revenue": 0.0, "costs": 0.0})
        for l in ledger:
            logged = (l.get("logged_at") or "")[:7]
            if logged:
                b = monthly_ledger[logged]
                b["month"] = logged
                amt = _safe_float(l.get("amount"))
                if l.get("cost_category"):
                    b["costs"] += amt
                else:
                    b["revenue"] += amt

        monthly_ledger_sorted = sorted(monthly_ledger.values(), key=lambda x: x["month"])
        for m in monthly_ledger_sorted:
            m["revenue"] = round(m["revenue"], 2)
            m["costs"] = round(m["costs"], 2)

        result["revenue_ledger"] = {
            "total_rows": len(ledger),
            "total_amount": round(total_ledger_amount, 2),
            "total_usdc": round(total_ledger_usdc, 2),
            "total_revenue": round(total_revenue, 2),
            "total_costs": round(total_costs, 2),
            "net_profit": round(total_revenue - total_costs, 2),
            "settled_revenue": round(settled_revenue, 2),
            "accrued_revenue": round(accrued_revenue, 2),
            "revenue_sources": len(revenue_entries),
            "cost_sources": len(cost_entries),
            "by_source_type": sources,
            "monthly_ledger": monthly_ledger_sorted,
        }
    except Exception as e:
        log.warning(f"[roi] revenue_ledger query failed: {e}")

    # ── SUMMARY CARDS ───────────────────────────────────────────────
    total_fees_amount = result.get("fees", {}).get("total_fee_amount", 0)
    collected_amount = result.get("fees", {}).get("collected_amount", 0)
    pending_amount_val = result.get("fees", {}).get("pending_amount", 0)
    total_claims_count = result.get("claims", {}).get("total", 0)
    settled_count = result.get("claims", {}).get("settled", 0)
    total_settled = result.get("claims", {}).get("total_settled_amount", 0)
    active_count_val = result.get("contractors", {}).get("active", 0)
    total_dispatch_count = result.get("dispatches", {}).get("total", 0)
    total_payouts_val = result.get("dispatches", {}).get("total_payouts", 0)
    net_profit_val = result.get("revenue_ledger", {}).get("net_profit", 0)
    ledger_revenue = result.get("revenue_ledger", {}).get("total_revenue", 0)

    # Estimate monthly revenue run rate from ledger if we have enough data
    monthly_run_rate = 0.0
    monthly_ledger_data = result.get("revenue_ledger", {}).get("monthly_ledger", [])
    if len(monthly_ledger_data) >= 1:
        # Use last complete month or average of available months
        recent_revs = [m["revenue"] for m in monthly_ledger_data if m["revenue"] > 0]
        if recent_revs:
            monthly_run_rate = round(sum(recent_revs) / len(recent_revs), 2)

    result["summary"] = {
        "total_contractors": result.get("contractors", {}).get("total", 0),
        "active_contractors": active_count_val,
        "total_claims": total_claims_count,
        "settled_claims": settled_count,
        "total_settled_amount": round(total_settled, 2),
        "total_fee_events": result.get("fees", {}).get("total", 0),
        "fees_collected": collected_amount,
        "fees_pending": pending_amount_val,
        "fee_collection_rate": result.get("fees", {}).get("collection_rate", 0),
        "total_dispatches": total_dispatch_count,
        "dispatch_acceptance_rate": result.get("dispatches", {}).get("acceptance_rate", 0),
        "total_payouts": total_payouts_val,
        "ledger_revenue": ledger_revenue,
        "ledger_costs": result.get("revenue_ledger", {}).get("total_costs", 0),
        "net_profit": net_profit_val,
        "monthly_run_rate_est": monthly_run_rate,
        "avg_fee_per_claim": round(total_fees_amount / total_claims_count, 2) if total_claims_count > 0 else 0.0,
        "revenue_per_contractor": round(ledger_revenue / active_count_val, 2) if active_count_val > 0 else 0.0,
    }

    return result
