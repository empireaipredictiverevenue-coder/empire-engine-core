#!/bin/bash
# Lead Scorer cron — runs every hour, classifies leads into hot/warm/cold
# and writes to the campaign_leads table for other campaign pipelines.
#
# Install in crontab:
#   0 * * * * /root/empire-v49/agents/lead_scorer/cron.sh >> /var/log/lead_scorer.log 2>&1
#
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.lead_scorer 2>&1
