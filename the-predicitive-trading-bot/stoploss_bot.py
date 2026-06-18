"""
PREDICITIVE TRADING BOT · STOP LOSS BOT
========================================
Standalone PM2 service that monitors open trading positions and
automatically executes stop losses when triggered.

Architecture:
  - Positions stored in ~/.trading/stop_loss_positions.db (SQLite WAL mode)
  - Price checks via Jupiter price API every N seconds
  - Supports fixed and trailing stop losses
  - Executes swaps via Jupiter when stop is triggered
  - PM2-compatible run_loop / main entry points

API endpoints (when used with stoploss_routes.py):
  POST   /api/v1/stoploss/add       — Add a position to monitor
  GET    /api/v1/stoploss/list      — List all positions
  POST   /api/v1/stoploss/cancel    — Cancel/remove a position
  DELETE /api/v1/stoploss/remove/{pid} — Hard-delete a position
  GET    /api/v1/stoploss/status    — Bot health and stats

CLI:
  python3 stoploss_bot.py --loop
  python3 stoploss_bot.py --add <MINT> <ENTRY> <AMOUNT> <STOP_PCT> [--trailing]
  python3 stoploss_bot.py --status
  python3 stoploss_bot.py --cancel <position_id>
  python3 stoploss_bot.py --remove <position_id>
  python3 stoploss_bot.py --once
"""

import json
import os
import sys
import time
import uuid
import sqlite3
import asyncio
import logging
import signal
import base64 as _base64
import contextlib
from datetime import datetime, timezone
from typing import Optional

import httpx
import aiosqlite


# ── Configuration ──────────────────────────────────────────────────────────

POSITIONS_DB = os.path.expanduser("~/.trading/stop_loss_positions.db")
POSITIONS_FILE_LEGACY = os.path.expanduser("~/.trading/stop_loss_positions.json")
CHECK_INTERVAL_SEC = int(os.environ.get("STOPLOSS_INTERVAL_SEC", "15"))
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"
JUPITER_PRICE_API = "https://price.jup.ag/v6/price"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WSOL_MINT = "So11111111111111111111111111111111111111112"
DEFAULT_OUTPUT_MINT = WSOL_MINT

# Wallet — base58-encoded 64-byte Ed25519 private key for stop loss execution.
# If unset, the bot runs in dry-run mode (quotes only, no real swaps).
_STOPLOSS_SIGNING_KEY = os.environ.get("STOPLOSS_WALLET_PRIVATE_KEY", "").strip()
_SOLANA_RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
_SOLANA_TIMEOUT_SEC = int(os.environ.get("STOPLOSS_SOLANA_TIMEOUT", "30"))

log = logging.getLogger("trading.stop_loss")


# ── Position Store ─────────────────────────────────────────────────────────


class PositionStore:
    """Async SQLite-backed store for trading positions.

    Schema:
      CREATE TABLE IF NOT EXISTS positions (
        id              TEXT PRIMARY KEY,
        token_mint      TEXT NOT NULL,
        output_mint     TEXT NOT NULL,
        entry_price     REAL NOT NULL,
        amount          REAL NOT NULL,
        stop_loss_percent REAL NOT NULL,
        current_stop_level REAL NOT NULL,
        highest_price   REAL NOT NULL,
        lowest_price    REAL NOT NULL,
        trailing        INTEGER NOT NULL DEFAULT 0,
        status          TEXT NOT NULL DEFAULT 'active',
        label           TEXT,
        slippage_bps    INTEGER NOT NULL DEFAULT 100,
        take_profit_percent REAL,
        take_profit_level REAL,
        created_at      TEXT NOT NULL,
        triggered_at    TEXT,
        triggered_price REAL,
        tx_signature    TEXT,
        last_checked_price REAL,
        last_checked_at TEXT,
        peak_drawdown_pct REAL NOT NULL DEFAULT 0.0,
        cancelled_at    TEXT,
        last_swap_result TEXT  -- JSON blob, NULL until triggered
      );
    """

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS positions (
            id              TEXT PRIMARY KEY,
            token_mint      TEXT NOT NULL,
            output_mint     TEXT NOT NULL,
            entry_price     REAL NOT NULL,
            amount          REAL NOT NULL,
            stop_loss_percent REAL NOT NULL,
            current_stop_level REAL NOT NULL,
            highest_price   REAL NOT NULL,
            lowest_price    REAL NOT NULL,
            trailing        INTEGER NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'active',
            label           TEXT,
            slippage_bps    INTEGER NOT NULL DEFAULT 100,
            take_profit_percent REAL,
            take_profit_level REAL,
            created_at      TEXT NOT NULL,
            triggered_at    TEXT,
            triggered_price REAL,
            tx_signature    TEXT,
            last_checked_price REAL,
            last_checked_at TEXT,
            peak_drawdown_pct REAL NOT NULL DEFAULT 0.0,
            cancelled_at    TEXT,
            last_swap_result TEXT
        );
    """

    def __init__(self, path: str = POSITIONS_DB):
        self._path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._migrate_from_json()

    def _migrate_from_json(self) -> None:
        """One-time migration: import legacy JSON positions into SQLite."""
        old_json = POSITIONS_FILE_LEGACY
        if os.path.exists(old_json) and not os.path.exists(self._path):
            try:
                with open(old_json) as f:
                    legacy = json.load(f)
                if not legacy:
                    return
                log.info(f"[stoploss] migrating {len(legacy)} positions from JSON → SQLite")
                conn = sqlite3.connect(self._path)
                conn.executescript(self._SCHEMA)
                _insert_sql = """
                    INSERT OR IGNORE INTO positions (
                        id, token_mint, output_mint, entry_price, amount,
                        stop_loss_percent, current_stop_level, highest_price, lowest_price,
                        trailing, status, label, slippage_bps,
                        take_profit_percent, take_profit_level,
                        created_at, triggered_at, triggered_price, tx_signature,
                        last_checked_price, last_checked_at, peak_drawdown_pct,
                        cancelled_at, last_swap_result
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """
                for pos_id, p in legacy.items():
                    conn.execute(_insert_sql, (
                        p.get("id", pos_id),
                        p.get("token_mint", ""),
                        p.get("output_mint", DEFAULT_OUTPUT_MINT),
                        p.get("entry_price", 0),
                        p.get("amount", 0),
                        p.get("stop_loss_percent", 0.05),
                        p.get("current_stop_level", 0),
                        p.get("highest_price", 0),
                        p.get("lowest_price", 0),
                        1 if p.get("trailing") else 0,
                        p.get("status", "active"),
                        p.get("label", "")[:100],
                        p.get("slippage_bps", 100),
                        p.get("take_profit_percent"),
                        p.get("take_profit_level"),
                        p.get("created_at", ""),
                        p.get("triggered_at"),
                        p.get("triggered_price"),
                        p.get("tx_signature"),
                        p.get("last_checked_price"),
                        p.get("last_checked_at"),
                        p.get("peak_drawdown_pct", 0.0),
                        p.get("cancelled_at"),
                        json.dumps(p.get("last_swap_result")) if p.get("last_swap_result") else None,
                    ))
                conn.commit()
                conn.close()
                os.rename(old_json, old_json + ".migrated")
                log.info(f"[stoploss] migration complete — {old_json}.migrated")
            except Exception as e:
                log.warning(f"[stoploss] migration from JSON failed: {e}")
                try:
                    if os.path.exists(self._path):
                        os.remove(self._path)
                except OSError:
                    pass

    @contextlib.asynccontextmanager
    async def _conn(self):
        """Async context manager yielding an aiosqlite connection with WAL mode."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.executescript(self._SCHEMA)
            yield db

    def _row_to_dict(self, row) -> dict:
        """Convert an aiosqlite.Row to a plain dict."""
        d = dict(row)
        d["trailing"] = bool(d["trailing"])
        if d.get("last_swap_result") and isinstance(d["last_swap_result"], str):
            try:
                d["last_swap_result"] = json.loads(d["last_swap_result"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    async def add(self, position: dict) -> str:
        """Insert a new position. Returns the position ID."""
        pos_id = position["id"]
        swap_json = json.dumps(position.get("last_swap_result")) if position.get("last_swap_result") else None
        async with self._conn() as db:
            await db.execute(
                """INSERT INTO positions (
                    id, token_mint, output_mint, entry_price, amount,
                    stop_loss_percent, current_stop_level, highest_price, lowest_price,
                    trailing, status, label, slippage_bps,
                    take_profit_percent, take_profit_level,
                    created_at, triggered_at, triggered_price, tx_signature,
                    last_checked_price, last_checked_at, peak_drawdown_pct,
                    cancelled_at, last_swap_result
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pos_id, position["token_mint"], position["output_mint"],
                    position["entry_price"], position["amount"],
                    position["stop_loss_percent"], position["current_stop_level"],
                    position["highest_price"], position["lowest_price"],
                    1 if position.get("trailing") else 0,
                    position["status"], position.get("label", ""),
                    position.get("slippage_bps", 100),
                    position.get("take_profit_percent"),
                    position.get("take_profit_level"),
                    position["created_at"],
                    position.get("triggered_at"), position.get("triggered_price"),
                    position.get("tx_signature"),
                    position.get("last_checked_price"), position.get("last_checked_at"),
                    position.get("peak_drawdown_pct", 0.0),
                    position.get("cancelled_at"),
                    swap_json,
                ),
            )
            await db.commit()
        return pos_id

    async def update(self, pos_id: str, updates: dict) -> bool:
        """Partial update on a position."""
        if not updates:
            return False
        set_clauses = []
        values = []
        for key, val in updates.items():
            if key == "trailing":
                val = 1 if val else 0
            elif key == "last_swap_result":
                val = json.dumps(val) if val is not None else None
            set_clauses.append(f"{key} = ?")
            values.append(val)
        values.append(pos_id)
        sql = f"UPDATE positions SET {', '.join(set_clauses)} WHERE id = ?"
        async with self._conn() as db:
            cursor = await db.execute(sql, values)
            await db.commit()
            return cursor.rowcount > 0

    async def remove(self, pos_id: str) -> bool:
        """Delete a position entirely."""
        async with self._conn() as db:
            cursor = await db.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get(self, pos_id: str) -> Optional[dict]:
        """Get a single position by ID."""
        async with self._conn() as db:
            cursor = await db.execute("SELECT * FROM positions WHERE id = ?", (pos_id,))
            row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None

    async def list_active(self) -> list[dict]:
        """Return all positions with status='active'."""
        async with self._conn() as db:
            cursor = await db.execute("SELECT * FROM positions WHERE status = 'active' ORDER BY created_at")
            rows = await cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]

    async def list_all(self) -> list[dict]:
        """Return all positions."""
        async with self._conn() as db:
            cursor = await db.execute("SELECT * FROM positions ORDER BY created_at")
            rows = await cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]

    async def snapshot(self) -> dict:
        """Return summary counts + all positions."""
        async with self._conn() as db:
            cursor = await db.execute("SELECT status, COUNT(*) as cnt FROM positions GROUP BY status")
            rows = await cursor.fetchall()
            counts = {r["status"]: r["cnt"] for r in rows}
            cursor2 = await db.execute("SELECT * FROM positions ORDER BY created_at")
            all_rows = await cursor2.fetchall()
            return {
                "total": sum(counts.values()),
                "active": counts.get("active", 0),
                "triggered": counts.get("triggered", 0),
                "cancelled": counts.get("cancelled", 0),
                "positions": [self._row_to_dict(r) for r in all_rows],
            }


# ── Price Fetcher ──────────────────────────────────────────────────────────


class PriceFetcher:
    """Fetches current token prices from Jupiter price API."""

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=15)

    async def get_price(self, token_mint: str) -> Optional[float]:
        """Get current USD price for a token via Jupiter price API."""
        try:
            url = f"{JUPITER_PRICE_API}?ids={token_mint}"
            r = await self._http.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                price_data = data.get("data", {}).get(token_mint, {})
                price = price_data.get("price")
                if price is not None:
                    return float(price)
        except Exception:
            pass

        # Fallback: quote for 1 token → USDC
        try:
            params = {
                "inputMint": token_mint,
                "outputMint": USDC_MINT,
                "amount": 1_000_000,
                "slippageBps": 100,
            }
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            r = await self._http.get(f"{JUPITER_QUOTE_API}?{qs}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                in_amount = float(data.get("inAmount", 0))
                out_amount = float(data.get("outAmount", 0))
                if in_amount > 0:
                    return out_amount / in_amount
        except Exception:
            pass

        return None

    async def close(self):
        await self._http.aclose()


# ── Swap Executor ──────────────────────────────────────────────────────────


class SwapExecutor:
    """Executes token swaps via Jupiter aggregator with live Solana signing."""

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=30)
        self._solders_vtx = None
        self._solana_client_cls = None
        self._keypair = None
        self._pubkey_str = None
        self._live_enabled = bool(_STOPLOSS_SIGNING_KEY)

        if self._live_enabled:
            try:
                import base58
                from solders.keypair import Keypair
                from solders.transaction import VersionedTransaction as _Vtx
                from solana.rpc.api import Client as _SolClient
                self._solders_vtx = _Vtx
                self._solana_client_cls = _SolClient

                raw_key = base58.b58decode(_STOPLOSS_SIGNING_KEY)
                if len(raw_key) != 64:
                    log.warning(
                        f"[stoploss] signing key must be 64 bytes, got {len(raw_key)} · dry-run"
                    )
                    self._live_enabled = False
                else:
                    self._keypair = Keypair.from_bytes(raw_key)
                    self._pubkey_str = str(self._keypair.pubkey())
                    log.info(f"[stoploss] live enabled · wallet {self._pubkey_str[:8]}...")
            except Exception as e:
                log.warning(f"[stoploss] failed to decode signing key: {e} · dry-run")
                self._live_enabled = False

    @property
    def wallet_pubkey(self) -> Optional[str]:
        return self._pubkey_str

    @property
    def can_execute_live(self) -> bool:
        return self._live_enabled and self._keypair is not None

    async def execute_stop_loss(
        self,
        token_mint: str,
        output_mint: str,
        amount: float,
        slippage_bps: int = 100,
        dry_run: bool = True,
    ) -> dict:
        """Execute a stop loss swap: token → output (e.g. SOL or USDC)."""
        # ── Step 1: Get Quote ───────────────────────────────────────────
        try:
            raw_amount = int(amount * 1e9)
            params = {
                "inputMint": token_mint,
                "outputMint": output_mint,
                "amount": raw_amount,
                "slippageBps": slippage_bps,
            }
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            r = await self._http.get(f"{JUPITER_QUOTE_API}?{qs}", timeout=15)

            if r.status_code != 200:
                return {
                    "success": False,
                    "error": f"Jupiter quote failed: HTTP {r.status_code}",
                    "dry_run": dry_run,
                }
            quote = r.json()
        except Exception as e:
            return {"success": False, "error": f"quote request failed: {e}", "dry_run": dry_run}

        # ── Step 2: Dry-run → return quote only ─────────────────────────
        if dry_run or not self.can_execute_live:
            return {
                "success": True,
                "dry_run": True,
                "input_mint": token_mint,
                "output_mint": output_mint,
                "amount_in": amount,
                "amount_out": float(quote.get("outAmount", 0)) / 1e9,
                "price_impact_pct": quote.get("priceImpactPct", 0),
                "route": quote.get("routePlan", []),
                "note": (
                    "Dry run — set STOPLOSS_WALLET_PRIVATE_KEY for live execution"
                    if not self.can_execute_live else
                    "Dry run — pass dry_run=False for live execution"
                ),
            }

        # ── Step 3: Get swap transaction from Jupiter ────────────────────
        try:
            swap_payload = {
                "quoteResponse": quote,
                "userPublicKey": self._pubkey_str,
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": "auto",
            }
            swap_resp = await self._http.post(JUPITER_SWAP_API, json=swap_payload, timeout=20)
            if swap_resp.status_code != 200:
                err_text = await swap_resp.aread()
                return {
                    "success": False,
                    "error": f"Jupiter swap API failed: HTTP {swap_resp.status_code}: {err_text[:200]}",
                    "dry_run": False,
                }
            swap_data = swap_resp.json()
            swap_tx_b64 = swap_data.get("swapTransaction")
            if not swap_tx_b64:
                return {"success": False, "error": "Jupiter returned no swapTransaction", "dry_run": False}
        except Exception as e:
            return {"success": False, "error": f"swap transaction request failed: {e}", "dry_run": False}

        # ── Step 4: Deserialize + sign ──────────────────────────────────
        try:
            VersionedTransaction = self._solders_vtx
            tx_bytes = _base64.b64decode(swap_tx_b64)
            tx = VersionedTransaction.from_bytes(tx_bytes)
            message_bytes = bytes(tx.message)
            sig = self._keypair.sign_message(message_bytes)
            signed_tx = VersionedTransaction(
                tuple([sig] + list(tx.signatures[1:])), tx.message
            )
        except Exception as e:
            return {"success": False, "error": f"transaction signing failed: {e}", "dry_run": False}

        # ── Step 5: Submit to Solana RPC ────────────────────────────────
        try:
            Client = self._solana_client_cls
            client = Client(_SOLANA_RPC_URL, timeout=_SOLANA_TIMEOUT_SEC)
            send_resp = await asyncio.to_thread(client.send_transaction, signed_tx)

            if send_resp.value is None:
                return {"success": False, "error": "RPC returned no signature", "dry_run": False}
            tx_sig = str(send_resp.value)
            log.info(
                f"[stoploss] swap submitted · {amount} tokens {token_mint[:8]}... → "
                f"{output_mint[:8]}... · sig {tx_sig[:16]}..."
            )
        except Exception as e:
            return {"success": False, "error": f"RPC submit failed: {e}", "dry_run": False}

        # ── Step 6: Poll for confirmation ───────────────────────────────
        try:
            poll_interval = 2
            max_polls = max(1, _SOLANA_TIMEOUT_SEC // poll_interval)
            amount_out = float(quote.get("outAmount", 0)) / 1e9

            for _attempt in range(max_polls):
                await asyncio.sleep(poll_interval)
                status_resp = await asyncio.to_thread(
                    client.get_signature_statuses, [send_resp.value]
                )
                if status_resp.value and status_resp.value[0] is not None:
                    status = status_resp.value[0]
                    status_str = (
                        str(status.confirmation_status).lower()
                        if status.confirmation_status else ""
                    )
                    if "confirmed" in status_str or "finalized" in status_str:
                        if status.err:
                            log.error(f"[stoploss] swap failed on-chain: {status.err}")
                            return {
                                "success": False,
                                "error": f"on-chain failure: {status.err}",
                                "tx_signature": tx_sig,
                                "dry_run": False,
                            }
                        log.info(f"[stoploss] swap confirmed · {tx_sig[:16]}... · {status_str}")
                        return {
                            "success": True,
                            "dry_run": False,
                            "tx_signature": tx_sig,
                            "input_mint": token_mint,
                            "output_mint": output_mint,
                            "amount_in": amount,
                            "amount_out": amount_out,
                            "price_impact_pct": quote.get("priceImpactPct", 0),
                            "confirmation_status": status_str,
                        }

            log.warning(f"[stoploss] swap unconfirmed within timeout · sig {tx_sig[:16]}...")
            return {
                "success": True,
                "dry_run": False,
                "tx_signature": tx_sig,
                "confirmed": False,
                "note": "Transaction submitted but confirmation unknown — check explorer",
            }
        except Exception as e:
            return {
                "success": True, "dry_run": False, "tx_signature": tx_sig,
                "confirmed": False, "error": f"confirmation poll failed: {e}",
            }

    async def close(self):
        await self._http.aclose()


# ── Stop Loss Bot ──────────────────────────────────────────────────────────


class StopLossBot:
    """Main bot — monitors positions, checks prices, triggers stop losses."""

    def __init__(self, interval: int = CHECK_INTERVAL_SEC):
        self.store = PositionStore()
        self.prices = PriceFetcher()
        self.executor = SwapExecutor()
        self.interval = interval
        self._running = False
        self._stats: dict = {"cycles": 0, "checks": 0, "triggers": 0, "errors": 0}

    # ── Position Management ────────────────────────────────────────────

    async def add_position(
        self,
        token_mint: str,
        entry_price: float,
        amount: float,
        stop_loss_percent: float,
        *,
        output_mint: str = DEFAULT_OUTPUT_MINT,
        trailing: bool = False,
        label: str = "",
        slippage_bps: int = 100,
        take_profit_percent: Optional[float] = None,
    ) -> dict:
        """Add a new position to monitor."""
        entry_stop = entry_price * (1 - stop_loss_percent)
        pos_id = f"sl_{uuid.uuid4().hex[:12]}"

        position = {
            "id": pos_id,
            "token_mint": token_mint,
            "output_mint": output_mint,
            "entry_price": entry_price,
            "amount": amount,
            "stop_loss_percent": stop_loss_percent,
            "current_stop_level": entry_stop,
            "highest_price": entry_price,
            "lowest_price": entry_price,
            "trailing": trailing,
            "status": "active",
            "label": label or f"{token_mint[:8]}...",
            "slippage_bps": slippage_bps,
            "take_profit_percent": take_profit_percent,
            "take_profit_level": entry_price * (1 + take_profit_percent) if take_profit_percent else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "triggered_at": None,
            "triggered_price": None,
            "tx_signature": None,
            "last_checked_price": None,
            "last_checked_at": None,
            "peak_drawdown_pct": 0.0,
        }

        await self.store.add(position)
        log.info(
            f"[stoploss] added {pos_id}: {token_mint[:12]}... "
            f"entry={entry_price} stop={entry_stop:.4f} "
            f"({'trailing' if trailing else 'fixed'})"
        )
        return position

    async def cancel_position(self, pos_id: str) -> bool:
        """Cancel monitoring a position."""
        pos = await self.store.get(pos_id)
        if not pos:
            return False
        await self.store.update(pos_id, {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
        })
        log.info(f"[stoploss] cancelled position {pos_id}")
        return True

    async def remove_position(self, pos_id: str) -> bool:
        """Remove a position entirely."""
        ok = await self.store.remove(pos_id)
        if ok:
            log.info(f"[stoploss] removed position {pos_id}")
        return ok

    # ── Monitoring Loop ────────────────────────────────────────────────

    async def check_once(self) -> list[dict]:
        """Single check cycle: iterate active positions, check prices, trigger stops."""
        active = await self.store.list_active()
        triggered: list[dict] = []
        now = datetime.now(timezone.utc).isoformat()

        for pos in active:
            pos_id = pos["id"]
            try:
                price = await self.prices.get_price(pos["token_mint"])
                self._stats["checks"] += 1

                if price is None:
                    log.warning(f"[{pos_id}] price unavailable for {pos['token_mint'][:12]}...")
                    continue

                await self.store.update(pos_id, {
                    "last_checked_price": price,
                    "last_checked_at": now,
                })

                # Track peak drawdown
                drawdown = (pos["highest_price"] - price) / pos["highest_price"] * 100
                if drawdown > pos.get("peak_drawdown_pct", 0):
                    await self.store.update(pos_id, {"peak_drawdown_pct": round(drawdown, 2)})

                # Trailing stop: update highest price
                if pos["trailing"] and price > pos["highest_price"]:
                    new_stop = price * (1 - pos["stop_loss_percent"])
                    await self.store.update(pos_id, {
                        "highest_price": price,
                        "current_stop_level": new_stop,
                    })

                if price < pos.get("lowest_price", price):
                    await self.store.update(pos_id, {"lowest_price": price})

                # Check take profit
                tp = pos.get("take_profit_level")
                if tp and price >= tp:
                    log.info(f"[{pos_id}] TAKE PROFIT: price={price:.6f} >= tp={tp:.6f}")
                    await self.store.update(pos_id, {
                        "status": "take_profit",
                        "triggered_at": now,
                        "triggered_price": price,
                    })
                    triggered.append(await self.store.get(pos_id))
                    self._stats["triggers"] += 1
                    continue

                # Check stop loss
                stop = pos["current_stop_level"]
                if price <= stop:
                    log.warning(
                        f"[{pos_id}] STOP LOSS: price={price:.6f} <= stop={stop:.6f} "
                        f"({drawdown:.1f}%)"
                    )
                    await self.store.update(pos_id, {
                        "status": "triggered",
                        "triggered_at": now,
                        "triggered_price": price,
                    })
                    triggered.append(await self.store.get(pos_id))
                    self._stats["triggers"] += 1

                    swap_result = await self.executor.execute_stop_loss(
                        token_mint=pos["token_mint"],
                        output_mint=pos["output_mint"],
                        amount=pos["amount"],
                        slippage_bps=pos.get("slippage_bps", 100),
                        dry_run=not self.executor.can_execute_live,
                    )
                    await self.store.update(pos_id, {"last_swap_result": swap_result})
                    if swap_result.get("success"):
                        log.info(
                            f"[{pos_id}] swap executed: "
                            f"{swap_result.get('amount_out', '?')} tokens out"
                        )

                await asyncio.sleep(0.3)

            except Exception as e:
                self._stats["errors"] += 1
                log.error(f"[{pos_id}] check error: {e}")

        self._stats["cycles"] += 1
        return triggered

    async def run_loop(self):
        """Background monitoring loop — call this for PM2."""
        self._running = True
        active_count = len(await self.store.list_active())
        log.info(
            f"[stoploss] ONLINE — monitoring every {self.interval}s "
            f"({active_count} active positions)"
        )
        while self._running:
            try:
                triggered = await self.check_once()
                if triggered:
                    log.info(f"[stoploss] {len(triggered)} stop(s) triggered this cycle")
            except Exception as e:
                log.error(f"[stoploss] loop error: {e}")
            await asyncio.sleep(self.interval)

    def stop(self):
        """Graceful stop."""
        self._running = False
        log.info("[stoploss] shutting down")

    # ── Status ─────────────────────────────────────────────────────────

    async def status(self) -> dict:
        """Full status snapshot."""
        store_snap = await self.store.snapshot()
        return {
            "bot": {
                "running": self._running,
                "interval_sec": self.interval,
                "cycles": self._stats["cycles"],
                "price_checks": self._stats["checks"],
                "triggers": self._stats["triggers"],
                "errors": self._stats["errors"],
                "live_enabled": self.executor.can_execute_live,
                "wallet_pubkey": self.executor.wallet_pubkey,
            },
            "positions": store_snap,
        }


# ── Global Singleton ────────────────────────────────────────────────────────

_bot: Optional[StopLossBot] = None


def get_bot() -> StopLossBot:
    global _bot
    if _bot is None:
        _bot = StopLossBot()
    return _bot


# ── CLI Entry Points ────────────────────────────────────────────────────────


async def run_loop(interval: Optional[int] = None):
    """Background loop entry point for PM2."""
    bot = get_bot()
    if interval:
        bot.interval = interval
    await bot.run_loop()


async def run_once():
    """Run a single check cycle and report."""
    bot = get_bot()
    triggered = await bot.check_once()
    status = await bot.status()
    print(json.dumps({
        "triggered": len(triggered),
        "details": triggered,
        "status": status,
    }, indent=2, default=str))


def sync_run_loop():
    """Sync wrapper for PM2 / main entry point."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _handle_sigterm():
        log.info("[stoploss] received SIGTERM")
        get_bot().stop()
        loop.stop()

    try:
        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
    except NotImplementedError:
        pass

    try:
        loop.run_until_complete(run_loop())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


def _print_usage():
    print("Usage: python3 stoploss_bot.py [COMMAND]")
    print()
    print("Commands:")
    print("  --loop                              Start the monitoring loop (default)")
    print("  --once                              Run a single check cycle and report")
    print("  --status                            Show bot status and all positions")
    print("  --add <MINT> <ENTRY> <AMT> <STOP%>  Add a position [--trailing]")
    print("  --cancel <position_id>              Cancel monitoring a position")
    print("  --remove <position_id>              Hard-delete a position from DB")
    print()
    print("Environment:")
    print("  STOPLOSS_WALLET_PRIVATE_KEY   Base58-encoded 64-byte Ed25519 private key")
    print("  SOLANA_RPC_URL                Solana RPC endpoint")
    print("  STOPLOSS_INTERVAL_SEC         Price check interval (default: 15)")
    print("  STOPLOSS_SOLANA_TIMEOUT      Tx confirmation timeout (default: 30)")
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        _print_usage()

    cmd = sys.argv[1]

    if cmd == "--once":
        asyncio.run(run_once())
    elif cmd == "--add":
        if len(sys.argv) < 6:
            print("Error: --add requires <TOKEN_MINT> <ENTRY_PRICE> <AMOUNT> <STOP_LOSS_PCT>")
            sys.exit(1)
        token = sys.argv[2]
        entry = float(sys.argv[3])
        amount = float(sys.argv[4])
        stop_pct = float(sys.argv[5])
        trailing = "--trailing" in sys.argv
        result = asyncio.run(get_bot().add_position(token, entry, amount, stop_pct, trailing=trailing))
        print(json.dumps(result, indent=2, default=str))
    elif cmd == "--cancel":
        if len(sys.argv) < 3:
            print("Error: --cancel requires <POSITION_ID>")
            sys.exit(1)
        pos_id = sys.argv[2]
        result = asyncio.run(get_bot().cancel_position(pos_id))
        print(json.dumps({"ok": result, "position_id": pos_id}))
    elif cmd == "--remove":
        if len(sys.argv) < 3:
            print("Error: --remove requires <POSITION_ID>")
            sys.exit(1)
        pos_id = sys.argv[2]
        result = asyncio.run(get_bot().remove_position(pos_id))
        print(json.dumps({"ok": result, "position_id": pos_id, "status": "deleted" if result else "not_found"}))
    elif cmd == "--status":
        result = asyncio.run(get_bot().status())
        print(json.dumps(result, indent=2, default=str))
    elif cmd == "--loop":
        sync_run_loop()
    else:
        print(f"Unknown command: {cmd}")
        _print_usage()
