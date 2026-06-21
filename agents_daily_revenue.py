"""
Empire AI · Daily Revenue Report
=================================
Queries fee_events, carrier_claims, empire_revenue_ledger, and
carrier_enrollments for the last 24 hours of revenue activity
and sends a Telegram digest to the operator chat.

Can run via:
  - Cron (legacy: 07:00 UTC daily)
  - Loop mode: python3 agents_daily_revenue.py --loop
  - Agent runner: python3 -m agents.agent_runner --agent revenue_daily_digest

Runs daily at 07:00 UTC via cron. Queries revenue tables for
the last 24 hours and sends a Telegram digest to the operator chat.

Sections:
  - Fee Events: today's fees, pending vs paid, all-time totals, top fees
  - Carrier Claims: open vs settled, today's activity, total settled
  - Revenue Ledger: Solana USDC inflow, recent transactions
  - Collection Status: pending fees awaiting collection, follow-up due
  - Carrier Enrollments: active carrier integrations

Logs to agent_activity so the operator SPA can chart it.
"""

import os
import sys
import uuid
import json
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

log = logging.getLogger("agents_daily_revenue")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [revenue-daily] %(levelname)s %(message)s",
)

AGENT_NAME = "revenue_daily_digest"
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
    """Fetch all revenue data for the report."""
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    yesterday = (now - timedelta(hours=24)).isoformat()

    # ── Today's fee_events ──────────────────────────────────────────
    r = sb.table("fee_events") \
        .select("id,claim_id,contractor_id,claim_amount,fee_amount,status,source,settled_at,created_at,meta") \
        .gte("created_at", today_start) \
        .order("created_at", desc=True) \
        .limit(100) \
        .execute()
    today_fees = r.data or []

    # ── Yesterday's fee_events for comparison ───────────────────────
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    r_y = sb.table("fee_events") \
        .select("id,fee_amount,status") \
        .gte("created_at", yesterday_start) \
        .lt("created_at", today_start) \
        .execute()
    yesterday_fees = r_y.data or []

    # ── All-time fee_events ─────────────────────────────────────────
    r_all = sb.table("fee_events") \
        .select("id,claim_amount,fee_amount,status,meta") \
        .execute()
    all_fees = r_all.data or []

    # ── Pending fees (all-time, not just today) ─────────────────────
    pending = [f for f in all_fees if f.get("status") == "pending"]

    # ── Carrier claims ──────────────────────────────────────────────
    r_cc = sb.table("carrier_claims") \
        .select("id,status,settled_amount,asset_value,loss_description,settled_at,filed_at,created_at") \
        .order("created_at", desc=True) \
        .limit(100) \
        .execute()
    carrier_claims = r_cc.data or []

    # ── Today's carrier claims ──────────────────────────────────────
    today_claims = [c for c in carrier_claims if (c.get("created_at") or "") >= today_start]
    today_settled_claims = [c for c in carrier_claims if (c.get("settled_at") or "") >= today_start]

    # ── Revenue ledger ─────────────────────────────────────────────
    r_rl = sb.table("empire_revenue_ledger") \
        .select("transaction_signature,sender_address,usdc_amount,tracking_memo,block_time_stamp,logged_at") \
        .order("block_time_stamp", desc=True) \
        .limit(50) \
        .execute()
    ledger_rows = r_rl.data or []

    # ── Today's ledger entries ──────────────────────────────────────
    today_ledger = [tx for tx in ledger_rows if (tx.get("block_time_stamp") or tx.get("logged_at") or "") >= today_start]

    # ── Carrier enrollments ─────────────────────────────────────────
    r_ce = sb.table("carrier_enrollments") \
        .select("id,carrier_name,status,contact_email,verified_at,created_at") \
        .order("created_at", desc=True) \
        .limit(50) \
        .execute()
    enrollments = r_ce.data or []

    # ── Collection status ───────────────────────────────────────────
    fees_with_collection = 0
    fees_follow_up_due = 0
    for f in pending:
        meta = f.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        history = meta.get("collection_history") or []
        if history:
            fees_with_collection += 1
            # Check if follow-up is due (last attempt >3 days ago)
            last_attempt = history[-1]
            last_sent = last_attempt.get("sent_at", "")
            if last_sent:
                try:
                    last_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
                    if (now - last_dt).days >= 3:
                        fees_follow_up_due += 1
                except Exception:
                    pass

    # ── Resolve contractor names for fees ───────────────────────────
    contractor_ids = set()
    for f in today_fees:
        cid = f.get("contractor_id")
        if cid:
            contractor_ids.add(cid)
    contractors: dict = {}
    if contractor_ids:
        for cid in contractor_ids:
            try:
                cr = sb.table("contractors").select("name").eq("id", cid).limit(1).execute()
                if cr.data:
                    contractors[cid] = cr.data[0].get("name", "?")
            except Exception:
                pass

    # ── Compute stats ───────────────────────────────────────────────
    today_fee_count = len(today_fees)
    today_fee_total = sum(float(f.get("fee_amount") or 0) for f in today_fees)
    today_fee_paid = sum(float(f.get("fee_amount") or 0) for f in today_fees if f.get("status") == "paid")
    today_fee_pending = sum(float(f.get("fee_amount") or 0) for f in today_fees if f.get("status") == "pending")

    yesterday_fee_total = sum(float(f.get("fee_amount") or 0) for f in yesterday_fees)

    all_time_fee_total = sum(float(f.get("fee_amount") or 0) for f in all_fees)
    all_time_fee_count = len(all_fees)
    all_time_paid = sum(float(f.get("fee_amount") or 0) for f in all_fees if f.get("status") == "paid")
    all_time_pending = sum(float(f.get("fee_amount") or 0) for f in all_fees if f.get("status") == "pending")

    all_time_claim_total = sum(float(f.get("claim_amount") or 0) for f in all_fees)

    # Carrier claims stats
    open_claims = [c for c in carrier_claims if c.get("status") == "open"]
    settled_claims = [c for c in carrier_claims if c.get("status") == "settled"]
    total_settled_amount = sum(float(c.get("settled_amount") or 0) for c in settled_claims)
    total_asset_value = sum(float(c.get("asset_value") or 0) for c in carrier_claims)

    # Ledger stats
    ledger_total = sum(float(tx.get("usdc_amount") or 0) for tx in ledger_rows)
    today_ledger_total = sum(float(tx.get("usdc_amount") or 0) for tx in today_ledger)

    # Enrollment stats
    active_enrollments = [e for e in enrollments if e.get("status") == "active"]
    verified_enrollments = [e for e in enrollments if e.get("verified_at")]

    # Top fees today
    sorted_fees = sorted(today_fees, key=lambda x: float(x.get("fee_amount") or 0), reverse=True)
    top_5 = sorted_fees[:5]

    # Fee by source
    source_counts = Counter(f.get("source", "unknown") for f in all_fees)

    # Fee by status
    status_counts = Counter(f.get("status", "?") for f in all_fees)

    return {
        "today_fee_count": today_fee_count,
        "today_fee_total": round(today_fee_total, 2),
        "today_fee_paid": round(today_fee_paid, 2),
        "today_fee_pending": round(today_fee_pending, 2),
        "yesterday_fee_total": round(yesterday_fee_total, 2),
        "all_time_fee_total": round(all_time_fee_total, 2),
        "all_time_fee_count": all_time_fee_count,
        "all_time_paid": round(all_time_paid, 2),
        "all_time_pending": round(all_time_pending, 2),
        "all_time_claim_total": round(all_time_claim_total, 2),
        "top_5": top_5,
        "contractors": contractors,
        "source_counts": dict(source_counts.most_common(5)),
        "status_counts": dict(status_counts),
        "open_claims": len(open_claims),
        "settled_claims": len(settled_claims),
        "total_settled_amount": round(total_settled_amount, 2),
        "total_asset_value": round(total_asset_value, 2),
        "today_claims": len(today_claims),
        "today_settled_claims": len(today_settled_claims),
        "ledger_total": round(ledger_total, 2),
        "ledger_count": len(ledger_rows),
        "today_ledger_total": round(today_ledger_total, 2),
        "today_ledger_count": len(today_ledger),
        "recent_ledger": ledger_rows[:5],
        "active_enrollments": len(active_enrollments),
        "verified_enrollments": len(verified_enrollments),
        "total_enrollments": len(enrollments),
        "enrollment_names": [e.get("carrier_name", "?") for e in active_enrollments],
        "pending_fee_count": len(pending),
        "pending_fee_total": round(sum(float(f.get("fee_amount") or 0) for f in pending), 2),
        "fees_with_collection": fees_with_collection,
        "fees_follow_up_due": fees_follow_up_due,
    }


def build_message(data: dict) -> str:
    """Build the Telegram HTML message."""
    now = datetime.now(timezone.utc)
    parts = ["<b>💰 Empire AI — Daily Revenue Report</b>"]
    parts.append(f"📅 {now.strftime('%Y-%m-%d (%A)')}  {now.strftime('%H:%M')} UTC")
    parts.append("")

    # ── Fee Events ─────────────────────────────────────────────────
    parts.append("<b>💵 Fee Events</b>")

    if data["today_fee_count"] > 0:
        parts.append(f"  Today: {data['today_fee_count']} events · <b>${data['today_fee_total']:,.2f}</b>")
        parts.append(f"  Paid: ${data['today_fee_paid']:,.2f} · Pending: ${data['today_fee_pending']:,.2f}")
    else:
        parts.append(f"  Today: no new fee events")

    # Today vs yesterday (only show when there's activity)
    fee_diff = data["today_fee_total"] - data["yesterday_fee_total"]
    if fee_diff != 0 or data["today_fee_total"] > 0:
        arrow = "▲" if fee_diff > 0 else ("▼" if fee_diff < 0 else "—")
        parts.append(f"  vs Yesterday: {arrow} ${abs(fee_diff):,.2f}")

    parts.append(f"  All-time: {data['all_time_fee_count']} events · <b>${data['all_time_fee_total']:,.2f}</b>")
    parts.append(f"  All-time claims: ${data['all_time_claim_total']:,.2f}")
    parts.append("")

    # ── Top Fees Today ──────────────────────────────────────────────
    if data["top_5"]:
        parts.append("<b>🏆 Top Fees (Today)</b>")
        for i, f in enumerate(data["top_5"], 1):
            cid = f.get("contractor_id")
            name = data["contractors"].get(cid, "?")[:22] if cid else "?"
            claim = str(f.get("claim_id") or "")[:16]
            fee = float(f.get("fee_amount") or 0)
            claim_amt = float(f.get("claim_amount") or 0)
            status = f.get("status", "?")
            status_icon = {"paid": "✅", "pending": "⏳", "settled": "💵"}.get(status, "❓")
            parts.append(f"  {i}. {status_icon} {name} · ${fee:,.0f} fee on ${claim_amt:,.0f} claim ({claim})")
        parts.append("")

    # ── Cash Position ──────────────────────────────────────────────
    parts.append("<b>💸 Cash Position</b>")
    parts.append(f"  Paid (collected): <b>${data['all_time_paid']:,.2f}</b>")
    parts.append(f"  Pending (awaiting): ${data['all_time_pending']:,.2f}")
    if data["all_time_fee_total"] > 0:
        pct = round(100 * data["all_time_paid"] / data["all_time_fee_total"], 1)
        parts.append(f"  Collection rate: {pct}%")
    parts.append("")

    # ── Collection Status ──────────────────────────────────────────
    if data["pending_fee_count"] > 0:
        parts.append("<b>📬 Collection Status</b>")
        parts.append(f"  Pending fees: {data['pending_fee_count']} (${data['pending_fee_total']:,.2f})")
        parts.append(f"  Contacted: {data['fees_with_collection']}")
        if data["fees_follow_up_due"] > 0:
            parts.append(f"  ⚠️ Follow-up due: {data['fees_follow_up_due']}")
        parts.append("")

    # ── Carrier Claims ─────────────────────────────────────────────
    parts.append("<b>🏛️ Carrier Claims</b>")
    parts.append(f"  Open: {data['open_claims']} · Settled: {data['settled_claims']}")
    parts.append(f"  Total settled: <b>${data['total_settled_amount']:,.2f}</b>")
    parts.append(f"  Total asset value: ${data['total_asset_value']:,.2f}")
    if data["today_settled_claims"] > 0:
        parts.append(f"  🆕 Settled today: {data['today_settled_claims']}")
    parts.append("")

    # ── Revenue Ledger (Solana USDC) ───────────────────────────────
    parts.append("<b>🔗 Solana USDC Ledger</b>")
    if data["ledger_count"] > 0:
        parts.append(f"  Total inflow: <b>${data['ledger_total']:,.2f}</b> ({data['ledger_count']} txs)")
        if data["today_ledger_count"] > 0:
            parts.append(f"  Today: ${data['today_ledger_total']:,.2f} ({data['today_ledger_count']} txs)")
        if data["recent_ledger"]:
            tx = data["recent_ledger"][0]
            amt = float(tx.get("usdc_amount") or 0)
            ts = (tx.get("block_time_stamp") or tx.get("logged_at") or "")[:16]
            memo = (tx.get("tracking_memo") or "-")[:40]
            parts.append(f"  Latest: ${amt:,.2f} · {ts} · {memo}")
    else:
        parts.append("  No on-chain USDC transactions yet")
    parts.append("")

    # ── Carrier Enrollments ────────────────────────────────────────
    parts.append("<b>🏢 Carrier Integrations</b>")
    parts.append(f"  Active: {data['active_enrollments']} · Verified: {data['verified_enrollments']}")
    if data["enrollment_names"]:
        names = ", ".join(data["enrollment_names"][:5])
        if len(data["enrollment_names"]) > 5:
            names += f" +{len(data['enrollment_names']) - 5} more"
        parts.append(f"  {names}")
    parts.append("")

    # ── By Source ──────────────────────────────────────────────────
    if data["source_counts"]:
        parts.append("<b>📦 Fee Sources (All-Time)</b>")
        for src, count in data["source_counts"].items():
            parts.append(f"  {src}: {count}")
        parts.append("")

    # ── By Status ──────────────────────────────────────────────────
    if data["status_counts"]:
        status_icons = {"paid": "✅", "pending": "⏳", "settled": "💵", "invoiced": "📄", "cancelled": "❌"}
        parts.append("<b>📊 Fee Status Breakdown</b>")
        for status, count in sorted(data["status_counts"].items()):
            icon = status_icons.get(status, "•")
            parts.append(f"  {icon} {status}: {count}")
        parts.append("")

    parts.append("<i>Auto-generated by agents_daily_revenue.py</i>")
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
    """Run revenue daily digest in an infinite loop."""
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
    """Run one revenue digest cycle asynchronously."""
    started_at = datetime.now(timezone.utc)
    log.info(f"running at {started_at.isoformat()}")

    try:
        data = fetch_data()
        log.info(
            f"fees: {data['today_fee_count']} today (${data['today_fee_total']:.2f}), "
            f"{data['all_time_fee_count']} all-time (${data['all_time_fee_total']:.2f}), "
            f"claims: {data['settled_claims']} settled, "
            f"ledger: ${data['ledger_total']:.2f}"
        )
    except Exception as e:
        log.error(f"fetch failed: {e}")
        await send_telegram(f"🔴 Revenue daily: fetch failed\n\n<code>{e}</code>")
        return 1

    message = build_message(data)
    log.info(f"built message ({len(message)} chars)")

    sent_ok = await send_telegram(message)

    summary = (
        f"fees_today=${data['today_fee_total']:.2f} "
        f"fees_alltime=${data['all_time_fee_total']:.2f} "
        f"settled=${data['settled_claims']} "
        f"ledger=${data['ledger_count']}tx "
        f"pending=${data['pending_fee_count']} "
        f"sent={'ok' if sent_ok else 'failed'}"
    )
    log_to_agent_activity(started_at, "ok" if sent_ok else "warn", summary)
    log.info(f"done: {summary}")
    return 0 if sent_ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Empire AI Daily Revenue Report")
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
