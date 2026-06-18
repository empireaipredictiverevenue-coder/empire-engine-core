"""
PREDICITIVE TRADING BOT · MEME SNIPER WORKER
=============================================
Auto-snipe engine that connects the sniper pipeline to the public API.

Architecture:
  - AutoSnipeEngine: in-process asyncio background loop
  - Reads enabled user configs from UserStore (sniper_configs table)
  - Watches for new tokens via Helius WebSocket or RPC polling
  - Per-user pipeline: scan → rug check → risk threshold → swap
  - Posts snipe events via callback (wired to WebSocket manager)
  - Sniper wallets: bot-generated + Fernet-encrypted, user-funded
  - Daily spend enforcement: max_daily_spend checked per-user before snipe

Lifecycle:
  engine = AutoSnipeEngine()
  engine.set_event_callback(ws_manager.broadcast_snipe_event)
  await engine.start()
  # ... runs in background ...
  await engine.stop()

Configuration per user (from sniper_configs table):
  - amount_per_snipe: SOL amount per snipe (default 0.1)
  - risk_threshold: max rug score to snipe (default 50, lower = safer)
  - min_liquidity: minimum pool liquidity in USD
  - max_age_seconds: max token age to consider
  - stop_loss_pct / take_profit_pct: auto-SL/TP
  - auto_approve: if True, skip manual approval
  - enabled_chains: comma-separated (solana, ethereum, base)
  - max_daily_spend: SOL spending cap per day (enforced by engine)
"""

import os
import json
import time
import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Optional, Any, Callable, Awaitable

import httpx

log = logging.getLogger("trading.sniper_worker")

# ── Configuration ──────────────────────────────────────────────────────

SCAN_INTERVAL_SEC = float(os.environ.get("SNIPER_SCAN_INTERVAL", "5.0"))
HELIUS_WS_URL = os.environ.get(
    "HELIUS_WS_URL",
    "wss://atlas-mainnet.helius-rpc.com/?api-key=" + os.environ.get("HELIUS_API_KEY", ""),
)
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"
WSOL_MINT = "So11111111111111111111111111111111111111112"

# Event callback type: async Callable(user_hash, event_dict) -> None
EventCallback = Callable[[str, dict], Awaitable[None]]


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-SNIPE ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class AutoSnipeEngine:
    """Background engine that auto-snipes meme coins per user config."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._event_callback: Optional[EventCallback] = None
        self._scan_count = 0
        self._snipe_count = 0
        self._http: Optional[httpx.AsyncClient] = None
        self._last_scan_at: Optional[str] = None
        self._known_tokens: set[str] = set()  # dedup across scans

    # ── Lifecycle ─────────────────────────────────────────────────

    def set_event_callback(self, callback: EventCallback) -> None:
        """Set callback for snipe events (→ WebSocket broadcast)."""
        self._event_callback = callback

    async def start(self) -> None:
        """Start the auto-snipe engine background loop."""
        if self._running:
            log.warning("[sniper] engine already running")
            return
        self._running = True
        self._http = httpx.AsyncClient(timeout=15)
        self._task = asyncio.create_task(self._run_loop())
        log.info("[sniper] engine started — scanning every %.1fs", SCAN_INTERVAL_SEC)

    async def stop(self) -> None:
        """Stop the auto-snipe engine."""
        self._running = False
        self._api_keys.clear()  # clear decryption key cache
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._http:
            await self._http.aclose()
            self._http = None
        log.info("[sniper] engine stopped — %d scans, %d snipes", self._scan_count, self._snipe_count)

    async def _run_loop(self) -> None:
        """Main loop: fetch enabled users → scan for tokens → evaluate → snipe."""
        from .public_api import get_user_store
        store = get_user_store()

        while self._running:
            try:
                # Get all enabled sniper users
                users = await store.get_enabled_sniper_users()
                if not users:
                    await asyncio.sleep(SCAN_INTERVAL_SEC)
                    continue

                # Scan for new tokens
                tokens = await self._scan_new_tokens()
                self._scan_count += 1
                self._last_scan_at = datetime.now(timezone.utc).isoformat()

                if tokens:
                    log.info("[sniper] scan #%d: %d new tokens found", self._scan_count, len(tokens))

                # Evaluate each token against each user's config
                for token_data in tokens:
                    for user in users:
                        if not self._running:
                            break
                        try:
                            await self._evaluate_token_for_user(
                                store, user, token_data
                            )
                        except Exception as e:
                            log.error(
                                "[sniper] eval error user=%s token=%s: %s",
                                user.get("api_key_hash", "?")[:12],
                                token_data.get("address", "?")[:16],
                                e,
                            )

                await asyncio.sleep(SCAN_INTERVAL_SEC)

            except asyncio.CancelledError:
                self._running = False
                break
            except Exception as e:
                log.error("[sniper] loop error: %s", e)
                await asyncio.sleep(SCAN_INTERVAL_SEC * 3)

    # ── Token scanning ────────────────────────────────────────────

    async def _scan_new_tokens(self) -> list[dict]:
        """Scan for new meme coin tokens on Solana DEXs.

        Uses Helius RPC getProgramAccounts for Raydium pools.
        Falls back to a simulated scan if Helius is unavailable.
        In production, use Helius WebSocket logsSubscribe for <1s detection.
        """
        tokens = []
        try:
            # Try Helius RPC scan
            rpc_url = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
            r = await self._http.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getProgramAccounts",
                    "params": [
                        "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium
                        {
                            "encoding": "jsonParsed",
                            "filters": [{"dataSize": 165}],
                        },
                    ],
                },
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                accounts = data.get("result", [])
                for acct in accounts[:30]:
                    address = acct.get("pubkey", "")
                    if address and address not in self._known_tokens:
                        self._known_tokens.add(address)
                        tokens.append({
                            "address": address,
                            "source": "raydium",
                            "chain": "solana",
                            "detected_at": datetime.now(timezone.utc).isoformat(),
                        })
        except Exception as e:
            log.debug("[sniper] Helius RPC scan failed: %s", e)

        # Keep known_tokens bounded
        if len(self._known_tokens) > 10_000:
            self._known_tokens = set(list(self._known_tokens)[-2000:])

        return tokens

    # ── Per-user token evaluation ────────────────────────────────

    async def _evaluate_token_for_user(
        self,
        store,
        user: dict,
        token_data: dict,
    ) -> None:
        """Run the sniper pipeline for a single user + token.

        Uses internal UserStore methods (accept user_hash directly) since
        the engine only has the hashed API key, not the raw key.
        """
        user_hash = user.get("api_key_hash", user.get("user_hash", ""))
        token_address = token_data.get("address", "")

        if not token_address or not user_hash:
            return

        # Check chain compatibility
        enabled_chains = (user.get("enabled_chains", "solana") or "solana").split(",")
        if token_data.get("chain", "solana") not in enabled_chains:
            return

        # Check token age
        max_age = int(user.get("max_age_seconds", 300))
        detected = token_data.get("detected_at", "")
        if detected and max_age < 3600:  # skip age check for very old tokens
            try:
                detected_dt = datetime.fromisoformat(detected)
                age_sec = (datetime.now(timezone.utc) - detected_dt).total_seconds()
                if age_sec > max_age:
                    return
            except (ValueError, TypeError):
                pass

        # ── Daily spend enforcement ──
        max_daily = float(user.get("max_daily_spend", 0) or 0)
        if max_daily > 0:
            spent_today = await store._get_daily_snipe_spend(user_hash)
            amount_per = float(user.get("amount_per_snipe", 0.1))
            if spent_today + amount_per > max_daily:
                log.debug(
                    "[sniper] user %s daily cap reached: spent %.3f of %.3f SOL",
                    user_hash[:12], spent_today, max_daily,
                )
                return

        # ── Log detection event (internal method — uses user_hash) ──
        event_id = await store._log_snipe_event_internal(
            user_hash=user_hash,
            event={
                "token_address": token_address,
                "chain": token_data.get("chain", "solana"),
                "status": "detected",
                "detected_at": token_data.get("detected_at"),
            },
        )

        # ── Fire event: snipe_detected ──
        await self._fire_event(user_hash, {
            "type": "snipe_detected",
            "token_address": token_address,
            "chain": token_data.get("chain", "solana"),
            "source": token_data.get("source", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": event_id,
        })

        # ── Rug check ──
        rug_score = 100  # default: unknown = risky
        rug_details = {}
        try:
            from .trading_skills import RugDetectSkill
            from .base import SkillInput

            rug_skill = RugDetectSkill()
            rug_out = await rug_skill.run(SkillInput(params={
                "token_address": token_address,
            }))
            if rug_out.success:
                rug_score = rug_out.data.get("risk_score", 100)
                rug_details = rug_out.data.get("checks", {})
        except Exception as e:
            log.debug("[sniper] rug check failed for %s: %s", token_address[:12], e)

        # Check against user's risk threshold
        risk_threshold = int(user.get("risk_threshold", 50))
        if rug_score > risk_threshold:
            await self._fire_event(user_hash, {
                "type": "snipe_rug_blocked",
                "token_address": token_address,
                "rug_score": rug_score,
                "threshold": risk_threshold,
                "reason": f"Rug score {rug_score} exceeds threshold {risk_threshold}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_id": event_id,
            })
            await store._update_snipe_event_internal(
                user_hash, event_id, {"status": "rug_blocked", "rug_score": rug_score}
            )
            return

        # ── Check minimum liquidity ──
        min_liquidity = float(user.get("min_liquidity", 5000))
        try:
            pool_liquidity = await self._check_pool_liquidity(token_address)
            if pool_liquidity is not None and pool_liquidity < min_liquidity:
                await self._fire_event(user_hash, {
                    "type": "snipe_rug_blocked",
                    "token_address": token_address,
                    "rug_score": rug_score,
                    "reason": f"Liquidity ${pool_liquidity:.0f} below minimum ${min_liquidity:.0f}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event_id": event_id,
                })
                await store._update_snipe_event_internal(
                    user_hash, event_id, {"status": "low_liquidity", "rug_score": rug_score}
                )
                return
        except Exception as e:
            log.debug("[sniper] liquidity check failed for %s: %s", token_address[:12], e)

        # ── Check auto-approve ──
        auto_approve = bool(int(user.get("auto_approve", 0)))
        if not auto_approve:
            await self._fire_event(user_hash, {
                "type": "snipe_requires_approval",
                "token_address": token_address,
                "rug_score": rug_score,
                "checks": {k: v.get("status", "unknown") for k, v in rug_details.items()},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_id": event_id,
            })
            await store._update_snipe_event_internal(
                user_hash, event_id, {"status": "waiting_approval", "rug_score": rug_score}
            )
            return

        # ── Execute snipe ──
        await self._fire_event(user_hash, {
            "type": "snipe_executing",
            "token_address": token_address,
            "amount_sol": float(user.get("amount_per_snipe", 0.1)),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": event_id,
        })

        await self._execute_snipe(store, user, user_hash, token_address, event_id, rug_score)

    # ── Snipe execution ──────────────────────────────────────────

    async def _execute_snipe(
        self,
        store,
        user: dict,
        user_hash: str,
        token_address: str,
        event_id: str,
        rug_score: int,
    ) -> None:
        """Execute a Solana token swap via Jupiter aggregator.

        Signs with the user's sniper wallet private key (decrypted from
        sniper_wallets table). Falls back to SNIPER_MASTER_KEY env var
        if per-user wallet is unavailable.
        """
        amount_sol = float(user.get("amount_per_snipe", 0.1))
        slippage_bps = 100  # 1% for meme coins
        stop_loss_pct = float(user.get("stop_loss_pct", 0.15))
        take_profit_pct = float(user.get("take_profit_pct", 0.50))

        quote_success = False
        entry_price = None
        tx_sig = None

        # ── Get Jupiter quote ──
        try:
            quote_params = {
                "inputMint": WSOL_MINT,
                "outputMint": token_address,
                "amount": int(amount_sol * 1e9),
                "slippageBps": slippage_bps,
            }
            qs_parts = [f"{k}={v}" for k, v in quote_params.items()]
            qs = "&".join(qs_parts)
            r = await self._http.get(
                f"{JUPITER_QUOTE_API}?{qs}",
                timeout=10,
            )
            if r.status_code == 200:
                quote = r.json()
                out_amount = int(quote.get("outAmount", 0))
                if out_amount > 0:
                    entry_price = amount_sol / (out_amount / (10 ** (quote.get("decimals", 9) or 9)))
                    quote_success = True
        except Exception as e:
            log.warning("[sniper] Jupiter quote failed: %s", e)

        if not quote_success:
            await self._fire_event(user_hash, {
                "type": "snipe_failed",
                "token_address": token_address,
                "reason": "No route found on Jupiter",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_id": event_id,
            })
            await store._update_snipe_event_internal(user_hash, event_id, {"status": "failed"})
            return

        # ── Build + sign + send transaction ──
        try:
            # Get swap transaction from Jupiter
            swap_body = {
                "quoteResponse": quote,
                "userPublicKey": user.get("sniper_wallet_pubkey", ""),
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": "auto",
            }
            swap_r = await self._http.post(
                JUPITER_SWAP_API,
                json=swap_body,
                timeout=15,
            )
            if swap_r.status_code != 200:
                raise RuntimeError(f"Jupiter swap API returned {swap_r.status_code}")

            swap_data = swap_r.json()
            swap_tx_b64 = swap_data.get("swapTransaction")
            if not swap_tx_b64:
                raise RuntimeError("No swapTransaction in Jupiter response")

            # Decode transaction, sign with sniper wallet, send
            from solders.transaction import VersionedTransaction
            from solders.keypair import Keypair
            from solana.rpc.api import Client as SolanaClient
            from base64 import b64decode, b64encode
            from solders.commitment import Commitment

            tx = VersionedTransaction.from_bytes(b64decode(swap_tx_b64))

            # Get sniper wallet private key — per-user wallet only
            signing_key_bytes = None
            wallet_info = await store._get_sniper_wallet_info(user_hash)
            if wallet_info:
                encrypted = wallet_info["encrypted_private"]
                if self._api_keys and user_hash in self._api_keys:
                    from .public_api import _derive_key
                    from cryptography.fernet import Fernet as _Fernet
                    key = _derive_key(self._api_keys[user_hash])
                    f = _Fernet(base64.urlsafe_b64encode(key))
                    signing_key_bytes = f.decrypt(encrypted.encode())

            if not signing_key_bytes:
                await store._update_snipe_event_internal(user_hash, event_id, {"status": "tx_failed"})
                return

            kp = Keypair.from_bytes(signing_key_bytes)

            # Sign the transaction
            from solders.message import to_bytes_versioned
            message = to_bytes_versioned(tx.message)
            sig = kp.sign_message(message)
            tx.signatures.append(sig)

            # Send
            solana_client = SolanaClient(
                os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
                commitment=Commitment("confirmed"),
            )
            tx_bytes = bytes(tx)
            send_resp = solana_client.send_raw_transaction(tx_bytes)
            tx_sig = str(send_resp.value)

        except Exception as e:
            log.warning("[sniper] transaction signing/sending failed: %s", e)

        if tx_sig:
            # Success
            self._snipe_count += 1
            await self._fire_event(user_hash, {
                "type": "snipe_success",
                "token_address": token_address,
                "amount_sol": amount_sol,
                "entry_price": entry_price,
                "tx_signature": tx_sig,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_id": event_id,
            })
            await store._update_snipe_event_internal(user_hash, event_id, {
                "status": "executed",
                "amount_sol": amount_sol,
                "entry_price": entry_price,
                "tx_signature": tx_sig,
            })
            # Add as tracked position with SL/TP (internal — uses user_hash)
            if entry_price:
                await store._add_position_internal(
                    user_hash=user_hash,
                    symbol=token_address,
                    entry_price=entry_price,
                    amount=amount_sol,
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                    side="long",
                )
        else:
            await self._fire_event(user_hash, {
                "type": "snipe_failed",
                "token_address": token_address,
                "reason": "Transaction signing failed — no signing key configured",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_id": event_id,
            })
            await store._update_snipe_event_internal(user_hash, event_id, {"status": "tx_failed"})

    # ── Liquidity check ───────────────────────────────────────────

    async def _check_pool_liquidity(self, token_address: str) -> Optional[float]:
        """Check pool liquidity for a token via Jupiter price API.

        Uses price * 24h volume as a liquidity proxy since Jupiter
        price API doesn't expose pool TVL directly.
        """
        try:
            r = await self._http.get(
                f"https://price.jup.ag/v6/price?ids={token_address}",
                timeout=8,
            )
            if r.status_code == 200:
                data = r.json()
                token_data = data.get("data", {}).get(token_address, {})
                price = float(token_data.get("price", 0))
                volume_24h = float(data.get("volume24h", 0))
                if price and volume_24h:
                    return price * volume_24h
                return None
        except Exception:
            pass
        return None

    # ── API key management for decryption ────────────────────────

    # The sniper engine needs raw API keys to decrypt per-user sniper
    # wallet private keys. These are provided at snipe-time via the
    # REST endpoint (user starts sniper → engine caches their API key).
    # Keys are stored in memory only, never persisted.

    _api_keys: dict[str, str] = {}  # user_hash → raw_api_key

    def set_api_key(self, user_hash: str, api_key: str) -> None:
        """Cache a user's API key for sniper wallet decryption."""
        self._api_keys[user_hash] = api_key

    def clear_api_key(self, user_hash: str) -> None:
        """Remove a user's cached API key (e.g., on sniper stop)."""
        self._api_keys.pop(user_hash, None)

    # ── Event dispatch ────────────────────────────────────────────

    async def _fire_event(self, user_hash: str, event: dict) -> None:
        """Fire a snipe event to the registered callback (→ WebSocket)."""
        if self._event_callback:
            try:
                await self._event_callback(user_hash, event)
            except Exception as e:
                log.error("[sniper] event callback failed: %s", e)

    # ── Status ───────────────────────────────────────────────────

    @property
    def status(self) -> dict:
        return {
            "running": self._running,
            "scan_count": self._scan_count,
            "snipe_count": self._snipe_count,
            "last_scan_at": self._last_scan_at,
            "scan_interval_sec": SCAN_INTERVAL_SEC,
        }


# ── Global singleton ───────────────────────────────────────────────────

_engine: Optional[AutoSnipeEngine] = None


def get_sniper_engine() -> AutoSnipeEngine:
    global _engine
    if _engine is None:
        _engine = AutoSnipeEngine()
    return _engine
