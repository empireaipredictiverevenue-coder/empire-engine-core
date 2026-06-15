---
name: contractor_outreach
status: live
schedule: */4 hours on :00
owner: STRIKER
last_verified: 2026-06-15
---

# contractor_outreach

## What it does

Enrolls active contractors in contractor_recruit SMS sequence. Calls hub /api/v1/sms/enroll.

## When it runs

*/4 hours on :00

## What it touches

### Tables
  - `contractors`
  - `sms_sequences`
  - `outreach_log`
  - `agent_config`
  - `agent_activity`

### Files
  - `agents/contractor_outreach/`
  - `agents/outreach/sms_sequences.py`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.contractor_outreach 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'contractor_outreach'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'contractor_outreach';
```

## Common issues

- Slowest agent: ~1s per contractor because the hub enroll endpoint is sequential. 281 contractors × 1s = 4-5 min per run.
- Cap (config_json.max_per_run): 500. Set higher if backlog is large.
- Skips contractors with active contractor_recruit sequences.

## Related agents

- **prospector** — Scans Google Places for contractor businesses in 11 metros × 5 niches. Writes re…
- **prospector_bridge** — Reads top-N prospects and writes matching rows to contractors table. Dedup by ph…
- **lead_scanner** — Reads radar_targets, parses address, dedup, writes to enriched_leads. Bounded by…
- **lead_converter** — Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enr…
- **warp_scout** — Reads storm forecasts, writes per-run history to storm_risk_log. NTFY/Telegram p…
- **retarget** — Reactivates soft-reply sequences (NOT STOP, NOT YES-converted, NOT failed-send-h…
- **sms_qc** — QC: tier-1 gate_regression auto-remediates sequences with failed_send_count >= 3…
- **dispatch** — Reads sms_log for inbound YES replies, looks up the lead (3-tier fallback: enric…
- **fee_watcher** — Scaffolded. Would poll for settled-claim events from the active carrier adapter.…
- **outreach** — Shared utilities for SMS sequence enrollment, voice scripts, and compliance chec…
- **settled_claim_monitor** — Polls the mock carrier for open claims and randomly settles 30% of them. DEV-ONL…
- **carrier_adapters** — Abstract CarrierAdapter interface + 5 stub implementations (State Farm, Allstate…
- **ab_monitor** — Polls /api/v1/ab-test/results and logs to agent_activity. A/B test data accumula…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
