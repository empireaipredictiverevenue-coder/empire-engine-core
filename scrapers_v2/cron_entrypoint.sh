#!/bin/bash
set -e
source /root/.env
cd /root/empire-v49/scrapers_v2
PYTHONPATH=. python3 main.py
