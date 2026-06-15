---
name: prospector
status: live
schedule: */6 hours on :05
owner: STRIKER
last_verified: 2026-06-15
---

# prospector

## What it does

Scans Google Places for contractor and B2B-service businesses in
11 metros × 12 niches. Writes real businesses to the prospects table.

### Niche list (33)

Storm-response (5): roofing, restoration, water mitigation, general contractor, hvac
Storm-adjacent (5): gutter, solar installer, tree removal, emergency services, public insurance adjuster
B2B (2): managed it, staffing
Legal (5): personal injury lawyer, mass tort lawyer, class action lawyer, workers comp lawyer, medical malpractice lawyer
Insurance (3): medicare advantage agent, life insurance agent, final expense insurance
Financial (3): debt consolidation, business loan broker, mortgage broker
Senior care (2): assisted living, home health agency
Healthcare non-emergency (3): addiction treatment center, mental health clinic, medical alert system
Education (2): CDL truck driving school, nursing school
Commercial (2): commercial solar, commercial roofing
Debt (1): debt relief

Each niche uses a niche-aware search query suffix (NICHE_QUERY_SUFFIX
in bots/prospector.py) so the Google Places search is appropriate for
the niche — "gutter contractors" for storm-response, "managed it
companies" for b2b, "personal injury lawyer firms" for legal.

Note: this 33-niche list aligns with the 41-lane CPL model
(/api/v1/cpl/lanes) so that every lane has a corresponding
prospector run to feed it.

## When it runs

*/6 hours on :05

## What it touches

### Tables
  - `prospects`
  - `agent_config`
  - `agent_activity`

### Files
  - `bots/prospector.py`
  - `agents/prospector/prospector.py`
  - `config/metros.py`

## How to run it manually

```bash
# Load the env
set -a; . /root/.env; set +a

# Run the agent
cd /root/empire-v49
/usr/bin/python3 -m agents.prospector 2>&1 | tail -20
```

## How to check it worked

```sql
-- Recent runs for this agent
SELECT started_at, status, summary
FROM agent_activity
WHERE agent_name = 'prospector'
ORDER BY started_at DESC
LIMIT 5;
```

```sql
-- Current state
SELECT enabled, dry_run, last_run_at, last_run_status
FROM agent_config
WHERE agent_name = 'prospector';
```

## Common issues

- Dedup may produce 0 new saves if the well is dry. That's normal, not an error.
- Memphis/Atlanta/Nashville returned 0 before metros were added to config/metros.py.
- Quota: Google Places API has rate limits. If 429 errors appear, the prospector pauses and retries on the next cron.

## Related agents

- **prospector_bridge** — Reads top-N prospects and writes matching rows to contractors table. Dedup by ph…
- **contractor_outreach** — Enrolls active contractors in contractor_recruit SMS sequence. Calls hub /api/v1…
- **lead_scanner** — Reads radar_targets, parses address, dedup, writes to enriched_leads. Bounded by…
- **lead_converter** — Reads pending_outreach + pending_enrichment leads, picks channel + sequence, enr…
- **warp_scout** — Reads storm forecasts, writes per-run history to storm_risk_log. NTFY/Telegram p…
- **retarget** — Reactivates soft-reply sequences (NOT STOP, NOT YES-converted, NOT failed-send-h…
- **sms_qc** — QC: tier-1 gate_regression auto-remediates sequences with failed_send_count >= 3…
- **fee_watcher** — Scaffolded. Would poll for settled-claim events from the active carrier adapter.…
- **settled_claim_monitor** — Polls the mock carrier for open claims and randomly settles 30% of them. DEV-ONL…
- **carrier_adapters** — Abstract CarrierAdapter interface + 5 stub implementations (State Farm, Allstate…
- **ab_monitor** — Polls /api/v1/ab-test/results and logs to agent_activity. A/B test data accumula…

## Operator notes

_(free-form. add things you learn while operating this agent.)_
