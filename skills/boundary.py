"""
EMPIRE V49 · SKILL BOUNDARY & FIDELITY
========================================
Enforces that agents only call skills they are equipped with.
Provides audit trail and fidelity scoring.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from .base import BaseSkill, SkillInput, SkillOutput
from .harness import SkillHarness, HarnessConfig
from .registry import SkillRegistry, SkillFidelityError


log = logging.getLogger("empire.skills.boundary")


# ─────────────────────────────────────────────────────────────────────────────
# SKILL BOUNDARY
# ─────────────────────────────────────────────────────────────────────────────


class SkillBoundary:
    """
    Wraps an agent with enforcement boundaries.

    What it blocks:
      - Modifying the agent's equips list after initialization
      - Adding capabilities at runtime
      - Calling unregistered skills

    What it allows:
      - Calling registered skills through the harness
      - Normal operations within skill context
    """

    def __init__(self, agent_name: str, equips: list[str], registry: SkillRegistry):
        self._agent_name = agent_name
        self._equips = frozenset(equips)
        self._registry = registry
        self._violations: list[dict] = []
        self._call_count = 0

    def verify_call(self, skill_name: str) -> bool:
        """Verify the agent is authorized to call a skill."""
        self._call_count += 1
        if skill_name not in self._equips:
            self._log_violation(f"Called unregistered skill '{skill_name}'")
            return False
        if not self._registry.has_skill(skill_name):
            self._log_violation(f"Skill '{skill_name}' is not registered")
            return False
        return True

    def _log_violation(self, msg: str) -> None:
        self._violations.append({"ts": time.time(), "msg": msg})
        log.warning(f"[boundary.{self._agent_name}] FIDELITY: {msg}")

    @property
    def fidelity_score(self) -> float:
        """0.0-1.0: percentage of calls with zero violations."""
        if self._call_count == 0:
            return 1.0
        recent = [v for v in self._violations if time.time() - v["ts"] < 3600]
        return max(0.0, 1.0 - (len(recent) / max(self._call_count, 1)))

    @property
    def agent_name(self) -> str:
        return self._agent_name

    @property
    def equips(self) -> frozenset:
        return self._equips

    def snapshot(self) -> dict:
        return {
            "agent": self._agent_name,
            "equips": sorted(self._equips),
            "call_count": self._call_count,
            "violations_last_hour": len(
                [v for v in self._violations if time.time() - v["ts"] < 3600]
            ),
            "fidelity_score": self.fidelity_score,
        }


# ─────────────────────────────────────────────────────────────────────────────
# FIDELITY-AWARE HARNESS
# ─────────────────────────────────────────────────────────────────────────────


class FidelityAwareHarness(SkillHarness):
    """
    Extends SkillHarness with agent authorization checks.

    Before executing any skill, verifies:
      1. The calling agent is equipped with this skill
      2. The skill hasn't been tampered with (if using ImmutableSkillRegistry)
    """

    def __init__(
        self,
        skill: BaseSkill,
        boundaries: dict[str, SkillBoundary],
        config: Optional[HarnessConfig] = None,
        registry: Optional[SkillRegistry] = None,
    ):
        super().__init__(skill, config, registry)
        self._boundaries = boundaries

    async def run(
        self,
        input: SkillInput,
        caller_agent_name: Optional[str] = None,
    ) -> SkillOutput:
        """Run with fidelity enforcement."""
        if caller_agent_name:
            boundary = self._boundaries.get(caller_agent_name)
            if boundary:
                if not boundary.verify_call(self._skill.name):
                    return SkillOutput(
                        success=False,
                        error=(
                            f"Agent '{caller_agent_name}' is not equipped "
                            f"with skill '{self._skill.name}'"
                        ),
                    )
                self._verify_skill_integrity()

        return await super().run(input)

    def _verify_skill_integrity(self) -> None:
        """Detect if the skill has been monkey-patched since registration."""
        for method_name in ["execute", "validate", "report"]:
            method = getattr(self._skill, method_name, None)
            if method and hasattr(method, "__func__"):
                stored = self._skill.__dict__.get(f"_locked_{method_name}")
                if stored and method.__func__ is not stored:
                    raise SkillFidelityError(
                        f"Skill '{self._skill.name}' method '{method_name}' "
                        f"has been replaced!"
                    )


# ─────────────────────────────────────────────────────────────────────────────
# FIDELITY AUDITOR
# ─────────────────────────────────────────────────────────────────────────────


class FidelityAuditor:
    """
    Central audit log for all skill fidelity events.
    """

    def __init__(self):
        self._events: list[dict] = []

    def log_call(self, agent_name: str, skill_name: str, allowed: bool) -> None:
        """Log a skill execution attempt (allowed or blocked)."""
        self._events.append({
            "type": "skill.call" if allowed else "skill.blocked",
            "agent": agent_name,
            "skill": skill_name,
            "ts": time.time(),
            "allowed": allowed,
        })
        # Keep last 10k events
        self._events = self._events[-10000:]

    def log_tamper(self, skill_name: str, method_name: str) -> None:
        """Log a skill tampering attempt (critical)."""
        self._events.append({
            "type": "skill.tampered",
            "skill": skill_name,
            "method": method_name,
            "ts": time.time(),
            "allowed": False,
        })

    def report(self) -> dict:
        """Generate fidelity report."""
        by_agent: dict[str, dict] = {}
        for e in self._events:
            agent = e.get("agent", "unknown")
            if agent not in by_agent:
                by_agent[agent] = {"calls": 0, "blocked": 0}
            by_agent[agent]["calls"] += 1
            if not e.get("allowed", True):
                by_agent[agent]["blocked"] += 1

        return {
            "total_events": len(self._events),
            "by_agent": by_agent,
            "fidelity_scores": {
                agent: max(0.0, 1.0 - (stats["blocked"] / max(stats["calls"], 1)))
                for agent, stats in by_agent.items()
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# ALERT SUPPRESSOR (storms prevention)
# ─────────────────────────────────────────────────────────────────────────────


class AlertSuppressor:
    """
    Prevents alert storms through root cause dedup and rate limiting.
    """

    ROOT_CAUSE_MAP: dict[str, list[str]] = {
        "infra.critical": [
            "skill.circuit_opened",
            "skill.failed",
        ],
        "degradation.level_up": [
            "skill.circuit_opened",
            "skill.failed",
        ],
    }

    def __init__(self):
        self._suppressed: dict[str, float] = {}
        self._alert_count = 0
        self._hour_bucket = time.time()

    def check_suppression(self, event_type: str) -> bool:
        """Check if an event is currently suppressed."""
        now = time.time()
        if now - self._hour_bucket > 3600:
            self._alert_count = 0
            self._hour_bucket = now
        if self._alert_count >= 20:
            return True
        suppressed_until = self._suppressed.get(event_type, 0)
        return now < suppressed_until

    def register_alert(self, event_type: str) -> None:
        """Register an ALERT-tier event that was sent."""
        self._alert_count += 1
        if event_type in self.ROOT_CAUSE_MAP:
            until = time.time() + 600
            for downstream in self.ROOT_CAUSE_MAP[event_type]:
                self._suppressed[downstream] = until

    def snapshot(self) -> dict:
        return {
            "suppressed_rules": len(self._suppressed),
            "alerts_this_hour": self._alert_count,
        }
