---
title: Empire AI Agent Fleet Index
last_updated: 2026-06-15
audience: operators
---

# Empire AI Agent Fleet

Empire AI runs a fleet of 19 agents on a 6-hour cron cycle. Each agent
is documented in its own README.md (in this directory or in
agents/<name>/README.md). This index is the entry point.

## Quick state

| Metric                | Value                                                   |
|-----------------------|---------------------------------------------------------|
| Agents in cron        | 11                                                      |
| Agents scaffolded     | 6 (lead_enricher, lead_scorer, contact_discovery, ugly_banner, backlinks, fee_watcher) |
| Agents in production  | 11 (prospector, prospector_bridge, contractor_outreach, lead_scanner, lead_converter, warp_scout, retarget, sms_qc, dispatch, ab_monitor, outreach) |
| Agents disabled       | 1 (settled_claim_monitor — dev-only mock)               |
| Stubs / patterns      | 1 (carrier_adapters.py)                                 |
| Cadence               | 6h on :05, :07, :10, :20, :25, :30, :50, :52, :55 + hub minute-tick for dispatch |

## The chain at a glance

```
[1] prospector (5 metros × 5 niches Google Places)
        ↓ writes
   prospects
        ↓
[2] prospector_bridge (dedup by phone)
        ↓ writes
   contractors
        ↓
[3] contractor_outreach (SMS sequence enrollment)
        ↓ writes
   sms_sequences (contractor_recruit)
        ↓
[4] warp_scout (storm forecasts → storm_risk_log, no actions)
        ↓
[5] lead_scanner (radar_targets → enriched_leads)
        ↓
[6] lead_converter (enriched_leads → storm_strike sequences, A/B)
        ↓
[7] dispatcher (inbound SMS YES → matching contractor)
        ↓
[8] sms_qc (sequence auto-remediation)
        ↓
[9] retarget (soft-reply reactivation, 30d cooldown, idle)
        ↓
[10] ab_monitor (A/B reply-rate polling)
        ↓
[11] settled_claim_monitor (DISABLED in production)
        ↓
[12] fee_watcher (manual trigger only, dry-run)
```

## Cron schedule (every 6h)

| :MM  | Agent                  | What it does                          |
|------|------------------------|----------------------------------------|
| :05  | prospector             | New prospects (Google Places)         |
| :07  | retarget               | Soft-reply reactivation               |
| :10  | prospector_bridge      | Prospects → contractors               |
| :20  | lead_scanner           | Radar targets → enriched leads        |
| :25  | lead_enricher          | (dry-run, scaffolded)                 |
| :30  | lead_converter         | Leads → storm_strike sequences        |
| :50  | warp_scout             | Storm forecasts                       |
| :52  | ab_monitor             | A/B test reply-rate polling           |
| :55  | sms_qc                 | Tier-1 gate regression                |
| :55  | fee_watcher            | (dry-run, manual trigger only)        |
| 1m   | dispatch (in hub)      | Inbound YES → contractor              |
| 4h   | contractor_outreach    | Contractors → contractor_recruit       |

## Per-agent entry points

Each agent has a README.md with: status, schedule, tables touched,
how to run it manually, how to verify, common issues, related agents.

```
/root/empire-v49/agents/<name>/README.md
/root/empire-v49/<name>_README.md   (for top-level agents)
```

If you're new to the fleet, start with:

1. **prospector/README.md** — the data source, easy to understand
2. **lead_converter/README.md** — the A/B-tested outreach
3. **dispatch/README.md** — the inbound-YES handler
4. **fee_watcher/README.md** — the closed-loop monetization

## Where to look when something breaks

1. **Chain is slow** → `agents/contractor_outreach/README.md` (hub enroll is sequential)
2. **No SMS going out** → `agents/dispatch/README.md` (quiet hours) or check dispatcher logs
3. **No new leads** → `agents/prospector/README.md` (Google Places quota) or `agents/lead_scanner/README.md`
4. **Bad data in enriched_leads** → `agents/lead_scanner/README.md` (address parser issues)
5. **fee_events growing unexpectedly** → `agents/settled_claim_monitor_README.md` (it's dev-only)

## Operator commands

```bash
# ssh to box
ssh -i ~/.ssh/hermes_to_server root@5.78.148.141

# tail a log
tail -50 /root/empire-v49/logs/agent_<name>.log

# run an agent manually
set -a; . /root/.env; set +a
cd /root/empire-v49
/usr/bin/python3 -m agents.<name> 2>&1 | tail -20

# check recent runs
/root/sniper_env/bin/python3 -c "
from supabase import create_client
sb = create_client('\$SUPABASE_URL', '\$SUPABASE_SERVICE_KEY')
r = sb.table('agent_activity').select('agent_name,started_at,status,summary').order('started_at', desc=True).limit(20).execute()
for row in r.data: print(row)
"

# check current agent_config state
/root/sniper_env/bin/python3 -c "
from supabase import create_client
sb = create_client('\$SUPABASE_URL', '\$SUPABASE_SERVICE_KEY')
r = sb.table('agent_config').select('agent_name,enabled,dry_run,last_run_at,last_run_status').execute()
for row in r.data: print(row)
"
```

## Verifying the chain end-to-end

```sql
-- The full pipeline state
SELECT 'prospects' AS table, count(*) FROM prospects
UNION ALL SELECT 'contractors', count(*) FROM contractors
UNION ALL SELECT 'enriched_leads', count(*) FROM enriched_leads
UNION ALL SELECT 'radar_targets', count(*) FROM radar_targets
UNION ALL SELECT 'dispatches', count(*) FROM dispatches
UNION ALL SELECT 'fee_events', count(*) FROM fee_events
UNION ALL SELECT 'storm_strike active', count(*) FROM sms_sequences WHERE sequence_type='storm_strike' AND status='active'
UNION ALL SELECT 'contractor_recruit active', count(*) FROM sms_sequences WHERE sequence_type='contractor_recruit' AND status='active'
UNION ALL SELECT 'sms_log outbound today', count(*) FROM sms_log WHERE direction='outbound' AND created_at > current_date
UNION ALL SELECT 'sms_log inbound today', count(*) FROM sms_log WHERE direction='inbound' AND created_at > current_date;
```

## Locked metrics (from STARTING_POINT.md)

| # | Metric                               | Status |
|---|--------------------------------------|--------|
| 1 | splash deployed at empire-ai.co.uk   | ✅ |
| 2 | 1 real lead in Supabase              | ✅ (1200+ enriched_leads) |
| 3 | 1 real contractor recruited         | ✅ (1097 contractors in DB) |
| 4 | 1 real fee earned                    | ✅ (1 fee_event, $3,750, from a real dispatch + operator mark-settled) |

The metric is met by exactly 1 fee_event. The data is honest.
