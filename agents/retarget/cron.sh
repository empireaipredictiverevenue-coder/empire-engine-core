#!/bin/bash
# Retarget agent cron wrapper.
# Walks replied sequences, re-enrolls soft-replies in a follow-up sequence.
# Conservative: once per source sequence, 30d window, no STOP, no already-active.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.retarget 2>&1
