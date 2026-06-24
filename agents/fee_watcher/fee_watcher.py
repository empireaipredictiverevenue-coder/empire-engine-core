"""
Empire AI · Fee Watcher Agent (v2)
===================================

Polls the carrier_claims table for claims with status='settled' that
don't yet have a corresponding fee_events row, and automatically creates
the fee_event.

The flow:
  1. Hub auto-creates a carrier_claims row when a dispatch goes out
     (status='open', no settlement info yet).
  2. Operator (or future carrier-scraping agent) calls
     POST /api/v1/claims/mark-settled to set status='settled' and settled_amount.
  3. This cron agent picks up settled claims and creates fee_events
     (3% of settled_amount).

Usage:
    python3 -m agents.fee_watcher
    python3 -m agents.fee_watcher --status
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

# Lazy import for bounty tracking — fee_watcher creates fee_events that
# may trigger referral bounties on the referred contractor's first claim.
_BOUNTY_IMPORTED = False

def _check_bounty(fee_event: dict):
    """Call check_bounty_eligible_sync on a newly created fee_event.
    Silent if bounty_tracker module can't be imported."""
    global _BOUNTY_IMPORTED
    try:
        if not _BOUNTY_IMPORTED:
            from bots.bounty_tracker import check_bounty_eligible_sync
            _BOUNTY_IMPORTED = True
        check_bounty_eligible_sync(fee_event)
    except ImportError:
        _BOUNTY_IMPORTED = True  # don't retry
    except Exception as e:
        log.debug(f"[fee_watcher] bounty check skipped: {e}")

log = logging.getLogger("empire.fee_watcher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "fee_watcher"
FEE_PERCENT = 0.03  # 3% per claim


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if not r.data:
        return {"enabled": False, "dry_run": False, "fee_percent": FEE_PERCENT}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", False),
        "dry_run": row.get("dry_run", False),
        "fee_percent": cfg.get("fee_percent", FEE_PERCENT),
    }


def _log_activity(sb, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_errored=0,
                  error=None, summary=None):
    finished_at = datetime.now(timezone.utc).isoformat()
    try:
        sb.table("agent_activity").insert({
            "agent_name": AGENT_NAME,
            "run_id": str(run_id),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at,
            "status": status,
            "rows_seen": rows_seen,
            "rows_processed": rows_processed,
            "rows_errored": rows_errored,
            "error": error,
            "summary": summary,
        }).execute()
    except Exception:
        pass
    return finished_at


def _update_config(sb, status, finished_at):
    try:
        sb.table("agent_config").update({
            "last_run_at": finished_at,
            "last_run_status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("agent_name", AGENT_NAME).execute()
    except Exception:
        pass


def _already_has_fee_event(sb, carrier_claim_id: str, dispatch_id: str = "") -> bool:
    """Check if a fee_event already exists for this carrier_claim.

    Two checks (any match wins):
      1. claim_id == carrier_claim_id   - the original dedup
      2. meta->>dispatch_id == dispatch_id - catches the webhook-created
         fee_event whose claim_id is a user-supplied string (e.g.
         "REAL-CLAIM-001"), not the carrier_claim UUID. The webhook
         handler inserts a carrier_claims row with an auto-generated
         UUID, so the fee_watcher poll would otherwise create a second
         fee_event for the same dispatch.

    Without the dispatch_id check, a webhook -> fee_watcher cron race
    fires ~2 minutes apart and inserts two fee_events for the same
    settled claim (observed 2026-06-24 with Porter & Sons Roofing).
    """
    try:
        r = sb.table("fee_events").select("id").eq("claim_id", carrier_claim_id).limit(1).execute()
        if r.data:
            return True
        if dispatch_id:
            r2 = (
                sb.table("fee_events")
                .select("id")
                .eq("meta->>dispatch_id", dispatch_id)
                .limit(1)
                .execute()
            )
            if r2.data:
                return True
        return False
    except Exception:
        return False


def _create_fee_event(sb, claim: dict, dry_run: bool, fee_percent: float) -> dict:
    """
    Given a settled carrier_claim row, create a fee_events row.
    Looks up the dispatch to get contractor_id and lead_id.
    """
    claim_id = claim.get("id")
    dispatch_id = claim.get("dispatch_id")
    settled_amount = float(claim.get("settled_amount", 0))
    fee = round(settled_amount * fee_percent, 2)

    # Resolve contractor_id and lead_id from dispatches
    contractor_id = None
    lead_id = None
    contractor_name = None
    contractor_phone = None
    contractor_email = None
    if dispatch_id:
        try:
            dr = sb.table("dispatches").select("contractor_id, lead_id").eq("id", dispatch_id).limit(1).execute()
            if dr.data:
                dispatch = dr.data[0]
                contractor_id = dispatch.get("contractor_id")
                lead_id = dispatch.get("lead_id")
                # lead_id in dispatches is actually radar_target_id; resolve to enriched_lead
                if lead_id:
                    el = sb.table("enriched_leads").select("id").eq("radar_target_id", lead_id).limit(1).execute()
                    if el.data:
                        lead_id = el.data[0]["id"]
                # Resolve contractor contact info for meta
                if contractor_id:
                    try:
                        cr = sb.table("contractors").select("name, phone, email").eq("id", contractor_id).limit(1).execute()
                        if cr.data:
                            c_data = cr.data[0]
                            contractor_name = c_data.get("name")
                            contractor_phone = c_data.get("phone")
                            contractor_email = c_data.get("email")
                    except Exception:
                        pass
        except Exception as e:
            log.warning(f"[fee_watcher] dispatch lookup failed for {dispatch_id}: {e}")

    fee_event = {
        "claim_id": str(claim_id),
        "contractor_id": contractor_id,
        "lead_id": lead_id,
        "claim_amount": settled_amount,
        "fee_amount": fee,
        "fee_percent": fee_percent,
        "currency": "USD",
        "settled_at": claim.get("settled_at") or datetime.now(timezone.utc).isoformat(),
        "source": "fee_watcher_poll",
        "status": "pending",
        "meta": {
            "carrier_claim_id": str(claim_id),
            "dispatch_id": dispatch_id,
            "contractor_name": contractor_name,
            "contractor_phone": contractor_phone,
            "contractor_email": contractor_email,
        },
    }

    if dry_run:
        return {"action": "would_create", "fee_event": fee_event, "fee": fee}

    try:
        r = sb.table("fee_events").insert(fee_event).execute()
        inserted_id = r.data[0]["id"] if r.data else None
        created_event = {"id": inserted_id, **fee_event}
        # Fire bounty check — the referred contractor's first fee_event
        # triggers a $500 bounty for the referrer
        if inserted_id:
            _check_bounty(created_event)
        return {"action": "created", "fee_event": created_event, "fee": fee}
    except Exception as e:
        return {"action": "error", "error": str(e)[:200]}


def run_once(dry_run_override=None) -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)
    dry_run = cfg["dry_run"] if dry_run_override is None else dry_run_override
    fee_percent = cfg["fee_percent"]

    if not cfg["enabled"]:
        msg = "agent disabled in agent_config — enable via agent_config.enabled=true"
        log.info(msg)
        _log_activity(sb, run_id, started_at, "skipped_disabled", summary=msg)
        return {"status": "skipped_disabled", "reason": msg}

    # ── Poll carrier_claims for settled claims ──────────────────
    rows_seen = 0
    rows_processed = 0
    rows_errored = 0
    fees_created = 0.0
    errors: list[str] = []

    try:
        r = sb.table("carrier_claims").select("*").eq("status", "settled").order("settled_at", desc=True).limit(200).execute()
        settled_claims = r.data or []
        rows_seen = len(settled_claims)

        for claim in settled_claims:
            claim_id = str(claim.get("id", ""))
            if not claim_id:
                rows_errored += 1
                errors.append("claim missing id")
                continue

            # Skip if fee_event already exists (checks claim_id AND dispatch_id)
            claim_dispatch_id = str(claim.get("dispatch_id") or "")
            if _already_has_fee_event(sb, claim_id, claim_dispatch_id):
                continue

            result = _create_fee_event(sb, claim, dry_run, fee_percent)
            if result["action"] in ("created", "would_create"):
                rows_processed += 1
                fees_created += result.get("fee", 0)
                log.info(
                    f"[fee_watcher] {result['action']}: claim={claim_id} "
                    f"dispatch={claim.get('dispatch_id')} "
                    f"amount=${claim.get('settled_amount', 0)} "
                    f"fee=${result.get('fee', 0)}"
                )
            else:
                rows_errored += 1
                err = result.get("error", "unknown")
                errors.append(f"claim {claim_id}: {err}")
                log.warning(f"[fee_watcher] error on claim {claim_id}: {err}")
    except Exception as e:
        msg = f"carrier_claims query failed: {e}"
        log.error(msg)
        errors.append(msg)
        rows_errored = rows_seen

    # ── Build summary ────────────────────────────────
    total_processed = rows_processed
    summary = (
        f"seen={rows_seen} processed={rows_processed} errored={rows_errored} "
        f"fees_created=${fees_created:.2f} dry_run={dry_run}"
    )
    if errors:
        summary += f" | errors: {'; '.join(errors[:3])}"

    log.info(f"[fee_watcher] {summary}")
    finished_at = _log_activity(
        sb, run_id, started_at,
        status="ok" if rows_errored == 0 else "partial",
        rows_seen=rows_seen,
        rows_processed=rows_processed,
        rows_errored=rows_errored,
        error="; ".join(errors[:5]) if errors else None,
        summary=summary,
    )
    _update_config(sb, "ok" if rows_errored == 0 else "partial", finished_at)

    return {
        "status": "ok" if rows_errored == 0 else "partial",
        "rows_seen": rows_seen,
        "rows_processed": rows_processed,
        "rows_errored": rows_errored,
        "fees_created": round(fees_created, 2),
        "dry_run": dry_run,
        "errors": errors[:5],
    }


def show_status():
    sb = _sb()
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if r.data:
        row = r.data[0]
        cfg = row.get("config_json") or {}
        print("agent:        " + AGENT_NAME)
        print("enabled:      " + str(row.get("enabled")))
        print("dry_run:      " + str(row.get("dry_run")))
        print("fee_percent:  " + str(cfg.get("fee_percent", FEE_PERCENT) * 100) + "%")
        print("last_run_at:  " + str(row.get("last_run_at")))
        print("last_status:  " + str(row.get("last_run_status")))
    else:
        print("agent:        " + AGENT_NAME + "  (no agent_config row yet)")

    # Show recent activity
    r2 = sb.table("agent_activity").select("started_at,status,summary").eq("agent_name", AGENT_NAME).order("started_at", desc=True).limit(5).execute()
    print("\nrecent runs:")
    for row in (r2.data or []):
        started = str(row.get("started_at", ""))[:19]
        status = str(row.get("status", ""))
        summary = str(row.get("summary", ""))[:80]
        print(f"  {started}  {status}  {summary}")

    # Show carrier_claims summary
    print("\ncarrier_claims:")
    try:
        r3 = sb.table("carrier_claims").select("id,status", count="exact").limit(0).execute()
        print(f"  total: {r3.count}")
        r4 = sb.table("carrier_claims").select("id,dispatch_id,status,settled_amount,settled_at,created_at").order("created_at", desc=True).limit(10).execute()
        for row in (r4.data or []):
            print(f"  {str(row.get('id',''))[:8]:8s}  {str(row.get('status','')):10s}  settled=${row.get('settled_amount', 0)}  {str(row.get('created_at',''))[:19]}")
    except Exception as e:
        print(f"  query error: {e}")

    # Show fee_events total
    try:
        r5 = sb.table("fee_events").select("id", count="exact").limit(0).execute()
        print(f"\nfee_events total: {r5.count}")
        if r5.count and r5.count > 0:
            r6 = sb.table("fee_events").select("claim_amount,fee_amount,status,settled_at,source").order("settled_at", desc=True).limit(5).execute()
            for row in (r6.data or []):
                print(f"  {str(row.get('settled_at',''))[:19]}  claim=${row.get('claim_amount',0)}  fee=${row.get('fee_amount',0)}  {row.get('status','')}  {row.get('source','')}")
    except Exception as e:
        print(f"  query error: {e}")


def main():
    p = argparse.ArgumentParser(description="Empire AI Fee Watcher v2 (carrier_claims → fee_events)")
    p.add_argument("--dry-run", action="store_true", help="Run without writing fee_events (overrides config)")
    p.add_argument("--status", action="store_true", help="Show agent status and recent activity")
    args = p.parse_args()
    if args.status:
        show_status()
        return
    result = run_once(dry_run_override=True if args.dry_run else None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
