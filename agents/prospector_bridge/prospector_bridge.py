"""
Empire AI - Predictive Revenue
Prospector Bridge Agent
==========================

Closes the gap between bots/prospector.py (which finds roofing
contractors via Google Places and writes them to the `prospects`
table) and the contractor_outreach agent (which reads from the
`contractors` table and enrolls them in the contractor_recruit
sequence). Without this bridge, prospects sit in `prospects` and
never get a real outreach.

For each prospect that qualifies (buy_signal_score >= MIN_SCORE,
status not already 'bridged'), this agent:

  1. Normalizes the phone to E.164 (+1US format)
  2. Skips if a contractors row already exists for the phone
     (idempotent - safe to re-run)
  3. Inserts a row into contractors with:
       - name           = prospect.business_name
       - phone          = E.164 normalized
       - email          = (none, will be filled by contact_discovery)
       - metro          = prospect.metro
       - active         = True
       - specialties    = [prospect.niche]
       - source         = "prospector_bridge"
       - meta           = carries all the buyer-signal context
  4. Updates the prospect row to status="bridged" with
     contractor_id=<new uuid>
  5. Logs to agent_activity for verification

The recruiter agent (agents/contractor_outreach) will pick up the new
contractors row on its next cron tick and enroll it in the
contractor_recruit sequence (v2 copy with the no-call ask).

Usage:
    python3 -m agents.prospector_bridge
    python3 -m agents.prospector_bridge --status
"""
import os
import sys
import re
import json
import uuid
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

log = logging.getLogger("empire.prospector_bridge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# Prospects must clear this bar to be bridged. The other agent's
# prospector already scored them 0-100 based on review count, website,
# phone, and rating. 40 = "has a real business with a phone number".
# Set higher for tighter qualification; lower for more volume.
MIN_SCORE: int = 40

# Status values the prospector sets that this bridge is willing to
# pick up. "contacted" means the other agent ran the prospector and
# printed the list - it has NOT actually been contacted by us. The
# bridge is the first real touch.
INCLUDED_STATUSES: Tuple[str, ...] = ("new", "contacted")


def _sb() -> Any:
    url: str = os.getenv("SUPABASE_URL", "")
    key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _normalize_phone(phone: str) -> str:
    """E.164 normalize. US default if 10 digits, +country if 11+."""
    if not phone:
        return ""
    digits: str = "".join(c for c in phone if c.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if phone.strip().startswith("+") and len(digits) >= 10:
        return "+" + digits
    return ""


def _read_config(sb: Any) -> Dict[str, Any]:
    r = sb.table("agent_config").select("*").eq("agent_name", "prospector_bridge").limit(1).execute()
    if not r.data:
        return {"enabled": True, "max_per_run": 100, "min_score": MIN_SCORE}
    row: Dict[str, Any] = r.data[0]
    cfg: Dict[str, Any] = row.get("config_json") or {}
    return {
        "enabled":    bool(row.get("enabled", True)),
        "max_per_run": int(cfg.get("max_per_run", 100)),
        "min_score":   int(cfg.get("min_score", MIN_SCORE)),
    }


def _log_activity(
    sb: Any,
    agent_name: str,
    run_id: uuid.UUID,
    started_at: datetime,
    status: str,
    **kwargs: Any,
) -> str:
    return emit_agent_event(
        sb=sb, agent_name=agent_name, run_id=run_id,
        started_at=started_at, status=status,
        **kwargs,
    )


def _update_config(
    sb: Any,
    agent_name: str,
    status: str,
    finished_at: str,
) -> None:
    sb.table("agent_config").update({
        "last_run_at":      finished_at,
        "last_run_status":  status,
        "updated_at":       datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", agent_name).execute()


def _find_existing_contractor_by_phone(sb: Any, phone: str) -> Optional[Dict[str, Any]]:
    """Return the existing contractors row for this phone, or None."""
    if not phone:
        return None
    try:
        r = sb.table("contractors").select("id,name,active").eq("phone", phone).limit(1).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        log.warning(f"prospector_bridge: existing-contractor check failed for {phone}: {e}")
        return None


def _build_contractor_row(prospect: Dict[str, Any], phone_e164: str) -> Dict[str, Any]:
    """Map a prospect row to a contractors insert payload."""
    biz: str = str(prospect.get("business_name") or "")
    # contractors.email is NOT NULL with a UNIQUE constraint. We don't
    # have a real email from Google Places; use a synthetic one keyed
    # off the PHONE (globally unique) instead of the business name
    # (collides on franchises like "The Brothers That Just Do Gutters"
    # which appear in 11 metros). contact_discovery overwrites this
    # with the real email on its next run.
    digits: str = "".join(c for c in phone_e164 if c.isdigit())
    synthetic_email: str = f"unknown.{digits}@prospector.placeholder"

    meta: Dict[str, Any] = {
        "source":              "prospector_bridge",
        "bridged_at":          datetime.now(timezone.utc).isoformat(),
        "tcpa_consent":        False,   # not yet opted in; the recruit sequence asks via reply
        "buy_signal_score":    prospect.get("buy_signal_score"),
        "rating":              prospect.get("rating"),
        "review_count":        prospect.get("review_count"),
        "prospect_id":         prospect.get("id"),
        "prospect_niche":      prospect.get("niche"),
        "prospect_metro":      prospect.get("metro"),
        "synthetic_email":     True,    # marker so contact_discovery knows to overwrite
    }
    if prospect.get("website"):
        meta["website"] = prospect["website"]
    if prospect.get("address"):
        meta["address"] = prospect["address"]
    if prospect.get("notes"):
        meta["notes"] = prospect["notes"]

    # Map niche to a specialties list. The real contractors.specialties
    # column is a list of strings; we put the niche as a single entry
    # so it shows up in the contractor dashboard filter.
    specialty: str = str(prospect.get("niche") or "roofing")
    return {
        "name":         biz,
        "phone":        phone_e164,
        "email":        synthetic_email,
        "metro":        str(prospect.get("metro") or ""),
        "active":       True,
        "specialties":  [specialty],
        "meta":         meta,
    }


def run() -> Dict[str, Any]:
    started_at: datetime = datetime.now(timezone.utc)
    run_id: uuid.UUID = uuid.uuid4()
    sb: Any = _sb()
    cfg: Dict[str, Any] = _read_config(sb)

    if not cfg["enabled"]:
        _log_activity(sb, "prospector_bridge", run_id, started_at, "skipped_disabled",
                      summary="disabled in agent_config")
        return {"status": "skipped_disabled", "rows_processed": 0}

    min_score: int = int(cfg.get("min_score", MIN_SCORE))

    # 1) Find prospects that qualify
    r = (sb.table("prospects")
           .select("*")
           .in_("status", list(INCLUDED_STATUSES))
           .gte("buy_signal_score", min_score)
           .not_.is_("phone", "null")
           .order("buy_signal_score", desc=True)
           .limit(int(cfg["max_per_run"]))
           .execute())
    candidates: List[Dict[str, Any]] = r.data or []
    rows_seen: int = len(candidates)
    log.info(f"prospector_bridge: {rows_seen} prospects qualify (status IN {INCLUDED_STATUSES}, score >= {min_score})")

    rows_processed: int = 0
    rows_skipped_dup: int = 0
    rows_errored: int = 0
    rows_no_phone: int = 0
    error_msgs: List[str] = []
    sample_bridges: List[Dict[str, Any]] = []

    for prospect in candidates:
        try:
            # Normalize phone
            phone_e164: str = _normalize_phone(str(prospect.get("phone", "") or ""))
            if not phone_e164:
                rows_no_phone += 1
                continue

            # Idempotency: skip if a contractor already exists for this phone
            existing: Optional[Dict[str, Any]] = _find_existing_contractor_by_phone(sb, phone_e164)
            if existing:
                # Mark the prospect as bridged anyway so it doesn't reappear
                try:
                    existing_notes: str = str(prospect.get("notes") or "")
                    sb.table("prospects").update({
                        "status":         "bridged",
                        "notes":          existing_notes + f"\nbridge: existing contractor {existing.get('id')}",
                    }).eq("id", prospect["id"]).execute()
                except Exception:
                    pass
                rows_skipped_dup += 1
                continue

            # Build + insert
            payload: Dict[str, Any] = _build_contractor_row(prospect, phone_e164)
            ins = sb.table("contractors").insert(payload).execute()
            if not ins.data:
                rows_errored += 1
                error_msgs.append(f"{prospect.get('business_name', '?')}: insert returned no row")
                continue

            new_id: str = str(ins.data[0]["id"])

            # Mark the prospect row as bridged
            try:
                prospect_notes: str = str(prospect.get("notes") or "")
                sb.table("prospects").update({
                    "status":         "bridged",
                    "contacted_at":   datetime.now(timezone.utc).isoformat(),
                    "contacted_status": "bridged_to_contractors",
                    "notes":          prospect_notes + f"\nbridged {new_id} at {datetime.now(timezone.utc).isoformat()}",
                }).eq("id", prospect["id"]).execute()
            except Exception as e:
                log.warning(f"prospector_bridge: could not mark prospect {prospect.get('id')} bridged: {e}")

            rows_processed += 1
            if len(sample_bridges) < 5:
                sample_bridges.append({
                    "prospect_id":  prospect.get("id"),
                    "contractor_id": new_id,
                    "business":     prospect.get("business_name"),
                    "phone":        phone_e164,
                    "metro":        prospect.get("metro"),
                    "score":        prospect.get("buy_signal_score"),
                })

        except Exception as e:
            rows_errored += 1
            error_msgs.append(f"{str(prospect.get('id', '?'))[:8]}: {type(e).__name__}: {e}")
            log.warning(f"prospector_bridge: failed for {prospect.get('id')}: {e}")

    finished_at: str = datetime.now(timezone.utc).isoformat()
    summary: str = (f"[LIVE] scanned {rows_seen} prospects, "
                    f"{rows_processed} bridged, "
                    f"{rows_skipped_dup} skipped (duplicate phone), "
                    f"{rows_no_phone} skipped (no phone), "
                    f"{rows_errored} errored")
    if sample_bridges:
        summary += f". Sample: {json.dumps(sample_bridges, default=str)[:500]}"

    status: str = "ok"  # always ok even with errors; errors are logged
    err_field: Optional[str] = None if rows_errored == 0 else "; ".join(error_msgs[:5])

    _log_activity(sb, "prospector_bridge", run_id, started_at, status,
                  rows_seen=rows_seen, rows_processed=rows_processed,
                  rows_blocked=rows_skipped_dup + rows_no_phone,
                  rows_errored=rows_errored, error=err_field, summary=summary)
    _update_config(sb, "prospector_bridge", status, finished_at)

    log.info(summary[:200])
    return {
        "status":            status,
        "rows_seen":         rows_seen,
        "rows_processed":    rows_processed,
        "rows_skipped_dup":  rows_skipped_dup,
        "rows_no_phone":     rows_no_phone,
        "rows_errored":      rows_errored,
        "sample_bridges":    sample_bridges,
    }


def main() -> None:
    p: argparse.ArgumentParser = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true")
    args = p.parse_args()
    if args.status:
        sb: Any = _sb()
        cfg: Dict[str, Any] = _read_config(sb)
        last_act = (sb.table("agent_activity")
                      .select("*")
                      .eq("agent_name", "prospector_bridge")
                      .order("started_at", desc=True)
                      .limit(1).execute())
        print(json.dumps({
            "config":  cfg,
            "last_run": last_act.data[0] if last_act.data else None,
        }, indent=2, default=str))
        return
    result: Dict[str, Any] = run()
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled") else 1)


if __name__ == "__main__":
    main()
