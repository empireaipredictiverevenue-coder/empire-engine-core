#!/bin/bash
# Contact Discovery cron — runs every 2 hours
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.contact_discovery 2>&1
