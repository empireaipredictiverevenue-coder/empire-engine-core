"""
Empire AI · Predictive Revenue
Contractor Outreach Agent
===========================

Recruitment arm. For every active contractor without an active
contractor_recruit sequence, enroll them. Track replies.

Usage:
    python3 -m agents.contractor_outreach
    python3 -m agents.contractor_outreach --status
"""
import os
import sys
import json
import uuid
import logging
import urllib.request
import urllib.error
import argparse
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.contractor_outreach")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


SEQUENCE = "contractor_recruit"


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", "contractor_outreach").limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True, "max_per_run": 25, "metros": []}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", 25),
        "metros": cfg.get("metros", []),
    }


def _log_activity(sb, agent_name, run_id, started_at, status, **kwargs):
    finished_at = datetime.now(timezone.utc).isoformat()
    sb.table("agent_activity").insert({
        "agent_name": agent_name,
        "run_id": str(run_id),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at,
        "status": status,
        **kwargs,
    }).execute()
    return finished_at


def _update_config(sb, agent_name, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", agent_name).execute()


def _normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def _has_active_recruit_sequence(sb, phone: str) -> bool:
    norm = _normalize_phone(phone)
    if not norm:
        return False
    r = sb.table("sms_sequences").select("id, status").eq("phone", norm).eq("sequence_type", SEQUENCE).limit(1).execute()
    if r.data:
        return r.data[0]["status"] == "active"
    return False


def _enroll_via_hub(hub_url: str, hub_token: str, phone: str, contractor: dict) -> dict:
    url = f"{hub_url.rstrip('/')}/api/v1/sms/enroll"
    payload = json.dumps({
        "phone": phone,
        "target_addr": f"{contractor.get('metro','')} ({contractor.get('name','')})",
        "sequence_type": SEQUENCE,
        "meta": {
            "contractor_id": contractor.get("id"),
            "contractor_name": contractor.get("name"),
            "metro": contractor.get("metro"),
            "source": "contractor_outreach_agent",
        },
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST",
                                  headers={"Content-Type": "application/json",
                                           "Authorization": f"Bearer {hub_token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"http_{e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def run() -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)

    if not cfg["enabled"]:
        _log_activity(sb, "contractor_outreach", run_id, started_at, "skipped_disabled",
                      summary="disabled in agent_config")
        _update_config(sb, "contractor_outreach", "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    # 1) Get all active contractors
    q = sb.table("contractors").select("id, name, email, phone, metro, active, meta").eq("active", True).limit(500)
    if cfg["metros"]:
        q = q.in_("metro", cfg["metros"])
    res = q.execute()
    candidates = res.data or []
    log.info(f"contractor_outreach: {len(candidates)} active contractors (filter metros={cfg['metros']})")
    rows_seen = len(candidates)

    # 2) Filter to those without an active recruit sequence AND have a phone
    to_enroll = []
    for c in candidates:
        phone = _normalize_phone(c.get("phone", ""))
        if not phone:
            continue
        if _has_active_recruit_sequence(sb, phone):
            continue
        to_enroll.append(c)
    to_enroll = to_enroll[:cfg["max_per_run"]]
    log.info(f"contractor_outreach: {len(to_enroll)} need recruitment (no active sequence)")

    # 3) Enroll each
    rows_processed = 0
    rows_errored = 0
    rows_skipped = 0
    error_msgs = []
    sample_enrolls = []
    hub_url = os.getenv("HUB_URL", "http://127.0.0.1:8000")
    hub_token = os.getenv("HUB_TOKEN", "")

    for c in to_enroll:
        try:
            phone = _normalize_phone(c.get("phone", ""))
            if cfg["dry_run"]:
                sb.table("outreach_log").insert({
                    "enriched_lead_id": None,
                    "agent_name": "contractor_outreach",
                    "run_id": str(run_id),
                    "channel": "sms",
                    "sequence": SEQUENCE,
                    "step": 0,
                    "body_preview": f"[DRY-RUN] would enroll {c.get('name')} ({phone}) in {SEQUENCE}",
                    "compliance_passed": True,
                    "mode": "dry_run",
                }).execute()
                rows_processed += 1
                continue

            result = _enroll_via_hub(hub_url, hub_token, phone, c)
            ok = result.get("ok", False)
            sb.table("outreach_log").insert({
                "enriched_lead_id": None,
                "agent_name": "contractor_outreach",
                "run_id": str(run_id),
                "channel": "sms",
                "sequence": SEQUENCE,
                "step": 0,
                "body_preview": f"enroll result for {c.get('name')}: {json.dumps(result)[:200]}",
                "compliance_passed": True,
                "mode": "live",
                "sent_at": datetime.now(timezone.utc).isoformat() if ok else None,
                "sent_status": "enrolled" if ok else "failed",
            }).execute()
            if ok:
                rows_processed += 1
                if len(sample_enrolls) < 3:
                    sample_enrolls.append({
                        "contractor": c.get("name"),
                        "phone": phone,
                        "metro": c.get("metro"),
                        "sequence_id": result.get("sequence_id"),
                    })
            else:
                rows_errored += 1
                error_msgs.append(f"{c.get('name')}: {result.get('error', '?')[:120]}")
        except Exception as e:
            rows_errored += 1
            error_msgs.append(f"{c.get('id', '?')[:8]}: {type(e).__name__}: {e}")
            log.warning(f"contractor_outreach: failed for {c.get('name')}: {e}")

    finished_at = datetime.now(timezone.utc)
    mode_label = "dry-run" if cfg["dry_run"] else "LIVE"
    summary = (f"[{mode_label}] scanned {rows_seen} contractors, "
               f"{rows_processed} enrolled, {rows_errored} errored")
    if sample_enrolls:
        summary += f". Sample: {json.dumps(sample_enrolls, default=str)[:500]}"
    status = "ok" if rows_errored == 0 else "ok"
    err_field = None if rows_errored == 0 else "; ".join(error_msgs[:5])

    _log_activity(sb, "contractor_outreach", run_id, started_at, status,
                  rows_seen=rows_seen, rows_processed=rows_processed,
                  rows_errored=rows_errored, error=err_field, summary=summary)
    _update_config(sb, "contractor_outreach", status, finished_at.isoformat())

    log.info(summary[:200])
    return {"status": status, "rows_seen": rows_seen, "rows_processed": rows_processed,
            "rows_errored": rows_errored, "sample_enrolls": sample_enrolls}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true")
    args = p.parse_args()
    if args.status:
        sb = _sb()
        cfg = _read_config(sb)
        last_act = (sb.table("agent_activity").select("*").eq("agent_name", "contractor_outreach").order("started_at", desc=True).limit(1).execute())
        print(json.dumps({"config": cfg, "last_run": last_act.data[0] if last_act.data else None},
                         indent=2, default=str))
        return
    result = run()
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled") else 1)


if __name__ == "__main__":
    main()
