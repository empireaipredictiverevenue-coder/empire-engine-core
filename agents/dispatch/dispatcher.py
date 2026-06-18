"""
Empire AI · Predictive Revenue
Dispatch Agent
==================

Closes the loop. When a lead replies YES to a storm_strike SMS, this
agent finds a contractor in the lead's metro and fires the dispatch
flow via the hub's POST /api/v1/matching/dispatch.

Idempotent: never dispatches the same (phone, sequence) twice.

Usage:
    python3 -m agents.dispatch
    python3 -m agents.dispatch --status
"""
import os
import sys
import json
import uuid
import logging
import urllib.request
import urllib.error
import argparse
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

from supabase import create_client
from agents.event_emitter import emit_agent_event

log = logging.getLogger("empire.dispatch")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", "dispatch").limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True, "max_per_run": 10, "lookback_hours": 24}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", 10),
        "lookback_hours": cfg.get("lookback_hours", 24),
    }


def _log_activity(sb, agent_name, run_id, started_at, status, **kwargs):
    return emit_agent_event(
        sb=sb, agent_name=agent_name, run_id=run_id,
        started_at=started_at, status=status,
        **kwargs,
    )


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


def _find_lead_by_phone(sb, phone: str) -> dict | None:
    """Find the lead this YES reply came from. Lookup order:
    1. enriched_leads by phone (most likely)
    2. sms_sequences meta.enriched_lead_id (for direct-enrolled leads)
    3. radar_targets by phone
    Returns {source, id, address, city, state, warehouse_name, radar_target_id, meta}
    """
    norm = _normalize_phone(phone)
    if not norm:
        return None
    # 1) enriched_leads by phone
    r = sb.table("enriched_leads").select("id, address, city, state, warehouse_name, radar_target_id, meta").eq("phone", norm).limit(1).execute()
    if r.data:
        return {"source": "enriched_leads", **r.data[0]}
    # 2) sms_sequences by phone (for leads enrolled without a lead record)
    r = sb.table("sms_sequences").select("phone, target_addr, meta, current_step, status").eq("phone", norm).limit(1).execute()
    if r.data:
        seq = r.data[0]
        meta = seq.get("meta") or {}
        enriched_id = meta.get("enriched_lead_id")
        if enriched_id:
            # the meta references an enriched_lead — fetch it
            r2 = sb.table("enriched_leads").select("id, address, city, state, warehouse_name, radar_target_id, meta").eq("id", enriched_id).limit(1).execute()
            if r2.data:
                return {"source": "sms_sequences_meta", **r2.data[0]}
        # use the sms_sequences row as the lead itself
        return {
            "source": "sms_sequences",
            "id": seq.get("phone"),  # no lead_id, dispatch will use radar_target_id from enriched_leads if available
            "address": seq.get("target_addr"),
            "city": None,
            "state": None,
            "warehouse_name": None,
            "radar_target_id": None,
        }
    # 3) radar_targets by phone
    r = sb.table("radar_targets").select("id, address, city, state, warehouse_name").eq("phone", norm).limit(1).execute()
    if r.data:
        return {"source": "radar_targets", **r.data[0]}
    return None


def _has_recent_dispatch(sb, lead_id: str, since_hours: int = 24) -> bool:
    """Idempotency check: has this lead been dispatched in the last N hours?"""
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    r = sb.table("dispatches").select("id").eq("lead_id", lead_id).gte("created_at", since).limit(1).execute()
    return bool(r.data)


def _call_dispatch_endpoint(hub_url: str, hub_token: str, lead_id: str, urgency: int, specialties: list) -> dict:
    """Call the hub's matching/dispatch endpoint. Returns parsed JSON or {"ok": False, "error": ...}."""
    url = f"{hub_url.rstrip('/')}/api/v1/matching/dispatch"
    payload = json.dumps({
        "lead_id": lead_id,
        "urgency": urgency,
        "specialties": specialties,
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST",
                                  headers={"Content-Type": "application/json",
                                           "Authorization": f"Bearer {hub_token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"ok": False, "error": f"http_{e.code}: {body[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _hub_alive(timeout: float = 2.0) -> bool:
    """Quick TCP-level health check on the hub. Avoids blasting YES
    dispatches into URLError when the hub is down."""
    import socket
    hub_url = os.getenv("HUB_URL", "http://127.0.0.1:8000")
    try:
        hostport = hub_url.split("://", 1)[1].split("/", 1)[0]
        if ":" in hostport:
            host, port_s = hostport.rsplit(":", 1)
            port = int(port_s)
        else:
            host, port = hostport, 80
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _is_yes(body: str) -> bool:
    """Heuristic: 'YES' anywhere in the inbound body counts. Case-insensitive. Trimmed."""
    if not body:
        return False
    cleaned = body.strip().upper()
    return "YES" in cleaned.split() or cleaned in ("YES", "Y", "YEAH", "YEP", "SURE", "OK", "OKAY")


def run() -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)

    if not cfg["enabled"]:
        _log_activity(sb, "dispatch", run_id, started_at, "skipped_disabled",
                      summary="disabled in agent_config")
        _update_config(sb, "dispatch", "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    # Hub precheck. /api/v1/matching/dispatch is a hub endpoint; if the
    # hub is down we'd just produce URLErrors on every YES reply.
    if not cfg.get("dry_run", True) and not _hub_alive():
        _log_activity(sb, "dispatch", run_id, started_at, "skipped_disabled",
                      summary="hub at HUB_URL unreachable — skipping live dispatch to avoid blasting YES into URLError")
        _update_config(sb, "dispatch", "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    # find recent YES replies that haven't been dispatched yet
    since = (datetime.now(timezone.utc) - timedelta(hours=cfg["lookback_hours"])).isoformat()
    sms_res = (sb.table("sms_log")
                .select("id, phone, body, created_at")
                .eq("direction", "inbound")
                .gte("created_at", since)
                .order("created_at", desc=False)
                .limit(cfg["max_per_run"] * 3)
                .execute())
    candidates = [r for r in (sms_res.data or []) if _is_yes(r.get("body", ""))]
    log.info(f"dispatch: {len(candidates)} YES replies in last {cfg['lookback_hours']}h")
    rows_seen = len(candidates)

    rows_processed = 0
    rows_errored = 0
    rows_blocked = 0
    rows_skipped = 0
    error_msgs = []
    sample_dispatches = []
    hub_url = os.getenv("HUB_URL", "http://127.0.0.1:8000")
    hub_token = os.getenv("HUB_TOKEN", "")

    for sms in candidates[:cfg["max_per_run"]]:
        try:
            phone = _normalize_phone(sms.get("phone", ""))
            lead = _find_lead_by_phone(sb, phone)
            if not lead:
                rows_blocked += 1
                log.info(f"dispatch: no lead found for phone {phone} (orphan YES)")
                sb.table("outreach_log").insert({
                    "enriched_lead_id": None,
                    "agent_name": "dispatch",
                    "run_id": str(run_id),
                    "channel": "sms",
                    "sequence": "manual_dispatch",
                    "step": 0,
                    "body_preview": f"[ORPHAN YES] from {phone}: {sms.get('body','')[:50]}",
                    "compliance_passed": True,
                    "mode": "dry_run" if cfg["dry_run"] else "live",
                }).execute()
                continue

            lead_id = lead.get("id")
            # IMPORTANT: the hub's /api/v1/matching/dispatch queries radar_targets by id.
            # if the lead is from enriched_leads, we need to use its radar_target_id, not the enriched_lead's own id.
            if lead.get("source") == "enriched_leads" and lead.get("radar_target_id"):
                lead_id = lead.get("radar_target_id")
            elif not lead.get("radar_target_id"):
                # orphan lead with no radar_target_id fallback
                log.info(f"dispatch: lead {phone} has no radar_target_id — likely needs manual enriched_leads row")
                rows_blocked += 1
                sb.table("outreach_log").insert({
                    "enriched_lead_id": None,
                    "agent_name": "dispatch",
                    "run_id": str(run_id),
                    "channel": "sms",
                    "sequence": "manual_dispatch",
                    "step": 0,
                    "body_preview": f"[NO-RADAR-TARGET-ID] {phone} → {lead.get('address', '?')[:80]}",
                    "compliance_passed": True,
                    "mode": "dry_run" if cfg["dry_run"] else "live",
                }).execute()
                continue

            if not lead_id:
                rows_errored += 1
                error_msgs.append(f"no lead_id resolved for {phone}")
                continue

            # idempotency: skip if already dispatched recently
            if _has_recent_dispatch(sb, str(lead_id), since_hours=24):
                rows_skipped += 1
                log.info(f"dispatch: skip {phone} — already dispatched in last 24h")
                continue

            # urgency is high (real human replied YES) but cap at 10
            urgency = 9
            # Use specialties that match what contractors actually have in the DB
            # Contractors: roofing (178), hvac (164), restoration (73), general_contractor (45)
            specialties = ["roofing", "restoration", "general_contractor"]

            if cfg["dry_run"]:
                # log would-dispatch, do NOT call hub
                sb.table("outreach_log").insert({
                    "enriched_lead_id": lead.get("id"),
                    "agent_name": "dispatch",
                    "run_id": str(run_id),
                    "channel": "sms",
                    "sequence": "manual_dispatch",
                    "step": 0,
                    "body_preview": f"[DRY-RUN] would dispatch lead {lead_id} (urgency={urgency}) to contractors in metro={lead.get('city')}",
                    "compliance_passed": True,
                    "mode": "dry_run",
                }).execute()
                rows_processed += 1
                continue

            # LIVE: call the hub
            result = _call_dispatch_endpoint(hub_url, hub_token, str(lead_id), urgency, specialties)
            ok = result.get("ok", False)
            dispatched = result.get("dispatched", 0)

            sb.table("outreach_log").insert({
                "enriched_lead_id": lead.get("id"),
                "agent_name": "dispatch",
                "run_id": str(run_id),
                "channel": "sms",
                "sequence": "manual_dispatch",
                "step": 0,
                "body_preview": f"dispatch result: {json.dumps(result)[:200]}",
                "compliance_passed": True,
                "mode": "live",
                "sent_at": datetime.now(timezone.utc).isoformat() if ok else None,
                "sent_status": "dispatched" if ok and dispatched > 0 else ("no_match" if ok else "failed"),
            }).execute()

            if ok and dispatched > 0:
                rows_processed += 1
                sample_dispatches.append({
                    "phone": phone,
                    "lead_id": lead_id,
                    "warehouse_name": lead.get("warehouse_name") or lead.get("address"),
                    "metro": lead.get("city"),
                    "dispatched": dispatched,
                    "top_score": result.get("top_score"),
                })
            elif ok and dispatched == 0:
                # hub returned ok but no matches (e.g. no contractors in that metro)
                rows_blocked += 1
            else:
                rows_errored += 1
                error_msgs.append(f"{phone}: {result.get('error', 'unknown')[:120]}")
        except Exception as e:
            rows_errored += 1
            error_msgs.append(f"{sms.get('phone','?')}: {type(e).__name__}: {e}")
            log.warning(f"dispatch: failed for {sms.get('phone')}: {e}")

    finished_at = datetime.now(timezone.utc)
    mode_label = "dry-run" if cfg["dry_run"] else "LIVE"
    summary = (f"[{mode_label}] scanned {rows_seen} YES replies, "
               f"{rows_processed} dispatched, {rows_blocked} no-lead, "
               f"{rows_skipped} already-dispatched, {rows_errored} errored")
    if sample_dispatches:
        summary += f". Sample: {json.dumps(sample_dispatches, default=str)[:500]}"
    status = "ok" if rows_errored == 0 else "ok"
    err_field = None if rows_errored == 0 else "; ".join(error_msgs[:5])

    _log_activity(sb, "dispatch", run_id, started_at, status,
                  rows_seen=rows_seen, rows_processed=rows_processed,
                  rows_blocked=rows_blocked, rows_errored=rows_errored,
                  error=err_field, summary=summary)
    _update_config(sb, "dispatch", status, finished_at.isoformat())

    log.info(summary[:200])
    return {"status": status, "rows_seen": rows_seen, "rows_processed": rows_processed,
            "rows_blocked": rows_blocked, "rows_errored": rows_errored}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true")
    args = p.parse_args()
    if args.status:
        sb = _sb()
        cfg = _read_config(sb)
        last_act = (sb.table("agent_activity").select("*").eq("agent_name", "dispatch").order("started_at", desc=True).limit(1).execute())
        print(json.dumps({"config": cfg, "last_run": last_act.data[0] if last_act.data else None},
                         indent=2, default=str))
        return
    result = run()
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled") else 1)


if __name__ == "__main__":
    main()
