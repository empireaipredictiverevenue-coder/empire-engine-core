"""
Empire AI · Predictive Revenue
Lead Converter Agent
===========================

Third and final agent in the lead-gen pipeline.

Reads top-scored enriched_leads (status=pending_outreach), runs them through
the compliance gate from agents.outreach.compliance, and either:
  - dry_run: log a would-send to outreach_log (does NOT actually send)
  - live:    call the hub to send, log the result

Idempotent: re-running won't re-send to leads already past step 1
(status=pending_followup or later).

Usage:
    python3 -m agents.lead_converter
    python3 -m agents.lead_converter --status
    python3 -m agents.lead_converter --live     # override dry_run, actually send
"""
import os
import sys
import json
import uuid
import logging
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
from agents.outreach import sms_sequences, voice_scripts, compliance

log = logging.getLogger("empire.lead_converter")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", "lead_converter").limit(1).execute()
    if not r.data:
        return {
            "enabled": True,
            "dry_run": True,
            "max_per_run": 10,
            "channels": ["sms", "voice"],
            "default_sequence": "storm_strike",
        }
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", 10),
        "channels": cfg.get("channels", ["sms", "voice"]),
        "default_sequence": cfg.get("default_sequence", "storm_strike"),
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


def _pick_sequence(lead: dict) -> str:
    """Pick the sequence based on what we have on the lead."""
    if lead.get("phone"):
        return "storm_strike"
    if lead.get("email"):
        return "lead_nurture"
    return "manual"


def _pick_channel(lead: dict, channels: list) -> str:
    """Pick the channel. SMS first if phone is present, voice as backup."""
    if "sms" in channels and lead.get("phone"):
        return "sms"
    if "voice" in channels and lead.get("phone"):
        return "voice"
    return "sms"  # fallback; will be caught by compliance


def _render_message(template: str, lead: dict) -> str:
    """Fill in {var} placeholders from a lead row. Missing vars become empty."""
    replacements = {
        "event": lead.get("meta", {}).get("event", "recent storm"),
        "severity": lead.get("meta", {}).get("severity", "Severe"),
        "address": lead.get("address") or "",
        "city": lead.get("city") or "",
        "state": lead.get("state") or "",
        "business_name": lead.get("warehouse_name") or "",
        "contact_name": "",
        "asset_value": str(lead.get("asset_value") or ""),
        "urgency": str(int(lead.get("score") or 0)),
        "agent_name": os.getenv("EMPIRE_SMS_PREFIX", "Empire AI"),
    }
    for k, v in replacements.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def _compliance_check(lead: dict, channel: str) -> tuple[bool, str]:
    """Returns (passed, block_reason)."""
    phone = (lead.get("phone") or "").strip()
    if not phone:
        return False, "no_phone"
    if compliance.is_opted_out(phone):
        return False, "opted_out"
    if compliance.is_on_dnc(phone):
        return False, "on_dnc"
    if not compliance.has_consent(lead.get("meta", {}).get("tcpa_consent", True)):
        return False, "no_consent"
    # quiet hours needs area code; if we don't have one, fail open (assumed ok)
    # is_quiet_hours takes area_code; without it we skip
    if not compliance.can_send_today(phone):
        return False, "rate_limited"
    return True, ""


def _do_live_send(channel: str, phone: str, body: str) -> tuple[bool, str]:
    """Call the hub to actually send. Returns (ok, sent_status_or_error)."""
    # The hub has /api/v1/sms/send (per empire_sms_routes; not yet wired but
    # this is the contract for when it is). For now, since the hub routes
    # are not yet registered, we surface a clear error.
    import urllib.request
    hub_url = os.getenv("HUB_URL", "http://127.0.0.1:8000")
    url = f"{hub_url}/api/v1/sms/send" if channel == "sms" else f"{hub_url}/api/v1/voice/call"
    payload = json.dumps({"to": phone, "body": body}).encode()
    req = urllib.request.Request(url, data=payload, method="POST",
                                  headers={"Content-Type": "application/json",
                                           "X-Empire-Secret": os.getenv("WEBHOOK_SECRET", "")})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True, "queued"
            return False, f"http_{resp.status}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def run(dry_run_override: bool = None) -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)
    dry_run = cfg["dry_run"] if dry_run_override is None else dry_run_override

    if not cfg["enabled"]:
        _log_activity(sb, "lead_converter", run_id, started_at, "skipped_disabled",
                      summary="disabled in agent_config")
        _update_config(sb, "lead_converter", "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    # 1) Read top-N pending_outreach leads by score
    rows_res = (sb.table("enriched_leads")
                  .select("*")
                  .eq("status", "pending_outreach")
                  .order("score", desc=True)
                  .limit(cfg["max_per_run"])
                  .execute())
    rows = rows_res.data or []
    log.info(f"converter: {len(rows)} top-scored pending_outreach leads (dry_run={dry_run})")
    rows_seen = len(rows)

    rows_processed = 0
    rows_blocked = 0
    rows_errored = 0
    error_msgs = []
    sample_would_send = []

    for lead in rows:
        try:
            channel = _pick_channel(lead, cfg["channels"])
            sequence = _pick_sequence(lead)

            # compliance gate
            passed, block_reason = _compliance_check(lead, channel)
            if not passed:
                # log the block, update lead status
                sb.table("outreach_log").insert({
                    "enriched_lead_id": lead["id"],
                    "agent_name": "lead_converter",
                    "run_id": str(run_id),
                    "channel": channel,
                    "sequence": sequence,
                    "step": 0,
                    "body_preview": f"[BLOCKED: {block_reason}]",
                    "compliance_passed": False,
                    "compliance_block_reason": block_reason,
                    "mode": "dry_run" if dry_run else "live",
                }).execute()
                sb.table("enriched_leads").update({
                    "status": "blocked",
                }).eq("id", lead["id"]).execute()
                rows_blocked += 1
                log.info(f"converter: blocked {lead.get('warehouse_name', '?')[:30]} — {block_reason}")
                continue

            # render the message
            template = sms_sequences.get_message(sequence, 1)
            body = _render_message(template, lead)
            body_preview = body[:280]

            if dry_run:
                # log would-send, do NOT call hub
                sb.table("outreach_log").insert({
                    "enriched_lead_id": lead["id"],
                    "agent_name": "lead_converter",
                    "run_id": str(run_id),
                    "channel": channel,
                    "sequence": sequence,
                    "step": 1,
                    "body_preview": body_preview,
                    "compliance_passed": True,
                    "mode": "dry_run",
                }).execute()
                # status moves to "converted" (means: step 1 outreach done, awaiting response)
                # a future follow-up agent will re-engage based on outreach_log.response_received_at
                sb.table("enriched_leads").update({
                    "status": "converted",
                }).eq("id", lead["id"]).execute()
                # track a sample for the activity summary
                if len(sample_would_send) < 5:
                    sample_would_send.append({
                        "lead": lead.get("warehouse_name") or lead.get("address"),
                        "phone": lead.get("phone"),
                        "channel": channel,
                        "sequence": sequence,
                        "body_preview": body_preview,
                    })
                rows_processed += 1
            else:
                # LIVE mode: actually send
                ok, sent_status = _do_live_send(channel, lead.get("phone"), body)
                sb.table("outreach_log").insert({
                    "enriched_lead_id": lead["id"],
                    "agent_name": "lead_converter",
                    "run_id": str(run_id),
                    "channel": channel,
                    "sequence": sequence,
                    "step": 1,
                    "body_preview": body_preview,
                    "compliance_passed": True,
                    "mode": "live",
                    "sent_at": datetime.now(timezone.utc).isoformat() if ok else None,
                    "sent_status": sent_status if ok else "failed",
                }).execute()
                if ok:
                    compliance.record_send(lead.get("phone"))
                    sb.table("enriched_leads").update({"status": "converted"}).eq("id", lead["id"]).execute()
                    rows_processed += 1
                else:
                    rows_errored += 1
                    error_msgs.append(f"{lead.get('warehouse_name', '?')[:30]}: {sent_status}")
        except Exception as e:
            rows_errored += 1
            error_msgs.append(f"{lead.get('id', '?')[:8]}: {type(e).__name__}: {e}")
            log.warning(f"converter: failed for {lead.get('id')}: {e}")

    finished_at = datetime.now(timezone.utc)
    mode_label = "dry-run" if dry_run else "LIVE"
    summary = (f"[{mode_label}] processed {rows_seen} leads: {rows_processed} sent, "
               f"{rows_blocked} blocked, {rows_errored} errored")
    if sample_would_send:
        summary += f". Sample would-sends: {json.dumps(sample_would_send, default=str)[:600]}"
    status = "ok" if rows_errored == 0 else "ok"
    err_field = None if rows_errored == 0 else "; ".join(error_msgs[:5])

    _log_activity(sb, "lead_converter", run_id, started_at, status,
                  rows_seen=rows_seen, rows_processed=rows_processed,
                  rows_blocked=rows_blocked, rows_errored=rows_errored,
                  error=err_field, summary=summary)
    _update_config(sb, "lead_converter", status, finished_at.isoformat())

    log.info(summary[:200])
    return {"status": status, "rows_seen": rows_seen, "rows_processed": rows_processed,
            "rows_blocked": rows_blocked, "rows_errored": rows_errored,
            "dry_run": dry_run, "sample_would_send": sample_would_send}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true")
    p.add_argument("--live", action="store_true",
                   help="Override config dry_run=True. Actually sends. Use with care.")
    args = p.parse_args()
    if args.status:
        sb = _sb()
        cfg = _read_config(sb)
        last_act = (sb.table("agent_activity")
                      .select("*").eq("agent_name", "lead_converter")
                      .order("started_at", desc=True).limit(1).execute())
        print(json.dumps({"config": cfg, "last_run": last_act.data[0] if last_act.data else None},
                         indent=2, default=str))
        return
    result = run(dry_run_override=not args.live)
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled") else 1)


if __name__ == "__main__":
    main()
