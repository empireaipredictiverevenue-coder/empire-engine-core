"""
EMPIRE V49 · SKILL REGISTRY
============================
Central registry of all skills in the system with immutability enforcement.
"""

import logging
from collections import defaultdict
from typing import Any, Optional, Type

from .base import BaseSkill


log = logging.getLogger("empire.skills.registry")


class SkillFidelityError(Exception):
    """Raised when a skill fidelity violation is detected."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# SKILL VERSION TRACKING
# ─────────────────────────────────────────────────────────────────────────────


class SkillVersion:
    """Tracks a skill class and its version metadata."""

    def __init__(self, version: str, skill_cls: Type[BaseSkill]):
        self.version = version
        self._skill_cls = skill_cls
        self._instance: Optional[BaseSkill] = None

    def instantiate(self) -> BaseSkill:
        if self._instance is None:
            self._instance = self._skill_cls()
        return self._instance


# ─────────────────────────────────────────────────────────────────────────────
# SKILL REGISTRY
# ─────────────────────────────────────────────────────────────────────────────


class SkillRegistry:
    """
    The central registry of all skills in the system.

    Responsibilities:
      - Register/unregister skills
      - Resolve dependencies (DAG-based topological sort)
      - Version management (semver, active version per skill)
      - Hot-swap (replace a skill version at runtime)
      - Discovery (find skills by tag, capability, dependency)
    """

    def __init__(self):
        self._skills: dict[str, list[SkillVersion]] = defaultdict(list)
        self._active: dict[str, str] = {}

    # ── Registration ───────────────────────────────────────────────────

    def register(self, skill_cls: Type[BaseSkill]) -> None:
        """Register a skill class. Instantiated lazily on first use."""
        name = skill_cls.name
        version = skill_cls.version
        self._skills[name].append(SkillVersion(version, skill_cls))
        self._skills[name].sort(key=lambda sv: sv.version, reverse=True)
        if name not in self._active:
            self._active[name] = version
        log.info(f"[skills] registered {name} v{version}")

    def unregister(self, skill_name: str) -> bool:
        """Remove all versions of a skill."""
        if skill_name in self._skills:
            del self._skills[skill_name]
            self._active.pop(skill_name, None)
            log.info(f"[skills] unregistered {skill_name}")
            return True
        return False

    # ── Version Management ─────────────────────────────────────────────

    def activate(self, skill_name: str, version: str) -> bool:
        """Switch to a specific version of a skill."""
        versions = self._skills.get(skill_name, [])
        for sv in versions:
            if sv.version == version:
                self._active[skill_name] = version
                log.info(f"[skills] activated {skill_name} v{version}")
                return True
        return False

    def list_versions(self, skill_name: str) -> list[str]:
        """List all registered versions of a skill."""
        return [sv.version for sv in self._skills.get(skill_name, [])]

    # ── Retrieval ─────────────────────────────────────────────────────

    def get(self, skill_name: str) -> Optional[BaseSkill]:
        """Get the active instance of a skill by name."""
        versions = self._skills.get(skill_name, [])
        active_ver = self._active.get(skill_name)
        for sv in versions:
            if sv.version == active_ver:
                return sv.instantiate()
        if versions:
            return versions[0].instantiate()
        return None

    def get_by_tag(self, tag: str) -> list[BaseSkill]:
        """Find all skills with a given tag."""
        results = []
        for name in self._skills:
            skill = self.get(name)
            if skill and tag in skill.tags:
                results.append(skill)
        return results

    def has_skill(self, skill_name: str) -> bool:
        """Check if a skill is registered."""
        return skill_name in self._skills

    # ── Dependency Resolution ──────────────────────────────────────────

    def resolve_dag(self, skill_name: str) -> list[str]:
        """Return the execution order for a skill and all its dependencies.
        Uses Kahn's algorithm. Returns [skill, dep1, dep2, ...] — execute in order.
        """
        graph = self._build_dependency_graph(skill_name)
        return self._topological_sort(graph)

    def _build_dependency_graph(self, skill_name: str) -> dict[str, list[str]]:
        """Build a directed graph of skill dependencies."""
        graph: dict[str, list[str]] = {}
        visited: set[str] = set()

        def _add_deps(name: str):
            if name in visited:
                return
            visited.add(name)
            skill = self.get(name)
            if skill:
                deps = skill.dependencies
                graph[name] = deps
                for dep in deps:
                    _add_deps(dep)
            else:
                graph[name] = []

        _add_deps(skill_name)
        return graph

    def _topological_sort(self, graph: dict[str, list[str]]) -> list[str]:
        """Kahn's algorithm for topological sort."""
        in_degree: dict[str, int] = {node: 0 for node in graph}
        for node, deps in graph.items():
            for dep in deps:
                if dep in graph:
                    in_degree[node] = in_degree.get(node, 0) + 1

        queue = [node for node, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for other, deps in graph.items():
                if node in deps:
                    in_degree[other] -= 1
                    if in_degree[other] == 0:
                        queue.append(other)

        # Check for cycles
        if len(result) != len(graph):
            raise ValueError(f"Circular dependency detected in skills: {graph}")

        return result

    # ── Snapshot ───────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Full registry snapshot for the SPA dashboard."""
        return {
            "total_skills": len(self._skills),
            "skills": {
                name: {
                    "versions": self.list_versions(name),
                    "active": self._active.get(name, "?"),
                }
                for name in self._skills
            },
            "active_versions": dict(self._active),
        }


# ─────────────────────────────────────────────────────────────────────────────
# IMMUTABLE SKILL REGISTRY
# ─────────────────────────────────────────────────────────────────────────────


class ImmutableSkillRegistry(SkillRegistry):
    """
    Extends SkillRegistry with immutability enforcement.

    After a skill class is registered:
      - Its instances are frozen (no attribute mutation)
      - Its methods cannot be replaced
      - Only the registry can switch active versions
    """

    def __init__(self):
        super().__init__()
        self._frozen: set[str] = set()

    def register(self, skill_cls: Type[BaseSkill]) -> None:
        super().register(skill_cls)
        name = skill_cls.name
        self._frozen.add(name)

        for version_entry in self._skills.get(name, []):
            instance = version_entry._instance
            if instance and not getattr(instance, "_frozen", False):
                self._freeze_skill(instance)

    def _freeze_skill(self, skill: BaseSkill) -> None:
        """Deep-freeze a skill instance to prevent runtime mutation."""
        if getattr(skill, "_frozen", False):
            return

        skill.__dict__["_frozen"] = True

        # Store refs to original methods for integrity verification
        for method_name in ["execute", "validate", "report"]:
            method = getattr(skill, method_name, None)
            if method and hasattr(method, "__func__"):
                skill.__dict__[f"_locked_{method_name}"] = method.__func__

        original_setattr = skill.__class__.__setattr__

        def _immutable_setattr(self, name, value):
            if name == "_frozen":
                original_setattr(self, name, value)
                return
            if getattr(self, "_frozen", False) and name != "__dict__":
                raise SkillFidelityError(
                    f"Cannot modify attribute '{name}' on frozen skill '{self.name}'"
                )
            original_setattr(self, name, value)

        skill.__class__.__setattr__ = _immutable_setattr

    def wire_dependency(self, skill_name: str, attr: str, value: Any) -> None:
        """
        Wire a dependency on a skill instance BEFORE it's frozen.
        
        Creates the skill instance if needed, sets the attribute,
        and marks the instance as ready for freeze on next get().
        Only allowed during initialization — before any skill is executed.
        """
        sv_list = self._skills.get(skill_name)
        if not sv_list:
            raise KeyError(f"Skill '{skill_name}' not registered yet. Call register() first.")
        sv = sv_list[0]  # Active version
        if sv._instance is None:
            sv._instance = sv._skill_cls()
        # Instance is not frozen yet — safe to set attributes
        setattr(sv._instance, attr, value)

    def get(self, skill_name: str) -> Optional[BaseSkill]:
        skill = super().get(skill_name)
        if skill and skill_name in self._frozen:
            if not getattr(skill, "_frozen", False):
                self._freeze_skill(skill)
        return skill
