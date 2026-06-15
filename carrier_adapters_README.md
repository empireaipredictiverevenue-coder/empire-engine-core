---
name: carrier_adapters
status: scaffolded
schedule: none
owner: STRIKER
last_verified: 2026-06-15
---

# carrier_adapters

## What it does

Abstract CarrierAdapter interface + 5 stub implementations (State Farm, Allstate, USAA, Liberty Mutual, Farmers). MockCarrierAdapter is the only one with health=True. Flip the active_carrier_adapter config flag when a real integration lands.

## When it runs

none

## What it touches

### Tables
  - `agent_config`

### Files
  - `carrier_adapters.py`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.carrier_adapters 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'carrier_adapters'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'carrier_adapters';
```

## Common issues

- active_carrier_adapter is currently 'mock' in agent_config.settled_claim_monitor.config_json.
- When a real integration lands: implement the methods on the matching stub class, then update the config flag.
- No production code depends on a specific carrier. The chain runs on whichever adapter is flagged.

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
- **ab_monitor** — Polls /api/v1/ab-test/results and logs to agent_activity. A/B test data accumula…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
