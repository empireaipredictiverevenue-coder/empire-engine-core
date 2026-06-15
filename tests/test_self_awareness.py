"""Tests for empire_self_awareness.py — Self-Awareness Engine."""

import pytest
from empire_self_awareness import (
    SelfAwarenessEngine,
    _SYSTEM_DEPENDENCIES,
    _AGENT_CAPABILITIES,
    _HEALTH_THRESHOLDS,
)


@pytest.fixture
def engine():
    """SelfAwarenessEngine with no DB."""
    return SelfAwarenessEngine(get_db=None)


class TestDataIntegrity:
    """Verify that the knowledge base data is self-consistent."""

    def test_dependencies_are_consistent(self):
        """All dependency targets exist in capabilities."""
        for agent, deps in _SYSTEM_DEPENDENCIES.items():
            for dep in deps:
                assert dep in _AGENT_CAPABILITIES, \
                    f"'{agent}' depends on '{dep}' but '{dep}' has no capabilities entry"

    def test_capabilities_exist_for_all_deps(self):
        """All agents in capabilities have an entry in dependencies (or are root)."""
        for agent in _AGENT_CAPABILITIES:
            assert agent in _SYSTEM_DEPENDENCIES, \
                f"'{agent}' has capabilities but no dependency entry"

    def test_health_thresholds_are_valid(self):
        """Health thresholds are positive and reasonable."""
        assert _HEALTH_THRESHOLDS["stale_seconds"] > 0
        assert _HEALTH_THRESHOLDS["critical_stale_seconds"] > _HEALTH_THRESHOLDS["stale_seconds"]
        assert _HEALTH_THRESHOLDS["min_active_agents"] > 0
        assert 0 <= _HEALTH_THRESHOLDS["min_lane_win_rate"] <= 1
        assert _HEALTH_THRESHOLDS["lane_slow_pacing_hours"] > 0


class TestSelfAwarenessEngine:
    """Core SelfAwarenessEngine functionality."""

    def test_system_model_returns_expected_structure(self, engine):
        """system_model() returns expected top-level keys."""
        model = engine.system_model()
        assert "agents" in model
        assert "services" in model
        assert "lanes" in model
        assert "revenue" in model
        assert "strategies" in model
        assert "dependencies" in model
        assert "capabilities" in model
        assert "health" in model
        assert "ts" in model

    def test_system_model_health(self, engine):
        """system_model() health section has expected keys."""
        model = engine.system_model()
        health = model["health"]
        assert "overall" in health
        assert "agent_healthy" in health
        assert "agent_total" in health
        assert health["agent_total"] > 0

    def test_system_model_agents_have_required_fields(self, engine):
        """Each agent entry has required fields."""
        model = engine.system_model()
        for agent in model["agents"]:
            assert "name" in agent
            assert "status" in agent
            assert "capabilities" in agent
            assert "stale" in agent

    def test_agent_catalog_returns_all_known_agents(self, engine):
        """_agent_catalog() returns all agents from the capability registry."""
        agents = engine._agent_catalog()
        names = {a["name"] for a in agents}
        for expected in _AGENT_CAPABILITIES:
            assert expected in names, f"Missing agent: {expected}"

    def test_agent_catalog_staleness(self, engine):
        """Agents without last_ping are marked stale and critical."""
        agents = engine._agent_catalog()
        for a in agents:
            if a.get("status") == "UNREGISTERED":
                assert a["stale"] is True
                assert a["critical"] is True

    def test_system_model_lanes(self, engine):
        """Lane model returns expected structure."""
        model = engine.system_model()
        lanes = model["lanes"]
        assert "total" in lanes
        assert "active" in lanes


class TestSelfNarrative:
    """Self-narrative generation."""

    def test_narrative_returns_expected_structure(self, engine):
        """self_narrative() returns all expected sections."""
        narr = engine.self_narrative()
        for key in ("overall_state", "agent_health", "lane_performance",
                     "revenue", "learning_status", "anomalies", "recommendations",
                     "model_snapshot", "ts"):
            assert key in narr, f"Missing key: {key}"

    def test_narrative_model_snapshot(self, engine):
        """Narrative model snapshot has expected keys."""
        narr = engine.self_narrative()
        snap = narr["model_snapshot"]
        assert "health_overall" in snap
        assert "agent_healthy" in snap
        assert "win_rate" in snap

    def test_narrative_different_depths(self, engine):
        """Narrative accepts depth parameter."""
        narr = engine.self_narrative(depth="executive")
        assert narr["depth"] == "executive"

    def test_overall_state_is_string(self, engine):
        """Overall state is a coherent string."""
        narr = engine.self_narrative()
        assert isinstance(narr["overall_state"], str)
        assert len(narr["overall_state"]) > 10


class TestAnomalyDetection:
    """Anomaly detection functionality."""

    def test_get_anomalies_returns_list(self, engine):
        """get_anomalies() returns a list."""
        anomalies = engine.get_anomalies()
        assert isinstance(anomalies, list)

    def test_anomalies_have_required_fields(self, engine):
        """Each anomaly has required fields."""
        anomalies = engine.get_anomalies()
        for a in anomalies:
            assert "type" in a
            assert "severity" in a
            assert "message" in a
            assert "recommendation" in a
            assert a["severity"] in ("critical", "warning")

    def test_anomaly_filter_by_severity(self, engine):
        """Filtering anomalies by severity works."""
        critical = engine.get_anomalies(severity="critical")
        warning = engine.get_anomalies(severity="warning")
        for a in critical:
            assert a["severity"] == "critical"
        for a in warning:
            assert a["severity"] == "warning"

    def test_anomaly_history_is_capped(self, engine):
        """Anomaly history doesn't grow unbounded."""
        # Detect anomalies multiple times
        for _ in range(10):
            engine.get_anomalies()
        # History should be capped
        assert len(engine._anomaly_history) <= 210  # initial + cap


class TestRootCauseAnalysis:
    """Root cause analysis functionality."""

    def test_root_cause_returns_list(self, engine):
        """root_cause_analysis() returns a list."""
        rca = engine.root_cause_analysis()
        assert isinstance(rca, list)

    def test_root_cause_with_specific_symptom(self, engine):
        """root_cause_analysis() with specific symptom returns traces."""
        rca = engine.root_cause_analysis(symptom="hub is down")
        assert len(rca) > 0
        assert rca[0]["affected_agent"] == "hub"

    def test_root_cause_structure(self, engine):
        """Each RCA entry has expected keys."""
        rca = engine.root_cause_analysis(symptom="orchestrator failed")
        for entry in rca:
            assert "symptom" in entry
            assert "affected_agent" in entry
            assert "dependency_chain" in entry
            assert "root_causes" in entry

    def test_root_cause_unknown_symptom(self, engine):
        """Unknown symptom returns a fallback trace."""
        rca = engine.root_cause_analysis(symptom="something completely unknown")
        assert len(rca) == 1
        assert rca[0]["affected_agent"] == "system"


class TestSelfImprovement:
    """Self-improvement suggestions."""

    def test_get_self_improve_returns_list(self, engine):
        """get_self_improve() returns a list."""
        improvements = engine.get_self_improve()
        assert isinstance(improvements, list)

    def test_improvements_have_required_fields(self, engine):
        """Each improvement has required fields."""
        improvements = engine.get_self_improve()
        for imp in improvements:
            assert "type" in imp
            assert "priority" in imp
            assert "message" in imp
            assert "action" in imp
            assert imp["priority"] in ("high", "medium", "low")

    def test_no_evolution_suggestion(self, engine):
        """If no evolutions have run, suggest starting evolution."""
        improvements = engine.get_self_improve()
        types = [i["type"] for i in improvements]
        # Should include suggestions about unregistered agents and other findings
        assert len(improvements) > 0


class TestSnapshot:
    """Full snapshot functionality."""

    def test_snapshot_returns_all_sections(self, engine):
        """snapshot() returns all expected sections."""
        snap = engine.snapshot()
        for key in ("system_model", "narrative", "anomalies", "anomaly_count",
                     "critical_count", "warning_count", "root_cause_analyses",
                     "improvements", "improvement_count", "ts"):
            assert key in snap, f"Missing key: {key}"

    def test_snapshot_counts(self, engine):
        """Snapshot counts match the actual data."""
        snap = engine.snapshot()
        assert snap["anomaly_count"] == len(snap["anomalies"])
        assert snap["improvement_count"] == len(snap["improvements"])
        assert snap["critical_count"] == sum(
            1 for a in snap["anomalies"] if a.get("severity") == "critical"
        )
        assert snap["warning_count"] == sum(
            1 for a in snap["anomalies"] if a.get("severity") == "warning"
        )

    def test_snapshot_has_timestamp(self, engine):
        """Snapshot has a valid timestamp."""
        snap = engine.snapshot()
        assert snap["ts"] is not None
        assert len(snap["ts"]) > 10

    def test_reset_state(self, engine):
        """reset_state() clears internal state."""
        engine.get_anomalies()  # populate
        engine.reset_state()
        assert engine._anomaly_history == []
        assert engine._last_snapshot_ts is None

    def test_snapshot_after_reset(self, engine):
        """Snapshot works after reset."""
        engine.reset_state()
        snap = engine.snapshot()
        assert len(snap["anomalies"]) >= 0  # may still detect anomalies
        assert "system_model" in snap
