"""
EMPIRE V49 · SOVEREIGN SYNTHETIC MATRIX
========================================
Autonomous AGI endpoints for the Empire AI sovereign intelligence layer.
Runs as a standalone FastAPI service on port 8010.

Wires into: AGI Governor, SI Core (Bayesian), Self-Awareness Engine,
AGI Optimizer, Skills Framework, Hermes Protocol mesh.

ENDPOINTS
─────────
  GET  /api/v6/matrix/health           → Health check
  POST /api/v6/matrix/affiliate-hunter  → AI-drafted outreach to publishers
  POST /api/v6/matrix/buyer-locksmith   → Provision buyer + trigger media engine
  POST /api/v6/matrix/strategy-decide   → AGI Governor strategy decision
  POST /api/v6/matrix/self-aware        → Self-awareness snapshot
  POST /api/v6/matrix/niche-analyze     → SI Core Bayesian niche analysis
  POST /api/v6/matrix/regime-detect     → Revenue regime shift detection
  POST /api/v6/matrix/agi-optimize      → AGI weight optimization (real LLM)
"""

import os
import sys
import json
import http.client
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

log = logging.getLogger("empire.matrix.agi")

app = FastAPI(title="Empire_AI_Sovereign_Synthetic_Matrix", version="7.0.0")

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "data" / "growth_logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SOVEREIGN_LOG = LOGS_DIR / "sovereign_decisions.jsonl"

# ── Models ────────────────────────────────────────────────────────────
class AffiliateLead(BaseModel):
    publisher_name: str
    traffic_source: str
    contact_info: str
    estimated_daily_calls: int


class BuyerContract(BaseModel):
    buyer_company: str
    target_niche: str
    active_zip_codes: list
    cost_per_call_agreement: float


class StrategyDecideRequest(BaseModel):
    niche: str = ""
    context: dict = {}


class SelfAwareRequest(BaseModel):
    depth: str = "executive"  # "executive" | "detailed"


class NicheAnalyzeRequest(BaseModel):
    niche: str
    strategies: list = []  # [{name, wins, losses, revenue, opportunities}]
    opportunities: int = 10


class RegimeDetectRequest(BaseModel):
    recent_revenues: list  # [float, ...]
    historical_revenues: list  # [float, ...]
    niche: str = "default"
    threshold: float = 0.5


class AGIOptimizeRequest(BaseModel):
    stats: dict = {}


# ── Ollama Helper ─────────────────────────────────────────────────────
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "localhost")
_OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
_OLLAMA_MODEL = os.environ.get("OLLAMA_MATRIX_MODEL", "llama3:8b")


def _call_local_brain(system_rules: str, user_context: str) -> dict:
    """Call local Ollama with a structured prompt, expecting JSON response."""
    conn = http.client.HTTPConnection(_OLLAMA_HOST, _OLLAMA_PORT, timeout=30)
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_rules},
            {"role": "user", "content": user_context},
        ],
        "stream": False,
        "format": "json",
    }
    try:
        conn.request("POST", "/api/chat", json.dumps(payload), headers)
        res = conn.getresponse()
        raw = res.read().decode()
        data = json.loads(raw)
        content = data.get("message", {}).get("content", "{}")
        return json.loads(content)
    except Exception as e:
        log.warning(f"[matrix] Ollama call failed: {e}")
        return {"error": f"Local brain connection dropped: {str(e)}"}
    finally:
        conn.close()


# ── Logging helper ────────────────────────────────────────────────────
def _log_decision(endpoint: str, result: dict):
    """Append a sovereign decision to the JSONL log (async-safe)."""
    record = {
        "endpoint": endpoint,
        "result": result,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(SOVEREIGN_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as e:
        log.warning(f"[matrix] log write failed: {e}")


# ── Supabase helper ──────────────────────────────────────────────────
_supabase_client = None


def _get_supabase():
    """Lazy-init a cached Supabase client for self-aware and strategy queries."""
    global _supabase_client
    if _supabase_client is None:
        su_url = os.environ.get("SUPABASE_URL", "")
        su_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if su_url and su_key:
            from supabase import create_client as _cc
            _supabase_client = _cc(su_url, su_key)
        else:
            return None
    return _supabase_client


# ══════════════════════════════════════════════════════════════════════
# CORE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@app.get("/api/v6/matrix/health")
async def matrix_health():
    """Health check for the sovereign matrix."""
    return {
        "status": "OPERATIONAL",
        "service": "sovereign-synthetic-matrix",
        "version": "7.0.0",
        "capabilities": [
            "affiliate-hunter",
            "buyer-locksmith",
            "strategy-decide",
            "self-aware",
            "niche-analyze",
            "regime-detect",
            "agi-optimize",
        ],
    }


@app.post("/api/v6/matrix/affiliate-hunter", status_code=status.HTTP_201_CREATED)
async def process_autonomous_affiliate(payload: AffiliateLead):
    """Review publisher details and auto-generate an outreach pitch."""
    sys_rules = (
        "You are the Affiliate Director for Empire AI. Review the publisher details "
        "and generate an automated outreach response. Pitch our high pay-per-call payouts "
        "for roofing and solar campaigns. Focus on predictive revenue. "
        "Return a JSON object containing exactly one key: 'outreach_message'."
    )
    user_data = (
        f"Publisher: {payload.publisher_name} | "
        f"Source: {payload.traffic_source} | "
        f"Traffic: {payload.estimated_daily_calls} calls/day"
    )
    ai_decision = _call_local_brain(sys_rules, user_data)
    message_to_send = ai_decision.get(
        "outreach_message", "Let's scale your traffic. Connect with us."
    )

    record = {
        **payload.model_dump(),
        "ai_action_drafted": message_to_send,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(LOGS_DIR / "affiliates_matrix.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return {
        "status": "SUCCESS",
        "action_taken": "OUTREACH_DRAFTED",
        "draft": message_to_send,
    }


@app.post("/api/v6/matrix/buyer-locksmith", status_code=status.HTTP_201_CREATED)
async def process_autonomous_buyer(payload: BuyerContract):
    """Provision a new buyer: select target city and trigger media engine."""
    sys_rules = (
        "You are the Operations Director for Empire AI. A new buyer needs high-volume "
        "phone calls. Select the primary target city from their regional list and output "
        "a creative command string for our rendering machine. "
        "Return a JSON object with exactly one key: 'media_engine_command'."
    )
    user_data = (
        f"Company: {payload.buyer_company} | "
        f"Niche: {payload.target_niche} | "
        f"Covered Locations: {json.dumps(payload.active_zip_codes)}"
    )
    ai_decision = _call_local_brain(sys_rules, user_data)
    engine_cmd = ai_decision.get(
        "media_engine_command",
        f"Build a vertical {payload.target_niche} ad framework.",
    )

    # Trigger Sovereign Media Engine (port 8005)
    media_status = "MEDIA_ENGINE_OFFLINE"
    try:
        conn = http.client.HTTPConnection("localhost", 8005, timeout=10)
        headers = {"Content-Type": "application/json"}
        media_payload = {"command": engine_cmd}
        conn.request(
            "POST", "/api/v6/sovereign/deploy", json.dumps(media_payload), headers
        )
        res = conn.getresponse()
        media_status = res.status
    except Exception as e:
        log.warning(f"[matrix] media engine trigger failed: {e}")
    finally:
        conn.close()

    # Log the buyer provisioning
    record = {
        **payload.model_dump(),
        "engine_command": engine_cmd,
        "media_pipeline_status": media_status,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(LOGS_DIR / "buyers_matrix.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return {
        "status": "BUYER_PROVISIONED",
        "allocated_strategy": engine_cmd,
        "media_pipeline_trigger": media_status,
    }


# ══════════════════════════════════════════════════════════════════════
# AGI-POWERED ENDPOINTS (NEW — v7.0.0)
# ══════════════════════════════════════════════════════════════════════

@app.post("/api/v6/matrix/strategy-decide")
async def strategy_decide(payload: StrategyDecideRequest):
    """Use the AGI Governor to make a strategy decision for a niche.

    Calls governor.direct_strategy() for HOLD vs AGGRESSIVE_STRIKE,
    then queries the niche-specific SI strategy via strategy_for_niche().
    Also includes agent staleness check for safety.
    """
    niche = payload.niche or "default"
    context = payload.context or {}

    result = {
        "niche": niche,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        from empire_agi_governor import governor

        # 1. Staleness gate — safety check before any decision
        health = await asyncio.to_thread(governor.check_agent_staleness)
        stale_count = len(health.get("stale", []))
        result["stale_agents"] = [a["agent_name"] for a in health.get("stale", [])]
        result["stale_count"] = stale_count

        # 2. Global strategy direction
        global_strategy = await asyncio.to_thread(governor.direct_strategy)
        result["global_strategy"] = global_strategy

        # 3. Niche-specific strategy from SI evolution
        niche_strategy = await asyncio.to_thread(governor.strategy_for_niche, niche)
        result["niche_strategy"] = niche_strategy

        # 4. Niche win rate for context
        win_rate = await asyncio.to_thread(governor.get_niche_win_rate, niche)
        result["niche_win_rate"] = round(win_rate, 4)

        # 5. Determine final decision
        if stale_count > 0:
            result["decision"] = "HOLD"
            result["reason"] = f"{stale_count} stale agent(s) detected"
        elif global_strategy == "AGGRESSIVE_STRIKE" and win_rate > 0.2:
            result["decision"] = "AGGRESSIVE_STRIKE"
            result["reason"] = f"Niche win rate {win_rate:.1%} supports aggressive execution"
        elif win_rate > 0.0:
            result["decision"] = "CAUTIOUS_PROCEED"
            result["reason"] = f"Positive but unproven win rate ({win_rate:.1%})"
        else:
            result["decision"] = "EXPLORE"
            result["reason"] = "Insufficient outcome data — explore-first"

        # Feed context into the decision
        if context.get("urgency") == "high":
            result["decision"] = "AGGRESSIVE_STRIKE"
            result["reason"] += " | Urgency signal overrode caution"

        _log_decision("strategy-decide", result)

    except ImportError as e:
        result["error"] = f"AGI Governor unavailable: {e}"
        result["decision"] = "HOLD"
    except Exception as e:
        log.warning(f"[matrix] strategy-decide error: {e}")
        result["error"] = str(e)[:500]
        result["decision"] = "HOLD"

    return result


@app.post("/api/v6/matrix/self-aware")
async def self_aware(payload: SelfAwareRequest):
    """Query the Self-Awareness Engine for system state, anomalies, and recommendations.

    Returns the full self-awareness snapshot including agent health,
    lane performance, revenue state, anomaly detection, and self-improvement
    suggestions.
    """
    depth = payload.depth or "executive"

    try:
        from empire_self_awareness import SelfAwarenessEngine

        # Use cached Supabase client (lazy-init once, not per-request)
        db = _get_supabase()
        if db:
            def get_db():
                return db
        else:
            get_db = None

        engine = SelfAwarenessEngine(get_db=get_db)

        if depth == "detailed":
            snapshot = await asyncio.to_thread(engine.snapshot)
        else:
            snapshot = await asyncio.to_thread(engine.self_narrative, "executive")

        _log_decision("self-aware", {"depth": depth, "health": snapshot.get("overall_state", snapshot.get("health", {}).get("overall", "?"))[:120]})

        return {"status": "OK", "depth": depth, "snapshot": snapshot}

    except ImportError as e:
        return {"status": "ERROR", "error": f"Self-Awareness Engine unavailable: {e}"}
    except Exception as e:
        log.warning(f"[matrix] self-aware error: {e}")
        return {"status": "ERROR", "error": str(e)[:500]}


@app.post("/api/v6/matrix/niche-analyze")
async def niche_analyze(payload: NicheAnalyzeRequest):
    """Run full SI Core Bayesian analysis on a niche's strategies.

    Uses SyntheticIntelligence.analyze_niche() which performs:
      - Beta-Binomial Bayesian win rate estimation
      - Thompson sampling for explore/exploit balance
      - Expected revenue with propagated confidence intervals
      - Probability calibration (Platt scaling)
      - Best strategy recommendation

    Strategies format: [{name, wins, losses, revenue, opportunities}]
    """
    niche = payload.niche
    strategies = payload.strategies or []
    opportunities = payload.opportunities or 10

    try:
        from empire_si_core import get_si_core

        si = get_si_core()

        if not strategies:
            # Auto-populate from knowledge base if available
            result = {
                "niche": niche,
                "strategies": [],
                "best_strategy": None,
                "best_score": 0,
                "niche_win_rate": {"mean": 0.5, "note": "no_data"},
                "niche_expected_revenue": {"expected": 0, "note": "no_strategies_provided"},
                "total_trials": 0,
            }
        else:
            # Inject opportunities into each strategy
            for s in strategies:
                s.setdefault("opportunities", opportunities)

            result = si.analyze_niche(niche, strategies)

        _log_decision("niche-analyze", {
            "niche": niche,
            "strategy_count": len(strategies),
            "best": result.get("best_strategy"),
        })

        return {"status": "OK", "analysis": result}

    except ImportError as e:
        return {"status": "ERROR", "error": f"SI Core unavailable: {e}"}
    except Exception as e:
        log.warning(f"[matrix] niche-analyze error: {e}")
        return {"status": "ERROR", "error": str(e)[:500]}


@app.post("/api/v6/matrix/regime-detect")
async def regime_detect(payload: RegimeDetectRequest):
    """Detect revenue regime shifts between two time windows.

    Uses SI Core's detect_regime_shift() which:
      - Fits Gamma distributions to recent and historical revenue
      - Computes KL divergence between the distributions
      - Flags regime shifts when KL > threshold
      - Provides recommendations: invest, conserve, or monitor
    """
    try:
        from empire_si_core import detect_regime_shift

        recent = payload.recent_revenues or []
        historical = payload.historical_revenues or []
        threshold = payload.threshold if payload.threshold is not None else 0.5

        shift = detect_regime_shift(recent, historical, threshold)

        _log_decision("regime-detect", {
            "niche": payload.niche,
            "detected": shift.get("regime_shift_detected", False),
            "recommendation": shift.get("recommendation", "?"),
        })

        return {
            "status": "OK",
            "niche": payload.niche or "default",
            "analysis": shift,
        }

    except ImportError as e:
        return {"status": "ERROR", "error": f"SI Core unavailable: {e}"}
    except Exception as e:
        log.warning(f"[matrix] regime-detect error: {e}")
        return {"status": "ERROR", "error": str(e)[:500]}


@app.post("/api/v6/matrix/agi-optimize")
async def agi_optimize(payload: AGIOptimizeRequest):
    """Run the AGI Optimizer for real LLM-driven weight tuning.

    Uses empire_agi.agi_optimize_priorities() which calls the AI Router
    (Llama 3.2 3b) to suggest weight adjustments based on:
      - Revenue pulse
      - Conversion rate
      - Proxy health
      - Lead velocity

    Returns the new optimized weight (clamped to [0.5, 2.0]) with reasoning.
    """
    stats = payload.stats or {}

    try:
        from empire_agi import agi_optimize_priorities

        result = await agi_optimize_priorities(stats)

        _log_decision("agi-optimize", {
            "weight": result.get("new_weight", 1.25),
            "reasoning": result.get("reasoning", "")[:120],
        })

        return {"status": "OK", "optimization": result}

    except ImportError as e:
        return {"status": "ERROR", "error": f"AGI Optimizer unavailable: {e}"}
    except Exception as e:
        log.warning(f"[matrix] agi-optimize error: {e}")
        return {"status": "ERROR", "error": str(e)[:500]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8010)
