#!/bin/bash
# test_card_checkout.sh — MoonPay Card Checkout E2E Test
# Usage: bash test_card_checkout.sh
# Tests: page render → payment creation → webhook → status → subscription activation
set -e

BASE="http://localhost:8001"
PASS=0
FAIL=0

green() { echo -e "\033[32m✓ $1\033[0m"; PASS=$((PASS+1)); }
red()   { echo -e "\033[31m✗ $1\033[0m"; FAIL=$((FAIL+1)); }

echo ""
echo "═══════════════════════════════════════════════════"
echo "  MOONPAY CARD CHECKOUT — END-TO-END TEST"
echo "  $(date -u +'%Y-%m-%d %H:%M UTC')"
echo "═══════════════════════════════════════════════════"
echo ""

# ── 1. Checkout page renders ───────────────────────────────────────────
echo "── Step 1: Checkout page renders ──"
for tier in MEETILY_PRO ALL_ACCESS SCRAPER_STARTER ROUTER_SaaS; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/checkout-card/$tier")
  if [ "$code" = "200" ]; then
    green "/checkout-card/$tier → $code"
  else
    red "/checkout-card/$tier → $code (expected 200)"
  fi
done

# Check that HTML has expected content
html=$(curl -s "$BASE/checkout-card/MEETILY_PRO")
if echo "$html" | grep -q "Pay with Card"; then
  green "Checkout page contains 'Pay with Card' tab"
else
  red "Checkout page missing 'Pay with Card' tab"
fi
if echo "$html" | grep -q "Pay with Crypto"; then
  green "Checkout page contains 'Pay with Crypto' fallback tab"
else
  red "Checkout page missing 'Pay with Crypto' tab"
fi

# ── 2. Create payment request ──────────────────────────────────────────
echo ""
echo "── Step 2: Create payment request ──"
PAYMENT=$(curl -s -X POST "$BASE/api/v1/crypto/pay" \
  -H "Content-Type: application/json" \
  -d '{"customer_email":"e2e-test@empire.ai","customer_account_id":"e2e_moonpay_test","tier_level":"MEETILY_PRO"}')

OK=$(echo "$PAYMENT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ok','false'))")
if [ "$OK" = "True" ]; then
  green "Payment request created successfully"
else
  red "Payment request failed: $(echo $PAYMENT | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','?'))")"
fi

MEMO=$(echo "$PAYMENT" | python3 -c "import sys,json; print(json.load(sys.stdin)['memo'])")
AMOUNT=$(echo "$PAYMENT" | python3 -c "import sys,json; print(json.load(sys.stdin)['amount_usdc'])")
PID=$(echo "$PAYMENT" | python3 -c "import sys,json; print(json.load(sys.stdin)['payment_id'])")
VAULT=$(echo "$PAYMENT" | python3 -c "import sys,json; print(json.load(sys.stdin)['vault_wallet'])")
echo "  memo: $MEMO  amount: $AMOUNT  pid: ${PID:0:12}..."

# Verify memo format (EMP-XXXXXX)
if [[ "$MEMO" =~ ^EMP-[A-Z0-9]{6}$ ]]; then
  green "Memo format valid: $MEMO"
else
  red "Memo format invalid: $MEMO (expected EMP-XXXXXX)"
fi

# ── 3. Simulate MoonPay webhook ─────────────────────────────────────────
echo ""
echo "── Step 3: Simulate MoonPay webhook (completed transaction) ──"
WEBHOOK_RESP=$(curl -s -X POST "$BASE/api/v1/moonpay/webhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"transaction_updated\",
    \"data\": {
      \"id\": \"e2e-tx-001\",
      \"status\": \"completed\",
      \"walletAddress\": \"$VAULT\",
      \"cryptoAmount\": $AMOUNT,
      \"currency\": \"usdc\",
      \"externalCustomerId\": \"$MEMO\",
      \"fromAddress\": \"11111111111111111111111111111111\"
    }
  }")

PROCESSED=$(echo "$WEBHOOK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('processed','false'))")
if [ "$PROCESSED" = "True" ]; then
  green "Webhook processed successfully"
else
  red "Webhook failed: $(echo $WEBHOOK_RESP)"
fi

# ── 4. Verify payment status = completed ───────────────────────────────
echo ""
echo "── Step 4: Verify payment status ──"
sleep 2
STATUS_RESP=$(curl -s "$BASE/api/v1/crypto/pay/$PID")
STATUS=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
if [ "$STATUS" = "completed" ] || [ "$STATUS" = "activation_pending" ]; then
  green "Payment status: $STATUS (completed or activation_pending is OK)"
else
  red "Payment status: $STATUS (expected completed or activation_pending)"
fi

# ── 5. Test idempotency — same webhook call should not crash ──────────
echo ""
echo "── Step 5: Idempotency test (call webhook again with same data) ──"
IDEM_RESP=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/v1/moonpay/webhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"transaction_updated\",
    \"data\": {
      \"id\": \"e2e-tx-001\",
      \"status\": \"completed\",
      \"walletAddress\": \"$VAULT\",
      \"cryptoAmount\": $AMOUNT,
      \"currency\": \"usdc\",
      \"externalCustomerId\": \"$MEMO\",
      \"fromAddress\": \"11111111111111111111111111111111\"
    }
  }")
if [ "$IDEM_RESP" = "200" ]; then
  green "Idempotency OK: second webhook returned $IDEM_RESP (no crash)"
else
  red "Idempotency FAIL: second webhook returned $IDEM_RESP (expected 200)"
fi

# ── 6. Test unknown tier → 404 ────────────────────────────────────────
echo ""
echo "── Step 6: Error handling tests ──"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/checkout-card/FAKE_TIER")
if [ "$code" = "404" ]; then
  green "Unknown tier → $code (expected 404)"
else
  red "Unknown tier → $code (expected 404)"
fi

# Test webhook with non-completed status (should not crash)
SKIP_RESP=$(curl -s -X POST "$BASE/api/v1/moonpay/webhook" \
  -H "Content-Type: application/json" \
  -d '{"data":{"status":"pending"}}')
SKIP_OK=$(echo "$SKIP_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('processed','?'), d.get('ok','?'))")
if echo "$SKIP_OK" | grep -q "False True"; then
  green "Non-completed webhook correctly skipped (processed=False, ok=True)"
else
  red "Non-completed webhook unexpected response: $SKIP_OK"
fi

# ── 7. Check MoonPay status endpoint ──────────────────────────────────
echo ""
echo "── Step 7: MoonPay status endpoint ──"
STATUS_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/v1/moonpay/status" \
  -H "Authorization: Bearer $(cat /root/.env | grep HUB_TOKEN | cut -d= -f2 | head -1)")
echo "  /api/v1/moonpay/status → $STATUS_CODE (401=no auth, 200=authed)"

# ── SUMMARY ────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo "  RESULTS: $PASS passed · $FAIL failed"
echo "═══════════════════════════════════════════════════"
echo ""

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
