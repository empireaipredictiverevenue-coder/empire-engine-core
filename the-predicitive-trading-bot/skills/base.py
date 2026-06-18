"""
PREDICITIVE TRADING BOT · SKILLS BASE
======================================
Abstract base class and data contracts for every skill in the system.
"""

import abc
import time
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional


log = logging.getLogger("trading.skills.base")


# ─────────────────────────────────────────────────────────────────────────────
# DATA CONTRACTS
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SkillInput:
    """Typed input contract for every skill execution."""
    params: dict
    context: Optional["SkillContext"] = None
    trace_parent: Optional[str] = None


@dataclass
class SkillOutput:
    """Typed output contract for every skill execution."""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    metrics: Optional["SkillMetrics"] = None
    artifacts: Optional[list[dict]] = None


@dataclass
class SkillMetrics:
    """Standard metrics every skill reports."""
    duration_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    api_calls: int = 0
    records_processed: int = 0
    records_errored: int = 0


class SkillContext:
    """
    Dependency injection container for skill execution.
    Skills receive a context with all their dependencies pre-injected.
    """

    def __init__(self):
        self._skills: dict[str, "BaseSkill"] = {}
        self._infra: dict[str, Any] = {}

    def inject_skill(self, name: str, skill: "BaseSkill") -> None:
        self._skills[name] = skill

    def get_skill(self, name: str) -> Optional["BaseSkill"]:
        return self._skills.get(name)

    def inject(self, key: str, value: Any) -> None:
        self._infra[key] = value

    def get(self, key: str) -> Any:
        return self._infra.get(key)

    @property
    def skills(self) -> dict[str, "BaseSkill"]:
        return dict(self._skills)

    @property
    def infra(self) -> dict[str, Any]:
        return dict(self._infra)


# ─────────────────────────────────────────────────────────────────────────────
# ABSTRACT BASE SKILL
# ─────────────────────────────────────────────────────────────────────────────


class BaseSkill(abc.ABC):
    """
    Abstract base for every skill in the system.

    Subclasses override:
      - name, version, description, tags (class-level metadata)
      - validate() — check inputs before execution
      - execute() — the core logic
      - report() — post-execution reporting (optional)

    Built-in: run() orchestrates validate → execute → report with
    retry backoff, timeout, and Langfuse tracing.
    """

    # ── Metadata (override in subclass) ────────────────────────────────
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0

    def __init_subclass__(cls, **kwargs):
        """Ensure every skill has a name."""
        super().__init_subclass__(**kwargs)
        if not cls.name:
            raise ValueError(f"{cls.__name__} must define a 'name' class attribute")

    # ── Lifecycle ──────────────────────────────────────────────────────

    @abc.abstractmethod
    async def validate(self, input: SkillInput) -> bool:
        """Validate inputs before execution.
        Return False if the skill cannot execute (missing params, bad state).
        """
        ...

    @abc.abstractmethod
    async def execute(self, input: SkillInput) -> SkillOutput:
        """Execute the skill's core logic.
        Must be idempotent where possible (retry-safe).
        """
        ...

    async def report(self, output: SkillOutput) -> None:
        """Post-execution reporting. Override for custom logging/metrics.
        Default: logs to the skill's logger.
        """
        if not output.success:
            log.warning(f"[skill.{self.name}] failed: {output.error}")
        else:
            metrics = output.metrics
            if metrics:
                log.info(
                    f"[skill.{self.name}] done in {metrics.duration_ms:.0f}ms "
                    f"· {metrics.api_calls} api calls"
                )

    # ── Built-in run method ────────────────────────────────────────────

    async def run(self, input: SkillInput) -> SkillOutput:
        """Standard run method: validate → execute → report.
        Handles retry, timeout, and error wrapping.
        """
        if not await self.validate(input):
            return SkillOutput(success=False, error="validation_failed")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                start = time.time()
                result = await asyncio.wait_for(
                    self.execute(input),
                    timeout=self.timeout_seconds,
                )
                if not result.metrics:
                    elapsed = int((time.time() - start) * 1000)
                    result.metrics = SkillMetrics(duration_ms=elapsed)

                await self.report(result)
                return result

            except asyncio.TimeoutError:
                last_error = f"timeout after {self.timeout_seconds}s"
                log.warning(
                    f"[skill.{self.name}] attempt {attempt + 1}/{self.max_retries}: "
                    f"{last_error}"
                )

            except Exception as e:
                last_error = str(e)
                log.warning(
                    f"[skill.{self.name}] attempt {attempt + 1}/{self.max_retries}: "
                    f"{last_error}"
                )

            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (2 ** attempt))

        error_out = SkillOutput(success=False, error=last_error)
        await self.report(error_out)
        return error_out
