"""
Empire AI · Predictive Revenue Forecasting
============================================

Analyzes historical revenue data from fee_events, empire_revenue_ledger,
and contractor_subscriptions to produce short-term revenue forecasts.

Forecast methods:
  - 7-day moving average (short-term trend)
  - Linear regression on daily aggregates (7/30/90 day outlook)
  - Minimum viable forecast (lower bound using worst 30 days)
  - MRR baseline from active subscriptions

Outputs:
  - Telegram digest to operator chat
  - Logs to agent_activity for SPA charting

Usage:
  python3 empire_revenue_predictive.py            # single run
  python3 empire_revenue_predictive.py --loop      # every 24h
  python3 empire_revenue_predictive.py --days 180  # override lookback
"""

import os
import sys
import json
import uuid
import argparse
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional, List, Tuple

sys.path.insert(0, str(Path("/root/empire-v49").resolve()))

try:
    from dotenv import load_dotenv
    for env_file in ("/root/.env", "/root/.hermes/.env"):
        try:
            load_dotenv(env_file)
        except Exception:
            pass
except Exception:
    pass

import httpx
from supabase import create_client

log = logging.getLogger("revenue_predictive")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [revenue-predictive] %(levelname)s %(message)s",
)

AGENT_NAME = "revenue_predictive"
DEFAULT_INTERVAL_SECONDS = 86400      # 24 hours
DEFAULT_LOOKBACK_DAYS = 90
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("OPERATOR_TELEGRAM_CHAT_ID", "808657420")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# ── Helpers ────────────────────────────────────────────────────────────────

def _sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


async def send_telegram(message: str) -> bool:
    """Send HTML message to operator chat. Best-effort."""
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set, skipping")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            ok = r.status_code == 200
            if not ok:
                log.warning(f"telegram send returned {r.status_code}: {r.text[:200]}")
            return ok
    except Exception as e:
        log.warning(f"telegram send error: {e}")
        return False


def log_to_agent_activity(started_at, status: str, summary: str) -> None:
    """Log forecast run to agent_activity table."""
    try:
        sb = _sb()
        sb.table("agent_activity").insert({
            "agent_name": AGENT_NAME,
            "run_id": str(uuid.uuid4()),
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "rows_seen": 0,
            "rows_processed": 0,
            "rows_errored": 0,
            "summary": summary[:500],
        }).execute()
    except Exception as e:
        log.error(f"failed to log to agent_activity: {e}")


# ── Statistical helpers (no external deps) ─────────────────────────────────

def linear_regression(xy: List[Tuple[float, float]]) -> Tuple[float, float, float]:
    """Return (slope, intercept, r_squared) for a list of (x, y) points."""
    n = len(xy)
    if n < 2:
        return 0.0, 0.0, 0.0
    sum_x = sum(p[0] for p in xy)
    sum_y = sum(p[1] for p in xy)
    sum_xy = sum(p[0] * p[1] for p in xy)
    sum_xx = sum(p[0] * p[0] for p in xy)
    mean_x = sum_x / n
    mean_y = sum_y / n
    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 0.0, mean_y, 0.0
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    # R²
    ss_tot = sum((p[1] - mean_y) ** 2 for p in xy)
    ss_res = sum((p[1] - (slope * p[0] + intercept)) ** 2 for p in xy)
    r_sq = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return slope, intercept, r_sq


def moving_average(values: List[float], window: int) -> Optional[float]:
    """Simple moving average of last `window` values."""
    if len(values) < 1:
        return None
    k = min(window, len(values))
    return sum(values[-k:]) / k


# ── Data fetching ──────────────────────────────────────────────────────────

def fetch_historical(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict:
    """Fetch historical revenue data and build daily time series."""
    sb = _sb()
    now = datetime.now(timezone.utc)
    lookback = (now - timedelta(days=lookback_days)).isoformat()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # ── fee_events (last N days) ──────────────────────────────────────
    r_fe = sb.table("fee_events") \
        .select("id,contractor_id,claim_amount,fee_amount,status,source,created_at") \
        .gte("created_at", lookback) \
        .order("created_at", desc=False) \
        .execute()
    fee_events = r_fe.data or []

    # ── empire_revenue_ledger (last N days) ──────────────────────────
    r_rl = sb.table("empire_revenue_ledger") \
        .select("transaction_signature,usdc_amount,status,block_time_stamp,logged_at") \
        .order("block_time_stamp", desc=False) \
        .limit(500) \
        .execute()
    ledger_rows = r_rl.data or []

    # ── contractor_subscriptions (all active/pending) ────────────────
    r_sub = sb.table("contractor_subscriptions") \
        .select("id,tier,monthly_amount_usdc,status,started_at,expires_at") \
        .execute()
    subscriptions = r_sub.data or []

    # ── Aggregate fee_events by day ───────────────────────────────────
    daily_fees = defaultdict(float)
    daily_fee_counts = defaultdict(int)
    for fe in fee_events:
        day = fe.get("created_at", "")[:10]
        amt = float(fe.get("fee_amount") or 0)
        status = fe.get("status", "")
        if day:
            daily_fees[day] += amt
            daily_fee_counts[day] += 1

    # ── Aggregate ledger by day ──────────────────────────────────────
    daily_ledger = defaultdict(float)
    for lr in ledger_rows:
        ts = lr.get("block_time_stamp") or lr.get("logged_at") or ""
        day = str(ts)[:10]
        amt = float(lr.get("usdc_amount") or 0)
        if day and amt > 0:
            daily_ledger[day] += amt

    # ── Merge into unified daily revenue ─────────────────────────────
    all_dates = set(list(daily_fees.keys()) + list(daily_ledger.keys()))
    daily_total = {}
    for d in sorted(all_dates):
        daily_total[d] = round(daily_fees.get(d, 0) + daily_ledger.get(d, 0), 2)

    # ── Compute rolling stats ────────────────────────────────────────
    daily_values = list(daily_total.values())
    daily_dates = list(daily_total.keys())

    # ── Subscription MRR ─────────────────────────────────────────────
    active_subs = [s for s in subscriptions if s.get("status") in ("active", "pending")]
    mrr_total = sum(float(s.get("monthly_amount_usdc") or 0) for s in active_subs)
    active_count = len(active_subs)

    return {
        "fee_events": fee_events,
        "ledger_rows": ledger_rows,
        "subscriptions": subscriptions,
        "daily_total": daily_total,
        "daily_fees": dict(daily_fees),
        "daily_fee_counts": dict(daily_fee_counts),
        "daily_ledger": dict(daily_ledger),
        "daily_values": daily_values,
        "daily_dates": daily_dates,
        "mrr_total": mrr_total,
        "active_sub_count": active_count,
        "total_fee_events": len(fee_events),
        "total_ledger_entries": len(ledger_rows),
        "lookback_days": lookback_days,
    }


# ── Forecasting engine ────────────────────────────────────────────────────

def compute_forecast(data: dict) -> dict:
    """Run forecasting models on daily revenue data."""
    daily_values = data["daily_values"]
    daily_dates = data["daily_dates"]
    n = len(daily_values)

    if n == 0:
        return {"error": "no historical data", "forecasts": {}, "confidence": {}}

    # ── MRR baseline ─────────────────────────────────────────────────
    mrr_monthly = data["mrr_total"]
    mrr_daily_equiv = mrr_monthly / 30.0 if mrr_monthly > 0 else 0.0

    # ── 7-day moving average ─────────────────────────────────────────
    ma_7 = moving_average(daily_values, 7) or 0.0
    ma_30 = moving_average(daily_values, 30) or ma_7

    # ── Linear regression on daily data ──────────────────────────────
    # Use points (day_index, revenue) for regression
    xy = [(float(i), v) for i, v in enumerate(daily_values) if v > 0]
    slope, intercept, r_sq = linear_regression(xy)

    # Project forward: 7, 30, 90 days
    forecast_7d = 0.0
    forecast_30d = 0.0
    forecast_90d = 0.0
    if n > 0 and abs(slope) > 1e-12:
        # Sum of projected daily values over the forecast horizon
        for i in range(n, n + 7):
            forecast_7d += max(0, slope * i + intercept)
        for i in range(n, n + 30):
            forecast_30d += max(0, slope * i + intercept)
        for i in range(n, n + 90):
            forecast_90d += max(0, slope * i + intercept)
    else:
        # Flat projection using moving average
        forecast_7d = ma_7 * 7
        forecast_30d = ma_30 * 30
        forecast_90d = ma_30 * 90

    # ── MRR-adjusted forecast ────────────────────────────────────────
    # Blend revenue trend with MRR baseline for a conservative estimate
    forecast_30d_with_mrr = max(forecast_30d, mrr_monthly)
    forecast_90d_with_mrr = max(forecast_90d, mrr_monthly * 3)

    # ── Confidence interval (lower bound: worst 30-day period) ───────
    # Find the lowest 30-day rolling sum
    min_30d = float("inf")
    if n >= 30:
        for i in range(n - 30 + 1):
            s = sum(daily_values[i:i + 30])
            if s < min_30d:
                min_30d = s
    elif n > 0:
        min_30d = sum(daily_values) * (30.0 / n)  # extrapolate
    else:
        min_30d = 0.0

    lower_bound_30d = max(min_30d, 0.0)
    upper_bound_30d = forecast_30d * 1.5 if n >= 14 else forecast_30d * 2.0

    # ── Weekly trend direction ───────────────────────────────────────
    if n >= 14:
        recent = sum(daily_values[-7:]) / 7.0
        prior = sum(daily_values[-14:-7]) / 7.0 if n >= 14 else recent
        trend_pct = ((recent - prior) / prior * 100) if prior > 0 else 0.0
    else:
        trend_pct = 0.0

    # ── Revenue velocity (last 7 days vs previous 7) ─────────────────
    last_7 = sum(daily_values[-7:]) if n >= 7 else sum(daily_values)
    prev_7 = sum(daily_values[-14:-7]) if n >= 14 else 0.0

    # ── Data quality ─────────────────────────────────────────────────
    data_days = n
    lookback_days = data["lookback_days"]
    coverage_pct = round(data_days / lookback_days * 100, 1) if lookback_days > 0 else 0.0

    return {
        "forecasts": {
            "next_7d": round(forecast_7d, 2),
            "next_30d": round(forecast_30d, 2),
            "next_90d": round(forecast_90d, 2),
            "next_30d_with_mrr": round(forecast_30d_with_mrr, 2),
            "next_90d_with_mrr": round(forecast_90d_with_mrr, 2),
        },
        "averages": {
            "ma_7d": round(ma_7, 2),
            "ma_30d": round(ma_30, 2),
            "mrr_monthly": round(mrr_monthly, 2),
            "mrr_daily_equiv": round(mrr_daily_equiv, 2),
        },
        "trend": {
            "slope": round(slope, 4),
            "r_squared": round(r_sq, 4),
            "direction": "up" if trend_pct > 5 else ("down" if trend_pct < -5 else "stable"),
            "week_over_week_pct": round(trend_pct, 1),
            "last_7d_revenue": round(last_7, 2),
            "prev_7d_revenue": round(prev_7, 2),
        },
        "confidence": {
            "lower_bound_30d": round(lower_bound_30d, 2),
            "upper_bound_30d": round(upper_bound_30d, 2),
            "data_coverage_pct": coverage_pct,
            "data_days": data_days,
        },
        "stats": {
            "daily_avg": round(sum(daily_values) / n, 2) if n > 0 else 0.0,
            "daily_max": round(max(daily_values), 2) if daily_values else 0.0,
            "daily_min": round(min(v for v in daily_values if v > 0) if any(v for v in daily_values) else 0.0, 2),
            "total_revenue_lookback": round(sum(daily_values), 2),
            "num_active_subs": data["active_sub_count"],
        },
    }


# ── Report builder ────────────────────────────────────────────────────────

def build_forecast_message(data: dict, forecast: dict) -> str:
    """Build the Telegram HTML forecast report."""
    now = datetime.now(timezone.utc)
    parts = ["<b>📈 Empire AI — Revenue Forecast</b>"]
    parts.append(f"📅 Generated {now.strftime('%Y-%m-%d %H:%M')} UTC")
    parts.append(f"📊 Lookback: {data['lookback_days']} days ({data['total_fee_events']} fees, {data['total_ledger_entries']} ledger entries)")
    parts.append("")

    # ── Error state ──────────────────────────────────────────────────
    if "error" in forecast:
        parts.append(f"⚠️ {forecast['error']}")
        return "\n".join(parts)

    f = forecast["forecasts"]
    a = forecast["averages"]
    t = forecast["trend"]
    c = forecast["confidence"]
    s = forecast["stats"]

    # ── Trend summary ────────────────────────────────────────────────
    emoji = {"up": "🟢", "down": "🔴", "stable": "🟡"}.get(t["direction"], "⚪")
    parts.append(f"<b>{emoji} Trend: {t['direction'].upper()}</b> ({t['week_over_week_pct']:+.1f}% WoW)")
    parts.append(f"  Last 7d: <b>${t['last_7d_revenue']:,.2f}</b>  |  Prev 7d: ${t['prev_7d_revenue']:,.2f}")
    parts.append(f"  Slope: {t['slope']:.4f}  |  R²: {t['r_squared']:.3f}")
    parts.append("")

    # ── Forecast ─────────────────────────────────────────────────────
    parts.append("<b>🔮 Forecast</b>")
    parts.append(f"  Next 7 days:  <b>${f['next_7d']:,.2f}</b>  (${f['next_7d']/7:,.2f}/day avg)")
    parts.append(f"  Next 30 days: <b>${f['next_30d']:,.2f}</b>  (${f['next_30d']/30:,.2f}/day avg)")
    parts.append(f"  Next 90 days: <b>${f['next_90d']:,.2f}</b>  (${f['next_90d']/90:,.2f}/day avg)")
    parts.append("")

    # ── MRR-Adjusted Forecast ────────────────────────────────────────
    if s["num_active_subs"] > 0:
        parts.append("<b>🏦 MRR-Adjusted Outlook</b>")
        parts.append(f"  Subscriptions: {s['num_active_subs']} active  |  MRR: <b>${a['mrr_monthly']:,.2f}</b>/mo")
        parts.append(f"  MRR-adjusted 30d: <b>${f['next_30d_with_mrr']:,.2f}</b>")
        parts.append(f"  MRR-adjusted 90d: <b>${f['next_90d_with_mrr']:,.2f}</b>")
        parts.append("")

    # ── Averages ─────────────────────────────────────────────────────
    parts.append("<b>📐 Moving Averages</b>")
    parts.append(f"  7-day MA: ${a['ma_7d']:,.2f}/day")
    parts.append(f"  30-day MA: ${a['ma_30d']:,.2f}/day")
    parts.append(f"  MRR daily equiv: ${a['mrr_daily_equiv']:,.2f}/day")
    parts.append("")

    # ── Confidence intervals ─────────────────────────────────────────
    parts.append("<b>🎯 Confidence Range (30d)</b>")
    parts.append(f"  Lower bound: ${c['lower_bound_30d']:,.2f}  (worst 30-day period)")
    parts.append(f"  Upper bound: ${c['upper_bound_30d']:,.2f}  (1.5x projection)")
    lookback_days = data['lookback_days']
    parts.append(f"  Data quality: {c['data_coverage_pct']}% coverage ({c['data_days']} of {lookback_days} days)")
    parts.append("")

    # ── Stats summary ────────────────────────────────────────────────
    parts.append("<b>📋 Summary Stats</b>")
    parts.append(f"  Daily avg: ${s['daily_avg']:,.2f}  |  Max: ${s['daily_max']:,.2f}  |  Min: ${s['daily_min']:,.2f}")
    parts.append(f"  Total ({data['lookback_days']}d): <b>${s['total_revenue_lookback']:,.2f}</b>")
    parts.append("")

    parts.append("<i>Auto-generated by empire_revenue_predictive.py</i>")
    return "\n".join(parts)


# ── Main logic ────────────────────────────────────────────────────────────

async def run_once(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict:
    """Run one forecasting cycle."""
    started_at = datetime.now(timezone.utc)
    log.info(f"running forecast (lookback={lookback_days}d)")

    try:
        data = fetch_historical(lookback_days)
        log.info(
            f"fetched {data['total_fee_events']} fees, "
            f"{data['total_ledger_entries']} ledger entries, "
            f"{data['active_sub_count']} subs (MRR=${data['mrr_total']:.2f})"
        )
    except Exception as e:
        log.error(f"fetch failed: {e}")
        await send_telegram(f"🔴 Revenue forecast: fetch failed\n\n<code>{e}</code>")
        return {"status": "error", "error": str(e)}

    try:
        forecast = compute_forecast(data)
        log.info(
            f"forecast: 7d=${forecast['forecasts']['next_7d']:.2f} "
            f"30d=${forecast['forecasts']['next_30d']:.2f} "
            f"90d=${forecast['forecasts']['next_90d']:.2f} "
            f"trend={forecast['trend']['direction']}"
        )
    except Exception as e:
        log.error(f"forecast computation failed: {e}")
        await send_telegram(f"🔴 Revenue forecast: computation failed\n\n<code>{e}</code>")
        return {"status": "error", "error": str(e)}

    message = build_forecast_message(data, forecast)
    log.info(f"built message ({len(message)} chars)")

    sent_ok = await send_telegram(message)

    summary = (
        f"forecast_7d=${forecast['forecasts']['next_7d']:.2f} "
        f"forecast_30d=${forecast['forecasts']['next_30d']:.2f} "
        f"forecast_90d=${forecast['forecasts']['next_90d']:.2f} "
        f"trend={forecast['trend']['direction']} "
        f"mrr=${forecast['averages']['mrr_monthly']:.2f} "
        f"sent={'ok' if sent_ok else 'failed'}"
    )
    log_to_agent_activity(started_at, "ok" if sent_ok else "warn", summary)
    log.info(f"done: {summary}")

    return {
        "status": "ok" if sent_ok else "warn",
        "forecast": forecast,
        "summary": summary,
    }


async def run_loop(interval_seconds: Optional[int] = None, lookback_days: int = DEFAULT_LOOKBACK_DAYS):
    """Run forecasting in an infinite loop."""
    delay = interval_seconds or DEFAULT_INTERVAL_SECONDS
    log.info(f"[{AGENT_NAME}] running in loop mode (interval={delay}s = {delay/3600:.0f}h)")
    while True:
        started = datetime.now(timezone.utc)
        try:
            result = await run_once(lookback_days=lookback_days)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            log.info(f"[{AGENT_NAME}] cycle done in {elapsed:.1f}s — status={result.get('status')}")
        except Exception as e:
            log.exception(f"[{AGENT_NAME}] cycle failed: {e}")
        slept = (datetime.now(timezone.utc) - started).total_seconds()
        await asyncio.sleep(max(30, delay - slept))


# ── CLI entry point ───────────────────────────────────────────────────────

def run():
    """Module-level entry point for empire-mesh (main.py imports → run())."""
    parser = argparse.ArgumentParser(description="Empire AI Revenue Forecast")
    parser.add_argument("--loop", action="store_true", help="run in loop mode")
    parser.add_argument("--interval", type=int, default=None,
                        help=f"loop interval in seconds (default: {DEFAULT_INTERVAL_SECONDS})")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help=f"lookback days for historical data (default: {DEFAULT_LOOKBACK_DAYS})")
    args, _ = parser.parse_known_args()

    if args.loop:
        asyncio.run(run_loop(interval_seconds=args.interval, lookback_days=args.days))
    else:
        asyncio.run(run_once(lookback_days=args.days))


if __name__ == "__main__":
    run()
