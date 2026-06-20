#!/bin/bash
# Storm Alert — every 15 min (during storm season)
# Fetches NWS severe weather alerts, spatial-matches against radar_targets,
# updates damage_severity and urgency_score for targets in storm polygons.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.storm_alert 2>&1
