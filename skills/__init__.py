"""
EMPIRE V49 · SKILLS FRAMEWORK
================================
Standardized routines for every bot and agent in the fleet.

Every skill has:
  - A validated input/output contract (SkillInput → SkillOutput)
  - A standard lifecycle (validate → execute → report)
  - Dependency resolution (DAG-based topological sort)
  - Retry with backoff, timeout, and circuit breaker
  - Langfuse tracing and metrics emission

Package structure:
  base.py       — BaseSkill abstract class, SkillInput, SkillOutput, SkillMetrics
  registry.py   — SkillRegistry + ImmutableSkillRegistry
  context.py    — SkillContext for dependency injection
  harness.py    — SkillHarness, HarnessConfig, HarnessManager
  boundary.py   — SkillBoundary, FidelityAwareHarness, FidelityAuditor
  dynamic.py    — DynamicSkill, VaultSkillDiscoverer, note parser/factory
"""

from .base import BaseSkill, SkillInput, SkillOutput, SkillMetrics, SkillContext
from .registry import SkillRegistry, ImmutableSkillRegistry, SkillFidelityError
from .harness import SkillHarness, HarnessConfig, HarnessManager
from .boundary import SkillBoundary, FidelityAwareHarness, FidelityAuditor, AlertSuppressor
from .dynamic import (
    DynamicSkill,
    VaultSkillDiscoverer,
    SkillNote,
    parse_vault_note,
    make_skill_class,
    register_dynamic_skill,
    unregister_dynamic_skill,
    is_skill_note,
)

__all__ = [
    "BaseSkill", "SkillInput", "SkillOutput", "SkillMetrics", "SkillContext",
    "SkillRegistry", "ImmutableSkillRegistry", "SkillFidelityError",
    "SkillHarness", "HarnessConfig", "HarnessManager",
    "SkillBoundary", "FidelityAwareHarness", "FidelityAuditor", "AlertSuppressor",
    "DynamicSkill", "VaultSkillDiscoverer", "SkillNote",
    "parse_vault_note", "make_skill_class", "register_dynamic_skill",
    "unregister_dynamic_skill", "is_skill_note",
]
