#!/bin/bash
# b2b_scrape_watchdog — every 30 min, check if Google Places quota is open
# and fire b2b_lead_scraper if so. Self-disables after firing.
set -a
. /root/.env
set +a
cd /root/empire-v49
/usr/bin/python3 /root/empire-v49/agents/b2b_scrape_watchdog.py >> /root/empire-v49/logs/b2b_watchdog.log 2>&1
exit=$?
echo "exit=$exit at $(date -u +%FT%TZ)"
