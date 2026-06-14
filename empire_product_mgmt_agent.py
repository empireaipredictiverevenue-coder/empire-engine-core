"""
EMPIRE V49 · PRODUCT MANAGEMENT AGENT
========================================
Full product management workflow agent that:
- Feature registry with prioritization and scoring
- Customer feedback aggregation and analysis
- Product roadmap planning and milestone tracking
- Release management and changelog
- Product usage analytics and metrics

Routes (registered via hub.py):
  GET  /api/product/features          — Feature registry with priorities
  GET  /api/product/feedback           — Customer feedback aggregation
  GET  /api/product/roadmap            — Product roadmap milestones
  GET  /api/product/releases           — Release history and changelog
  GET  /api/product/metrics            — Product usage analytics
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.product_mgmt_agent")


class ProductManagementAgent:
    """Full product management suite: features, feedback, roadmap, releases."""

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        self._features: list[dict] = []
        self._feedback: list[dict] = []
        self._roadmap: list[dict] = []
        self._seed_features()
        self._seed_feedback()
        self._seed_roadmap()

    # ── SEED DATA ───────────────────────────────────────────────────────────

    def _seed_features(self):
        """Seed feature registry from system capabilities."""
        self._features = [
            {
                "id": "feat-001",
                "name": "AI-Powered Voice Outreach",
                "product": "predictive_revenue",
                "description": "Automated voice calls with AGI-driven scripts and objection handling",
                "status": "shipped",
                "priority": "P0",
                "effort": "large",
                "impact": "high",
                "score": 95,
                "shipped_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
                "owners": ["ai_closer", "voice_router"],
            },
            {
                "id": "feat-002",
                "name": "Multi-Product Subscription Suite",
                "product": "suite_core",
                "description": "SEO Starter, SEO Growth, SEO Pro, All Access subscription tiers",
                "status": "shipped",
                "priority": "P0",
                "effort": "large",
                "impact": "high",
                "score": 90,
                "shipped_at": (datetime.now(timezone.utc) - timedelta(days=14)).isoformat(),
                "owners": ["suite_core"],
            },
            {
                "id": "feat-003",
                "name": "AGI Governor & Strategy Evolution",
                "product": "strategic_intelligence",
                "description": "Genetic algorithm strategy evolution with AGI governor oversight",
                "status": "shipped",
                "priority": "P0",
                "effort": "large",
                "impact": "high",
                "score": 88,
                "shipped_at": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
                "owners": ["empire_si_strategy", "empire_agi_governor"],
            },
            {
                "id": "feat-004",
                "name": "MRR-Based Engagement Tiers",
                "product": "predictive_revenue",
                "description": "5-tier lead routing system based on monthly recurring revenue",
                "status": "shipped",
                "priority": "P0",
                "effort": "medium",
                "impact": "high",
                "score": 92,
                "shipped_at": datetime.now(timezone.utc).isoformat(),
                "owners": ["empire_ai_closer"],
            },
            {
                "id": "feat-005",
                "name": "Command SPA Dashboard",
                "product": "operations",
                "description": "Real-time WebSocket-based command and control dashboard",
                "status": "shipped",
                "priority": "P1",
                "effort": "large",
                "impact": "high",
                "score": 85,
                "shipped_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
                "owners": ["empire_command_spa"],
            },
            {
                "id": "feat-006",
                "name": "Multi-Channel Attribution",
                "product": "analytics",
                "description": "Last-touch attribution model for marketing channels",
                "status": "in_progress",
                "priority": "P1",
                "effort": "medium",
                "impact": "medium",
                "score": 72,
                "shipped_at": None,
                "owners": ["empire_marketing_agent"],
            },
            {
                "id": "feat-007",
                "name": "Human Operator Escalation",
                "product": "predictive_revenue",
                "description": "Auto-escalate high-value leads to human operators",
                "status": "planned",
                "priority": "P1",
                "effort": "medium",
                "impact": "high",
                "score": 78,
                "shipped_at": None,
                "owners": ["empire_ai_closer"],
            },
            {
                "id": "feat-008",
                "name": "Self-Service Contractor Portal",
                "product": "suite_core",
                "description": "Contractor-facing portal for lead management and analytics",
                "status": "planned",
                "priority": "P2",
                "effort": "large",
                "impact": "high",
                "score": 68,
                "shipped_at": None,
                "owners": ["affiliate_portal"],
            },
            {
                "id": "feat-009",
                "name": "Predictive Lead Scoring v2",
                "product": "predictive_revenue",
                "description": "Enhanced lead scoring with behavioral signals and intent data",
                "status": "backlog",
                "priority": "P2",
                "effort": "large",
                "impact": "high",
                "score": 65,
                "shipped_at": None,
                "owners": ["empire_ai_closer"],
            },
            {
                "id": "feat-010",
                "name": "Cross-Niche Synergy Engine",
                "product": "strategic_intelligence",
                "description": "Cross-niche strategy recombination for emergent intelligence",
                "status": "backlog",
                "priority": "P3",
                "effort": "medium",
                "impact": "medium",
                "score": 52,
                "shipped_at": None,
                "owners": ["empire_si_strategy"],
            },
        ]

    def _seed_feedback(self):
        """Seed customer feedback items."""
        self._feedback = [
            {
                "id": "fb-001",
                "source": "operator",
                "category": "feature_request",
                "title": "Add manual call trigger for specific leads",
                "body": "Would like to manually trigger an AI call for leads that look high-value",
                "sentiment": "positive",
                "frequency": 3,
                "status": "under_review",
                "received_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
            },
            {
                "id": "fb-002",
                "source": "system_log",
                "category": "bug",
                "title": "WebSocket reconnection delay",
                "body": "Dashboard disconnects briefly during hub restart (~12s downtime)",
                "sentiment": "negative",
                "frequency": 8,
                "status": "acknowledged",
                "received_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            },
            {
                "id": "fb-003",
                "source": "operator",
                "category": "improvement",
                "title": "Show caller ID in dashboard",
                "body": "Would be helpful to see which number is being used for each call",
                "sentiment": "neutral",
                "frequency": 2,
                "status": "planned",
                "received_at": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
            },
            {
                "id": "fb-004",
                "source": "analytics",
                "category": "feature_request",
                "title": "Export revenue reports to CSV",
                "body": "Need CSV export for quarterly financial reporting",
                "sentiment": "positive",
                "frequency": 4,
                "status": "under_review",
                "received_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
            },
        ]

    def _seed_roadmap(self):
        """Seed roadmap milestones."""
        now = datetime.now(timezone.utc)
        self._roadmap = [
            {
                "id": "ms-001",
                "title": "Q2 2026 Foundation Complete",
                "description": "All core revenue engines online: voice, subscriptions, strategy evolution",
                "status": "completed",
                "target_date": (now - timedelta(days=15)).isoformat(),
                "completion_pct": 100,
                "features": ["feat-001", "feat-002", "feat-003"],
            },
            {
                "id": "ms-002",
                "title": "MRR Tiering & Optimization",
                "description": "Engagement tiers, attribution, dashboard refinements",
                "status": "in_progress",
                "target_date": (now + timedelta(days=14)).isoformat(),
                "completion_pct": 70,
                "features": ["feat-004", "feat-005", "feat-006"],
            },
            {
                "id": "ms-003",
                "title": "Human-in-the-Loop Escalation",
                "description": "Operator escalation, contractor portal v1, notification system",
                "status": "planned",
                "target_date": (now + timedelta(days=45)).isoformat(),
                "completion_pct": 0,
                "features": ["feat-007", "feat-008"],
            },
            {
                "id": "ms-004",
                "title": "Q3 2026 Intelligence Expansion",
                "description": "Predictive scoring v2, cross-niche synergy, enhanced analytics",
                "status": "planned",
                "target_date": (now + timedelta(days=90)).isoformat(),
                "completion_pct": 0,
                "features": ["feat-009", "feat-010"],
            },
        ]

    # ── HELPERS ────────────────────────────────────────────────────────────

    def _get_revenue(self) -> dict:
        out = {"total_24h": 0, "mrr_projected": 0, "calls_24h": 0, "active_buyers": 0}
        try:
            from bots import predictive_revenue
            pl = predictive_revenue.per_lane_forecast() or {}
            totals = pl.get("totals", {}) or {}
            out["total_24h"] = totals.get("revenue_24h", 0)
            out["mrr_projected"] = totals.get("mrr_projected", 0)
            out["calls_24h"] = totals.get("calls_24h", 0)
            out["active_buyers"] = totals.get("active_buyers", 0)
        except Exception:
            pass
        return out

    # ── FEATURES ────────────────────────────────────────────────────────────

    def features(self) -> dict:
        """
        Feature registry with prioritization scores and status breakdown.
        """
        # Calculate impact-effort score for unscored features
        impact_map = {"high": 9, "medium": 6, "low": 3}
        effort_map = {"small": 3, "medium": 6, "large": 9}

        for f in self._features:
            if f["score"] == 0:
                imp = impact_map.get(f.get("impact", "medium"), 6)
                eff = effort_map.get(f.get("effort", "medium"), 6)
                f["score"] = round((imp * 10) / eff, 1)

        by_status = {}
        for f in self._features:
            by_status.setdefault(f["status"], []).append(f)

        by_product = {}
        for f in self._features:
            by_product.setdefault(f["product"], []).append(f)

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "features": sorted(self._features, key=lambda x: x.get("score", 0), reverse=True),
            "summary": {
                "total": len(self._features),
                "by_status": {k: len(v) for k, v in by_status.items()},
                "by_product": {k: len(v) for k, v in by_product.items()},
                "avg_score": round(
                    sum(f.get("score", 0) for f in self._features) / max(len(self._features), 1), 1
                ),
            },
        }

    # ── FEEDBACK ────────────────────────────────────────────────────────────

    def feedback(self) -> dict:
        """
        Customer feedback aggregation with sentiment analysis.
        """
        sentiment_dist = {}
        category_dist = {}
        for fb in self._feedback:
            sentiment_dist[fb.get("sentiment", "neutral")] = \
                sentiment_dist.get(fb.get("sentiment", "neutral"), 0) + 1
            category_dist[fb.get("category", "other")] = \
                category_dist.get(fb.get("category", "other"), 0) + 1

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "feedback": self._feedback,
            "summary": {
                "total": len(self._feedback),
                "by_sentiment": sentiment_dist,
                "by_category": category_dist,
                "by_status": {
                    "under_review": sum(1 for f in self._feedback if f["status"] == "under_review"),
                    "planned": sum(1 for f in self._feedback if f["status"] == "planned"),
                    "acknowledged": sum(1 for f in self._feedback if f["status"] == "acknowledged"),
                },
                "top_request": max(self._feedback, key=lambda x: x.get("frequency", 0))
                if self._feedback else {},
            },
        }

    # ── ROADMAP ─────────────────────────────────────────────────────────────

    def roadmap(self) -> dict:
        """
        Product roadmap with milestone tracking and timeline.
        """
        overall_pct = round(
            sum(m["completion_pct"] for m in self._roadmap)
            / max(len(self._roadmap), 1), 1
        )

        # Overdue milestones
        now = datetime.now(timezone.utc)
        overdue = []
        for m in self._roadmap:
            if m["status"] != "completed" and m.get("target_date"):
                target = datetime.fromisoformat(m["target_date"].replace("Z", "+00:00"))
                if target < now:
                    overdue.append({
                        "id": m["id"],
                        "title": m["title"],
                        "overdue_days": (now - target).days,
                    })

        return {
            "ts": now.isoformat(),
            "milestones": self._roadmap,
            "overall_completion_pct": overall_pct,
            "by_status": {
                "completed": sum(1 for m in self._roadmap if m["status"] == "completed"),
                "in_progress": sum(1 for m in self._roadmap if m["status"] == "in_progress"),
                "planned": sum(1 for m in self._roadmap if m["status"] == "planned"),
            },
            "overdue": overdue,
        }

    # ── RELEASES ────────────────────────────────────────────────────────────

    def releases(self) -> dict:
        """
        Release history and changelog from git and feature data.
        """
        # Build release entries from feature ship dates + git log
        shipped_features = [f for f in self._features if f["shipped_at"]]

        releases = []
        for f in sorted(shipped_features, key=lambda x: x["shipped_at"], reverse=True):
            releases.append({
                "version": f.get("id", ""),
                "title": f["name"],
                "description": f["description"],
                "date": f["shipped_at"],
                "product": f["product"],
                "type": "feature",
            })

        # Try to get recent git commits for changelog
        try:
            import subprocess
            result = subprocess.run(
                ["git", "log", "--oneline", "-15", "--format=%H|%s|%aI"],
                capture_output=True, text=True, timeout=5,
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split("|", 2)
                    if len(parts) == 3:
                        commit_hash, message, date = parts
                        releases.append({
                            "version": commit_hash[:8],
                            "title": message,
                            "date": date.replace("Z", "+00:00"),
                            "product": "unknown",
                            "type": "commit",
                        })
        except Exception:
            pass

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "releases": releases[:25],
            "total_releases": len(releases),
        }

    # ── PRODUCT METRICS ─────────────────────────────────────────────────────

    def product_metrics(self) -> dict:
        """
        Product usage analytics and adoption metrics.
        """
        rev = self._get_revenue()
        calls_24h = rev.get("calls_24h", 0)
        mrr = rev.get("mrr_projected", 0)
        buyers = rev.get("active_buyers", 0)

        product_metrics = [
            {
                "product": "predictive_revenue",
                "name": "Predictive Revenue Engine",
                "usage_24h": calls_24h,
                "active_users": buyers,
                "mrr_contribution": round(mrr * 0.60, 2),
                "adoption_pct": 100,
            },
            {
                "product": "suite_core",
                "name": "Suite Subscription Core",
                "usage_24h": max(1, calls_24h // 10),
                "active_users": max(1, buyers // 3),
                "mrr_contribution": round(mrr * 0.25, 2),
                "adoption_pct": min(100, round(buyers / 10 * 100)),
            },
            {
                "product": "strategic_intelligence",
                "name": "Strategic Intelligence",
                "usage_24h": 24,  # hourly cycles
                "active_users": 2,  # agents
                "mrr_contribution": round(mrr * 0.10, 2),
                "adoption_pct": 100,
            },
            {
                "product": "operations",
                "name": "Operations Dashboard",
                "usage_24h": 48,  # page views
                "active_users": 1,
                "mrr_contribution": 0.0,
                "adoption_pct": 100,
            },
        ]

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "products": product_metrics,
            "summary": {
                "total_products": len(product_metrics),
                "total_usage_24h": sum(p["usage_24h"] for p in product_metrics),
                "total_active_users": sum(p["active_users"] for p in product_metrics),
                "total_mrr": round(sum(p["mrr_contribution"] for p in product_metrics), 2),
                "avg_adoption": round(
                    sum(p["adoption_pct"] for p in product_metrics) / len(product_metrics), 1
                ),
            },
        }

    # ── SNAPSHOT ───────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return product management stats for the SPA."""
        feat = self.features()
        return {
            "feature_count": feat["summary"]["total"],
            "shipped": feat["summary"]["by_status"].get("shipped", 0),
            "in_progress": feat["summary"]["by_status"].get("in_progress", 0),
            "planned": feat["summary"]["by_status"].get("planned", 0),
            "backlog": feat["summary"]["by_status"].get("backlog", 0),
            "avg_score": feat["summary"]["avg_score"],
            "modified": datetime.now(timezone.utc).isoformat(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────────

def register_product_routes(app, require_auth=None):
    """Register Product Management Agent endpoints on a FastAPI app."""
    product = ProductManagementAgent()

    if require_auth:

        @app.get("/api/product/features")
        async def _features(auth=Depends(require_auth)):
            return product.features()

        @app.get("/api/product/feedback")
        async def _feedback(auth=Depends(require_auth)):
            return product.feedback()

        @app.get("/api/product/roadmap")
        async def _roadmap(auth=Depends(require_auth)):
            return product.roadmap()

        @app.get("/api/product/releases")
        async def _releases(auth=Depends(require_auth)):
            return product.releases()

        @app.get("/api/product/metrics")
        async def _metrics(auth=Depends(require_auth)):
            return product.product_metrics()

    else:

        @app.get("/api/product/features")
        async def _features():
            return product.features()

        @app.get("/api/product/feedback")
        async def _feedback():
            return product.feedback()

        @app.get("/api/product/roadmap")
        async def _roadmap():
            return product.roadmap()

        @app.get("/api/product/releases")
        async def _releases():
            return product.releases()

        @app.get("/api/product/metrics")
        async def _metrics():
            return product.product_metrics()

    log.info("[product_mgmt_agent] Routes registered · /api/product/*")


# Lazy import for FastAPI Depends
from fastapi import Depends  # noqa: E402
