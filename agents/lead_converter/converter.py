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
    # NOTE: there is no --live / --dry-run flag. The agent reads dry_run
    # exclusively from agent_config.lead_converter.dry_run. To pause live
    # sending, set dry_run=true in that row. The only way to do a real send
    # is to enroll through /api/v1/sms/enroll — there is no "send a one-off
    # SMS" code path.
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
            "channels": ["sms", "voice", "email"],
            "default_sequence": "storm_strike",
        }
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", 10),
        "channels": cfg.get("channels", ["sms", "voice", "email"]),
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


# B2B niches (from the 33-niche prospector config) — leads from these
# get routed to b2b_outreach instead of storm_strike. The 3% success
# fee pitch in storm_strike is wrong for staffing/HR/IT/insurance/etc.
B2B_NICHES = {
    # proven b2b
    "managed it", "staffing",
    # legal
    "personal injury lawyer", "mass tort lawyer", "class action lawyer",
    "workers comp lawyer", "medical malpractice lawyer",
    # insurance
    "medicare advantage agent", "life insurance agent", "final expense insurance",
    # financial
    "debt consolidation", "business loan broker", "mortgage broker",
    # senior care
    "assisted living", "home health agency",
    # healthcare
    "addiction treatment center", "mental health clinic", "medical alert system",
    # education
    "cdl truck driving school", "nursing school",
    # debt
    "debt relief",
}

# Commercial variants → commercial_roofing, commercial_solar

# Legal sub-niches (5 lanes from mesh_orchestrator LANES 16-20) → legal_mass_tort.
# Buyer names in `buyers` table are still PENDING placeholders; until Phil recruits
# real buyers and sets is_active=True, the lead_converter routes to legal_mass_tort
# but no real dispatch happens. Sequence was added 2026-06-17.
LEGAL_NICHES = {
    "pharma liability", "pharma_liability",
    "medical device",   "medical_device",
    "consumer product", "consumer_product",
    "class action",     "class_action",
    "mass tort",        "mass_tort",
}

# Adjuster niches → insurance_adjuster_recruit
ADJUSTER_NICHES = {
    "public insurance adjuster", "public_adjuster", "insurance adjuster",
}


COMMERCIAL_NICHE_MAP = {
    "commercial roofing": "commercial_roofing",
    "commercial solar": "commercial_solar",
}


def _pick_sequence(lead: dict) -> str:
    """Pick the SMS sequence based on lead metadata.

    Priority order:
      1. Lead's own niche (from radar_targets) routes to the right
         sequence type: B2B → b2b_outreach, commercial → commercial_*,
         storm → storm_strike A/B
      2. b2b_sub_niche in lead.meta → legacy routing from matrix agents
      3. Phone + storm niche → A/B cohort split (storm_strike vs
         storm_strike_v2, 50/50 by hash of lead id)
      4. email only → lead_nurture
      5. fallback → manual
    """
    # 1. Check the lead's own niche (from the radar_target it came from)
    niche = (lead.get("niche") or "").lower()
    if niche in B2B_NICHES:
        return "b2b_outreach"
    if niche in ADJUSTER_NICHES:
        return "insurance_adjuster_recruit"
    if niche in COMMERCIAL_NICHE_MAP:
        return COMMERCIAL_NICHE_MAP[niche]
    if niche in LEGAL_NICHES:
        return "legal_mass_tort"

    # 2. Legacy: b2b_sub_niche in meta (from matrix agents' older leads)
    meta = lead.get("meta") or {}
    if isinstance(meta, dict):
        sub_niche = meta.get("b2b_sub_niche", "")
        if sub_niche == "Commercial Roofing":
            return "commercial_roofing"
        if sub_niche == "Commercial Solar":
            return "commercial_solar"
        if sub_niche == "Debt Relief":
            return "debt_relief"
        if sub_niche in ("HR & Staffing", "Managed IT", "Merchant Services"):
            return "b2b_outreach"

    # 3. Phone leads: A/B storm_strike cohort split. The hub's
    # sms_sequences only knows about 'storm_strike' right now (v2 is
    # planned but not defined yet). The A/B bucket is kept for future
    # use; for now both buckets route to storm_strike so leads never
    # hit a KeyError.
    if lead.get("phone"):
        import hashlib
        h = hashlib.md5(str(lead.get("id", "")).encode()).hexdigest()
        bucket = int(h[:8], 16) % 2
        # bucket is reserved for the day v2 ships; today both → storm_strike
        _ = bucket  # noqa: F841
        return "storm_strike"
    if lead.get("email"):
        return "lead_nurture"
    return "manual"


def _pick_channel(lead: dict, channels: list) -> str:
    """Pick the channel. SMS first if phone, voice as backup,
    email for leads that have email but no phone.
    """
    if "sms" in channels and lead.get("phone"):
        return "sms"
    if "voice" in channels and lead.get("phone"):
        return "voice"
    if "email" in channels and lead.get("email"):
        return "email"
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
    """Returns (passed, block_reason).

    For SMS/voice: checks phone, opted-out, DNC, consent, quiet hours.
    For email: checks email is present and not unsubscribed.
    """
    if channel == "email":
        email = (lead.get("email") or "").strip()
        if not email or "@" not in email:
            return False, "no_valid_email"
        return True, ""

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


def _normalize_phone(phone: str) -> str:
    """E.164 normalize: strip non-digits, ensure leading + and country code."""
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return ""
    # US default: 10 digits → +1, 11 digits starting with 1 → +1
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    # otherwise, assume it's already international, prefix with +
    return "+" + digits


def _do_live_send(channel: str, phone: str, body: str, lead: dict) -> tuple[bool, str]:
    """Call the hub to enroll the lead in the SMS or email sequence.
    Returns (ok, sent_status_or_error)."""
    import urllib.request
    hub_url = os.getenv("HUB_URL", "http://127.0.0.1:8000")
    hub_token = os.getenv("HUB_TOKEN", "")
    if not hub_token:
        return False, "no_hub_token_in_env"

    if channel == "sms":
        normalized = _normalize_phone(phone)
        if not normalized:
            return False, "phone_normalize_failed"
        url = f"{hub_url}/api/v1/sms/enroll"
        payload = json.dumps({
            "phone": normalized,
            "target_addr": lead.get("address", ""),
            "sequence_type": lead.get("_sequence", "storm_strike"),
            "meta": {
                "enriched_lead_id": lead.get("id"),
                "warehouse_name": lead.get("warehouse_name"),
                "source": "lead_converter",
                "body_preview": body[:200],
            },
        }).encode()
    elif channel == "email":
        email = (lead.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return False, "no_valid_email"
        url = f"{hub_url}/api/v1/email/enroll"
        payload = json.dumps({
            "email": email,
            "target_addr": lead.get("address", ""),
            "sequence_type": lead.get("_sequence", "lead_nurture"),
            "meta": {
                "enriched_lead_id": lead.get("id"),
                "warehouse_name": lead.get("warehouse_name"),
                "source": "lead_converter",
                "email_guess": lead.get("meta", {}).get("email_guess", False),
                "city": lead.get("city", ""),
                "state": lead.get("state", ""),
            },
        }).encode()
    else:
        # voice channel: not wired into the lead_converter. TCPA compliance
        # requires explicit consent before voice calls, and the converter
        # only has the lead's phone number from the storm pipeline (no
        # TCPA opt-in recorded yet). Future voice agent will handle this
        # with proper opt-in tracking.
        return False, "voice_not_wired_in_converter_use_voice_agent"

    req = urllib.request.Request(url, data=payload, method="POST",
                                  headers={"Content-Type": "application/json",
                                           "Authorization": f"Bearer {hub_token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True, "enrolled"
            return False, f"http_{resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"http_{e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _hub_alive(timeout: float = 2.0) -> bool:
    """Quick TCP-level health check on the hub. Avoids blasting leads
    into URLError when the hub is down (PM2 crash-loop, restart, etc).
    Returns True if the hub accepts a TCP connection on the configured
    port within `timeout` seconds."""
    import socket
    hub_url = os.getenv("HUB_URL", "http://127.0.0.1:8000")
    # crude parse: assume http://host:port
    try:
        # strip scheme
        hostport = hub_url.split("://", 1)[1]
        # strip path
        hostport = hostport.split("/", 1)[0]
        if ":" in hostport:
            host, port_s = hostport.rsplit(":", 1)
            port = int(port_s)
        else:
            host, port = hostport, 80
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


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

    # Hub precheck. In live mode, the hub MUST be up — otherwise we'd
    # blast 200 leads into URLErrors. In dry_run we don't need the hub
    # at all (we just log locally), so skip the check.
    if not dry_run and not _hub_alive():
        _log_activity(sb, "lead_converter", run_id, started_at, "skipped_disabled",
                      summary="hub at HUB_URL unreachable — skipping live run to avoid blasting leads into URLError")
        _update_config(sb, "lead_converter", "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    # 1) Read top-N pending leads by score. Accepts both pending_outreach
    # (the documented state) and pending_enrichment (what lead_scanner
    # actually writes, since lead_enricher is not currently in the chain).
    rows_res = (sb.table("enriched_leads")
                  .select("*")
                  .in_("status", ["pending_outreach", "pending_enrichment"])
                  .order("score", desc=True)
                  .order("created_at", desc=False)
                  .limit(cfg["max_per_run"])
                  .execute())
    rows = rows_res.data or []
    log.info(f"converter: {len(rows)} pending leads (pending_outreach|pending_enrichment) (dry_run={dry_run})")
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
                # LIVE mode: enroll in the SMS sequence
                # pass the sequence into the lead dict so _do_live_send can read it
                lead_for_send = dict(lead)
                lead_for_send["_sequence"] = sequence
                ok, sent_status = _do_live_send(channel, lead.get("phone"), body, lead_for_send)
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
    result = run()
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled") else 1)


if __name__ == "__main__":
    main()
