"""Empire AI · System Supervisor

Daily watchdog that catches breaks before they fester. Runs via cron at 09:00 UTC.

Checks:
  1. CRON HEALTH — every cron-managed agent's last_run_at within expected window
  2. HUB ROUTES — every documented /api/v1/* route returns 200/expected (sample probe)
  3. AGENT ERRORS — agent_activity rows in last 24h with status != ok and rows_errored > 0
  4. MONEY FIELDS — radar_targets.asset_value in placeholder tier ($1-$50)
  5. PLACEHOLDER EMAILS — contractors / prospects with synthetic/placeholder emails
  6. ZOMBIE OUTREACH — outreach_log rows > 7d old with no response_received_at

Posts a single Telegram message with severity tier (OK / WARN / CRITICAL).
CRITICAL issues page Phil; WARN issues are summarized in the daily digest.

Usage:
    python3 -m agents.system_supervisor              # full check + telegram
    python3 -m agents.system_supervisor --no-tg      # dry run (just print)
    python3 -m agents.system_supervisor --json       # machine-readable
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

import httpx
from supabase import create_client

log = logging.getLogger("empire.system_supervisor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# ── CRITICAL AGENTS — if these don't run, revenue breaks ─────────────────
# Format: agent_name -> expected max interval in hours
CRITICAL_AGENT_MAX_INTERVAL_HOURS = {
    "fee_collection":         2.0,
    "dispatch":               1.0,
    "lead_scanner":           1.0,
    "lead_enricher":          1.0,
    "lead_converter":         0.5,
    "contractor_outreach":    4.0,
    "storm_alert":            1.0,
    "vault_monitor":          1.0,
}


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _check_cron_health(sb) -> list[dict]:
    """Each critical agent's last_run_at must be within expected window."""
    issues = []
    r = sb.table("agent_config").select("agent_name,last_run_at,last_run_status,enabled").execute()
    cfg_map = {x["agent_name"]: x for x in (r.data or [])}
    now = datetime.now(timezone.utc)
    for agent, max_h in CRITICAL_AGENT_MAX_INTERVAL_HOURS.items():
        cfg = cfg_map.get(agent)
        if not cfg:
            issues.append({"check": "cron", "agent": agent, "severity": "warn",
                           "msg": f"no agent_config row"})
            continue
        if not cfg.get("enabled"):
            continue  # disabled agents are intentional
        last = cfg.get("last_run_at")
        if not last:
            issues.append({"check": "cron", "agent": agent, "severity": "critical",
                           "msg": f"never ran"})
            continue
        try:
            # Python 3.10 fromisoformat is strict — can't parse .XXXX+00:00 with
            # arbitrary fractional digits. Drop fractional entirely; we only need minute precision.
            last_clean = last
            for suffix in ("Z", "+00:00", "-00:00"):
                if last_clean.endswith(suffix):
                    last_clean = last_clean[:-len(suffix)]
                    break
            # also strip any other tz offset like +05:30
            import re as _re
            last_clean = _re.sub(r"[+-]\d{2}:?\d{2}$", "", last_clean)
            # and strip fractional seconds
            if "." in last_clean:
                last_clean = last_clean.split(".")[0]
            last_dt = datetime.fromisoformat(last_clean).replace(tzinfo=timezone.utc)
        except Exception:
            issues.append({"check": "cron", "agent": agent, "severity": "warn",
                           "msg": f"unparseable last_run_at: {last}"})
            continue
        age_h = (now - last_dt).total_seconds() / 3600.0
        if age_h > max_h:
            issues.append({"check": "cron", "agent": agent, "severity": "critical",
                           "msg": f"last ran {age_h:.1f}h ago (max {max_h}h)"})
        elif cfg.get("last_run_status") == "error":
            issues.append({"check": "cron", "agent": agent, "severity": "warn",
                           "msg": f"last run status=error"})
    return issues


def _check_agent_errors(sb) -> list[dict]:
    """agent_activity rows in last 24h with errors."""
    issues = []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    r = (sb.table("agent_activity")
           .select("agent_name,status,rows_errored,error,started_at")
           .gte("started_at", cutoff)
           .gt("rows_errored", 0)
           .order("started_at", desc=True)
           .limit(20)
           .execute())
    for x in (r.data or []):
        issues.append({"check": "agent_errors", "agent": x["agent_name"],
                       "severity": "warn",
                       "msg": f"errored on {x['started_at'][:19]}: {(x.get('error') or '')[:80]}"})
    return issues


def _check_money_placeholders(sb) -> list[dict]:
    """radar_targets.asset_value in placeholder tier ($1-$50)."""
    issues = []
    r = sb.table("radar_targets").select("id", count="exact").gt("asset_value", 0).lte("asset_value", 50).execute()
    n_placeholder = r.count or 0
    if n_placeholder > 100:
        issues.append({"check": "money_placeholder", "severity": "critical",
                       "msg": f"{n_placeholder} radar_targets have placeholder asset_value ($1-$50)"})
    elif n_placeholder > 0:
        issues.append({"check": "money_placeholder", "severity": "warn",
                       "msg": f"{n_placeholder} radar_targets have placeholder asset_value"})
    return issues


def _check_placeholder_emails(sb) -> list[dict]:
    """Contractors / prospects with synthetic / placeholder emails."""
    issues = []
    placeholder_patterns = ["@empire-ai.placeholder", "@placeholder", ".placeholder@"]
    for tbl in ("contractors", "prospects"):
        for pat in placeholder_patterns:
            try:
                r = sb.table(tbl).select("id", count="exact").like("email", f"%{pat}%").execute()
                n = r.count or 0
                if n > 50:
                    issues.append({"check": "placeholder_email", "table": tbl,
                                   "pattern": pat, "severity": "warn",
                                   "msg": f"{n} rows in {tbl} match '{pat}'"})
            except Exception:
                # column doesn't exist on this table — skip
                continue
    return issues


def _check_zombie_outreach(sb) -> list[dict]:
    """outreach_log rows > 7d old with no response."""
    issues = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    r = (sb.table("outreach_log")
           .select("id", count="exact")
           .lt("created_at", cutoff)
           .is_("response_received_at", "null")
           .execute())
    n = r.count or 0
    if n > 200:
        issues.append({"check": "zombie_outreach", "severity": "warn",
                       "msg": f"{n} outreach rows > 7d old, no response"})
    return issues


def _check_hub_routes() -> list[dict]:
    """Probe a few key hub endpoints for 200s."""
    issues = []
    hub = os.getenv("HUB_URL", "http://localhost:8001").rstrip("/")
    probes = [
        ("/api/v1/bbb/recent", 200),
        ("/api/v1/bbb/stats", 200),
    ]
    for path, expected in probes:
        try:
            r = httpx.get(f"{hub}{path}", timeout=15)
            if r.status_code != expected:
                issues.append({"check": "hub_route", "path": path, "severity": "critical",
                               "msg": f"{path} returned {r.status_code} (expected {expected})"})
        except Exception as e:
            issues.append({"check": "hub_route", "path": path, "severity": "critical",
                           "msg": f"{path} probe failed: {type(e).__name__}: {e}"})
    return issues


def run() -> dict:
    sb = _sb()
    findings = []
    findings += _check_cron_health(sb)
    findings += _check_agent_errors(sb)
    findings += _check_money_placeholders(sb)
    findings += _check_placeholder_emails(sb)
    findings += _check_zombie_outreach(sb)
    findings += _check_hub_routes()

    crit = [f for f in findings if f.get("severity") == "critical"]
    warn = [f for f in findings if f.get("severity") == "warn"]
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "critical": crit,
        "warn": warn,
        "total": len(findings),
        "summary": f"{len(crit)} critical, {len(warn)} warn, {len(findings)} total",
    }


def _send_telegram(report: dict):
    bot = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("OPERATOR_TELEGRAM_CHAT_ID", "")
    if not bot or not chat:
        log.warning("TELEGRAM_BOT_TOKEN or OPERATOR_TELEGRAM_CHAT_ID not set; skip tg")
        return False
    if not report["critical"] and not report["warn"]:
        # All clear — only send if explicitly enabled
        if os.getenv("SUPERVISOR_ALWAYS_REPORT", "0") != "1":
            log.info("supervisor: all clear, skipping tg")
            return False

    lines = [f"*Empire System Supervisor* — {report['ts'][:19]}"]
    lines.append(f"`{report['summary']}`")
    if report["critical"]:
        lines.append("")
        lines.append("🔴 *CRITICAL*")
        for f in report["critical"]:
            ctx = f.get('agent') or f.get('path') or f.get('table') or ''
            lines.append(f"  • `{f.get('check')}` {ctx}: {f['msg']}")
    if report["warn"]:
        lines.append("")
        lines.append("🟡 *WARN*")
        for f in report["warn"][:10]:
            ctx = f.get('agent') or f.get('table') or ''
            lines.append(f"  • `{f.get('check')}` {ctx}: {f['msg']}")
    text = "\n".join(lines)
    # Strip problematic markdown — telegram markdown parser hates underscores in identifiers
    safe_text = text.replace("_", "-")
    try:
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat,
            "text": safe_text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "1",
        }).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10).read()
        log.info("supervisor: tg sent")
        return True
    except Exception as e:
        log.warning(f"supervisor: tg send failed: {e}")
        # Fallback: try plain text
        try:
            data2 = urllib.parse.urlencode({
                "chat_id": chat, "text": safe_text, "disable_web_page_preview": "1",
            }).encode()
            req2 = urllib.request.Request(url, data=data2)
            urllib.request.urlopen(req2, timeout=10).read()
            log.info("supervisor: tg sent (plain text)")
            return True
        except Exception as e2:
            log.warning(f"supervisor: tg plain fallback failed: {e2}")
            return False


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--no-tg", action="store_true", help="don't send telegram")
    p.add_argument("--json", action="store_true", help="json output")
    p.add_argument("--always", action="store_true", help="send tg even when all clear")
    args = p.parse_args()

    if args.always:
        os.environ["SUPERVISOR_ALWAYS_REPORT"] = "1"

    report = run()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"\n=== Empire System Supervisor — {report['ts'][:19]} ===")
        print(report["summary"])
        for f in report["critical"]:
            print(f"  CRIT  {f.get('check')}: {f.get('agent') or f.get('path') or f.get('table','')} — {f['msg']}")
        for f in report["warn"]:
            print(f"  WARN  {f.get('check')}: {f.get('agent') or f.get('table','')} — {f['msg']}")

    if not args.no_tg:
        _send_telegram(report)


if __name__ == "__main__":
    main()