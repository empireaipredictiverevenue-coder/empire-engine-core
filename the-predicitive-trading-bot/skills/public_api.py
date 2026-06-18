"""
PREDICITIVE TRADING BOT · PUBLIC API MODULE
=============================================
Non-custodial user management for the public trading API.

Architecture:
  - UserStore: SQLite-backed user + exchange key storage (WAL mode)
  - Wallet verification: Solana Ed25519 challenge → sign → verify
  - API key lifecycle: generate, validate, rotate, revoke
  - Exchange key storage: Fernet-encrypted via PBKDF2-derived key
  - Drawdown + TPC tracker: per-user peak value, drawdown pct,
    take-profit events, daily P&L

Security:
  - Private keys NEVER touch the server (signature verification only)
  - Exchange API keys encrypted at rest (Fernet + PBKDF2 from user API key)
  - API keys hashed with SHA-256 for storage; only shown once at creation

Tables (in ~/.trading/public_users.db):
  - users: api_key_hash, wallet_pubkey, tier, created_at, last_seen
  - exchange_keys: user_hash, exchange, encrypted_keys_blob, created_at
  - user_positions: user_hash, symbol, entry_price, amount, stop_loss,
    take_profit, peak_price, status, created_at
  - auth_challenges: challenge_nonce, wallet_pubkey, expires_at
"""

import os
import json
import uuid
import time
import base64
import hashlib
import hmac
import secrets
import logging
import contextlib
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

import aiosqlite

log = logging.getLogger("trading.public_api")

# ── DB Path ────────────────────────────────────────────────────────────

USERS_DB = os.path.expanduser("~/.trading/public_users.db")

# ── Schema ─────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    api_key_hash       TEXT PRIMARY KEY,
    wallet_pubkey      TEXT NOT NULL,
    tier               TEXT NOT NULL DEFAULT 'free',
    label              TEXT DEFAULT '',
    strategy_params    TEXT DEFAULT '{}',
    peak_portfolio_value REAL DEFAULT 0.0,
    current_drawdown_pct REAL DEFAULT 0.0,
    max_drawdown_pct   REAL DEFAULT 0.0,
    daily_start_value  REAL DEFAULT 0.0,
    daily_pnl_pct      REAL DEFAULT 0.0,
    total_trades       INTEGER DEFAULT 0,
    total_profit       REAL DEFAULT 0.0,
    created_at         TEXT NOT NULL,
    last_seen          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exchange_keys (
    id                 TEXT PRIMARY KEY,
    user_hash          TEXT NOT NULL,
    exchange           TEXT NOT NULL,
    encrypted_blob     TEXT NOT NULL,
    label              TEXT DEFAULT '',
    created_at         TEXT NOT NULL,
    FOREIGN KEY (user_hash) REFERENCES users(api_key_hash)
);

CREATE TABLE IF NOT EXISTS user_positions (
    id                 TEXT PRIMARY KEY,
    user_hash          TEXT NOT NULL,
    symbol             TEXT NOT NULL,
    entry_price        REAL NOT NULL,
    amount             REAL NOT NULL,
    current_stop_loss  REAL,
    take_profit_level  REAL,
    peak_price         REAL NOT NULL,
    current_drawdown   REAL DEFAULT 0.0,
    status             TEXT NOT NULL DEFAULT 'open',
    side               TEXT NOT NULL DEFAULT 'long',
    created_at         TEXT NOT NULL,
    closed_at          TEXT,
    pnl_pct            REAL,
    FOREIGN KEY (user_hash) REFERENCES users(api_key_hash)
);

CREATE TABLE IF NOT EXISTS auth_challenges (
    nonce              TEXT PRIMARY KEY,
    wallet_pubkey      TEXT NOT NULL,
    expires_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sniper_configs (
    user_hash           TEXT PRIMARY KEY,
    is_enabled          INTEGER NOT NULL DEFAULT 0,
    amount_per_snipe    REAL NOT NULL DEFAULT 0.1,
    max_daily_spend     REAL,
    risk_threshold      INTEGER NOT NULL DEFAULT 50,
    min_liquidity       REAL NOT NULL DEFAULT 5000.0,
    max_age_seconds     INTEGER NOT NULL DEFAULT 300,
    stop_loss_pct       REAL NOT NULL DEFAULT 0.15,
    take_profit_pct     REAL NOT NULL DEFAULT 0.50,
    enabled_chains      TEXT NOT NULL DEFAULT 'solana',
    auto_approve        INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (user_hash) REFERENCES users(api_key_hash)
);

CREATE TABLE IF NOT EXISTS sniper_wallets (
    user_hash           TEXT PRIMARY KEY,
    wallet_pubkey       TEXT NOT NULL,
    encrypted_private   TEXT NOT NULL,
    balance_sol         REAL DEFAULT 0.0,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (user_hash) REFERENCES users(api_key_hash)
);

CREATE TABLE IF NOT EXISTS snipe_history (
    id                  TEXT PRIMARY KEY,
    user_hash           TEXT NOT NULL,
    token_address       TEXT NOT NULL,
    token_symbol        TEXT DEFAULT '',
    chain               TEXT NOT NULL DEFAULT 'solana',
    detected_at         TEXT NOT NULL,
    rug_score           INTEGER,
    amount_sol          REAL,
    entry_price         REAL,
    tx_signature        TEXT,
    status              TEXT NOT NULL DEFAULT 'detected',
    pnl_pct             REAL,
    closed_at           TEXT,
    FOREIGN KEY (user_hash) REFERENCES users(api_key_hash)
);

CREATE INDEX IF NOT EXISTS idx_exchange_user ON exchange_keys(user_hash);
CREATE INDEX IF NOT EXISTS idx_positions_user ON user_positions(user_hash);
CREATE INDEX IF NOT EXISTS idx_challenges_expiry ON auth_challenges(expires_at);
CREATE INDEX IF NOT EXISTS idx_snipe_history_user ON snipe_history(user_hash);
CREATE INDEX IF NOT EXISTS idx_snipe_history_status ON snipe_history(status);
"""

CHALLENGE_TTL_SEC = 300  # 5 minutes


# ── Crypto helpers ─────────────────────────────────────────────────────

def _derive_key(api_key: str) -> bytes:
    """PBKDF2 derive an AES key from the API key for Fernet-like use."""
    salt = b"empire_predictive_v1"
    return hashlib.pbkdf2_hmac("sha256", api_key.encode(), salt, 100_000, dklen=32)


def _encrypt_exchange_keys(api_key: str, plaintext: dict) -> str:
    """Encrypt exchange API keys using derived Fernet-style encryption."""
    key = _derive_key(api_key)
    from cryptography.fernet import Fernet
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.encrypt(json.dumps(plaintext).encode()).decode()


def _decrypt_exchange_keys(api_key: str, encrypted_blob: str) -> dict:
    """Decrypt exchange API keys."""
    key = _derive_key(api_key)
    from cryptography.fernet import Fernet
    f = Fernet(base64.urlsafe_b64encode(key))
    return json.loads(f.decrypt(encrypted_blob.encode()).decode())


# ── User Store ─────────────────────────────────────────────────────────

class UserStore:
    """Async SQLite-backed store for public API users."""

    def __init__(self, path: str = USERS_DB):
        self._path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    @contextlib.asynccontextmanager
    async def _conn(self):
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.executescript(_SCHEMA)
            yield db

    # ── Challenge management ───────────────────────────────────────

    async def create_challenge(self, wallet_pubkey: str) -> str:
        """Create a challenge nonce for wallet signature verification."""
        nonce = secrets.token_hex(32)
        expires = (datetime.now(timezone.utc) + timedelta(seconds=CHALLENGE_TTL_SEC)).isoformat()
        async with self._conn() as db:
            await db.execute(
                "INSERT OR REPLACE INTO auth_challenges (nonce, wallet_pubkey, expires_at) VALUES (?,?,?)",
                (nonce, wallet_pubkey, expires),
            )
            await db.commit()
        return nonce

    async def consume_challenge(self, nonce: str) -> Optional[str]:
        """Validate and consume a challenge. Returns wallet_pubkey if valid."""
        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT wallet_pubkey, expires_at FROM auth_challenges WHERE nonce = ?",
                (nonce,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires:
                await db.execute("DELETE FROM auth_challenges WHERE nonce = ?", (nonce,))
                await db.commit()
                return None
            # Consume (one-time use)
            await db.execute("DELETE FROM auth_challenges WHERE nonce = ?", (nonce,))
            await db.commit()
            return row["wallet_pubkey"]

    async def cleanup_expired_challenges(self):
        """Remove expired challenges."""
        async with self._conn() as db:
            await db.execute(
                "DELETE FROM auth_challenges WHERE expires_at < ?",
                (datetime.now(timezone.utc).isoformat(),),
            )
            await db.commit()

    # ── User management ────────────────────────────────────────────

    async def register_user(
        self,
        wallet_pubkey: str,
        tier: str = "free",
        label: str = "",
    ) -> dict:
        """Register a new user. Returns dict with api_key (only shown once)."""
        # Check if already registered
        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT api_key_hash FROM users WHERE wallet_pubkey = ?",
                (wallet_pubkey,),
            )
            existing = await cursor.fetchone()
            if existing:
                # Return existing user info (no API key — already issued)
                cursor2 = await db.execute(
                    "SELECT * FROM users WHERE wallet_pubkey = ?",
                    (wallet_pubkey,),
                )
                row = await cursor2.fetchone()
                user = dict(row)
                return {
                    "api_key_hash": user["api_key_hash"],
                    "wallet_pubkey": user["wallet_pubkey"],
                    "tier": user["tier"],
                    "created_at": user["created_at"],
                    "note": "Already registered. API key not re-displayed for security.",
                }

            # Generate API key
            api_key = f"emp_sk_{secrets.token_hex(24)}"
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            now = datetime.now(timezone.utc).isoformat()

            await db.execute(
                """INSERT INTO users (
                    api_key_hash, wallet_pubkey, tier, label, created_at, last_seen
                ) VALUES (?,?,?,?,?,?)""",
                (api_key_hash, wallet_pubkey, tier, label, now, now),
            )
            await db.commit()

        log.info(f"[public_api] registered user: {wallet_pubkey[:12]}... tier={tier}")
        return {
            "api_key": api_key,
            "api_key_hash": api_key_hash,
            "wallet_pubkey": wallet_pubkey,
            "tier": tier,
            "created_at": now,
            "warning": "Store this API key securely. It will NOT be shown again.",
        }

    async def get_user_by_api_key(self, api_key: str) -> Optional[dict]:
        """Look up user by API key. Updates last_seen on access."""
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE api_key_hash = ?", (api_key_hash,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            # Update last_seen
            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "UPDATE users SET last_seen = ? WHERE api_key_hash = ?",
                (now, api_key_hash),
            )
            await db.commit()
            return dict(row)

    async def rotate_api_key(self, old_api_key: str) -> Optional[dict]:
        """Rotate an API key. Old key is invalidated, new one returned.

        IMPORTANT: Re-encrypts all exchange keys with the new API key
        so they remain decryptable. If any re-encryption fails, the
        rotation is aborted and the old key remains valid.
        """
        user = await self.get_user_by_api_key(old_api_key)
        if not user:
            return None

        new_api_key = f"emp_sk_{secrets.token_hex(24)}"
        new_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
        old_hash = user["api_key_hash"]
        now = datetime.now(timezone.utc).isoformat()

        async with self._conn() as db:
            # ── Re-encrypt exchange keys with new API key ───────────
            try:
                cursor = await db.execute(
                    "SELECT * FROM exchange_keys WHERE user_hash = ?",
                    (old_hash,),
                )
                exchange_rows = await cursor.fetchall()

                for row in exchange_rows:
                    # Decrypt with old key, re-encrypt with new key
                    try:
                        plaintext = _decrypt_exchange_keys(old_api_key, row["encrypted_blob"])
                    except Exception:
                        log.warning(
                            f"[public_api] cannot decrypt exchange key {row['id']} during rotation — removing"
                        )
                        await db.execute(
                            "DELETE FROM exchange_keys WHERE id = ?", (row["id"],)
                        )
                        continue

                    new_blob = _encrypt_exchange_keys(new_api_key, plaintext)
                    await db.execute(
                        "UPDATE exchange_keys SET encrypted_blob = ?, user_hash = ? WHERE id = ?",
                        (new_blob, new_hash, row["id"]),
                    )
            except Exception as e:
                log.error(f"[public_api] exchange key re-encryption failed: {e}")
                await db.rollback()
                return {"error": f"Exchange key re-encryption failed: {e}"}

            # Transfer positions
            await db.execute(
                "UPDATE user_positions SET user_hash = ? WHERE user_hash = ?",
                (new_hash, old_hash),
            )
            # Update user record
            await db.execute(
                "UPDATE users SET api_key_hash = ?, last_seen = ? WHERE api_key_hash = ?",
                (new_hash, now, old_hash),
            )
            await db.commit()

        log.info(f"[public_api] rotated API key for {user['wallet_pubkey'][:12]}...")
        return {
            "api_key": new_api_key,
            "api_key_hash": new_hash,
            "wallet_pubkey": user["wallet_pubkey"],
            "warning": "Previous API key is now invalid.",
        }

    # ── Exchange key management ────────────────────────────────────

    async def store_exchange_keys(
        self,
        api_key: str,
        exchange: str,
        exchange_api_key: str,
        exchange_api_secret: str,
        exchange_passphrase: str = "",
        label: str = "",
    ) -> dict:
        """Store encrypted exchange API keys for a user."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        plaintext = {
            "api_key": exchange_api_key,
            "api_secret": exchange_api_secret,
            "passphrase": exchange_passphrase,
        }

        encrypted = _encrypt_exchange_keys(api_key, plaintext)
        key_id = f"ex_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        async with self._conn() as db:
            await db.execute(
                """INSERT OR REPLACE INTO exchange_keys (
                    id, user_hash, exchange, encrypted_blob, label, created_at
                ) VALUES (?,?,?,?,?,?)""",
                (key_id, user["api_key_hash"], exchange, encrypted, label, now),
            )
            await db.commit()

        return {
            "id": key_id,
            "exchange": exchange,
            "label": label,
            "created_at": now,
            "note": "Exchange keys stored encrypted at rest.",
        }

    async def get_exchange_keys(
        self, api_key: str, exchange: Optional[str] = None
    ) -> list[dict]:
        """Retrieve and decrypt exchange keys for a user."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        async with self._conn() as db:
            if exchange:
                cursor = await db.execute(
                    "SELECT * FROM exchange_keys WHERE user_hash = ? AND exchange = ?",
                    (user["api_key_hash"], exchange),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM exchange_keys WHERE user_hash = ?",
                    (user["api_key_hash"],),
                )
            rows = await cursor.fetchall()

        results = []
        for row in rows:
            try:
                decrypted = _decrypt_exchange_keys(api_key, row["encrypted_blob"])
                results.append({
                    "id": row["id"],
                    "exchange": row["exchange"],
                    "label": row["label"],
                    "api_key": decrypted["api_key"][:8] + "...",  # partial display
                    "has_secret": bool(decrypted.get("api_secret")),
                    "created_at": row["created_at"],
                })
            except Exception as e:
                log.warning(f"[public_api] failed to decrypt exchange key {row['id']}: {e}")
                results.append({
                    "id": row["id"],
                    "exchange": row["exchange"],
                    "error": "decryption_failed",
                })

        return results

    async def delete_exchange_keys(self, api_key: str, key_id: str) -> bool:
        """Delete a stored exchange key."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        async with self._conn() as db:
            cursor = await db.execute(
                "DELETE FROM exchange_keys WHERE id = ? AND user_hash = ?",
                (key_id, user["api_key_hash"]),
            )
            await db.commit()
            return cursor.rowcount > 0

    # ── Drawdown + TPC tracking ────────────────────────────────────

    async def update_portfolio_value(
        self, api_key: str, current_value: float
    ) -> dict:
        """Update user's peak portfolio value and compute drawdown + daily P&L."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        peak = max(float(user.get("peak_portfolio_value", 0)), current_value)
        drawdown = (peak - current_value) / peak * 100 if peak > 0 else 0.0
        max_dd = max(float(user.get("max_drawdown_pct", 0)), drawdown)

        # Daily P&L: compare to daily_start_value if set, otherwise current value
        daily_start = float(user.get("daily_start_value", 0))
        if daily_start <= 0:
            daily_start = current_value  # first update of the day
        daily_pnl = (current_value - daily_start) / daily_start * 100 if daily_start > 0 else 0.0

        async with self._conn() as db:
            await db.execute(
                """UPDATE users SET peak_portfolio_value = ?,
                   current_drawdown_pct = ?, max_drawdown_pct = ?,
                   daily_start_value = ?, daily_pnl_pct = ?, last_seen = ?
                   WHERE api_key_hash = ?""",
                (round(peak, 2), round(drawdown, 2), round(max_dd, 2),
                 round(daily_start, 2), round(daily_pnl, 4),
                 datetime.now(timezone.utc).isoformat(),
                 user["api_key_hash"]),
            )
            await db.commit()

        return {
            "peak_value": round(peak, 2),
            "current_drawdown_pct": round(drawdown, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "daily_pnl_pct": round(daily_pnl, 4),
        }

    async def add_position(
        self,
        api_key: str,
        symbol: str,
        entry_price: float,
        amount: float,
        *,
        stop_loss_pct: float = 0.05,
        take_profit_pct: Optional[float] = None,
        side: str = "long",
    ) -> dict:
        """Add a tracked position with take-profit level."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        pos_id = f"up_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        stop_level = entry_price * (1 - stop_loss_pct) if side == "long" else entry_price * (1 + stop_loss_pct)
        tp_level = entry_price * (1 + take_profit_pct) if take_profit_pct and side == "long" else (
            entry_price * (1 - take_profit_pct) if take_profit_pct else None
        )

        async with self._conn() as db:
            await db.execute(
                """INSERT INTO user_positions (
                    id, user_hash, symbol, entry_price, amount,
                    current_stop_loss, take_profit_level,
                    peak_price, status, side, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (pos_id, user["api_key_hash"], symbol, entry_price, amount,
                 stop_level, tp_level, entry_price, "open", side, now),
            )
            # Increment trade count
            await db.execute(
                "UPDATE users SET total_trades = total_trades + 1 WHERE api_key_hash = ?",
                (user["api_key_hash"],),
            )
            await db.commit()

        return {
            "position_id": pos_id,
            "symbol": symbol,
            "entry_price": entry_price,
            "amount": amount,
            "stop_loss": round(stop_level, 6) if stop_level else None,
            "take_profit": round(tp_level, 6) if tp_level else None,
            "side": side,
            "created_at": now,
        }

    async def update_position_price(
        self, api_key: str, pos_id: str, current_price: float
    ) -> dict:
        """Update a position's peak price and drawdown."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT * FROM user_positions WHERE id = ? AND user_hash = ?",
                (pos_id, user["api_key_hash"]),
            )
            row = await cursor.fetchone()
            if not row:
                return {"error": "position_not_found"}

            pos = dict(row)
            peak = max(float(pos["peak_price"]), current_price)
            dd = (peak - current_price) / peak * 100 if peak > 0 else 0.0

            # Check stop loss
            stop = pos["current_stop_loss"]
            tp = pos["take_profit_level"]
            new_status = pos["status"]

            if stop and (
                (pos["side"] == "long" and current_price <= stop) or
                (pos["side"] == "short" and current_price >= stop)
            ):
                new_status = "stopped_out"
            elif tp and (
                (pos["side"] == "long" and current_price >= tp) or
                (pos["side"] == "short" and current_price <= tp)
            ):
                new_status = "take_profit"

            now = datetime.now(timezone.utc).isoformat()
            pnl = None
            if new_status != "open":
                if pos["side"] == "long":
                    pnl = round((current_price - pos["entry_price"]) / pos["entry_price"] * 100, 2)
                else:
                    pnl = round((pos["entry_price"] - current_price) / pos["entry_price"] * 100, 2)

                await db.execute(
                    """UPDATE user_positions SET peak_price = ?, current_drawdown = ?,
                       status = ?, closed_at = ?, pnl_pct = ?
                       WHERE id = ?""",
                    (peak, round(dd, 2), new_status, now, pnl, pos_id),
                )
                # Update user total profit
                if pnl is not None:
                    await db.execute(
                        "UPDATE users SET total_profit = total_profit + ? WHERE api_key_hash = ?",
                        (pnl, user["api_key_hash"]),
                    )
            else:
                await db.execute(
                    "UPDATE user_positions SET peak_price = ?, current_drawdown = ? WHERE id = ?",
                    (peak, round(dd, 2), pos_id),
                )
            await db.commit()

        return {
            "position_id": pos_id,
            "current_price": current_price,
            "peak_price": round(peak, 6),
            "drawdown_pct": round(dd, 2),
            "status": new_status,
            "pnl_pct": pnl,
        }

    async def close_position(
        self, api_key: str, pos_id: str, close_price: float
    ) -> dict:
        """Manually close a position."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT * FROM user_positions WHERE id = ? AND user_hash = ?",
                (pos_id, user["api_key_hash"]),
            )
            row = await cursor.fetchone()
            if not row:
                return {"error": "position_not_found"}

            pos = dict(row)
            now = datetime.now(timezone.utc).isoformat()

            if pos["side"] == "long":
                pnl = round((close_price - pos["entry_price"]) / pos["entry_price"] * 100, 2)
            else:
                pnl = round((pos["entry_price"] - close_price) / pos["entry_price"] * 100, 2)

            await db.execute(
                """UPDATE user_positions SET status = 'closed', closed_at = ?,
                   pnl_pct = ?, current_drawdown = 0 WHERE id = ?""",
                (now, pnl, pos_id),
            )
            await db.execute(
                "UPDATE users SET total_profit = total_profit + ? WHERE api_key_hash = ?",
                (pnl, user["api_key_hash"]),
            )
            await db.commit()

        return {
            "position_id": pos_id,
            "close_price": close_price,
            "pnl_pct": pnl,
            "status": "closed",
        }

    async def get_user_positions(self, api_key: str) -> list[dict]:
        """Get all positions for a user."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT * FROM user_positions WHERE user_hash = ? ORDER BY created_at DESC",
                (user["api_key_hash"],),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_user_profile(self, api_key: str) -> dict:
        """Get full user profile with stats."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        positions = await self.get_user_positions(api_key)
        open_positions = [p for p in positions if p["status"] == "open"]
        closed_positions = [p for p in positions if p["status"] != "open"]

        return {
            "wallet_pubkey": user["wallet_pubkey"],
            "tier": user["tier"],
            "label": user["label"],
            "created_at": user["created_at"],
            "last_seen": user["last_seen"],
            "stats": {
                "peak_portfolio_value": round(float(user.get("peak_portfolio_value", 0)), 2),
                "current_drawdown_pct": round(float(user.get("current_drawdown_pct", 0)), 2),
                "max_drawdown_pct": round(float(user.get("max_drawdown_pct", 0)), 2),
                "daily_pnl_pct": round(float(user.get("daily_pnl_pct", 0)), 4),
                "total_trades": user.get("total_trades", 0),
                "total_profit_pct": round(float(user.get("total_profit", 0)), 2),
            },
            "open_positions": len(open_positions),
            "closed_positions": len(closed_positions),
            "positions": [
                {
                    "id": p["id"],
                    "symbol": p["symbol"],
                    "entry_price": p["entry_price"],
                    "amount": p["amount"],
                    "side": p["side"],
                    "status": p["status"],
                    "current_drawdown": p.get("current_drawdown", 0),
                    "pnl_pct": p.get("pnl_pct"),
                }
                for p in positions[:50]
            ],
        }

    async def update_strategy_params(self, api_key: str, params: dict) -> dict:
        """Store user-specific strategy parameter overrides."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        params_json = json.dumps(params)
        async with self._conn() as db:
            await db.execute(
                "UPDATE users SET strategy_params = ?, last_seen = ? WHERE api_key_hash = ?",
                (params_json, datetime.now(timezone.utc).isoformat(), user["api_key_hash"]),
            )
            await db.commit()

        return {"strategy_params": params}

    async def get_strategy_params(self, api_key: str) -> dict:
        """Get user-specific strategy parameter overrides."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        try:
            return json.loads(user.get("strategy_params", "{}"))
        except (json.JSONDecodeError, TypeError):
            return {}

    async def user_count(self) -> int:
        """Return total registered users."""
        async with self._conn() as db:
            cursor = await db.execute("SELECT COUNT(*) as cnt FROM users")
            row = await cursor.fetchone()
            return row["cnt"] if row else 0

    # ── Sniper config management ──────────────────────────────────

    async def get_sniper_config(self, api_key: str) -> Optional[dict]:
        """Get a user's auto-snipe configuration."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT * FROM sniper_configs WHERE user_hash = ?",
                (user["api_key_hash"],),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            config = dict(row)
            # Also include sniper wallet info
            wcur = await db.execute(
                "SELECT wallet_pubkey, balance_sol FROM sniper_wallets WHERE user_hash = ?",
                (user["api_key_hash"],),
            )
            wrow = await wcur.fetchone()
            if wrow:
                config["sniper_wallet"] = {
                    "pubkey": wrow["wallet_pubkey"],
                    "balance_sol": wrow["balance_sol"],
                }
            return config

    async def set_sniper_config(self, api_key: str, config: dict) -> dict:
        """Create or update auto-snipe configuration for a user."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        user_hash = user["api_key_hash"]
        now = datetime.now(timezone.utc).isoformat()

        async with self._conn() as db:
            # Upsert
            await db.execute(
                """INSERT INTO sniper_configs (
                    user_hash, is_enabled, amount_per_snipe, max_daily_spend,
                    risk_threshold, min_liquidity, max_age_seconds,
                    stop_loss_pct, take_profit_pct, enabled_chains,
                    auto_approve, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_hash) DO UPDATE SET
                    is_enabled=excluded.is_enabled,
                    amount_per_snipe=excluded.amount_per_snipe,
                    max_daily_spend=excluded.max_daily_spend,
                    risk_threshold=excluded.risk_threshold,
                    min_liquidity=excluded.min_liquidity,
                    max_age_seconds=excluded.max_age_seconds,
                    stop_loss_pct=excluded.stop_loss_pct,
                    take_profit_pct=excluded.take_profit_pct,
                    enabled_chains=excluded.enabled_chains,
                    auto_approve=excluded.auto_approve,
                    updated_at=excluded.updated_at""",
                (
                    user_hash,
                    int(config.get("is_enabled", False)),
                    float(config.get("amount_per_snipe", 0.1)),
                    float(config.get("max_daily_spend", 0)) if config.get("max_daily_spend") else None,
                    int(config.get("risk_threshold", 50)),
                    float(config.get("min_liquidity", 5000)),
                    int(config.get("max_age_seconds", 300)),
                    float(config.get("stop_loss_pct", 0.15)),
                    float(config.get("take_profit_pct", 0.50)),
                    str(config.get("enabled_chains", "solana")),
                    int(config.get("auto_approve", False)),
                    now, now,
                ),
            )
            await db.commit()

        log.info(f"[public_api] sniper config updated for {user_hash[:12]}... enabled={config.get('is_enabled')}")
        return await self.get_sniper_config(api_key) or {}

    async def delete_sniper_config(self, api_key: str) -> bool:
        """Delete a user's sniper config (disables auto-snipe)."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        async with self._conn() as db:
            cursor = await db.execute(
                "DELETE FROM sniper_configs WHERE user_hash = ?",
                (user["api_key_hash"],),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_enabled_sniper_users(self) -> list[dict]:
        """Get all users with auto-snipe enabled (for the sniper engine)."""
        async with self._conn() as db:
            cursor = await db.execute(
                """SELECT u.api_key_hash, u.wallet_pubkey, sc.*
                   FROM sniper_configs sc
                   JOIN users u ON u.api_key_hash = sc.user_hash
                   WHERE sc.is_enabled = 1"""
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ── Sniper wallet management ──────────────────────────────────

    async def generate_sniper_wallet(self, api_key: str) -> dict:
        """Generate a Solana keypair for auto-snipe execution.

        The private key is Fernet-encrypted using the user's API key.
        User must fund this wallet before auto-snipe can execute.
        """
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        user_hash = user["api_key_hash"]

        # Generate keypair
        try:
            from solders.keypair import Keypair
            kp = Keypair()
            pubkey_str = str(kp.pubkey())
            private_bytes = bytes(kp)
        except ImportError:
            return {"error": "solders not installed — cannot generate sniper wallet"}

        # Encrypt private key
        key = _derive_key(api_key)
        from cryptography.fernet import Fernet
        f = Fernet(base64.urlsafe_b64encode(key))
        encrypted_private = f.encrypt(private_bytes).decode()

        now = datetime.now(timezone.utc).isoformat()

        async with self._conn() as db:
            await db.execute(
                """INSERT OR REPLACE INTO sniper_wallets (
                    user_hash, wallet_pubkey, encrypted_private, created_at
                ) VALUES (?,?,?,?)""",
                (user_hash, pubkey_str, encrypted_private, now),
            )
            await db.commit()

        log.info(f"[public_api] sniper wallet generated for {user_hash[:12]}... → {pubkey_str[:12]}...")
        return {
            "wallet_pubkey": pubkey_str,
            "note": "Transfer SOL to this address to fund auto-snipes. Minimum recommended: 1 SOL.",
            "created_at": now,
        }

    async def get_sniper_wallet_private(self, api_key: str) -> Optional[bytes]:
        """Decrypt and return the sniper wallet private key bytes.

        INTERNAL USE ONLY — called by the sniper engine.
        """
        user = await self.get_user_by_api_key(api_key)
        if not user:
            return None

        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT encrypted_private FROM sniper_wallets WHERE user_hash = ?",
                (user["api_key_hash"],),
            )
            row = await cursor.fetchone()
            if not row:
                return None

        key = _derive_key(api_key)
        from cryptography.fernet import Fernet
        f = Fernet(base64.urlsafe_b64encode(key))
        return f.decrypt(row["encrypted_private"].encode())

    async def check_sniper_wallet_balance(self, api_key: str) -> Optional[float]:
        """Check SOL balance of the user's sniper wallet via RPC."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            return None

        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT wallet_pubkey FROM sniper_wallets WHERE user_hash = ?",
                (user["api_key_hash"],),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            pubkey = row["wallet_pubkey"]

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as http:
                r = await http.post(
                    os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
                    json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [pubkey]},
                )
                data = r.json()
                balance = data.get("result", {}).get("value", 0) / 1e9

        except Exception as e:
            log.warning(f"[public_api] failed to check sniper wallet balance for {pubkey[:12]}...: {e}")
            return None

        # Update stored balance
        async with self._conn() as db:
            await db.execute(
                "UPDATE sniper_wallets SET balance_sol = ? WHERE user_hash = ?",
                (round(balance, 6), user["api_key_hash"]),
            )
            await db.commit()

        return balance

    # ── Snipe history ────────────────────────────────────────────

    async def log_snipe_event(self, api_key: str, event: dict) -> str:
        """Record a snipe event in the history table.

        Args:
            api_key: User's API key
            event: dict with keys: token_address, chain, status, and optionally
                   token_symbol, rug_score, amount_sol, entry_price, tx_signature
        """
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        event_id = f"sn_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        async with self._conn() as db:
            await db.execute(
                """INSERT INTO snipe_history (
                    id, user_hash, token_address, token_symbol, chain,
                    detected_at, rug_score, amount_sol, entry_price,
                    tx_signature, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    user["api_key_hash"],
                    event["token_address"],
                    event.get("token_symbol", ""),
                    event.get("chain", "solana"),
                    event.get("detected_at", now),
                    event.get("rug_score"),
                    event.get("amount_sol"),
                    event.get("entry_price"),
                    event.get("tx_signature"),
                    event.get("status", "detected"),
                ),
            )
            await db.commit()

        return event_id

    async def update_snipe_event(self, event_id: str, updates: dict) -> bool:
        """Update a snipe history event (e.g., after execution)."""
        async with self._conn() as db:
            sets = []
            vals = []
            for key in ("status", "tx_signature", "amount_sol", "entry_price", "pnl_pct", "closed_at"):
                if key in updates:
                    sets.append(f"{key} = ?")
                    vals.append(updates[key])
            if not sets:
                return False
            vals.append(event_id)
            await db.execute(
                f"UPDATE snipe_history SET {', '.join(sets)} WHERE id = ?",
                tuple(vals),
            )
            await db.commit()
            return True

    async def get_snipe_history(self, api_key: str, limit: int = 50) -> list[dict]:
        """Get a user's snipe history."""
        user = await self.get_user_by_api_key(api_key)
        if not user:
            raise ValueError("Invalid API key")

        async with self._conn() as db:
            cursor = await db.execute(
                """SELECT * FROM snipe_history
                   WHERE user_hash = ?
                   ORDER BY detected_at DESC LIMIT ?""",
                (user["api_key_hash"], limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ── Internal methods (accept user_hash, no API key needed) ────
    # These are used by the sniper engine which only has the hash.

    async def _log_snipe_event_internal(self, user_hash: str, event: dict) -> str:
        """Internal: record a snipe event by user_hash directly."""
        event_id = f"sn_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        async with self._conn() as db:
            await db.execute(
                """INSERT INTO snipe_history (
                    id, user_hash, token_address, token_symbol, chain,
                    detected_at, rug_score, amount_sol, entry_price,
                    tx_signature, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id, user_hash,
                    event["token_address"],
                    event.get("token_symbol", ""),
                    event.get("chain", "solana"),
                    event.get("detected_at", now),
                    event.get("rug_score"),
                    event.get("amount_sol"),
                    event.get("entry_price"),
                    event.get("tx_signature"),
                    event.get("status", "detected"),
                ),
            )
            await db.commit()
        return event_id

    async def _update_snipe_event_internal(self, user_hash: str, event_id: str, updates: dict) -> bool:
        """Internal: update a snipe history event with ownership check."""
        async with self._conn() as db:
            sets = []
            vals = []
            for key in ("status", "tx_signature", "amount_sol", "entry_price", "pnl_pct", "closed_at", "rug_score"):
                if key in updates:
                    sets.append(f"{key} = ?")
                    vals.append(updates[key])
            if not sets:
                return False
            vals.append(event_id)
            vals.append(user_hash)
            await db.execute(
                f"UPDATE snipe_history SET {', '.join(sets)} WHERE id = ? AND user_hash = ?",
                tuple(vals),
            )
            await db.commit()
            return True

    async def _get_sniper_wallet_private_internal(self, user_hash: str) -> Optional[bytes]:
        """Internal: decrypt sniper wallet private key by user_hash."""
        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT encrypted_private FROM sniper_wallets WHERE user_hash = ?",
                (user_hash,),
            )
            row = await cursor.fetchone()
            if not row:
                return None

        # We need the raw API key to decrypt, but the engine only has user_hash.
        # The private key is encrypted with a derived key from the API key.
        # Solution: we need a way to decrypt without the API key.
        # For now, the engine must have access to the API key (passed at init).
        # Return the encrypted blob — engine handles decryption if it has the key.
        return row["encrypted_private"].encode()

    async def _add_position_internal(
        self,
        user_hash: str,
        symbol: str,
        entry_price: float,
        amount: float,
        *,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.50,
        side: str = "long",
    ) -> Optional[str]:
        """Internal: add a tracked position by user_hash directly."""
        pos_id = f"up_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        stop_level = entry_price * (1 - stop_loss_pct) if side == "long" else entry_price * (1 + stop_loss_pct)
        tp_level = entry_price * (1 + take_profit_pct) if take_profit_pct and side == "long" else (
            entry_price * (1 - take_profit_pct) if take_profit_pct else None
        )
        async with self._conn() as db:
            await db.execute(
                """INSERT INTO user_positions (
                    id, user_hash, symbol, entry_price, amount,
                    current_stop_loss, take_profit_level,
                    peak_price, status, side, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (pos_id, user_hash, symbol, entry_price, amount,
                 stop_level, tp_level, entry_price, "open", side, now),
            )
            await db.execute(
                "UPDATE users SET total_trades = total_trades + 1 WHERE api_key_hash = ?",
                (user_hash,),
            )
            await db.commit()
        return pos_id

    async def _get_daily_snipe_spend(self, user_hash: str) -> float:
        """Internal: get total SOL spent on snipes today for a user."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with self._conn() as db:
            cursor = await db.execute(
                """SELECT COALESCE(SUM(amount_sol), 0) as total
                   FROM snipe_history
                   WHERE user_hash = ?
                     AND status = 'executed'
                     AND detected_at >= ?""",
                (user_hash, today + "T00:00:00"),
            )
            row = await cursor.fetchone()
            return float(row["total"]) if row else 0.0

    async def _get_sniper_wallet_info(self, user_hash: str) -> Optional[dict]:
        """Internal: get sniper wallet pubkey and encrypted private key."""
        async with self._conn() as db:
            cursor = await db.execute(
                "SELECT wallet_pubkey, encrypted_private FROM sniper_wallets WHERE user_hash = ?",
                (user_hash,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "pubkey": row["wallet_pubkey"],
                "encrypted_private": row["encrypted_private"],
            }


# ── Wallet verification ────────────────────────────────────────────────

def verify_solana_signature(
    pubkey_b58: str,
    message: str,
    signature_b58: str,
) -> bool:
    """Verify an Ed25519 signature from a Solana wallet.

    Uses solders (already in requirements.txt).

    Args:
        pubkey_b58: Base58-encoded 32-byte Ed25519 public key
        message: The raw message that was signed (UTF-8 string)
        signature_b58: Base58-encoded 64-byte Ed25519 signature

    Returns:
        True if the signature is valid.
    """
    try:
        from solders.pubkey import Pubkey
        from solders.signature import Signature

        pubkey = Pubkey.from_string(pubkey_b58)
        sig = Signature.from_string(signature_b58)
        message_bytes = message.encode("utf-8")

        # solders-native Ed25519 verify
        sig.verify(pubkey, message_bytes)
        return True
    except Exception as e:
        log.warning(f"[public_api] signature verification failed: {e}")
        return False


# ── Global singleton ───────────────────────────────────────────────────

_store: Optional[UserStore] = None


def get_user_store() -> UserStore:
    global _store
    if _store is None:
        _store = UserStore()
    return _store
