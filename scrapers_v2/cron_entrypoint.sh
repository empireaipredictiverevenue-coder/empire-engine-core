#!/bin/bash
set -e
source /root/.env
cd /root/empire-v49/scrapers_v2
mkdir -p logs
PYTHONPATH=. python3 main.py >> logs/scraper_cron.log 2>&1
