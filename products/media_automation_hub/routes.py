"""
EMPIRE V49 · MEDIA AUTOMATION HUB — API Routes
================================================
REST API endpoints for the media automation hub, wired into hub.py.

Routes:
  GET  /api/v1/media/status          — Hub health and capability envelope
  GET  /api/v1/media/pipelines       — List available pipelines
  GET  /api/v1/media/tools           — List registered tools
  POST /api/v1/media/run             — Execute a pipeline
  POST /api/v1/media/dry-run         — Validate a pipeline without executing
  GET  /api/v1/media/runs            — List recent pipeline runs
"""

import json
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query

log = logging.getLogger("empire.media_hub.routes")


def register_media_hub_routes(app, require_auth=None):
    """Register media automation hub endpoints on the FastAPI app.

    Usage from hub.py:
        from products.media_automation_hub.routes import register_media_hub_routes
        register_media_hub_routes(app, require_auth=require_auth)
    """

    @app.get("/api/v1/media/status")
    async def media_hub_status(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return the orchestrator health and full capability envelope."""
        from products.media_automation_hub import status
        return status()

    @app.get("/api/v1/media/pipelines")
    async def media_hub_pipelines(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List all available pipelines with their stage counts."""
        from products.media_automation_hub.pipeline_registry import get_pipeline_registry
        reg = get_pipeline_registry()
        return {
            "ok": True,
            "pipelines": reg.list_pipelines(),
            "count": len(reg.list_pipelines()),
        }

    @app.get("/api/v1/media/tools")
    async def media_hub_tools(
        category: Optional[str] = Query(None, description="Filter by category: engine, platform, scraper"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List all registered tools, optionally filtered by category."""
        from products.media_automation_hub.pipeline_registry import get_registry
        reg = get_registry()
        tools = reg.list_tools(category=category)
        return {
            "ok": True,
            "tools": tools,
            "count": len(tools),
            "categories": sorted(set(t["category"] for t in tools)),
        }

    @app.post("/api/v1/media/dry-run")
    async def media_hub_dry_run(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Validate a pipeline without executing — checks tool availability."""
        pipeline_name = body.get("pipeline", "")
        if not pipeline_name:
            raise HTTPException(400, "Missing required field: pipeline")

        from products.media_automation_hub import MediaOrchestrator, get_orchestrator
        orch = get_orchestrator()
        result = await orch.run_pipeline(pipeline_name, dry_run=True)
        return result

    @app.post("/api/v1/media/run")
    async def media_hub_run(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Execute a pipeline.

        Body:
          pipeline: str (required) — Pipeline name (short-form, b2b-explainer, etc.)
          topic: str (optional) — Topic for content generation
          script: str (optional) — Pre-written script text
          dry_run: bool (optional) — Validate only, don't execute
        """
        pipeline_name = body.get("pipeline", "")
        if not pipeline_name:
            raise HTTPException(400, "Missing required field: pipeline")

        from products.media_automation_hub import get_orchestrator
        orch = get_orchestrator()

        ctx = {}
        if body.get("topic"):
            ctx["topic"] = body["topic"]
        if body.get("script"):
            ctx["script_text"] = body["script"]
        if body.get("niche"):
            ctx["niche"] = body["niche"]

        dry_run = body.get("dry_run", False)
        result = await orch.run_pipeline(pipeline_name, ctx=ctx, dry_run=dry_run)
        return result

    @app.get("/api/v1/media/runs")
    async def media_hub_runs(
        limit: int = Query(20, ge=1, le=100),
        pipeline: Optional[str] = Query(None),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List recent pipeline runs from Supabase."""
        import os
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return {"ok": False, "error": "Supabase not configured", "runs": []}

        try:
            from supabase import create_client
            sb = create_client(url, key)
            query = sb.table("media_pipeline_runs").select("*").order("timestamp", desc=True).limit(limit)
            if pipeline:
                query = query.eq("pipeline_name", pipeline)
            r = query.execute()
            return {"ok": True, "runs": r.data or [], "count": len(r.data or [])}
        except Exception as e:
            return {"ok": False, "error": str(e), "runs": []}

    # ── Analytics endpoints ──────────────────────────────────────────

    @app.get("/api/v1/media/analytics")
    async def media_analytics_overview(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Pipeline run analytics: success rates, run counts, avg durations per pipeline."""
        from products.media_automation_hub.pipeline_registry import get_registry
        reg = get_registry()
        tool = reg.get_tool("analytics_reporter")
        if tool is None:
            return {"ok": False, "error": "analytics_reporter tool not registered"}
        result = await tool.execute({}, {"action": "overview"})
        return {"ok": result.ok, "analytics": result.output, "error": result.error}

    @app.get("/api/v1/media/analytics/pipeline/{pipeline_name}")
    async def media_analytics_pipeline(
        pipeline_name: str,
        limit: int = Query(50, ge=1, le=200),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Per-pipeline detail: recent runs, success rate, avg duration."""
        from products.media_automation_hub.pipeline_registry import get_registry
        reg = get_registry()
        tool = reg.get_tool("analytics_reporter")
        if tool is None:
            return {"ok": False, "error": "analytics_reporter tool not registered"}
        result = await tool.execute({}, {"action": "pipeline", "pipeline": pipeline_name, "limit": limit})
        return {"ok": result.ok, "analytics": result.output, "error": result.error}

    @app.get("/api/v1/media/analytics/timeseries")
    async def media_analytics_timeseries(
        days: int = Query(14, ge=1, le=90),
        pipeline: Optional[str] = Query(None),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Daily pipeline run volumes over time."""
        from products.media_automation_hub.pipeline_registry import get_registry
        reg = get_registry()
        tool = reg.get_tool("analytics_reporter")
        if tool is None:
            return {"ok": False, "error": "analytics_reporter tool not registered"}
        result = await tool.execute({}, {"action": "timeseries", "days": days, "pipeline": pipeline or ""})
        return {"ok": result.ok, "analytics": result.output, "error": result.error}

    @app.get("/api/v1/media/analytics/tools")
    async def media_analytics_tool_usage(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Tool/stage usage stats: failure rates, avg durations per stage."""
        from products.media_automation_hub.pipeline_registry import get_registry
        reg = get_registry()
        tool = reg.get_tool("analytics_reporter")
        if tool is None:
            return {"ok": False, "error": "analytics_reporter tool not registered"}
        result = await tool.execute({}, {"action": "tool_usage"})
        return {"ok": result.ok, "analytics": result.output, "error": result.error}

    log.info("[media_hub.routes] REST routes registered (10 endpoints)")
