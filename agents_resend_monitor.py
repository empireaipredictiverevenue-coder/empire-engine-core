"""
Empire AI · Resend Domain Monitor
=================================
Polls the Resend API every 6h to verify the sending domain's DNS
records are still healthy. Logs the result to agent_activity so the
operator SPA can chart it, and fires a Telegram alert if the domain
status flips from `verified` to anything else.

Why this matters: Resend emails WILL FAIL SILENTLY if the domain is
partially_failed (DKIM/SPF/Tracking records invalid). We've seen this
once already (2026-06-17, empire-ai.co.uk stuck at partially_failed
because the tracking CNAME wasn't set in Cloudflare). Without this
monitor, the email channel goes dark and nobody notices for days.

The tracking CNAME is the most fragile piece because Cloudflare proxies
CNAMEs by default, which breaks Resend's verification. The fix is
to add the CNAME as "DNS only" (grey cloud). This monitor catches it.

VERIFICATION: status=verified means Resend accepts our domain.
Anything else (partially_failed, failed, unverified, etc) is a real
issue that needs operator action.
"""
import os
import sys
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path("/root/empire-v49").resolve()))

# Load .env files so RESEND_API_KEY, TELEGRAM_BOT_TOKEN, etc. are present
# even when run from cron (which doesn't inherit a login-shell env).
# Two locations: /root/.env (operational secrets) and /root/.hermes/.env
# (telegram bot token). Both must be loaded because empire code reads
# from one and hermes code reads from the other, depending on context.
try:
    from dotenv import load_dotenv
    for env_file in ("/root/.env", "/root/.hermes/.env"):
        try:
            load_dotenv(env_file)
        except Exception as e:
            print(f"[resend-monitor] dotenv load {env_file}: {e}", file=sys.stderr)
except Exception:
    pass  # dotenv optional; fall back to whatever env the caller provides

import httpx
from supabase import create_client

log = logging.getLogger("agents_resend_monitor")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [resend-monitor] %(levelname)s %(message)s",
)

AGENT_NAME = "resend_domain_monitor"
RESEND_BASE = "https://api.resend.com"
DOMAIN_NAME = "empire-ai.co.uk"  # single domain for now; can be made list


def _api_key() -> str:
    key = os.environ.get("RESEND_API_KEY", "")
    if not key:
        log.error("RESEND_API_KEY not set")
    return key


def _telegram_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _telegram_chat_id() -> str:
    # Phil's operator chat (Empire1aibot). Falls back to default if missing.
    return os.environ.get("OPERATOR_TELEGRAM_CHAT_ID", "808657420")


async def _send_telegram_alert(message: str) -> bool:
    """Best-effort Telegram alert. Silent on failure so the monitor doesn't
    crash if Telegram is misconfigured."""
    tok = _telegram_token()
    chat = _telegram_chat_id()
    if not tok:
        log.warning("TELEGRAM_BOT_TOKEN not set; skipping alert")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True},
            )
            ok = r.status_code == 200
            if not ok:
                log.warning(f"telegram send returned {r.status_code}: {r.text[:200]}")
            return ok
    except Exception as e:
        log.warning(f"telegram send failed: {e}")
        return False


def _fetch_domain_status(api_key: str) -> dict:
    """Hit Resend's /domains endpoint, return the row for empire-ai.co.uk
    plus the per-record status. Caches nothing — fresh on every call."""
    if not api_key:
        return {"ok": False, "error": "missing_api_key"}
    try:
        # List domains, then pull detail for ours
        with httpx.Client(timeout=15) as client:
            r = client.get(
                f"{RESEND_BASE}/domains",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if r.status_code != 200:
                return {"ok": False, "error": f"list_status_{r.status_code}", "body": r.text[:300]}
            data = r.json()
            rows = data.get("data", [])
            our = next((d for d in rows if d.get("name") == DOMAIN_NAME), None)
            if not our:
                return {"ok": False, "error": "domain_not_found", "available": [d.get("name") for d in rows]}

            # Pull detail with the records array
            detail_r = client.get(
                f"{RESEND_BASE}/domains/{our['id']}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if detail_r.status_code != 200:
                return {"ok": False, "error": f"detail_status_{detail_r.status_code}"}
            detail = detail_r.json()
            records = detail.get("records", [])
            failed_records = [
                {"record": r.get("record"), "name": r.get("name"), "type": r.get("type"), "status": r.get("status")}
                for r in records if r.get("status") != "verified"
            ]
            return {
                "ok": True,
                "domain_id": our["id"],
                "domain_name": detail.get("name"),
                "domain_status": detail.get("status"),
                "region": detail.get("region"),
                "tracking_subdomain": detail.get("tracking_subdomain"),
                "open_tracking": detail.get("open_tracking"),
                "click_tracking": detail.get("click_tracking"),
                "records_total": len(records),
                "records_verified": sum(1 for r in records if r.get("status") == "verified"),
                "records_failed": failed_records,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"http_error: {type(e).__name__}: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"unexpected: {type(e).__name__}: {e}"}


def run_once() -> dict:
    """Single pass: check the domain, log to agent_activity, alert on failure."""
    api_key = _api_key()
    started_at = datetime.now(timezone.utc)
    result = _fetch_domain_status(api_key)

    if not result.get("ok"):
        log.error(f"check failed: {result.get('error')}")
        # Log + alert even on API failure (key revoked, network down, etc)
        _log_to_agent_activity(started_at, "error", summary=f"check failed: {result.get('error')[:200]}", details=result)  # already 'error', schema-OK
        asyncio.run(_send_telegram_alert(
            f"🔴 Resend monitor: API check failed\n\n"
            f"<code>{result.get('error', 'unknown')}</code>\n\n"
            f"Domain emails may be silently broken. Check RESEND_API_KEY."
        ))
        return {"status": "error", "result": result}

    status = result.get("domain_status", "unknown")
    verified = result.get("records_verified", 0)
    total = result.get("records_total", 0)
    failed = result.get("records_failed", [])

    summary = (
        f"domain={result.get('domain_name')} status={status} "
        f"records={verified}/{total} verified"
    )
    if failed:
        summary += f" · FAILED: {', '.join(r['record'] + ':' + r['status'] for r in failed)}"

    log.info(summary)

    # Log to agent_activity (so operator SPA can chart it).
    # Schema CHECK: status in ('running','ok','error','skipped_disabled').
    # Use 'error' if domain not fully verified — more visible in the SPA.
    agent_status = "ok" if status == "verified" else "error"
    _log_to_agent_activity(
        started_at, agent_status,
        summary=summary[:500],
        details=result,
    )

    # Alert if not fully verified
    if status != "verified":
        failed_lines = "\n".join(
            f"  • {r['record']} ({r['type']} {r['name']}): {r['status']}"
            for r in failed
        ) or "  (no per-record failure detail)"
        asyncio.run(_send_telegram_alert(
            f"🔴 Resend domain <b>{result.get('domain_name')}</b> status: <b>{status}</b>\n\n"
            f"Records: {verified}/{total} verified\n"
            f"Failed:\n{failed_lines}\n\n"
            f"⚠️  Emails may fail silently until fixed.\n"
            f"Check DNS in Cloudflare (CNAME must be DNS-only, not proxied)."
        ))
    else:
        log.info("all records verified — no alert needed")

    return {"status": agent_status, "result": result}


def _log_to_agent_activity(started_at, status: str, summary: str, details: dict) -> None:
    try:
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        sb.table("agent_activity").insert({
            "agent_name": AGENT_NAME,
            "run_id": str(uuid.uuid4()),
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "rows_seen": details.get("records_total", 0) if isinstance(details, dict) else 0,
            "rows_processed": details.get("records_verified", 0) if isinstance(details, dict) else 0,
            "rows_errored": len(details.get("records_failed", [])) if isinstance(details, dict) else 0,
            "error": details.get("error") if status == "error" else None,
            "summary": summary,
            "meta": details,  # full status payload for charting
        }).execute()
    except Exception as e:
        log.error(f"failed to log to agent_activity: {e}")


if __name__ == "__main__":
    out = run_once()
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if out.get("status") == "ok" else 1)
