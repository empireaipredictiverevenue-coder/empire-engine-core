#!/bin/bash
# prospector_bridge cron wrapper.
# Reads prospects, writes contractors, marks prospects as bridged.
# Designed to run on a heartbeat cadence (e.g. hourly) AFTER the
# other agent's prospector has had a chance to populate prospects.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.prospector_bridge 2>&1
