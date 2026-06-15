---
name: sms_qc
status: live
schedule: */6 hours on :55
owner: STRIKER
last_verified: 2026-06-15
---

# sms_qc

## What it does

QC: tier-1 gate_regression auto-remediates sequences with failed_send_count >= 3 from 'active' to 'replied' to prevent retry-storming bad phones.

## When it runs

*/6 hours on :55

## What it touches

### Tables
  - `sms_sequences`
  - `qc_alerts`
  - `agent_config`
  - `agent_activity`

### Files
  - `agents/sms_qc/`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.sms_qc 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'sms_qc'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'sms_qc';
```

## Common issues

- Retarget respects the qc guard. Phones with failed_send_count >= 3 are not retargeted.

## Related agents

- **prospector** — Scans Google Places for contractor businesses in 11 metros × 5 niches. Writes re…
- **prospector_bridge** — Reads top-N prospects and writes matching rows to contractors table. Dedup by ph…
- **contractor_outreach** — Enrolls active contractors in contractor_recruit SMS sequence. Calls hub /api/v1…
- **lead_scanner** — Reads radar_targets, parses address, dedup, writes to enriched_leads. Bounded by…
- **lead_converter** — Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enr…
- **warp_scout** — Reads storm forecasts, writes per-run history to storm_risk_log. NTFY/Telegram p…
- **retarget** — Reactivates soft-reply sequences (NOT STOP, NOT YES-converted, NOT failed-send-h…
- **dispatch** — Reads sms_log for inbound YES replies, looks up the lead (3-tier fallback: enric…
- **fee_watcher** — Scaffolded. Would poll for settled-claim events from the active carrier adapter.…
- **outreach** — Shared utilities for SMS sequence enrollment, voice scripts, and compliance chec…
- **settled_claim_monitor** — Polls the mock carrier for open claims and randomly settles 30% of them. DEV-ONL…
- **carrier_adapters** — Abstract CarrierAdapter interface + 5 stub implementations (State Farm, Allstate…
- **ab_monitor** — Polls /api/v1/ab-test/results and logs to agent_activity. A/B test data accumula…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
