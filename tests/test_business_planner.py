"""
Tests for the Business Planner Agent (empire_business_planner.py).
Uses injected mock data sources for fast, deterministic tests.
"""

import pytest
from empire_business_planner import BusinessPlannerAgent


class MockSelfAwareness:
    def snapshot(self):
        return {
            "anomalies": [
                {"title": "zero_revenue_24h", "severity": "critical", "details": "No revenue in last 24h"},
                {"title": "low_win_rate", "severity": "warning", "details": "Win rate dropped to 40%"},
            ],
            "improvements": [
                {"title": "optimize_calls", "severity": "info", "detail": "Call routing improvements available", "suggestion": "Review lane routing"},
            ],
        }


class MockLoopAgent:
    def all_rank_rent_scores(self):
        return [
            {"niche": "Roofing Restoration", "score": 82, "verdict": "STRONG_RENT",
             "price_model": "flat_rent", "estimated_monthly_revenue": 5000,
             "competition": "medium", "typical_lead_value_usd": 350},
            {"niche": "Legal/Pharma Liability", "score": 68, "verdict": "RENTABLE",
             "price_model": "ppl", "estimated_monthly_revenue": 3200,
             "competition": "high", "typical_lead_value_usd": 1200},
            {"niche": "HVAC/Plumbing", "score": 45, "verdict": "BORDERLINE",
             "price_model": "flat_rent", "estimated_monthly_revenue": 1500,
             "competition": "low", "typical_lead_value_usd": 200},
        ]

    def loop_overview(self):
        return {"total_lanes": 36, "total_runs": 514, "total_wins": 373,
                "overall_win_rate": 0.726}

    def evolution_history(self):
        return [{"niche": "Roofing Restoration", "ts": "2026-06-01",
                 "old_strategy": "AGGRESSIVE_STRIKE", "new_strategy": "RECALL_SNIPER"}]

    def optimization_suggestions(self):
        return [{"niche": "Roofing Restoration", "suggestion": "Increase pacing"}]


class MockPsychologyMindMap:
    def get_effectiveness_summary(self):
        return {
            "overall_conversion_rate": 0.35,
            "total_attempts": 120,
            "total_successes": 42,
            "total_combinations_tracked": 18,
            "best_persona": "authority_seeker",
            "best_principle": "social_proof",
            "best_niche": "Roofing Restoration",
        }

    def snapshot(self):
        return {"niche_profiles_count": 3}

    def get_all_niche_profiles(self):
        return [
            {"niche": "Roofing Restoration", "recommended_persona": "authority_seeker",
             "best_principle": "social_proof"},
            {"niche": "Legal/Pharma Liability", "recommended_persona": "risk_averse",
             "best_principle": "scarcity"},
        ]


class MockStrategist:
    def overview(self):
        return {"strategies": ["AGGRESSIVE_STRIKE", "RECALL_SNIPER", "UGLY_BANNER"]}

    def recommendations(self):
        return [{"niche": "Roofing Restoration", "action": "scale"}]

    def trends(self):
        return {"rising_niches": ["Solar Installation", "Debt Settlement"]}

    def generate_narrative(self):
        return {"narrative": "Q2 focus on Roofing Restoration and Legal verticals"}


class MockBusinessManagement:
    def exec_report(self):
        return {
            "health_score": 17.2,
            "health_label": "critical",
            "revenue": {"mrr_projected": 679.5, "revenue_24h": 0.0},
        }

    def okrs(self):
        return {"summary": {"mrr_target": 10000, "current_mrr": 679.5}}

    def health(self):
        return {"status": "critical"}


@pytest.fixture
def planner():
    return BusinessPlannerAgent(
        self_awareness=MockSelfAwareness(),
        loop_agent=MockLoopAgent(),
        psychology_mind_map=MockPsychologyMindMap(),
        strategist=MockStrategist(),
        business_mgmt=MockBusinessManagement(),
    )


class TestBusinessPlanner:
    def test_quarterly_plan_structure(self, planner):
        plan = planner.quarterly_plan()
        assert isinstance(plan, dict)
        assert plan["quarter"] == "Q2 2026"
        assert "generated_at" in plan
        assert "executive_summary" in plan
        assert "niche_plans" in plan
        assert "resource_allocation" in plan
        assert "risk_assessment" in plan
        assert "action_roadmap" in plan
        assert "psychology_insights" in plan
        assert "total_niches_planned" in plan
        assert "total_actions" in plan

    def test_executive_summary(self, planner):
        plan = planner.quarterly_plan()
        exec_sum = plan["executive_summary"]
        assert exec_sum["quarter"] == "Q2 2026"
        assert "current_state" in exec_sum
        assert "targets" in exec_sum
        assert "health_status" in exec_sum
        assert "focus" in exec_sum
        assert exec_sum["targets"]["target_mrr"] >= 10000
        assert 0 <= exec_sum["confidence_score"] <= 100

    def test_niche_plans(self, planner):
        plan = planner.quarterly_plan()
        niches = plan["niche_plans"]
        assert isinstance(niches, list)
        assert len(niches) > 0
        n = niches[0]
        assert "niche" in n
        assert "priority" in n
        assert "rank_rent_score" in n
        assert "verdict" in n
        assert "actions" in n

    def test_niche_plans_sorted_by_priority(self, planner):
        plan = planner.quarterly_plan()
        niches = plan["niche_plans"]
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        priorities = [priority_order.get(n["priority"], 99) for n in niches]
        assert priorities == sorted(priorities)

    def test_action_roadmap(self, planner):
        plan = planner.quarterly_plan()
        actions = plan["action_roadmap"]
        assert isinstance(actions, list)
        if actions:
            a = actions[0]
            assert "id" in a
            assert "action" in a
            assert "category" in a
            assert "priority" in a
            assert "timeline" in a

    def test_risk_assessment(self, planner):
        plan = planner.quarterly_plan()
        risks = plan["risk_assessment"]
        assert "risks" in risks
        assert "total_risks" in risks
        assert "critical_risks" in risks

    def test_psychology_insights(self, planner):
        plan = planner.quarterly_plan()
        psych = plan["psychology_insights"]
        assert "overall_conversion_rate" in psych
        assert "total_attempts" in psych

    def test_resource_allocation(self, planner):
        plan = planner.quarterly_plan()
        res = plan["resource_allocation"]
        assert "recommended_focus" in res
        assert "allocation_pct" in res

    def test_niche_specific_plan(self, planner):
        plan = planner.quarterly_plan()
        niches = plan["niche_plans"]
        assert len(niches) > 0
        first_niche = niches[0]["niche"]
        niche_plan = planner.niche_plan(first_niche)
        assert niche_plan["niche_plan"]["niche"] == first_niche
        assert "executive_summary" in niche_plan

    def test_niche_plan_not_found(self, planner):
        result = planner.niche_plan("NonExistentNicheXYZ")
        assert "error" in result["niche_plan"] or result["niche_plan"]["niche"] == "NonExistentNicheXYZ"

    def test_plan_summary(self, planner):
        summary = planner.plan_summary()
        assert "quarter" in summary
        assert "executive_summary" in summary
        assert "top_priorities" in summary
        assert "action_count" in summary
        assert "niche_count" in summary

    def test_different_quarter(self, planner):
        plan = planner.quarterly_plan(quarter="Q3 2026")
        assert plan["quarter"] == "Q3 2026"

    def test_confidence_score_range(self, planner):
        plan = planner.quarterly_plan()
        score = plan["executive_summary"]["confidence_score"]
        assert 0 <= score <= 100

    def test_mrr_target_reasonable(self, planner):
        plan = planner.quarterly_plan()
        target = plan["executive_summary"]["targets"]["target_mrr"]
        current = plan["executive_summary"]["current_state"]["current_mrr"]
        assert target >= current * 3 or target >= 10000

    def test_regenerate_returns_plan(self, planner):
        plan1 = planner.quarterly_plan()
        plan2 = planner.quarterly_plan()
        assert plan2["total_niches_planned"] == plan1["total_niches_planned"]

    def test_built_in_fallback(self):
        """Test that the agent works without injected mocks (uses real data sources)."""
        b = BusinessPlannerAgent()
        plan = b.quarterly_plan()
        assert "executive_summary" in plan
        assert "niche_plans" in plan

    def test_action_count(self, planner):
        plan = planner.quarterly_plan()
        assert plan["total_actions"] > 0
        assert len(plan["action_roadmap"]) == plan["total_actions"]

    def test_top_priority_niches(self, planner):
        plan = planner.quarterly_plan()
        critical = [n for n in plan["niche_plans"] if n["priority"] == "critical"]
        high = [n for n in plan["niche_plans"] if n["priority"] == "high"]
        # Roofing (score 82) should be critical, Legal (68) should be high at minimum
        critical_names = {n["niche"] for n in critical}
        high_names = {n["niche"] for n in high}
        all_top = critical_names | high_names
        assert "Roofing Restoration" in all_top
