"""
EMPIRE V49 · SNIPER BRAIN BRIDGE
=================================
AGI/SI-driven dynamic configuration server for the Solana Meme Sniper Bot.

The Rust sniper bot polls /api/v1/sniper/dynamic-config every 5 seconds.
This server uses the AI Router (Ollama) to optimize sniper parameters based
on market conditions, wallet balance, and recent performance.

Run standalone:
    uvicorn empire_sniper_brain:app --host 0.0.0.0 --port 8055

Or register in hub.py for co-location:
    from empire_sniper_brain import register_sniper_brain_routes
    register_sniper_brain_routes(app, require_auth=require_auth)
"""

import os
import sys
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

sys.path.insert(0, "/root/empire-v49")

from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

log = logging.getLogger("empire.sniper.brain")

# ── Try to import AIRouter for LLM-driven config optimization ──────────
try:
    from empire_ai_router import AIRouter
    _HAS_ROUTER = True
except ImportError:
    _HAS_ROUTER = False
    log.warning("[sniper-brain] AIRouter not available — running in static mode")

# ── Try Supabase for wallet balance / perf stats ───────────────────────
try:
    from supabase import create_client
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
    _db = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None
except ImportError:
    _db = None


# ─────────────────────────────────────────────────────────────────────
# DEFAULT CONFIG
# ─────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG: Dict[str, Any] = {
    "min_risk_score": 40,
    "buy_amount_sol": 0.05,
    "jito_base_tip_sol": 0.005,
    "jito_max_tip_sol": 0.02,
    "copy_trade_sol": 0.1,
    "max_slippage_bps": 500,       # 5% slippage
    "market_mode": "balanced",     # aggressive | balanced | conservative
    "pause_sniping": False,
    "tracked_wallets": [],
    "generated_at": None,
    "generated_by": "static",
    "reasoning": "Default configuration (brain offline)",
}


# ─────────────────────────────────────────────────────────────────────
# LLM-DRIVEN CONFIG OPTIMIZATION
# ─────────────────────────────────────────────────────────────────────
SNIPER_OPTIMIZER_SYSTEM = """You are the AGI optimizer for a Solana meme coin sniper bot.

Your job: given current market conditions, wallet balance, and recent snipe
performance, return an optimized JSON configuration for the sniper bot.

Rules:
- min_risk_score (0-100): higher = safer. Conservative=60+, Balanced=40, Aggressive=20
- buy_amount_sol: SOL per snipe. Scale with wallet balance. Max 10% of balance per trade.
- jito_base_tip_sol: base Jito tip. 0.001-0.01 range.
- jito_max_tip_sol: max Jito tip. 2-5x base.
- copy_trade_sol: SOL per copy-trade. Same scaling rules as buy_amount.
- max_slippage_bps: basis points. 100=1%. Tight=100, Normal=500, Loose=1000.
- market_mode: "aggressive" (fast, high tips, low risk threshold) | "balanced" | "conservative" (slow, low tips, high risk threshold, only pump.fun)
- pause_sniping: true if wallet < 2x buy_amount + max_tip + rent, or if recent failure rate > 50%

Meme coin market context (Solana 2026):
- Pump.fun dominates new launches (80%+ volume)
- Jito tips: 0.005-0.01 SOL typical for fast inclusion
- Honeypot rate: ~40% of new tokens have freeze/mint authority
- Slippage: 500bps (5%) is normal for meme coins

Return ONLY valid JSON, no explanation outside the JSON."""


async def _optimize_with_llm(current_stats: dict) -> Dict[str, Any]:
    """Use the AI Router to generate an optimized sniper config."""
    if not _HAS_ROUTER:
        return {**DEFAULT_CONFIG, "generated_by": "static", "reasoning": "AIRouter unavailable"}

    router = AIRouter(get_db=(lambda: _db) if _db else None)

    prompt = f"""Current sniper bot state:
{json.dumps(current_stats, indent=2)}

Return an optimized sniper configuration as JSON with these exact keys:
min_risk_score, buy_amount_sol, jito_base_tip_sol, jito_max_tip_sol,
copy_trade_sol, max_slippage_bps, market_mode, pause_sniping, reasoning"""

    try:
        result = await router.generate_json(
            prompt=prompt,
            task="sniper.optimize",
            system=SNIPER_OPTIMIZER_SYSTEM,
            temperature=0.2,
            max_tokens=300,
            context=current_stats,
        )
    except Exception as e:
        log.warning(f"[sniper-brain] LLM call failed: {e}")
        return {**DEFAULT_CONFIG, "generated_by": "static", "reasoning": f"LLM error: {str(e)[:100]}"}

    if "_error" in result:
        log.warning(f"[sniper-brain] LLM returned error: {result.get('_error')}")
        return {**DEFAULT_CONFIG, "generated_by": "static", "reasoning": f"LLM error: {result.get('_error', 'unknown')[:100]}"}

    # ── Clamp values to safe ranges ──────────────────────────────────
    config = {
        "min_risk_score": max(10, min(80, int(result.get("min_risk_score", 40)))),
        "buy_amount_sol": max(0.01, min(1.0, float(result.get("buy_amount_sol", 0.05)))),
        "jito_base_tip_sol": max(0.001, min(0.05, float(result.get("jito_base_tip_sol", 0.005)))),
        "jito_max_tip_sol": max(0.002, min(0.2, float(result.get("jito_max_tip_sol", 0.02)))),
        "copy_trade_sol": max(0.01, min(1.0, float(result.get("copy_trade_sol", 0.1)))),
        "max_slippage_bps": max(50, min(2000, int(result.get("max_slippage_bps", 500)))),
        "market_mode": result.get("market_mode", "balanced"),
        "pause_sniping": bool(result.get("pause_sniping", False)),
        "tracked_wallets": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "agi",
        "reasoning": result.get("reasoning", "LLM-optimized")[:300],
    }

    # Validate market_mode
    if config["market_mode"] not in ("aggressive", "balanced", "conservative"):
        config["market_mode"] = "balanced"

    return config


# ─────────────────────────────────────────────────────────────────────
# STATS COLLECTOR
# ─────────────────────────────────────────────────────────────────────
def _collect_stats(sniper_state: Optional[dict] = None) -> dict:
    """Collect current sniper bot state for the LLM optimizer."""
    stats = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wallet_balance_sol": None,
        "recent_snipes_24h": 0,
        "recent_failures_24h": 0,
        "success_rate_pct": None,
        "current_market_sentiment": "neutral",
    }

    # Try to pull stats from Supabase
    if _db:
        try:
            r = _db.table("sniper_stats").select("*").order("created_at", desc=True).limit(1).execute()
            if r.data:
                row = r.data[0]
                stats["recent_snipes_24h"] = row.get("snipes_24h", 0)
                stats["recent_failures_24h"] = row.get("failures_24h", 0)
                stats["wallet_balance_sol"] = row.get("wallet_balance_sol")
                total = stats["recent_snipes_24h"] + stats["recent_failures_24h"]
                if total > 0:
                    stats["success_rate_pct"] = round(stats["recent_snipes_24h"] / total * 100, 1)
        except Exception:
            pass

    # Overlay with caller-provided state (from the Rust bot's last report)
    if sniper_state:
        stats.update(sniper_state)

    return stats


# ─────────────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="Empire AI · Sniper Brain Bridge", version="49.0.0")

# In-memory override (operator can set via POST)
_operator_override: Optional[Dict[str, Any]] = None
_override_expires_at: float = 0.0


@app.get("/api/v1/sniper/dynamic-config")
async def dynamic_config(
    wallet_balance_sol: Optional[float] = Query(None, description="Current wallet balance in SOL"),
    snipes_24h: int = Query(0, description="Snipes in last 24h"),
    failures_24h: int = Query(0, description="Failures in last 24h"),
    optimize: bool = Query(True, description="Run LLM optimization"),
):
    """Return the current dynamic sniper configuration.

    The Rust sniper bot polls this every 5 seconds. Query parameters
    provide real-time state from the bot for LLM-driven optimization.

    Response keys (all optional — Rust bot falls back to CLI/env defaults):
      min_risk_score, buy_amount_sol, jito_base_tip_sol, jito_max_tip_sol,
      copy_trade_sol, max_slippage_bps, market_mode, pause_sniping,
      tracked_wallets, generated_at, generated_by, reasoning
    """
    # ── Check for operator override ──────────────────────────────────
    if _operator_override and time.time() < _override_expires_at:
        config = dict(_operator_override)
        config["generated_by"] = "operator_override"
        config["generated_at"] = datetime.now(timezone.utc).isoformat()
        return JSONResponse(config)

    # ── Collect stats ────────────────────────────────────────────────
    sniper_state = {
        "wallet_balance_sol": wallet_balance_sol,
        "recent_snipes_24h": snipes_24h,
        "recent_failures_24h": failures_24h,
    }
    if snipes_24h + failures_24h > 0:
        sniper_state["success_rate_pct"] = round(snipes_24h / (snipes_24h + failures_24h) * 100, 1)

    stats = _collect_stats(sniper_state)

    # ── Generate config ──────────────────────────────────────────────
    if optimize and _HAS_ROUTER and (snipes_24h + failures_24h) > 0:
        config = await _optimize_with_llm(stats)

        # ── Blend AutoHedge genome risk management ──
        try:
            from bots.autohedge_genome import get_autohedge_genome
            ah = get_autohedge_genome()
            ah_config = ah.optimize_sniper_config(stats)
            # Blend: LLM config takes priority, AutoHedge fills gaps
            blended = False
            for key, val in ah_config.items():
                if key not in config or config[key] == DEFAULT_CONFIG.get(key):
                    config[key] = val
                    blended = True
            if blended:
                config["generated_by"] = "agi+autohedge"
                config["reasoning"] = (config.get("reasoning", "") + " | AutoHedge risk-adjusted")[:300]
        except Exception as e:
            log.warning(f"[sniper-brain] AutoHedge blend failed: {e}")
    else:
        config = dict(DEFAULT_CONFIG)
        config["generated_at"] = datetime.now(timezone.utc).isoformat()
        if not optimize:
            config["reasoning"] = "LLM optimization disabled by caller"
        elif not _HAS_ROUTER:
            config["reasoning"] = "AIRouter unavailable — static defaults"
        else:
            config["reasoning"] = "Insufficient data for optimization — using defaults"

    return JSONResponse(config)


@app.get("/api/v1/sniper/brain/health")
async def brain_health():
    """Health check for the sniper brain bridge."""
    return JSONResponse({
        "status": "ok",
        "brain_healthy": True,
        "router_available": _HAS_ROUTER,
        "db_available": _db is not None,
        "operator_override_active": bool(_operator_override and time.time() < _override_expires_at),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.post("/api/v1/sniper/brain/override")
async def set_override(request: Request):
    """Set an operator override for the sniper config.

    Body: any subset of config keys + optional ttl_seconds (default 300).
    The override takes precedence over LLM-generated config until TTL expires.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    global _operator_override, _override_expires_at

    ttl = max(10, min(3600, int(body.get("ttl_seconds", 300))))
    _override_expires_at = time.time() + ttl

    override = {}
    for key in DEFAULT_CONFIG:
        if key in body:
            override[key] = body[key]

    if not override:
        raise HTTPException(400, "No valid config keys provided")

    override["generated_by"] = "operator_override"
    _operator_override = override

    log.info(f"[sniper-brain] operator override set — expires in {ttl}s: {json.dumps(override)}")
    return JSONResponse({
        "ok": True,
        "override": override,
        "ttl_seconds": ttl,
        "expires_at": datetime.fromtimestamp(_override_expires_at, tz=timezone.utc).isoformat(),
    })


@app.delete("/api/v1/sniper/brain/override")
async def clear_override():
    """Clear any active operator override immediately."""
    global _operator_override, _override_expires_at
    _operator_override = None
    _override_expires_at = 0.0
    log.info("[sniper-brain] operator override cleared")
    return JSONResponse({"ok": True, "message": "Override cleared"})


# ─────────────────────────────────────────────────────────────────────
# HUB REGISTRATION (optional — for co-location with hub.py)
# ─────────────────────────────────────────────────────────────────────
def register_sniper_brain_routes(
    parent_app: FastAPI,
    *,
    require_auth=None,
):
    """Register sniper brain routes on the parent FastAPI app.

    When co-located with hub.py, the endpoints are mounted under
    the hub's auth middleware. Without auth, endpoints are public
    (the Rust bot polls without authentication).
    """
    # GET /api/v1/sniper/dynamic-config — public, polled by Rust bot
    @parent_app.get("/api/v1/sniper/dynamic-config")
    async def _dynamic_config_passthrough(
        wallet_balance_sol: Optional[float] = Query(None),
        snipes_24h: int = Query(0),
        failures_24h: int = Query(0),
        optimize: bool = Query(True),
    ):
        return await dynamic_config(
            wallet_balance_sol=wallet_balance_sol,
            snipes_24h=snipes_24h,
            failures_24h=failures_24h,
            optimize=optimize,
        )

    # POST /api/v1/sniper/brain/override — operator-only
    if require_auth:
        @parent_app.post("/api/v1/sniper/brain/override")
        async def _override_auth(request: Request, auth: bool = Depends(require_auth)):
            return await set_override(request)

        @parent_app.delete("/api/v1/sniper/brain/override")
        async def _clear_override_auth(auth: bool = Depends(require_auth)):
            return await clear_override()
    else:
        @parent_app.post("/api/v1/sniper/brain/override")
        async def _override_noauth(request: Request):
            return await set_override(request)

        @parent_app.delete("/api/v1/sniper/brain/override")
        async def _clear_override_noauth():
            return await clear_override()

    @parent_app.get("/api/v1/sniper/brain/health")
    async def _health_passthrough():
        return await brain_health()

    log.info("[sniper-brain] routes registered on parent app")


# ─────────────────────────────────────────────────────────────────────
# STANDALONE ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("SNIPER_BRAIN_PORT", "8055"))
    log.info(f"[sniper-brain] starting standalone on :{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
