"""
EMPIRE V49 · LOOP ENGINEERING AGENT UNIT TESTS
===============================================
Tests the LoopAgent class — lane optimization, pacing, strategy comparison,
and throughput forecasting. Does not use a DB (all mock data).
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from empire_loop_agent import LoopAgent, _LANE_GROUPS, _MOCK_LANE_STATS, _STRATEGY_COMPARE


@pytest.fixture
def agent():
    """LoopAgent with no DB (all mock data)."""
    return LoopAgent(get_db=None)


# ═════════════════════════════════════════════════════════════════════
# CONSTRUCTION
# ═════════════════════════════════════════════════════════════════════

class TestConstruction:
    def test_no_db(self, agent):
        assert agent.get_db is None

    def test_constructor_accepts_db(self):
        db = MagicMock()
        agent = LoopAgent(get_db=lambda: db)
        assert agent.get_db() is db


# ═════════════════════════════════════════════════════════════════════
# LOOP OVERVIEW
# ═════════════════════════════════════════════════════════════════════

class TestLoopOverview:
    def test_returns_all_keys(self, agent):
        result = agent.loop_overview()
        for key in ("total_lanes", "assigned_lanes", "active_lanes", "idle_lanes",
                     "unassigned_lanes", "total_runs", "total_wins", "total_revenue",
                     "overall_win_rate", "niches", "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_total_lanes_is_36(self, agent):
        result = agent.loop_overview()
        assert result["total_lanes"] == 36

    def test_assigned_lanes_matches_config(self, agent):
        result = agent.loop_overview()
        expected = sum(len(g["lanes"]) for g in _LANE_GROUPS.values())
        assert result["assigned_lanes"] == expected

    def test_win_rate_is_between_0_and_1(self, agent):
        result = agent.loop_overview()
        assert 0 <= result["overall_win_rate"] <= 1

    def test_niches_has_expected_keys(self, agent):
        result = agent.loop_overview()
        for niche in _LANE_GROUPS:
            assert niche in result["niches"], f"Missing niche: {niche}"


# ═════════════════════════════════════════════════════════════════════
# LANE DETAIL
# ═════════════════════════════════════════════════════════════════════

class TestLaneDetail:
    def test_known_lane_returns_data(self, agent):
        detail = agent.lane_detail(0)
        assert detail["lane_id"] == 0
        assert "niche" in detail
        assert "strategy" in detail
        assert "stats" in detail
        assert "win_rate" in detail
        assert "recommendation" in detail

    def test_unknown_lane_returns_no_data(self, agent):
        detail = agent.lane_detail(99)
        assert detail["status"] == "no_data"

    def test_recommendation_for_high_win_rate(self, agent):
        detail = agent.lane_detail(4)  # 82 wins / 100 runs = 0.82
        assert detail["recommendation"] == "AGGRESSIVE_EXECUTE"

    def test_recommendation_for_few_runs(self, agent):
        detail = agent.lane_detail(3)  # 4 runs
        assert detail["recommendation"] == "EXPLORE_NEED_MORE_DATA"

    def test_lane_detail_has_avg_deal(self, agent):
        detail = agent.lane_detail(0)
        assert "avg_deal" in detail
        assert detail["avg_deal"] > 0

    def test_lane_detail_has_pacing_hours(self, agent):
        detail = agent.lane_detail(0)
        assert "pacing_hours" in detail
        assert detail["pacing_hours"] > 0


# ═════════════════════════════════════════════════════════════════════
# ALL LANES
# ═════════════════════════════════════════════════════════════════════

class TestAllLanes:
    def test_returns_lanes_list(self, agent):
        lanes = agent.all_lanes()
        assert isinstance(lanes, list)
        assert len(lanes) > 0

    def test_each_lane_has_lane_id(self, agent):
        lanes = agent.all_lanes()
        for lane in lanes:
            assert "lane_id" in lane

    def test_lanes_match_config(self, agent):
        lanes = agent.all_lanes()
        lane_ids = {l["lane_id"] for l in lanes}
        expected = {lid for g in _LANE_GROUPS.values() for lid in g["lanes"]}
        assert lane_ids.issubset(expected)


# ═════════════════════════════════════════════════════════════════════
# PACING ANALYSIS
# ═════════════════════════════════════════════════════════════════════

class TestPacingAnalysis:
    def test_returns_all_keys(self, agent):
        result = agent.pacing_analysis()
        for key in ("niches", "fastest", "slowest", "overall_avg_pacing", "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_fastest_and_slowest_are_strings(self, agent):
        result = agent.pacing_analysis()
        if result["fastest"]:
            assert isinstance(result["fastest"], str)
        if result["slowest"]:
            assert isinstance(result["slowest"], str)

    def test_overall_avg_is_positive(self, agent):
        result = agent.pacing_analysis()
        assert result["overall_avg_pacing"] > 0

    def test_niches_have_expected_keys(self, agent):
        result = agent.pacing_analysis()
        for n in result["niches"]:
            for key in ("niche", "lanes", "active", "avg_pacing_hours", "total_runs", "runs_per_day"):
                assert key in n, f"Missing key: {key}"


# ═════════════════════════════════════════════════════════════════════
# STRATEGY PERFORMANCE
# ═════════════════════════════════════════════════════════════════════

class TestStrategyPerformance:
    def test_returns_all_keys(self, agent):
        result = agent.strategy_performance()
        for key in ("strategies", "count", "best_by_win_rate", "best_by_revenue", "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_count_matches_data(self, agent):
        result = agent.strategy_performance()
        assert result["count"] == len(_STRATEGY_COMPARE)
        assert result["count"] == len(result["strategies"])

    def test_best_by_win_rate_has_highest_rate(self, agent):
        result = agent.strategy_performance()
        max_rate = max(s["avg_win_rate"] for s in _STRATEGY_COMPARE)
        assert result["best_by_win_rate"]["avg_win_rate"] == max_rate

    def test_best_by_revenue_has_highest_revenue(self, agent):
        result = agent.strategy_performance()
        max_rev = max(s["total_revenue"] for s in _STRATEGY_COMPARE)
        assert result["best_by_revenue"]["total_revenue"] == max_rev

    def test_each_strategy_has_expected_keys(self, agent):
        result = agent.strategy_performance()
        for s in result["strategies"]:
            for key in ("strategy", "active_lanes", "total_runs", "total_wins",
                         "total_revenue", "avg_win_rate", "best_niche"):
                assert key in s, f"Missing key: {key}"


# ═════════════════════════════════════════════════════════════════════
# THROUGHPUT FORECAST
# ═════════════════════════════════════════════════════════════════════

class TestThroughputForecast:
    def test_returns_all_keys(self, agent):
        result = agent.throughput_forecast()
        for key in ("daily_capacity", "weekly_capacity", "monthly_capacity",
                     "current_monthly_runs", "utilization_pct", "bottleneck_niches",
                     "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_capacities_are_positive(self, agent):
        result = agent.throughput_forecast()
        assert result["daily_capacity"] > 0
        assert result["weekly_capacity"] > 0
        assert result["monthly_capacity"] > 0

    def test_bottleneck_niches_is_list(self, agent):
        result = agent.throughput_forecast()
        assert isinstance(result["bottleneck_niches"], list)


# ═════════════════════════════════════════════════════════════════════
# OPTIMIZATION SUGGESTIONS
# ═════════════════════════════════════════════════════════════════════

class TestOptimizationSuggestions:
    def test_returns_list(self, agent):
        suggestions = agent.optimization_suggestions()
        assert isinstance(suggestions, list)

    def test_suggestion_has_expected_keys(self, agent):
        suggestions = agent.optimization_suggestions()
        if suggestions:
            s = suggestions[0]
            for key in ("lane_id", "niche", "strategy", "issue", "recommendation"):
                assert key in s, f"Missing key: {key}"

    def test_recommendations_are_strings(self, agent):
        suggestions = agent.optimization_suggestions()
        for s in suggestions:
            assert isinstance(s["recommendation"], str)
            assert len(s["recommendation"]) > 0


# ═════════════════════════════════════════════════════════════════════
# LOOP REPORT
# ═════════════════════════════════════════════════════════════════════

class TestLoopReport:
    def test_contains_all_sections(self, agent):
        result = agent.loop_report()
        for key in ("overview", "pacing", "strategies", "forecast",
                     "optimizations", "optimization_count", "timestamp"):
            assert key in result, f"Missing key: {key}"

    def test_sections_are_dicts(self, agent):
        result = agent.loop_report()
        assert isinstance(result["overview"], dict)
        assert isinstance(result["pacing"], dict)
        assert isinstance(result["strategies"], dict)
        assert isinstance(result["forecast"], dict)
        assert isinstance(result["optimizations"], list)

    def test_optimization_count_matches(self, agent):
        result = agent.loop_report()
        assert result["optimization_count"] == len(result["optimizations"])


# ═════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_all_methods_return_without_crashing(self, agent):
        """All public methods return without exceptions."""
        methods = [
            agent.loop_overview,
            lambda: agent.lane_detail(0),
            lambda: agent.lane_detail(99),
            agent.all_lanes,
            agent.pacing_analysis,
            agent.strategy_performance,
            agent.throughput_forecast,
            agent.optimization_suggestions,
            agent.loop_report,
        ]
        for m in methods:
            result = m()
            assert result is not None, f"{m.__name__} returned None"

    def test_timestamps_are_iso(self, agent):
        """All responses have parseable ISO timestamps."""
        result = agent.loop_overview()
        parsed = datetime.fromisoformat(result["timestamp"])
        assert parsed is not None
