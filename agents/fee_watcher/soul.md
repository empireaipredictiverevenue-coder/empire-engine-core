# Fee Watcher Agent

Watches for settled insurance claims and writes `fee_events` rows
(amount = 3% of claim amount).

## Status

**Scaffolded, not wired.** The agent exists, has the fee math, has
`fee_events` table references, but there's no real claim event source
yet. When the dispatcher sends a "we have a lead" notification to a
contractor, the contractor does the actual claim work with the
homeowner. When the claim settles, that settlement event needs to
arrive back at Empire AI. Possible sources:

  1. **Webhook from insurance carrier** — carrier POSTs to
     `/api/v1/fee/claim-settled` when a claim settles
  2. **Polling carrier API** — daily pull of the carrier's claim status
     feed
  3. **Manual webhook from operator** — operator marks a claim settled
     via dashboard button
  4. **Contractor self-report** — contractor logs in and reports the
     settlement (and a small commission is paid on integrity — risky
     but viable)

## Cron

```
# 11. Fee Watcher — every 6h on :55 (offset from other 6h agents)
55 */6 * * * /bin/bash /root/empire-v49/agents/fee_watcher/cron.sh >> /root/empire-v49/logs/agent_fee_watcher.log 2>&1
```

## Usage

```bash
python3 -m agents.fee_watcher           # one run (honors agent_config.dry_run)
python3 -m agents.fee_watcher --status  # last runs + fee_event count
```

## Config

`agent_config` row keyed `agent_name = "fee_watcher"`:
- `enabled` (bool, default False)
- `dry_run` (bool, default True)
- `config_json.fee_percent` (float, default 0.03)
- `config_json.claim_source` (str, default "none")

## What it does (when enabled)

For each settled-claim event:
  1. Calculate fee = claim_amount * 0.03
  2. Insert a `fee_events` row with:
     - claim_id, contractor_id, lead_id (joined)
     - claim_amount, fee_amount, fee_percent
     - status = "pending" (later changed to "paid" when invoiced)
     - source = "fee_watcher"
  3. Optionally notify operator (Telegram) for any fee > $X

## Locked-metric impact

This is the last piece needed to fully automate metric #4 (1 real fee earned).
Currently the chain produces:
  - Real leads in Supabase ✓
  - Real contractor outreach ✓
  - Real SMS to real businesses ✓
  - No real fee_events yet (waiting on claim source)
