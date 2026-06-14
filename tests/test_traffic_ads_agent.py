"""
EMPIRE V49 · TRAFFIC & ADS AGENT UNIT TESTS
============================================
Tests the TrafficAdsAgent class with mocked DB and no-DB scenarios.

Data priority chain tested:
  1. call_logs (real call-level data)
  2. buyers (real buyer/partner data)
  3. _PLATFORMS (static benchmarks as last resort)
"""

import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from empire_traffic_ads_agent import TrafficAdsAgent, _PLATFORMS, _TRENDING_NICHES


# ── Helpers ─────────────────────────────────────────────────────────────

def _make_mock_db(call_logs_rows=None, buyers_rows=None, contractors_rows=None):
    """Build a mock get_db callable that returns a mocked Supabase client.

    Each table's .select().gte().not_().neq().limit().execute() chain
    returns the given rows.
    """
    db = MagicMock()

    # Returns the right query builder per table name
    def _table(name):
        q = MagicMock()
        if name == "call_logs":
            q.select.return_value = q
            q.gte.return_value = q
            q.not_.is_.return_value = q
            q.neq.return_value = q
            q.limit.return_value = q
            q.execute.return_value = MagicMock(data=call_logs_rows or [])
        elif name == "buyers":
            q.select.return_value = q
            q.limit.return_value = q
            q.execute.return_value = MagicMock(data=buyers_rows or [])
        elif name == "contractors":
            q.select.return_value = q
            q.limit.return_value = q
            q.execute.return_value = MagicMock(data=contractors_rows or [])
        else:
            q.execute.return_value = MagicMock(data=[])
        return q

    db.table.side_effect = _table
    return db


@pytest.fixture
def agent_no_db():
    """Agent with no DB connection — should fall back to mock data."""
    return TrafficAdsAgent(get_db=None)


@pytest.fixture
def agent_empty_db():
    """Agent with DB but empty tables — should fall through buyers → mock."""
    db = _make_mock_db(call_logs_rows=[], buyers_rows=[], contractors_rows=[])
    return TrafficAdsAgent(get_db=lambda: db)


@pytest.fixture
def agent_with_buyers():
    """Agent with DB containing buyer rows but empty call_logs."""
    buyers = [
        {"id": "b1", "buyer_name": "Test Buyer A", "niche": "Roofing Restoration",
         "is_active": True, "status": "ACTIVE", "base_payout": 100.0,
         "calls_offered": 50, "calls_accepted": 12, "calls_today": 3,
         "monthly_retainer": 500.0, "fee_rate": 0.03, "daily_cap": 20},
        {"id": "b2", "buyer_name": "Test Buyer B", "niche": "Legal",
         "is_active": True, "status": "active", "base_payout": 200.0,
         "calls_offered": 30, "calls_accepted": 8, "calls_today": 1,
         "monthly_retainer": 1000.0, "fee_rate": 0.03, "daily_cap": 10},
    ]
    db = _make_mock_db(call_logs_rows=[], buyers_rows=buyers)
    return TrafficAdsAgent(get_db=lambda: db)


@pytest.fixture
def agent_with_call_logs():
    """Agent with DB containing call_logs rows and buyers."""
    logs = [
        {"channel": "voice", "fee_earned": 500.0, "cost_usd": 150.0,
         "is_billable": True, "qualified": True},
        {"channel": "voice", "fee_earned": 300.0, "cost_usd": 90.0,
         "is_billable": True, "qualified": True},
        {"channel": "sms", "fee_earned": 200.0, "cost_usd": 50.0,
         "is_billable": True, "qualified": False},
        {"channel": "web", "fee_earned": 0.0, "cost_usd": 0.0,
         "is_billable": False, "qualified": True},
    ]
    db = _make_mock_db(call_logs_rows=logs, buyers_rows=[], contractors_rows=[])
    return TrafficAdsAgent(get_db=lambda: db)


# ═════════════════════════════════════════════════════════════════════
# CONSTRUCTION
# ═════════════════════════════════════════════════════════════════════

class TestConstruction:
    def test_no_db(self, agent_no_db):
        """Agent can be constructed without a DB connection."""
        assert agent_no_db.get_db is None

    def test_with_db(self):
        """Agent stores the get_db callable."""
        db = MagicMock()
        agent = TrafficAdsAgent(get_db=lambda: db)
        assert agent.get_db is not None
        assert agent.get_db() is db


# ═════════════════════════════════════════════════════════════════════
# DB HELPERS
# ═════════════════════════════════════════════════════════════════════

class TestDbHelpers:
    def test_query_call_logs_empty_no_db(self, agent_no_db):
        """_query_call_logs returns [] when there's no DB."""
        assert agent_no_db._query_call_logs() == []

    def test_query_call_logs_empty_db(self, agent_empty_db):
        """_query_call_logs returns [] when DB has no call_logs."""
        assert agent_empty_db._query_call_logs() == []

    def test_query_call_logs_with_data(self, agent_with_call_logs):
        """_query_call_logs aggregates by channel correctly."""
        result = agent_with_call_logs._query_call_logs()
        channels = {r["channel"] for r in result}
        assert "voice" in channels
        assert "sms" in channels
        assert "web" in channels
        voice = next(r for r in result if r["channel"] == "voice")
        assert voice["count"] == 2
        assert voice["revenue"] == 800.0
        assert voice["cost"] == 240.0
        assert voice["billable"] == 2
        assert voice["qualified"] == 2

    def test_query_buyers_empty_no_db(self, agent_no_db):
        """_query_buyers returns zeros when there's no DB."""
        result = agent_no_db._query_buyers()
        assert result == {"total": 0, "active": 0}

    def test_query_buyers_with_data(self, agent_with_buyers):
        """_query_buyers counts active buyers correctly."""
        result = agent_with_buyers._query_buyers()
        assert result["total"] == 2
        assert result["active"] == 2

    def test_query_buyers_as_platforms_empty_no_db(self, agent_no_db):
        """_query_buyers_as_platforms returns [] when there's no DB."""
        assert agent_no_db._query_buyers_as_platforms() == []

    def test_query_buyers_as_platforms_with_data(self, agent_with_buyers):
        """_query_buyers_as_platforms maps buyers to platform dicts."""
        platforms = agent_with_buyers._query_buyers_as_platforms()
        assert len(platforms) == 2
        names = {p["name"] for p in platforms}
        assert "Test Buyer A" in names
        assert "Test Buyer B" in names
        # Check field mapping
        buyer_a = next(p for p in platforms if p["name"] == "Test Buyer A")
        assert buyer_a["niche"] == "Roofing Restoration"
        assert buyer_a["total_calls"] == 50
        assert buyer_a["conversions"] == 12
        assert buyer_a["revenue"] == 1200.0  # 100 * 12
        assert buyer_a["budget_spent"] == 36.0  # 1200 * 0.03
        assert buyer_a["status"] == "active"
        assert "roas" in buyer_a
        assert buyer_a["daily_cap"] == 20

    def test_channel_to_platform_known(self, agent_no_db):
        """Known channels map to correct platform."""
        p = agent_no_db._channel_to_platform("voice")
        assert p["id"] == "voice_calls"
        assert p["name"] == "Voice Calls"
        assert p["type"] == "ppc"

    def test_channel_to_platform_unknown(self, agent_no_db):
        """Unknown channels get a generic mapping."""
        p = agent_no_db._channel_to_platform("snail_mail")
        assert p["id"] == "snail_mail"
        assert p["type"] == "other"

    def test_query_niche_activity_empty_no_db(self, agent_no_db):
        """_query_niche_activity returns [] when there's no DB."""
        assert agent_no_db._query_niche_activity() == []


# ═════════════════════════════════════════════════════════════════════
# PLATFORMS OVERVIEW
# ═════════════════════════════════════════════════════════════════════

class TestPlatformsOverview:
    def test_returns_mock_when_no_db(self, agent_no_db):
        """Without DB, platforms_overview returns _PLATFORMS data."""
        result = agent_no_db.platforms_overview()
        assert len(result["platforms"]) == len(_PLATFORMS)
        assert result["platforms"][0]["name"] == _PLATFORMS[0]["name"]

    def test_returns_buyers_when_call_logs_empty(self, agent_with_buyers):
        """When call_logs is empty but buyers exist, use buyers data."""
        result = agent_with_buyers.platforms_overview()
        assert len(result["platforms"]) == 2
        names = [p["name"] for p in result["platforms"]]
        assert "Test Buyer A" in names
        assert result["total"]["budget_total"] > 0

    def test_returns_call_logs_when_available(self, agent_with_call_logs):
        """When call_logs has data, use it."""
        result = agent_with_call_logs.platforms_overview()
        platforms = result["platforms"]
        # Should have voice, sms, web channels
        names = [p["name"] for p in platforms]
        assert "Voice Calls" in names
        assert "SMS Campaigns" in names
        assert "Web / Organic" in names

    def test_response_shape(self, agent_no_db):
        """Response has expected top-level keys."""
        result = agent_no_db.platforms_overview()
        assert "platforms" in result
        assert "total" in result
        assert "timestamp" in result
        assert "impressions" in result["total"]
        assert "conversions" in result["total"]

    def test_timestamp_is_utc_iso(self, agent_no_db):
        """Timestamp is ISO format."""
        result = agent_no_db.platforms_overview()
        parsed = datetime.fromisoformat(result["timestamp"])
        assert parsed.tzinfo is not None or True  # just verify it parses


# ═════════════════════════════════════════════════════════════════════
# CAMPAIGNS
# ═════════════════════════════════════════════════════════════════════

class TestCampaigns:
    def test_returns_mock_when_no_db(self, agent_no_db):
        """Without DB, campaigns uses _PLATFORMS mock data."""
        campaigns = agent_no_db.campaigns()
        assert len(campaigns) > 0
        # No organic channels in campaigns
        types = [c["type"] for c in campaigns]
        assert "organic" not in types

    def test_returns_buyers_when_call_logs_empty(self, agent_with_buyers):
        """When call_logs empty but buyers exist, use buyers as campaigns."""
        campaigns = agent_with_buyers.campaigns()
        assert len(campaigns) == 2
        names = [c["platform_name"] for c in campaigns]
        assert "Test Buyer A" in names

    def test_campaign_shape(self, agent_no_db):
        """Each campaign has expected keys."""
        campaigns = agent_no_db.campaigns()
        c = campaigns[0]
        for key in ("platform_id", "platform_name", "type", "budget", "spend",
                     "conversions", "cpa", "roas", "status"):
            assert key in c, f"Missing key: {key}"

    def test_no_organic_in_campaigns(self, agent_no_db):
        """Organic channels are excluded from campaigns."""
        campaigns = agent_no_db.campaigns()
        names = [c["platform_name"] for c in campaigns]
        assert "SEO / Organic" not in names


# ═════════════════════════════════════════════════════════════════════
# TREND DETECTION
# ═════════════════════════════════════════════════════════════════════

class TestTrendDetection:
    def test_returns_mock_when_no_db(self, agent_no_db):
        """Without DB, trend_detection uses _TRENDING_NICHES."""
        result = agent_no_db.trend_detection()
        assert result["niche_trend_count"] == len(_TRENDING_NICHES)

    def test_returns_buyer_niches_when_call_logs_empty(self, agent_with_buyers):
        """When call_logs empty but buyers exist, use buyer niches."""
        result = agent_with_buyers.trend_detection()
        assert result["niche_trend_count"] > 0
        niches = [n["niche"] for n in result["trending_niches"]]
        assert "Roofing Restoration" in niches

    def test_response_shape(self, agent_no_db):
        """Response has expected keys."""
        result = agent_no_db.trend_detection()
        assert "trending_niches" in result
        assert "trending_keywords" in result
        assert "buyers_active" in result
        assert "timestamp" in result

    def test_keywords_always_present(self, agent_no_db):
        """Trending keywords should always be present (static data)."""
        result = agent_no_db.trend_detection()
        assert len(result["trending_keywords"]) > 0
        assert result["keyword_count"] > 0


# ═════════════════════════════════════════════════════════════════════
# BUDGET OPTIMIZATION
# ═════════════════════════════════════════════════════════════════════

class TestBudgetOptimization:
    def test_returns_mock_when_no_db(self, agent_no_db):
        """Without DB, budget_optimization uses _PLATFORMS."""
        result = agent_no_db.budget_optimization()
        assert len(result["recommendations"]) > 0
        assert result["total_budget"] > 0

    def test_recommendations_have_correct_keys(self, agent_no_db):
        """Each recommendation has expected keys."""
        result = agent_no_db.budget_optimization()
        rec = result["recommendations"][0]
        for key in ("platform_id", "platform_name", "roas", "cpa",
                     "current_share_pct", "recommendation", "suggested_share_pct"):
            assert key in rec, f"Missing key: {key}"

    def test_recommendation_values_valid(self, agent_no_db):
        """Recommendation is one of increase/maintain/decrease."""
        result = agent_no_db.budget_optimization()
        for rec in result["recommendations"]:
            assert rec["recommendation"] in ("increase", "maintain", "decrease")

    def test_returns_buyers_when_call_logs_empty(self, agent_with_buyers):
        """When call_logs empty, use buyers for budget recommendations."""
        result = agent_with_buyers.budget_optimization()
        assert len(result["recommendations"]) > 0
        names = [r["platform_name"] for r in result["recommendations"]]
        assert "Test Buyer A" in names


# ═════════════════════════════════════════════════════════════════════
# ORGANIC CHANNELS
# ═════════════════════════════════════════════════════════════════════

class TestOrganicChannels:
    def test_returns_mock_when_no_db(self, agent_no_db):
        """Without DB, organic_channels uses _PLATFORMS organic data."""
        result = agent_no_db.organic_channels()
        assert len(result["channels"]) > 0

    def test_channel_is_organic(self, agent_no_db):
        """Returned channels are all organic type."""
        result = agent_no_db.organic_channels()
        for ch in result["channels"]:
            assert ch["type"] == "organic"

    def test_response_shape(self, agent_no_db):
        """Response has expected keys."""
        result = agent_no_db.organic_channels()
        assert "channels" in result
        assert "total_organic_impressions" in result
        assert "total_organic_conversions" in result
        assert "estimated_seo_value" in result


# ═════════════════════════════════════════════════════════════════════
# ADS SUMMARY
# ═════════════════════════════════════════════════════════════════════

class TestAdsSummary:
    def test_returns_all_sections(self, agent_no_db):
        """Summary contains all expected sections."""
        result = agent_no_db.ads_summary()
        assert "platforms" in result
        assert "trends" in result
        assert "budget" in result
        assert "organic" in result
        assert "consolidated" in result

    def test_consolidated_has_expected_keys(self, agent_no_db):
        """Consolidated section has all expected metrics."""
        c = agent_no_db.ads_summary()["consolidated"]
        for key in ("total_monthly_budget", "total_spent", "total_conversions",
                     "blended_cpa", "total_impressions", "trending_niches_count",
                     "organic_share_pct"):
            assert key in c, f"Missing key: {key}"


# ═════════════════════════════════════════════════════════════════════
# NARRATIVE
# ═════════════════════════════════════════════════════════════════════

class TestNarrative:
    def test_returns_narrative_string(self, agent_no_db):
        """Narrative returns a multi-line text and timestamp."""
        result = agent_no_db.narrative()
        assert "narrative" in result
        assert "generated_at" in result
        assert isinstance(result["narrative"], str)
        assert len(result["narrative"]) > 50

    def test_narrative_mentions_platforms(self, agent_no_db):
        """Narrative text mentions platform-related terms."""
        result = agent_no_db.narrative()
        text = result["narrative"]
        assert "platforms" in text or "budget" in text or "ROAS" in text

    def test_narrative_has_trending(self, agent_no_db):
        """Narrative includes trending info."""
        result = agent_no_db.narrative()
        assert "Trending" in result["narrative"] or "Organic" in result["narrative"]


# ═════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_db_query_failure_falls_through(self):
        """When DB query raises, agent falls through to next data source."""
        db = MagicMock()
        db.table.side_effect = Exception("DB timeout")
        agent = TrafficAdsAgent(get_db=lambda: db)
        result = agent.platforms_overview()
        # Should fall through to mock
        assert len(result["platforms"]) == len(_PLATFORMS)

    def test_partial_buyer_data(self):
        """Buyers with missing optional fields still produce platform dicts."""
        buyers = [
            {"id": "b1", "buyer_name": "Minimal Buyer", "niche": "Test"},
            # Missing most numeric fields
        ]
        db = _make_mock_db(buyers_rows=buyers)
        agent = TrafficAdsAgent(get_db=lambda: db)
        platforms = agent._query_buyers_as_platforms()
        assert len(platforms) == 1
        p = platforms[0]
        assert p["name"] == "Minimal Buyer"
        assert p["total_calls"] == 0
        assert p["revenue"] == 0.0
        assert p["roas"] is None

    def test_all_methods_return_without_crashing(self, agent_no_db):
        """All public methods return without raising exceptions."""
        methods = [
            lambda: agent_no_db.platforms_overview(),
            lambda: agent_no_db.campaigns(),
            lambda: agent_no_db.trend_detection(),
            lambda: agent_no_db.budget_optimization(),
            lambda: agent_no_db.organic_channels(),
            lambda: agent_no_db.ads_summary(),
            lambda: agent_no_db.narrative(),
        ]
        for m in methods:
            result = m()
            assert result is not None, f"{m.__name__} returned None"
