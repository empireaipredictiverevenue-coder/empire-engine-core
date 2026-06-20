"""
Empire AI · Daily Billing Digest
==================================
Queries the call_logs table for the last 24 hours of billing activity
and sends a Telegram digest to the operator chat.

Can run via:
  - Cron (legacy: 07:00 UTC daily)
  - Loop mode: python3 agents_billing_daily.py --loop
  - Agent runner: python3 -m agents.agent_runner

Runs daily at 07:00 UTC via cron. Queries the call_logs table for
the last 24 hours of billing activity and sends a Telegram digest
to the operator chat.

Sections:
  - Summary: total calls routed, completed, billable
  - Fees: today's total fee_earned, plus all-time total
  - Top calls: highest-payout routed calls (up to 5)
  - Vonage: nginx event delivery rates (200 vs 404)
  - Active buyers: count and total available payout capacity

Logs to agent_activity so the operator SPA can chart it.
"""

import os
import sys
import uuid
import argparse
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter
from typing import Optional

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

log = logging.getLogger("agents_billing_daily")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [billing-daily] %(levelname)s %(message)s",
)

AGENT_NAME = "billing_daily_digest"
DEFAULT_INTERVAL_SECONDS = 86400  # 24 hours
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("OPERATOR_TELEGRAM_CHAT_ID", "808657420")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


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


def fetch_data() -> dict:
    """Fetch all billing data for the report."""
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    yesterday = (now - timedelta(hours=24)).isoformat()

    # ── Today's call_logs ───────────────────────────────────────────
    r = sb.table("call_logs") \
        .select("id,vonage_call_id,niche,caller_state,payout_value,is_billable,fee_earned,status,source,created_at") \
        .gte("created_at", today_start) \
        .order("created_at", desc=True) \
        .limit(100) \
        .execute()
    today_logs = r.data or []

    # ── Yesterday's for comparison ──────────────────────────────────
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    r_y = sb.table("call_logs") \
        .select("id,is_billable,fee_earned,payout_value") \
        .gte("created_at", yesterday_start) \
        .lt("created_at", today_start) \
        .execute()
    yesterday_logs = r_y.data or []

    # ── All-time billing ────────────────────────────────────────────
    r_all = sb.table("call_logs") \
        .select("id,is_billable,fee_earned,payout_value") \
        .execute()
    all_logs = r_all.data or []

    # ── Active buyers ───────────────────────────────────────────────
    r_b = sb.table("buyers") \
        .select("buyer_name,niche,state_coverage,base_payout,fee_rate,is_active") \
        .eq("is_active", True) \
        .execute()
    buyers = r_b.data or []

    # ── Compute stats ───────────────────────────────────────────────
    today_routed = sum(1 for c in today_logs if c.get("status") in ("routed", "completed"))
    today_completed = sum(1 for c in today_logs if c.get("status") == "completed")
    today_billed = sum(1 for c in today_logs if c.get("is_billable"))
    today_fees = sum(float(c.get("fee_earned") or 0) for c in today_logs if c.get("is_billable"))
    today_payout = sum(float(c.get("payout_value") or 0) for c in today_logs)

    yesterday_payout = sum(float(c.get("payout_value") or 0) for c in yesterday_logs)
    yesterday_fees = sum(float(c.get("fee_earned") or 0) for c in yesterday_logs if c.get("is_billable"))

    all_time_fees = sum(float(c.get("fee_earned") or 0) for c in all_logs if c.get("is_billable"))
    all_time_billed = sum(1 for c in all_logs if c.get("is_billable"))

    # Top 5 by payout
    sorted_logs = sorted(today_logs, key=lambda x: float(x.get("payout_value") or 0), reverse=True)
    top_5 = sorted_logs[:5]

    # By source
    source_counts = Counter(c.get("source", "direct") for c in today_logs)

    # By niche
    niche_counts = Counter(c.get("niche", "unknown") for c in today_logs)

    return {
        "today_logs": today_logs,
        "today_routed": today_routed,
        "today_completed": today_completed,
        "today_billed": today_billed,
        "today_fees": round(today_fees, 2),
        "today_payout": round(today_payout, 2),
        "yesterday_payout": round(yesterday_payout, 2),
        "yesterday_fees": round(yesterday_fees, 2),
        "all_time_fees": round(all_time_fees, 2),
        "all_time_billed": all_time_billed,
        "top_5": top_5,
        "buyers": buyers,
        "source_counts": dict(source_counts.most_common(3)),
        "niche_counts": dict(niche_counts.most_common(5)),
        "total_calls_all_time": len(all_logs),
    }


def build_message(data: dict) -> str:
    """Build the Telegram HTML message."""
    parts = ["<b>Empire AI — Daily Billing Summary</b>"]
    parts.append(f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d (%A)')}")
    parts.append("")

    # ── Summary ──────────────────────────────────────────────────
    parts.append("<b>📊 Today</b>")
    parts.append(f"  Routed: {data['today_routed']}")
    parts.append(f"  Completed: {data['today_completed']}")
    parts.append(f"  Billable: {data['today_billed']}")
    parts.append(f"  Payout routed: <b>${data['today_payout']:,.0f}</b>")
    parts.append(f"  Fees earned: <b>${data['today_fees']:.2f}</b>")
    parts.append("")

    # ── Comparison with yesterday ─────────────────────────────────
    parts.append("<b>📈 vs Yesterday</b>")
    payout_diff = data['today_payout'] - data['yesterday_payout']
    fee_diff = data['today_fees'] - data['yesterday_fees']
    payout_arrow = "▲" if payout_diff > 0 else ("▼" if payout_diff < 0 else "—")
    fee_arrow = "▲" if fee_diff > 0 else ("▼" if fee_diff < 0 else "—")
    parts.append(f"  Payout: {payout_arrow} ${abs(payout_diff):,.0f}" if payout_diff else "  Payout: — $0")
    parts.append(f"  Fees: {fee_arrow} ${abs(fee_diff):.2f}" if fee_diff else "  Fees: — $0.00")
    parts.append("")

    # ── Top calls ─────────────────────────────────────────────────
    top_5 = data["top_5"]
    if top_5:
        parts.append("<b>🏆 Top Calls (Today)</b>")
        for i, c in enumerate(top_5, 1):
            vid = str(c.get("vonage_call_id") or "")[:10]
            niche = c.get("niche", "?")
            state = c.get("caller_state", "?")
            payout = float(c.get("payout_value") or 0)
            billed = "💰" if c.get("is_billable") else "⏳"
            source = c.get("source", "?")
            parts.append(f"  {i}. {vid}... {billed} {niche}/{state} ${payout:,.0f} ({source})")
        parts.append("")

    # ── By source ─────────────────────────────────────────────────
    if data["source_counts"]:
        parts.append("<b>📦 By Source</b>")
        for src, count in data["source_counts"].items():
            parts.append(f"  {src}: {count}")
        parts.append("")

    # ── All-time ──────────────────────────────────────────────────
    parts.append("<b>🏅 All-Time</b>")
    parts.append(f"  Calls logged: {data['total_calls_all_time']}")
    parts.append(f"  Billable calls: {data['all_time_billed']}")
    parts.append(f"  Total fees: <b>${data['all_time_fees']:,.2f}</b>")
    parts.append("")

    # ── Active buyers ─────────────────────────────────────────────
    buyers = data["buyers"]
    if buyers:
        parts.append("<b>🏢 Active Buyers</b>")
        for b in buyers:
            name = b.get("buyer_name", "?")
            niche = b.get("niche", "?")
            payout = float(b.get("base_payout") or 0)
            rate = float(b.get("fee_rate") or 0.03) * 100
            states = ", ".join(b.get("state_coverage") or []) or "all"
            parts.append(f"  {name} ({niche}) ${payout:,.0f} @ {rate:.0f}% — {states}")
    else:
        parts.append("<b>🏢 Active Buyers</b>: none")
    parts.append("")

    # ── Vonage event delivery health ──────────────────────────────
    try:
        import subprocess
        result = subprocess.run(
            ["tail", "-n", "2000", "/var/log/nginx/access.log"],
            capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.splitlines()
        total_vonage = sum(1 for line in lines if "vonage/status" in line)
        vonage_200 = sum(1 for line in lines if "vonage/status" in line and " 200 " in line)
        vonage_404 = sum(1 for line in lines if "vonage/status" in line and " 404 " in line)
        if total_vonage > 0:
            health = "✅" if vonage_200 > vonage_404 else "⚠️"
            parts.append("<b>📡 Vonage Event Health</b>")
            parts.append(f"  {health} Total events: {total_vonage}")
            parts.append(f"  ✅ 200: {vonage_200} (proxy fix working)")
            parts.append(f"  ❌ 404: {vonage_404} (before proxy fix)")
    except Exception:
        pass

    parts.append("")
    parts.append("<i>Auto-generated by agents_billing_daily.py</i>")
    return "\n".join(parts)


def log_to_agent_activity(started_at, status: str, summary: str) -> None:
    try:
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
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


# ── Loop mode ───────────────────────────────────────────────────────────

async def run_loop(interval_seconds: Optional[int] = None):
    """Run billing daily digest in an infinite loop."""
    delay = interval_seconds or DEFAULT_INTERVAL_SECONDS
    log.info(f"[{AGENT_NAME}] running in loop mode (interval={delay}s = {delay/3600:.0f}h)")
    while True:
        started = datetime.now(timezone.utc)
        try:
            exit_code = await _run_once_async()
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            log.info(f"[{AGENT_NAME}] cycle done in {elapsed:.1f}s — exit_code={exit_code}")
        except Exception as e:
            log.exception(f"[{AGENT_NAME}] cycle failed: {e}")
        slept = (datetime.now(timezone.utc) - started).total_seconds()
        await asyncio.sleep(max(30, delay - slept))


async def _run_once_async() -> int:
    """Run one billing cycle asynchronously (safe for both loop mode and sync main())."""
    started_at = datetime.now(timezone.utc)
    log.info(f"running at {started_at.isoformat()}")

    try:
        data = fetch_data()
        log.info(
            f"today: {data['today_routed']} routed, {data['today_billed']} billed, "
            f"${data['today_fees']:.2f} fees"
        )
    except Exception as e:
        log.error(f"fetch failed: {e}")
        await send_telegram(f"🔴 Billing daily: fetch failed\n\n<code>{e}</code>")
        return 1

    message = build_message(data)
    log.info(f"built message ({len(message)} chars)")

    sent_ok = await send_telegram(message)

    summary = (
        f"today_routed={data['today_routed']} "
        f"today_billed={data['today_billed']} "
        f"fees=${data['today_fees']:.2f} "
        f"all_time_fees=${data['all_time_fees']:.2f} "
        f"sent={'ok' if sent_ok else 'failed'}"
    )
    log_to_agent_activity(started_at, "ok" if sent_ok else "warn", summary)
    log.info(f"done: {summary}")
    return 0 if sent_ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Empire AI Daily Billing Digest")
    p.add_argument("--loop", action="store_true", help="run in loop mode (replaces cron)")
    p.add_argument("--interval", type=int, default=None,
                   help=f"loop interval in seconds (default: {DEFAULT_INTERVAL_SECONDS})")
    args, _ = p.parse_known_args()
    if args.loop:
        asyncio.run(run_loop(interval_seconds=args.interval))
        return 0
    return asyncio.run(_run_once_async())


if __name__ == "__main__":
    sys.exit(main())
