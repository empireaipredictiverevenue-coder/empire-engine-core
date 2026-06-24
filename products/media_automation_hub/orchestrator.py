"""
EMPIRE V49 · MEDIA AUTOMATION HUB — Orchestrator
===================================================
OpenMontage-inspired pipeline orchestrator for the media automation hub.

Reads a pipeline definition (YAML) and executes its stages sequentially,
using the tool registry to find and invoke the right tools for each stage.
Reports progress to Supabase and supports checkpoint/resume.

Architecture:
    PipelineDef → StageConfig[] → Tool.execute(ctx, config) → ToolResult

Usage:
    from products.media_automation_hub.orchestrator import MediaOrchestrator
    orch = MediaOrchestrator()
    result = await orch.run_pipeline("short-form", ctx={"topic": "storm leads"})
"""

import os
import re
import json
import uuid
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from products.media_automation_hub.pipeline_registry import (
    ToolRegistry, PipelineRegistry, PipelineDef, StageConfig, ToolResult,
    get_registry, get_pipeline_registry,
)

log = logging.getLogger("empire.media_hub.orchestrator")

# ── Supabase (optional, graceful degradation) ──────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _sb():
    """Lazy Supabase client. Returns None if not configured."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


def _log_run(sb, run_id: str, pipeline_name: str, stage: str, status: str,
             result: Dict[str, Any] = None, error: str = "", duration_ms: float = 0):
    """Log a pipeline stage run to Supabase. Best-effort."""
    if sb is None:
        return
    try:
        sb.table("media_pipeline_runs").insert({
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "stage_name": stage,
            "status": status,
            "result": result or {},
            "error": error[:500],
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass


# ── Orchestrator ────────────────────────────────────────────────────────


class MediaOrchestrator:
    """Runs media automation pipelines from YAML definitions.

    Features:
      - Pipeline loading from YAML
      - Stage-by-stage execution with tool discovery
      - Progress logging to Supabase (media_pipeline_runs)
      - Checkpoint/resume support
      - Dry-run mode for pipeline validation
    """

    def __init__(self, pipeline_registry: PipelineRegistry = None, tool_registry: ToolRegistry = None):
        self.pipeline_registry = pipeline_registry or get_pipeline_registry()
        self.tool_registry = tool_registry or get_registry()
        self._sb = _sb()

    # ── Public API ─────────────────────────────────────────────────────

    async def run_pipeline(self, pipeline_name: str, ctx: Dict[str, Any] = None,
                           dry_run: bool = False) -> Dict[str, Any]:
        """Execute a full pipeline by name.

        Args:
            pipeline_name: Name of the pipeline (e.g. 'short-form')
            ctx: Context dict passed to every stage (topic, script, paths, etc.)
            dry_run: If True, validate pipeline and tools without executing

        Returns:
            Dict with status, stages, output, and run_id
        """
        ctx = ctx or {}
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        pipeline = self.pipeline_registry.load_pipeline(pipeline_name)
        if pipeline is None:
            return {"status": "failed", "error": f"Pipeline not found: {pipeline_name}"}

        log.info(f"[media_hub] START pipeline={pipeline_name} run={run_id[:8]} "
                 f"({len(pipeline.stages)} stages)")

        if dry_run:
            return await self._dry_run(pipeline, run_id)

        # ── Execute stages sequentially ────────────────────────────────
        stage_results = []
        overall_ok = True
        pipeline_output = {}

        for i, stage in enumerate(pipeline.stages):
            stage_start = time.time()
            log.info(f"[media_hub]  stage {i+1}/{len(pipeline.stages)}: {stage.name} "
                     f"→ {stage.tools}")

            stage_result = await self._execute_stage(stage, ctx, run_id, pipeline.name)

            duration_ms = (time.time() - stage_start) * 1000
            stage_result["duration_ms"] = duration_ms
            stage_results.append(stage_result)

            # Merge stage output into context for downstream stages
            if stage_result.get("output"):
                ctx.update(stage_result["output"])
                pipeline_output.update(stage_result["output"])

            # Log to Supabase
            _log_run(self._sb, run_id, pipeline.name, stage.name,
                     "ok" if stage_result["ok"] else "failed",
                     result=stage_result.get("output"),
                     error=stage_result.get("error", ""),
                     duration_ms=duration_ms)

            if not stage_result["ok"]:
                overall_ok = False
                log.warning(f"[media_hub] stage {stage.name} FAILED: {stage_result.get('error', '')}")

                # Check retry
                if stage.retry_count > 0:
                    log.info(f"[media_hub] retrying stage {stage.name} ({stage.retry_count} retries remaining)")
                    for retry in range(stage.retry_count):
                        retry_result = await self._execute_stage(stage, ctx, run_id, pipeline.name)
                        if retry_result["ok"]:
                            stage_results[-1] = retry_result
                            overall_ok = True
                            break
                        log.info(f"[media_hub] retry {retry+1}/{stage.retry_count} also failed")

                if not overall_ok:
                    break

            # Approval gate
            if stage.requires_approval and not dry_run:
                log.info(f"[media_hub] approval required for stage: {stage.name}")
                stage_result["awaiting_approval"] = True
                # In automated mode, continue but flag for review

        # ── Finalize ───────────────────────────────────────────────────
        finished_at = datetime.now(timezone.utc)
        total_duration_ms = (finished_at - started_at).total_seconds() * 1000

        result = {
            "status": "ok" if overall_ok else "failed",
            "run_id": run_id,
            "pipeline": pipeline_name,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": total_duration_ms,
            "stages": stage_results,
            "output": pipeline_output,
        }

        # Log final run to agent_activity
        sb = self._sb
        if sb:
            try:
                sb.table("agent_activity").insert({
                    "agent_name": "media_automation_hub",
                    "run_id": run_id,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "status": result["status"],
                    "rows_processed": len([s for s in stage_results if s["ok"]]),
                    "rows_errored": len([s for s in stage_results if not s["ok"]]),
                    "summary": f"{pipeline_name}: {len(stage_results)} stages, {'OK' if overall_ok else 'FAILED'}",
                    "meta": {"pipeline": pipeline_name, "stages": len(stage_results)},
                }).execute()
            except Exception:
                pass

        log.info(f"[media_hub] DONE pipeline={pipeline_name} run={run_id[:8]} "
                 f"status={result['status']} ({total_duration_ms:.0f}ms)")
        return result

    @staticmethod
    def _resolve_ctx_ref(value: Any, ctx: Dict[str, Any]) -> Any:
        """Resolve {{ctx.key.path}} template references in a config value.

        Supports dotted paths like {{ctx.download.file_path}} by
        walking nested dicts. Non-string values pass through unchanged.
        """
        if not isinstance(value, str):
            return value
        # Match {{ctx.key.path}} patterns
        def _replacer(m):
            path = m.group(1).strip()
            parts = path.split(".")
            node = ctx
            for p in parts:
                if isinstance(node, dict):
                    node = node.get(p)
                else:
                    return m.group(0)  # unresolvable — leave as-is
                if node is None:
                    return m.group(0)
            return str(node) if not isinstance(node, (dict, list)) else m.group(0)
        return re.sub(r"\{\{ctx\.([^}]+)\}\}", _replacer, value)

    @staticmethod
    def _interpolate_config(config: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively resolve {{ctx.*}} references in a config dict."""
        return {
            k: MediaOrchestrator._resolve_ctx_ref(v, ctx)
            for k, v in config.items()
        }

    async def _execute_stage(self, stage: StageConfig, ctx: Dict[str, Any],
                             run_id: str, pipeline_name: str) -> Dict[str, Any]:
        """Execute a single pipeline stage — find tools, run them, collect results."""
        stage_outputs = {}
        stage_ok = True
        stage_error = ""

        # Resolve template references ({{ctx.download.file_path}}) in config
        resolved_config = self._interpolate_config(stage.config, ctx)
        # Merge resolved config into ctx so tools that read from ctx
        # (FFmpegComposer, CaptionBurner, KeyframeExtractor) can access
        # interpolated values like audio_path, video_path, output_path.
        merged_ctx = {**ctx, **resolved_config}

        for tool_name in stage.tools:
            tool = self.tool_registry.get_tool(tool_name)
            if tool is None:
                log.warning(f"[media_hub] tool not found: {tool_name}")
                stage_ok = False
                stage_error = f"Tool not found in registry: {tool_name}"
                continue

            try:
                result = await tool.execute(merged_ctx, resolved_config)
                if result.ok and result.output:
                    output_dict = result.output if isinstance(result.output, dict) else {"result": result.output}
                    stage_outputs.update(output_dict)
                    # Feed output into merged_ctx so later tools in the same
                    # stage can see earlier tools' results (e.g. caption_burner
                    # → captions_ass → ffmpeg_composer).
                    merged_ctx.update(output_dict)
                if not result.ok:
                    stage_ok = False
                    stage_error = result.error or f"Tool '{tool_name}' failed"
            except Exception as e:
                stage_ok = False
                stage_error = f"Tool '{tool_name}' crashed: {e}"
                log.exception(f"[media_hub] tool {tool_name} crashed")

        return {
            "stage": stage.name,
            "tools_used": stage.tools,
            "ok": stage_ok,
            "output": stage_outputs,
            "error": stage_error,
        }

    async def _dry_run(self, pipeline: PipelineDef, run_id: str) -> Dict[str, Any]:
        """Validate pipeline and tool availability without executing."""
        stages = []
        all_ok = True
        for stage in pipeline.stages:
            missing = [t for t in stage.tools if self.tool_registry.get_tool(t) is None]
            stages.append({
                "stage": stage.name,
                "tools": stage.tools,
                "available": [t for t in stage.tools if t not in missing],
                "missing": missing,
                "ok": len(missing) == 0,
            })
            if missing:
                all_ok = False

        return {
            "status": "dry_run",
            "run_id": run_id,
            "pipeline": pipeline.name,
            "stages": stages,
            "all_tools_available": all_ok,
            "verdict": "READY" if all_ok else "MISSING_TOOLS",
        }

    def status(self) -> Dict[str, Any]:
        """Return orchestrator health and capability summary."""
        return {
            "orchestrator": "online",
            "tools_available": len(self.tool_registry.list_tools()),
            "pipelines_available": len(self.pipeline_registry.list_pipelines()),
            "supabase_connected": self._sb is not None,
            "support_envelope": self.tool_registry.support_envelope(),
        }


# ── Singleton ───────────────────────────────────────────────────────────

_orchestrator: Optional[MediaOrchestrator] = None


def get_orchestrator() -> MediaOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MediaOrchestrator()
    return _orchestrator


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    import asyncio
    import sys

    if "--list" in sys.argv:
        reg = get_pipeline_registry()
        print(json.dumps(reg.list_pipelines(), indent=2))
    elif "--tools" in sys.argv:
        reg = get_registry()
        print(json.dumps(reg.list_tools(), indent=2))
    elif "--envelope" in sys.argv:
        reg = get_registry()
        print(json.dumps(reg.support_envelope(), indent=2))
    elif "--dry-run" in sys.argv:
        pipeline_name = sys.argv[sys.argv.index("--dry-run") + 1] if len(sys.argv) > 2 else "short-form"
        result = asyncio.run(get_orchestrator().run_pipeline(pipeline_name, dry_run=True))
        print(json.dumps(result, indent=2, default=str))
    elif "--run" in sys.argv:
        pipeline_name = sys.argv[sys.argv.index("--run") + 1] if len(sys.argv) > 2 else "short-form"
        topic = sys.argv[sys.argv.index("--topic") + 1] if "--topic" in sys.argv else "storm leads"
        result = asyncio.run(get_orchestrator().run_pipeline(pipeline_name, ctx={"topic": topic}))
        print(json.dumps(result, indent=2, default=str))
    else:
        orch = get_orchestrator()
        print(json.dumps(orch.status(), indent=2, default=str))


if __name__ == "__main__":
    main()
