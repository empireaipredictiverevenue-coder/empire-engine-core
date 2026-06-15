---
name: lead_enricher
status: dry-run
schedule: */6 hours on :25
owner: STRIKER
last_verified: 2026-06-15
---

# lead_enricher

## What it does

Placeholder. Would enrich enriched_leads with email, asset_value, ownership signals. Not yet wired.

## When it runs

*/6 hours on :25

## What it touches

### Tables
  - `enriched_leads`

### Files
  - `agents/lead_enricher/`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.lead_enricher 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'lead_enricher'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'lead_enricher';
```

## Common issues

- Scaffolded but not implemented. The lead_converter currently writes leads with status=pending_enrichment, but the enricher doesn't run on those.

## Related agents

- **lead_scanner** — Reads radar_targets, parses address, dedup, writes to enriched_leads. Bounded by…
- **lead_converter** — Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enr…
- **lead_scorer** — Placeholder. Would score enriched_leads on urgency × asset_value × likelihood. N…
- **dispatch** — Reads sms_log for inbound YES replies, looks up the lead (3-tier fallback: enric…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
