"""
Empire AI · Predictive Revenue
Fee Watcher Agent
====================

Polls the insurance claim tracking table (or webhook source) for
settled-claim events that should generate a fee_event row.

Right now this is a stub — there's no actual claim event source wired in.
The real flow needs a webhook from the insurance carrier API or a polling
cron that checks a public claim status page. For now this agent:

  1. Checks agent_config for an enabled claim source
  2. Reports what it sees (currently: nothing — no claim event source)
  3. When a real claim event source exists, this becomes the entry point

The "fee" itself: Empire AI charges 3% on settled insurance claims. So
when a claim_event row arrives with status='settled' and amount > 0,
we write a fee_event row with amount = 0.03 * claim_amount.

This is scaffolded but not wired because we don't have a claim source
yet. The agent runs in dry-run mode by default.

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

log = logging.getLogger("empire.fee_watcher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "fee_watcher"
FEE_PERCENT = 0.03  # 3% per claim — see commits 2a038ef, f81f868


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if not r.data:
        return {"enabled": False, "dry_run": True, "fee_percent": FEE_PERCENT,
                "claim_source": "none"}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", False),
        "dry_run": row.get("dry_run", True),
        "fee_percent": cfg.get("fee_percent", FEE_PERCENT),
        "claim_source": cfg.get("claim_source", "none"),
    }


def _log_activity(sb, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_errored=0,
                  error=None, summary=None):
    finished_at = datetime.now(timezone.utc).isoformat()
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
    return finished_at


def _update_config(sb, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", AGENT_NAME).execute()


def _process_settled_claim(sb, claim: dict, dry_run: bool) -> dict:
    """
    Given a settled claim dict (must have id, amount, contractor_id, lead_id),
    create a fee_event row.
    """
    claim_amount = float(claim.get("amount", 0))
    fee = round(claim_amount * FEE_PERCENT, 2)
    fee_event = {
        "claim_id": claim.get("id"),
        "contractor_id": claim.get("contractor_id"),
        "lead_id": claim.get("lead_id"),
        "claim_amount": claim_amount,
        "fee_amount": fee,
        "fee_percent": FEE_PERCENT,
        "currency": "USD",
        "settled_at": claim.get("settled_at") or datetime.now(timezone.utc).isoformat(),
        "source": "fee_watcher",
        "status": "pending",
    }
    if dry_run:
        return {"action": "would_create", "fee_event": fee_event, "fee": fee}
    sb.table("fee_events").insert(fee_event).execute()
    return {"action": "created", "fee_event": fee_event, "fee": fee}


def run_once(dry_run_override=None) -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)
    dry_run = cfg["dry_run"] if dry_run_override is None else dry_run_override

    if not cfg["enabled"]:
        msg = "agent disabled in agent_config — fee_watcher is scaffolded but not wired (no claim event source yet)"
        log.info(msg)
        _log_activity(sb, run_id, started_at, "skipped_disabled", summary=msg)
        return {"status": "skipped_disabled", "reason": msg}

    # No claim event source wired yet. This is the right place to plug in:
    # - Polling: read claim_events table (or carrier API) for status='settled'
    # - Webhook: hub POSTs to /api/v1/fee/claim-settled when carrier notifies
    # - Cron pull: hit a public claim status page
    # For now: report the state and exit.
    summary = (
        f"agent ENABLED, claim_source={cfg['claim_source']}, fee_percent={cfg['fee_percent']*100:.1f}%. "
        f"Waiting for claim event source to deliver settled-claim events. "
        f"Next step: wire /api/v1/fee/claim-settled webhook OR add a claim_events table + polling."
    )
    log.info(summary)
    finished_at = _log_activity(sb, run_id, started_at, "idle", summary=summary[:500])
    _update_config(sb, "idle", finished_at)
    return {
        "status": "idle",
        "claim_source": cfg["claim_source"],
        "fee_percent": cfg["fee_percent"],
        "next_step": "wire a claim event source (webhook or polling)",
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
        print("claim_source: " + str(cfg.get("claim_source", "none")))
        print("last_run_at:  " + str(row.get("last_run_at")))
        print("last_status:  " + str(row.get("last_run_status")))
    else:
        print("agent:        " + AGENT_NAME + "  (no agent_config row yet)")
    r2 = sb.table("agent_activity").select("started_at,status,summary").eq("agent_name", AGENT_NAME).order("started_at", desc=True).limit(5).execute()
    print("recent runs:")
    for row in r2.data:
        print("  " + str(row.get("started_at",""))[:19] + "  " + str(row.get("status","")) + "  " + str(row.get("summary",""))[:80])
    r3 = sb.table("fee_events").select("id", count="exact").limit(0).execute()
    print("\nfee_events total: " + str(r3.count))
    if r3.count and r3.count > 0:
        r4 = sb.table("fee_events").select("claim_amount,fee_amount,status,settled_at,source").order("settled_at", desc=True).limit(5).execute()
        for row in r4.data:
            print("  " + str(row.get("settled_at",""))[:19] + "  claim=$" + str(row.get("claim_amount",0)) + "  fee=$" + str(row.get("fee_amount",0)) + "  " + str(row.get("status","")))


def main():
    p = argparse.ArgumentParser(description="Empire AI Fee Watcher (claim→fee)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--status", action="store_true")
    args = p.parse_args()
    if args.status:
        show_status()
        return
    result = run_once(dry_run_override=True if args.dry_run else None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
