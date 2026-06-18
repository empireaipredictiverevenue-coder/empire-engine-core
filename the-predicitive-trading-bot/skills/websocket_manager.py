"""
PREDICITIVE TRADING BOT · WEBSOCKET MANAGER
=============================================
Real-time WebSocket endpoint for position price updates and
stop-loss / take-profit auto-trigger notifications.

Architecture:
  - ConnectionManager: per-user WebSocket tracking, subscribe/unsubscribe
  - Price feed loop: polls Jupiter for each subscribed position's token
  - Auto-trigger: calls UserStore.update_position_price() which fires
    SL/TP internally, then pushes results to the WebSocket client

Security:
  - API key validated on connect (Bearer or query param)
  - Users only see their own positions
  - Connections tracked per-user with automatic cleanup on disconnect

WebSocket protocol (JSON messages):

  Client → Server:
    {"type": "subscribe_positions"}     Start streaming position updates
    {"type": "unsubscribe_positions"}   Stop streaming
    {"type": "ping"}                    Keep-alive

  Server → Client:
    {"type": "connected", "user": "abc..."}                   Welcome
    {"type": "price_update", "position_id": "...",            Individual position
     "symbol": "BTC/USD", "price": 42100, "drawdown_pct": 1.2}
    {"type": "alert", "event": "stop_loss|take_profit",      Trigger notification
     "position_id": "...", "symbol": "BTC/USD",
     "price": 39800, "pnl_pct": -5.2}
    {"type": "positions_snapshot", "positions": [...]}        Full refresh
    {"type": "subscribed", "count": 3}                        Confirmation
    {"type": "error", "message": "..."}                       Error
    {"type": "pong"}                                          Keep-alive response
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Any

import httpx

log = logging.getLogger("trading.websocket")

# ── Jupiter Price API ────────────────────────────────────────────────

JUPITER_PRICE_API = "https://price.jup.ag/v6/price"
_PRICE_POLL_INTERVAL_SEC = float(os.environ.get("WS_PRICE_INTERVAL", "3.0"))


# ═══════════════════════════════════════════════════════════════════════
# CONNECTION MANAGER
# ═══════════════════════════════════════════════════════════════════════

class ConnectionManager:
    """Manages WebSocket connections per user with subscription tracking."""

    def __init__(self):
        # user_hash → list[websocket]  (one user can have multiple tabs)
        self._connections: dict[str, list] = {}
        # user_hash → bool
        self._subscriptions: dict[str, bool] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, user_hash: str, websocket) -> None:
        """Register a new WebSocket connection for a user."""
        if user_hash not in self._connections:
            self._connections[user_hash] = []
        self._connections[user_hash].append(websocket)
        log.info(f"[ws] user {user_hash[:12]}... connected ({len(self._connections[user_hash])} connections)")

        await self._send(websocket, {
            "type": "connected",
            "user_hash": user_hash[:12] + "...",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def disconnect(self, user_hash: str, websocket) -> None:
        """Remove a WebSocket connection."""
        if user_hash in self._connections:
            try:
                self._connections[user_hash].remove(websocket)
            except ValueError:
                pass
            if not self._connections[user_hash]:
                del self._connections[user_hash]
                # Cancel running task if no connections left
                self._unsubscribe(user_hash)
        log.info(f"[ws] user {user_hash[:12]}... disconnected")

    def _unsubscribe(self, user_hash: str) -> None:
        """Cancel the price feed task for a user."""
        self._subscriptions.pop(user_hash, None)
        task = self._running_tasks.pop(user_hash, None)
        if task and not task.done():
            task.cancel()

    async def _broadcast(self, user_hash: str, message: dict) -> None:
        """Send a message to all active connections for a user."""
        if user_hash not in self._connections:
            return
        dead = []
        for ws in self._connections[user_hash]:
            try:
                await self._send(ws, message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(user_hash, ws)

    @staticmethod
    async def _send(websocket, message: dict) -> None:
        """Send a JSON message over the WebSocket."""
        await websocket.send_text(json.dumps(message, default=str))

    # ── Subscription control ────────────────────────────────────────

    async def handle_message(
        self,
        user_hash: str,
        api_key: str,
        websocket,
        message: dict,
    ) -> None:
        """Process incoming WebSocket messages from a client."""
        msg_type = message.get("type", "")

        if msg_type == "subscribe_positions":
            await self._start_price_feed(user_hash, api_key, websocket)

        elif msg_type == "unsubscribe_positions":
            self._unsubscribe(user_hash)
            await self._send(websocket, {"type": "unsubscribed"})

        elif msg_type == "ping":
            await self._send(websocket, {"type": "pong"})

        else:
            await self._send(websocket, {
                "type": "error",
                "message": f"Unknown message type: {msg_type}",
            })

    async def _start_price_feed(
        self, user_hash: str, api_key: str, websocket
    ) -> None:
        """Begin streaming price updates for a user's positions."""
        from .public_api import get_user_store

        # Cancel existing task if any
        self._unsubscribe(user_hash)

        self._subscriptions[user_hash] = True

        # Send initial snapshot to ALL connections for this user
        store = get_user_store()
        try:
            positions = await store.get_user_positions(api_key)
            open_positions = [p for p in positions if p["status"] == "open"]
            snapshot_msg = {
                "type": "positions_snapshot",
                "positions": [
                    {
                        "id": p["id"],
                        "symbol": p["symbol"],
                        "entry_price": p["entry_price"],
                        "amount": p["amount"],
                        "side": p["side"],
                        "stop_loss": p.get("current_stop_loss"),
                        "take_profit": p.get("take_profit_level"),
                        "current_drawdown": p.get("current_drawdown", 0),
                        "created_at": p["created_at"],
                    }
                    for p in open_positions
                ],
            }
            await self._broadcast(user_hash, snapshot_msg)
            await self._broadcast(user_hash, {
                "type": "subscribed",
                "count": len(open_positions),
                "interval_sec": _PRICE_POLL_INTERVAL_SEC,
            })
        except Exception as e:
            await self._send(websocket, {
                "type": "error",
                "message": f"Failed to load positions: {e}",
            })
            return

        # Start background price feed loop
        task = asyncio.create_task(
            self._price_feed_loop(user_hash, api_key)
        )
        self._running_tasks[user_hash] = task

    async def _price_feed_loop(self, user_hash: str, api_key: str) -> None:
        """Background loop: poll prices, update positions, push alerts."""
        from .public_api import get_user_store as _gs

        store = _gs()
        http = httpx.AsyncClient(timeout=10)

        try:
            while self._subscriptions.get(user_hash):
                try:
                    # Fetch open positions
                    positions = await store.get_user_positions(api_key)
                    open_positions = [p for p in positions if p["status"] == "open"]

                    if not open_positions:
                        await asyncio.sleep(_PRICE_POLL_INTERVAL_SEC)
                        continue

                    # Collect unique tokens to fetch prices
                    tokens = list(set(p["symbol"] for p in open_positions))
                    prices = await self._fetch_prices(http, tokens)

                    # Update each position
                    for pos in open_positions:
                        symbol = pos["symbol"]
                        price = prices.get(symbol)
                        if price is None:
                            continue

                        # Update position → triggers SL/TP internally
                        result = await store.update_position_price(
                            api_key, pos["id"], price
                        )

                        if "error" in result:
                            continue

                        # Push price update
                        await self._broadcast(user_hash, {
                            "type": "price_update",
                            "position_id": pos["id"],
                            "symbol": symbol,
                            "price": price,
                            "drawdown_pct": result.get("drawdown_pct", 0),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                        # Push alert if SL or TP triggered
                        if result.get("status") in ("stopped_out", "take_profit"):
                            await self._broadcast(user_hash, {
                                "type": "alert",
                                "event": "stop_loss" if result["status"] == "stopped_out" else "take_profit",
                                "position_id": pos["id"],
                                "symbol": symbol,
                                "price": price,
                                "pnl_pct": result.get("pnl_pct"),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })

                    await asyncio.sleep(_PRICE_POLL_INTERVAL_SEC)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error(f"[ws] price feed error for {user_hash[:12]}...: {e}")
                    await asyncio.sleep(_PRICE_POLL_INTERVAL_SEC * 2)

        finally:
            await http.aclose()
            self._subscriptions.pop(user_hash, None)

    async def _fetch_prices(
        self, http: httpx.AsyncClient, symbols: list[str]
    ) -> dict[str, float]:
        """Fetch current prices for a list of symbols concurrently.

        For Solana mint addresses: uses Jupiter price API.
        For forex/crypto pairs: Binance public ticker as fallback.
        """
        prices = {}
        urls: list[tuple[str, str]] = []  # (symbol, url)

        for symbol in symbols:
            # Solana token mint addresses (base58, no slash)
            if "/" not in symbol and len(symbol) > 32:
                urls.append((symbol, f"{JUPITER_PRICE_API}?ids={symbol}"))
            else:
                # Named pairs: Binance public ticker
                symbol_clean = symbol.replace("/", "")
                urls.append((symbol,
                    f"https://api.binance.com/api/v3/ticker/price?symbol={symbol_clean}"))

        # Fire all requests concurrently
        async def _fetch_one(sym: str, url: str) -> tuple[str, Optional[float]]:
            try:
                r = await http.get(url, timeout=8)
                if r.status_code != 200:
                    return sym, None
                data = r.json()
                # Jupiter response
                if "data" in data:
                    price_data = data.get("data", {}).get(sym, {})
                    price = price_data.get("price")
                    if price is not None:
                        return sym, float(price)
                # Binance response
                price = data.get("price")
                if price:
                    return sym, float(price)
                return sym, None
            except Exception:
                return sym, None

        results = await asyncio.gather(*[_fetch_one(s, u) for s, u in urls])
        for sym, price in results:
            if price is not None:
                prices[sym] = price

        return prices

    @property
    def active_connections(self) -> int:
        """Total active WebSocket connections across all users."""
        return sum(len(v) for v in self._connections.values())

    @property
    def active_subscriptions(self) -> int:
        """Total active price feed subscriptions."""
        return len(self._subscriptions)


# ── Global singleton ─────────────────────────────────────────────────

_manager: Optional[ConnectionManager] = None


def get_ws_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
