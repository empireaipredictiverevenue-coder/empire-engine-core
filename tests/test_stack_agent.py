"""
EMPIRE V49 · STACK ENGINEERING AGENT UNIT TESTS
================================================
Tests the StackAgent class with mocked subprocess, file I/O, and DB calls.

Infrastructure-dependent methods (pm2, system resources, git) are mocked
so tests run independently of the actual server environment.
"""

import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, mock_open

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from empire_stack_agent import StackAgent


# ── Sample PM2 jlist output ────────────────────────────────────────────
_PM2_JSON = json.dumps([
    {
        "name": "empire-hub",
        "pid": 1234,
        "pm2_env": {
            "status": "online",
            "pm_uptime": (datetime.now(timezone.utc).timestamp() - 3600) * 1000,
            "restart_time": 2,
            "exec_mode": "fork",
            "instances": 1,
            "version": "49.0.0",
        },
        "monit": {"cpu": 2.5, "memory": 128 * 1024 * 1024},
    },
    {
        "name": "empire-mesh",
        "pid": 5678,
        "pm2_env": {
            "status": "online",
            "pm_uptime": (datetime.now(timezone.utc).timestamp() - 7200) * 1000,
            "restart_time": 0,
            "exec_mode": "fork",
            "instances": 1,
            "version": "49.0.0",
        },
        "monit": {"cpu": 1.2, "memory": 256 * 1024 * 1024},
    },
])


@pytest.fixture
def agent():
    """StackAgent with no DB (all data from system commands)."""
    return StackAgent(get_db=None)


@pytest.fixture
def agent_with_db():
    """StackAgent with a mocked DB."""
    db = MagicMock()
    db.table.return_value.execute.return_value = MagicMock(data=[])
    return StackAgent(get_db=lambda: db)


# ═════════════════════════════════════════════════════════════════════
# CONSTRUCTION
# ═════════════════════════════════════════════════════════════════════

class TestConstruction:
    def test_no_db(self, agent):
        assert agent.get_db is None

    def test_with_db(self, agent_with_db):
        assert agent_with_db.get_db is not None


# ═════════════════════════════════════════════════════════════════════
# STATUS
# ═════════════════════════════════════════════════════════════════════

class TestStatus:
    @patch("empire_stack_agent._get_system_resources")
    @patch("empire_stack_agent._get_git_info")
    @patch("empire_stack_agent._run_cmd")
    def test_status_shape(self, mock_run_cmd, mock_git, mock_resources, agent):
        """status() returns expected top-level keys."""
        mock_run_cmd.return_value = _PM2_JSON
        mock_resources.return_value = {"cpu_usage_pct": 45.0, "memory_total_mb": 16000}
        mock_git.return_value = {"branch": "main"}
        result = agent.status()
        assert "services" in result
        assert "service_count" in result
        assert "online" in result
        assert "stopped" in result
        assert "resources" in result
        assert "git" in result
        assert "health" in result
        assert "timestamp" in result

    @patch("empire_stack_agent._get_system_resources")
    @patch("empire_stack_agent._get_git_info")
    @patch("empire_stack_agent._run_cmd")
    def test_status_service_count(self, mock_run_cmd, mock_git, mock_resources, agent):
        """status() counts PM2 services correctly."""
        mock_run_cmd.return_value = _PM2_JSON
        mock_resources.return_value = {"cpu_usage_pct": 45.0, "memory_total_mb": 16000}
        mock_git.return_value = {"branch": "main"}
        result = agent.status()
        assert result["service_count"] == 2
        assert result["online"] == 2
        assert result["stopped"] == 0
        assert result["health"] == "healthy"

    @patch("empire_stack_agent._get_system_resources")
    @patch("empire_stack_agent._get_git_info")
    @patch("empire_stack_agent._run_cmd")
    def test_status_with_stopped_services(self, mock_run_cmd, mock_git, mock_resources, agent):
        """status() detects stopped services."""
        pm2_data = json.loads(_PM2_JSON)
        pm2_data[0]["pm2_env"]["status"] = "stopped"
        mock_run_cmd.return_value = json.dumps(pm2_data)
        mock_resources.return_value = {"cpu_usage_pct": 45.0, "memory_total_mb": 16000}
        mock_git.return_value = {"branch": "main"}
        result = agent.status()
        assert result["stopped"] == 1
        assert result["health"] == "degraded"

    @patch("empire_stack_agent._get_system_resources")
    @patch("empire_stack_agent._get_git_info")
    @patch("empire_stack_agent._run_cmd")
    def test_status_handles_pm2_failure(self, mock_run_cmd, mock_git, mock_resources, agent):
        """status() gracefully handles PM2 command failure."""
        mock_run_cmd.return_value = ""
        result = agent.status()
        assert result["service_count"] == 0
        assert result["services"] == []


# ═════════════════════════════════════════════════════════════════════
# SERVICES DETAIL
# ═════════════════════════════════════════════════════════════════════

class TestServicesDetail:
    @patch("empire_stack_agent._run_cmd")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="line1\nline2\n")
    def test_services_detail_shape(self, mock_file, mock_exists, mock_run_cmd, agent):
        """services_detail() returns service list with log tails."""
        mock_run_cmd.return_value = _PM2_JSON
        mock_exists.return_value = True
        result = agent.services_detail()
        assert "services" in result
        assert "count" in result
        assert result["count"] == 2
        for s in result["services"]:
            assert "log_tail" in s

    @patch("empire_stack_agent._run_cmd")
    def test_handles_missing_logs(self, mock_run_cmd, agent):
        """services_detail() handles missing log files gracefully."""
        mock_run_cmd.return_value = _PM2_JSON
        result = agent.services_detail()
        for s in result["services"]:
            assert "log_tail" in s  # empty string if file doesn't exist


# ═════════════════════════════════════════════════════════════════════
# DEPLOYMENT HISTORY
# ═════════════════════════════════════════════════════════════════════

class TestDeploymentHistory:
    @patch("empire_stack_agent._run_cmd")
    def test_deployment_history_shape(self, mock_run_cmd, agent):
        """deployment_history() returns expected keys."""
        mock_run_cmd.return_value = "abc1234|feat: something|2026-06-14"
        result = agent.deployment_history()
        assert "deployments" in result
        assert "count" in result
        assert "current" in result
        if result["deployments"]:
            d = result["deployments"][0]
            assert "commit" in d
        result = agent.deployment_history()
        assert "deployments" in result
        assert "count" in result
        assert "current" in result


# ═════════════════════════════════════════════════════════════════════
# INCIDENTS
# ═════════════════════════════════════════════════════════════════════

class TestIncidents:
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="")
    def test_incidents_shape(self, mock_file, mock_exists, agent):
        """incidents() returns expected keys even without data."""
        mock_exists.return_value = True
        result = agent.incidents()
        assert "incidents" in result
        assert "count" in result
        assert "total_restarts_24h" in result
        assert "services_with_restarts" in result
        assert "timestamp" in result

    @patch("empire_stack_agent._get_pm2_status")
    @patch("os.path.exists")
    def test_incidents_handles_missing_logs(self, mock_exists, mock_pm2, agent):
        """incidents() handles missing log files."""
        mock_exists.return_value = False
        mock_pm2.return_value = []
        result = agent.incidents()
        assert result["count"] == 0
        assert result["total_restarts_24h"] == 0


# ═════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    @patch("empire_stack_agent._get_pm2_status")
    @patch("empire_stack_agent._get_system_resources")
    @patch("http.client.HTTPConnection")
    def test_health_check_shape(self, mock_http, mock_resources, mock_pm2, agent):
        """health_check() returns expected keys."""
        mock_pm2.return_value = []
        mock_resources.return_value = {"disk_usage_pct": "50%"}
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value.status = 200
        mock_http.return_value = mock_conn

        # Need to mock DB usage
        result = agent.health_check()
        assert "checks" in result
        assert "healthy" in result
        assert "timestamp" in result

    @patch("empire_stack_agent._get_system_resources")
    @patch("empire_stack_agent._get_pm2_status")
    def test_handles_no_db(self, mock_pm2, mock_resources, agent):
        """health_check() works without DB."""
        mock_pm2.return_value = []
        mock_resources.return_value = {"cpu_usage_pct": 45.0, "memory_total_mb": 16000, "memory_usage_pct": 50, "disk_usage_pct": "60%"}
        result = agent.health_check()
        assert "checks" in result
        assert "healthy" in result or not result["healthy"]
        # Should have at least pm2 and disk checks
        check_names = [c["service"] for c in result["checks"]]
        assert "pm2" in check_names
        assert "disk" in check_names


# ═════════════════════════════════════════════════════════════════════
# RESOURCE FORECAST
# ═════════════════════════════════════════════════════════════════════

class TestResourceForecast:
    @patch("empire_stack_agent._get_system_resources")
    def test_no_forecasts_when_healthy(self, mock_resources, agent):
        """No forecasts when resources are healthy."""
        mock_resources.return_value = {
            "memory_usage_pct": 50,
            "disk_usage_pct": "60%",
        }
        result = agent.resource_forecast()
        assert result["count"] == 0

    @patch("empire_stack_agent._get_system_resources")
    def test_forecasts_when_high_usage(self, mock_resources, agent):
        """Forecasts generated when resources are high."""
        mock_resources.return_value = {
            "memory_usage_pct": 85,
            "disk_usage_pct": "90%",
        }
        result = agent.resource_forecast()
        assert result["count"] >= 2
        risks = [f["risk"] for f in result["forecasts"]]
        assert "high" in risks or "medium" in risks

    @patch("empire_stack_agent._get_system_resources")
    def test_forecast_shape(self, mock_resources, agent):
        """Each forecast has expected keys."""
        mock_resources.return_value = {
            "memory_usage_pct": 92,
            "disk_usage_pct": "88%",
        }
        result = agent.resource_forecast()
        for f in result["forecasts"]:
            assert "resource" in f
            assert "current_pct" in f
            assert "risk" in f
            assert "recommendation" in f


# ═════════════════════════════════════════════════════════════════════
# STACK REPORT
# ═════════════════════════════════════════════════════════════════════

class TestStackReport:
    @patch("empire_stack_agent._get_system_resources")
    @patch("empire_stack_agent._get_git_info")
    @patch("empire_stack_agent._run_cmd")
    def test_report_shape(self, mock_run_cmd, mock_git, mock_resources, agent):
        """stack_report() consolidates all sections."""
        mock_run_cmd.return_value = "abc1234|feat: something|2026-06-14"
        mock_resources.return_value = {"cpu_usage_pct": 45.0, "memory_total_mb": 16000, "memory_usage_pct": 50, "disk_usage_pct": "60%"}
        mock_git.return_value = {"branch": "main"}
        result = agent.stack_report()
        assert "status" in result
        assert "health" in result
        assert "incidents" in result
        assert "forecast" in result
        assert "overall" in result
        assert "timestamp" in result
        assert "services_online" in result["overall"]
        assert "active_incidents" in result["overall"]

    @patch("empire_stack_agent._get_system_resources")
    @patch("empire_stack_agent._get_git_info")
    @patch("empire_stack_agent._run_cmd")
    def test_overall_summary(self, mock_run_cmd, mock_git, mock_resources, agent):
        """Overall summary has expected shape."""
        mock_run_cmd.return_value = "abc1234|feat: something|2026-06-14"
        mock_resources.return_value = {"cpu_usage_pct": 45.0, "memory_total_mb": 16000, "memory_usage_pct": 50, "disk_usage_pct": "60%"}
        result = agent.stack_report()
        o = result["overall"]
        for key in ("status", "services_online", "health_check_passing",
                     "active_incidents", "resource_alerts"):
            assert key in o, f"Missing key: {key}"


# ═════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    @patch("empire_stack_agent._run_cmd")
    def test_all_methods_return_without_crashing(self, mock_run_cmd, agent):
        """All public methods return without exceptions."""
        mock_run_cmd.return_value = ""
        methods = [
            agent.status,
            agent.services_detail,
            agent.deployment_history,
            agent.incidents,
            agent.health_check,
            agent.resource_forecast,
            agent.stack_report,
        ]
        for m in methods:
            result = m()
            assert result is not None, f"{m.__name__} returned None"

    def test_constructor_stores_db(self):
        """get_db is stored correctly."""
        db = MagicMock()
        agent = StackAgent(get_db=lambda: db)
        assert agent.get_db() is db
