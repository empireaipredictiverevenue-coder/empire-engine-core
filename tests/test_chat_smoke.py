"""
Quick-start smoke test for the contractor chat widget.
=======================================================
Uses the hub TestClient with mocked dependencies to verify
POST /api/contractors/chat returns replies correctly.

Runs without external infrastructure (no Supabase, no synthetic_brain).
Matches the patching pattern from tests/test_webhook_lead_integration.py.

Usage:
    pytest tests/test_chat_smoke.py -v
    python3 -m pytest tests/test_chat_smoke.py -v
"""

import os
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient


# ── Set dummy env vars before any hub imports ─────────────────────
os.environ.setdefault("SUPABASE_URL", "http://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("HUB_TOKEN", "test-hub-token")
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:8000")


# ── Import module under test (for rate limit access) ──────────────
from empire_contractors import _CHAT_RATE_LIMIT, _check_chat_rate_limit


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """Minimal mock Supabase client (same pattern as webhook tests)."""

    class MockTable:
        def __init__(self, name):
            self._name = name
            self._inserted = []
            self._filters = {}

        def select(self, *args):
            self._select_cols = args
            return self

        def insert(self, data):
            if isinstance(data, dict):
                data = {**data, "id": "mock-id-" + str(len(self._inserted) + 1)}
                self._inserted.append(data)
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
            return self

        def execute(self):
            return self._FakeResult(self._inserted[-1:] if self._inserted else [])

        class _FakeResult:
            def __init__(self, data):
                self.data = data

    class MockClient:
        def __init__(self):
            self._tables = {}

        def table(self, name):
            if name not in self._tables:
                self._tables[name] = MockTable(name)
            return self._tables[name]

    return MockClient()


@pytest.fixture
def patched_hub(mock_db):
    """Patch hub dependencies so it imports clean, then expose its app.

    Same pattern as test_webhook_lead_integration.py's patched_hub fixture.
    """
    patches = [
        patch("supabase.create_client", return_value=mock_db),
        patch("empire_pain_points.PainPointLibrary._load_from_db"),
    ]
    for p in patches:
        p.start()

    try:
        import hub as _hub_mod
        # Replace the runtime get_db so handlers use our mock
        _hub_mod.get_db = MagicMock(return_value=mock_db)
        yield _hub_mod
    finally:
        for p in patches:
            p.stop()


@pytest.fixture
def client(patched_hub):
    """TestClient wired to the actual hub FastAPI app."""
    return TestClient(patched_hub.app)


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Clear the in-memory rate limit dict before every test."""
    _CHAT_RATE_LIMIT.clear()


# ── Mock helpers ──────────────────────────────────────────────────

_CHAT_SESSION = "test_sid_smoke"


def chat_payload(message: str = "How does Empire AI work?",
                 session_id: str = _CHAT_SESSION) -> dict:
    return {"session_id": session_id, "message": message}


def _mock_brain_post(reply_text: str, status_code: int = 200,
                     reply_key: str = "response"):
    """Patch httpx.AsyncClient.post so the chat handler gets a controlled reply.

    Uses MagicMock (not AsyncMock) for the response because the handler
    calls .json() synchronously (without await). AsyncMock.json would
    return a coroutine, crashing with 'coroutine' object has no attribute 'get'.
    """
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = {reply_key: reply_text}

    patcher = patch.object(
        target=__import__("httpx").AsyncClient,
        attribute="post",
        new_callable=AsyncMock,
        return_value=mock_response,
    )
    patcher.start()
    return patcher


# ═══════════════════════════════════════════════════════════════════
# VALIDATION TESTS  (no mock needed — pure input checking)
# ═══════════════════════════════════════════════════════════════════

class TestChatValidation:
    """Input validation on POST /api/contractors/chat."""

    def test_missing_session_id_returns_400(self, client):
        resp = client.post("/api/contractors/chat", json={"message": "hello"})
        assert resp.status_code == 400
        assert resp.json().get("error") == "missing_session_id"

    def test_missing_message_returns_400(self, client):
        resp = client.post("/api/contractors/chat", json={"session_id": "s1"})
        assert resp.status_code == 400
        assert resp.json().get("error") == "missing_message"

    def test_empty_session_id_returns_400(self, client):
        resp = client.post("/api/contractors/chat",
                           json={"session_id": "", "message": "hi"})
        assert resp.status_code == 400
        assert resp.json().get("error") == "missing_session_id"

    def test_empty_message_returns_400(self, client):
        resp = client.post("/api/contractors/chat",
                           json={"session_id": "s1", "message": ""})
        assert resp.status_code == 400
        assert resp.json().get("error") == "missing_message"

    def test_invalid_json_returns_400(self, client):
        resp = client.post("/api/contractors/chat", content=b"not json",
                           headers={"content-type": "application/json"})
        assert resp.status_code == 400
        assert resp.json().get("error") == "invalid_json"

    def test_non_dict_body_returns_400(self, client):
        resp = client.post("/api/contractors/chat", json="hello")
        assert resp.status_code == 400
        assert resp.json().get("error") == "invalid_payload"

    def test_session_id_too_long_returns_400(self, client):
        resp = client.post("/api/contractors/chat", json={
            "session_id": "x" * 129, "message": "hi",
        })
        assert resp.status_code == 400
        assert resp.json().get("error") == "session_id_too_long"

    def test_message_too_long_returns_400(self, client):
        resp = client.post("/api/contractors/chat", json={
            "session_id": "s1", "message": "x" * 2001,
        })
        assert resp.status_code == 400
        assert resp.json().get("error") == "message_too_long"

    def test_valid_session_id_boundary_128_chars(self, client):
        """128-char session_id should be accepted (limit is > 128)."""
        patcher = _mock_brain_post("OK")
        try:
            resp = client.post("/api/contractors/chat", json={
                "session_id": "x" * 128, "message": "hi",
            })
            assert resp.status_code == 200
        finally:
            patcher.stop()


# ═══════════════════════════════════════════════════════════════════
# SUCCESS PATH TESTS  (mocked brain)
# ═══════════════════════════════════════════════════════════════════

class TestChatSuccessPath:
    """Happy path — valid request returns a reply from the synthetic brain."""

    FAKE_REPLY = "Empire AI helps contractors by delivering pre-qualified leads."

    def test_valid_request_returns_reply(self, client):
        patcher = _mock_brain_post(self.FAKE_REPLY)
        try:
            resp = client.post("/api/contractors/chat", json=chat_payload())
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("ok") is True
            assert data.get("reply") == self.FAKE_REPLY
            assert isinstance(data.get("count_remaining"), int)
            # First message in a fresh session → remaining = 29 (30 - 1)
            assert data["count_remaining"] == 29
        finally:
            patcher.stop()

    def test_count_remaining_decrements(self, client):
        """count_remaining goes down after multiple messages in one session."""
        sid = "test_sid_decrement"
        patcher = _mock_brain_post("ok")
        try:
            r1 = client.post("/api/contractors/chat", json=chat_payload(
                session_id=sid, message="One"
            ))
            r2 = client.post("/api/contractors/chat", json=chat_payload(
                session_id=sid, message="Two"
            ))
            assert r2.json()["count_remaining"] < r1.json()["count_remaining"]
        finally:
            patcher.stop()

    def test_response_has_expected_fields(self, client):
        """Response contains {ok, reply, count_remaining}."""
        patcher = _mock_brain_post("Some reply")
        try:
            resp = client.post("/api/contractors/chat", json=chat_payload(
                session_id="test_sid_shape"
            ))
            data = resp.json()
            assert "ok" in data and isinstance(data["ok"], bool)
            assert "reply" in data and isinstance(data["reply"], str)
            assert "count_remaining" in data and isinstance(data["count_remaining"], int)
        finally:
            patcher.stop()


# ═══════════════════════════════════════════════════════════════════
# BRAIN FALLBACK TESTS  (mocked edge cases)
# ═══════════════════════════════════════════════════════════════════

class TestChatBrainFallback:
    """When synthetic_brain returns unusual responses, handler adapts."""

    def test_empty_reply_returns_default(self, client):
        """Brain returns empty 'response' → handler uses fallback message."""
        patcher = _mock_brain_post("", reply_key="response")
        try:
            resp = client.post("/api/contractors/chat", json=chat_payload(
                session_id="test_sid_empty_reply"
            ))
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("ok") is True
            assert len(data.get("reply", "").strip()) > 10
        finally:
            patcher.stop()

    def test_brain_returns_reply_key(self, client):
        """Brain returns 'reply' key instead of 'response'."""
        patcher = _mock_brain_post("Using the reply key.", reply_key="reply")
        try:
            resp = client.post("/api/contractors/chat", json=chat_payload(
                session_id="test_sid_reply_key"
            ))
            assert resp.status_code == 200
            assert resp.json().get("reply") == "Using the reply key."
        finally:
            patcher.stop()

    def test_brain_returns_answer_key(self, client):
        """Brain returns 'answer' key instead of 'response'."""
        patcher = _mock_brain_post("Using the answer key.", reply_key="answer")
        try:
            resp = client.post("/api/contractors/chat", json=chat_payload(
                session_id="test_sid_answer_key"
            ))
            assert resp.status_code == 200
            assert resp.json().get("reply") == "Using the answer key."
        finally:
            patcher.stop()


# ═══════════════════════════════════════════════════════════════════
# RATE LIMITING TESTS  (no mock — uses brain-down path)
# ═══════════════════════════════════════════════════════════════════

class TestChatRateLimit:
    """Rate limiting behavior: 30 messages/hr/session."""

    def test_rate_limit_blocked(self, client):
        """After hitting the limit, the endpoint returns 429."""
        sid = "test_sid_rate_blocked"
        # Fill up the limit (30 requests) — each hits the brain-down path
        for i in range(30):
            r = client.post("/api/contractors/chat", json=chat_payload(
                session_id=sid, message=f"Message {i}"
            ))
            assert r.status_code == 200, f"Request {i} failed"
        # 31st should be rate-limited
        resp = client.post("/api/contractors/chat", json=chat_payload(
            session_id=sid, message="One more"
        ))
        assert resp.status_code == 429
        assert resp.json().get("error") == "rate_limited"

    def test_rate_limits_are_per_session(self, client):
        """Different sessions have independent 30/hr limits."""
        sid_a = "test_sid_per_session_a"
        sid_b = "test_sid_per_session_b"
        # Exhaust session A
        for i in range(30):
            client.post("/api/contractors/chat", json=chat_payload(
                session_id=sid_a, message=f"Msg {i}"
            ))
        # Session A should be blocked
        r_a = client.post("/api/contractors/chat", json=chat_payload(
            session_id=sid_a, message="One more"
        ))
        assert r_a.status_code == 429
        # Session B should still work — first msg, remaining = 29
        r_b = client.post("/api/contractors/chat", json=chat_payload(
            session_id=sid_b, message="Hello"
        ))
        assert r_b.status_code == 200
        assert r_b.json()["count_remaining"] == 29

    def test_rate_limit_response_shape(self, client):
        """429 response has {error: 'rate_limited', message} for the widget."""
        sid = "test_sid_rate_shape"
        for i in range(30):
            client.post("/api/contractors/chat", json=chat_payload(
                session_id=sid, message=f"M{i}"
            ))
        resp = client.post("/api/contractors/chat", json=chat_payload(
            session_id=sid, message="One more"
        ))
        data = resp.json()
        assert data.get("error") == "rate_limited"
        assert "message" in data
        assert len(data["message"]) > 0


# ═══════════════════════════════════════════════════════════════════
# RATE LIMIT CLEANUP TESTS  (unit-level, no HTTP)
# ═══════════════════════════════════════════════════════════════════

class TestRateLimitCleanup:
    """Direct tests of _check_chat_rate_limit internals."""

    def test_stale_entries_are_cleared(self):
        """Expired timestamps get removed, allowing the session through."""
        old_ts = time.time() - 7200  # 2 hours ago (past the 1-hour window)
        _CHAT_RATE_LIMIT["test_sid_stale"] = [old_ts, old_ts, old_ts]
        allowed, count = _check_chat_rate_limit("test_sid_stale")
        assert allowed is True
        assert count == 1  # the just-appended entry

    def test_fresh_session_returns_allowed(self):
        """A brand-new session is always allowed."""
        allowed, count = _check_chat_rate_limit("test_sid_fresh")
        assert allowed is True
        assert count == 1  # first entry recorded
