---
name: retarget
status: dry-run (idle)
schedule: */6 hours on :07
owner: STRIKER
last_verified: 2026-06-15
---

# retarget

## What it does

Reactivates soft-reply sequences (NOT STOP, NOT YES-converted, NOT failed-send-history). 30-day cooldown before re-send.

## When it runs

*/6 hours on :07

## What it touches

### Tables
  - `sms_sequences`
  - `sms_log`
  - `sms_opt_outs`
  - `agent_config`
  - `agent_activity`

### Files
  - `agents/retarget/retarget.py`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.retarget 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'retarget'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'retarget';
```

## Common issues

- dry_run=True because all current soft-replies are seed-data 555 numbers with failed_send_count=3. No real candidates to retarget.
- Cooldown: 30 days. Was 30 seconds (which would have spam-fired).
- Sends the same step-0 template of the source sequence (re-pitch).

## Related agents

- **prospector** — Scans Google Places for contractor businesses in 11 metros × 5 niches. Writes re…
- **prospector_bridge** — Reads top-N prospects and writes matching rows to contractors table. Dedup by ph…
- **contractor_outreach** — Enrolls active contractors in contractor_recruit SMS sequence. Calls hub /api/v1…
- **lead_scanner** — Reads radar_targets, parses address, dedup, writes to enriched_leads. Bounded by…
- **lead_converter** — Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enr…
- **warp_scout** — Reads storm forecasts, writes per-run history to storm_risk_log. NTFY/Telegram p…
- **sms_qc** — QC: tier-1 gate_regression auto-remediates sequences with failed_send_count >= 3…
- **dispatch** — Reads sms_log for inbound YES replies, looks up the lead (3-tier fallback: enric…
- **fee_watcher** — Scaffolded. Would poll for settled-claim events from the active carrier adapter.…
- **outreach** — Shared utilities for SMS sequence enrollment, voice scripts, and compliance chec…
- **settled_claim_monitor** — Polls the mock carrier for open claims and randomly settles 30% of them. DEV-ONL…
- **carrier_adapters** — Abstract CarrierAdapter interface + 5 stub implementations (State Farm, Allstate…
- **ab_monitor** — Polls /api/v1/ab-test/results and logs to agent_activity. A/B test data accumula…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
