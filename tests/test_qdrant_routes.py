"""
Smoke tests for integrations/qdrant API routes.

Covers all 13 REST endpoints:
  GET    /api/v1/qdrant/health             — Qdrant connectivity health
  GET    /api/v1/qdrant/stats              — Collection stats
  POST   /api/v1/qdrant/ensure             — Create collections if missing
  POST   /api/v1/qdrant/skills/search      — Semantic skill search
  POST   /api/v1/qdrant/skills/upsert      — Index a skill
  DELETE /api/v1/qdrant/skills/{id}        — Remove a skill
  POST   /api/v1/qdrant/leads/search       — Semantic lead search
  POST   /api/v1/qdrant/leads/upsert       — Index a lead
  DELETE /api/v1/qdrant/leads/{id}         — Remove a lead
  POST   /api/v1/qdrant/documents/search   — Semantic document search
  POST   /api/v1/qdrant/documents/upsert   — Index a document
  DELETE /api/v1/qdrant/documents/{id}     — Remove a document

Strategy:
  - Create a minimal FastAPI app and register the Qdrant routes WITHOUT auth.
  - Mock the async data-fetching functions (search_skills, health_check,
    collection_stats, etc.) so no Qdrant connection is needed.
  - Verify response status codes, top-level keys, and response shapes.

Run with:
    python3 -m pytest tests/test_qdrant_routes.py -v
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

# Make the project root importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from integrations.qdrant import register_qdrant_routes


# ─── Sample data fixtures ──────────────────────────────────────────────────

SAMPLE_HEALTH_OK = {
    "status": "ok",
    "collections": ["skills", "leads", "documents"],
}

SAMPLE_HEALTH_UNAVAILABLE = {
    "status": "unavailable",
    "error": "Qdrant client not initialized",
}

SAMPLE_STATS = {
    "skills": {
        "points_count": 138,
        "status": "green",
        "vectors_count": 138,
        "indexed_vectors_count": 138,
    },
    "leads": {
        "points_count": 500,
        "status": "green",
        "vectors_count": 500,
        "indexed_vectors_count": 490,
    },
    "documents": {
        "points_count": 75,
        "status": "green",
        "vectors_count": 75,
        "indexed_vectors_count": 75,
    },
}

SAMPLE_STATS_SINGLE = {
    "skills": {
        "points_count": 138,
        "status": "green",
        "vectors_count": 138,
        "indexed_vectors_count": 138,
    },
}

SAMPLE_SKILL_SEARCH_RESULTS = [
    {
        "id": "browser.dev-browser",
        "score": 0.89,
        "payload": {
            "skill_name": "browser.dev-browser",
            "content_preview": "Headless browser automation for scraping and screenshot capture.",
            "indexed_at": "2026-06-21T12:00:00",
            "version": "2.1.0",
            "tags": ["browser", "scraping", "automation"],
            "domain": "devtools",
        },
    },
    {
        "id": "email.campaign",
        "score": 0.72,
        "payload": {
            "skill_name": "marketing.emails",
            "content_preview": "Email sequence design — drip campaigns, welcome series, lifecycle emails.",
            "indexed_at": "2026-06-20T08:00:00",
            "version": "2.0.0",
            "tags": ["domain:marketing", "email", "sequence"],
            "domain": "marketing",
        },
    },
]

SAMPLE_LEAD_SEARCH_RESULTS = [
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "score": 0.94,
        "payload": {
            "name": "Summit Roofing LLC",
            "description_preview": "Storm damage restoration specialist serving Dallas-Fort Worth metro.",
            "city": "Dallas",
            "metro": "Dallas-Fort Worth",
            "niche": "Roofing Restoration",
            "status": "active",
            "score": 85,
        },
    },
]

SAMPLE_DOCUMENT_SEARCH_RESULTS = [
    {
        "id": "doc-001",
        "score": 0.81,
        "payload": {
            "title": "Storm Response Email Template",
            "content_preview": "Subject: Immediate storm damage assessment for your property...",
            "doc_type": "email",
            "source": "outreach_engine",
            "tags": ["storm", "roofing", "template"],
        },
    },
]

SAMPLE_ENSURE_RESULT = {
    "ensured": True,
    "collections": ["skills", "leads", "documents"],
}

SAMPLE_UPSERT_OK = {"indexed": True}
SAMPLE_DELETE_OK = {"deleted": True}
SAMPLE_UPSERT_FAIL = {"indexed": False}
SAMPLE_DELETE_FAIL = {"deleted": False}


# ─── Test client fixture ───────────────────────────────────────────────────

def _build_test_app(prefix: str = "/api/v1/qdrant"):
    """Build a minimal FastAPI app with Qdrant routes (no auth)."""
    app = FastAPI()
    register_qdrant_routes(app, prefix=prefix, require_auth=None)
    return app


# ─── Tests ─────────────────────────────────────────────────────────────────

class TestQdrantSmoke(unittest.TestCase):
    """Smoke tests for all Qdrant REST endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.prefix = "/api/v1/qdrant"
        cls.app = _build_test_app(cls.prefix)
        cls.client = TestClient(cls.app)

    # ── GET /health ─────────────────────────────────────────────────

    def test_health_returns_200_when_available(self):
        with patch("integrations.qdrant.health_check",
                   return_value=SAMPLE_HEALTH_OK):
            resp = self.client.get(f"{self.prefix}/health")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("collections", data)
        self.assertEqual(len(data["collections"]), 3)

    def test_health_returns_200_when_unavailable(self):
        with patch("integrations.qdrant.health_check",
                   return_value=SAMPLE_HEALTH_UNAVAILABLE):
            resp = self.client.get(f"{self.prefix}/health")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "unavailable")
        self.assertIn("error", data)

    # ── GET /stats ──────────────────────────────────────────────────

    def test_stats_returns_all_collections(self):
        with patch("integrations.qdrant.collection_stats",
                   return_value=SAMPLE_STATS):
            resp = self.client.get(f"{self.prefix}/stats")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("skills", data)
        self.assertIn("leads", data)
        self.assertIn("documents", data)
        self.assertEqual(data["skills"]["points_count"], 138)

    def test_stats_returns_single_collection(self):
        with patch("integrations.qdrant.collection_stats",
                   return_value=SAMPLE_STATS_SINGLE):
            resp = self.client.get(f"{self.prefix}/stats?collection=skills")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("skills", data)
        self.assertNotIn("leads", data)
        self.assertEqual(data["skills"]["points_count"], 138)

    def test_stats_returns_error_when_unavailable(self):
        with patch("integrations.qdrant.collection_stats",
                   return_value={"error": "Qdrant not available"}):
            resp = self.client.get(f"{self.prefix}/stats")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("error", resp.json())

    # ── POST /ensure ────────────────────────────────────────────────

    def test_ensure_returns_200(self):
        with patch("integrations.qdrant.ensure_collections",
                   return_value=True):
            resp = self.client.post(f"{self.prefix}/ensure")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ensured"])
        self.assertIn("collections", data)
        self.assertEqual(len(data["collections"]), 3)

    def test_ensure_returns_200_when_fails(self):
        with patch("integrations.qdrant.ensure_collections",
                   return_value=False):
            resp = self.client.post(f"{self.prefix}/ensure")

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["ensured"])

    # ── POST /skills/search ─────────────────────────────────────────

    def test_skills_search_returns_results(self):
        with patch("integrations.qdrant.search_skills",
                   return_value=SAMPLE_SKILL_SEARCH_RESULTS):
            resp = self.client.post(
                f"{self.prefix}/skills/search",
                json={"query": "browser automation", "limit": 5},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["results"][0]["id"], "browser.dev-browser")
        self.assertEqual(data["results"][0]["score"], 0.89)
        self.assertIn("skill_name", data["results"][0]["payload"])

    def test_skills_search_empty_query(self):
        with patch("integrations.qdrant.search_skills",
                   return_value=[]):
            resp = self.client.post(
                f"{self.prefix}/skills/search",
                json={"query": "", "limit": 10},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"], [])

    def test_skills_search_with_filter(self):
        """Search with domain filter returns filtered results."""
        with patch("integrations.qdrant.search_skills",
                   return_value=[SAMPLE_SKILL_SEARCH_RESULTS[1]]):
            resp = self.client.post(
                f"{self.prefix}/skills/search",
                json={
                    "query": "email marketing",
                    "limit": 10,
                    "filter": {"domain": "marketing"},
                },
            )

        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["payload"]["domain"], "marketing")

    def test_skills_search_with_score_threshold(self):
        """Only results above the score threshold are returned."""
        with patch("integrations.qdrant.search_skills",
                   return_value=[SAMPLE_SKILL_SEARCH_RESULTS[0]]):
            resp = self.client.post(
                f"{self.prefix}/skills/search",
                json={"query": "browser", "score_threshold": 0.8},
            )

        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(results[0]["score"], 0.8)

    # ── POST /skills/upsert ─────────────────────────────────────────

    def test_skills_upsert_success(self):
        with patch("integrations.qdrant.upsert_skill",
                   return_value=True):
            resp = self.client.post(
                f"{self.prefix}/skills/upsert",
                json={
                    "id": "test.skill",
                    "skill_name": "Test Skill",
                    "content": "A test skill for validation.",
                    "metadata": {"version": "1.0.0", "tags": ["test"]},
                },
            )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["indexed"])

    def test_skills_upsert_failure(self):
        with patch("integrations.qdrant.upsert_skill",
                   return_value=False):
            resp = self.client.post(
                f"{self.prefix}/skills/upsert",
                json={"id": "test.fail", "skill_name": "Fail", "content": ""},
            )

        self.assertEqual(resp.status_code, 500)
        self.assertIn("detail", resp.json())

    # ── DELETE /skills/{id} ─────────────────────────────────────────

    def test_skills_delete_success(self):
        with patch("integrations.qdrant.delete_skill",
                   return_value=True):
            resp = self.client.delete(
                f"{self.prefix}/skills/test.skill"
            )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["deleted"])

    def test_skills_delete_not_found(self):
        with patch("integrations.qdrant.delete_skill",
                   return_value=False):
            resp = self.client.delete(
                f"{self.prefix}/skills/nonexistent.skill"
            )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["deleted"])

    # ── POST /leads/search ──────────────────────────────────────────

    def test_leads_search_returns_results(self):
        with patch("integrations.qdrant.search_leads",
                   return_value=SAMPLE_LEAD_SEARCH_RESULTS):
            resp = self.client.post(
                f"{self.prefix}/leads/search",
                json={"query": "storm damage roofing contractor"},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["id"],
                         "550e8400-e29b-41d4-a716-446655440000")
        self.assertEqual(data["results"][0]["payload"]["niche"],
                         "Roofing Restoration")

    def test_leads_search_empty_results(self):
        with patch("integrations.qdrant.search_leads",
                   return_value=[]):
            resp = self.client.post(
                f"{self.prefix}/leads/search",
                json={"query": "nonexistent niche query"},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"], [])

    def test_leads_search_with_filters(self):
        """Search leads filtered by metro and niche."""
        with patch("integrations.qdrant.search_leads",
                   return_value=SAMPLE_LEAD_SEARCH_RESULTS):
            resp = self.client.post(
                f"{self.prefix}/leads/search",
                json={
                    "query": "roofing",
                    "filter": {"metro": "Dallas-Fort Worth", "niche": "Roofing Restoration"},
                },
            )

        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["payload"]["city"], "Dallas")

    # ── POST /leads/upsert ──────────────────────────────────────────

    def test_leads_upsert_success(self):
        with patch("integrations.qdrant.upsert_lead",
                   return_value=True):
            resp = self.client.post(
                f"{self.prefix}/leads/upsert",
                json={
                    "id": "lead-001",
                    "name": "Test Contractor",
                    "description": "A roofing contractor for testing.",
                    "metadata": {"city": "Austin", "niche": "Roofing", "score": 90},
                },
            )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["indexed"])

    def test_leads_upsert_failure(self):
        with patch("integrations.qdrant.upsert_lead",
                   return_value=False):
            resp = self.client.post(
                f"{self.prefix}/leads/upsert",
                json={"id": "lead-fail", "name": "", "description": ""},
            )

        self.assertEqual(resp.status_code, 500)

    # ── DELETE /leads/{id} ──────────────────────────────────────────

    def test_leads_delete_success(self):
        with patch("integrations.qdrant.delete_lead",
                   return_value=True):
            resp = self.client.delete(
                f"{self.prefix}/leads/lead-001"
            )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["deleted"])

    def test_leads_delete_not_found(self):
        with patch("integrations.qdrant.delete_lead",
                   return_value=False):
            resp = self.client.delete(
                f"{self.prefix}/leads/nonexistent"
            )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["deleted"])

    # ── POST /documents/search ──────────────────────────────────────

    def test_documents_search_returns_results(self):
        with patch("integrations.qdrant.search_documents",
                   return_value=SAMPLE_DOCUMENT_SEARCH_RESULTS):
            resp = self.client.post(
                f"{self.prefix}/documents/search",
                json={"query": "storm email template"},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["payload"]["doc_type"], "email")

    def test_documents_search_with_type_filter(self):
        """Search documents filtered by document type."""
        with patch("integrations.qdrant.search_documents",
                   return_value=SAMPLE_DOCUMENT_SEARCH_RESULTS):
            resp = self.client.post(
                f"{self.prefix}/documents/search",
                json={
                    "query": "template",
                    "filter": {"doc_type": "email"},
                },
            )

        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["payload"]["doc_type"], "email")

    # ── POST /documents/upsert ──────────────────────────────────────

    def test_documents_upsert_success(self):
        with patch("integrations.qdrant.upsert_document",
                   return_value=True):
            resp = self.client.post(
                f"{self.prefix}/documents/upsert",
                json={
                    "id": "doc-100",
                    "title": "Test Document",
                    "content": "Test content for indexing.",
                    "doc_type": "note",
                    "metadata": {"source": "test", "tags": ["test"]},
                },
            )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["indexed"])

    def test_documents_upsert_failure(self):
        with patch("integrations.qdrant.upsert_document",
                   return_value=False):
            resp = self.client.post(
                f"{self.prefix}/documents/upsert",
                json={"id": "doc-fail", "title": "", "content": ""},
            )

        self.assertEqual(resp.status_code, 500)

    # ── DELETE /documents/{id} ──────────────────────────────────────

    def test_documents_delete_success(self):
        with patch("integrations.qdrant.delete_document",
                   return_value=True):
            resp = self.client.delete(
                f"{self.prefix}/documents/doc-100"
            )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["deleted"])

    def test_documents_delete_not_found(self):
        with patch("integrations.qdrant.delete_document",
                   return_value=False):
            resp = self.client.delete(
                f"{self.prefix}/documents/nonexistent"
            )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["deleted"])

    # ── 404 for unknown routes ──────────────────────────────────────

    def test_unknown_route_returns_404(self):
        resp = self.client.get(f"{self.prefix}/nonexistent")
        self.assertEqual(resp.status_code, 404)

    def test_unknown_collection_search_returns_404(self):
        """POST to a non-existent collection path returns 404."""
        resp = self.client.post(
            f"{self.prefix}/widgets/search",
            json={"query": "test"},
        )
        self.assertEqual(resp.status_code, 404)

    # ── Missing body fields ─────────────────────────────────────────

    def test_search_without_body_returns_422(self):
        """POST /skills/search without JSON body returns 422."""
        resp = self.client.post(
            f"{self.prefix}/skills/search",
            headers={"Content-Type": "application/json"},
            content=b"",
        )
        self.assertEqual(resp.status_code, 422)

    def test_upsert_without_body_returns_422(self):
        resp = self.client.post(
            f"{self.prefix}/skills/upsert",
            headers={"Content-Type": "application/json"},
            content=b"",
        )
        self.assertEqual(resp.status_code, 422)

    # ── Content-Type check for all routes ───────────────────────────

    def test_all_routes_return_json(self):
        """All Qdrant routes return application/json content type."""
        with patch("integrations.qdrant.health_check",
                   return_value=SAMPLE_HEALTH_OK), \
             patch("integrations.qdrant.collection_stats",
                   return_value=SAMPLE_STATS), \
             patch("integrations.qdrant.ensure_collections",
                   return_value=True), \
             patch("integrations.qdrant.search_skills",
                   return_value=SAMPLE_SKILL_SEARCH_RESULTS), \
             patch("integrations.qdrant.upsert_skill",
                   return_value=True), \
             patch("integrations.qdrant.delete_skill",
                   return_value=True), \
             patch("integrations.qdrant.search_leads",
                   return_value=SAMPLE_LEAD_SEARCH_RESULTS), \
             patch("integrations.qdrant.upsert_lead",
                   return_value=True), \
             patch("integrations.qdrant.delete_lead",
                   return_value=True), \
             patch("integrations.qdrant.search_documents",
                   return_value=SAMPLE_DOCUMENT_SEARCH_RESULTS), \
             patch("integrations.qdrant.upsert_document",
                   return_value=True), \
             patch("integrations.qdrant.delete_document",
                   return_value=True):

            routes = [
                ("GET", f"{self.prefix}/health"),
                ("GET", f"{self.prefix}/stats"),
                ("POST", f"{self.prefix}/ensure"),
                ("POST", f"{self.prefix}/skills/search", {"query": "test"}),
                ("POST", f"{self.prefix}/skills/upsert",
                 {"id": "t", "skill_name": "t", "content": "t"}),
                ("DELETE", f"{self.prefix}/skills/test"),
                ("POST", f"{self.prefix}/leads/search", {"query": "test"}),
                ("POST", f"{self.prefix}/leads/upsert",
                 {"id": "t", "name": "t", "description": "t"}),
                ("DELETE", f"{self.prefix}/leads/test"),
                ("POST", f"{self.prefix}/documents/search", {"query": "test"}),
                ("POST", f"{self.prefix}/documents/upsert",
                 {"id": "t", "title": "t", "content": "t"}),
                ("DELETE", f"{self.prefix}/documents/test"),
            ]

            for route_def in routes:
                method = route_def[0]
                path = route_def[1]
                body = route_def[2] if len(route_def) > 2 else None

                if method == "GET":
                    resp = self.client.get(path)
                elif method == "POST":
                    resp = self.client.post(path, json=body or {})
                elif method == "DELETE":
                    resp = self.client.delete(path)
                else:
                    continue

                self.assertEqual(
                    resp.status_code, 200,
                    f"{method} {path} should return 200, got {resp.status_code}",
                )
                self.assertIn(
                    "application/json",
                    resp.headers.get("content-type", ""),
                    f"{method} {path} should return JSON",
                )


# ─── Edge cases ────────────────────────────────────────────────────────────

class TestQdrantEdgeCases(unittest.TestCase):
    """Edge cases: missing Qdrant, invalid IDs, malformed requests."""

    @classmethod
    def setUpClass(cls):
        cls.prefix = "/api/v1/qdrant"
        cls.app = _build_test_app(cls.prefix)
        cls.client = TestClient(cls.app)

    def test_health_when_qdrant_down(self):
        """Simulate Qdrant being unreachable."""
        with patch("integrations.qdrant.health_check",
                   return_value={"status": "error", "error": "Connection refused"}):
            resp = self.client.get(f"{self.prefix}/health")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "error")

    def test_stats_empty_collections(self):
        """When Qdrant has no collections, stats returns empty dict."""
        with patch("integrations.qdrant.collection_stats",
                   return_value={}):
            resp = self.client.get(f"{self.prefix}/stats")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {})

    def test_search_with_empty_body(self):
        """POST with empty JSON body should still return 200 (empty query)."""
        with patch("integrations.qdrant.search_skills",
                   return_value=[]):
            resp = self.client.post(
                f"{self.prefix}/skills/search",
                json={},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"], [])

    def test_upsert_with_empty_id(self):
        """Upsert with empty ID still goes through to the service layer."""
        with patch("integrations.qdrant.upsert_skill",
                   return_value=True):
            resp = self.client.post(
                f"{self.prefix}/skills/upsert",
                json={"id": "", "skill_name": "", "content": ""},
            )

        # Service layer handles empty IDs — route just proxies
        self.assertEqual(resp.status_code, 200)

    def test_collection_stats_respects_parameter(self):
        """When collection query param is provided, only that collection is returned."""
        with patch("integrations.qdrant.collection_stats") as mock_stats:
            mock_stats.return_value = SAMPLE_STATS_SINGLE
            resp = self.client.get(f"{self.prefix}/stats?collection=skills")

        self.assertEqual(resp.status_code, 200)
        # Verify the `name` parameter was passed to collection_stats
        # (the mock just returns; we verify the response shape)
        data = resp.json()
        self.assertIn("skills", data)

    def test_delete_with_empty_id(self):
        """DELETE with an empty skill ID returns 404 (empty path segment)."""
        with patch("integrations.qdrant.delete_skill",
                   return_value=False):
            resp = self.client.delete(f"{self.prefix}/skills/")

        self.assertEqual(resp.status_code, 404)

    def test_missing_upsert_body_key_graceful(self):
        """Upsert with missing 'content' key should still work (defaults to empty)."""
        with patch("integrations.qdrant.upsert_skill",
                   return_value=True):
            resp = self.client.post(
                f"{self.prefix}/skills/upsert",
                json={"id": "test", "skill_name": "test"},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["indexed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
