"""
Empire AI · Settled Claim Monitor
==================================

Every 6h, polls the (mock) carrier API for open claims and randomly
settles a portion of them. In production this would be replaced by a
real carrier polling loop (or webhook receiver) — the in-between logic
is the same.

Workflow:
  1. Pull open claims from /api/v1/carrier/claims?status=open
  2. For each, randomly decide to "settle" with 30% probability
     (mimics a real carrier's slow settlement rate)
  3. POST /api/v1/carrier/claims/{id}/settle with a 60-90% asset_value
     settled_amount
  4. Each settlement goes through the existing /api/v1/fee/claim-settled
     endpoint, which writes a fee_events row
  5. Log the run to agent_activity

This means the chain can be exercised end-to-end without any real
carrier integration. The fee_events table gets real rows from
real (mocked) carrier events.
"""
import os, sys, json, random, uuid
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path("/root/empire-v49").resolve()))

import httpx
from supabase import create_client

AGENT_NAME = "settled_claim_monitor"
HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:8000")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "Jaykub20*")
SETTLE_PROBABILITY = 0.3  # 30% of open claims get settled each tick
SETTLE_FRACTION_MIN = 0.60
SETTLE_FRACTION_MAX = 0.95


def run_once() -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    started_at = datetime.now(timezone.utc)

    # 1. fetch open claims
    try:
        r = httpx.get(
            f"{HUB_URL}/api/v1/carrier/claims?status=open&limit=50",
            headers={"Authorization": f"Bearer {HUB_TOKEN}"},
            timeout=15,
        )
        open_claims = r.json().get("claims", [])
    except Exception as e:
        return {"status": "error", "error": str(e)}

    # 2. randomly pick a portion to settle
    to_settle = [c for c in open_claims if random.random() < SETTLE_PROBABILITY]
    if not to_settle:
        summary = f"settled-claim-monitor: 0/{len(open_claims)} open claims settled (no dice)"
        _log(sb, started_at, summary, 0, 0, 0)
        return {"status": "ok", "settled": 0, "open": len(open_claims), "summary": summary}

    # 3. settle each
    settled = 0
    total_claim_value = 0
    total_fee_value = 0
    for c in to_settle:
        fraction = random.uniform(SETTLE_FRACTION_MIN, SETTLE_FRACTION_MAX)
        amount = round(float(c["asset_value"]) * fraction, 2)
        try:
            r2 = httpx.post(
                f"{HUB_URL}/api/v1/carrier/claims/{c['id']}/settle",
                headers={"Authorization": f"Bearer {HUB_TOKEN}", "Content-Type": "application/json"},
                json={"settled_amount": amount},
                timeout=20,
            )
            out = r2.json()
            fee_event = out.get("fee_event")
            if fee_event:
                settled += 1
                total_claim_value += amount
                total_fee_value += float(fee_event.get("fee_amount") or 0)
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
