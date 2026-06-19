---
title: Empire AI Operator Runbook
last_updated: 2026-06-15
audience: operators
---

# Operator Runbook

This is the on-call runbook. When something is wrong, look here
first, then drill into the agent's README.

## Daily health check (5 min)

```bash
ssh -i ~/.ssh/hermes_to_server root@5.78.148.141
set -a; . /root/.env; set +a
/root/sniper_env/bin/python3 -c "
from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])

# 1. agent_config — what's enabled and what ran recently?
r = sb.table('agent_config').select('agent_name,enabled,dry_run,last_run_at,last_run_status').order('agent_name').execute()
print('=== agent_config ===')
for row in r.data:
    enabled = 'ON ' if row.get('enabled') else 'off'
    dry = 'dry ' if row.get('dry_run') else 'LIVE'
    last = (row.get('last_run_at') or 'never')[:19]
    status = row.get('last_run_status') or '-'
    print('  ' + row.get('agent_name','').ljust(22) + ' ' + enabled + ' ' + dry + ' ' + last + '  ' + status)

# 2. inbound today
r = sb.table('sms_log').select('id', count='exact').eq('direction','inbound').gte('created_at','2026-06-15T00:00:00+00:00').execute()
print('\\ninbound today: ' + str(r.count))
r = sb.table('sms_log').select('id', count='exact').eq('direction','outbound').gte('created_at','2026-06-15T00:00:00+00:00').execute()
print('outbound today: ' + str(r.count))

# 3. fee_events state
r = sb.table('fee_events').select('id', count='exact').execute()
print('fee_events total: ' + str(r.count))
"
```

What you should see:
- **outbound today:** 500-2000 SMS (we send in batches during quiet hours)
- **inbound today:** depends on reply window; 24-72h for organic YES
- **fee_events:** 1+ (the real one from operator mark-settled, no mock)
- **agent_config:** all agents either live or dry-run, no `last_run_status='error'`

## What to do when X is broken

### "no SMS going out"

1. Check quiet hours (the dispatcher doesn't send 9pm-8am Central):
   - `TZ=America/Chicago date '+%H:%M'`
   - If 21:00-08:00 Central, that's why.
2. Check the dispatcher is alive:
   - `pm2 logs empire-hub --lines 50` — look for "Dispatch running"
   - `curl http://127.0.0.1:8001/command` — HTTP 200 means it's up
3. Check sms_sequences:
   - Is `nsa < now()` for active sequences? If not, they need to be rescheduled.

### "no leads"

1. Check prospector last run: `agent_config.prospector.last_run_at` + `last_run_status`
2. If `last_run_status='ok'` but saved=0: well is dry, that's fine
3. If `last_run_status='error'`: check `summary` in agent_activity for the error
4. Check Google Places quota: if 429, the prospector pauses

### "no contractor_recruit replies"

1. Check sequences exist: `sms_sequences WHERE sequence_type='contractor_recruit' AND status='active'`
2. Check the dispatcher is actually running (`pm2 logs empire-hub`)
3. The 3% fee model is the hook. If it's not converting, the copy may be off. See `agents/contractor_outreach/README.md` for the template.

### "fee_events growing unexpectedly"

1. Check `source` field on the new rows. If `source='mock_carrier'`: settled_claim_monitor is somehow running. Disable it: `agent_config.settled_claim_monitor.enabled=false`
2. If `source='webhook_test'`: someone is testing the carrier webhook
3. If `source='operator_mark_settled'`: that's the real flow

### "hub is down"

1. `pm2 list` — is empire-hub online?
2. `pm2 logs empire-hub --lines 50` — what's the error?
3. `pm2 restart empire-hub` — restart it
4. If restarts keep incrementing: there's a code error, check the traceback

### "agent errors"

```sql
SELECT agent_name, started_at, status, error, summary
FROM agent_activity
WHERE status = 'error'
ORDER BY started_at DESC
LIMIT 20;
```

The `error` field has the short message. The `summary` has more context.

## How to add a new agent

1. Create `agents/<name>/__init__.py` and `agents/<name>/__main__.py`
2. Implement the agent with this skeleton:
   ```python
   # agents/<name>/agent.py
   from supabase import create_client
   import os
   import uuid
   from datetime import datetime, timezone

   def main():
       sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
       started_at = datetime.now(timezone.utc)
       run_id = str(uuid.uuid4())
       # ... do work ...
       # log to agent_activity
       sb.table('agent_activity').insert({
           'agent_name': '<name>',
           'run_id': run_id,
           'started_at': started_at.isoformat(),
           'finished_at': datetime.now(timezone.utc).isoformat(),
           'status': 'ok',  # or 'error'
           'rows_seen': 0,
           'rows_processed': 0,
           'rows_errored': 0,
           'error': None,
           'summary': '...',
       }).execute()
   ```
3. Add a `cron.sh` that loads env vars and runs the agent
4. Add to `agents/CRONTAB.fragment` with a unique :MM offset
5. Install the cron: `bash cron.sh` (it's idempotent)
6. Add a `README.md` following the format in `agents/prospector/README.md`
7. Add an entry to `agents/INDEX.md`

## How to onboard a new operator

1. Read `agents/INDEX.md` (one-page directory)
2. Read `agents/RUNBOOK.md` (this file)
3. Pick 3-4 agent READMEs to deep-read:
   - prospector, lead_converter, dispatch, fee_watcher
4. Run the daily health check
5. Watch `pm2 logs empire-hub` for an hour
6. Try running one agent manually (see "Operator commands" in INDEX.md)

## Safety rules

- **Never edit production code without a backup.** The `/root/empire-v49` directory is on a real server. The git history is the safety net.
- **Test dry-run first.** Every agent has a `dry_run` config flag. New agents should be `enabled=true, dry_run=true` for at least one full cycle before `dry_run=false`.
- **Watch the quiet-hours gate.** Real SMS doesn't go out 9pm-8am Central. If you see "0 sends" during that window, that's normal.
- **Don't fabricate data.** fee_events should only come from real claim settlements. Mock_carrier is dev-only and is disabled in production.
- **The predictive-revenue coder agent runs concurrently.** It has its own `corridor.py`, `empire_loop_agent.py`, `empire_command_spa.py` (the same file we edit), and matrix agents. It will sweep changes. Commit often.

## Recovery procedures

### "fee_events wiped"

Re-running /tmp/restore_fees.py is no longer the right call — that script re-creates mock_carrier rows. If real fee_events rows get deleted by an external process, the right recovery is to identify which rows are real (source=operator_mark_settled, source=webhook_test from a real carrier, etc.) and re-insert them manually via the operator mark-settled flow.

### "a cron broke the system"

The crontab lives on the box. Run `crontab -l` to see all entries. Each entry points to a `.sh` file with the agent command. Comment out a broken entry with `#` at the start of the line and re-run `crontab`.

### "I need to roll back a code change"

```bash
cd /root/empire-v49
git log --oneline | head -20   # find the bad commit
git revert <hash>             # create a new commit that undoes the bad one
git push                       # (no push, this is a local-only repo)
pm2 restart empire-hub        # the running process needs to reload
```

## Where to look for context

- `STARTING_POINT.md` — the locked metrics + business model
- `carrier_integration_landscape.txt` — research on real carrier integration paths
- `carrier_outreach_drafts/` — 5 ready-to-send emails to insurance carriers
- `operators/agents_INDEX.md` — wait, that's at /root/empire-v49/agents/INDEX.md
- `/root/empire-v49/.commit_msg*.txt` — git history has the full session log
