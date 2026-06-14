#!/bin/bash
# Lead Converter cron — runs every 30 min
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.lead_converter 2>&1
