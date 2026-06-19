"""
Integration tests for the POST /webhook/lead endpoint.

Uses FastAPI TestClient with mocked Supabase and dependencies so tests
run without external infrastructure.  Covers the multi-source affiliate
auto-tag logic (cookie > query param > body field priority) end-to-end
through the actual webhook handler.
"""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ── Helper: extract the last inserted inbound_lead row ────────────
def _last_inserted_lead(mock_db):
    """Return the last inserted inbound_lead dict from the mock Supabase.

    pytest shares the same fixture instance between test function and
    its dependencies (patched_hub → mock_db), so this inspects the
    exact same MockClient that the webhook handler wrote to.
    """
    table = mock_db._tables.get("inbound_leads")
    if not table or not table._inserted:
        return None
    return table._inserted[-1]


def _all_inserted_leads(mock_db):
    """Return all inbound_lead dicts inserted into the mock Supabase.

    Useful for multi-request tests that need to assert on the full
    sequence of stored records.
    """
    table = mock_db._tables.get("inbound_leads")
    if not table:
        return []
    return list(table._inserted)


# ── Set dummy env vars before any hub imports ─────────────────────
# These are consumed at module-import time in hub.py.  We provide
# plausible values so the engines construct without crashing; actual
# DB calls are mocked below.
os.environ.setdefault("SUPABASE_URL", "http://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("HUB_TOKEN", "test-hub-token")
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:8001")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")


@pytest.fixture
def mock_db():
    """Return a mock Supabase client that tracks inserted data."""

    class MockTable:
        """Minimal mock for a Supabase table builder (select/insert/update)."""

        def __init__(self, name):
            self._name = name
            self._inserted = []
            self._filters = {}
            self._order_args = None
            self._limit_val = None
            self._range_vals = None

        def select(self, *args):
            self._select_cols = args
            return self

        def insert(self, data):
            if isinstance(data, dict):
                data = {**data, "id": "mock-id-" + str(len(self._inserted) + 1)}
                self._inserted.append(data)
            elif isinstance(data, list):
                for d in data:
                    d["id"] = d.get("id", "mock-id-" + str(len(self._inserted) + 1))
                self._inserted.extend(data)
            return self

        def update(self, data):
            self._last_update = data
            return self

        def eq(self, col, val):
            self._filters[col] = val
            return self

        def order(self, col, **kwargs):
            self._order_args = (col, kwargs)
            return self

        def limit(self, n):
            self._limit_val = n
            return self

        def range(self, start, end):
            self._range_vals = (start, end)
            return self

        def execute(self):
            return self._FakeResult(self._inserted[-1:] if self._inserted else [])

        class _FakeResult:
            def __init__(self, data):
                self.data = data
                self.count = len(data)

    class MockClient:
        def __init__(self):
            self._tables = {}

        def table(self, name):
            if name not in self._tables:
                self._tables[name] = MockTable(name)
            return self._tables[name]

    client = MockClient()
    return client


@pytest.fixture
def webhook_secret():
    return os.environ["WEBHOOK_SECRET"]


# We need to patch deeply before importing hub because hub.py does a lot
# of engine construction at module level (import time).  We patch:
#   1. supabase.create_client so engine constructors that call get_db()
#      during __init__ don't crash.
#   2. hub.get_db so the webhook handler gets our mock.
#   3. hub.sales_funnel.optimize_conversion so it returns a known route.
#   4. hub.ai_closer.close so the fire-and-forget closer doesn't run.
#
# The critical insight: before importing hub, we patch the *global* hub
# attributes we know the webhook handler touches.


@pytest.fixture
def patched_hub(mock_db):
    """Import hub with all heavy dependencies mocked."""
    patches = [
        patch("supabase.create_client", return_value=mock_db),
        patch("empire_pain_points.PainPointLibrary._load_from_db"),
    ]
    for p in patches:
        p.start()

    try:
        # Import hub AFTER patches are active
        import hub as _hub_mod

        # Save originals so we can restore them after the test
        original_get_db = _hub_mod.get_db
        original_optimize = _hub_mod.sales_funnel.optimize_conversion
        original_close = _hub_mod.ai_closer.close

        # Now patch the runtime globals the webhook handler uses
        _hub_mod.get_db = MagicMock(return_value=mock_db)
        _hub_mod.sales_funnel.optimize_conversion = MagicMock(
            return_value="ROUTE_TO_VOICE_PIPELINE"
        )
        _hub_mod.ai_closer.close = AsyncMock(
            return_value={"status": "queued"}
        )

        yield _hub_mod

        # Restore originals so we don't leak mocks to other tests
        _hub_mod.get_db = original_get_db
        _hub_mod.sales_funnel.optimize_conversion = original_optimize
        _hub_mod.ai_closer.close = original_close
    finally:
        for p in patches:
            p.stop()


@pytest.fixture
def client(patched_hub):
    """FastAPI TestClient wired to the patched hub app."""
    from fastapi.testclient import TestClient

    return TestClient(patched_hub.app)


# ── Helper to build the common request body ───────────────────────


def _lead_body(**overrides):
    body = {
        "name": "Test Warehouse",
        "phone": "+15551234567",
        "email": "test@warehouse.com",
        "metro": "Dallas–Fort Worth",
        "source": "webhook_test",
    }
    body.update(overrides)
    return body


# ═══════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════


class TestWebhookLeadAuth:
    """x-empire-secret header validation."""

    def test_wrong_secret_returns_401(self, client):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(),
            headers={"x-empire-secret": "wrong-secret"},
        )
        assert resp.status_code == 401
        assert "unauthorized" in resp.text.lower()


    def test_missing_secret_returns_401(self, client):
        resp = client.post("/webhook/lead", json=_lead_body())
        assert resp.status_code == 401
        assert "unauthorized" in resp.text.lower()


    def test_correct_secret_returns_200(self, client, webhook_secret):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["id"] is not None


# ═══════════════════════════════════════════════════════════════════
# AFFILIATE CODE EXTRACTION — PRIORITY ORDERING
# ═══════════════════════════════════════════════════════════════════


class TestAffiliateCookieSource:
    """Cookie source wins over query params and body."""

    def test_cookie_affiliate_ref_is_used(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(),
            cookies={"affiliate_ref": "cookie-aff-99"},
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "cookie-aff-99"

    def test_cookie_wins_over_query_param(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead?affiliate_code=query-44",
            json=_lead_body(),
            cookies={"affiliate_ref": "cookie-wins"},
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "cookie-wins"

    def test_cookie_wins_over_body_field(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(affiliate_code="body-aff"),
            cookies={"affiliate_ref": "cookie-still-wins"},
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "cookie-still-wins"

    def test_empty_cookie_falls_through(self, client, webhook_secret, mock_db):
        """Empty cookie should not block query param fallback."""
        resp = client.post(
            "/webhook/lead?affiliate_code=query-fallback",
            json=_lead_body(),
            cookies={"affiliate_ref": ""},
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "query-fallback"


class TestAffiliateQueryParamSource:
    """Query params are checked when no cookie is present."""

    def test_query_affiliate_code(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead?affiliate_code=query-123",
            json=_lead_body(),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "query-123"

    def test_query_ref_param(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead?ref=ref-from-url",
            json=_lead_body(),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "ref-from-url"

    def test_query_utm_source(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead?utm_source=partner-roofing",
            json=_lead_body(),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "partner-roofing"

    def test_query_affiliate_code_beats_ref(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead?affiliate_code=ac-wins&ref=ref-loses",
            json=_lead_body(),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "ac-wins"

    def test_query_affiliate_code_beats_utm(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead?affiliate_code=ac-wins&utm_source=utm-loses",
            json=_lead_body(),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "ac-wins"

    def test_query_ref_beats_utm(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead?ref=ref-wins&utm_source=utm-loses",
            json=_lead_body(),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "ref-wins"

    def test_query_direct_utm_is_filtered(self, client, webhook_secret, mock_db):
        """'(direct)' UTM should be treated as no affiliate source."""
        resp = client.post(
            "/webhook/lead?utm_source=(direct)",
            json=_lead_body(),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        # No affiliate_code should be set when UTM is filtered
        assert lead.get("affiliate_code") is None


class TestAffiliateBodyFieldSource:
    """Body fields are checked as last resort."""

    def test_body_affiliate_code(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(affiliate_code="body-aff-777"),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "body-aff-777"

    def test_body_ref_field(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(ref="body-ref-888"),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "body-ref-888"

    def test_body_utm_source(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(utm_source="body-utm-999"),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "body-utm-999"

    def test_body_affiliate_code_beats_ref(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(affiliate_code="ac-wins", ref="ref-loses"),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "ac-wins"


class TestAffiliatePriorityOrdering:
    """End-to-end priority: cookie > query param > body field."""

    def test_cookie_wins_over_query_and_body(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead?affiliate_code=query-xx",
            json=_lead_body(affiliate_code="body-yy"),
            cookies={"affiliate_ref": "cookie-zz"},
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "cookie-zz"

    def test_query_wins_over_body(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead?affiliate_code=query-abc",
            json=_lead_body(affiliate_code="body-xyz"),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "query-abc"

    def test_body_fallback_when_no_cookie_or_query(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(affiliate_code="body-only"),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") == "body-only"

    def test_no_affiliate_source_returns_success(self, client, webhook_secret, mock_db):
        """No affiliate info anywhere should still succeed."""
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        assert lead.get("affiliate_code") is None

# ═══════════════════════════════════════════════════════════════════
# MULTI-REQUEST SEQUENCE
# ═══════════════════════════════════════════════════════════════════


class TestMultiRequestSequence:
    """Send multiple leads in sequence and verify id uniqueness and
    affiliate_code correctness per request."""

    def test_three_leads_each_get_unique_ids_and_correct_affiliate(
        self, client, webhook_secret, mock_db,
    ):
        # ── Lead 1: cookie source ──
        resp1 = client.post(
            "/webhook/lead",
            json=_lead_body(name="Warehouse Alpha"),
            cookies={"affiliate_ref": "cookie-alpha"},
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp1.status_code == 200
        r1 = resp1.json()

        # ── Lead 2: query param source ──
        resp2 = client.post(
            "/webhook/lead?affiliate_code=query-beta",
            json=_lead_body(name="Warehouse Beta"),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp2.status_code == 200
        r2 = resp2.json()

        # ── Lead 3: body field source ──
        resp3 = client.post(
            "/webhook/lead",
            json=_lead_body(name="Warehouse Gamma", affiliate_code="body-gamma"),
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp3.status_code == 200
        r3 = resp3.json()

        # ── Verify unique IDs across responses ──
        ids = {r1["id"], r2["id"], r3["id"]}
        assert len(ids) == 3, f"Expected 3 unique IDs, got {len(ids)}"
        for i, rid in enumerate([r1["id"], r2["id"], r3["id"]], 1):
            assert rid is not None and rid != "", f"Lead {i} has empty/null ID"

        # ── Verify all 3 rows stored in mock DB ──
        leads = _all_inserted_leads(mock_db)
        assert len(leads) == 3, f"Expected 3 rows, got {len(leads)}"

        # ── Verify each row has the correct affiliate_code ──
        assert leads[0].get("affiliate_code") == "cookie-alpha", (
            f"Lead 0: expected cookie-alpha, got {leads[0].get('affiliate_code')!r}"
        )
        assert leads[1].get("affiliate_code") == "query-beta", (
            f"Lead 1: expected query-beta, got {leads[1].get('affiliate_code')!r}"
        )
        assert leads[2].get("affiliate_code") == "body-gamma", (
            f"Lead 2: expected body-gamma, got {leads[2].get('affiliate_code')!r}"
        )

        # ── Verify response IDs match stored row IDs ──
        assert leads[0].get("id") == r1["id"]
        assert leads[1].get("id") == r2["id"]
        assert leads[2].get("id") == r3["id"]

        # ── Verify names survived the round-trip ──
        assert leads[0].get("name") == "Warehouse Alpha"
        assert leads[1].get("name") == "Warehouse Beta"
        assert leads[2].get("name") == "Warehouse Gamma"


class TestWebhookBodyParsing:
    """Body parsing edge cases."""

    def test_invalid_json_returns_400(self, client, webhook_secret):
        resp = client.post(
            "/webhook/lead",
            content=b"not json",
            headers={
                "x-empire-secret": webhook_secret,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client, webhook_secret):
        resp = client.post(
            "/webhook/lead",
            content=b"",
            headers={"x-empire-secret": webhook_secret},
        )
        assert resp.status_code == 400

    def test_response_contains_expected_fields(self, client, webhook_secret, mock_db):
        resp = client.post(
            "/webhook/lead",
            json=_lead_body(name="Acme Warehouse"),
            headers={"x-empire-secret": webhook_secret},
        )
        data = resp.json()
        assert data["status"] == "success"
        assert "id" in data
        assert "funnel_route" in data
        assert "closer_result" in data
        assert data["funnel_route"] == "ROUTE_TO_VOICE_PIPELINE"
        lead = _last_inserted_lead(mock_db)
        assert lead is not None
        # Verify other payload fields survived the round-trip
        assert lead.get("name") == "Acme Warehouse"
        assert lead.get("source") == "webhook_test"
        assert lead.get("id") == data["id"]
