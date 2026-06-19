#!/bin/bash
# Fee Watcher — every 15 min on :05, :20, :35, :50
# Polls carrier_claims for settled claims → creates fee_events.
# Enabled Jun 2026 after carrier_claims auto-filing was wired in hub.py.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.fee_watcher 2>&1
