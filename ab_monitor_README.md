---
name: ab_monitor
status: live
schedule: */6 hours on :52
owner: STRIKER
last_verified: 2026-06-15
---

# ab_monitor

## What it does

Polls /api/v1/ab-test/results and logs to agent_activity. A/B test data accumulates over time as organic replies come in.

## When it runs

*/6 hours on :52

## What it touches

### Tables
  - `agent_config`
  - `agent_activity`

### Files
  - `agents_ab_monitor.py`
  - `empire_abtest.py`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.ab_monitor 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'ab_monitor'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'ab_monitor';
```

## Common issues

- Reply rates look inflated early on because of the 11 historical seed replies. Real rate comes in 24-72h after sends.
- A/B cohorts: bucket 0 = storm_strike, bucket 1 = storm_strike_v2. 50/50 split by hash(lead_id).

## Related agents

- **prospector** — Scans Google Places for contractor businesses in 11 metros × 5 niches. Writes re…
- **prospector_bridge** — Reads top-N prospects and writes matching rows to contractors table. Dedup by ph…
- **contractor_outreach** — Enrolls active contractors in contractor_recruit SMS sequence. Calls hub /api/v1…
- **lead_scanner** — Reads radar_targets, parses address, dedup, writes to enriched_leads. Bounded by…
- **lead_converter** — Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enr…
- **warp_scout** — Reads storm forecasts, writes per-run history to storm_risk_log. NTFY/Telegram p…
- **retarget** — Reactivates soft-reply sequences (NOT STOP, NOT YES-converted, NOT failed-send-h…
- **sms_qc** — QC: tier-1 gate_regression auto-remediates sequences with failed_send_count >= 3…
- **fee_watcher** — Scaffolded. Would poll for settled-claim events from the active carrier adapter.…
- **settled_claim_monitor** — Polls the mock carrier for open claims and randomly settles 30% of them. DEV-ONL…
- **carrier_adapters** — Abstract CarrierAdapter interface + 5 stub implementations (State Farm, Allstate…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
