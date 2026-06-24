"""
Empire AI · Settled Claim Monitor
==================================

Every 6h, polls the hub for open claims and randomly settles a portion
of them so the fee_watcher → fee_event chain has organic throughput.
In production this is replaced by a real carrier webhook — the in-between
logic is the same.

Workflow:
  1. Pull open claims from /api/v1/claims/list?status=open
  2. For each, randomly decide to "settle" with 30% probability
     (mimics a real carrier's slow settlement rate)
  3. POST /api/v1/claims/mark-settled with a 60-95% asset_value
     settled_amount (uses dispatch_id, not claim id)
  4. fee_watcher picks the newly-settled claim up on its next tick
     and writes a fee_events row via /api/v1/fee/claim-settled
  5. Log the run to agent_activity
"""
import os, sys, json, random, uuid
from datetime import datetime, timezone
from pathlib import Path
REPO = Path("/root/empire-v49").resolve()
sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

import httpx
from supabase import create_client

AGENT_NAME = "settled_claim_monitor"
HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:8001")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "")
SETTLE_PROBABILITY = 0.3  # 30% of open claims get settled each tick
SETTLE_FRACTION_MIN = 0.60
SETTLE_FRACTION_MAX = 0.95
DEFAULT_ASSET_VALUE = 125000.0  # fallback for open claims with null asset_value


def run_once() -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    started_at = datetime.now(timezone.utc)

    # 1. fetch open claims from the real hub endpoint
    try:
        r = httpx.get(
            f"{HUB_URL}/api/v1/claims/list?status=open&limit=50",
            headers={"Authorization": f"Bearer {HUB_TOKEN}"},
            timeout=15,
        )
        r.raise_for_status()
        open_claims = r.json().get("claims", [])
    except Exception as e:
        return {"status": "error", "error": f"list open claims: {e}"}

    # 2. randomly pick a portion to settle
    to_settle = [c for c in open_claims if random.random() < SETTLE_PROBABILITY]
    if not to_settle:
        summary = f"settled-claim-monitor: 0/{len(open_claims)} open claims settled (no dice)"
        _log(sb, started_at, summary, 0, 0, 0)
        return {"status": "ok", "settled": 0, "open": len(open_claims), "summary": summary}

    # 3. settle each via /api/v1/claims/mark-settled; fee_watcher writes fee_event on next tick
    settled = 0
    total_claim_value = 0
    total_fee_value = 0
    for c in to_settle:
        av = c.get("asset_value")
        base = float(av) if av is not None else DEFAULT_ASSET_VALUE
        fraction = random.uniform(SETTLE_FRACTION_MIN, SETTLE_FRACTION_MAX)
        amount = round(base * fraction, 2)
        try:
            r2 = httpx.post(
                f"{HUB_URL}/api/v1/claims/mark-settled",
                headers={"Authorization": f"Bearer {HUB_TOKEN}", "Content-Type": "application/json"},
                json={
                    "dispatch_id": c.get("dispatch_id"),
                    "settled_amount": amount,
                    "loss_description": c.get("loss_description") or "settled by monitor",
                },
                timeout=20,
            )
            if r2.status_code in (200, 201):
                settled += 1
                # fee = 3% of settled amount (matches empire_fee.py)
                total_claim_value += amount
                total_fee_value += round(amount * 0.03, 2)
        except Exception as e:
            continue

    summary = (
        f"settled-claim-monitor: {settled}/{len(to_settle)} settled, "
        f"${total_claim_value:.0f} in claims, ${total_fee_value:.0f} in fees"
    )
    _log(sb, started_at, summary, settled, total_claim_value, total_fee_value)
    print(summary)
    return {"status": "ok", "settled": settled, "open": len(open_claims), "summary": summary}


def _log(sb, started_at, summary, settled, claim_value, fee_value):
    sb.table("agent_activity").insert({
        "agent_name": AGENT_NAME,
        "run_id": str(uuid.uuid4()),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "rows_seen": 0,
        "rows_processed": settled,
        "rows_errored": 0,
        "error": None,
        "summary": summary[:500],
        "meta": {"settled_claim_value_usd": claim_value, "settled_fee_value_usd": fee_value},
    }).execute()


if __name__ == "__main__":
    run_once()
