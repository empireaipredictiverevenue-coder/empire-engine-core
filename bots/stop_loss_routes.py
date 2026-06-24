"""
EMPIRE V49 · STOP LOSS ROUTES
===============================
REST API routes for managing stop loss positions on the hub.

Routes:
  POST   /api/v1/stoploss/add       — Add a position to monitor
  GET    /api/v1/stoploss/list      — List all positions
  POST   /api/v1/stoploss/cancel    — Cancel/remove a position
  GET    /api/v1/stoploss/status    — Bot health and stats

Wired from hub.py via:
  from bots.stop_loss_routes import register_stop_loss_routes
  register_stop_loss_routes(app, require_auth=require_auth)
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query


log = logging.getLogger("empire.stop_loss.routes")


# ── Sentinels ────────────────────────────────────────────────────────────
_AUTH_OPTIONAL = None  # default: endpoints are public unless callers pass require_auth


def register_stop_loss_routes(app, require_auth=_AUTH_OPTIONAL):
    """Register stop loss management endpoints on the FastAPI app."""

    # Lazy import to avoid circular deps at module level
    from bots.stop_loss_bot import get_bot

    @app.post("/api/v1/stoploss/add")
    async def stoploss_add(
        body: dict,
        auth=Depends(require_auth) if require_auth is not _AUTH_OPTIONAL else None,
    ):
        """Add a new position to monitor for stop loss.

        Body:
          token_mint: str (required) — Solana token mint address
          entry_price: float (required) — Entry price in USD
          amount: float (required) — Position size in tokens
          stop_loss_percent: float (required) — Stop loss as decimal (e.g. 0.05 = 5%)
          output_mint: str (optional) — Token to swap into (default: WSOL)
          trailing: bool (optional) — Enable trailing stop (default: false)
          label: str (optional) — Human-readable label
          slippage_bps: int (optional) — Slippage in basis points (default: 100)
          take_profit_percent: float (optional) — Take profit level
        """
        bot = get_bot()
        try:
            token_mint = str(body["token_mint"])
            entry_price = float(body["entry_price"])
            amount = float(body["amount"])
            stop_loss_percent = float(body["stop_loss_percent"])
        except KeyError as e:
            raise HTTPException(400, f"Missing required field: {e}")
        except (TypeError, ValueError) as e:
            raise HTTPException(400, f"Invalid field value: {e}")

        if stop_loss_percent <= 0 or stop_loss_percent >= 1:
            raise HTTPException(400, "stop_loss_percent must be between 0 and 1 (e.g. 0.05 for 5%)")
        if entry_price <= 0:
            raise HTTPException(400, "entry_price must be positive")
        if amount <= 0:
            raise HTTPException(400, "amount must be positive")

        result = await bot.add_position(
            token_mint=token_mint,
            entry_price=entry_price,
            amount=amount,
            stop_loss_percent=stop_loss_percent,
            output_mint=str(body.get("output_mint", "So11111111111111111111111111111111111111112")),
            trailing=bool(body.get("trailing", False)),
            label=str(body.get("label", "")),
            slippage_bps=int(body.get("slippage_bps", 100)),
            take_profit_percent=float(body["take_profit_percent"]) if body.get("take_profit_percent") else None,
        )
        return result

    @app.get("/api/v1/stoploss/list")
    async def stoploss_list(
        auth=Depends(require_auth) if require_auth is not _AUTH_OPTIONAL else None,
    ):
        """List all tracked positions with their status."""
        bot = get_bot()
        return await bot.status()

    @app.post("/api/v1/stoploss/cancel")
    async def stoploss_cancel(
        body: dict,
        auth=Depends(require_auth) if require_auth is not _AUTH_OPTIONAL else None,
    ):
        """Cancel monitoring a position.

        Body:
          position_id: str (required) — The position ID to cancel
        """
        pos_id = body.get("position_id", "")
        if not pos_id:
            raise HTTPException(400, "Missing required field: position_id")

        bot = get_bot()
        ok = await bot.cancel_position(pos_id)
        if not ok:
            raise HTTPException(404, f"Position '{pos_id}' not found")
        return {"ok": True, "position_id": pos_id, "status": "cancelled"}

    @app.delete("/api/v1/stoploss/remove/{position_id}")
    async def stoploss_remove(
        position_id: str,
        auth=Depends(require_auth) if require_auth is not _AUTH_OPTIONAL else None,
    ):
        """Hard-delete a position entirely (removed from DB, not just cancelled).

        Path param:
          position_id: str (required) — The position ID to permanently delete
        """
        if not position_id:
            raise HTTPException(400, "Missing required path param: position_id")

        bot = get_bot()
        ok = await bot.remove_position(position_id)
        if not ok:
            raise HTTPException(404, f"Position '{position_id}' not found")
        return {"ok": True, "position_id": position_id, "status": "deleted"}

    @app.get("/api/v1/stoploss/status")
    async def stoploss_status(
        auth=Depends(require_auth) if require_auth is not _AUTH_OPTIONAL else None,
    ):
        """Stop loss bot health and stats."""
        bot = get_bot()
        status = await bot.status()
        return {
            "ok": True,
            "bot": status["bot"],
            "positions": status["positions"],
        }

    log.info("[stop_loss.routes] REST routes registered")
