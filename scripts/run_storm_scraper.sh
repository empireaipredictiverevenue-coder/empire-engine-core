#!/bin/bash
# Wrapper for the NWS storm scraper cron job.
# Runs every 12h (00:00 and 12:00). Idempotent. Logs to the standard log.
set -e
/root/sniper_env/bin/python3 /root/empire-v49/scripts/storm_scraper.py
