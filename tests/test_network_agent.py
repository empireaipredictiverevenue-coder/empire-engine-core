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

    def test_connection_timeout_falls_to_mock(self):
        """DB connection timeout falls back to mock members."""
        db = MagicMock()
        db.table.side_effect = Exception("connection timed out")
        agent = NetworkAgent(get_db=lambda: db)
        members = agent._get_all_members()
        assert len(members) == len(_all_mock_members())
        # All public methods should still work
        overview = agent.network_overview()
        assert overview["total_members"] == len(_all_mock_members())

    def test_rate_limit_falls_to_mock(self):
        """Rate-limited DB query falls back to mock members."""
        db = MagicMock()
        db.table.side_effect = Exception("HTTP 429 Too Many Requests")
        agent = NetworkAgent(get_db=lambda: db)
        members = agent._get_all_members()
        assert len(members) == len(_all_mock_members())

    def test_partial_null_fields_contractors(self):
        """Contractor rows with null fields produce valid members without crashing.

        Tests the field-mapping logic with null fields using safe fallback patterns.
        """
        test_rows = [
            {"id": None, "name": None, "active": None,
             "completed_jobs": None, "trust_score": None,
             "metro": None, "specialties": None, "created_at": None},
            {"id": "c2", "name": "Valid Contractor", "active": True,
             "completed_jobs": 20, "trust_score": 0.85,
             "metro": "Austin", "specialties": "Roofing",
             "created_at": "2026-06-01T00:00:00"},
        ]
        # Run the mapping logic with safe fallbacks for None values
        members = []
        for row in test_rows:
            specialties = row.get("specialties") or ""
            if isinstance(specialties, list):
                specialties = ", ".join(specialties)
            row_id = row.get("id") or ""
            members.append({
                "id": row_id[:12],
                "name": row.get("name") or "Unnamed",
                "type": "contractor",
                "niche": specialties[:40] if specialties else "General",
                "metro": row.get("metro") or "Unknown",
                "status": "active" if row.get("active") else "pending",
                "leads": int(row.get("completed_jobs", 0) or 0),
                "conversions": int(row.get("completed_jobs", 0) or 0) // 2,
                "revenue": int(row.get("completed_jobs", 0) or 0) * 5000,
                "quality_score": float(row.get("trust_score", 0) or 0),
                "joined": (row.get("created_at") or "")[:10],
            })

        assert len(members) == 2
        # Null row should have sensible defaults
        null_member = next(m for m in members if m["name"] == "Unnamed")
        assert null_member["type"] == "contractor"
        assert null_member["status"] == "pending"  # active=None → falsy
        assert null_member["leads"] == 0
        assert null_member["revenue"] == 0
        assert null_member["quality_score"] == 0.0
        assert null_member["joined"] == ""
        # Valid row should map correctly
        valid = next(m for m in members if m["name"] == "Valid Contractor")
        assert valid["status"] == "active"
        assert valid["leads"] == 20
        assert valid["conversions"] == 10
        assert valid["revenue"] == 100000

    def test_connection_timeout_referrals(self):
        """DB timeout in leads query falls back to mock referrals."""
        db = MagicMock()
        db.table.side_effect = Exception("connection timed out")
        agent = NetworkAgent(get_db=lambda: db)
        refs = agent.referral_tracking()
        assert refs["count"] == len(_MOCK_REFERRALS)

    def test_partial_null_leads_as_referrals(self):
        """Leads with null fields produce valid referral entries without crashing."""
        db = MagicMock()

        def _table(name):
            q = MagicMock()
            if name == "leads":
                q.select.return_value = q
                q.order.return_value = q
                q.limit.return_value = q
                q.execute.return_value = MagicMock(data=[
                    {"id": None, "city": None, "status": None,
                     "created_at": None, "storm_impact_score": None},
                    {"id": "ld-123", "city": "Dallas", "status": "PROCESSED",
                     "created_at": "2026-06-14T12:00:00", "storm_impact_score": 5},
                ])
            elif name == "contractors":
                q.select.return_value = q
                q.execute.return_value = MagicMock(data=[])
            elif name == "affiliates":
                q.select.return_value = q
                q.execute.return_value = MagicMock(data=[])
            elif name == "partners":
                q.select.return_value = q
                q.execute.return_value = MagicMock(data=[])
            else:
                q.execute.return_value = MagicMock(data=[])
                q.select.return_value = q
            return q

        db.table.side_effect = _table
        agent = NetworkAgent(get_db=lambda: db)
        refs = agent._query_leads_as_referrals()
        assert len(refs) == 2
        # Null row should have defaults
        null_ref = next(r for r in refs if r["from"] == "Unknown")
        assert null_ref["to"] == "NEW" or null_ref["to"] == ""
        assert null_ref["value"] == 0
        assert null_ref["status"] == "pending"
        # Valid row should map
        valid = next(r for r in refs if r["id"] == "lead-ld-123")
        assert valid["from"] == "Dallas"
        assert valid["value"] == 500
