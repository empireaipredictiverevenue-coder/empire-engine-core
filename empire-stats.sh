#!/bin/bash
# ── empire-stats — one-command outreach template performance ──
# Usage:
#   empire-stats              → table view
#   empire-stats --json       → raw JSON
#   empire-stats --variant warehouse → single variant detail
#
# Reads HUB_TOKEN from /root/.env, talks to localhost:8000.

set -euo pipefail

HUB_URL="${EMPIRE_HUB_URL:-http://localhost:8000}"
ENDPOINT="/api/v1/outreach/template-stats"

# ── extract HUB_TOKEN safely ──────────────────────────────────────
TOKEN=$(python3 -c "
import os; from dotenv import load_dotenv
load_dotenv('/root/.env')
print(os.environ.get('HUB_TOKEN',''))
" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "✗ HUB_TOKEN not found in /root/.env" >&2
  exit 1
fi

# ── fetch ─────────────────────────────────────────────────────────
JSON=$(curl -s --max-time 10 "${HUB_URL}${ENDPOINT}?token=${TOKEN}" 2>/dev/null)

if [ -z "$JSON" ]; then
  echo "✗ No response from ${HUB_URL}${ENDPOINT}" >&2
  exit 1
fi

if ! echo "$JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'variants' in d else 1)" 2>/dev/null; then
  echo "✗ Auth failed or bad response:" >&2
  echo "$JSON" | python3 -m json.tool 2>/dev/null || echo "$JSON"
  exit 1
fi

# ── display ───────────────────────────────────────────────────────
MODE="${1:-}"

if [ "$MODE" = "--json" ]; then
  echo "$JSON" | python3 -m json.tool
  exit 0
fi

if [ "$MODE" = "--variant" ]; then
  VAR="${2:-}"
  echo "$JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
v = next((x for x in d.get('variants',[]) if x['template_variant']=='$VAR'), None)
if v:
    print(f\"\\n  Variant: {v['template_variant']}\")
    print(f\"  Total:   {v['total']}\")
    print(f\"  Email:   {v['email_sent']} sent  |  SMS: {v['sms_sent']} sent\")
    print(f\"  Replied: {v['replied']}  →  {v['reply_rate']*100:.1f}% reply rate\")
    print(f\"  Converted: {v['converted']}  →  {v['conversion_rate']*100:.1f}% conversion rate\")
    print()
else:
    print(f'  No data for variant: $VAR')
"
  exit 0
fi

# ── table view (default) ──────────────────────────────────────────
echo "$JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
vs = d.get('variants', [])

print()
print('═══ EMPIRE OUTREACH PERFORMANCE ═══')
print(f\"  Variants: {d.get('total_variants',0)}  |  Total: {d.get('total_outreach',0)}\")
print()
print(f\"  {'Variant':12s} {'Total':>5s}  {'Email':>5s}  {'SMS':>5s}  {'Replied':>8s}  {'Converted':>10s}  {'Reply %':>8s}  {'Conv %':>8s}\")
print(f\"  {'─'*12} {'─'*5}  {'─'*5}  {'─'*5}  {'─'*8}  {'─'*10}  {'─'*8}  {'─'*8}\")

for v in vs:
    print(f\"  {v['template_variant']:12s} {v['total']:5d}  {v['email_sent']:5d}  {v['sms_sent']:5d}  {v['replied']:8d}  {v['converted']:10d}  {v['reply_rate']*100:7.1f}%  {v['conversion_rate']*100:7.1f}%\")

tr = sum(v['replied'] for v in vs)
tc = sum(v['converted'] for v in vs)
tt = d.get('total_outreach', 1)
print(f\"  {'─'*12} {'─'*5}  {'─'*5}  {'─'*5}  {'─'*8}  {'─'*10}  {'─'*8}  {'─'*8}\")
print(f\"  {'TOTAL':12s} {tt:5d}  {'':5s}  {'':5s}  {tr:8d}  {tc:10d}  {tr/tt*100:7.1f}%  {tc/tt*100:7.1f}%\")
print()
"
