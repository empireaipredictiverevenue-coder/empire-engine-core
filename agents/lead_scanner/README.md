---
name: lead_scanner
status: live
schedule: */6 hours on :20
owner: STRIKER
last_verified: 2026-06-15
---

# lead_scanner

## What it does

Reads radar_targets, parses address, dedup, writes to enriched_leads. Bounded by max_per_run=500.

## When it runs

*/6 hours on :20

## What it touches

### Tables
  - `radar_targets`
  - `enriched_leads`
  - `agent_config`
  - `agent_activity`

### Files
  - `agents/lead_scanner/scanner.py`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.lead_scanner 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'lead_scanner'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'lead_scanner';
```

## Common issues

- Address parser is comma-separated (real Google Places format). Old parser was space-separated and produced zip-as-city artifacts.
- Empire-pipeline radar_targets have company-name-in-address-column (upstream pipeline.py bug). The scanner handles both shapes but produces dirty address data on the empire-pipeline rows.
- Dedup query must be chunked to <200 IDs per call (PGRST204 invalid_json on large URL params).

## Related agents

- **prospector** — Scans Google Places for contractor businesses in 11 metros × 5 niches. Writes re…
- **prospector_bridge** — Reads top-N prospects and writes matching rows to contractors table. Dedup by ph…
- **contractor_outreach** — Enrolls active contractors in contractor_recruit SMS sequence. Calls hub /api/v1…
- **lead_enricher** — Placeholder. Would enrich enriched_leads with email, asset_value, ownership sign…
- **lead_converter** — Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enr…
- **lead_scorer** — Placeholder. Would score enriched_leads on urgency × asset_value × likelihood. N…
- **warp_scout** — Reads storm forecasts, writes per-run history to storm_risk_log. NTFY/Telegram p…
- **retarget** — Reactivates soft-reply sequences (NOT STOP, NOT YES-converted, NOT failed-send-h…
- **sms_qc** — QC: tier-1 gate_regression auto-remediates sequences with failed_send_count >= 3…
- **dispatch** — Reads sms_log for inbound YES replies, looks up the lead (3-tier fallback: enric…
- **fee_watcher** — Scaffolded. Would poll for settled-claim events from the active carrier adapter.…
- **settled_claim_monitor** — Polls the mock carrier for open claims and randomly settles 30% of them. DEV-ONL…
- **carrier_adapters** — Abstract CarrierAdapter interface + 5 stub implementations (State Farm, Allstate…
- **ab_monitor** — Polls /api/v1/ab-test/results and logs to agent_activity. A/B test data accumula…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
