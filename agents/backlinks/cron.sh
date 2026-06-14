#!/bin/bash
# Backlinks Agent cron — runs every 12 hours
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m bots.backlinks_agent 2>&1
