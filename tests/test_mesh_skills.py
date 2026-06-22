"""
Tests: Mesh Skill Dispatch — email.execute and design.execute
===============================================================
Verifies that AgentMesh.execute_skill() correctly routes to the
HarnessManager and that the convenience wrappers (execute_email_skill,
execute_design_skill) validate namespace and dispatch properly.

These tests mock the HarnessManager to avoid requiring actual skill
registration or LLM inference.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional, Dict, Callable

# ── Test helper ──────────────────────────────────────────────────────


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


# ── Fake HarnessManager ──────────────────────────────────────────────


class FakeHarnessOutput:
    """Simulates SkillOutput from harness_mgr.run()."""
    def __init__(self, success=True, data=None, error=None):
        self.success = success
        self.data = data or {"skill": "test.skill", "execution_mode": "analysis_only"}
        self.error = error


class FakeHarnessManager:
    """Mock HarnessManager that records calls and returns controlled results."""
    def __init__(self):
        self.calls = []  # (skill_name, params) tuples
        self.fail_on = set()  # skill names that should fail
        self.return_data = None  # custom return data override

    async def run(self, skill_name: str, params: dict) -> FakeHarnessOutput:
        self.calls.append((skill_name, params))
        if skill_name in self.fail_on:
            return FakeHarnessOutput(success=False, error=f"Simulated failure for {skill_name}")
        if self.return_data:
            return FakeHarnessOutput(success=True, data=self.return_data)
        return FakeHarnessOutput(success=True, data={
            "skill": skill_name,
            "execution_mode": "analysis_only",
            "input_params": params,
        })


# ── Fixture: build an AgentMesh with fake harness ────────────────────

@pytest.fixture
def mesh_with_harness():
    """Create an AgentMesh with a mock HarnessManager and a fake DB callable."""
    from agent_mesh import AgentMesh

    def fake_db():
        return MagicMock()

    harness = FakeHarnessManager()
    mesh = AgentMesh(get_db=fake_db, router=MagicMock(), harness_mgr=harness)
    return mesh, harness


@pytest.fixture
def mesh_without_harness():
    """Create an AgentMesh without a HarnessManager (simulates uninitialized)."""
    from agent_mesh import AgentMesh

    def fake_db():
        return MagicMock()

    mesh = AgentMesh(get_db=fake_db, router=MagicMock(), harness_mgr=None)
    return mesh


# ══════════════════════════════════════════════════════════════════════
# EXECUTE SKILL — BASE DISPATCH
# ══════════════════════════════════════════════════════════════════════


class TestExecuteSkill:
    def test_dispatches_to_harness_with_params(self, mesh_with_harness):
        """execute_skill should call harness_mgr.run() with skill_name and params."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_skill("email.strategy", {"goal": "test"}))

        assert len(harness.calls) == 1
        call_skill, call_params = harness.calls[0]
        assert call_skill == "email.strategy"
        assert call_params["goal"] == "test"
        assert result["ok"] is True
        assert result["skill"] == "email.strategy"

    def test_dispatches_without_params(self, mesh_with_harness):
        """execute_skill should work with no params (default to empty dict)."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_skill("email.sequence"))

        assert len(harness.calls) == 1
        assert result["ok"] is True

    def test_returns_error_on_harness_failure(self, mesh_with_harness):
        """execute_skill should propagate harness failures."""
        mesh, harness = mesh_with_harness
        harness.fail_on.add("email.broken")
        result = _run(mesh.execute_skill("email.broken", {}))

        assert result["ok"] is False
        assert "Simulated failure" in result.get("error", "")

    def test_returns_error_on_missing_harness(self, mesh_without_harness):
        """execute_skill should return error when no HarnessManager is wired."""
        result = _run(mesh_without_harness.execute_skill("email.strategy", {}))

        assert result["ok"] is False
        assert "HarnessManager not wired" in result.get("error", "")

    def test_handles_keyerror_as_not_found(self, mesh_with_harness):
        """execute_skill should return error for unregistered skills."""
        mesh, harness = mesh_with_harness

        async def failing_run(skill_name, params):
            raise KeyError(f"Skill '{skill_name}' not registered")

        harness.run = failing_run
        result = _run(mesh.execute_skill("nonexistent.skill", {}))

        assert result["ok"] is False
        assert "not registered" in result.get("error", "")

    def test_result_contains_skill_name(self, mesh_with_harness):
        """Result dict should always include the skill name."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_skill("design.visual-color", {"goal": "test"}))
        assert result["skill"] == "design.visual-color"


# ══════════════════════════════════════════════════════════════════════
# EMAIL SKILL DISPATCH
# ══════════════════════════════════════════════════════════════════════


class TestExecuteEmailSkill:
    def test_valid_email_skill_passes_through(self, mesh_with_harness):
        """execute_email_skill should route email.* skills to execute_skill."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_email_skill("email.strategy", {"goal": "test"}))

        assert result["ok"] is True
        assert len(harness.calls) == 1
        assert harness.calls[0][0] == "email.strategy"

    def test_rejects_non_email_skill(self, mesh_with_harness):
        """execute_email_skill should reject skills not in email.* namespace."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_email_skill("design.visual-color", {}))

        assert result["ok"] is False
        assert "Not an email skill" in result.get("error", "")
        assert len(harness.calls) == 0  # Should not attempt execution

    def test_all_email_skill_namespaces_accepted(self, mesh_with_harness):
        """Common email skill prefixes should all route correctly."""
        mesh, harness = mesh_with_harness
        email_skills = [
            "email.strategy",
            "email.sequence",
            "email.deliverability",
            "email.compliance-can-spam",
            "email.copy-subject",
            "email.analytics",
            "email.provider-resend",
        ]
        for skill in email_skills:
            result = _run(mesh.execute_email_skill(skill, {}))
            assert result["ok"] is True, f"Failed for {skill}"

        assert len(harness.calls) == len(email_skills)

    def test_email_skill_rejects_marketing(self, mesh_with_harness):
        """marketing.* skills should be rejected by email dispatch."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_email_skill("marketing.emails", {}))
        assert result["ok"] is False
        assert "Not an email skill" in result.get("error", "")


# ══════════════════════════════════════════════════════════════════════
# DESIGN SKILL DISPATCH
# ══════════════════════════════════════════════════════════════════════


class TestExecuteDesignSkill:
    def test_valid_design_skill_passes_through(self, mesh_with_harness):
        """execute_design_skill should route design.* skills to execute_skill."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_design_skill("design.visual-color", {"goal": "palette"}))

        assert result["ok"] is True
        assert len(harness.calls) == 1
        assert harness.calls[0][0] == "design.visual-color"

    def test_rejects_non_design_skill(self, mesh_with_harness):
        """execute_design_skill should reject skills not in design.* namespace."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_design_skill("email.strategy", {}))

        assert result["ok"] is False
        assert "Not a design skill" in result.get("error", "")
        assert len(harness.calls) == 0

    def test_all_design_skill_namespaces_accepted(self, mesh_with_harness):
        """Common design skill prefixes should all route correctly."""
        mesh, harness = mesh_with_harness
        design_skills = [
            "design.ui-component",
            "design.ui-layout",
            "design.ux-flow",
            "design.visual-brand",
            "design.system-tokens",
            "design.motion-transitions",
            "design.a11y-audit",
            "design.ops-critique",
            "design.web-builder",
        ]
        for skill in design_skills:
            result = _run(mesh.execute_design_skill(skill, {}))
            assert result["ok"] is True, f"Failed for {skill}"

        assert len(harness.calls) == len(design_skills)

    def test_design_skill_rejects_marketing(self, mesh_with_harness):
        """marketing.* skills should be rejected by design dispatch."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_design_skill("marketing.emails", {}))
        assert result["ok"] is False
        assert "Not a design skill" in result.get("error", "")


# ══════════════════════════════════════════════════════════════════════
# MARKETING SKILL DISPATCH
# ══════════════════════════════════════════════════════════════════════


class TestExecuteMarketingSkill:
    def test_valid_marketing_skill_passes_through(self, mesh_with_harness):
        """execute_marketing_skill should route marketing.* skills to execute_skill."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_marketing_skill("marketing.emails", {"goal": "campaign"}))

        assert result["ok"] is True
        assert len(harness.calls) == 1
        assert harness.calls[0][0] == "marketing.emails"

    def test_rejects_non_marketing_skill(self, mesh_with_harness):
        """execute_marketing_skill should reject skills not in marketing.* namespace."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_marketing_skill("email.strategy", {}))
        assert result["ok"] is False
        assert "Not a marketing skill" in result.get("error", "")
        assert len(harness.calls) == 0

    def test_all_marketing_skill_namespaces_accepted(self, mesh_with_harness):
        """Common marketing skill prefixes should all route correctly."""
        mesh, harness = mesh_with_harness
        marketing_skills = [
            "marketing.product",
            "marketing.emails",
            "marketing.ads",
            "marketing.copywriting",
            "marketing.seo-audit",
            "marketing.cro",
            "marketing.sms",
            "marketing.social",
            "marketing.referrals",
        ]
        for skill in marketing_skills:
            result = _run(mesh.execute_marketing_skill(skill, {}))
            assert result["ok"] is True, f"Failed for {skill}"

        assert len(harness.calls) == len(marketing_skills)


# ══════════════════════════════════════════════════════════════════════
# MARKETING NEW TASK TYPES — from the updated routing table
# ══════════════════════════════════════════════════════════════════════


class TestMarketingNewTaskTypes:
    """Verify that specific marketing task types from the updated routing table
    (SKILLS.md section 6) dispatch correctly through execute_marketing_skill()."""

    def test_marketing_seo_content_dispatches(self, mesh_with_harness):
        """marketing.seo.content should route through execute_marketing_skill."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_marketing_skill(
            "marketing.seo.content",
            {"topic": "storm damage roof repair", "audience": "homeowners"}
        ))
        assert result["ok"] is True
        assert len(harness.calls) == 1
        assert harness.calls[0][0] == "marketing.seo.content"
        assert harness.calls[0][1]["topic"] == "storm damage roof repair"

    def test_marketing_cold_outreach_dispatches(self, mesh_with_harness):
        """marketing.cold.outreach should route through execute_marketing_skill."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_marketing_skill(
            "marketing.cold.outreach",
            {"industry": "roofing", "volume": 500}
        ))
        assert result["ok"] is True
        assert len(harness.calls) == 1
        assert harness.calls[0][0] == "marketing.cold.outreach"

    def test_marketing_conversion_dispatches(self, mesh_with_harness):
        """marketing.conversion should route through execute_marketing_skill."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_marketing_skill(
            "marketing.conversion",
            {"page": "landing", "metric": "ctr"}
        ))
        assert result["ok"] is True
        assert harness.calls[0][0] == "marketing.conversion"

    def test_marketing_sms_campaign_dispatches(self, mesh_with_harness):
        """marketing.sms.campaign should route through execute_marketing_skill."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_marketing_skill(
            "marketing.sms.campaign",
            {"message": "Limited time offer", "compliance": "tcpa"}
        ))
        assert result["ok"] is True
        assert harness.calls[0][0] == "marketing.sms.campaign"
        assert harness.calls[0][1]["compliance"] == "tcpa"


# ══════════════════════════════════════════════════════════════════════
# SOCIAL SKILL DISPATCH
# ══════════════════════════════════════════════════════════════════════


class TestExecuteSocialSkill:
    def test_valid_social_skill_passes_through(self, mesh_with_harness):
        """execute_social_skill should route social.* skills to execute_skill."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_social_skill("social.deepgram", {"goal": "transcribe"}))

        assert result["ok"] is True
        assert len(harness.calls) == 1
        assert harness.calls[0][0] == "social.deepgram"

    def test_rejects_non_social_skill(self, mesh_with_harness):
        """execute_social_skill should reject skills not in social.* namespace."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_social_skill("marketing.emails", {}))

        assert result["ok"] is False
        assert "Not a social skill" in result.get("error", "")
        assert len(harness.calls) == 0

    def test_all_social_skill_namespaces_accepted(self, mesh_with_harness):
        """Common social skill prefixes should all route correctly."""
        mesh, harness = mesh_with_harness
        social_skills = [
            "social.deepgram",
            "social.content",
            "social.scheduling",
            "social.analytics",
            "social.engagement",
            "social.listening",
            "social.advertising",
        ]
        for skill in social_skills:
            result = _run(mesh.execute_social_skill(skill, {}))
            assert result["ok"] is True, f"Failed for {skill}"

        assert len(harness.calls) == len(social_skills)

    def test_social_skill_rejects_email(self, mesh_with_harness):
        """email.* skills should be rejected by social dispatch."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_social_skill("email.strategy", {}))
        assert result["ok"] is False
        assert "Not a social skill" in result.get("error", "")


# ══════════════════════════════════════════════════════════════════════
# EDGE CASES
# ══════════════════════════════════════════════════════════════════════


class TestSkillDispatchEdgeCases:
    def test_dot_in_skill_name(self, mesh_with_harness):
        """Skill names with multiple dots should resolve correctly."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_skill("design.visual.data-viz", {"goal": "chart"}))
        assert result["ok"] is True
        assert harness.calls[0][0] == "design.visual.data-viz"

    def test_hyphen_in_skill_name(self, mesh_with_harness):
        """Skill names with hyphens should pass through cleanly."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_skill("email.compliance-can-spam", {}))
        assert result["ok"] is True
        assert harness.calls[0][0] == "email.compliance-can-spam"

    def test_empty_skill_name(self, mesh_with_harness):
        """Empty skill name should be passed to harness (which will fail on lookup)."""
        mesh, harness = mesh_with_harness
        harness.fail_on.add("")
        result = _run(mesh.execute_skill("", {}))
        assert result["ok"] is False

    def test_none_params(self, mesh_with_harness):
        """None params should be converted to empty dict."""
        mesh, harness = mesh_with_harness
        result = _run(mesh.execute_skill("email.strategy", None))
        assert result["ok"] is True

    def test_large_params_dict(self, mesh_with_harness):
        """Large params dict should pass through uncorrupted."""
        mesh, harness = mesh_with_harness
        params = {f"key_{i}": f"value_{i}" for i in range(100)}
        result = _run(mesh.execute_skill("design.visual-color", params))
        assert result["ok"] is True
        received_params = harness.calls[0][1]
        assert len(received_params) == 100
        assert received_params["key_50"] == "value_50"
