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
import re
import json
import math
import time
import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Optional, Any, Callable, Awaitable

import httpx
import websockets

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

# ── DEX Program IDs for WebSocket log monitoring ──────────────────────
# Raydium AMM
RAYDIUM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
# PumpFun
PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
# Meteora DLMM
METEORA_PROGRAM = "LBUZKhRxPF3XUp3B63Gk53K112N215m5y2pT4rSpR1T"

# ── Jito MEV Protection Configuration ──────────────────────────────
# Block Engine endpoint for submitting bundles (replace with your regional endpoint)
JITO_BUNDLE_ENDPOINT = os.environ.get(
    "JITO_BUNDLE_ENDPOINT",
    "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
)
# Jito tip accounts (any will work — rotated periodically by Jito)
JITO_TIP_ACCOUNTS = [
    "Cw8PF4NQqW3tP3EpsJCiMGmFQSsWSCjYmKVB5cRXBbbi",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
]
# Default Jito tip in SOL (dynamically scaled by _compute_jito_tip)
JITO_DEFAULT_TIP_SOL = float(os.environ.get("JITO_DEFAULT_TIP_SOL", "0.005"))
JITO_MAX_TIP_SOL = float(os.environ.get("JITO_MAX_TIP_SOL", "0.02"))

# Log patterns that indicate a new pool/token creation
_RE_INIT_PATTERN = re.compile(r"Instruction:\s*(Initialize2|initialize2|create|Create|initialize_pool|InitializePool)")

# Event callback type: async Callable(user_hash, event_dict) -> None
EventCallback = Callable[[str, dict], Awaitable[None]]


# ═══════════════════════════════════════════════════════════════════════════
# HELIUS WEBSOCKET STREAM DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

class HeliusStreamDetector:
    """WebSocket-based token detector using Helius logsSubscribe.

    Subscribes to logs from major Solana DEX programs (Raydium, PumpFun, Meteora)
    and detects new pool/token creations in <1 second — vs 5s polling with RPC.

    When a relevant log pattern is found (e.g. "Instruction: Initialize2"), it
    fetches the full transaction via RPC to extract the token mint address, then
    pushes the detection onto an asyncio.Queue for the engine to process.

    Reconnects automatically with exponential backoff on WebSocket drops.
    """

    def __init__(
        self,
        ws_url: str,
        token_queue: asyncio.Queue,
        http_client: httpx.AsyncClient,
    ):
        self._ws_url = ws_url
        self._queue = token_queue
        self._http = http_client
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # Dedup by signature so we don't double-report the same launch
        self._known_sigs: set[str] = set()
        self._connection_errors = 0
        self._tokens_detected = 0

    async def start(self) -> None:
        """Start the WebSocket detector background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        log.info("[sniper] HeliusStreamDetector started")

    async def stop(self) -> None:
        """Stop the WebSocket detector."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("[sniper] HeliusStreamDetector stopped — %d tokens detected", self._tokens_detected)

    async def _run(self) -> None:
        """Main loop: connect → subscribe → listen → reconnect on failure."""
        programs = [RAYDIUM_PROGRAM, PUMPFUN_PROGRAM, METEORA_PROGRAM]
        program_labels = {
            RAYDIUM_PROGRAM: "raydium",
            PUMPFUN_PROGRAM: "pumpfun",
            METEORA_PROGRAM: "meteora",
        }

        while self._running:
            try:
                log.info("[sniper] connecting to Helius WebSocket...")
                async with websockets.connect(
                    self._ws_url,
                    max_size=10 * 1024 * 1024,  # 10 MB
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    log.info("[sniper] Helius WebSocket connected")
                    self._connection_errors = 0

                    # ── Batch-subscribe to all DEX programs ──
                    # Send ALL subscribe requests first, then collect responses.
                    # This avoids stray log notifications leaking between send/recv
                    # pairs and lets us enter the listen loop only after all subs
                    # are confirmed.
                    for i, prog in enumerate(programs):
                        sub_req = {
                            "jsonrpc": "2.0",
                            "id": i + 1,
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [prog]},
                                {"commitment": "processed"},
                            ],
                        }
                        await ws.send(json.dumps(sub_req))

                    # Collect exactly N subscription responses
                    sub_ids = []
                    for i, prog in enumerate(programs):
                        try:
                            resp = await asyncio.wait_for(ws.recv(), timeout=10)
                        except asyncio.TimeoutError:
                            log.warning(
                                "[sniper] subscribe timeout for %s — skipping",
                                program_labels.get(prog, prog[:12]),
                            )
                            continue
                        try:
                            data = json.loads(resp)
                        except json.JSONDecodeError:
                            log.warning(
                                "[sniper] subscribe response decode error for %s",
                                program_labels.get(prog, prog[:12]),
                            )
                            continue
                        sid = data.get("result")
                        if sid is not None:
                            sub_ids.append(sid)
                            label = program_labels.get(prog, prog[:12])
                            log.info("[sniper] subscribed to %s (sub_id=%s)", label, sid)
                        else:
                            log.warning(
                                "[sniper] subscribe failed for %s: %s",
                                prog[:12], data.get("error", "unknown"),
                            )

                    if not sub_ids:
                        log.warning("[sniper] no subscriptions succeeded — retrying in 10s")
                        await asyncio.sleep(10)
                        continue

                    log.info(
                        "[sniper] listening for new tokens on %d subscriptions...",
                        len(sub_ids),
                    )

                    # ── Listen loop ──
                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        except asyncio.TimeoutError:
                            # Send a ping to keep connection alive
                            try:
                                pong = await ws.ping()
                                await asyncio.wait_for(pong, timeout=5)
                            except Exception:
                                log.debug("[sniper] WS ping failed — reconnecting")
                                break
                            continue

                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        # Only process subscription notifications
                        params = msg.get("params", {})
                        result = params.get("result", {})
                        value = result.get("value", {})
                        logs = value.get("logs", [])
                        signature = value.get("signature", "")

                        if not logs or not signature:
                            continue

                        # Skip already-seen signatures
                        if signature in self._known_sigs:
                            continue
                        self._known_sigs.add(signature)

                        # Keep known_sigs bounded
                        if len(self._known_sigs) > 50_000:
                            self._known_sigs = set(list(self._known_sigs)[-10_000:])

                        # Log content is the subscription message, not the raw value
                        log_entries = logs if isinstance(logs, list) else []

                        # Check for pool creation / new token patterns in logs
                        is_new_pool = any(
                            _RE_INIT_PATTERN.search(entry) for entry in log_entries
                        )
                        if not is_new_pool:
                            continue

                        # Determine which program this is from
                        source = "unknown"
                        for prog, label in program_labels.items():
                            if any(prog[:20] in entry for entry in log_entries):
                                source = label
                                break

                        # Fetch transaction details to extract the token mint
                        token_address = await self._extract_token_from_tx(signature, source)
                        if token_address:
                            self._tokens_detected += 1
                            await self._queue.put({
                                "address": token_address,
                                "source": f"helius_ws_{source}",
                                "chain": "solana",
                                "detected_at": datetime.now(timezone.utc).isoformat(),
                                "signature": signature,
                            })
                            log.info(
                                "[sniper] 🟢 WS detected new token: %s (%s) — %d total",
                                token_address[:16], source, self._tokens_detected,
                            )

            except websockets.ConnectionClosed as e:
                self._connection_errors += 1
                backoff = min(30, 2 ** self._connection_errors)
                log.warning(
                    "[sniper] WS disconnected (%s) — reconnecting in %ds (attempt #%d)",
                    e, backoff, self._connection_errors,
                )
                await asyncio.sleep(backoff)
            except Exception as e:
                self._connection_errors += 1
                backoff = min(60, 5 * 2 ** self._connection_errors)
                log.warning(
                    "[sniper] WS error: %s — reconnecting in %ds (attempt #%d)",
                    e, backoff, self._connection_errors,
                )
                await asyncio.sleep(backoff)

        log.info("[sniper] HeliusStreamDetector: run loop exited")

    async def _extract_token_from_tx(self, signature: str, source: str) -> Optional[str]:
        """Fetch a transaction via RPC and extract the token mint address.

        For PumpFun, the token mint is typically the first account in the
        transaction's inner instructions. For Raydium/Meteora, it's found
        in the Initialize2 instruction accounts.
        """
        try:
            rpc_url = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
            r = await self._http.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [
                        signature,
                        {
                            "encoding": "jsonParsed",
                            "maxSupportedTransactionVersion": 0,
                            "commitment": "confirmed",
                        },
                    ],
                },
                timeout=10,
            )
            if r.status_code != 200:
                return None

            data = r.json()
            result = data.get("result")
            if not result:
                return None

            tx_data = result.get("transaction", {})
            message = tx_data.get("message", {}) if isinstance(tx_data, dict) else {}
            account_keys = message.get("accountKeys", [])
            instructions = message.get("instructions", [])
            meta = result.get("meta", {}) or {}
            inner_ixns = meta.get("innerInstructions", []) or []

            # Strategy 1: For PumpFun, the token mint is one of the first
            # accounts passed to the create instruction. The mint is typically
            # at index 0 or 1 in the inner instructions' accounts.
            if source == "pumpfun":
                # Look for the token mint in the inner instructions
                for inner_group in inner_ixns:
                    ixns = inner_group.get("instructions", [])
                    for ix in ixns:
                        accounts = ix.get("accounts", [])
                        if accounts:
                            # First account is usually the token mint
                            mint_idx = accounts[0]
                            if isinstance(mint_idx, int) and mint_idx < len(account_keys):
                                mint = account_keys[mint_idx].get("pubkey", "")
                                if mint and len(mint) == 44:
                                    return mint

            # Strategy 2: For Raydium/Meteora, look at the Initialize2
            # instruction accounts. The token mint is typically the second
            # or third account in the top-level instruction.
            for ix in instructions:
                accounts = ix.get("accounts", [])
                if len(accounts) >= 3:
                    # Token mint is often at index 1 or 2
                    for idx in (1, 2):
                        if idx < len(accounts):
                            acct_idx = accounts[idx]
                            if isinstance(acct_idx, int) and acct_idx < len(account_keys):
                                mint = account_keys[acct_idx].get("pubkey", "")
                                if mint and len(mint) == 44:
                                    return mint

            # Strategy 3: Parse the preTokenBalances / postTokenBalances
            # for new token accounts (base mint that wasn't in preBalances)
            pre_balances = meta.get("preTokenBalances", []) or []
            post_balances = meta.get("postTokenBalances", []) or []
            pre_mints = {
                b.get("mint", "") for b in pre_balances if b.get("mint")
            }
            for pb in post_balances:
                mint = pb.get("mint", "")
                owner = pb.get("owner", "")
                # New token mint that's not WSOL and went to a non-owner
                if (
                    mint
                    and mint not in pre_mints
                    and mint != WSOL_MINT
                    and len(mint) == 44
                    and owner
                ):
                    return mint

        except Exception as e:
            log.debug("[sniper] _extract_token_from_tx error: %s", e)

        return None

    @property
    def status(self) -> dict:
        return {
            "running": self._running,
            "tokens_detected": self._tokens_detected,
            "connection_errors": self._connection_errors,
        }


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
        self._token_queue: asyncio.Queue = asyncio.Queue()
        self._ws_detector: Optional[HeliusStreamDetector] = None
        self._last_executing_amount: Optional[float] = None  # for Jito tip calc

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

        # Start the WebSocket stream detector (primary detection)
        self._token_queue = asyncio.Queue()
        ws_url = os.environ.get(
            "HELIUS_WS_URL",
            "wss://atlas-mainnet.helius-rpc.com/?api-key=" + os.environ.get("HELIUS_API_KEY", ""),
        )
        self._ws_detector = HeliusStreamDetector(
            ws_url=ws_url,
            token_queue=self._token_queue,
            http_client=self._http,
        )
        await self._ws_detector.start()

        self._task = asyncio.create_task(self._run_loop())
        log.info(
            "[sniper] engine started — WebSocket primary / poll backup every %.1fs",
            SCAN_INTERVAL_SEC,
        )

    async def stop(self) -> None:
        """Stop the auto-snipe engine."""
        self._running = False
        self._api_keys.clear()  # clear decryption key cache

        # Capture WS detector stats before stopping
        ws_detected = self._ws_detector.tokens_detected if self._ws_detector else 0

        # Stop WebSocket detector first
        if self._ws_detector:
            await self._ws_detector.stop()
            self._ws_detector = None

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._http:
            await self._http.aclose()
            self._http = None
        log.info(
            "[sniper] engine stopped — %d WS detections, %d scans, %d snipes",
            ws_detected,
            self._scan_count,
            self._snipe_count,
        )

        # Clear remaining queue items
        while not self._token_queue.empty():
            try:
                self._token_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _run_loop(self) -> None:
        """Main loop: fetch enabled users → detect tokens → evaluate → snipe.

        Primary detection: Helium WebSocket logsSubscribe (sub-second).
        Fallback: RPC polling when queue is empty (covers gaps in WS detection).
        """
        from .public_api import get_user_store
        store = get_user_store()

        poll_interval = max(SCAN_INTERVAL_SEC, 2.0)  # at least 2s polling

        while self._running:
            try:
                # Get all enabled sniper users
                users = await store.get_enabled_sniper_users()
                if not users:
                    # Even with no users, keep draining the queue
                    await self._drain_queue(store, users)
                    await asyncio.sleep(SCAN_INTERVAL_SEC)
                    continue

                # ── Primary: drain WebSocket-detected tokens (non-blocking) ──
                ws_tokens = await self._drain_queue(store, users)

                # ── Fallback: poll RPC if queue is idle (covers gaps) ──
                tokens = await self._scan_new_tokens()
                self._scan_count += 1
                self._last_scan_at = datetime.now(timezone.utc).isoformat()

                if tokens:
                    log.info(
                        "[sniper] scan #%d (WS=%d/poll=%d): evaluating %d users",
                        self._scan_count, len(ws_tokens), len(tokens), len(users),
                    )

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

                # Dynamic sleep: shorter if WS detector is active, longer if not
                if self._ws_detector and self._ws_detector.status.get("running"):
                    await asyncio.sleep(poll_interval)
                else:
                    await asyncio.sleep(SCAN_INTERVAL_SEC)

            except asyncio.CancelledError:
                self._running = False
                break
            except Exception as e:
                log.error("[sniper] loop error: %s", e)
                await asyncio.sleep(SCAN_INTERVAL_SEC * 3)

    async def _drain_queue(self, store, users: list[dict]) -> list[dict]:
        """Drain all pending WebSocket-detected tokens from the queue.

        Returns the list of drained tokens (for metrics).
        """
        drained = []
        if not users:
            # Still drain to keep queue empty
            while not self._token_queue.empty():
                try:
                    self._token_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            return drained

        while not self._token_queue.empty():
            try:
                token_data = self._token_queue.get_nowait()
                drained.append(token_data)
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
            except asyncio.QueueEmpty:
                break
        return drained

    # ── Token scanning ────────────────────────────────────────────

    async def _scan_new_tokens(self) -> list[dict]:
        """Polling fallback: scan for new meme coin tokens via RPC.

        Uses Helius RPC getProgramAccounts for Raydium pools.
        This is a backup for when the WebSocket detector is unavailable.
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

            # ── Jito MEV-protected bundle submission ──────────────
            tx_bytes = bytes(tx)
            self._last_executing_amount = amount_sol
            bundle_id = await self._send_jito_bundle(
                signed_swap_tx=tx_bytes,
                wallet_keypair=kp,
                wallet_pubkey_str=str(kp.pubkey()),
            )

            if bundle_id:
                # Jito bundle accepted — use bundle ID as tx tracking
                tx_sig = bundle_id
                log.info(
                    "[sniper] 🛡️ Jito bundle submitted: %s for %s",
                    bundle_id[:20], token_address[:16],
                )
            else:
                # Fall back to direct RPC send if Jito unavailable
                log.warning(
                    "[sniper] Jito unavailable — falling back to raw RPC send for %s",
                    token_address[:16],
                )
                solana_client = SolanaClient(
                    os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
                    commitment=Commitment("confirmed"),
                )
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

    # ── Jito MEV-Protected Bundle Submission ─────────────────────

    async def _send_jito_bundle(
        self,
        signed_swap_tx: bytes,        # fully-signed VersionedTransaction bytes
        wallet_keypair,                # solders.keypair.Keypair
        wallet_pubkey_str: str,        # base58 pubkey
    ) -> Optional[str]:
        """Submit the swap transaction as a Jito bundle for MEV protection.

        Constructs a 2-transaction bundle:
          Tx 1: Swap (already signed, from Jupiter)
          Tx 2: Jito tip transfer (SOL → Jito tip account)

        The bundle is submitted via Jito Block Engine's sendBundle JSON-RPC.
        Returns the bundle ID on success, None on failure.
        """
        try:
            # Get the latest blockhash for the tip transaction
            solana_rpc = os.environ.get(
                "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
            )
            bh_r = await self._http.post(
                solana_rpc,
                json={"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash", "params": []},
                timeout=10,
            )
            if bh_r.status_code != 200:
                log.warning("[jito] failed to fetch blockhash: HTTP %d", bh_r.status_code)
                return None
            bh_data = bh_r.json()
            bh_value = bh_data.get("result", {}).get("value", {})
            blockhash_str = bh_value.get("blockhash", "")
            if not blockhash_str:
                log.warning("[jito] blockhash response missing blockhash")
                return None

            from solders.hash import Hash
            from solders.transaction import Transaction
            from solders.system_program import transfer as sol_transfer

            blockhash = Hash.from_string(blockhash_str)
            wallet_pubkey = wallet_keypair.pubkey()

            # Select a Jito tip account (deterministic — rotate to spread load)
            import hashlib
            tip_index = int(hashlib.sha256(wallet_pubkey_str.encode()).hexdigest(), 16) % len(JITO_TIP_ACCOUNTS)
            tip_account_str = JITO_TIP_ACCOUNTS[tip_index]

            # Compute dynamic tip based on swap amount
            from solders.pubkey import Pubkey
            tip_account = Pubkey.from_string(tip_account_str)
            amount_sol = float(self._last_executing_amount or JITO_DEFAULT_TIP_SOL)
            tip_lamports = self._compute_jito_tip(amount_sol)

            # Create the tip transfer instruction
            tip_ix = sol_transfer(
                from_pubkey=wallet_pubkey,
                to_pubkey=tip_account,
                lamports=tip_lamports,
            )

            # Build and sign the tip transaction
            tip_tx = Transaction.new_signed_with_payer(
                instructions=[tip_ix],
                payer=wallet_pubkey,
                signing_keypair=wallet_keypair,
                recent_blockhash=blockhash,
            )

            # Serialize both transactions to base64
            from base64 import b64encode
            swap_b64 = b64encode(signed_swap_tx).decode()
            tip_b64 = b64encode(bytes(tip_tx)).decode()
            bundle = [swap_b64, tip_b64]

            # Submit to Jito Block Engine
            jito_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [bundle],
            }
            jito_r = await self._http.post(
                JITO_BUNDLE_ENDPOINT,
                json=jito_req,
                timeout=15,
                headers={"Content-Type": "application/json"},
            )

            if jito_r.status_code != 200:
                log.warning(
                    "[jito] bundle rejected: HTTP %d — %s",
                    jito_r.status_code, jito_r.text[:200],
                )
                return None

            jito_resp = jito_r.json()
            bundle_id = jito_resp.get("result")
            if bundle_id:
                log.info(
                    "[jito] ✅ bundle submitted: %s — tip=%.6f SOL (%s)",
                    bundle_id[:20],
                    tip_lamports / 1e9,
                    tip_account_str[:12],
                )
                return bundle_id

            error = jito_resp.get("error", {})
            log.warning("[jito] sendBundle RPC error: %s", error.get("message", "unknown"))
            return None

        except ImportError as e:
            log.warning("[jito] import error (solders not fully installed?): %s", e)
            return None
        except Exception as e:
            log.warning("[jito] bundle submission failed: %s", e)
            return None

    def _compute_jito_tip(self, amount_sol: float) -> int:
        """Compute a dynamic Jito tip based on swap amount.

        Formula:
          base = JITO_DEFAULT_TIP_SOL
          For swaps > 0.5 SOL, scale: tip = base * sqrt(amount / 0.5)
          Always cap at JITO_MAX_TIP_SOL.
        """
        base = JITO_DEFAULT_TIP_SOL
        if amount_sol > 0.5:
            scaled = base * math.sqrt(amount_sol / 0.5)
            tip_sol = min(scaled, JITO_MAX_TIP_SOL)
        else:
            tip_sol = max(base, 0.001)  # at least 0.001 SOL (1M lamports)

        lamports = int(tip_sol * 1e9)
        return max(lamports, 1_000)  # absolute floor: 1,000 lamports

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
        ws_status = self._ws_detector.status if self._ws_detector else {}
        return {
            "running": self._running,
            "ws_detector_running": ws_status.get("running", False),
            "ws_tokens_detected": ws_status.get("tokens_detected", 0),
            "queue_size": self._token_queue.qsize(),
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
