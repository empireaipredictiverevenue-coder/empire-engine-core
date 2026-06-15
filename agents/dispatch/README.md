---
name: dispatch
status: live
schedule: */1 minutes (foreground cron in hub)
owner: STRIKER
last_verified: 2026-06-15
---

# dispatch

## What it does

Reads sms_log for inbound YES replies, looks up the lead (3-tier fallback: enriched_leads, sms_sequences meta, radar_targets), checks idempotency (24h), calls hub /api/v1/matching/dispatch.

## When it runs

*/1 minutes (foreground cron in hub)

## What it touches

### Tables
  - `sms_log`
  - `enriched_leads`
  - `sms_sequences`
  - `radar_targets`
  - `dispatches`
  - `outreach_log`

### Files
  - `agents/dispatch/dispatcher.py`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.dispatch 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'dispatch'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'dispatch';
```

## Common issues

- Idempotency: a lead dispatched within 24h is skipped.
- 3-tier lead lookup fallback: enriched_leads (preferred), sms_sequences meta, radar_targets (last resort).
- Only responds to YES, NOTMAYBE, NOTNOW, etc. — only YES, Y, OK, etc.

## Related agents

- **contractor_outreach** — Enrolls active contractors in contractor_recruit SMS sequence. Calls hub /api/v1…
- **lead_scanner** — Reads radar_targets, parses address, dedup, writes to enriched_leads. Bounded by…
- **lead_enricher** — Placeholder. Would enrich enriched_leads with email, asset_value, ownership sign…
- **lead_converter** — Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enr…
- **lead_scorer** — Placeholder. Would score enriched_leads on urgency × asset_value × likelihood. N…
- **retarget** — Reactivates soft-reply sequences (NOT STOP, NOT YES-converted, NOT failed-send-h…
- **sms_qc** — QC: tier-1 gate_regression auto-remediates sequences with failed_send_count >= 3…
- **outreach** — Shared utilities for SMS sequence enrollment, voice scripts, and compliance chec…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
