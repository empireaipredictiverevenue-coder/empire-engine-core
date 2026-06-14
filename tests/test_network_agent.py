"""
EMPIRE V49 · NETWORK AGENT UNIT TESTS
======================================
Tests the NetworkAgent class with mocked DB and no-DB fallback.

Covers: network_overview, network_map, member_performance, referral_tracking,
growth_opportunities, compliance_status, network_report.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from empire_network_agent import NetworkAgent, _MOCK_CONTRACTORS, _MOCK_AFFILIATES, _MOCK_PARTNERS, _MOCK_REFERRALS


def _all_mock_members():
    return _MOCK_CONTRACTORS + _MOCK_AFFILIATES + _MOCK_PARTNERS


@pytest.fixture
def agent_no_db():
    """Agent with no DB — uses mock member data."""
    return NetworkAgent(get_db=None)


@pytest.fixture
def agent_with_db():
    """Agent with DB returning real contractors."""
    db = MagicMock()

    def _table(name):
        q = MagicMock()
        if name == "contractors":
            q.select.return_value = q
            q.execute.return_value = MagicMock(data=[
                {"id": "c1", "name": "Real Contractor A",
                 "active": True, "completed_jobs": 30,
                 "trust_score": 0.9, "metro": "Dallas",
                 "specialties": "Roofing", "created_at": "2026-01-01"},
                {"id": "c2", "name": "Real Contractor B",
                 "active": True, "completed_jobs": 16,
                 "trust_score": 0.8, "metro": "Houston",
                 "specialties": "HVAC", "created_at": "2026-02-01"},
            ])
        elif name == "affiliates":
            q.select.return_value = q
            q.execute.return_value = MagicMock(data=[])  # No affiliates table in DB
        elif name == "partners":
            q.select.return_value = q
            q.execute.return_value = MagicMock(data=[])
        else:
            q.execute.return_value = MagicMock(data=[])
        return q

    db.table.side_effect = _table
    return NetworkAgent(get_db=lambda: db)


@pytest.fixture
def agent_empty_db():
    """Agent with DB but empty tables — falls back to mock data."""
    db = MagicMock()

    def _table(name):
        q = MagicMock()
        q.execute.return_value = MagicMock(data=[])
        q.select.return_value = q
        return q

    db.table.side_effect = _table
    return NetworkAgent(get_db=lambda: db)


# ═════════════════════════════════════════════════════════════════════
# CONSTRUCTION
# ═════════════════════════════════════════════════════════════════════

class TestConstruction:
    def test_no_db(self, agent_no_db):
        assert agent_no_db.get_db is None

    def test_with_db(self, agent_with_db):
        assert agent_with_db.get_db is not None


# ═════════════════════════════════════════════════════════════════════
# GET ALL MEMBERS
# ═════════════════════════════════════════════════════════════════════

class TestGetAllMembers:
    def test_returns_mock_when_no_db(self, agent_no_db):
        members = agent_no_db._get_all_members()
        assert len(members) == len(_all_mock_members())

    def test_returns_db_data_when_available(self, agent_with_db):
        members = agent_with_db._get_all_members()
        names = [m["name"] for m in members]
        assert "Real Contractor A" in names
        assert "Real Contractor B" in names

    def test_falls_back_to_mock_when_db_empty(self, agent_empty_db):
        members = agent_empty_db._get_all_members()
        assert len(members) == len(_all_mock_members())


# ═════════════════════════════════════════════════════════════════════
# NETWORK OVERVIEW
# ═════════════════════════════════════════════════════════════════════

class TestNetworkOverview:
    def test_returns_all_keys(self, agent_no_db):
        result = agent_no_db.network_overview()
        for key in ("total_members", "active", "pending", "by_type",
                     "total_revenue", "total_leads", "total_conversions",
                     "conversion_rate_pct", "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_counts_are_accurate(self, agent_no_db):
        result = agent_no_db.network_overview()
        mock_total = len(_all_mock_members())
        assert result["total_members"] == mock_total
        assert result["by_type"]["contractor"] == len(_MOCK_CONTRACTORS)
        assert result["by_type"]["affiliate"] == len(_MOCK_AFFILIATES)

    def test_returns_db_data(self, agent_with_db):
        result = agent_with_db.network_overview()
        assert result["total_members"] == 2
        assert result["active"] == 2


# ═════════════════════════════════════════════════════════════════════
# NETWORK MAP
# ═════════════════════════════════════════════════════════════════════

class TestNetworkMap:
    def test_returns_metros(self, agent_no_db):
        result = agent_no_db.network_map()
        assert "metros" in result
        assert "count" in result
        assert len(result["metros"]) > 0

    def test_metro_has_keys(self, agent_no_db):
        result = agent_no_db.network_map()
        for metro in result["metros"]:
            assert "name" in metro
            assert "members" in metro
            assert "revenue" in metro

    def test_timestamp(self, agent_no_db):
        result = agent_no_db.network_map()
        assert "timestamp" in result


# ═════════════════════════════════════════════════════════════════════
# MEMBER PERFORMANCE
# ═════════════════════════════════════════════════════════════════════

class TestMemberPerformance:
    def test_returns_sorted_members(self, agent_no_db):
        result = agent_no_db.member_performance()
        assert "members" in result
        assert "count" in result
        assert result["count"] == len(_all_mock_members())

    def test_members_sorted_by_revenue_desc(self, agent_no_db):
        result = agent_no_db.member_performance()
        revenues = [m["revenue"] for m in result["members"]]
        assert revenues == sorted(revenues, reverse=True)

    def test_member_has_expected_keys(self, agent_no_db):
        result = agent_no_db.member_performance()
        m = result["members"][0]
        for key in ("id", "name", "type", "niche", "status", "leads",
                     "conversions", "revenue", "conversion_rate_pct"):
            assert key in m, f"Missing key: {key}"

    def test_conversion_rate(self, agent_no_db):
        result = agent_no_db.member_performance()
        for m in result["members"]:
            if m["leads"] > 0:
                expected = round(m["conversions"] / m["leads"] * 100, 1)
                assert m["conversion_rate_pct"] == expected


# ═════════════════════════════════════════════════════════════════════
# REFERRAL TRACKING
# ═════════════════════════════════════════════════════════════════════

class TestReferralTracking:
    def test_returns_all_keys(self, agent_no_db):
        result = agent_no_db.referral_tracking()
        for key in ("referrals", "count", "total_value", "settled_count",
                     "pending_count", "settled_value", "pending_value",
                     "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_counts_are_accurate(self, agent_no_db):
        result = agent_no_db.referral_tracking()
        assert result["count"] == len(_MOCK_REFERRALS)
        assert result["settled_count"] + result["pending_count"] == result["count"]

    def test_values_sum_correctly(self, agent_no_db):
        result = agent_no_db.referral_tracking()
        assert result["total_value"] == result["settled_value"] + result["pending_value"]


# ═════════════════════════════════════════════════════════════════════
# GROWTH OPPORTUNITIES
# ═════════════════════════════════════════════════════════════════════

class TestGrowthOpportunities:
    def test_returns_all_keys(self, agent_no_db):
        result = agent_no_db.growth_opportunities()
        for key in ("niche_gaps", "gap_count", "underserved_metros",
                     "recommendation", "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_gap_count_is_accurate(self, agent_no_db):
        result = agent_no_db.growth_opportunities()
        assert result["gap_count"] == len(result["niche_gaps"])

    def test_recommendation_is_string(self, agent_no_db):
        result = agent_no_db.growth_opportunities()
        assert isinstance(result["recommendation"], str)
        assert len(result["recommendation"]) > 0


# ═════════════════════════════════════════════════════════════════════
# COMPLIANCE STATUS
# ═════════════════════════════════════════════════════════════════════

class TestComplianceStatus:
    def test_returns_all_keys(self, agent_no_db):
        result = agent_no_db.compliance_status()
        for key in ("total_members", "active_contractors", "active_affiliates",
                     "opt_out_rate_pct", "tcpaf_flags", "contract_expiring_30d",
                     "compliant", "notes", "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_compliant_is_bool(self, agent_no_db):
        result = agent_no_db.compliance_status()
        assert isinstance(result["compliant"], bool)


# ═════════════════════════════════════════════════════════════════════
# NETWORK REPORT
# ═════════════════════════════════════════════════════════════════════

class TestNetworkReport:
    def test_contains_all_sections(self, agent_no_db):
        result = agent_no_db.network_report()
        for key in ("overview", "performance", "referrals", "growth",
                     "compliance", "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_sections_are_dicts(self, agent_no_db):
        result = agent_no_db.network_report()
        assert isinstance(result["overview"], dict)
        assert isinstance(result["performance"], dict)
        assert isinstance(result["referrals"], dict)
        assert isinstance(result["growth"], dict)
        assert isinstance(result["compliance"], dict)


# ═════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_all_methods_return_without_crashing(self, agent_no_db):
        """All public methods return without exceptions."""
        methods = [
            agent_no_db.network_overview,
            agent_no_db.network_map,
            agent_no_db.member_performance,
            agent_no_db.referral_tracking,
            agent_no_db.growth_opportunities,
            agent_no_db.compliance_status,
            agent_no_db.network_report,
        ]
        for m in methods:
            result = m()
            assert result is not None, f"{m.__name__} returned None"

    def test_db_tables_missing_does_not_crash(self):
        """When DB tables don't exist, agent falls back to mock data."""
        db = MagicMock()
        db.table.side_effect = Exception("relation does not exist")
        agent = NetworkAgent(get_db=lambda: db)
        members = agent._get_all_members()
        assert len(members) == len(_all_mock_members())
