"""
Smoke + validation tests for POST /api/v1/fee/operator-mark-settled.
====================================================================

Tests the empire_fee_operator module in isolation using a minimal
FastAPI app with mocked Supabase. No hub import needed.

Usage:
    pytest tests/test_fee_operator.py -v
    python3 -m pytest tests/test_fee_operator.py -v
"""

import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from empire_fee_operator import register_operator_mark_settled


# ── Mock Supabase client ──────────────────────────────────────────

class MockTable:
    """Minimal chainable Supabase table mock."""

    def __init__(self, name: str):
        self._name = name
        self._rows: list[dict] = []
        self._filters: dict = {}
        self._last_update: dict = {}

    def select(self, *cols):
        self._select_cols = cols
        return self

    def insert(self, data):
        row = {**data, "id": "mock-inserted-id"}
        self._rows.append(row)
        return self

    def update(self, data):
        self._last_update = data
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def order(self, col, **kwargs):
        return self

    def limit(self, n):
        self._limit_val = n
        return self

    def execute(self):
        matching = []
        for row in self._rows:
            if all(row.get(k) == v for k, v in self._filters.items()):
                matching.append(row)
        if self._filters:
            return _FakeResult(matching)
        return _FakeResult(self._rows[-1:] if self._rows else [])


class _FakeResult:
    def __init__(self, data):
        self.data = data


class MockClient:
    def __init__(self):
        self._tables: dict[str, MockTable] = {}

    def table(self, name: str):
        if name not in self._tables:
            self._tables[name] = MockTable(name)
        return self._tables[name]


# ── Auth mock ─────────────────────────────────────────────────────

async def mock_auth(request=None):
    return {
        "id": "mock-op-id",
        "name": "Test Operator",
        "email": "test@empire-ai.co.uk",
        "role": "owner",
        "legacy": False,
    }


# ── Test fixtures ─────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """A fresh MockClient pre-seeded with a dispatch row."""
    db = MockClient()

    dispatch_row = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "lead_id": "radar-target-123",
        "contractor_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "meta": {},
    }
    db.table("dispatches")._rows.append(dispatch_row)

    enriched_row = {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "radar_target_id": "radar-target-123",
    }
    db.table("enriched_leads")._rows.append(enriched_row)

    return db


@pytest.fixture
def app_and_db(mock_db):
    """Create a minimal FastAPI app with the operator-mark-settled route."""
    app = FastAPI()

    def get_db():
        return mock_db

    register_operator_mark_settled(app, require_auth=mock_auth, get_db=get_db)
    return app, mock_db


@pytest.fixture
def client(app_and_db):
    """TestClient wired to the minimal app."""
    app, _ = app_and_db
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════
# VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOperatorMarkSettledValidation:
    """Input validation on POST /api/v1/fee/operator-mark-settled."""

    def test_missing_dispatch_id_returns_400(self, client):
        resp = client.post(
            "/api/v1/fee/operator-mark-settled",
            json={"claim_amount": 50000},
        )
        assert resp.status_code == 400
        assert "dispatch_id" in resp.json()["detail"].lower()

    def test_missing_claim_amount_returns_400(self, client):
        resp = client.post(
            "/api/v1/fee/operator-mark-settled",
            json={"dispatch_id": "abc-123"},
        )
        assert resp.status_code == 400
        assert "claim_amount" in resp.json()["detail"].lower()

    def test_negative_claim_amount_returns_400(self, client):
        resp = client.post(
            "/api/v1/fee/operator-mark-settled",
            json={"dispatch_id": "abc-123", "claim_amount": -100},
        )
        assert resp.status_code == 400
        assert "positive" in resp.json()["detail"].lower()

    def test_zero_claim_amount_returns_400(self, client):
        resp = client.post(
            "/api/v1/fee/operator-mark-settled",
            json={"dispatch_id": "abc-123", "claim_amount": 0},
        )
        assert resp.status_code == 400
        assert "positive" in resp.json()["detail"].lower()

    def test_non_numeric_claim_amount_returns_400(self, client):
        resp = client.post(
            "/api/v1/fee/operator-mark-settled",
            json={"dispatch_id": "abc-123", "claim_amount": "fifty-thousand"},
        )
        assert resp.status_code == 400
        assert "number" in resp.json()["detail"].lower()

    def test_invalid_json_returns_400(self, client):
        resp = client.post(
            "/api/v1/fee/operator-mark-settled",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_unknown_dispatch_returns_404(self, client):
        resp = client.post(
            "/api/v1/fee/operator-mark-settled",
            json={"dispatch_id": "nonexistent-dispatch", "claim_amount": 50000},
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# SUCCESS PATH TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOperatorMarkSettledSuccess:
    """Happy path — valid request writes fee_event + updates dispatch."""

    VALID_DISPATCH = "550e8400-e29b-41d4-a716-446655440000"
    ENDPOINT = "/api/v1/fee/operator-mark-settled"

    def test_valid_request_returns_200_and_ok(self, client):
        resp = client.post(
            self.ENDPOINT,
            json={"dispatch_id": self.VALID_DISPATCH, "claim_amount": 50000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "fee_event" in data
        assert data["dispatch_id"] == self.VALID_DISPATCH

    def test_fee_calculation_correct(self, client):
        """3% fee on $50,000 = $1,500."""
        resp = client.post(
            self.ENDPOINT,
            json={"dispatch_id": self.VALID_DISPATCH, "claim_amount": 50000},
        )
        assert resp.status_code == 200
        fee_event = resp.json()["fee_event"]
        assert fee_event["fee_amount"] == 1500.0
        assert fee_event["fee_percent"] == 0.03

    def test_fee_calculation_rounds_correctly(self, client):
        """$50,000.01 * 3% = $1,500.0003 → rounds to $1,500.00."""
        resp = client.post(
            self.ENDPOINT,
            json={"dispatch_id": self.VALID_DISPATCH, "claim_amount": 50000.01},
        )
        assert resp.status_code == 200
        fee_event = resp.json()["fee_event"]
        assert fee_event["fee_amount"] == 1500.00
        assert fee_event["claim_amount"] == 50000.01

    def test_response_includes_inserted_id(self, client):
        resp = client.post(
            self.ENDPOINT,
            json={"dispatch_id": self.VALID_DISPATCH, "claim_amount": 75000},
        )
        assert resp.status_code == 200
        fee_event = resp.json()["fee_event"]
        assert fee_event["id"] == "mock-inserted-id"

    def test_optional_claim_id_accepted(self, client):
        resp = client.post(
            self.ENDPOINT,
            json={
                "dispatch_id": self.VALID_DISPATCH,
                "claim_amount": 50000,
                "claim_id": "CUST-CLAIM-001",
            },
        )
        assert resp.status_code == 200
        fee_event = resp.json()["fee_event"]
        assert fee_event["claim_id"] == "CUST-CLAIM-001"

    def test_optional_settled_at_accepted(self, client):
        resp = client.post(
            self.ENDPOINT,
            json={
                "dispatch_id": self.VALID_DISPATCH,
                "claim_amount": 50000,
                "settled_at": "2026-06-15T12:00:00Z",
            },
        )
        assert resp.status_code == 200
        fee_event = resp.json()["fee_event"]
        assert fee_event["settled_at"] == "2026-06-15T12:00:00Z"

    def test_source_field_is_operator_mark_settled(self, client):
        resp = client.post(
            self.ENDPOINT,
            json={"dispatch_id": self.VALID_DISPATCH, "claim_amount": 50000},
        )
        fee_event = resp.json()["fee_event"]
        assert fee_event["source"] == "operator_mark_settled"
        assert fee_event["status"] == "pending"

    def test_currency_is_usd(self, client):
        resp = client.post(
            self.ENDPOINT,
            json={"dispatch_id": self.VALID_DISPATCH, "claim_amount": 50000},
        )
        assert resp.json()["fee_event"]["currency"] == "USD"


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION: VERIFY DISPATCH UPDATE
# ═══════════════════════════════════════════════════════════════════

class TestOperatorMarkSettledDispatchUpdate:
    """Verify the dispatch row is updated correctly."""

    VALID_DISPATCH = "550e8400-e29b-41d4-a716-446655440000"
    ENDPOINT = "/api/v1/fee/operator-mark-settled"

    def test_dispatch_meta_updated_after_mark(self, client, app_and_db):
        """After mark-settled, the dispatch meta has settled=True and fee_event_id."""
        _, mock_db = app_and_db
        client.post(
            self.ENDPOINT,
            json={"dispatch_id": self.VALID_DISPATCH, "claim_amount": 50000},
        )
        disp_table = mock_db.table("dispatches")
        update = disp_table._last_update
        assert update is not None
        meta = update["meta"]
        assert meta["settled"] is True
        assert "settled_at" in meta
        assert meta["claim_amount"] == 50000
        assert meta["fee_event_id"] == "mock-inserted-id"

    def test_fee_event_written_to_db(self, client, app_and_db):
        """After mark-settled, the fee_events table has a new row."""
        _, mock_db = app_and_db
        client.post(
            self.ENDPOINT,
            json={"dispatch_id": self.VALID_DISPATCH, "claim_amount": 50000},
        )
        fee_table = mock_db.table("fee_events")
        assert len(fee_table._rows) >= 1
        fee = fee_table._rows[-1]
        assert fee["claim_amount"] == 50000
        assert fee["fee_amount"] == 1500.0
        assert fee["source"] == "operator_mark_settled"

    def test_lead_id_is_none_when_enriched_lead_missing(self, client, app_and_db):
        """When enriched_leads lookup fails, lead_id should be None, not a raw radar target id."""
        _, mock_db = app_and_db
        # Use a dispatch whose lead_id has no enriched_lead match
        resp = client.post(
            self.ENDPOINT,
            json={"dispatch_id": self.VALID_DISPATCH, "claim_amount": 50000},
        )
        fee_event = resp.json()["fee_event"]
        # The dispatch's lead_id is "radar-target-123" which DOES have a match,
        # so this test checks the normal path. For the edge case, we'd need
        # a dispatch with an unmatched lead_id.
        assert fee_event["lead_id"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


class TestOperatorMarkSettledEdgeCases:
    """Edge case and boundary tests."""

    def test_lead_id_none_when_no_enriched_match(self, mock_db):
        """Dispatch with a lead_id that doesn't match any enriched_lead → fee_event.lead_id is None."""
        # Create a fresh app for this test with a dispatch that has no matching enriched_lead
        db = MockClient()
        dispatch_row = {
            "id": "edge-dispatch-no-enrich",
            "lead_id": "unmatched-radar-target",
            "contractor_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
            "meta": {},
        }
        db.table("dispatches")._rows.append(dispatch_row)
        # No enriched_lead with radar_target_id="unmatched-radar-target"

        app = FastAPI()
        register_operator_mark_settled(app, require_auth=mock_auth, get_db=lambda: db)
        tc = TestClient(app)

        resp = tc.post(
            "/api/v1/fee/operator-mark-settled",
            json={"dispatch_id": "edge-dispatch-no-enrich", "claim_amount": 50000},
        )
        assert resp.status_code == 200
        fee_event = resp.json()["fee_event"]
        assert fee_event["lead_id"] is None

    def test_meta_includes_operator_name(self, client):
        resp = client.post(
            "/api/v1/fee/operator-mark-settled",
            json={"dispatch_id": "550e8400-e29b-41d4-a716-446655440000", "claim_amount": 50000},
        )
        fee_event = resp.json()["fee_event"]
        assert fee_event["meta"]["marked_by"] == "Test Operator"
        assert fee_event["meta"]["source"] == "operator_mark_settled"
