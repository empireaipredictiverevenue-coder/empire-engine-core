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

log = logging.getLogger("trading.orchestrator")


# ── Skill Registration ─────────────────────────────────────────────────────


def register_skills() -> Optional[dict]:
    """Register all trading skills into a SkillContext.

    Returns the context dict with 'context' and 'skill_names' keys,
    or None if skills aren't available.
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

        names = get_trading_skill_names()
        log.info(f"[trading] registered {len(names)} trading skills: {names}")
        return {"context": ctx, "skill_names": names}
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

    # Skill listing
    @app.get("/api/v1/skills")
    async def list_skills():
        skills_info = register_skills()
        if skills_info:
            return {
                "ok": True,
                "skills": skills_info["skill_names"],
            }
        return {"ok": True, "skills": [], "note": "Skills not loaded — check imports"}

    log.info("[trading] FastAPI app created with stop loss routes")
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
