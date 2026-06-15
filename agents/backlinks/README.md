---
name: backlinks
status: scaffolded
schedule: none
owner: STRIKER
last_verified: 2026-06-15
---

# backlinks

## What it does

Placeholder. SEO/backlink monitoring agent. Not yet wired.

## When it runs

none

## What it touches

### Tables


### Files
  - `agents/backlinks/`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.backlinks 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'backlinks'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'backlinks';
```

## Common issues

- Scaffolded but not implemented.

## Related agents

_(none)_

## Operator notes

_(free-form. add things you learn while operating this agent.)_
