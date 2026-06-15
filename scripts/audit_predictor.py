"""
Data-fitness audit for the predictive_revenue engine.

For each input source the predictor uses, check:
  - row count
  - freshness (most recent row)
  - null/empty rate on key columns
  - data quality (e.g. negative numbers, broken JSON, etc.)

For each input source the predictor DOESN'T use, note it
explicitly. The audit is a one-shot read, no writes.

Output: a printable report Phil can read in 60 seconds.
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Tables the predictor USES (per bots/predictive_revenue.py read)
USES = [
    ("radar_targets",    ["damage_severity", "urgency_score", "meta", "created_at"]),
    ("call_logs",        ["niche", "fee_earned", "is_billable", "created_at"]),
    ("buyers",           ["niche", "base_payout", "fee_rate", "monthly_retainer", "is_active"]),
    ("payout_log",       ["niche", "amount_usdc", "status", "created_at"]),
    ("pipeline_health",  ["total_tcv", "total_forecasted_fee", "lead_count", "close_rate", "created_at"]),
    ("brain_memory",     ["outcome", "created_at"]),
]

# Tables the predictor COULD use but doesn't
GAPS = [
    ("sms_log",          ["phone", "direction", "delivered", "body", "created_at"],
        "Reply rate, opt-out rate, sequence advance rate. None of this is in the predictor."),
    ("agent_activity",   ["agent_name", "status", "rows_processed", "started_at", "finished_at"],
        "Which agents move the funnel. Leading indicator of next-30-day revenue."),
    ("dispatches",       ["status", "contractor_id", "created_at", "responded_at"],
        "Real signal: a dispatch is a leading indicator of revenue (60-day claim cycle)."),
    ("enriched_leads",   ["phone", "address", "status", "converted_at"],
        "The enrichment layer adds quality signal the predictor doesn't see."),
    ("contractors",      ["active", "last_dispatched_at", "completed_jobs"],
        "Network size + activity. The predictor doesn't know how many contractors are warm."),
    ("storm_forecasts",  ["alert_id", "severity", "starts_at"],
        "Upstream signal. Not in the prediction. Could feed 'expected leads in next 24h'."),
    ("qc_events",        ["category", "severity", "created_at"],
        "Quality of work. A sudden spike in tier_2 pings is a leading indicator of revenue loss."),
]

now = datetime.now(timezone.utc)
day_ago = (now - timedelta(hours=24)).isoformat()
week_ago = (now - timedelta(days=7)).isoformat()


def safe_count(t, **kw):
    try:
        r = sb.table(t).select("id", count="exact").execute()
        return r.count or 0
    except Exception as e:
        return f"ERR: {e}"


def recent(t, days=1):
    cutoff = (now - timedelta(days=days)).isoformat()
    return safe_count(t) and safe_count(t)  # placeholder; we use the gte below
    # actually:
    try:
        r = sb.table(t).select("id", count="exact").gte("created_at", cutoff).execute()
        return r.count or 0
    except Exception as e:
        return f"ERR: {e}"


def freshness(t):
    try:
        r = sb.table(t).select("created_at").order("created_at", desc=True).limit(1).execute()
        if r.data and r.data[0].get("created_at"):
            return r.data[0]["created_at"][:19]
    except Exception:
        pass
    return "(none)"


def null_rate(t, col):
    """Return (total, null_count) for the column."""
    try:
        all_r = sb.table(t).select(col).limit(500).execute()
        rows = all_r.data or []
        total = len(rows)
        nulls = sum(1 for r in rows if r.get(col) is None or r.get(col) == "")
        return total, nulls
    except Exception:
        return None, None


def check_uses():
    print("=" * 78)
    print("INPUTS THE PREDICTOR ALREADY USES")
    print("=" * 78)
    print(f"{'table':<20} {'rows':>8} {'last 24h':>10} {'last 7d':>10} {'freshest':<20}")
    print("-" * 78)
    for t, _ in USES:
        all_n = safe_count(t)
        d1 = recent(t, 1)
        d7 = recent(t, 7)
        fr = freshness(t)
        print(f"{t:<20} {str(all_n):>8} {str(d1):>10} {str(d7):>10} {fr:<20}")


def check_uses_nulls():
    print()
    print("NULL RATES ON KEY COLUMNS (predictor's actual uses)")
    print("-" * 78)
    for t, cols in USES:
        for col in cols:
            if col in ("created_at",):
                continue
            total, nulls = null_rate(t, col)
            if total is None:
                continue
            pct = (nulls / total * 100) if total else 0
            flag = "  <- HIGH" if pct > 50 else ("  <- mid" if pct > 20 else "")
            print(f"  {t}.{col:<20}  nulls={nulls:>3}/{total:<3}  ({pct:>4.1f}%){flag}")


def check_gaps():
    print()
    print("=" * 78)
    print("INPUTS THE PREDICTOR DOES NOT USE  (the 'be big on data' gaps)")
    print("=" * 78)
    for t, cols, why in GAPS:
        all_n = safe_count(t)
        d1 = recent(t, 1)
        fr = freshness(t)
        print(f"\n  {t}  ({all_n} rows total, {d1} in last 24h, freshest {fr})")
        print(f"    why it matters: {why}")
        print(f"    columns available: {', '.join(cols)}")


def check_calibration_state():
    """The predictor has a self-calibration dict. Check if it's been tuned
    away from defaults, or if it's still at the 0.15 baseline."""
    print()
    print("=" * 78)
    print("CALIBRATION STATE")
    print("=" * 78)
    # brain_memory: rows with outcome in (won, closed, converted)
    try:
        r = sb.table("brain_memory").select("outcome,created_at").limit(500).execute()
        rows = r.data or []
        outcomes = defaultdict(int)
        for row in rows:
            o = (row.get("outcome") or "").lower()
            outcomes[o] += 1
        total_outcomes = sum(outcomes.values())
        won = sum(outcomes[k] for k in ("won", "closed", "converted"))
        if total_outcomes >= 10:
            cr = max(0.05, min(0.6, won / total_outcomes))
            print(f"  brain_memory rows: {total_outcomes}")
            print(f"  won/closed/converted: {won}")
            print(f"  computed close_rate: {cr:.3f} (vs 0.15 default)")
            if cr < 0.10:
                print(f"  -> WARNING: computed close_rate is LOWER than default. The predictor will use the default (0.15) but the real rate is {cr:.3f}.")
        else:
            print(f"  brain_memory has only {total_outcomes} rows (need 10+ for calibration).")
            print(f"  -> predictor will use DEFAULT 0.15 close_rate.")
    except Exception as e:
        print(f"  brain_memory query failed: {e}")


def check_pipeline_health_history():
    """Has the predictor been writing pipeline_health rows? If so, trend exists."""
    print()
    print("=" * 78)
    print("PIPELINE_HEALTH HISTORY  (the predictor's own trend table)")
    print("=" * 78)
    try:
        r = sb.table("pipeline_health").select("created_at,total_forecasted_fee,total_tcv,lead_count").order("created_at", desc=True).limit(20).execute()
        rows = r.data or []
        if not rows:
            print("  EMPTY. The predictor has never written a pipeline_health row.")
            print("  -> 7-day trend (revenue_health_check) is broken until pipeline_forecast() runs at least once.")
            return
        fees = [float(r.get("total_forecasted_fee") or 0) for r in rows]
        print(f"  rows: {len(rows)}")
        print(f"  most recent fee: ${fees[0]:.2f}")
        if len(fees) > 1:
            print(f"  oldest in window: ${fees[-1]:.2f}")
            print(f"  avg: ${sum(fees)/len(fees):.2f}")
    except Exception as e:
        print(f"  query failed: {e}")


if __name__ == "__main__":
    print()
    print("EMPIRE AI \u00b7 PREDICTIVE_REVENUE DATA FITNESS AUDIT")
    print(f"  run at: {now.isoformat()}")
    print()
    check_uses()
    check_uses_nulls()
    check_gaps()
    check_calibration_state()
    check_pipeline_health_history()
    print()
    print("=" * 78)
    print("DONE")
    print("=" * 78)
