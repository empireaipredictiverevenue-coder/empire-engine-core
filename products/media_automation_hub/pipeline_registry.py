"""
EMPIRE V49 · MEDIA AUTOMATION HUB — Pipeline Registry
======================================================
OpenMontage-inspired pipeline + tool registry for the media automation hub.

Loads YAML pipeline definitions and discovers tools from the engines/,
platforms/, and scrapers/ directories. Pipelines define stages, each
stage lists tools to execute. The orchestrator reads a pipeline manifest
and executes its stages in sequence.

Architecture:
    Pipeline (YAML) → Stage → Tool (Python) → output

Usage:
    from products.media_automation_hub.pipeline_registry import (
        PipelineRegistry, get_registry, discover_tools,
    )
    reg = get_registry()
    pipeline = reg.load_pipeline("short-form")
    for stage in pipeline.stages:
        result = await stage.execute(ctx)
"""

import os
import sys
import yaml
import logging
import inspect
import importlib
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Type
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger("empire.media_hub.registry")

HUB_DIR = Path(__file__).resolve().parent

# ── Data Classes ────────────────────────────────────────────────────────


@dataclass
class ToolResult:
    """Result from executing a pipeline tool."""
    ok: bool
    output: Any = None
    error: str = ""
    duration_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageConfig:
    """Configuration for a single pipeline stage."""
    name: str
    description: str = ""
    tools: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    timeout_seconds: int = 300
    retry_count: int = 0


@dataclass
class PipelineDef:
    """A complete pipeline definition loaded from YAML."""
    name: str
    label: str
    description: str = ""
    version: str = "1.0"
    output_format: str = "mp4"
    platforms: List[str] = field(default_factory=list)
    stages: List[StageConfig] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Base Tool ───────────────────────────────────────────────────────────


class BaseMediaTool:
    """Base class for all media automation tools.

    Subclasses register automatically when modules are imported.
    Each tool has a name, description, and async execute() method.
    """

    name: str = ""
    description: str = ""
    category: str = "general"  # engine, platform, scraper
    version: str = "1.0"

    async def execute(self, ctx: Dict[str, Any], config: Dict[str, Any]) -> ToolResult:
        """Execute the tool. Override in subclasses."""
        raise NotImplementedError

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Return list of missing required config keys, empty if valid."""
        return []


# ── Tool Registry ───────────────────────────────────────────────────────


class ToolRegistry:
    """Discovers and manages media automation tools."""

    def __init__(self):
        self._tools: Dict[str, Type[BaseMediaTool]] = {}
        self._instances: Dict[str, BaseMediaTool] = {}
        self._discovered = False

    def _scan_module_for_tools(self, mod, count: int) -> int:
        """Scan a module for BaseMediaTool subclasses and register them.
        Returns number of tools found in this module."""
        found = 0
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if (issubclass(obj, BaseMediaTool) and
                    obj is not BaseMediaTool and
                    obj.name):
                self._tools[obj.name] = obj
                found += 1
                log.info(f"[media_hub] discovered tool: {obj.name} ({obj.category})")
        return found

    def discover(self, packages: List[str] = None) -> int:
        """Discover tools by scanning Python packages for BaseMediaTool subclasses."""
        if self._discovered:
            return len(self._tools)

        if packages is None:
            packages = [
                "products.media_automation_hub.engines",
                "products.media_automation_hub.platforms",
                "products.media_automation_hub.scrapers",
            ]

        count = 0
        for pkg_name in packages:
            try:
                pkg = importlib.import_module(pkg_name)
                pkg_path = Path(pkg.__file__).parent

                # ── Scan the package's __init__.py itself ────────────
                # pkgutil.iter_modules skips __init__.py, but all our
                # tools are defined there (one-file-per-package pattern).
                count += self._scan_module_for_tools(pkg, 0)

                # ── Scan separate .py files in the package ───────────
                for _, mod_name, _ in pkgutil.iter_modules([str(pkg_path)]):
                    try:
                        full_name = f"{pkg_name}.{mod_name}"
                        mod = importlib.import_module(full_name)
                        count += self._scan_module_for_tools(mod, 0)
                    except Exception as e:
                        log.debug(f"[media_hub] skip module {mod_name}: {e}")
                        continue
            except Exception as e:
                log.debug(f"[media_hub] package {pkg_name} not importable: {e}")
                continue

        self._discovered = True
        log.info(f"[media_hub] discovered {count} tools across {len(packages)} packages")
        return count

    def get_tool(self, name: str) -> Optional[BaseMediaTool]:
        """Get a tool instance by name (cached)."""
        if name in self._instances:
            return self._instances[name]
        cls = self._tools.get(name)
        if cls is None:
            return None
        instance = cls()
        self._instances[name] = instance
        return instance

    def list_tools(self, category: str = None) -> List[Dict[str, str]]:
        """List all registered tools, optionally filtered by category."""
        result = []
        for name, cls in sorted(self._tools.items()):
            if category and cls.category != category:
                continue
            result.append({
                "name": name,
                "description": cls.description,
                "category": cls.category,
                "version": cls.version,
            })
        return result

    def support_envelope(self) -> Dict[str, Any]:
        """Return the capability envelope — what this hub can do."""
        self.discover()
        by_category = {}
        for name, cls in self._tools.items():
            by_category.setdefault(cls.category, []).append(name)
        return {
            "tools": len(self._tools),
            "by_category": {k: len(v) for k, v in by_category.items()},
            "categories": {k: v for k, v in by_category.items()},
            "pipelines_available": PipelineRegistry().list_pipelines(),
        }


# ── Pipeline Registry ───────────────────────────────────────────────────


class PipelineRegistry:
    """Loads and manages YAML pipeline definitions."""

    def __init__(self, pipeline_dir: str = None):
        self._dir = Path(pipeline_dir) if pipeline_dir else HUB_DIR / "pipeline_defs"
        self._pipelines: Dict[str, PipelineDef] = {}
        self._loaded = False

    def load_all(self, tool_registry: ToolRegistry = None) -> Dict[str, PipelineDef]:
        """Load all pipeline YAML files from the pipeline_defs directory."""
        if self._loaded:
            return self._pipelines

        if not self._dir.is_dir():
            log.warning(f"[media_hub] pipeline_dir not found: {self._dir}")
            self._loaded = True
            return self._pipelines

        count = 0
        for yaml_file in sorted(self._dir.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                if not data or "name" not in data:
                    continue

                stages = []
                for s in data.get("stages", []):
                    stages.append(StageConfig(
                        name=s.get("name", ""),
                        description=s.get("description", ""),
                        tools=s.get("tools", []),
                        config=s.get("config", {}),
                        requires_approval=s.get("requires_approval", False),
                        timeout_seconds=s.get("timeout_seconds", 300),
                        retry_count=s.get("retry_count", 0),
                    ))

                pipeline = PipelineDef(
                    name=data["name"],
                    label=data.get("label", data["name"]),
                    description=data.get("description", ""),
                    version=data.get("version", "1.0"),
                    output_format=data.get("output_format", "mp4"),
                    platforms=data.get("platforms", []),
                    stages=stages,
                    metadata=data.get("metadata", {}),
                )
                self._pipelines[pipeline.name] = pipeline
                count += 1
                log.info(f"[media_hub] loaded pipeline: {pipeline.name} ({len(stages)} stages)")

            except Exception as e:
                log.warning(f"[media_hub] failed to load {yaml_file}: {e}")

        self._loaded = True
        log.info(f"[media_hub] loaded {count} pipelines")
        return self._pipelines

    def load_pipeline(self, name: str) -> Optional[PipelineDef]:
        """Load a specific pipeline by name."""
        self.load_all()
        return self._pipelines.get(name)

    def list_pipelines(self) -> List[Dict[str, Any]]:
        """List all available pipelines."""
        self.load_all()
        return [
            {
                "name": p.name,
                "label": p.label,
                "description": p.description,
                "stages": len(p.stages),
                "platforms": p.platforms,
                "output_format": p.output_format,
            }
            for p in sorted(self._pipelines.values(), key=lambda x: x.name)
        ]


# ── Singleton ───────────────────────────────────────────────────────────

_registry: Optional[ToolRegistry] = None
_pipeline_registry: Optional[PipelineRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _registry.discover()
    return _registry


def get_pipeline_registry() -> PipelineRegistry:
    global _pipeline_registry
    if _pipeline_registry is None:
        _pipeline_registry = PipelineRegistry()
        _pipeline_registry.load_all()
    return _pipeline_registry


def discover_tools() -> int:
    """Force tool discovery. Returns count of tools found."""
    return get_registry().discover()


def support_envelope() -> Dict[str, Any]:
    """Return the full capability envelope for this hub."""
    return get_registry().support_envelope()
