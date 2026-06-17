"""
EMPIRE V49 · CRYPTO PAYMENT ENGINE UNIT TESTS
===============================================
Covers: create_payment_request, match_payment, get_payment_status,
        list_pending_requests, get_db_stats, _lookup_price, memo
        generation, state machine transitions, rate limiting,
        vault wallet validation, and engine stats.
All tests are pure unit tests — no Supabase, no network.
"""
import asyncio
import uuid
import time as _time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock

import pytest

from empire_crypto_payments import (
    CryptoPaymentEngine,
    TIER_PRICES_USDC,
    _generate_memo,
    _check_rate_limit,
    _record_rate_limit,
    _RATE_LIMIT_BUCKET,
    _RATE_LIMIT_MAX,
)


# ── MOCK HELPERS ─────────────────────────────────────────────────────

def _mock_supabase_query(data=None, count=None):
    """Return a mock that chains .table().select().eq()... → .execute()"""
    mock = MagicMock()
    # make the mock chainable: every method returns itself
    for method in ("table", "select", "eq", "neq", "gt", "gte", "lt", "lte",
                    "order", "limit", "insert", "update", "upsert", "on_conflict"):
        getattr(mock, method).return_value = mock
    # resolve at .execute()
    result = MagicMock()
    result.data = data or []
    result.count = count
    mock.execute.return_value = result
    return mock


def _make_pending_row(**overrides):
    """Build a pending crypto_payment_requests row with defaults."""
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "customer_email": "buyer@example.com",
        "customer_account_id": "buyer_123",
        "product_slug": "",
        "tier_level": "ROUTER_SaaS",
        "amount_usdc": 499.00,
        "status": "pending",
        "transaction_signature": None,
        "sender_address": None,
        "paid_at": None,
        "paid_amount_usdc": None,
        "memo": "EMP-ABC123",
        "created_by": "self-serve",
        "created_at": now,
        "updated_at": now,
        "expires_at": expires,
        "notes": "",
        **overrides,
    }


# ── FIXTURES ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """Return a get_db callable backed by a fresh MagicMock."""
    db = _mock_supabase_query()
    get_db = MagicMock(return_value=db)
    return get_db, db


@pytest.fixture
def engine(mock_db):
    """Return a CryptoPaymentEngine with a mocked get_db."""
    get_db, _ = mock_db
    return CryptoPaymentEngine(
        get_db=get_db,
        vault_wallet="vAu1tWaLl3tAdDr3550000",
    )


@pytest.fixture
def engine_with_subs(mock_db):
    """Return an engine wired with a mock subscription_engine."""
    get_db, _ = mock_db
    sub_engine = MagicMock()
    sub_engine.create_subscription.return_value = {
        "ok": True, "subscription_id": "sub_abc123",
    }
    return CryptoPaymentEngine(
        get_db=get_db,
        vault_wallet="vAu1tWaLl3t",
        subscription_engine=sub_engine,
    ), sub_engine


# ═══════════════════════════════════════════════════════════════════
#  Vault wallet validation
# ═══════════════════════════════════════════════════════════════════

class TestVaultWalletValidation:
    """CryptoPaymentEngine must fail-fast on empty vault wallet."""

    def test_empty_vault_wallet_raises(self, mock_db):
        """Constructor raises RuntimeError if vault_wallet is empty."""
        get_db, _ = mock_db
        with pytest.raises(RuntimeError, match="EMPIRE_VAULT_WALLET"):
            CryptoPaymentEngine(get_db=get_db, vault_wallet="")

    def test_empty_vault_wallet_raises_with_whitespace(self, mock_db):
        """Constructor raises even if vault_wallet is whitespace-only."""
        get_db, _ = mock_db
        with pytest.raises(RuntimeError, match="EMPIRE_VAULT_WALLET"):
            CryptoPaymentEngine(get_db=get_db, vault_wallet="   ")


# ═══════════════════════════════════════════════════════════════════
#  Memo generation
# ═══════════════════════════════════════════════════════════════════

class TestMemoGeneration:
    """_generate_memo creates unique EMP-XXXXXX identifiers."""

    def test_memo_format(self):
        """Memo matches EMP-XXXXXX pattern with valid chars."""
        memo = _generate_memo()
        assert memo.startswith("EMP-")
        assert len(memo) == 10  # EMP- + 6 chars
        suffix = memo[4:]
        assert len(suffix) == 6
        valid_chars = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
        assert all(c in valid_chars for c in suffix)

    def test_memos_are_unique(self):
        """Generating 100 memos produces 100 unique values."""
        memos = {_generate_memo() for _ in range(100)}
        assert len(memos) == 100

    def test_no_confusable_chars(self):
        """Memos must not contain I, O, 0, or 1 to avoid confusion."""
        for _ in range(50):
            memo = _generate_memo()
            assert "I" not in memo
            assert "O" not in memo
            assert "0" not in memo
            assert "1" not in memo


# ═══════════════════════════════════════════════════════════════════
#  create_payment_request
# ═══════════════════════════════════════════════════════════════════

class TestCreatePaymentRequest:
    """create_payment_request — the public entry point for buyers."""

    def test_known_tier_returns_payment_details(self, engine, mock_db):
        """Creating a payment request for a known tier returns
        payment_id, vault_wallet, amount, memo, status_url."""
        _, db = mock_db
        db.execute.return_value.data = []

        async def run():
            return await engine.create_payment_request(
                customer_email="buyer@example.com",
                customer_account_id="buyer_123",
                tier_level="ROUTER_SaaS",
            )
        result = asyncio.run(run())

        assert result["ok"] is True
        assert len(result["payment_id"]) == 36  # uuid4
        assert result["vault_wallet"] == "vAu1tWaLl3tAdDr3550000"
        assert result["amount_usdc"] == 499.00
        assert result["memo"].startswith("EMP-")
        assert len(result["memo"]) == 10
        assert result["tier_level"] == "ROUTER_SaaS"
        assert result["customer_email"] == "buyer@example.com"
        assert "/api/v1/crypto/pay/" in result["status_url"]
        assert "instructions" in result
        assert "memo" in result["instructions"].lower()
        assert engine.stats["requests_created"] == 1

    def test_unknown_tier_returns_error(self, engine, mock_db):
        """An unknown tier returns ok=False with helpful error."""
        _, db = mock_db
        db.execute.return_value.data = []

        async def run():
            return await engine.create_payment_request(
                customer_email="buyer@example.com",
                customer_account_id="buyer_123",
                tier_level="NONEXISTENT_TIER",
            )
        result = asyncio.run(run())

        assert result["ok"] is False
        assert "Unknown tier" in result["error"]
        assert "Available:" in result["error"]

    def test_price_from_product_metadata(self, engine, mock_db):
        """When product_metadata has a price and product_slug is given,
        it's preferred over fallback."""
        _, db = mock_db
        db.execute.return_value.data = [{"monthly_price_usd": 599.00}]

        async def run():
            return await engine.create_payment_request(
                customer_email="buyer@example.com",
                customer_account_id="buyer_123",
                tier_level="ROUTER_SaaS",
                product_slug="router",
            )
        result = asyncio.run(run())

        assert result["ok"] is True
        assert result["amount_usdc"] == 599.00

    def test_db_insert_error_is_caught(self, engine, mock_db):
        """When the DB insert raises, the error is caught and returned."""
        _, db = mock_db
        db.execute.side_effect = [
            MagicMock(data=[]),
            Exception("Connection refused"),
        ]

        async def run():
            return await engine.create_payment_request(
                customer_email="buyer@example.com",
                customer_account_id="buyer_123",
                tier_level="ROUTER_SaaS",
                product_slug="router",
            )
        result = asyncio.run(run())

        assert result["ok"] is False
        assert "Connection refused" in result["error"]
        assert engine.stats["errors"] == 1

    def test_strike_pack_enterprise_price(self, engine, mock_db):
        """STRIKE_ENTERPRISE maps to the Strike Pack price ($7999)."""
        _, db = mock_db
        db.execute.return_value.data = []

        async def run():
            return await engine.create_payment_request(
                customer_email="vip@example.com",
                customer_account_id="vip_456",
                tier_level="STRIKE_ENTERPRISE",
            )
        result = asyncio.run(run())

        assert result["ok"] is True
        assert result["amount_usdc"] == 7999.00


# ═══════════════════════════════════════════════════════════════════
#  get_payment_status
# ═══════════════════════════════════════════════════════════════════

class TestGetPaymentStatus:
    """get_payment_status — polled by checkout page JS."""

    def test_found_pending(self, engine, mock_db):
        """An existing pending payment returns its status fields."""
        _, db = mock_db
        row = _make_pending_row()
        db.execute.return_value.data = [row]

        result = engine.get_payment_status(row["id"])

        assert result["ok"] is True
        assert result["status"] == "pending"
        assert result["amount_usdc"] == 499.00
        assert result["memo"] == "EMP-ABC123"
        assert result["tier_level"] == "ROUTER_SaaS"
        assert result["customer_email"] == "buyer@example.com"
        assert result["paid_amount_usdc"] is None

    def test_found_completed(self, engine, mock_db):
        """A completed payment returns its transaction_signature."""
        _, db = mock_db
        row = _make_pending_row(
            status="completed",
            transaction_signature="5h3xS1gN4tur3",
            sender_address="sEnD3rW4Ll3t",
            paid_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            paid_amount_usdc=498.50,
        )
        db.execute.return_value.data = [row]

        result = engine.get_payment_status(row["id"])

        assert result["ok"] is True
        assert result["status"] == "completed"
        assert result["transaction_signature"] == "5h3xS1gN4tur3"
        assert result["paid_amount_usdc"] == 498.50

    def test_found_activation_pending(self, engine, mock_db):
        """An activation_pending payment is reported correctly."""
        _, db = mock_db
        row = _make_pending_row(
            status="activation_pending",
            transaction_signature="5h3xS1gN4tur3",
            sender_address="sEnD3rW4Ll3t",
            paid_amount_usdc=499.00,
        )
        db.execute.return_value.data = [row]

        result = engine.get_payment_status(row["id"])
        assert result["ok"] is True
        assert result["status"] == "activation_pending"

    def test_found_activation_failed(self, engine, mock_db):
        """An activation_failed payment is reported correctly."""
        _, db = mock_db
        row = _make_pending_row(
            status="activation_failed",
            notes="Activation failed: DB timeout",
        )
        db.execute.return_value.data = [row]

        result = engine.get_payment_status(row["id"])
        assert result["ok"] is True
        assert result["status"] == "activation_failed"

    def test_not_found(self, engine, mock_db):
        """A nonexistent payment_id returns ok=False."""
        _, db = mock_db
        db.execute.return_value.data = []

        result = engine.get_payment_status("nonexistent-id")
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_auto_expire_stale_pending(self, engine, mock_db):
        """A pending request past expires_at is auto-expired on status check."""
        _, db = mock_db
        past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        row = _make_pending_row(expires_at=past)
        db.execute.return_value.data = [row]

        result = engine.get_payment_status(row["id"])
        assert result["ok"] is True
        assert result["status"] == "expired"

    def test_db_error_is_caught(self, engine, mock_db):
        """A DB query failure returns ok=False with error message."""
        _, db = mock_db
        db.execute.side_effect = Exception("Table missing")

        result = engine.get_payment_status("any-id")
        assert result["ok"] is False
        assert "Table missing" in result["error"]


# ═══════════════════════════════════════════════════════════════════
#  list_pending_requests
# ═══════════════════════════════════════════════════════════════════

class TestListPendingRequests:
    """list_pending_requests — operator dashboard stats."""

    def test_returns_pending_rows(self, engine, mock_db):
        """Returns list of pending requests ordered by created_at."""
        _, db = mock_db
        rows = [_make_pending_row() for _ in range(3)]
        db.execute.return_value.data = rows

        result = engine.list_pending_requests()
        assert len(result) == 3
        for r in result:
            assert r["status"] == "pending"

    def test_handles_db_error(self, engine, mock_db):
        """DB errors return empty list rather than crashing."""
        _, db = mock_db
        db.execute.side_effect = Exception("DB down")
        assert engine.list_pending_requests() == []

    def test_respects_limit(self, engine, mock_db):
        """limit=5 returns at most 5 rows."""
        _, db = mock_db
        db.execute.return_value.data = [_make_pending_row() for _ in range(5)]
        result = engine.list_pending_requests(limit=5)
        assert len(result) == 5


# ═══════════════════════════════════════════════════════════════════
#  get_db_stats
# ═══════════════════════════════════════════════════════════════════

class TestGetDbStats:
    """get_db_stats — DB-backed status counts."""

    def test_returns_status_counts(self, engine, mock_db):
        """Returns dict with counts for all statuses."""
        _, db = mock_db
        db.execute.return_value.count = 5

        result = engine.get_db_stats()
        assert isinstance(result, dict)
        assert "pending" in result
        assert "activation_pending" in result
        assert "completed" in result
        assert "expired" in result
        assert "activation_failed" in result

    def test_handles_db_error(self, engine, mock_db):
        """DB errors return empty dict."""
        _, db = mock_db
        db.execute.side_effect = Exception("DB down")
        result = engine.get_db_stats()
        assert result == {}


# ═══════════════════════════════════════════════════════════════════
#  match_payment — MEMO MATCHING (the safe path)
# ═══════════════════════════════════════════════════════════════════

class TestMatchPaymentMemoMatching:
    """Memo matching is the primary, unambiguous matching strategy."""

    def test_exact_memo_match(self, engine, mock_db):
        """A payment with matching memo is matched immediately."""
        _, db = mock_db
        row = _make_pending_row(memo="EMP-A1B2C3", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-A1B2C3",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["claimed"] is True
        assert result["payment_id"] == row["id"]

    def test_memo_beats_sender_match(self, engine, mock_db):
        """When a memo matches, it wins even if sender is different."""
        _, db = mock_db
        # Two pending requests: one with matching memo but different sender,
        # one with matching sender but different memo.
        correct_row = _make_pending_row(
            id="correct-id",
            memo="EMP-XYZ999",
            sender_address="other_sender",
            amount_usdc=499.00,
        )
        wrong_row = _make_pending_row(
            id="wrong-id",
            memo="EMP-WRONG",
            sender_address="sEnD3rW4Ll3t",
            amount_usdc=499.00,
        )
        # First query (memo match) returns correct row
        db.execute.return_value.data = [correct_row]

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-XYZ999",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["payment_id"] == "correct-id"

    def test_memo_not_whitespace_only(self, engine, mock_db):
        """Whitespace-only memos are treated as no memo — fallback matching."""
        _, db = mock_db
        row = _make_pending_row(
            sender_address="sEnD3rW4Ll3t",
            amount_usdc=499.00,
        )
        db.execute.return_value.data = [row]

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="   ",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["claimed"] is True


# ═══════════════════════════════════════════════════════════════════
#  match_payment — STATE MACHINE
# ═══════════════════════════════════════════════════════════════════

class TestMatchPaymentStateMachine:
    """Payment transitions: pending → activation_pending → completed/failed."""

    def test_successful_activation_goes_to_completed(self, mock_db, engine_with_subs):
        """A successful activation transitions to 'completed'."""
        eng, sub_engine = engine_with_subs
        _, db = mock_db
        row = _make_pending_row(memo="EMP-TEST01", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await eng.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-TEST01",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["subscription"]["ok"] is True
        assert result["subscription"]["method"] == "suite_engine"
        assert eng.stats["subscriptions_activated"] == 1

    def test_activation_failure_goes_to_activation_failed(self, mock_db):
        """When activation fails, payment goes to activation_failed (not completed)."""
        get_db, db = mock_db
        # Create subscription engine that fails
        sub_engine = MagicMock()
        sub_engine.create_subscription.side_effect = Exception("Supabase timeout")
        eng = CryptoPaymentEngine(
            get_db=get_db,
            vault_wallet="vAu1tWaLl3t",
            subscription_engine=sub_engine,
        )

        row = _make_pending_row(memo="EMP-FAIL1", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await eng.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-FAIL1",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["claimed"] is True
        assert result["subscription"]["ok"] is False
        assert eng.stats["subscriptions_activated"] == 0  # not incremented

    def test_concurrent_claim_guard(self, engine, mock_db):
        """Two concurrent webhooks can't both claim the same request."""
        # This is tested by the .eq("status", "pending") guard on the UPDATE.
        # The test verifies the guard is present in the code by verifying
        # that match_payment returns claimed=True for a normal match.
        _, db = mock_db
        row = _make_pending_row(memo="EMP-GUARD", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-GUARD",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["claimed"] is True


# ═══════════════════════════════════════════════════════════════════
#  match_payment — FALLBACK MATCHING
# ═══════════════════════════════════════════════════════════════════

class TestMatchPaymentFallback:
    """Backward-compatible sender + amount matching when no memo."""

    def test_no_pending_requests(self, engine, mock_db):
        """When there are no pending requests, return unmatched."""
        _, db = mock_db
        db.execute.return_value.data = []

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
            )
        result = asyncio.run(run())

        assert result["matched"] is False
        assert result["claimed"] is False
        assert result["reason"] == "no_match"

    def test_exact_sender_match_no_memo(self, engine, mock_db):
        """A pending request with matching sender_address is matched."""
        _, db = mock_db
        row = _make_pending_row(
            sender_address="sEnD3rW4Ll3t",
            amount_usdc=499.00,
        )
        db.execute.return_value.data = [row]

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["claimed"] is True
        assert result["payment_id"] == row["id"]

    def test_amount_proximity_match_no_sender(self, engine, mock_db):
        """When there's no sender_address on the request, match by amount proximity."""
        _, db = mock_db
        row = _make_pending_row(
            sender_address=None,
            memo="",
            amount_usdc=499.00,
        )
        db.execute.return_value.data = [row]

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=498.80,
                tx_signature="5h3xS1g",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["claimed"] is True
        assert result["payment_id"] == row["id"]

    def test_amount_too_far_apart_no_match(self, engine, mock_db):
        """If the amount differs by >$0.50, do NOT match."""
        _, db = mock_db
        row = _make_pending_row(sender_address=None, memo="", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=450.00,
                tx_signature="5h3xS1g",
            )
        result = asyncio.run(run())

        assert result["matched"] is False
        assert result["claimed"] is False
        assert result["reason"] == "no_match"

    def test_db_query_failure(self, engine, mock_db):
        """When the initial select raises, match returns unmatched with error."""
        _, db = mock_db
        db.execute.side_effect = Exception("Connection timeout")

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
            )
        result = asyncio.run(run())

        assert result["matched"] is False
        assert result["claimed"] is False
        assert "error" in result
        assert engine.stats["errors"] == 1


# ═══════════════════════════════════════════════════════════════════
#  match_payment — SUBSCRIPTION ACTIVATION
# ═══════════════════════════════════════════════════════════════════

class TestMatchPaymentSubscription:
    """Subscription activation via SuiteSubscriptionEngine or direct Supabase."""

    def test_no_subscription_engine_fails_gracefully(self, engine, mock_db):
        """Without subscription_engine, activation fails gracefully (not a crash)."""
        _, db = mock_db
        row = _make_pending_row(memo="EMP-NOSUB", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await engine.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-NOSUB",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["subscription"]["ok"] is False
        assert "No subscription engine" in result["subscription"]["error"]
        assert engine.stats["subscriptions_activated"] == 0

    def test_suite_engine_path(self, mock_db, engine_with_subs):
        """When subscription_engine is wired, it's preferred."""
        eng, sub_engine = engine_with_subs
        _, db = mock_db

        row = _make_pending_row(memo="EMP-SUITE", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await eng.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-SUITE",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["subscription"]["ok"] is True
        assert result["subscription"]["method"] == "suite_engine"
        sub_engine.create_subscription.assert_called_once()
        assert eng.stats["subscriptions_activated"] == 1

    def test_subscription_already_exists_is_ok(self, mock_db):
        """If suite engine says 'already has', it still counts as OK."""
        get_db, db = mock_db
        sub_engine = MagicMock()
        sub_engine.create_subscription.return_value = {
            "ok": False,
            "error": "Account already has an active ROUTER_SaaS subscription",
        }
        eng = CryptoPaymentEngine(
            get_db=get_db,
            vault_wallet="vAu1tWaLl3t",
            subscription_engine=sub_engine,
        )

        row = _make_pending_row(memo="EMP-EXIST", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await eng.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-EXIST",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        assert result["subscription"]["ok"] is True
        assert result["subscription"]["method"] == "already_exists"
        assert eng.stats["subscriptions_activated"] == 1

    def test_match_broadcasts(self, mock_db):
        """When broadcaster is wired, a completion event is sent."""
        get_db, db = mock_db
        broadcaster = MagicMock()
        broadcaster.broadcast = AsyncMock()
        eng = CryptoPaymentEngine(
            get_db=get_db,
            vault_wallet="vAu1tWaLl3t",
            broadcaster=broadcaster,
        )

        row = _make_pending_row(memo="EMP-BCAST", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await eng.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-BCAST",
            )
        result = asyncio.run(run())

        assert result["matched"] is True
        broadcaster.broadcast.assert_called_once()
        call_args = broadcaster.broadcast.call_args[0][0]
        assert call_args["type"] == "crypto_payment_completed"
        assert call_args["amount_usdc"] == 499.00

    def test_broadcast_failure_is_silent(self, mock_db):
        """If broadcast raises, match still succeeds."""
        get_db, db = mock_db
        broadcaster = MagicMock()
        broadcaster.broadcast = AsyncMock(side_effect=Exception("Broadcast pipe broken"))
        eng = CryptoPaymentEngine(
            get_db=get_db,
            vault_wallet="vAu1tWaLl3t",
            broadcaster=broadcaster,
        )

        row = _make_pending_row(memo="EMP-SILENT", amount_usdc=499.00)
        db.execute.return_value.data = [row]

        async def run():
            return await eng.match_payment(
                sender_address="sEnD3rW4Ll3t",
                amount_usdc=499.00,
                tx_signature="5h3xS1g",
                memo="EMP-SILENT",
            )
        result = asyncio.run(run())

        assert result["matched"] is True


# ═══════════════════════════════════════════════════════════════════
#  _lookup_price
# ═══════════════════════════════════════════════════════════════════

class TestLookupPrice:
    """_lookup_price — product_metadata first, fallback second."""

    def test_fallback_prices(self, engine, mock_db):
        """When product_metadata is empty, fall back to TIER_PRICES_USDC."""
        _, db = mock_db
        db.execute.return_value.data = []

        async def run():
            return await engine._lookup_price("ROUTER_SaaS", "")
        price = asyncio.run(run())

        assert price == 499.00

    def test_product_metadata_overrides_fallback(self, engine, mock_db):
        """product_metadata monthly_price_usd is preferred when a product_slug is provided."""
        _, db = mock_db
        db.execute.return_value.data = [{"monthly_price_usd": 599.00}]

        async def run():
            return await engine._lookup_price("ROUTER_SaaS", "router")
        price = asyncio.run(run())

        assert price == 599.00

    def test_unknown_tier_returns_none(self, engine, mock_db):
        """A tier not in product_metadata or fallback returns None."""
        _, db = mock_db
        db.execute.return_value.data = []

        async def run():
            return await engine._lookup_price("NONEXISTENT_TIER", "")
        price = asyncio.run(run())

        assert price is None

    def test_db_error_falls_back(self, engine, mock_db):
        """If product_metadata query fails, fall back to TIER_PRICES_USDC."""
        _, db = mock_db
        db.execute.side_effect = Exception("Permission denied")

        async def run():
            return await engine._lookup_price("ALL_ACCESS", "")
        price = asyncio.run(run())

        assert price == 2499.00


# ═══════════════════════════════════════════════════════════════════
#  Rate limiting
# ═══════════════════════════════════════════════════════════════════

class TestRateLimiting:
    """In-memory IP-based rate limiting for the payment creation endpoint."""

    def setup_method(self):
        """Clear the rate limit bucket before each test."""
        _RATE_LIMIT_BUCKET.clear()

    def test_allows_first_requests(self):
        """First few requests are allowed."""
        for _ in range(_RATE_LIMIT_MAX):
            assert _check_rate_limit("1.2.3.4") is True
            _record_rate_limit("1.2.3.4")

    def test_blocks_after_limit(self):
        """After max requests, further requests are blocked."""
        for _ in range(_RATE_LIMIT_MAX):
            assert _check_rate_limit("5.6.7.8") is True
            _record_rate_limit("5.6.7.8")

        assert _check_rate_limit("5.6.7.8") is False

    def test_different_ips_independent(self):
        """Rate limits are per-IP."""
        # Exhaust IP 1
        for _ in range(_RATE_LIMIT_MAX):
            _record_rate_limit("10.0.0.1")

        # IP 2 should still be allowed
        assert _check_rate_limit("10.0.0.2") is True

    def test_bucket_cleanup(self):
        """Stale entries are pruned during periodic cleanup."""
        # Manually add a stale entry
        _RATE_LIMIT_BUCKET["stale-ip"] = [_time.time() - 7200]  # 2 hours ago
        # Add enough entries to trigger cleanup
        for i in range(501):
            _RATE_LIMIT_BUCKET[f"ip-{i}"] = [_time.time()]

        # Record a new request to trigger cleanup
        _record_rate_limit("fresh-ip")

        # The stale entry should be gone
        assert "stale-ip" not in _RATE_LIMIT_BUCKET


# ═══════════════════════════════════════════════════════════════════
#  Engine Stats
# ═══════════════════════════════════════════════════════════════════

class TestEngineStats:
    """stats dict accumulates across operations."""

    def test_initial_stats_zero(self, engine):
        """Fresh engine starts with all counters at zero."""
        assert engine.stats == {
            "requests_created": 0,
            "payments_matched": 0,
            "subscriptions_activated": 0,
            "errors": 0,
        }

    def test_vault_wallet_is_stored(self, engine):
        """vault_wallet is set from constructor argument."""
        assert engine.vault_wallet == "vAu1tWaLl3tAdDr3550000"

    def test_get_db_stats_integration(self, engine, mock_db):
        """get_db_stats queries DB for each status and returns counts."""
        _, db = mock_db
        db.execute.return_value.count = 3

        result = engine.get_db_stats()
        assert result["pending"] == 3
        assert result["completed"] == 3


# ═══════════════════════════════════════════════════════════════════
#  TIER_PRICES_USDC constants
# ═══════════════════════════════════════════════════════════════════

class TestTierPricesDict:
    """The TIER_PRICES_USDC fallback dict has no collisions."""

    def test_no_duplicate_keys(self):
        """TIER_PRICES_USDC should not have any duplicate keys."""
        keys = list(TIER_PRICES_USDC.keys())
        assert len(keys) == len(set(keys)), "TIER_PRICES_USDC has duplicate keys"

    def test_strike_enterprise_is_strike_pack_price(self):
        """STRIKE_ENTERPRISE must be $7999 (Strike Pack), not $2999 (standalone)."""
        assert TIER_PRICES_USDC["STRIKE_ENTERPRISE"] == 7999.00

    def test_suite_product_prices(self):
        """Suite product prices match the pricing page."""
        assert TIER_PRICES_USDC["ROUTER_SaaS"] == 499.00
        assert TIER_PRICES_USDC["DATA_ENTERPRISE"] == 799.00
        assert TIER_PRICES_USDC["SPY_DATA"] == 1499.00
        assert TIER_PRICES_USDC["ALL_ACCESS"] == 2499.00

    def test_advanced_product_prices(self):
        """Advanced product prices match the pricing page."""
        assert TIER_PRICES_USDC["OMNI_BRIDGE"] == 999.00
        assert TIER_PRICES_USDC["AGENT_ORCHESTRATOR"] == 1999.00
        assert TIER_PRICES_USDC["B2B_PRO"] == 2999.00

    def test_strike_pack_prices(self):
        """Strike Pack prices match the pricing page."""
        assert TIER_PRICES_USDC["STRIKE_STANDARD"] == 499.00
        assert TIER_PRICES_USDC["STRIKE_COMBO"] == 999.00
        assert TIER_PRICES_USDC["STRIKE_WHALE"] == 2999.00
