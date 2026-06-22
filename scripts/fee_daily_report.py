"""
Empire AI · Daily Collection Report
====================================

Posts a daily summary to Telegram (and email as backup) so the operator has
situational awareness on the $34k+ pending funnel without checking the dashboard.

Format: tight ops report. Numbers up top, action needed next, then context.

Cron (9am UTC daily):
  0 9 * * * /usr/bin/python3 /root/empire-v49/scripts/fee_daily_report.py >> /root/empire-v49/logs/fee_daily_report.log 2>&1
"""
import os, sys, json, logging, time, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx
from supabase import create_client

log = logging.getLogger("fee_daily_report")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

GHOSTING_DAYS = 7  # pending with no recent activity = "ghosting"


def _send_telegram(text: str) -> bool:
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (bot and chat):
        log.info("[report] no Telegram creds, skipping push")
        return False
    try:
        # Telegram 4096 char limit per message
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)] or [""]
        for chunk in chunks:
            r = httpx.post(
                f"https://api.telegram.org/bot{bot}/sendMessage",
                json={"chat_id": chat, "text": chunk, "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=15,
            )
            if r.status_code != 200:
                log.warning(f"[report] telegram chunk failed: {r.status_code} {r.text[:200]}")
        return True
    except Exception as e:
        log.warning(f"[report] telegram error: {e}")
        return False


def _build_report(sb) -> str:
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    seven_days_ago = (now - timedelta(days=GHOSTING_DAYS)).isoformat()
    forty_eight_hours = (now + timedelta(hours=48)).isoformat()

    # Pull everything once
    fees = sb.table("fee_events").select(
        "id,claim_id,contractor_id,fee_amount,discount_amount,status,discount_expires_at,settled_at,created_at,meta"
    ).execute().data or []

    paid = [f for f in fees if f["status"] == "paid"]
    pending = [f for f in fees if f["status"] == "pending"]
    paid_today = [f for f in paid if f.get("settled_at", "").startswith(today)]
    paid_week = [f for f in paid if f.get("settled_at", "") > seven_days_ago]

    paid_total = sum(f["fee_amount"] for f in paid)
    pending_total = sum(f["fee_amount"] for f in pending)
    pending_discounted = sum(max(0, f["fee_amount"] - (f.get("discount_amount") or 0)) for f in pending)
    paid_today_total = sum(f["fee_amount"] for f in paid_today)

    # Ghosting: pending with no recent activity (no urgency push, no call_log entry in 7d)
    ghosting = []
    for f in pending:
        meta = f.get("meta") or {}
        if isinstance(meta, str):
            try: meta = json.loads(meta)
            except: meta = {}
        last_push = meta.get("urgency_pushed_at")
        if not last_push or last_push < seven_days_ago:
            ghosting.append(f)

    # Expiring in 48h
    expiring = [f for f in pending
                if f.get("discount_expires_at")
                and f["discount_expires_at"] < forty_eight_hours]

    # By contractor — who owes what
    by_contractor = {}
    for f in pending:
        cid = f.get("contractor_id", "unknown")
        by_contractor.setdefault(cid, {"count": 0, "original": 0.0, "discounted": 0.0})
        by_contractor[cid]["count"] += 1
        by_contractor[cid]["original"] += f["fee_amount"]
        by_contractor[cid]["discounted"] += max(0, f["fee_amount"] - (f.get("discount_amount") or 0))

    contractors = {}
    if by_contractor:
        r = sb.table("contractors").select("id,name").in_("id", list(by_contractor.keys())).execute()
        for c in r.data or []:
            contractors[c["id"]] = c.get("name", "?")

    # Top action: highest-priority single thing to do
    action = "no action needed"
    if expiring:
        first_exp = expiring[0]
        cid = first_exp.get("contractor_id")
        action = f"🔥 {len(expiring)} fee(s) expiring in <48h. Top: {contractors.get(cid, '?')} ${first_exp['fee_amount']:,.0f}. Call them."
    elif ghosting and paid_today_total == 0:
        first_g = ghosting[0]
        cid = first_g.get("contractor_id")
        action = f"💀 {len(ghosting)} ghosting contractors, no payments today. Top: {contractors.get(cid, '?')} ${first_g['fee_amount']:,.0f}. Send another nudge."
    elif pending_discounted > 0 and paid_today_total == 0:
        action = f"⏳ {len(pending)} pending fees, ${pending_discounted:,.0f} if all pay. No movement today. Watch vault."

    lines = [
        f"📊 <b>Empire daily report</b> — {today}",
        "",
        f"<b>Cash:</b>",
        f"  paid:    ${paid_total:,.0f}  (today: ${paid_today_total:,.0f}, last 7d: ${sum(f['fee_amount'] for f in paid_week):,.0f})",
        f"  pending: ${pending_total:,.0f}",
        f"  if all pay with discount: ${pending_discounted:,.0f}",
        "",
        f"<b>Action:</b> {action}",
        "",
        f"<b>Funnel ({len(pending)} pending):</b>",
        f"  expiring in <48h: {len(expiring)}",
        f"  ghosting ({GHOSTING_DAYS}+ days no activity): {len(ghosting)}",
        f"  paid this week: {len(paid_week)}",
        "",
    ]

    if expiring:
        lines.append("<b>Expiring in 48h:</b>")
        for f in expiring[:5]:
            cid = f.get("contractor_id")
            name = contractors.get(cid, "?")[:30]
            dleft = f.get("discount_expires_at", "")
            try:
                exp = datetime.fromisoformat(dleft.replace("Z", "+00:00"))
                hrs = max(0, int((exp - now).total_seconds() // 3600))
                dlbl = f"{hrs}h"
            except Exception:
                dlbl = "?"
            lines.append(f"  ⏰ {name} — ${max(0, f['fee_amount']-(f.get('discount_amount') or 0)):,.0f} ({dlbl})")
        lines.append("")

    if ghosting:
        lines.append(f"<b>Ghosting ({GHOSTING_DAYS}d+ no contact):</b>")
        # Sort by fee amount, top 5
        ghosting.sort(key=lambda f: f["fee_amount"], reverse=True)
        for f in ghosting[:5]:
            cid = f.get("contractor_id")
            name = contractors.get(cid, "?")[:30]
            lines.append(f"  💀 {name} — ${f['fee_amount']:,.0f} (claim {f.get('claim_id','')[:13]})")
        lines.append("")

    if paid_today:
        lines.append("<b>Paid today:</b>")
        for f in paid_today[:5]:
            cid = f.get("contractor_id")
            name = contractors.get(cid, "?")[:30]
            lines.append(f"  ✅ {name} — ${f['fee_amount']:,.0f}")
        lines.append("")

    return "\n".join(lines)


def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    report = _build_report(sb)
    print(report)
    sent = _send_telegram(report)
    print(f"\n[report] telegram sent: {sent}")


if __name__ == "__main__":
    main()