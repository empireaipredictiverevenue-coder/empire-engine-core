#!/bin/bash
# A/B Monitor — every 6h on :55 (just before fee_watcher at :55 too)
# Pulls the A/B reply-rate comparison and logs to agent_activity.
# Operator SPA can chart this over time.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /root/sniper_env/bin/python3 /root/empire-v49/agents_ab_monitor.py 2>&1
