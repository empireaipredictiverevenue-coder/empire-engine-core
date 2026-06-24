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
from agents.event_emitter import emit_agent_event

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
        return {"enabled": True, "dry_run": True, "max_per_run": 25,
                "voice_dry_run": True, "voice_max_per_run": 3,
                "voice_for_named_only": True, "metros": []}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", 25),
        # Voice lane config (added 2026-06-16)
        "voice_dry_run": cfg.get("voice_dry_run", True),
        "voice_max_per_run": cfg.get("voice_max_per_run", 3),
        "voice_for_named_only": cfg.get("voice_for_named_only", True),
        "metros": cfg.get("metros", []),
    }


def _has_real_name(contractor: dict) -> bool:
    """True if contractor.meta.contact_name is a real human name
    (i.e. decision_makers has enriched this row)."""
    meta = contractor.get("meta") or {}
    cn = (meta.get("contact_name") or "").strip()
    if not cn:
        return False
    # Cheap stop-list to filter the worst false-positives from
    # decision_makers' regex. Same logic as bots/decision_makers.py.
    parts = cn.lower().split()
    if len(parts) != 2:
        return False
    for p in parts:
        if len(p) < 3 or p in {
            "wants", "wanted", "wanting", "helps", "helped", "helping",
            "starts", "started", "starting", "stops", "stopped",
            "ends", "ended", "ending", "sends", "sent", "sending",
            "calls", "called", "calling", "meets", "met", "meeting",
            "joins", "joined", "joining", "feels", "felt", "feeling",
            "becomes", "became", "becoming", "remains", "remained",
            "appears", "appeared", "appearing", "happens", "happened",
            "begins", "began", "begun", "beginning", "continues", "continued",
            "decides", "decided", "deciding", "expects", "expected",
            "includes", "included", "including", "requires", "required",
        }:
            return False
        if not any(c in "aeiou" for c in p):
            return False
    return True


def _has_active_call(sb, phone: str) -> bool:
    """True if this phone already has a live voice outreach row in the
    last 7 days. Prevents re-calling the same contractor every 4h."""
    from datetime import timedelta
    norm = _normalize_phone(phone)
    if not norm:
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    r = (sb.table("outreach_log")
           .select("id")
           .eq("phone", None)  # outreach_log has no phone col; check via meta
           .eq("agent_name", "contractor_recruit_call")
           .eq("sent_status", "placed")
           .gte("sent_at", cutoff)
           .execute())
    # outreach_log lacks phone col directly; instead check by meta.contractor_id
    cid = ""
    # we have no `phone` in outreach_log; use a different approach below
    return False


def _has_active_call_v2(sb, contractor_id: str) -> bool:
    """Check via meta.contractor_id whether this contractor already
    received a placed voice call in the last 7 days."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    # meta is jsonb, so use the @> containment operator
    r = (sb.table("outreach_log")
           .select("id,meta")
           .eq("agent_name", "contractor_recruit_call")
           .eq("sent_status", "placed")
           .gte("sent_at", cutoff)
           .execute())
    for row in (r.data or []):
        m = row.get("meta") or {}
        if m.get("contractor_id") == contractor_id:
            return True
    return False


def _place_voice_call(contractor: dict) -> dict:
    """Place a real voice call via empire_outbound_dialer.
    Returns the dialer's result dict."""
    try:
        from empire_outbound_dialer import initiate_contractor_recruit_call
    except Exception as e:
        return {"ok": False, "error": f"dialer_import_failed: {e}"}
    try:
        return initiate_contractor_recruit_call(contractor)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _render_voice_preview(contractor: dict) -> str:
    """Render the contractor_recruit voice body for the outreach_log
    body_preview. Reused by dry-run mode."""
    try:
        from agents.outreach.voice_scripts import get_script
        meta = contractor.get("meta") or {}
        first = (meta.get("contact_name") or "").split()[0] or "there"
        metro = contractor.get("metro") or "your area"
        s = get_script("contractor_recruit")
        intro = s["intro"].format(first_name=first, metro=metro)
        main  = s["main"].format(first_name=first, metro=metro)
        return f"{intro} ... {main}"[:280]
    except Exception as e:
        return f"[voice-render-failed: {e}]"


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
    # Pull named contact (if any) from contractor meta. decision_makers
    # writes contact_name/contact_title into contractors.meta when a
    # public-website scrape succeeds.
    c_meta = contractor.get("meta") or {}
    contact_name = c_meta.get("contact_name") or ""
    contact_title = c_meta.get("contact_title") or ""
    payload = json.dumps({
        "phone": phone,
        "target_addr": f"{contractor.get('metro','')} ({contractor.get('name','')})",
        "sequence_type": SEQUENCE,
        "meta": {
            "contractor_id": contractor.get("id"),
            "contractor_name": contractor.get("name"),
            "metro": contractor.get("metro"),
            "source": "contractor_outreach_agent",
            "contact_name": contact_name,
            "contact_title": contact_title,
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

    # 2) Hub precheck: in live mode, skip run if hub is unreachable
    # to avoid blasting 100 contractors into URLErrors
    if not cfg["dry_run"]:
        import socket as _socket
        hub_url = os.getenv("HUB_URL", "http://127.0.0.1:8001")
        hub_alive = False
        try:
            hostport = hub_url.split("://", 1)[1].split("/", 1)[0]
            host, port_s = hostport.rsplit(":", 1) if ":" in hostport else (hostport, "80")
            with _socket.create_connection((host, int(port_s)), timeout=2.0):
                hub_alive = True
        except Exception:
            pass
        if not hub_alive:
            _log_activity(sb, "contractor_outreach", run_id, started_at, "skipped_disabled",
                          rows_seen=0, rows_processed=0, rows_errored=0,
                          summary="hub at HUB_URL unreachable — skipping run to avoid blasting URLErrors")
            _update_config(sb, "contractor_outreach", "skipped_disabled", datetime.now(timezone.utc).isoformat())
            log.info("[contractor_outreach] hub unreachable — skipped")
            return {"status": "skipped_disabled", "rows_processed": 0}

    # 3) Filter to those without an active recruit sequence AND have a phone
    to_enroll = []
    for c in candidates:
        phone = _normalize_phone(c.get("phone", ""))
        if not phone:
            continue
        if _has_active_recruit_sequence(sb, phone):
            continue
        to_enroll.append(c)

    # 2b) Voice lane: pre-process the named contractors first. They get
    # a voice call (or dry-render) before the SMS enroll. Voice runs in
    # the same run but with a separate cap (voice_max_per_run).
    rows_voice_attempted = 0
    rows_voice_placed   = 0
    rows_voice_dry      = 0
    rows_voice_blocked  = 0
    rows_voice_errored  = 0
    rows_voice_skipped  = 0  # already called in last 7d
    voice_skipped_ids   = set()
    voice_sample        = []
    voice_errors        = []
    if cfg.get("voice_for_named_only", True) and cfg.get("voice_max_per_run", 0) > 0:
        voice_cap = cfg["voice_max_per_run"]
        # Pick the named contractors from to_enroll (skip those already called)
        voice_candidates = [c for c in to_enroll if _has_real_name(c)]
        log.info(f"contractor_outreach[voice]: {len(voice_candidates)} named candidates (cap {voice_cap})")
        for c in voice_candidates:
            if rows_voice_attempted >= voice_cap:
                break
            cid = c.get("id")
            try:
                if _has_active_call_v2(sb, cid):
                    rows_voice_skipped += 1
                    voice_skipped_ids.add(cid)
                    continue
            except Exception:
                pass
            rows_voice_attempted += 1
            phone = _normalize_phone(c.get("phone", ""))
            meta = c.get("meta") or {}
            contact_name = meta.get("contact_name") or ""
            if cfg.get("voice_dry_run", True):
                # Dry-render only: log what we'd say, no call
                preview = _render_voice_preview(c)
                try:
                    sb.table("outreach_log").insert({
                        "enriched_lead_id": None,
                        "agent_name":       "contractor_recruit_call",
                        "run_id":           str(uuid.uuid4()),
                        "channel":          "voice",
                        "sequence":         "contractor_recruit",
                        "step":             0,
                        "body_preview":     f"[DRY-RUN voice] {preview}"[:280],
                        "compliance_passed": True,
                        "mode":             "dry_run",
                        "sent_at":          datetime.now(timezone.utc).isoformat(),
                        "sent_status":      "dry_render",
                        "meta":             {"contractor_id": cid, "contact_name": contact_name, "phone": phone},
                    }).execute()
                    rows_voice_dry += 1
                    if len(voice_sample) < 3:
                        voice_sample.append({
                            "contractor": c.get("name"),
                            "phone": phone,
                            "mode": "dry_run",
                            "first_name": (contact_name.split() or [""])[0],
                        })
                except Exception as e:
                    rows_voice_errored += 1
                    voice_errors.append(f"{c.get('name')}: {type(e).__name__}: {e}")
            else:
                # Live: place a real call
                res = _place_voice_call(c)
                if res.get("blocked"):
                    rows_voice_blocked += 1
                    voice_errors.append(f"{c.get('name')}: BLOCKED ({res.get('rule')}): {res.get('reason')}")
                elif res.get("ok"):
                    rows_voice_placed += 1
                    if len(voice_sample) < 3:
                        voice_sample.append({
                            "contractor": c.get("name"),
                            "phone": phone,
                            "mode": "live",
                            "first_name": (contact_name.split() or [""])[0],
                            "vonage_uuid": res.get("uuid"),
                        })
                else:
                    rows_voice_errored += 1
                    voice_errors.append(f"{c.get('name')}: {res.get('error','?')[:120]}")
        # Exclude voice'd contractors from the SMS path so we don't
        # double-touch them in the same run.
        to_enroll = [c for c in to_enroll if c.get("id") not in voice_skipped_ids]
    to_enroll = to_enroll[:cfg["max_per_run"]]
    log.info(f"contractor_outreach: {len(to_enroll)} need recruitment (no active sequence)")

    # 3) Enroll each
    rows_processed = 0
    rows_errored = 0
    rows_skipped = 0
    error_msgs = []
    sample_enrolls = []
    hub_url = os.getenv("HUB_URL", "http://127.0.0.1:8001")
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
    # Voice lane summary (added 2026-06-16)
    if cfg.get("voice_max_per_run", 0) > 0:
        voice_mode = "dry-run" if cfg.get("voice_dry_run", True) else "LIVE"
        summary += (f" | [voice {voice_mode}] attempted={rows_voice_attempted} "
                    f"placed={rows_voice_placed} dry={rows_voice_dry} "
                    f"blocked={rows_voice_blocked} skipped={rows_voice_skipped} "
                    f"errored={rows_voice_errored}")
        if voice_sample:
            summary += f" voice_sample={json.dumps(voice_sample, default=str)[:300]}"
        if voice_errors:
            summary += f" voice_errors={json.dumps(voice_errors[:3], default=str)[:300]}"
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
