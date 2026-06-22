#!/bin/bash
# Mon/Thu 10:00 UTC — refresh discount offers (push 20% off to any pending fee
# that doesn't already have one, expire in 7d) and place AI voice calls to
# all contractors with a pending fee.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a

echo "=== $(date -u) — fee collection cycle ==="
echo "--- refresh discounts ---"
/usr/bin/python3 scripts/fee_settlement_discount.py --offer --days 7 --percent 20 --status || true

echo "--- place AI calls (skip fees called in last 48h) ---"
/usr/bin/python3 scripts/fee_collection_call.py --all 2>&1 || true

echo "--- push discount SMS (one per contractor, largest fee) ---"
/usr/bin/python3 scripts/push_discount_sms.py 2>&1 || true

echo "--- push email follow-up ---"
/usr/bin/python3 scripts/fee_collection_agent.py --follow-up --now 2>&1 | tail -5 || true

echo "=== cycle complete ==="