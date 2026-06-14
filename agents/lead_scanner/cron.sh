#!/bin/bash
# Lead Scanner cron — runs hourly
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.lead_scanner 2>&1
