"""
PREDICITIVE TRADING BOT · MAIN ORCHESTRATOR
=============================================
Entry point for the standalone trading bot. Wires together:
  - Stop loss bot (background price monitoring + swap execution)
  - Trading skills (market analysis, indicators, meme scanning, etc.)
  - REST API (FastAPI server for position management)

Start the full stack:
  python3 trading_bot.py

Start only the stop loss monitor:
  python3 trading_bot.py --stoploss-only

Start only the REST API:
  python3 trading_bot.py --api-only

Start without API (monitor + CLI):
  python3 trading_bot.py --no-api
"""

import os
import sys
import json
import asyncio
import logging
import signal
from typing import Optional

try:
    import uvicorn
    HAS_UVICORN = True
except ImportError:
    HAS_UVICORN = False

try:
    from fastapi import FastAPI
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

from stoploss_bot import get_bot, StopLossBot

from fastapi import Depends, Header, HTTPException

try:
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    HAS_SECURITY = True
except ImportError:
    HAS_SECURITY = False
    HTTPBearer = None
    HTTPAuthorizationCredentials = None

log = logging.getLogger("trading.orchestrator")


# ── Skill Registration ─────────────────────────────────────────────────────


def register_skills() -> Optional[dict]:
    """Register all trading skills and strategies.

    Returns a dict with 'context', 'skill_names', 'strategy_registry',
    and 'strategy_names' keys, or None if unavailable.
    """
    try:
        from skills.base import SkillContext
        from skills.trading_skills import (
            TRADING_SKILL_CLASSES,
            get_trading_skill_names,
        )

        ctx = SkillContext()
        for cls in TRADING_SKILL_CLASSES:
            ctx.inject_skill(cls.name, cls())

        skill_names = get_trading_skill_names()
        log.info(f"[trading] registered {len(skill_names)} trading skills: {skill_names}")

        # Register strategies via their own registry
        strategy_names = []
        strategy_registry = None
        try:
            from skills.strategy import (
                StrategyRegistry,
                register_builtin_strategies,
                get_strategy_names,
            )
            strategy_registry = StrategyRegistry()
            register_builtin_strategies(strategy_registry)
            strategy_names = get_strategy_names()
            log.info(f"[trading] registered {len(strategy_names)} strategies: {strategy_names}")
        except ImportError:
            log.info("[trading] strategies not available")

        return {
            "context": ctx,
            "skill_names": skill_names,
            "strategy_registry": strategy_registry,
            "strategy_names": strategy_names,
        }
    except ImportError as e:
        log.warning(f"[trading] skills not available: {e}")
        return None
    except Exception as e:
        log.error(f"[trading] skill registration failed: {e}")
        return None


# ── FastAPI App ─────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    if not HAS_FASTAPI:
        raise RuntimeError("fastapi is required. Install with: pip install fastapi")

    from fastapi.responses import JSONResponse

    app = FastAPI(
        title="Predictive Trading Bot",
        version="1.0.0",
        description="Solana trading bot with stop loss monitoring, swap execution, and trading intelligence skills.",
    )

    # Register stop loss routes
    from stoploss_routes import register_stop_loss_routes
    register_stop_loss_routes(app)

    # Health check
    @app.get("/api/v1/health")
    async def health():
        bot = get_bot()
        status = await bot.status()
        return {
            "status": "ok",
            "service": "trading-bot",
            "stoploss": {
                "running": status["bot"]["running"],
                "live_enabled": status["bot"]["live_enabled"],
                "active_positions": status["positions"]["active"],
                "total_positions": status["positions"]["total"],
            },
        }

    # Skill + strategy listing — cached at module level
    _skills_cache = register_skills()

    @app.get("/api/v1/skills")
    async def list_skills():
        if _skills_cache:
            return {
                "ok": True,
                "skills": _skills_cache["skill_names"],
                "strategies": _skills_cache.get("strategy_names", []),
            }
        return {"ok": True, "skills": [], "strategies": [], "note": "Skills not loaded — check imports"}

    # ── Batch signal endpoint ────────────────────────────────────────

    _vector_engine = None

    def _get_vector_engine():
        nonlocal _vector_engine
        if _vector_engine is None and _skills_cache:
            try:
                from skills.vector_engine import VectorEngine
                registry = _skills_cache.get("strategy_registry")
                _vector_engine = VectorEngine(registry=registry)
                log.info(f"[trading] VectorEngine initialized with "
                         f"{len(_vector_engine.strategies)} strategies")
            except ImportError:
                log.warning("[trading] VectorEngine not available — numpy missing")
            except Exception as e:
                log.error(f"[trading] VectorEngine init failed: {e}")
        return _vector_engine

    @app.post("/api/v1/batch/signals")
    async def batch_signals(body: dict):
        """Run batch signal generation across multiple symbols.

        Request body:
            {
              "symbols": {
                "BTC/USD": [42000, 42100, ...],
                "ETH/USD": [2200, 2210, ...]
              },
              "indicators": ["RSI", "MACD", "MA", "BB"],  // optional
              "serialize": true  // optional, converts numpy → lists
            }

        Response:
            {
              "ok": true,
              "symbols": ["BTC/USD", "ETH/USD"],
              "signals": {
                "strategy.momentum": {
                  "action": [1, 0],
                  "confidence": [0.7, 0.5],
                  ...
                }
              },
              "meta": {"n_symbols": 2, "elapsed_ms": 0.4}
            }
        """
        engine = _get_vector_engine()
        if engine is None:
            return JSONResponse(
                {"ok": False, "error": "VectorEngine unavailable — numpy required"},
                status_code=503,
            )

        symbols_dict = body.get("symbols", {})
        if not symbols_dict:
            return JSONResponse(
                {"ok": False, "error": "Missing 'symbols' dict"}, status_code=400
            )

        indicator_names = body.get("indicators")
        result = engine.run(symbols_dict, indicators=indicator_names)

        # Serialize numpy arrays for JSON compatibility
        if body.get("serialize", True):
            serialized = engine.to_serializable(result)
            serialized["ok"] = True
            return serialized

        # Raw numpy mode (faster, but not JSON-safe — caller must handle)
        return JSONResponse(
            {"ok": True, "note": "serialize=false not supported via JSON — use serialize=true"},
            status_code=400,
        )

    @app.get("/api/v1/batch/benchmark")
    async def batch_benchmark(n: int = 10000, bars: int = 200):
        """Run a synthetic benchmark of the batch engine."""
        engine = _get_vector_engine()
        if engine is None:
            return JSONResponse(
                {"ok": False, "error": "VectorEngine unavailable"}, status_code=503
            )

        result = engine.run_benchmark(n_symbols=n, n_bars=bars)
        serialized = engine.to_serializable(result)
        serialized["ok"] = True
        return serialized

    log.info("[trading] FastAPI app created with stop loss + batch signal routes")

    # ── Public API endpoints ───────────────────────────────────────

    _user_store = None
    _bearer = HTTPBearer(auto_error=False) if HAS_SECURITY else None

    def _get_user_store():
        nonlocal _user_store
        if _user_store is None:
            from skills.public_api import get_user_store
            _user_store = get_user_store()
        return _user_store

    async def _require_auth(
        credentials: HTTPAuthorizationCredentials = Depends(_bearer) if _bearer else None,
        x_api_key: str = Header(None, alias="X-API-Key"),
    ) -> dict:
        """Authenticate via Bearer token or X-API-Key header."""
        api_key = None
        if credentials:
            api_key = credentials.credentials
        elif x_api_key:
            api_key = x_api_key

        if not api_key:
            raise HTTPException(401, "Missing API key — use Bearer token or X-API-Key header")

        if not api_key.startswith("emp_sk_"):
            raise HTTPException(401, "Invalid API key format")

        store = _get_user_store()
        user = await store.get_user_by_api_key(api_key)
        if not user:
            raise HTTPException(401, "Invalid or revoked API key")

        return {"user": user, "api_key": api_key}

    # ── Auth: challenge + verify ───────────────────────────────

    @app.post("/api/v1/auth/challenge")
    async def auth_challenge(body: dict):
        """Get a challenge nonce to sign with your Solana wallet.

        Body:
          wallet_pubkey: str (required) — Base58 Solana public key

        Response:
          nonce: hex string to sign (Ed25519)
          expires_in: seconds until expiry
        """
        wallet = (body.get("wallet_pubkey") or "").strip()
        if not wallet or len(wallet) < 32:
            return JSONResponse({"ok": False, "error": "Invalid wallet_pubkey"}, status_code=400)

        store = _get_user_store()
        nonce = await store.create_challenge(wallet)
        return {
            "ok": True,
            "nonce": nonce,
            "message": f"Sign this message to verify your wallet: {nonce}",
            "expires_in_sec": 300,
        }

    @app.post("/api/v1/auth/verify")
    async def auth_verify(body: dict):
        """Verify a signed challenge and get an API key.

        Body:
          wallet_pubkey: str (required) — Base58 Solana public key
          nonce: str (required) — The challenge nonce
          signature: str (required) — Base58 Ed25519 signature of nonce

        Response:
          api_key: your permanent API key (shown only once)
          tier: account tier
        """
        wallet = (body.get("wallet_pubkey") or "").strip()
        nonce = (body.get("nonce") or "").strip()
        signature = (body.get("signature") or "").strip()

        if not wallet or not nonce or not signature:
            return JSONResponse({"ok": False, "error": "wallet_pubkey, nonce, and signature required"}, status_code=400)

        store = _get_user_store()

        # Verify challenge
        expected_wallet = await store.consume_challenge(nonce)
        if not expected_wallet:
            return JSONResponse({"ok": False, "error": "Invalid or expired nonce"}, status_code=401)
        if expected_wallet != wallet:
            return JSONResponse({"ok": False, "error": "Wallet mismatch"}, status_code=401)

        # Verify signature
        from skills.public_api import verify_solana_signature
        if not verify_solana_signature(wallet, nonce, signature):
            return JSONResponse({"ok": False, "error": "Signature verification failed"}, status_code=401)

        # Register or return existing
        user_info = await store.register_user(wallet)
        return {"ok": True, **user_info}

    # ── User profile ───────────────────────────────────────────

    @app.get("/api/v1/user/profile")
    async def user_profile(auth: dict = Depends(_require_auth)):
        """Get your profile with drawdown stats, P&L, and positions."""
        store = _get_user_store()
        profile = await store.get_user_profile(auth["api_key"])
        return {"ok": True, **profile}

    @app.post("/api/v1/user/strategy-params")
    async def user_strategy_params(body: dict, auth: dict = Depends(_require_auth)):
        """Set your strategy parameter overrides."""
        store = _get_user_store()
        result = await store.update_strategy_params(auth["api_key"], body.get("params", {}))
        return {"ok": True, **result}

    @app.get("/api/v1/user/strategy-params")
    async def user_get_strategy_params(auth: dict = Depends(_require_auth)):
        """Get your strategy parameter overrides."""
        store = _get_user_store()
        params = await store.get_strategy_params(auth["api_key"])
        return {"ok": True, "params": params}

    # ── Exchange keys ──────────────────────────────────────────

    @app.post("/api/v1/user/exchange")
    async def user_add_exchange(body: dict, auth: dict = Depends(_require_auth)):
        """Connect exchange API keys (encrypted at rest).

        Body:
          exchange: str (required) — "binance", "bybit", "kraken", etc.
          api_key: str (required) — Exchange API key
          api_secret: str (required) — Exchange API secret
          passphrase: str (optional) — Exchange passphrase
          label: str (optional)
        """
        exchange = (body.get("exchange") or "").strip().lower()
        ex_api_key = (body.get("api_key") or "").strip()
        ex_secret = (body.get("api_secret") or "").strip()
        if not exchange or not ex_api_key or not ex_secret:
            return JSONResponse({"ok": False, "error": "exchange, api_key, api_secret required"}, status_code=400)

        store = _get_user_store()
        try:
            result = await store.store_exchange_keys(
                api_key=auth["api_key"],
                exchange=exchange,
                exchange_api_key=ex_api_key,
                exchange_api_secret=ex_secret,
                exchange_passphrase=body.get("passphrase", ""),
                label=body.get("label", ""),
            )
            return {"ok": True, **result}
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=401)

    @app.get("/api/v1/user/exchange")
    async def user_list_exchanges(auth: dict = Depends(_require_auth)):
        """List your connected exchange keys (secrets partially masked)."""
        store = _get_user_store()
        try:
            keys = await store.get_exchange_keys(auth["api_key"])
            return {"ok": True, "exchanges": keys}
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=401)

    @app.delete("/api/v1/user/exchange/{key_id}")
    async def user_delete_exchange(key_id: str, auth: dict = Depends(_require_auth)):
        """Delete a connected exchange key."""
        store = _get_user_store()
        try:
            ok = await store.delete_exchange_keys(auth["api_key"], key_id)
            return {"ok": ok, "key_id": key_id}
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=401)

    # ── Drawdown + take-profit tracking ────────────────────────

    @app.post("/api/v1/user/portfolio-value")
    async def user_update_portfolio(body: dict, auth: dict = Depends(_require_auth)):
        """Update your portfolio value for drawdown tracking.

        Body:
          value: float (required) — Current total portfolio value in USD
        """
        value = body.get("value")
        if value is None:
            return JSONResponse({"ok": False, "error": "value required"}, status_code=400)

        store = _get_user_store()
        try:
            result = await store.update_portfolio_value(auth["api_key"], float(value))
            return {"ok": True, **result}
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=401)

    @app.post("/api/v1/user/position")
    async def user_add_position(body: dict, auth: dict = Depends(_require_auth)):
        """Add a tracked position with stop-loss and take-profit.

        Body:
          symbol: str (required)
          entry_price: float (required)
          amount: float (required)
          stop_loss_pct: float (optional, default 0.05)
          take_profit_pct: float (optional)
          side: str (optional, "long" or "short", default "long")
        """
        symbol = (body.get("symbol") or "").strip()
        entry = body.get("entry_price")
        amount = body.get("amount")
        if not symbol or entry is None or amount is None:
            return JSONResponse({"ok": False, "error": "symbol, entry_price, amount required"}, status_code=400)

        store = _get_user_store()
        try:
            result = await store.add_position(
                api_key=auth["api_key"],
                symbol=symbol,
                entry_price=float(entry),
                amount=float(amount),
                stop_loss_pct=float(body.get("stop_loss_pct", 0.05)),
                take_profit_pct=float(body["take_profit_pct"]) if body.get("take_profit_pct") else None,
                side=body.get("side", "long"),
            )
            return {"ok": True, **result}
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=401)

    @app.post("/api/v1/user/position/{pos_id}/price")
    async def user_update_position_price(
        pos_id: str, body: dict, auth: dict = Depends(_require_auth)
    ):
        """Update a position's current price (triggers stop-loss/take-profit checks).

        Body:
          price: float (required) — Current market price
        """
        price = body.get("price")
        if price is None:
            return JSONResponse({"ok": False, "error": "price required"}, status_code=400)

        store = _get_user_store()
        try:
            result = await store.update_position_price(auth["api_key"], pos_id, float(price))
            return {"ok": True, **result}
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=401)

    @app.post("/api/v1/user/position/{pos_id}/close")
    async def user_close_position(
        pos_id: str, body: dict, auth: dict = Depends(_require_auth)
    ):
        """Manually close a position at a given price.

        Body:
          price: float (required) — Closing price
        """
        price = body.get("price")
        if price is None:
            return JSONResponse({"ok": False, "error": "price required"}, status_code=400)

        store = _get_user_store()
        try:
            result = await store.close_position(auth["api_key"], pos_id, float(price))
            return {"ok": True, **result}
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=401)

    # ── Personalized batch signals ──────────────────────────────

    @app.post("/api/v1/user/signals")
    async def user_signals(body: dict, auth: dict = Depends(_require_auth)):
        """Get personalized batch trading signals using your strategy params.

        Body:
          symbols: {"BTC/USD": [prices...], "ETH/USD": [prices...]} (required)
          indicators: ["RSI", "MACD", ...] (optional)
        """
        symbols_dict = body.get("symbols", {})
        if not symbols_dict:
            return JSONResponse({"ok": False, "error": "Missing 'symbols' dict"}, status_code=400)

        engine = _get_vector_engine()
        if engine is None:
            return JSONResponse({"ok": False, "error": "VectorEngine unavailable"}, status_code=503)

        # Apply user's strategy param overrides (save/restore to prevent cross-user contamination)
        store = _get_user_store()
        user_params = await store.get_strategy_params(auth["api_key"])
        saved_params = []
        if user_params:
            for strategy in engine.strategies:
                saved = {}
                for key, val in user_params.items():
                    if key in strategy.parameters:
                        saved[key] = strategy.parameters[key]
                        strategy.parameters[key] = val
                saved_params.append((strategy, saved))

        try:
            indicator_names = body.get("indicators")
            result = engine.run(symbols_dict, indicators=indicator_names)
            serialized = engine.to_serializable(result)
        except Exception as e:
            log.error(f"[trading] user signals batch failed: {e}")
            return JSONResponse(
                {"ok": False, "error": f"Batch engine failed: {e}"},
                status_code=500,
            )
        finally:
            # Restore original parameters (even on error)
            for strategy, saved in saved_params:
                for key, val in saved.items():
                    strategy.parameters[key] = val

        serialized["ok"] = True
        serialized["user_params_applied"] = bool(user_params)
        return serialized

    # ── Public health + stats ──────────────────────────────────

    @app.get("/api/v1/public/stats")
    async def public_stats():
        """Public platform statistics (no auth required)."""
        store = _get_user_store()
        count = await store.user_count()
        return {
            "ok": True,
            "users": count,
            "strategies": len(_skills_cache["strategy_names"]) if _skills_cache else 0,
            "uptime": "operational",
        }

    log.info("[trading] public API endpoints registered")

    # ── WebSocket endpoint ────────────────────────────────────────

    @app.websocket("/ws/user")
    async def ws_user(websocket, api_key: str = ""):
        """Real-time WebSocket for position price updates and SL/TP alerts.

        Connect with:  ws://host:8050/ws/user?api_key=emp_sk_...

        Client → Server messages:
          {"type": "subscribe_positions"}  — start streaming position prices
          {"type": "unsubscribe_positions"} — stop streaming
          {"type": "ping"}                 — keep-alive

        Server → Client messages:
          {"type": "connected", ...}       — welcome
          {"type": "positions_snapshot", ...} — current open positions
          {"type": "price_update", ...}    — per-position price + drawdown
          {"type": "alert", ...}           — stop_loss / take_profit triggered
          {"type": "pong"}                — keep-alive response
        """
        from skills.websocket_manager import get_ws_manager

        await websocket.accept()

        # Auth: validate API key
        if not api_key or not api_key.startswith("emp_sk_"):
            await websocket.send_text(json.dumps({
                "type": "error", "message": "Valid api_key query parameter required"
            }))
            await websocket.close(code=4001)
            return

        store = _get_user_store()
        user = await store.get_user_by_api_key(api_key)
        if not user:
            await websocket.send_text(json.dumps({
                "type": "error", "message": "Invalid API key"
            }))
            await websocket.close(code=4001)
            return

        user_hash = user["api_key_hash"]
        ws_manager = get_ws_manager()
        await ws_manager.connect(user_hash, websocket)

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({
                        "type": "error", "message": "Invalid JSON"
                    }))
                    continue

                await ws_manager.handle_message(user_hash, api_key, websocket, message)
        except Exception:
            pass
        finally:
            await ws_manager.disconnect(user_hash, websocket)

    log.info("[trading] WebSocket endpoint registered")
    return app


# ── Main Orchestrator ──────────────────────────────────────────────────────


async def run_api(app: FastAPI, host: str, port: int):
    """Run the FastAPI server."""
    if not HAS_UVICORN:
        log.error("uvicorn is required for API mode. Install with: pip install uvicorn")
        return

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    log.info(f"[trading] API starting on {host}:{port}")
    await server.serve()


async def run_stoploss(bot: StopLossBot):
    """Run the stop loss monitoring loop."""
    log.info("[trading] stop loss monitor starting")
    await bot.run_loop()


async def main(
    *,
    api_host: str = "0.0.0.0",
    api_port: int = 8050,
    stoploss_only: bool = False,
    api_only: bool = False,
    no_api: bool = False,
):
    """Main orchestrator entry point."""
    log.info("=" * 60)
    log.info("[trading] PREDICITIVE TRADING BOT v1.0.0")
    log.info("=" * 60)

    bot = get_bot()

    # Register skills (informational only — doesn't affect stop loss loop)
    skills = register_skills()
    if skills:
        log.info(f"[trading] {len(skills['skill_names'])} skills available")
    else:
        log.info("[trading] running without skills (stop loss only)")

    tasks = []

    if api_only:
        if not HAS_FASTAPI:
            log.error("fastapi not installed — cannot run API-only mode")
            return
        app = create_app()
        log.info(f"[trading] API-only mode on {api_host}:{api_port}")
        await run_api(app, api_host, api_port)
        return

    if stoploss_only or no_api:
        if stoploss_only:
            log.info("[trading] stop loss-only mode")
        else:
            log.info("[trading] monitor + CLI mode (no API)")
        await run_stoploss(bot)
        return

    # Full stack: API + stop loss monitor
    if not HAS_FASTAPI:
        log.warning("fastapi not installed — falling back to stop loss-only mode")
        await run_stoploss(bot)
        return

    app = create_app()
    log.info(f"[trading] full stack: API on {api_host}:{api_port} + stop loss monitor")

    api_task = asyncio.create_task(run_api(app, api_host, api_port))
    stoploss_task = asyncio.create_task(run_stoploss(bot))

    done, pending = await asyncio.wait(
        [api_task, stoploss_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # If one task finishes, cancel the other
    for task in pending:
        task.cancel()

    for task in done:
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[trading] task error: {e}")


# ── CLI ─────────────────────────────────────────────────────────────────────


def _print_usage():
    print("Usage: python3 trading_bot.py [FLAGS]")
    print()
    print("Flags:")
    print("  --stoploss-only    Run only the stop loss monitor (no API)")
    print("  --api-only         Run only the REST API server (no monitor)")
    print("  --no-api           Run monitor without API (interactive CLI)")
    print("  --host HOST        API bind host (default: 0.0.0.0)")
    print("  --port PORT        API bind port (default: 8050)")
    print()
    print("Default (no flags): Run full stack (API + stop loss monitor)")
    print()
    print("Environment:")
    print("  STOPLOSS_WALLET_PRIVATE_KEY   Base58-encoded 64-byte Ed25519 private key")
    print("  SOLANA_RPC_URL                Solana RPC endpoint")
    print("  STOPLOSS_INTERVAL_SEC         Price check interval (default: 15)")
    print("  HELIUS_API_KEY                Helius RPC API key (for trading skills)")
    print("  BIRDEYE_API_KEY               Birdeye API key (for trading skills)")
    print("  JUPITER_API_KEY               Jupiter API key")
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if "--help" in sys.argv or "-h" in sys.argv:
        _print_usage()

    stoploss_only = "--stoploss-only" in sys.argv
    api_only = "--api-only" in sys.argv
    no_api = "--no-api" in sys.argv

    host = "0.0.0.0"
    port = 8050

    if "--host" in sys.argv:
        idx = sys.argv.index("--host")
        if idx + 1 < len(sys.argv):
            host = sys.argv[idx + 1]

    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])

    # Handle graceful shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _handle_sigterm():
        log.info("[trading] received SIGTERM — shutting down")
        get_bot().stop()
        loop.stop()

    try:
        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
    except NotImplementedError:
        pass

    try:
        loop.run_until_complete(
            main(
                api_host=host,
                api_port=port,
                stoploss_only=stoploss_only,
                api_only=api_only,
                no_api=no_api,
            )
        )
    except KeyboardInterrupt:
        log.info("[trading] received interrupt — shutting down")
        get_bot().stop()
    finally:
        loop.close()
