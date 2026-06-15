#!/bin/bash
# Warp Scout — every 6h on :50 (offset from other 6h agents)
# Queries NOAA Storm Prediction Center for per-metro storm risk (day 1-3)
# Writes history to storm_risk_log, logs to agent_activity.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /root/sniper_env/bin/python3 -m agents.warp_scout 2>&1
