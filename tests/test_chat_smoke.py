"""
Smoke test for the contractor chat widget endpoint.
====================================================
Verifies POST /api/contractors/chat works end-to-end through the
FastAPI routing layer, including input validation, rate limiting,
and the synthetic brain integration (mocked).

Uses a standalone FastAPI app (not hub.py) so the test runs without
the pre-existing StaticFiles import error in hub.py.

Mock strategy:
  - Patch httpx.AsyncClient.post (the METHOD, not the class) so
    FastAPI's TestClient (which uses httpx.Client internally) is
    unaffected.
  - Fallback tests (brain down) don't need a mock — they test the
    real exception path when 127.0.0.1:8005 is unreachable.

Usage:
    pytest tests/test_chat_smoke.py -v
    python3 -m pytest tests/test_chat_smoke.py -v
"""

import os
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Set env vars the module reads during import ────────────────────
os.environ.setdefault("SUPABASE_URL", "http://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

# ── Import the module under test ──────────────────────────────────
from empire_contractors import register_contractor_routes, _check_chat_rate_limit, _CHAT_RATE_LIMIT


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def app():
    """Fresh FastAPI app with only contractor routes registered."""
    _app = FastAPI()
    register_contractor_routes(_app)
    return _app


@pytest.fixture
def client(app):
    """TestClient wired to the standalone app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Clear the in-memory rate limit dict before every test so state
    doesn't leak between tests."""
    _CHAT_RATE_LIMIT.clear()


# ── Helpers ───────────────────────────────────────────────────────

_CHAT_SESSION = "test_sid_smoke"


def chat_payload(message: str = "How does Empire AI work?", session_id: str = _CHAT_SESSION) -> dict:
    return {"session_id": session_id, "message": message}


def _mock_brain_post(reply_text: str, status_code: int = 200, reply_key: str = "response"):
    """Patch httpx.AsyncClient.post so the chat handler gets a controlled reply.

    We patch the method on the class rather than the class itself,
    because FastAPI TestClient uses httpx internally and replacing
    the entire class would break test transport.

    IMPORTANT: The response mock uses MagicMock, NOT AsyncMock, because
    the handler calls .json() synchronously (not await). AsyncMock.json
    would return a coroutine object, crashing with:
      'coroutine' object has no attribute 'get'
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
# VALIDATION TESTS  (no mock needed)
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
        resp = client.post("/api/contractors/chat", json={"session_id": "", "message": "hi"})
        assert resp.status_code == 400
        assert resp.json().get("error") == "missing_session_id"

    def test_empty_message_returns_400(self, client):
        resp = client.post("/api/contractors/chat", json={"session_id": "s1", "message": ""})
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
# SUCCESS PATH TESTS  (patched brain)
# ═══════════════════════════════════════════════════════════════════

class TestChatSuccessPath:
    """Happy path — valid request with mocked synthetic brain."""

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
            # First message → remaining should be 29 (30 - 1)
            assert data["count_remaining"] == 29
        finally:
            patcher.stop()

    def test_count_remaining_decrements(self, client):
        """count_remaining goes down after multiple messages in the same session."""
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

    def test_response_has_expected_shape(self, client):
        """Happy path response has {ok, reply, count_remaining}."""
        patcher = _mock_brain_post("Some reply")
        try:
            resp = client.post("/api/contractors/chat", json=chat_payload(
                session_id="test_sid_shape"
            ))
            data = resp.json()
            assert "ok" in data
            assert "reply" in data
            assert "count_remaining" in data
            assert isinstance(data["ok"], bool)
            assert isinstance(data["reply"], str)
            assert isinstance(data["count_remaining"], int)
        finally:
            patcher.stop()


# ═══════════════════════════════════════════════════════════════════
# BRAIN FALLBACK TESTS  (mocked or real brain-down)
# ═══════════════════════════════════════════════════════════════════

class TestChatBrainFallback:
    """When synthetic_brain is down, the chat should return a friendly fallback."""

    def test_brain_empty_reply_returns_default(self, client):
        """Brain returns empty 'response' → handler uses default message."""
        patcher = _mock_brain_post("", reply_key="response")
        try:
            resp = client.post("/api/contractors/chat", json=chat_payload(
                session_id="test_sid_empty_reply"
            ))
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("ok") is True
            # Should fall back to the default message when brain returns empty
            assert len(data.get("reply", "").strip()) > 10
        finally:
            patcher.stop()

    def test_brain_returns_reply_key(self, client):
        """Brain may return 'reply' instead of 'response'."""
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
        """Brain may return 'answer' instead of 'response'."""
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
# RATE LIMITING TESTS  (no mock needed for fallback path)
# ═══════════════════════════════════════════════════════════════════

class TestChatRateLimit:
    """Rate limiting behavior: 30 messages/hr/session."""

    def test_rate_limit_blocked(self, client):
        """After hitting the limit, the endpoint returns 429."""
        sid = "test_sid_rate_blocked"

        # We use the brain-down path so we don't need a mock
        # Fill up the rate limit (30 requests) — each one will return
        # the fallback reply instead of a real brain response, which is fine.
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
        """Different sessions have independent limits."""
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

        # Session B should still work — first message, remaining = 29
        r_b = client.post("/api/contractors/chat", json=chat_payload(
            session_id=sid_b, message="Hello"
        ))
        assert r_b.status_code == 200
        assert r_b.json()["count_remaining"] == 29

    def test_rate_limit_response_shape(self, client):
        """429 response has the fields the widget expects: error, message."""
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
# RATE LIMIT CLEANUP TESTS  (unit-level, no client needed)
# ═══════════════════════════════════════════════════════════════════

class TestRateLimitCleanup:
    """Direct tests of _check_chat_rate_limit (no HTTP, no mock)."""

    def test_stale_entries_are_cleared(self):
        """Calls with expired timestamps should clear them and allow through."""
        old_ts = time.time() - 7200  # 2 hours ago (past the 1-hour window)
        _CHAT_RATE_LIMIT["test_sid_stale"] = [old_ts, old_ts, old_ts]
        allowed, count = _check_chat_rate_limit("test_sid_stale")
        assert allowed is True
        assert count == 1  # the just-appended entry

    def test_fresh_session_returns_allowed(self):
        """A session with no history should be allowed through."""
        allowed, count = _check_chat_rate_limit("test_sid_fresh")
        assert allowed is True
        assert count == 1
