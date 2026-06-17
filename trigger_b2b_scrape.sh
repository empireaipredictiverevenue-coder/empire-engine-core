#!/bin/bash
# Trigger b2b_lead_scraper once. Re-runnable. Stops at Google's daily quota.
# USAGE: bash /root/empire-v49/trigger_b2b_scrape.sh
set -a
. /root/.env
set +a
export PLACES_DAILY_BUDGET=2000  # script-side cap; Google's project quota is the real gate
cd /root/empire-v49
/usr/bin/python3 -m bots.b2b_lead_scraper 2>&1 | tee -a /root/empire-v49/logs/b2b_lead_scraper.log
echo "exit=$?"
