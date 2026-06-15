#!/bin/bash
# Prospector agent cron wrapper.
# Runs bots/prospector.py via the agent wrapper so the run is logged
# to agent_activity and agent_config is updated.
#
# The agent_config row's dry_run flag controls whether writes happen.
# This cron always runs; if dry_run=true, no DB writes.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.prospector 2>&1
