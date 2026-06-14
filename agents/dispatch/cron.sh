#!/bin/bash
# Dispatch cron — runs every 5 min, picks up YES replies
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.dispatch 2>&1
