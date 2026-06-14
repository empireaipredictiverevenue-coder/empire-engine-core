#!/bin/bash
# Contractor Outreach cron — runs every 4 hours
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.contractor_outreach 2>&1
