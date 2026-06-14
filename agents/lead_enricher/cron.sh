#!/bin/bash
# Lead Enricher cron — runs hourly, offset 5 min from scanner
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.lead_enricher 2>&1
