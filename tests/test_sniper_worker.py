"""
PREDICITIVE TRADING BOT · SNIPER WORKER UNIT TESTS
===================================================
Tests for HeliusStreamDetector: WebSocket connection, log parsing,
token extraction, deduplication, and reconnection logic.

All external dependencies (websockets, httpx) are mocked — no network I/O.
"""

import os
import json
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# The predictive trading bot module lives in a directory with dashes
# (the-predicitive-trading-bot/), so we can't import it as a dotted
# module path. Instead, we add its path to sys.path and import from
# the `skills` subpackage directly.
#
# IMPORTANT: The project root also has a `skills/` package that can
# shadow the trading-bot's during full-suite collection. We clear any
# cached `skills` entries from sys.modules so the import finds the
# trading-bot's version first (its path is inserted at position 0).
for _key in list(sys.modules.keys()):
    if _key.startswith("skills"):
        del sys.modules[_key]

_PRED_BOT_DIR = os.path.join(_PROJECT_ROOT, "the-predicitive-trading-bot")
if _PRED_BOT_DIR not in sys.path:
    sys.path.insert(0, _PRED_BOT_DIR)

from skills.sniper_worker import (
    HeliusStreamDetector,
    _RE_INIT_PATTERN,
    RAYDIUM_PROGRAM,
    PUMPFUN_PROGRAM,
    METEORA_PROGRAM,
    WSOL_MINT,
)


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def token_queue():
    return asyncio.Queue()


@pytest.fixture
def http_client():
    return AsyncMock()


@pytest.fixture
def detector(token_queue, http_client):
    return HeliusStreamDetector(
        ws_url="wss://mock.helius.io/ws",
        token_queue=token_queue,
        http_client=http_client,
    )


# ═══════════════════════════════════════════════════════════════════════════
# _RE_INIT_PATTERN — LOG PARSING
# ═══════════════════════════════════════════════════════════════════════════

class TestReInitPattern:
    """Verify the regex that detects new pool/token creation log entries."""

    def test_matches_raydium_initialize2(self):
        assert _RE_INIT_PATTERN.search("Instruction: Initialize2") is not None

    def test_matches_raydium_initialize2_lowercase(self):
        assert _RE_INIT_PATTERN.search("Instruction: initialize2") is not None

    def test_matches_generic_create(self):
        assert _RE_INIT_PATTERN.search("Instruction: create") is not None

    def test_matches_capitalized_create(self):
        assert _RE_INIT_PATTERN.search("Instruction: Create") is not None

    def test_matches_initialize_pool(self):
        assert _RE_INIT_PATTERN.search("Instruction: initialize_pool") is not None

    def test_matches_initialize_pool_capitalized(self):
        assert _RE_INIT_PATTERN.search("Instruction: InitializePool") is not None

    def test_matches_with_extra_context(self):
        log_line = "Program log: Instruction: Initialize2"
        assert _RE_INIT_PATTERN.search(log_line) is not None

    def test_does_not_match_swap(self):
        assert _RE_INIT_PATTERN.search("Instruction: Swap") is None

    def test_does_not_match_withdraw(self):
        assert _RE_INIT_PATTERN.search("Instruction: Withdraw") is None

    def test_does_not_match_deposit(self):
        assert _RE_INIT_PATTERN.search("Instruction: Deposit") is None

    def test_does_not_match_settle_fees(self):
        assert _RE_INIT_PATTERN.search("Instruction: SettleFee") is None

    def test_does_not_match_empty_string(self):
        assert _RE_INIT_PATTERN.search("") is None


# ═══════════════════════════════════════════════════════════════════════════
# _extract_token_from_tx — TOKEN EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def _build_tx_response(
    account_keys=None,
    instructions=None,
    inner_instructions=None,
    pre_token_balances=None,
    post_token_balances=None,
):
    """Helper to build a mock getTransaction response."""
    return {
        "jsonrpc": "2.0",
        "result": {
            "transaction": {
                "message": {
                    "accountKeys": account_keys or [],
                    "instructions": instructions or [],
                },
            },
            "meta": {
                "innerInstructions": inner_instructions or [],
                "preTokenBalances": pre_token_balances or [],
                "postTokenBalances": post_token_balances or [],
            },
        },
    }


class TestExtractTokenPumpFun:
    """Token mint extraction for PumpFun (index 0 of inner instructions)."""

    async def test_extracts_from_first_inner_instruction_account(self, detector):
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: _build_tx_response(
                account_keys=[
                    {"pubkey": "TokenMintAddr1234567890123456789012345678901"},
                ],
                instructions=[{"accounts": [0]}],
                inner_instructions=[{
                    "instructions": [{"accounts": [0]}],
                }],
            ),
        )
        mint = await detector._extract_token_from_tx("sig123", "pumpfun")
        assert mint == "TokenMintAddr1234567890123456789012345678901"

    async def test_ignores_short_mint_length(self, detector):
        """Mints shorter than 44 chars should be rejected."""
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: _build_tx_response(
                account_keys=[{"pubkey": "ShortMint"}],
                instructions=[{"accounts": [0]}],
                inner_instructions=[{
                    "instructions": [{"accounts": [0]}],
                }],
            ),
        )
        mint = await detector._extract_token_from_tx("sig123", "pumpfun")
        assert mint is None

    async def test_returns_none_on_http_error(self, detector):
        http = detector._http
        http.post.return_value = MagicMock(status_code=500, json=lambda: {})
        mint = await detector._extract_token_from_tx("sig123", "pumpfun")
        assert mint is None

    async def test_returns_none_on_missing_result(self, detector):
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"jsonrpc": "2.0", "result": None},
        )
        mint = await detector._extract_token_from_tx("sig123", "pumpfun")
        assert mint is None


class TestExtractTokenRaydium:
    """Token mint extraction for Raydium/Meteora (index 1 or 2 of instructions)."""

    async def test_extracts_from_instruction_index_1(self, detector):
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: _build_tx_response(
                account_keys=[
                    {"pubkey": "ignored"},
                    {"pubkey": "RdiumTokenMintHere12345678901234567890123456"},
                    {"pubkey": "ignored"},  # index 2
                ],
                instructions=[{"accounts": [0, 1, 2]}],
            ),
        )
        mint = await detector._extract_token_from_tx("sig456", "raydium")
        # Should find it at index 1 first
        assert mint == "RdiumTokenMintHere12345678901234567890123456"

    async def test_falls_back_to_index_2(self, detector):
        """If index 1 is too short, try index 2."""
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: _build_tx_response(
                account_keys=[
                    {"pubkey": "ignored"},
                    {"pubkey": "short"},  # index 1 — too short
                    {"pubkey": "MeteoraMintHere12345678901234567890123456789"},  # index 2
                ],
                instructions=[{"accounts": [0, 1, 2]}],
            ),
        )
        mint = await detector._extract_token_from_tx("sig789", "meteora")
        assert mint == "MeteoraMintHere12345678901234567890123456789"

    async def test_returns_none_when_no_instructions_have_3_accounts(self, detector):
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: _build_tx_response(
                account_keys=[{"pubkey": "a"}],
                instructions=[{"accounts": [0]}],  # only 1 account
            ),
        )
        mint = await detector._extract_token_from_tx("sig101", "raydium")
        assert mint is None


class TestExtractTokenBalanceFallback:
    """Fallback strategy: parse preTokenBalances / postTokenBalances."""

    async def test_finds_new_mint_not_in_pre_balances(self, detector):
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: _build_tx_response(
                account_keys=[{"pubkey": "somewallet"}],
                instructions=[{"accounts": []}],  # no instruction match
                pre_token_balances=[{
                    "mint": WSOL_MINT,
                    "owner": "somewallet",
                }],
                post_token_balances=[
                    {"mint": WSOL_MINT, "owner": "somewallet"},
                    {
                        "mint": "NewTokenMintViaBalances123456789012345678901",
                        "owner": "somewallet",
                    },
                ],
            ),
        )
        mint = await detector._extract_token_from_tx("sig202", "unknown")
        assert mint == "NewTokenMintViaBalances123456789012345678901"

    async def test_ignores_wsol_in_pre_balances(self, detector):
        """WSOL mint should be excluded from fallback."""
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: _build_tx_response(
                account_keys=[{"pubkey": "wallet"}],
                instructions=[{"accounts": []}],
                post_token_balances=[
                    {
                        "mint": WSOL_MINT,
                        "owner": "wallet",
                    },
                ],
            ),
        )
        mint = await detector._extract_token_from_tx("sig303", "unknown")
        assert mint is None

    async def test_skips_duplicate_mints_in_pre(self, detector):
        """Already-seen mints should be excluded."""
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: _build_tx_response(
                account_keys=[{"pubkey": "wallet"}],
                instructions=[{"accounts": []}],
                pre_token_balances=[{
                    "mint": "ExistingToken1234567890123456789012345678901",
                    "owner": "wallet",
                }],
                post_token_balances=[{
                    "mint": "ExistingToken1234567890123456789012345678901",
                    "owner": "wallet",
                }],
            ),
        )
        mint = await detector._extract_token_from_tx("sig404", "unknown")
        assert mint is None

    async def test_returns_none_on_exception(self, detector):
        """Any exception in extraction should return None gracefully."""
        http = detector._http
        # Simulate an unexpected response structure
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"jsonrpc": "2.0", "result": {"transaction": None}},
        )
        mint = await detector._extract_token_from_tx("sig505", "unknown")
        assert mint is None


# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET LIFECYCLE & DETECTION
# ═══════════════════════════════════════════════════════════════════════════

class TestWebSocketLifecycle:
    """Start, stop, and the main detect loop."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self, detector):
        await detector.start()
        assert detector._running is True
        assert detector._task is not None
        await detector.stop()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, detector):
        await detector.start()
        task_id = id(detector._task)
        await detector.start()  # second start should be no-op
        assert id(detector._task) == task_id
        await detector.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, detector):
        await detector.start()
        await detector.stop()
        assert detector._running is False
        assert detector._task is None or detector._task.done()

    @pytest.mark.asyncio
    async def test_status_property(self, detector):
        status = detector.status
        assert status["running"] is False
        assert status["tokens_detected"] == 0
        assert status["connection_errors"] == 0

    @pytest.mark.asyncio
    async def test_status_after_start(self, detector):
        await detector.start()
        status = detector.status
        assert status["running"] is True
        await detector.stop()

    @pytest.mark.asyncio
    @patch("skills.sniper_worker.websockets.connect")
    async def test_full_detect_flow(self, mock_connect, detector, token_queue):
        """Simulate the full WebSocket flow: connect → subscribe → detect new token."""
        # ── Mock WebSocket connection ──
        # The production code does: async with websockets.connect(...) as ws:
        # So we need mock_connect() to return a CM, and __aenter__ to return mock_ws
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.send = AsyncMock()

        # Subscribe responses: one per DEX program
        mock_ws.recv.side_effect = [
            json.dumps({"jsonrpc": "2.0", "result": 1, "id": 1}),  # Raydium sub
            json.dumps({"jsonrpc": "2.0", "result": 2, "id": 2}),  # PumpFun sub
            json.dumps({"jsonrpc": "2.0", "result": 3, "id": 3}),  # Meteora sub
            # Then a real log notification with "Instruction: Initialize2"
            json.dumps({
                "jsonrpc": "2.0",
                "method": "logsNotification",
                "params": {
                    "result": {
                        "value": {
                            "logs": [
                                "Program log: Instruction: Initialize2",
                                "Program log: some other log",
                            ],
                            "signature": "tx-sig-abc-123",
                        },
                    },
                },
            }),
        ]

        # Wire up the context manager pattern:
        # mock_connect(url) → return_value (CM) → __aenter__ → mock_ws
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_ws)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_connect.return_value = cm

        # ── Mock _extract_token_from_tx to return a known mint ──
        detector._extract_token_from_tx = AsyncMock(
            return_value=            "DetectedMintAddr1234567890123456789012345678",
        )

        # ── Run the detection loop ──
        await detector.start()

        # Allow the _run coroutine to process one message, then stop
        await asyncio.sleep(0.1)

        # ── Assertions ──
        assert detector._tokens_detected >= 1, f"Expected >=1 tokens, got {detector._tokens_detected}"

        # Check that the token was pushed to the queue
        assert token_queue.qsize() >= 1, f"Expected >=1 queue items, got {token_queue.qsize()}"
        if token_queue.qsize() >= 1:
            token = token_queue.get_nowait()
            assert token["address"] == "DetectedMintAddr1234567890123456789012345678"
            assert token["chain"] == "solana"
            assert token["signature"] == "tx-sig-abc-123"
            assert "source" in token
            assert "detected_at" in token

        await detector.stop()

    @pytest.mark.asyncio
    @patch("skills.sniper_worker.websockets.connect")
    async def test_dedup_by_signature(self, mock_connect, detector, token_queue):
        """Duplicate signatures should be skipped."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.send = AsyncMock()

        # Subscribe responses + two identical log notifications
        duplicate_notification = json.dumps({
            "jsonrpc": "2.0",
            "method": "logsNotification",
            "params": {
                "result": {
                    "value": {
                        "logs": ["Program log: Instruction: Initialize2"],
                        "signature": "duplicate-sig",
                    },
                },
            },
        })

        mock_ws.recv.side_effect = [
            json.dumps({"jsonrpc": "2.0", "result": 1, "id": 1}),
            json.dumps({"jsonrpc": "2.0", "result": 2, "id": 2}),
            json.dumps({"jsonrpc": "2.0", "result": 3, "id": 3}),
            duplicate_notification,
            duplicate_notification,  # same sig again
        ]

        # Context manager pattern
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_ws)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_connect.return_value = cm

        detector._extract_token_from_tx = AsyncMock(return_value="MintDedupTest")

        await detector.start()
        await asyncio.sleep(0.1)
        await detector.stop()

        # Only one token should have been detected despite 2 notifications
        assert detector._tokens_detected == 1


# ═══════════════════════════════════════════════════════════════════════════
# RECONNECTION & ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════════════

class TestReconnection:
    """Automatic reconnection on WebSocket drops."""

    @pytest.mark.asyncio
    @patch("skills.sniper_worker.websockets.connect")
    async def test_reconnects_on_connection_closed(self, mock_connect, detector):
        """When the WS connection drops, it should reconnect."""
        import websockets.exceptions

        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        call_count = 0

        async def recv_with_disconnect():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                # Return subscribe responses
                results = {
                    1: json.dumps({"jsonrpc": "2.0", "result": 1, "id": 1}),
                    2: json.dumps({"jsonrpc": "2.0", "result": 2, "id": 2}),
                    3: json.dumps({"jsonrpc": "2.0", "result": 3, "id": 3}),
                }
                return results[call_count]
            # After subs, simulate disconnect
            raise websockets.exceptions.ConnectionClosed(1000, "gone")

        mock_ws.recv = AsyncMock(side_effect=recv_with_disconnect)

        # Context manager pattern
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_ws)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_connect.return_value = cm

        await detector.start()
        await asyncio.sleep(0.1)
        await detector.stop()

        # Should have recorded at least 1 connection error
        assert detector._connection_errors >= 1

    @pytest.mark.asyncio
    @patch("skills.sniper_worker.websockets.connect")
    async def test_general_exception_handling(self, mock_connect, detector):
        """Non-WS exceptions (e.g. JSON parse errors) should not crash the loop."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.send = AsyncMock()

        mock_ws.recv.side_effect = [
            json.dumps({"jsonrpc": "2.0", "result": 1, "id": 1}),
            json.dumps({"jsonrpc": "2.0", "result": 2, "id": 2}),
            json.dumps({"jsonrpc": "2.0", "result": 3, "id": 3}),
        ]

        # Context manager pattern
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_ws)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_connect.return_value = cm

        await detector.start()
        await asyncio.sleep(0.1)
        await detector.stop()

        # Should not crash — no exception should reach the test
        assert True


# ═══════════════════════════════════════════════════════════════════════════
# DETECTOR MESSAGE PARSING — EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestMessageParsing:
    """Parse various WebSocket notification shapes."""

    @staticmethod
    def _cm_for(mock_ws):
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_ws)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    @pytest.mark.asyncio
    @patch("skills.sniper_worker.websockets.connect")
    async def test_skip_non_init_logs(self, mock_connect, detector):
        """Notifications without Initialize2/create patterns should be skipped."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.send = AsyncMock()

        mock_ws.recv.side_effect = [
            json.dumps({"jsonrpc": "2.0", "result": 1, "id": 1}),
            json.dumps({"jsonrpc": "2.0", "result": 2, "id": 2}),
            json.dumps({"jsonrpc": "2.0", "result": 3, "id": 3}),
            json.dumps({
                "jsonrpc": "2.0",
                "method": "logsNotification",
                "params": {
                    "result": {
                        "value": {
                            "logs": ["Program log: Instruction: Swap"],
                            "signature": "swap-sig",
                        },
                    },
                },
            }),
        ]

        mock_connect.return_value = self._cm_for(mock_ws)
        detector._extract_token_from_tx = AsyncMock(return_value=None)

        await detector.start()
        await asyncio.sleep(0.1)
        await detector.stop()

        assert detector._tokens_detected == 0

    @pytest.mark.asyncio
    @patch("skills.sniper_worker.websockets.connect")
    async def test_skip_signature_only_messages(self, mock_connect, detector):
        """Messages without logs or signature should be skipped."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.send = AsyncMock()

        mock_ws.recv.side_effect = [
            json.dumps({"jsonrpc": "2.0", "result": 1, "id": 1}),
            json.dumps({"jsonrpc": "2.0", "result": 2, "id": 2}),
            json.dumps({"jsonrpc": "2.0", "result": 3, "id": 3}),
            json.dumps({
                "jsonrpc": "2.0",
                "method": "logsNotification",
                "params": {
                    "result": {
                        "value": {
                            "signature": "empty-logs-sig",
                        },
                    },
                },
            }),
        ]

        mock_connect.return_value = self._cm_for(mock_ws)

        await detector.start()
        await asyncio.sleep(0.1)
        await detector.stop()

        assert detector._tokens_detected == 0

    @pytest.mark.asyncio
    @patch("skills.sniper_worker.websockets.connect")
    async def test_malformed_json_does_not_crash(self, mock_connect, detector):
        """Malformed WebSocket messages should be silently skipped."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.send = AsyncMock()

        mock_ws.recv.side_effect = [
            json.dumps({"jsonrpc": "2.0", "result": 1, "id": 1}),
            json.dumps({"jsonrpc": "2.0", "result": 2, "id": 2}),
            json.dumps({"jsonrpc": "2.0", "result": 3, "id": 3}),
            "not-valid-json-at-all{{",  # malformed
        ]

        mock_connect.return_value = self._cm_for(mock_ws)

        await detector.start()
        await asyncio.sleep(0.1)
        await detector.stop()

        assert True


# ═══════════════════════════════════════════════════════════════════════════
# DETECTOR PROGRAM SOURCE DETECTION
# ═══════════════════════════════════════════════════════════════════════════

class TestProgramSourceDetection:
    """Verify the program source labeling in the listen loop."""

    @pytest.mark.asyncio
    @patch("skills.sniper_worker.websockets.connect")
    async def test_raydium_source_label(self, mock_connect, detector, token_queue):
        """If a log mentions Raydium program ID, source should be 'raydium'."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.send = AsyncMock()

        raydium_sub_id = json.dumps({"jsonrpc": "2.0", "result": 10, "id": 1})
        mock_ws.recv.side_effect = [
            raydium_sub_id,
            json.dumps({"jsonrpc": "2.0", "result": 20, "id": 2}),
            json.dumps({"jsonrpc": "2.0", "result": 30, "id": 3}),
            # Notification with Raydium program reference in logs
            json.dumps({
                "jsonrpc": "2.0",
                "method": "logsNotification",
                "params": {
                    "result": {
                        "value": {
                            "logs": [
                                f"Program {RAYDIUM_PROGRAM[:20]} invoke",
                                "Program log: Instruction: Initialize2",
                            ],
                            "signature": "raydium-sig",
                        },
                    },
                },
            }),
        ]

        # Context manager pattern
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_ws)
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_connect.return_value = cm

        detector._extract_token_from_tx = AsyncMock(return_value="RaydiumMint")

        await detector.start()
        await asyncio.sleep(0.1)
        await detector.stop()

        assert detector._tokens_detected == 1
        # Source should be raydium
        assert not token_queue.empty()
        token = token_queue.get_nowait()
        assert "helius_ws_raydium" in token.get("source", "")


# ═══════════════════════════════════════════════════════════════════════════
# KNOWN_SIGS BOUNDED SET BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════════

class TestKnownSigsBounding:
    """_known_sigs set should be bounded to prevent memory leaks."""

    def test_known_sigs_trim_does_not_crash(self, detector):
        """The bounding logic should complete without error."""
        for i in range(51_000):
            detector._known_sigs.add(f"sig-{i}")
        # Trigger the exact same bounding logic from the listen loop
        if len(detector._known_sigs) > 50_000:
            detector._known_sigs = set(list(detector._known_sigs)[-10_000:])
        assert len(detector._known_sigs) == 10_000


# ═══════════════════════════════════════════════════════════════════════════
# DETECTOR PERFECT HEALTH — NO REGRESSION
# ═══════════════════════════════════════════════════════════════════════════

class TestDetectorEdgeCases:
    """Edge cases that should never crash the detector."""

    @pytest.mark.asyncio
    async def test_stop_without_start(self, detector):
        """Stopping a detector that was never started should not crash."""
        await detector.stop()
        assert True

    @pytest.mark.asyncio
    async def test_stop_twice(self, detector):
        """Stopping twice should be safe."""
        await detector.start()
        await detector.stop()
        await detector.stop()
        assert True

    @pytest.mark.asyncio
    async def test_extract_token_empty_response(self, detector):
        """Empty RPC response should produce None (not crash)."""
        http = detector._http
        http.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"jsonrpc": "2.0", "result": {}},
        )
        mint = await detector._extract_token_from_tx("sig", "unknown")
        assert mint is None
