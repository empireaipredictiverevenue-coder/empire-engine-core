# Warp Scout Agent

Wrapper around `bots/storm_predictor.py` (the "Warp Scout"). Polls NOAA
Storm Prediction Center for severe-weather outlooks, scores each of 11
metros against the polygons, and writes per-run history to `storm_risk_log`.

## What it does

1. Calls `bots.storm_predictor.assess()` → list of {metro, day, risk_level, risk_rank, lat, lon}
2. Inserts one row per forecast into `storm_risk_log` (history table)
3. Logs to `agent_activity` (standard fleet pattern)
4. Updates `agent_config.last_run_at` / `last_run_status`
5. Pings Telegram (via ntfy) if any metro goes Slight+ (rank >= 4)

## Cron

```
# 10. Warp Scout — every 6h on :50 (offset from other 6h agents)
50 */6 * * * /bin/bash /root/empire-v49/agents/warp_scout/cron.sh >> /root/empire-v49/logs/agent_warp_scout.log 2>&1
```

## Usage

```bash
python3 -m agents.warp_scout           # one run (honors agent_config.dry_run)
python3 -m agents.warp_scout --dry-run # score and report, don't write
python3 -m agents.warp_scout --status  # last runs + risk log
```

## Config

`agent_config` row keyed `agent_name = "warp_scout"`:
- `enabled` (bool)
- `dry_run` (bool)
- `config_json.alert_below_rank` (int, default 4 = Slight)

## What it does NOT do

- Does not directly send SMS, dispatch leads, or modify the storm pipeline.
- Does not write to `storm_forecasts` (legacy single-row table from the
  original `while True` daemon). The new `storm_risk_log` table replaces
  it for per-run history.

## History

`bots/storm_predictor.py` was last touched 2026-05-30 and depended on
`python-dotenv` (not installed in the venv). This wrapper:
  - installs `python-dotenv` (one-time)
  - converts the `while True` daemon into a cron one-shot
  - adds per-run history (vs single-row upsert)
  - adds Telegram alert on Slight+ risk
