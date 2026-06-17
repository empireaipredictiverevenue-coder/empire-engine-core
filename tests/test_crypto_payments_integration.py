"""
EMPIRE V49 · CRYPTO PAYMENT ROUTE INTEGRATION TESTS
====================================================
Tests the HTTP route handlers for the self-hosted crypto payment
system: checkout pages, payment creation, status checks, validation,
and rate limiting.

Uses FastAPI TestClient with a minimal test app that registers only
the crypto payment routes. Mocks the underlying Supabase DB layer.

Marked as `integration` (not `unit`) because they test the full
route handler stack including request parsing, validation, rate
limiting, and response formatting.
"""
import asyncio
import json
import uuid
import time as _time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from empire_crypto_payments import (
    CryptoPaymentEngine,
    register_crypto_payment_routes,
    _RATE_LIMIT_BUCKET,
)


# ── HELPERS ──────────────────────────────────────────────────────────


def _make_mock_db():
    """Create a mock Supabase client."""
    mock = MagicMock()
    # Chainable: .table().select().eq().execute()
    for method in ("table", "select", "eq", "neq", "gt", "gte", "lt", "lte",
                   "order", "limit", "insert", "update", "upsert", "on_conflict"):
        getattr(mock, method).return_value = mock

    result = MagicMock()
    result.data = []
    result.count = 0
    mock.execute.return_value = result
    return mock


def _make_get_db(mock_db=None):
    """Return a get_db() callable."""
    if mock_db is None:
        mock_db = _make_mock_db()
    return MagicMock(return_value=mock_db)


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


@pytest.fixture(autouse=True)
def _clear_rate_limit_bucket():
    """Clear the in-memory rate limit bucket before each test."""
    _RATE_LIMIT_BUCKET.clear()


@pytest.fixture
def mock_db():
    """Return a mock Supabase DB instance."""
    return _make_mock_db()


@pytest.fixture
def get_db(mock_db):
    """Return a get_db() callable backed by mock_db."""
    return _make_get_db(mock_db)


@pytest.fixture
def engine(get_db):
    """Return a CryptoPaymentEngine with mocked DB."""
    return CryptoPaymentEngine(
        get_db=get_db,
        vault_wallet="vAu1tWaLl3tAdDr3550000",
    )


@pytest.fixture
def test_app(engine) -> FastAPI:
    """Create a minimal FastAPI app with crypto payment routes registered."""
    app = FastAPI(title="Test-Crypto")

    # Add CORS (mirrors hub.py setup)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register crypto routes WITHOUT auth (so we can test without tokens)
    register_crypto_payment_routes(
        app,
        engine=engine,
        require_auth=None,
        public_base_url="http://testserver",
    )
    return app


@pytest.fixture
def client(test_app) -> TestClient:
    """Return a TestClient for the test app."""
    return TestClient(test_app)


# ═══════════════════════════════════════════════════════════════════════
#  GET /crypto/checkout/{tier} — Checkout pages
# ═══════════════════════════════════════════════════════════════════════

class TestCheckoutPage:
    """Checkout pages render correct HTML."""

    def test_known_tier_returns_html(self, client):
        """Known tier renders an HTML page with the tier name."""
        r = client.get("/crypto/checkout/ROUTER_SaaS")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "ROUTER_SaaS" in r.text
        assert "Subscribe" in r.text
        assert "USDC" in r.text
        assert "createPayment" in r.text  # JS function present

    def test_unknown_tier_returns_404(self, client):
        """Unknown tier returns 404."""
        r = client.get("/crypto/checkout/FAKE_TIER")
        assert r.status_code == 404

    def test_all_access_page_has_2499_price(self, client):
        """ALL_ACCESS checkout shows $2499."""
        r = client.get("/crypto/checkout/ALL_ACCESS")
        assert r.status_code == 200
        assert "2499" in r.text
        assert "ALL_ACCESS" in r.text

    def test_strike_enterprise_page_has_7999_price(self, client):
        """STRIKE_ENTERPRISE checkout shows $7999."""
        r = client.get("/crypto/checkout/STRIKE_ENTERPRISE")
        assert r.status_code == 200
        assert "7999" in r.text
        assert "STRIKE_ENTERPRISE" in r.text

    def test_checkout_page_has_vault_wallet(self, client):
        """Checkout page shows the vault wallet address."""
        r = client.get("/crypto/checkout/ROUTER_SaaS")
        assert r.status_code == 200
        assert "vAu1tWaLl3tAdDr3550000" in r.text


# ═══════════════════════════════════════════════════════════════════════
#  POST /api/v1/crypto/pay — Create payment request
# ═══════════════════════════════════════════════════════════════════════

class TestCreatePaymentRoute:
    """Creating payment requests via the HTTP endpoint."""

    def test_create_payment_success(self, client, mock_db):
        """A valid payment request returns 200 with payment details."""
        mock_db.execute.return_value.data = []

        r = client.post(
            "/api/v1/crypto/pay",
            json={
                "customer_email": "buyer@example.com",
                "customer_account_id": "buyer_123",
                "tier_level": "ROUTER_SaaS",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "payment_id" in data
        assert len(data["payment_id"]) == 36  # UUID
        assert data["vault_wallet"] == "vAu1tWaLl3tAdDr3550000"
        assert data["amount_usdc"] == 499.00
        assert data["memo"].startswith("EMP-")
        assert data["tier_level"] == "ROUTER_SaaS"
        assert data["customer_email"] == "buyer@example.com"
        assert "/api/v1/crypto/pay/" in data["status_url"]
        assert "instructions" in data
        assert "memo" in data["instructions"].lower()

    def test_missing_fields_returns_400(self, client):
        """Missing required fields returns 400 with clear message."""
        r = client.post("/api/v1/crypto/pay", json={})
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "customer_email" in detail
        assert "customer_account_id" in detail
        assert "tier_level" in detail

    def test_missing_email_returns_400(self, client):
        """Missing email field returns 400."""
        r = client.post(
            "/api/v1/crypto/pay",
            json={"customer_account_id": "x", "tier_level": "ROUTER_SaaS"},
        )
        assert r.status_code == 400

    def test_invalid_email_returns_400(self, client):
        """Invalid email format returns 400."""
        r = client.post(
            "/api/v1/crypto/pay",
            json={
                "customer_email": "not-an-email",
                "customer_account_id": "x",
                "tier_level": "ROUTER_SaaS",
            },
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "Invalid email" in detail

    def test_unknown_tier_returns_400(self, client):
        """Unknown tier returns 400 with available tiers listed."""
        r = client.post(
            "/api/v1/crypto/pay",
            json={
                "customer_email": "test@example.com",
                "customer_account_id": "test",
                "tier_level": "FAKE_TIER_XYZ",
            },
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "Unknown tier" in detail
        assert "Available:" in detail

    def test_empty_string_fields_returns_400(self, client):
        """Empty customer_account_id or tier_level returns 400."""
        r = client.post(
            "/api/v1/crypto/pay",
            json={
                "customer_email": "test@example.com",
                "customer_account_id": "",
                "tier_level": "ROUTER_SaaS",
            },
        )
        assert r.status_code == 400

    def test_empty_tier_level_returns_400(self, client):
        """Empty tier_level returns 400."""
        r = client.post(
            "/api/v1/crypto/pay",
            json={
                "customer_email": "test@example.com",
                "customer_account_id": "test",
                "tier_level": "",
            },
        )
        assert r.status_code == 400

    def test_extra_fields_ignored(self, client, mock_db):
        """Extra unknown fields in the body are ignored."""
        mock_db.execute.return_value.data = []
        r = client.post(
            "/api/v1/crypto/pay",
            json={
                "customer_email": "test@example.com",
                "customer_account_id": "test",
                "tier_level": "ROUTER_SaaS",
                "unknown_field": "should be ignored",
            },
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_invalid_json_returns_400(self, client):
        """Non-JSON body returns 400."""
        r = client.post(
            "/api/v1/crypto/pay",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400

    def test_product_slug_is_optional(self, client, mock_db):
        """product_slug is optional — request still succeeds without it."""
        mock_db.execute.return_value.data = []

        r = client.post(
            "/api/v1/crypto/pay",
            json={
                "customer_email": "test@example.com",
                "customer_account_id": "test",
                "tier_level": "ALL_ACCESS",
            },
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_strike_enterprise_price_is_7999(self, client, mock_db):
        """STRIKE_ENTERPRISE payment request uses $7999 price."""
        mock_db.execute.return_value.data = []

        r = client.post(
            "/api/v1/crypto/pay",
            json={
                "customer_email": "vip@example.com",
                "customer_account_id": "vip_456",
                "tier_level": "STRIKE_ENTERPRISE",
            },
        )
        assert r.status_code == 200
        assert r.json()["amount_usdc"] == 7999.00


# ═══════════════════════════════════════════════════════════════════════
#  GET /api/v1/crypto/pay/{id} — Payment status
# ═══════════════════════════════════════════════════════════════════════

class TestPaymentStatusRoute:
    """Checking payment request status via HTTP."""

    def test_pending_status_returns_correctly(self, client, mock_db):
        """A pending payment returns correct status fields."""
        row = _make_pending_row()
        mock_db.execute.return_value.data = [row]

        r = client.get(f"/api/v1/crypto/pay/{row['id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["status"] == "pending"
        assert data["payment_id"] == row["id"]
        assert data["amount_usdc"] == 499.00
        assert data["memo"] == "EMP-ABC123"
        assert data["tier_level"] == "ROUTER_SaaS"
        assert data["customer_email"] == "buyer@example.com"
        assert data["paid_amount_usdc"] is None

    def test_completed_status_returns_tx(self, client, mock_db):
        """A completed payment includes transaction signature."""
        row = _make_pending_row(
            status="completed",
            transaction_signature="5h3xS1gN4tur3",
            paid_amount_usdc=498.50,
        )
        mock_db.execute.return_value.data = [row]

        r = client.get(f"/api/v1/crypto/pay/{row['id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "completed"
        assert data["transaction_signature"] == "5h3xS1gN4tur3"
        assert data["paid_amount_usdc"] == 498.50

    def test_activation_pending_status(self, client, mock_db):
        """activation_pending payments are reported correctly."""
        row = _make_pending_row(status="activation_pending", paid_amount_usdc=499.00)
        mock_db.execute.return_value.data = [row]

        r = client.get(f"/api/v1/crypto/pay/{row['id']}")
        assert r.status_code == 200
        assert r.json()["status"] == "activation_pending"

    def test_activation_failed_status(self, client, mock_db):
        """activation_failed payments are reported correctly."""
        row = _make_pending_row(
            status="activation_failed",
            notes="Activation failed: DB timeout",
        )
        mock_db.execute.return_value.data = [row]

        r = client.get(f"/api/v1/crypto/pay/{row['id']}")
        assert r.status_code == 200
        assert r.json()["status"] == "activation_failed"

    def test_expired_status_auto_expires(self, client, mock_db):
        """A stale pending request is auto-expired on status check."""
        past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        row = _make_pending_row(expires_at=past)
        mock_db.execute.return_value.data = [row]

        r = client.get(f"/api/v1/crypto/pay/{row['id']}")
        assert r.status_code == 200
        assert r.json()["status"] == "expired"

    def test_not_found_returns_404(self, client, mock_db):
        """Nonexistent payment_id returns 404."""
        mock_db.execute.return_value.data = []
        r = client.get("/api/v1/crypto/pay/nonexistent-id")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  GET /crypto/pay/{id} — Rendered status page
# ═══════════════════════════════════════════════════════════════════════

class TestRenderedStatusPage:
    """The rendered (HTML) status page for users."""

    def test_pending_renders_correctly(self, client, mock_db):
        """A pending payment renders HTML with 'Waiting for payment'."""
        row = _make_pending_row()
        mock_db.execute.return_value.data = [row]

        r = client.get(f"/crypto/pay/{row['id']}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "PENDING" in r.text
        assert "Waiting for payment" in r.text
        assert row["id"][:12] in r.text

    def test_completed_renders_success(self, client, mock_db):
        """A completed payment renders success message."""
        row = _make_pending_row(status="completed")
        mock_db.execute.return_value.data = [row]

        r = client.get(f"/crypto/pay/{row['id']}")
        assert r.status_code == 200
        assert "completed" in r.text.lower()
        assert "confirmed" in r.text.lower()

    def test_expired_renders_expired(self, client, mock_db):
        """An expired payment shows expired message."""
        row = _make_pending_row(status="expired")
        mock_db.execute.return_value.data = [row]

        r = client.get(f"/crypto/pay/{row['id']}")
        assert r.status_code == 200
        assert "expired" in r.text.lower()

    def test_activation_failed_renders_alert(self, client, mock_db):
        """An activation_failed payment shows alert message."""
        row = _make_pending_row(status="activation_failed")
        mock_db.execute.return_value.data = [row]

        r = client.get(f"/crypto/pay/{row['id']}")
        assert r.status_code == 200
        assert "failed" in r.text.lower() or "received" in r.text.lower()

    def test_not_found_returns_404(self, client, mock_db):
        """Nonexistent payment_id returns 404."""
        mock_db.execute.return_value.data = []
        r = client.get("/crypto/pay/nonexistent-id")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  Rate limiting
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimitingRoute:
    """POST /api/v1/crypto/pay rate limiting."""

    def test_allows_first_requests(self, client, mock_db):
        """First N requests are allowed (where N=rate limit max)."""
        mock_db.execute.return_value.data = []

        # First 3 requests should succeed
        for i in range(3):
            r = client.post(
                "/api/v1/crypto/pay",
                json={
                    "customer_email": f"user{i}@example.com",
                    "customer_account_id": f"user{i}",
                    "tier_level": "ROUTER_SaaS",
                },
            )
            assert r.status_code == 200, f"Request {i+1} should be allowed"

    def test_blocks_after_limit(self, client, mock_db):
        """After the rate limit, further requests are blocked."""
        mock_db.execute.return_value.data = []

        # Exhaust quota
        for i in range(3):
            client.post(
                "/api/v1/crypto/pay",
                json={
                    "customer_email": f"user{i}@example.com",
                    "customer_account_id": f"user{i}",
                    "tier_level": "ROUTER_SaaS",
                },
            )

        # 4th request should be blocked
        r = client.post(
            "/api/v1/crypto/pay",
            json={
                "customer_email": "blocked@example.com",
                "customer_account_id": "blocked",
                "tier_level": "ROUTER_SaaS",
            },
        )
        assert r.status_code == 429
        assert "Too many payment requests" in r.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════
#  GET /api/v1/crypto/stats — Engine stats
# ═══════════════════════════════════════════════════════════════════════

class TestStatsRoute:
    """Stats endpoint with and without auth."""

    def test_stats_without_auth_succeeds_when_no_auth_configured(self, client, mock_db):
        """When require_auth=None, stats endpoint returns data."""
        mock_db.execute.return_value.count = 5

        r = client.get("/api/v1/crypto/stats")
        assert r.status_code == 200
        data = r.json()
        # In the test app, auth is None, so it should succeed
        assert isinstance(data, dict)
        assert "stats" in data
        assert "db_stats" in data
        assert "vault_wallet" in data
        assert "activation_failed" in data


# ═══════════════════════════════════════════════════════════════════════
#  Product / tier price constants
# ═══════════════════════════════════════════════════════════════════════

class TestTierPricesRoute:
    """Checkout pages display correct prices for all tiers."""

    def test_router_saas_price(self, client):
        """ROUTER_SaaS checkout shows $499."""
        r = client.get("/crypto/checkout/ROUTER_SaaS")
        assert r.status_code == 200
        assert "499" in r.text

    def test_data_enterprise_price(self, client):
        """DATA_ENTERPRISE checkout shows $799."""
        r = client.get("/crypto/checkout/DATA_ENTERPRISE")
        assert r.status_code == 200
        assert "799" in r.text

    def test_spy_data_price(self, client):
        """SPY_DATA checkout shows $1499."""
        r = client.get("/crypto/checkout/SPY_DATA")
        assert r.status_code == 200
        assert "1499" in r.text

    def test_omni_bridge_price(self, client):
        """OMNI_BRIDGE checkout shows $999."""
        r = client.get("/crypto/checkout/OMNI_BRIDGE")
        assert r.status_code == 200
        assert "999" in r.text

    def test_agent_orchestrator_price(self, client):
        """AGENT_ORCHESTRATOR checkout shows $1999."""
        r = client.get("/crypto/checkout/AGENT_ORCHESTRATOR")
        assert r.status_code == 200
        assert "1999" in r.text

    def test_b2b_pro_price(self, client):
        """B2B_PRO checkout shows $2999."""
        r = client.get("/crypto/checkout/B2B_PRO")
        assert r.status_code == 200
        assert "2999" in r.text

    def test_seo_starter_price(self, client):
        """SEO_STARTER checkout shows $299."""
        r = client.get("/crypto/checkout/SEO_STARTER")
        assert r.status_code == 200
        assert "299" in r.text

    def test_leadscore_growth_price(self, client):
        """LEADSCORE_GROWTH checkout shows $499."""
        r = client.get("/crypto/checkout/LEADSCORE_GROWTH")
        assert r.status_code == 200
        assert "499" in r.text

    def test_compliant_enterprise_price(self, client):
        """COMPLIANT_ENTERPRISE checkout shows $1999."""
        r = client.get("/crypto/checkout/COMPLIANT_ENTERPRISE")
        assert r.status_code == 200
        assert "1999" in r.text

    def test_strike_whale_price(self, client):
        """STRIKE_WHALE checkout shows $2999."""
        r = client.get("/crypto/checkout/STRIKE_WHALE")
        assert r.status_code == 200
        assert "2999" in r.text

    def test_strike_standard_price(self, client):
        """STRIKE_STANDARD checkout shows $499."""
        r = client.get("/crypto/checkout/STRIKE_STANDARD")
        assert r.status_code == 200
        assert "499" in r.text

    def test_strike_combo_price(self, client):
        """STRIKE_COMBO checkout shows $999."""
        r = client.get("/crypto/checkout/STRIKE_COMBO")
        assert r.status_code == 200
        assert "999" in r.text
