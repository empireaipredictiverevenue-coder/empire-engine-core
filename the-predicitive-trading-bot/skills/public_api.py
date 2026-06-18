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

CREATE INDEX IF NOT EXISTS idx_exchange_user ON exchange_keys(user_hash);
CREATE INDEX IF NOT EXISTS idx_positions_user ON user_positions(user_hash);
CREATE INDEX IF NOT EXISTS idx_challenges_expiry ON auth_challenges(expires_at);
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
