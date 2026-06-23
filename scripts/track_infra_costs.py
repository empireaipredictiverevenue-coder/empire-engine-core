#!/usr/bin/env python3
"""
EMPIRE V49 · INFRASTRUCTURE COST TRACKER
==========================================
Estimates and records infrastructure costs to empire_revenue_ledger for a
unified profit/loss view alongside revenue data.

Cost sources tracked:
  - Supabase       (flat monthly subscription)
  - Hetzner server (flat monthly hosting — runs Ollama, PM2, hub, brain)
  - Vonage SMS     (per-message outbound)
  - Vonage Voice   (per-minute billable)
  - AI inference   (per-call from ai_call_log.cost_usd)

All costs can be overridden via env vars:
    SUPABASE_MONTHLY_COST=25        (USD, default 25)
    HETZNER_MONTHLY_COST=67         (USD, default ~€57/mo for dedicated AX41)
    VONAGE_SMS_COST_PER=0.008       (USD per outbound SMS, default 0.008)
    VONAGE_VOICE_COST_PER_MINUTE=0.012  (USD per minute, default 0.012)

Modes:
    --daily           Record costs for yesterday (default)
    --month-to-date   Record costs from 1st of month through yesterday
    --dry-run         Report only — no writes
    --force           Re-record even if already recorded

Examples:
    python3 scripts/track_infra_costs.py                      # daily (default)
    python3 scripts/track_infra_costs.py --month-to-date      # full month
    python3 scripts/track_infra_costs.py --dry-run            # preview
    python3 scripts/track_infra_costs.py --month-to-date --force  # re-record
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("track_infra_costs")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [infra-costs] %(levelname)s %(message)s",
)

AGENT_NAME = "track_infra_costs"

# ── Config (overridable via env vars) ───────────────────────────────────
CONFIG = {
    "supabase": {
        "label": "Supabase",
        "cost_category": "subscription",
        "monthly_cost": float(os.environ.get("SUPABASE_MONTHLY_COST", "25")),
    },
    "hetzner": {
        "label": "Hetzner (Dedicated Server)",
        "cost_category": "subscription",
        "monthly_cost": float(os.environ.get("HETZNER_MONTHLY_COST", "67")),  # ~€57/mo = ~$67 AX41 dedi
    },
    "vonage_sms": {
        "label": "Vonage SMS",
        "cost_category": "usage",
        "cost_per": float(os.environ.get("VONAGE_SMS_COST_PER", "0.008")),  # per outbound SMS
    },
    "vonage_voice": {
        "label": "Vonage Voice",
        "cost_category": "usage",
        "cost_per_minute": float(os.environ.get("VONAGE_VOICE_COST_PER_MINUTE", "0.012")),
    },
    "ai_inference": {
        "label": "AI Inference",
        "cost_category": "inference",
        # cost is read from ai_call_log.cost_usd directly
    },
    "resend": {
        "label": "Resend (Email)",
        "cost_category": "subscription",
        "monthly_cost": float(os.environ.get("RESEND_MONTHLY_COST", "0")),
        # Resend free tier up to 100 emails/day; base plan starts at $0/mo
        # Override via RESEND_MONTHLY_COST env var for paid tiers
    },
    "minimax": {
        "label": "MiniMax AI",
        "cost_category": "subscription",
        "monthly_cost": float(os.environ.get("MINIMAX_MONTHLY_COST", "0")),
        # MiniMax pay-as-you-go token pricing
        # Override via MINIMAX_MONTHLY_COST env var
    },
}


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _already_recorded(sb, source_id: str, period_label: str) -> bool:
    """Check if a cost entry already exists for this service + period."""
    r = sb.table("empire_revenue_ledger") \
        .select("id") \
        .eq("source_type", "infra_cost") \
        .eq("source_id", source_id) \
        .eq("description", period_label) \
        .limit(1).execute()
    return len(r.data or []) > 0


def _record_cost(sb, source_id: str, label: str, cost_category: str,
                 amount: float, description: str, block_time: str,
                 dry_run: bool, force: bool) -> bool:
    """Record a single cost entry. Returns True if inserted."""
    if amount <= 0:
        return False

    if not force and _already_recorded(sb, source_id, description):
        log.info(f"  ⏭  {label}: already recorded for this period (use --force to re-record)")
        return False

    if dry_run:
        log.info(f"  [DRY-RUN] {label}: ${amount:.2f} — {description}")
        return True

    entry = {
        "status":            "accrued",
        "source_type":       "infra_cost",
        "source_id":         source_id,
        "cost_category":     cost_category,
        "amount":            round(amount, 6),
        "usdc_amount":       0,  # not USDC, just tracking in USD
        "description":       description,
        "sender_address":    f"infra:{source_id}",
        "destination_address": "infra:system",
        "tracking_memo":     f"cost:{source_id}",
        "block_time_stamp":  block_time,
        "logged_at":         datetime.now(timezone.utc).isoformat(),
        "meta": {
            "service": source_id,
            "cost_category": cost_category,
            "amount_usd": round(amount, 2),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    try:
        sb.table("empire_revenue_ledger").insert(entry).execute()
        log.info(f"  ✓ {label}: ${amount:.2f} — {description}")
        return True
    except Exception as e:
        log.warning(f"  ✗ Failed to record {label}: {e}")
        return False


def _record_subscription_costs(sb, period_start: date, period_end: date,
                               period_label: str, dry_run: bool,
                               force: bool) -> dict:
    """Record flat monthly subscription costs (Supabase, Ollama)."""
    results = {}
    for key, cfg in CONFIG.items():
        if cfg.get("cost_category") != "subscription":
            continue
        monthly = cfg["monthly_cost"]
        # Prorate: (days in period) / (days in month)
        if period_start.month == period_end.month:
            month_days = (date(period_end.year, period_end.month + 1, 1) - timedelta(days=1)).day \
                if period_end.month < 12 else 31
            days_in_period = (period_end - period_start).days + 1
            prorated = monthly * days_in_period / month_days
        else:
            prorated = monthly  # cross-month fallback

        ok = _record_cost(
            sb=sb,
            source_id=key,
            label=cfg["label"],
            cost_category=cfg["cost_category"],
            amount=prorated,
            description=period_label,
            block_time=period_end.isoformat(),
            dry_run=dry_run,
            force=force,
        )
        results[key] = {"amount": round(prorated, 2), "recorded": ok}
    return results


def _record_usage_costs(sb, period_start: date, period_end: date,
                        period_label: str, dry_run: bool,
                        force: bool) -> dict:
    """Record usage-based costs (Vonage SMS, Vonage Voice, AI inference)."""
    results = {}
    cutoff_start = datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    cutoff_end = datetime.combine(period_end, datetime.max.time(), tzinfo=timezone.utc).isoformat()

    # ── Vonage SMS ─────────────────────────────────────────────────
    try:
        r = sb.table("sms_log") \
            .select("id") \
            .eq("direction", "outbound") \
            .gte("created_at", cutoff_start) \
            .lte("created_at", cutoff_end) \
            .execute()
        sms_count = len(r.data or [])
        cost = sms_count * CONFIG["vonage_sms"]["cost_per"]
        ok = _record_cost(
            sb=sb, source_id="vonage_sms",
            label=CONFIG["vonage_sms"]["label"],
            cost_category=CONFIG["vonage_sms"]["cost_category"],
            amount=cost,
            description=f"{period_label} ({sms_count} outbound SMS × ${CONFIG['vonage_sms']['cost_per']:.4f})",
            block_time=period_end.isoformat(),
            dry_run=dry_run,
            force=force,
        )
        results["vonage_sms"] = {"count": sms_count, "amount": round(cost, 2), "recorded": ok}
    except Exception as e:
        log.warning(f"  ⚠  Vonage SMS query failed: {e}")
        results["vonage_sms"] = {"count": 0, "amount": 0, "recorded": False}

    # ── Vonage Voice ───────────────────────────────────────────────
    try:
        r = sb.table("call_logs") \
            .select("duration_seconds") \
            .gte("created_at", cutoff_start) \
            .lte("created_at", cutoff_end) \
            .execute()
        call_data = r.data or []
        total_seconds = sum(int(d.get("duration_seconds", 0) or 0) for d in call_data)
        total_minutes = total_seconds / 60.0
        cost = total_minutes * CONFIG["vonage_voice"]["cost_per_minute"]
        ok = _record_cost(
            sb=sb, source_id="vonage_voice",
            label=CONFIG["vonage_voice"]["label"],
            cost_category=CONFIG["vonage_voice"]["cost_category"],
            amount=cost,
            description=f"{period_label} ({len(call_data)} calls, {total_minutes:.1f} min × ${CONFIG['vonage_voice']['cost_per_minute']:.4f}/min)",
            block_time=period_end.isoformat(),
            dry_run=dry_run,
            force=force,
        )
        results["vonage_voice"] = {"calls": len(call_data), "minutes": round(total_minutes, 1),
                                    "amount": round(cost, 2), "recorded": ok}
    except Exception as e:
        log.warning(f"  ⚠  Vonage Voice query failed: {e}")
        results["vonage_voice"] = {"calls": 0, "minutes": 0, "amount": 0, "recorded": False}

    # ── AI Inference ───────────────────────────────────────────────
    try:
        r = sb.table("ai_call_log") \
            .select("cost_usd") \
            .gte("created_at", cutoff_start) \
            .lte("created_at", cutoff_end) \
            .execute()
        ai_data = r.data or []
        total_cost_usd = sum(float(d.get("cost_usd", 0) or 0) for d in ai_data)
        ok = _record_cost(
            sb=sb, source_id="ai_inference",
            label=CONFIG["ai_inference"]["label"],
            cost_category=CONFIG["ai_inference"]["cost_category"],
            amount=total_cost_usd,
            description=f"{period_label} ({len(ai_data)} inference calls)",
            block_time=period_end.isoformat(),
            dry_run=dry_run,
            force=force,
        )
        results["ai_inference"] = {"calls": len(ai_data), "amount": round(total_cost_usd, 2), "recorded": ok}
    except Exception as e:
        log.warning(f"  ⚠  AI Inference query failed: {e}")
        results["ai_inference"] = {"calls": 0, "amount": 0, "recorded": False}

    return results


def run_track(
    mode: str = "daily",
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Run the infrastructure cost tracker.

    Args:
        mode: 'daily' (yesterday) or 'month-to-date' (1st through yesterday)
        dry_run: Report only — no writes
        force: Re-record even if already recorded
    """
    sb = _sb()
    started_at = datetime.now(timezone.utc)
    today = date.today()

    if mode == "month-to-date":
        period_start = date(today.year, today.month, 1)
        period_end = today - timedelta(days=1)  # through yesterday
        if period_end < period_start:
            period_end = period_start
            log.info("First day of month — recording 1 day")
    else:
        period_start = today - timedelta(days=1)
        period_end = today - timedelta(days=1)

    period_label = f"{period_start.isoformat()}–{period_end.isoformat()}"
    log.info(f"=== INFRASTRUCTURE COST TRACKER ===")
    log.info(f"Period: {period_label}")
    log.info(f"Mode:   {'MONTH-TO-DATE' if mode == 'month-to-date' else 'DAILY'}")
    if dry_run:
        log.info("DRY-RUN MODE — no writes will be performed")

    # ── 1. Subscription costs ───────────────────────────────────────────
    log.info("--- Subscription Costs ---")
    sub_results = _record_subscription_costs(
        sb, period_start, period_end, period_label, dry_run, force,
    )

    # ── 2. Usage costs ──────────────────────────────────────────────────
    log.info("--- Usage Costs ---")
    usage_results = _record_usage_costs(
        sb, period_start, period_end, period_label, dry_run, force,
    )

    # ── 3. Summary ──────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    all_results = {**sub_results, **usage_results}
    total_recorded = sum(1 for v in all_results.values() if v.get("recorded"))
    total_cost = sum(v.get("amount", 0) for v in all_results.values())

    log.info("=== SUMMARY ===")
    log.info(f"Period:   {period_label}")
    log.info(f"Mode:     {mode}")
    log.info(f"Dry-run:  {dry_run}")
    log.info(f"Total:    ${total_cost:.2f} across {total_recorded} services")
    for key, res in sorted(all_results.items()):
        if res.get("recorded", False):
            log.info(f"  ✓ {CONFIG[key]['label']}: ${res['amount']:.2f}")
        else:
            label = CONFIG.get(key, {}).get("label", key)
            log.info(f"  - {label}: ${res['amount']:.2f} (skipped)")
    log.info(f"Elapsed:  {elapsed:.1f}s")

    summary = {
        "period": period_label,
        "mode": mode,
        "dry_run": dry_run,
        "services_recorded": total_recorded,
        "total_cost_usd": round(total_cost, 2),
        "breakdown": {k: {"label": CONFIG.get(k, {}).get("label", k), **v}
                      for k, v in all_results.items()},
        "elapsed_seconds": round(elapsed, 1),
    }

    return summary


def main():
    p = argparse.ArgumentParser(
        description="Infrastructure Cost Tracker — record infra costs to empire_revenue_ledger"
    )
    p.add_argument("--daily", action="store_true",
                    help="Record costs for yesterday (default)")
    p.add_argument("--month-to-date", action="store_true",
                    help="Record costs from 1st of month through yesterday")
    p.add_argument("--dry-run", action="store_true",
                    help="Report only — no writes")
    p.add_argument("--force", action="store_true",
                    help="Re-record even if already recorded")
    args = p.parse_args()

    mode = "month-to-date" if args.month_to_date else "daily"

    result = run_track(
        mode=mode,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
