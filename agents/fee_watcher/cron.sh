#!/bin/bash
# Fee Watcher — every 6h on :55 (offset from other 6h agents)
# Polls for settled-claim events. Currently scaffolded: no claim source
# wired yet. Disabled by default. Enable once a claim event source is
# in place (webhook /api/v1/fee/claim-settled or polling a claim_events table).
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a
exec /usr/bin/python3 -m agents.fee_watcher 2>&1
