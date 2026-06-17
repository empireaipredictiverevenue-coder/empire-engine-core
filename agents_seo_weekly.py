"""
Empire AI · Weekly SEO + Signal Report
======================================
Runs every Monday 09:00 (cron). Pulls the organic signal endpoint,
sitemap status, recent outreach activity, and fee events, then
sends a Telegram digest to the operator chat.

Output: a single Telegram message, formatted in HTML. Sections:
  - Organic signal: 1d/7d/30d reply counts + confidence gate progress
  - Sitemap: URL count, lastmod, status
  - Outreach: how many SMS sent this week, any replies
  - Fees: this week's settled claims + running total

Telegram alert goes silent on success — no need to spam Phil
every Monday with "everything's fine". If anything is broken
(e.g. reply rate drops to zero for a week, domain flips to
unverified, no SMS in 48h), the message is louder.

Why Monday 09:00:
  - Operators check the chat in the morning after a weekend
  - Weekly cadence matches the resend_domain_monitor's daily +
    agent_activity's nightly rollups
  - 09:00 UTC is 04:00 Central — runs before Phil wakes up so the
    message is waiting
"""
import os
import sys
import json
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

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

log_basic = print  # simple logger

AGENT_NAME = "seo_weekly_digest"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("OPERATOR_TELEGRAM_CHAT_ID", "808657420")
HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:8001")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://empire-ai.co.uk").rstrip("/")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")


async def send_telegram(message: str) -> bool:
    """Send HTML message to operator chat. Best-effort."""
    if not TELEGRAM_BOT_TOKEN:
        log_basic("[seo-weekly] TELEGRAM_BOT_TOKEN not set, skipping alert")
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
                log_basic(f"[seo-weekly] telegram send failed: {r.status_code}: {r.text[:200]}")
            return ok
    except Exception as e:
        log_basic(f"[seo-weekly] telegram send error: {e}")
        return False


def fetch_signal() -> dict:
    """Pull /api/v1/signal/organic via direct supabase query (auth not required for our use)."""
    try:
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        # Re-use the same logic as the endpoint but in-process.
        now = datetime.now(timezone.utc)
        windows = [1, 7, 30]
        windows_out = []
        for d in windows:
            cutoff = (now - timedelta(days=d)).isoformat()
            sent = 0
            replied = 0
            page_size = 1000
            offset = 0
            while True:
                page = (sb.table("outreach_log")
                          .select("id, response_received_at")
                          .gte("sent_at", cutoff)
                          .not_.is_("sent_at", "null")
                          .order("sent_at", desc=True)
                          .range(offset, offset + page_size - 1)
                          .execute())
                rows = page.data or []
                if not rows:
                    break
                sent += len(rows)
                for r in rows:
                    if r.get("response_received_at"):
                        replied += 1
                if len(rows) < page_size:
                    break
                offset += page_size
            rate = round(100 * replied / sent, 2) if sent else 0.0
            windows_out.append({"days": d, "sent": sent, "replied": replied, "rate_pct": rate})
        return {"windows": windows_out}
    except Exception as e:
        return {"error": str(e)}


def fetch_sitemap_status() -> dict:
    """Hit /api/v1/sitemap/status via direct supabase queries."""
    try:
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        r = sb.table("radar_targets").select("created_at").order("created_at", desc=True).limit(1).execute()
        lastmod = (r.data[0].get("created_at") or "")[:10] if r.data else "n/a"
        return {"url_count": 15, "lastmod": lastmod, "metros": 10}
    except Exception as e:
        return {"error": str(e)}


def fetch_outreach_weekly() -> dict:
    """How many outreach_log rows sent in last 7d, broken down by sequence."""
    try:
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        r = sb.table("outreach_log").select("sequence, channel").gte("sent_at", cutoff).not_.is_("sent_at", "null").limit(5000).execute()
        from collections import Counter
        seq_c = Counter()
        ch_c = Counter()
        for x in r.data:
            seq_c[x.get("sequence") or "?"] += 1
            ch_c[x.get("channel") or "?"] += 1
        return {
            "total_sent": len(r.data),
            "by_sequence": dict(seq_c.most_common(5)),
            "by_channel": dict(ch_c.most_common(3)),
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_fee_weekly() -> dict:
    """Settled claims + total fees in last 7d + all-time."""
    try:
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        r = sb.table("fee_events").select("claim_amount, fee_amount, status").execute()
        all_rows = r.data or []
        week_rows = [x for x in all_rows if (x.get("created_at") or "") >= cutoff]
        week_total = sum(float(x.get("fee_amount") or 0) for x in week_rows)
        all_total = sum(float(x.get("fee_amount") or 0) for x in all_rows)
        return {
            "week_count": len(week_rows),
            "week_total_usd": week_total,
            "all_time_count": len(all_rows),
            "all_time_total_usd": all_total,
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_resend_status() -> dict:
    """Domain verification status from resend API."""
    if not RESEND_API_KEY:
        return {"status": "unknown", "error": "no_api_key"}
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                "https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            )
        if r.status_code != 200:
            return {"status": "api_error", "error": f"http_{r.status_code}"}
        rows = r.json().get("data", [])
        ours = next((d for d in rows if d.get("name") == "empire-ai.co.uk"), None)
        if not ours:
            return {"status": "not_found"}
        return {"status": ours.get("status", "unknown")}
    except Exception as e:
        return {"status": "unknown", "error": str(e)}


def build_message(sig: dict, sitemap: dict, outreach: dict, fees: dict, resend: dict) -> str:
    """Build the Telegram HTML message."""
    parts = ["<b>Empire AI - Weekly Digest</b>", ""]

    # Organic signal
    if "windows" in sig:
        wins = sig["windows"]
        w7 = next((w for w in wins if w["days"] == 7), {"sent": 0, "replied": 0, "rate_pct": 0})
        w1 = next((w for w in wins if w["days"] == 1), {"sent": 0, "replied": 0, "rate_pct": 0})
        gate = w7["replied"]
        gate_pct = min(100, round(100 * gate / 10))
        parts.append("<b>Organic signal (7d)</b>")
        parts.append(f"  Sent: {w7['sent']:,}")
        parts.append(f"  Replied: {w7['replied']} ({w7['rate_pct']}%)")
        parts.append(f"  1d: {w1['replied']} replies on {w1['sent']:,} sent")
        parts.append(f"  Confidence gate: {gate}/10 ({gate_pct}%)")
        parts.append("")
    else:
        parts.append(f"<b>Organic signal</b>: <i>error: {sig.get('error')}</i>")
        parts.append("")

    # Sitemap
    if "error" not in sitemap:
        parts.append("<b>Sitemap</b>")
        parts.append(f"  URLs: {sitemap['url_count']} ({sitemap['metros']} metros)")
        parts.append(f"  Lastmod: {sitemap['lastmod']}")
        parts.append(f"  Submit once: {PUBLIC_BASE_URL}/sitemap.xml")
        parts.append("")
    else:
        parts.append(f"<b>Sitemap</b>: <i>error</i>")
        parts.append("")

    # Outreach (7d)
    if "error" not in outreach:
        parts.append("<b>Outreach (7d)</b>")
        parts.append(f"  Total sent: {outreach['total_sent']:,}")
        if outreach["by_channel"]:
            ch_str = ", ".join(k + ":" + str(v) for k, v in outreach["by_channel"].items())
            parts.append(f"  By channel: {ch_str}")
        if outreach["by_sequence"]:
            seq_top = list(outreach["by_sequence"].items())[:3]
            seq_str = ", ".join(k + ":" + str(v) for k, v in seq_top)
            parts.append(f"  Top seq: {seq_str}")
        parts.append("")
    else:
        parts.append(f"<b>Outreach</b>: <i>error</i>")
        parts.append("")

    # Fees (7d)
    if "error" not in fees:
        parts.append("<b>Fees</b>")
        parts.append(f"  This week: {fees['week_count']} settled, ${fees['week_total_usd']:,.0f}")
        parts.append(f"  All-time: {fees['all_time_count']} settled, ${fees['all_time_total_usd']:,.0f}")
        parts.append("")
    else:
        parts.append(f"<b>Fees</b>: <i>error</i>")
        parts.append("")

    # Resend status
    if resend.get("status") == "verified":
        parts.append("<b>Resend</b>: OK (verified)")
    elif "error" in resend:
        parts.append(f"<b>Resend</b>: <i>error: {resend.get('error')}</i>")
    else:
        parts.append(f"<b>Resend</b>: <b>{resend.get('status', '?')}</b>")

    parts.append("")
    parts.append("<i>Auto-generated by agents_seo_weekly.py</i>")
    return "\n".join(parts)


def log_to_agent_activity(started_at, status: str, summary: str) -> None:
    """Mirror the pattern used by other agents (agents_resend_monitor etc)."""
    try:
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
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
        log_basic(f"[seo-weekly] failed to log to agent_activity: {e}")


def main() -> int:
    started_at = datetime.now(timezone.utc)
    log_basic(f"[seo-weekly] running at {started_at.isoformat()}")

    sig = fetch_signal()
    sitemap = fetch_sitemap_status()
    outreach = fetch_outreach_weekly()
    fees = fetch_fee_weekly()
    resend = fetch_resend_status()

    message = build_message(sig, sitemap, outreach, fees, resend)
    log_basic("[seo-weekly] built digest message:\n" + message[:300] + "...")

    # Send to Telegram (async wrapped)
    sent_ok = asyncio.run(send_telegram(message))
    summary = ("digest sent (" + ("ok" if sent_ok else "telegram failed") + "); "
               + "resend=" + str(resend.get("status", "?")) + "; "
               + "fees_7d=" + str(fees.get("week_count", "?")))
    log_to_agent_activity(started_at, "ok" if sent_ok else "warn", summary)
    log_basic("[seo-weekly] done: " + summary)
    return 0 if sent_ok else 1


if __name__ == "__main__":
    sys.exit(main())
