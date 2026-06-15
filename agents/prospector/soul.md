# Prospector Agent

Thin wrapper around `bots/prospector.py` (URL/contractor discovery via
Google Places) that logs each run to `agent_activity` and updates
`agent_config.last_run_at`.

This is the upstream half of the contractor-acquisition chain:

    bots/prospector.py   →   prospects   →   prospector_bridge   →   contractors
                                                                     ↓
                                                       contractor_outreach   →   sms_sequences

Without this agent, prospector_bridge finds nothing to bridge and
contractor_outreach finds nothing to recruit.

## Cron

```
# Every 6h, offset 5min from b2b_lead_scraper
5 */6 * * * /bin/bash /root/empire-v49/agents/prospector/cron.sh >> /root/empire-v49/logs/agent_prospector.log 2>&1
```

## Usage

```bash
# one run (honors agent_config.dry_run)
python3 -m agents.prospector

# force dry-run
python3 -m agents.prospector --dry-run

# last runs
python3 -m agents.prospector --status
```

## Config

`agent_config` row keyed `agent_name = "prospector"`:
- `enabled` (bool): master switch
- `dry_run` (bool): if true, no DB writes

The `bots/prospector.py` module handles metro / niche selection from
`config/metros.py` and `bots/prospector.NICHES`.
