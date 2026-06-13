#!/bin/bash
# =============================================================================
# HOOK ENGINE MIGRATION AND DEPLOYMENT
# =============================================================================
# Registers the viral hook framework schema and starts the Trend Decider
# microservice on port 8046.
#
# Usage:
#   chmod +x scripts/deploy_hooks.sh
#   ./scripts/deploy_hooks.sh
# =============================================================================

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}"

echo "==> Constructing Hook Database Matrix..."
sqlite3 "${ROOT}/data/storm_alerts.sqlite" < "${ROOT}/database/hook_frameworks.sql"
echo "    Schema applied: viral_hook_formulas + incoming_trend_telemetry"

echo "==> Clearing duplicate hook engine instances..."
pkill -f "uvicorn hook_analytics:app" 2>/dev/null || true
sleep 1

echo "==> Activating Hook Trend Decision Controller on Port 8046..."
cd "${ROOT}"
nohup uvicorn hook_analytics:app \
    --host 0.0.0.0 \
    --port 8046 \
    --workers 2 \
    --log-level info \
    > "${LOG_DIR}/hook_matrix.log" 2>&1 &

echo "    PID: $!"
echo "    Log: ${LOG_DIR}/hook_matrix.log"

sleep 3

echo ""
echo "==> Testing Trend Decider with a high-intent Mass Tort sample pattern..."
curl -s -X POST "http://localhost:8046/api/v6/hooks/evaluate" \
    -H "Content-Type: application/json" \
    -d '{
      "niche_category": "mass_tort",
      "hook_text_detected": "Most operators are completely wrong about the new chemical hair straightener lawsuit.",
      "sample_size_videos": 18,
      "average_velocity_multiplier": 2.4
    }' | python3 -m json.tool

echo ""
echo "==> Verifying formula registry..."
curl -s "http://localhost:8046/api/v6/hooks/formulas" | python3 -m json.tool

echo ""
echo "==> Hook database and decision code pipelines are fully live."
