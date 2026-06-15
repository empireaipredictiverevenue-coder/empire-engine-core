---
name: outreach
status: live
schedule: internal (used by other agents)
owner: STRIKER
last_verified: 2026-06-15
---

# outreach

## What it does

Shared utilities for SMS sequence enrollment, voice scripts, and compliance checks. Not a standalone agent — imported by lead_converter, contractor_outreach, retarget.

## When it runs

internal (used by other agents)

## What it touches

### Tables
  - `sms_sequences`
  - `sms_log`
  - `sms_opt_outs`
  - `outreach_log`

### Files
  - `agents/outreach/sms_sequences.py`
  - `agents/outreach/voice_scripts.py`
  - `agents/outreach/compliance.py`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.outreach 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'outreach'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'outreach';
```

## Common issues

- TEMPLATES dict keyed by sequence_type: storm_strike, storm_strike_v2, contractor_recruit, b2b_outreach, etc.
- Compliance module: is_opted_out(phone), is_on_dnc(phone), record_send(phone). Caches values in memory.

## Related agents

- **contractor_outreach** — Enrolls active contractors in contractor_recruit SMS sequence. Calls hub /api/v1…
- **lead_converter** — Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enr…
- **retarget** — Reactivates soft-reply sequences (NOT STOP, NOT YES-converted, NOT failed-send-h…
- **sms_qc** — QC: tier-1 gate_regression auto-remediates sequences with failed_send_count >= 3…
- **dispatch** — Reads sms_log for inbound YES replies, looks up the lead (3-tier fallback: enric…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
