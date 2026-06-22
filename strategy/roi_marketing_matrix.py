"""
EMPIRE V49 · ROI & STRATEGY MATRIX
====================================
Financial margin engine. Calculates campaign ROI, triggers AI-based budget
adjustments when margins drop below threshold. Runs on port 8020.

ENDPOINTS
─────────
  POST /api/v6/strategy/roi-calc  → Calculate ROI, auto-adjust if needed
  GET  /api/v6/strategy/health    → Health check
"""

import os
import json
import http.client
import logging
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, status
from pydantic import BaseModel

log = logging.getLogger("empire.strategy.roi")

app = FastAPI(title="Empire_AI_ROI_and_Strategy_Matrix", version="6.0.0")

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "data" / "strategy_logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Models ────────────────────────────────────────────────────────────
class ROICalculatorInput(BaseModel):
    campaign_id: str
    ad_spend: float
    total_calls_generated: int
    buyer_payout_per_call: float
    closed_deals: int


class StrategyRequest(BaseModel):
    target_niche: str
    current_unverified_leads: int
    active_regions: list


# ── Ollama Helper ─────────────────────────────────────────────────────
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "localhost")
_OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
_OLLAMA_MODEL = os.environ.get("OLLAMA_STRATEGY_MODEL", "llama3.2:3b")


def _consult_synthetic_brain(system_rules: str, current_stats: str) -> dict:
    """Call local Ollama for strategic decisioning."""
    conn = http.client.HTTPConnection(_OLLAMA_HOST, _OLLAMA_PORT, timeout=30)
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_rules},
            {"role": "user", "content": current_stats},
        ],
        "stream": False,
        "format": "json",
    }
    try:
        conn.request("POST", "/api/chat", json.dumps(payload), headers)
        res = conn.getresponse()
        raw_data = json.loads(res.read().decode())
        content = raw_data.get("message", {}).get("content", "{}")
        return json.loads(content)
    except Exception as e:
        log.warning(f"[strategy] Ollama call failed: {e}")
        return {"error": f"Strategy core disconnected: {str(e)}"}
    finally:
        conn.close()


# ── Routes ────────────────────────────────────────────────────────────
@app.get("/api/v6/strategy/health")
async def strategy_health():
    """Health check for the ROI strategy matrix."""
    return {
        "status": "OPERATIONAL",
        "service": "roi-strategy-matrix",
        "version": "6.0.0",
    }


@app.post("/api/v6/strategy/roi-calc", status_code=status.HTTP_200_OK)
async def analyze_campaign_roi(payload: ROICalculatorInput):
    """Calculate campaign ROI. If below 30%, trigger AI budget adjustment."""
    revenue = payload.total_calls_generated * payload.buyer_payout_per_call
    net_profit = revenue - payload.ad_spend
    roi_percentage = (
        (net_profit / payload.ad_spend) * 100 if payload.ad_spend > 0 else 0.0
    )

    result = {
        "campaign_id": payload.campaign_id,
        "metrics": {
            "revenue": round(revenue, 2),
            "net_profit": round(net_profit, 2),
            "roi_pct": round(roi_percentage, 2),
            "closed_deals": payload.closed_deals,
            "calls_generated": payload.total_calls_generated,
        },
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    # If ROI is critically low, trigger AI budget maneuver
    if roi_percentage < 30.0:
        sys_rules = (
            "You are the Financial Commander for Empire AI. A campaign has a low ROI. "
            "Write an aggressive ad budget adjustment tactic. Keep it under two sentences. "
            "Return a JSON object with exactly one key: 'budget_maneuver'."
        )
        stats = (
            f"Campaign: {payload.campaign_id} | "
            f"Spend: ${payload.ad_spend} | "
            f"ROI: {roi_percentage}%"
        )
        ai_fix = _consult_synthetic_brain(sys_rules, stats)
        result["status"] = "OVERRIDE_ACTIVE"
        result["action"] = ai_fix
        log.info(
            f"[strategy] ROI override triggered for {payload.campaign_id}: "
            f"{roi_percentage}% — AI budget maneuver drafted"
        )
    else:
        result["status"] = "MARGINS_HEALTHY"

    # Persist to strategy log
    with open(LOGS_DIR / "roi_calculations.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8020)
