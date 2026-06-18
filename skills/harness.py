"""
EMPIRE V49 · SKILL HARNESS
===========================
Wraps every skill in a controlled execution environment.
Handles resource limits, injection, retries, circuit breaker, and observability.
"""

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .base import BaseSkill, SkillInput, SkillOutput, SkillMetrics, SkillContext
from .registry import SkillRegistry


log = logging.getLogger("empire.skills.harness")


# ─────────────────────────────────────────────────────────────────────────────
# HARNESS CONFIG
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HarnessConfig:
    """Configuration for a skill execution harness."""

    # Resource limits
    timeout: float = 30.0
    max_retries: int = 3
    retry_backoff: float = 1.0
    max_concurrent: int = 1

    # Injection
    inject_skills: bool = True
    inject_db: bool = False
    inject_llm: bool = False

    # Observability
    emit_metrics: bool = True

    # Error handling
    raise_on_failure: bool = False
    fallback_skill: Optional[str] = None
    circuit_breaker: bool = False
    circuit_threshold: int = 5
    circuit_reset_seconds: float = 60.0

    # Testing
    mock_deps: Optional[dict[str, BaseSkill]] = None


# ─────────────────────────────────────────────────────────────────────────────
# SKILL HARNESS
# ─────────────────────────────────────────────────────────────────────────────


class SkillHarness:
    """
    Wraps a BaseSkill with a controlled execution environment.

    The harness handles:
      - Resource enforcement (timeout, concurrency, retries)
      - Dependency injection (skills, DB, LLM)
      - Observability (metrics, logging)
      - Error containment (circuit breaker, fallback)
    """

    def __init__(
        self,
        skill: BaseSkill,
        config: Optional[HarnessConfig] = None,
        registry: Optional[SkillRegistry] = None,
    ):
        self._skill = skill
        self._config = config or HarnessConfig()
        self._registry = registry
        self._circuit_state: dict[str, Any] = {"failures": 0, "open_until": 0.0}
        self._concurrency_sem = asyncio.Semaphore(self._config.max_concurrent)
        self._total_executions = 0
        self._total_failures = 0

    # ── Public API ────────────────────────────────────────────────────

    async def run(self, input: SkillInput) -> SkillOutput:
        """Execute the skill through the harness."""
        if self._config.circuit_breaker and self._circuit_open():
            return SkillOutput(success=False, error="circuit_breaker_open")

        async with self._concurrency_sem:
            return await self._execute_with_guardrails(input)

    @property
    def skill(self) -> BaseSkill:
        return self._skill

    @property
    def config(self) -> HarnessConfig:
        return self._config

    # ── Internal Execution ─────────────────────────────────────────────

    async def _execute_with_guardrails(self, input: SkillInput) -> SkillOutput:
        """Execute with injection, retry backoff, timeout."""
        context = await self._build_context(input)
        injected_input = SkillInput(
            params=input.params,
            context=context,
            trace_parent=input.trace_parent,
        )

        last_error = None
        for attempt in range(self._config.max_retries):
            try:
                start = time.time()
                output = await asyncio.wait_for(
                    self._skill.execute(injected_input),
                    timeout=self._config.timeout,
                )
                elapsed = int((time.time() - start) * 1000)

                if not output.metrics:
                    output.metrics = SkillMetrics(duration_ms=elapsed)

                if self._config.emit_metrics:
                    self._total_executions += 1
                    self._circuit_state["failures"] = 0

                await self._skill.report(output)
                return output

            except asyncio.TimeoutError:
                last_error = f"timeout after {self._config.timeout}s"
                log.warning(f"[harness.{self._skill.name}] attempt {attempt+1}: timeout")

            except Exception as e:
                last_error = str(e)
                log.warning(f"[harness.{self._skill.name}] attempt {attempt+1}: {e}")

            if attempt < self._config.max_retries - 1:
                await asyncio.sleep(self._config.retry_backoff * (2 ** attempt))

        # All retries exhausted
        self._total_failures += 1
        error_out = SkillOutput(success=False, error=last_error)

        if self._config.circuit_breaker:
            self._circuit_state["failures"] += 1
            if self._circuit_state["failures"] >= self._config.circuit_threshold:
                self._circuit_state["open_until"] = time.time() + self._config.circuit_reset_seconds
                log.warning(f"[harness.{self._skill.name}] circuit OPEN after "
                           f"{self._circuit_state['failures']} failures")

        # Fallback skill
        if self._config.fallback_skill and self._registry:
            fallback = self._registry.get(self._config.fallback_skill)
            if fallback:
                log.info(f"[harness.{self._skill.name}] using fallback: {fallback.name}")
                fallback_harness = SkillHarness(fallback, config=self._config)
                return await fallback_harness.run(input)

        if self._config.raise_on_failure:
            raise RuntimeError(last_error)

        return error_out

    async def _build_context(self, input: SkillInput) -> SkillContext:
        """Build the injection context for this execution."""
        context = SkillContext()

        if self._config.inject_skills and self._registry:
            for dep_name in self._skill.dependencies:
                dep_skill = self._registry.get(dep_name)
                if dep_skill:
                    context.inject_skill(dep_name, dep_skill)

        if self._config.mock_deps:
            for name, mock in self._config.mock_deps.items():
                context.inject_skill(name, mock)

        return context

    def _circuit_open(self) -> bool:
        state = self._circuit_state
        now = time.time()
        if state["open_until"] > now:
            return True
        if state["open_until"] > 0 and state["open_until"] <= now:
            state["failures"] = 0
            state["open_until"] = 0.0
        return False

    def reset_circuit(self) -> None:
        """Manually reset the circuit breaker."""
        self._circuit_state = {"failures": 0, "open_until": 0.0}
        log.info(f"[harness.{self._skill.name}] circuit manually reset")

    def snapshot(self) -> dict:
        """Harness state snapshot for dashboard."""
        return {
            "skill": self._skill.name,
            "version": self._skill.version,
            "config": {
                "timeout": self._config.timeout,
                "max_retries": self._config.max_retries,
                "max_concurrent": self._config.max_concurrent,
                "circuit_breaker": self._config.circuit_breaker,
            },
            "circuit": {
                "open": self._circuit_open(),
                "failures": self._circuit_state["failures"],
            },
            "executions": self._total_executions,
            "failures": self._total_failures,
        }


# ─────────────────────────────────────────────────────────────────────────────
# HARNESS MANAGER
# ─────────────────────────────────────────────────────────────────────────────


class HarnessManager:
    """
    Manages all skill harnesses in the fleet.

    Responsibilities:
      - Create/configure harnesses for all registered skills
      - Global concurrency limits (across all skills)
      - Health monitoring (error rates, circuit breaker states)
      - Dynamic reconfiguration (update timeouts, retries at runtime)
    """

    def __init__(
        self,
        registry: SkillRegistry,
        default_config: Optional[HarnessConfig] = None,
    ):
        self._registry = registry
        self._harnesses: dict[str, SkillHarness] = {}
        self._default_config = default_config or HarnessConfig()
        self._overrides: dict[str, HarnessConfig] = {}
        self._global_sem = asyncio.Semaphore(50)

    def configure_skill(self, skill_name: str, config: HarnessConfig) -> None:
        """Override harness config for a specific skill."""
        self._overrides[skill_name] = config
        if skill_name in self._harnesses:
            skill = self._registry.get(skill_name)
            if skill:
                self._harnesses[skill_name] = SkillHarness(
                    skill, config, registry=self._registry
                )

    async def run(
        self,
        skill_name: str,
        params: dict,
        *,
        trace_parent: Optional[str] = None,
    ) -> SkillOutput:
        """Run a skill through its harness."""
        harness = self._get_or_create_harness(skill_name)
        async with self._global_sem:
            return await harness.run(SkillInput(
                params=params,
                trace_parent=trace_parent,
            ))

    def get_harness(self, skill_name: str) -> Optional[SkillHarness]:
        return self._harnesses.get(skill_name)

    def reset_circuit(self, skill_name: str) -> bool:
        """Manually reset a skill's circuit breaker."""
        harness = self.get_harness(skill_name)
        if harness:
            harness.reset_circuit()
            return True
        return False

    def _get_or_create_harness(self, skill_name: str) -> SkillHarness:
        if skill_name not in self._harnesses:
            skill = self._registry.get(skill_name)
            if not skill:
                raise KeyError(f"Skill '{skill_name}' not registered")
            config = self._overrides.get(skill_name, self._default_config)
            self._harnesses[skill_name] = SkillHarness(
                skill, config, registry=self._registry
            )
        return self._harnesses[skill_name]

    def health_check(self) -> dict:
        """Health status of all active harnesses."""
        status = {}
        for name, harness in self._harnesses.items():
            snap = harness.snapshot()
            status[name] = {
                "healthy": not snap["circuit"]["open"],
                "circuit_open": snap["circuit"]["open"],
                "circuit_failures": snap["circuit"]["failures"],
                "executions": snap["executions"],
                "failures": snap["failures"],
            }
        return {
            "total_harnesses": len(self._harnesses),
            "circuits_open": sum(1 for s in status.values() if s["circuit_open"]),
            "healthy": sum(1 for s in status.values() if s["healthy"]),
            "harnesses": status,
        }

    def snapshot(self) -> dict:
        """Full HarnessManager snapshot."""
        return {
            "total_harnesses": len(self._harnesses),
            "default_config": {
                "timeout": self._default_config.timeout,
                "max_retries": self._default_config.max_retries,
                "circuit_breaker": self._default_config.circuit_breaker,
            },
            "overrides": {
                name: {
                    "timeout": cfg.timeout,
                    "max_retries": cfg.max_retries,
                    "circuit_breaker": cfg.circuit_breaker,
                }
                for name, cfg in self._overrides.items()
            },
            "harnesses": {
                name: h.snapshot() for name, h in self._harnesses.items()
            },
        }
