---
name: lead_converter
status: live
schedule: */6 hours on :30
owner: STRIKER
last_verified: 2026-06-15
---

# lead_converter

## What it does

Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enrolls in storm_strike or storm_strike_v2 (50/50 A/B split by hash).

## When it runs

*/6 hours on :30

## What it touches

### Tables
  - `enriched_leads`
  - `sms_sequences`
  - `outreach_log`
  - `agent_config`
  - `agent_activity`

### Files
  - `agents/lead_converter/converter.py`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.lead_converter 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'lead_converter'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'lead_converter';
```

## Common issues

- Voice channel is NOT wired (TCPA requires explicit opt-in). Returns 'voice_not_wired_in_converter_use_voice_agent' for voice candidates.
- A/B split: bucket 0 → storm_strike, bucket 1 → storm_strike_v2, based on md5(lead_id) % 2.
- Patched to accept both 'pending_outreach' and 'pending_enrichment' statuses (was only the former).

## Related agents

- **prospector** — Scans Google Places for contractor businesses in 11 metros × 5 niches. Writes re…
- **prospector_bridge** — Reads top-N prospects and writes matching rows to contractors table. Dedup by ph…
- **contractor_outreach** — Enrolls active contractors in contractor_recruit SMS sequence. Calls hub /api/v1…
- **lead_scanner** — Reads radar_targets, parses address, dedup, writes to enriched_leads. Bounded by…
- **lead_enricher** — Placeholder. Would enrich enriched_leads with email, asset_value, ownership sign…
- **lead_scorer** — Placeholder. Would score enriched_leads on urgency × asset_value × likelihood. N…
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
