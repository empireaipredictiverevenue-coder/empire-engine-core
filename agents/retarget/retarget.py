"""
Empire AI · Predictive Revenue
Retarget Agent
================

Walks `sms_sequences` rows in `replied` state and re-enrolls soft-replies
in a follow-up sequence. Conservative default: once per source sequence,
last 30d only, no STOP, no already-converted.

What counts as a "soft reply":
  - The sequence status moved to `replied` (someone replied)
  - The last inbound sms in sms_log for that phone is NOT a STOP / YES
  - The phone is not in sms_opt_outs
  - There is no active sms_sequence for that phone right now
  - We have not already retargeted this source sequence (tracked in meta)

A "source sequence" is the original sequence the reply came from.
A "retarget" creates a NEW sms_sequences row, NOT a modification
of the source. The source row stays in `replied` for audit.

Usage:
    python3 -m agents.retarget           # one run, exits
    python3 -m agents.retarget --dry-run # score and report, don't write
    python3 -m agents.retarget --status  # last run + stats
"""
import os
import sys
import json
import uuid
import logging
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter

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

log = logging.getLogger("empire.retarget")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "retarget"

# Conservative defaults — change in agent_config.retarget_window_days if you want different
DEFAULT_WINDOW_DAYS = 30

# Phrases that mean "do not retarget". Match is case-insensitive substring.
STOP_PHRASES = ("stop", "unsubscribe", "remove me", "opt out", "quit", "cancel")
YES_PHRASES = ("yes", "y", "interested", "yep", "yeah", "sure", "ok", "okay")

# DNC / opt-out tables
OPT_OUT_TABLES = ("sms_opt_outs", "do_not_contact")


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True, "window_days": DEFAULT_WINDOW_DAYS}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "window_days": cfg.get("window_days", DEFAULT_WINDOW_DAYS),
    }


def _log_activity(sb, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_blocked=0, rows_errored=0,
                  error=None, summary=None):
    return emit_agent_event(
        sb=sb, agent_name=AGENT_NAME, run_id=run_id,
        started_at=started_at, status=status,
        rows_seen=rows_seen, rows_processed=rows_processed,
        rows_blocked=rows_blocked, rows_errored=rows_errored,
        error=error, summary=summary,
    )


def _update_config(sb, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", AGENT_NAME).execute()


def _normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = "".join(c for c in str(phone) if c.isdigit())
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if str(phone).startswith("+") and len(digits) >= 10:
        return "+" + digits
    return ""


def _is_stop_reply(body: str) -> bool:
    if not body:
        return False
    b = body.strip().lower()
    return any(p == b or b.startswith(p + " ") or b == p for p in STOP_PHRASES)


def _is_yes_reply(body: str) -> bool:
    if not body:
        return False
    b = body.strip().lower()
    return b in YES_PHRASES


def _hub_url() -> str:
    return os.getenv("HUB_URL", "http://127.0.0.1:8001").rstrip("/")


def _hub_token() -> str:
    return os.getenv("HUB_TOKEN", "") or os.getenv("HUB_API_KEY", "")


def _reactivate_source(source: dict) -> dict:
    """
    Reactivate the source replied sequence for re-engagement.
    (We can't INSERT a new sms_sequences row — the phone column has a UNIQUE
    constraint. So we flip the existing replied row back to active and reset
    its step + next_send_at, then mark it retarget_done so we never loop.)

    Updates the source row:
      - status         = "active"
      - current_step   = 0
      - next_send_at   = now+30s
      - meta.retarget_count += 1
      - meta.retarget_at    = now
      - meta.retarget_done  = True (idempotent: never retarget this row again)

    Returns: {"ok": bool, "sequence_id": str|None, "error"?: str}
    """
    sb = _sb()
    try:
        meta = source.get("meta") or {}
        retarget_count = int(meta.get("retarget_count", 0)) + 1
        meta["retarget_count"] = retarget_count
        meta["retarget_at"] = datetime.now(timezone.utc).isoformat()
        meta["retarget_done"] = True

        sb.table("sms_sequences").update({
            "status":       "active",
            "current_step": 0,
            "next_send_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "meta":         meta,
        }).eq("id", source["id"]).execute()
        return {"ok": True, "sequence_id": source["id"], "retarget_count": retarget_count}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _find_soft_replies(sb, window_days: int) -> list:
    """Find replied sequences in the last N days that look retargetable."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    r = sb.table("sms_sequences").select("id,phone,sequence_type,status,target_addr,created_at,meta,replies_count").eq("status", "replied").gte("created_at", cutoff).limit(500).execute()
    out = []
    for row in r.data:
        meta = row.get("meta") or {}
        # Skip if this source was already retargeted
        if meta.get("retarget_done") or meta.get("retarget_of_id"):
            continue
        out.append(row)
    return out


def _is_on_dnc(sb, phone: str) -> bool:
    """Check opt-out tables. Returns True if the phone should never be re-enrolled."""
    for t in OPT_OUT_TABLES:
        try:
            r = sb.table(t).select("id").eq("phone", phone).limit(1).execute()
            if r.data:
                return True
        except Exception:
            # table may not exist; ignore
            pass
    return False


def _has_active_sequence(sb, phone: str) -> bool:
    r = sb.table("sms_sequences").select("id").eq("phone", phone).eq("status", "active").limit(1).execute()
    return bool(r.data)


def _has_failed_send_history(sb, phone: str, threshold: int = 3) -> bool:
    """
    A phone with failed_send_count >= threshold is "broken" — Vonage is
    returning 422 / non-deliverable, so re-engaging just wastes an SMS
    and trips the sms_qc gate_regression check.
    """
    r = sb.table("sms_sequences").select("meta").eq("phone", phone).limit(1).execute()
    if not r.data:
        return False
    meta = r.data[0].get("meta") or {}
    fc = int(meta.get("failed_send_count", 0))
    return fc >= threshold


def _get_last_inbound_body(sb, phone: str) -> str:
    r = sb.table("sms_log").select("body").eq("phone", phone).eq("direction", "inbound").order("created_at", desc=True).limit(1).execute()
    if r.data:
        return r.data[0].get("body") or ""
    return ""


def _mark_retarget_done(sb, source_id: str) -> None:
    """Mark the source sequence as already-retargeted so we never loop."""
    try:
        # fetch existing meta
        r = sb.table("sms_sequences").select("meta").eq("id", source_id).limit(1).execute()
        if r.data:
            meta = r.data[0].get("meta") or {}
            meta["retarget_done"] = True
            meta["retarget_cooldown_until"] = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            meta["retarget_at"] = datetime.now(timezone.utc).isoformat()
            sb.table("sms_sequences").update({"meta": meta}).eq("id", source_id).execute()
    except Exception as e:
        log.warning(f"_mark_retarget_done failed for {source_id}: {e}")


def run_once(dry_run_override=None) -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)
    dry_run = cfg["dry_run"] if dry_run_override is None else dry_run_override
    window_days = cfg["window_days"]

    if not cfg["enabled"]:
        msg = "agent disabled in agent_config — skipping"
        log.info(msg)
        _log_activity(sb, run_id, started_at, "skipped", summary=msg)
        return {"status": "skipped", "reason": msg}

    candidates = _find_soft_replies(sb, window_days)
    rows_seen = len(candidates)
    rows_processed = 0
    rows_blocked = 0
    rows_errored = 0
    error_msgs = []
    block_reasons = Counter()
    enroll_results = []

    for src in candidates:
        phone = _normalize_phone(src.get("phone"))
        if not phone:
            rows_blocked += 1
            block_reasons["bad_phone"] += 1
            continue
        if _is_on_dnc(sb, phone):
            rows_blocked += 1
            block_reasons["on_dnc"] += 1
            continue
        if _has_active_sequence(sb, phone):
            rows_blocked += 1
            block_reasons["already_active"] += 1
            continue
        if _has_failed_send_history(sb, phone):
            rows_blocked += 1
            block_reasons["failed_send_history"] += 1
            _mark_retarget_done(sb, src["id"])  # never retry broken phones
            continue
        last_in = _get_last_inbound_body(sb, phone)
        if _is_stop_reply(last_in):
            rows_blocked += 1
            block_reasons["stop_reply"] += 1
            _mark_retarget_done(sb, src["id"])  # never retry
            continue
        if _is_yes_reply(last_in):
            rows_blocked += 1
            block_reasons["yes_reply"] += 1
            _mark_retarget_done(sb, src["id"])  # already-converted, no need
            continue

        if dry_run:
            rows_processed += 1
            enroll_results.append({
                "source_id": src["id"],
                "phone": phone,
                "sequence_type": src.get("sequence_type"),
                "would_reactivate": True,
            })
            continue

        result = _reactivate_source(src)
        if result.get("ok"):
            rows_processed += 1
            enroll_results.append({
                "source_id": src["id"],
                "phone": phone,
                "sequence_type": src.get("sequence_type"),
                "reactivated": True,
                "retarget_count": result.get("retarget_count"),
            })
        else:
            rows_errored += 1
            err = (result.get("error") or "?")[:200]
            error_msgs.append(f"{phone[:8]}: {err}")

    summary_parts = [
        f"[{'DRY-RUN' if dry_run else 'LIVE'}] window={window_days}d",
        f"seen={rows_seen}",
        f"enrolled={rows_processed}",
        f"blocked={rows_blocked}",
        f"errored={rows_errored}",
    ]
    if block_reasons:
        br = ", ".join(f"{k}={v}" for k, v in block_reasons.most_common())
        summary_parts.append(f"block_reasons=[{br}]")
    summary = " · ".join(summary_parts)
    log.info(summary)

    final_status = "ok" if rows_errored == 0 else "ok_with_errors"
    err_field = None if rows_errored == 0 else "; ".join(error_msgs[:5])
    finished_at = _log_activity(
        sb, run_id, started_at, final_status,
        rows_seen=rows_seen,
        rows_processed=rows_processed,
        rows_blocked=rows_blocked,
        rows_errored=rows_errored,
        error=err_field,
        summary=summary[:500],
    )
    _update_config(sb, final_status, finished_at)
    return {
        "status": final_status,
        "rows_seen": rows_seen,
        "rows_processed": rows_processed,
        "rows_blocked": rows_blocked,
        "rows_errored": rows_errored,
        "block_reasons": dict(block_reasons),
        "enroll_results": enroll_results[:20],
    }


def show_status():
    sb = _sb()
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if r.data:
        row = r.data[0]
        cfg = row.get("config_json") or {}
        print(f"agent:           {AGENT_NAME}")
        print(f"enabled:         {row.get('enabled')}")
        print(f"dry_run:         {row.get('dry_run')}")
        print(f"window_days:     {cfg.get('window_days', DEFAULT_WINDOW_DAYS)}")
        print(f"last_run_at:     {row.get('last_run_at')}")
        print(f"last_status:     {row.get('last_run_status')}")
    else:
        print(f"agent:           {AGENT_NAME}  (no agent_config row yet)")
    r2 = sb.table("agent_activity").select("started_at,status,rows_seen,rows_processed,rows_blocked,rows_errored,summary").eq("agent_name", AGENT_NAME).order("started_at", desc=True).limit(5).execute()
    print("recent runs:")
    for row in r2.data:
        sa = (row.get("started_at") or "")[:19]
        st = (row.get("status") or "")
        rs = row.get("rows_seen", 0)
        rp = row.get("rows_processed", 0)
        rb = row.get("rows_blocked", 0)
        re_ = row.get("rows_errored", 0)
        sm = (row.get("summary") or "")[:90]
        print(f"  {sa}  {st:15}  seen={rs}  proc={rp}  block={rb}  err={re_}  {sm}")


def main():
    p = argparse.ArgumentParser(description="Empire AI Retarget Agent")
    p.add_argument("--dry-run", action="store_true", help="score and report, don't enroll")
    p.add_argument("--status", action="store_true", help="print last run + stats")
    args = p.parse_args()
    if args.status:
        show_status()
        return
    result = run_once(dry_run_override=True if args.dry_run else None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
