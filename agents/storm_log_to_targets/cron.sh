#!/bin/bash
# Storm Log → Radar Targets — every 30 min at :25 (offset from other agents)
# Reads storm_risk_log and updates radar_targets with damage_severity and
# urgency_score for active storm-risk metros. Only upgrades — never downgrades.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.storm_log_to_targets 2>&1
