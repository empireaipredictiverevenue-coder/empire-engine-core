"""
EMPIRE V49 · SKILLS ROUTES
============================
REST API routes for the Skills Framework — registry management,
harness configuration, boundary/fidelity monitoring, vault access,
and dynamic skill discovery.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from skills.registry import SkillRegistry
from skills.harness import HarnessManager, HarnessConfig
from skills.boundary import SkillBoundary, FidelityAuditor


log = logging.getLogger("empire.skills.routes")


def register_skills_routes(
    app,
    registry: SkillRegistry,
    harness_mgr: HarnessManager,
    auditor: FidelityAuditor,
    boundaries: dict[str, SkillBoundary],
    require_auth=None,
    discoverer=None,
):
    """Wire Skills Framework REST routes onto the hub.

    If discoverer (VaultSkillDiscoverer) is provided, dynamic skill discovery
    and generation routes are also registered.
    """

    # ── Skills list (static path — must be before {skill_name}) ──────

    @app.get("/api/v1/skills")
    async def skills_list(auth=Depends(require_auth) if require_auth else None):
        """List all registered skills with version info."""
        return registry.snapshot()

    # ── Dynamic Skill Discovery routes (static paths — before {skill_name}) ─

    if discoverer is not None:

        @app.get("/api/v1/skills/discovered")
        async def skills_discovered(auth=Depends(require_auth) if require_auth else None):
            """List all vault-discovered dynamic skills."""
            return {
                "skills": discoverer.list_discovered(),
                "tracked": discoverer.snapshot(),
            }

        @app.post("/api/v1/skills/discover")
        async def skills_discover_scan(auth=Depends(require_auth) if require_auth else None):
            """Scan vault notes for type:skill definitions and register new ones."""
            result = discoverer.scan_and_register()
            return {
                "ok": True,
                "registered": result["registered"],
                "skipped": result["skipped"],
                "failed": result["failed"],
                "total": result["total"],
                "skills": result["skills"],
            }

        @app.post("/api/v1/skills/generate")
        async def skills_generate(
            body: dict,
            auth=Depends(require_auth) if require_auth else None,
        ):
            """Create a new vault skill note from explicit parameters.

            Body:
              name: str (required)
              description: str
              instructions: str
              tags: list[str]
              required_params: list[str]
              dependencies: list[str]
              execution_mode: str (default 'llm')
              timeout_seconds: float (default 60.0)
              overwrite: bool (default false)
            """
            p = body
            try:
                result = await discoverer.generate_skill_note(
                    name=p["name"],
                    description=p.get("description", ""),
                    instructions=p.get("instructions", "Execute the skill according to its description."),
                    tags=p.get("tags"),
                    required_params=p.get("required_params"),
                    dependencies=p.get("dependencies"),
                    execution_mode=p.get("execution_mode", "llm"),
                    timeout_seconds=float(p.get("timeout_seconds", 60.0)),
                    overwrite=bool(p.get("overwrite", False)),
                )
                if result.get("ok"):
                    return result
                raise HTTPException(400, result.get("error", "skill generation failed"))
            except KeyError as e:
                raise HTTPException(400, f"Missing required field: {e}")

        @app.post("/api/v1/skills/generate-from-description")
        async def skills_generate_from_desc(
            body: dict,
            auth=Depends(require_auth) if require_auth else None,
        ):
            """Use AI to generate a vault skill note from a natural language description.

            Body:
              description: str (required) — what the skill should do
            """
            desc = body.get("description", "")
            if not desc:
                raise HTTPException(400, "Missing 'description' field")

            if discoverer.ask_llm is None:
                raise HTTPException(400, "ask_llm not available — cannot generate from description")

            result = await discoverer.generate_from_description(description=desc)
            if result.get("ok"):
                return result
            raise HTTPException(400, result.get("error", "AI skill generation failed"))

        log.info("[skills] dynamic discovery routes registered")

    # ── Skill detail (parameterized path — must be after static routes) ──

    @app.get("/api/v1/skills/{skill_name}")
    async def skills_get(skill_name: str, auth=Depends(require_auth) if require_auth else None):
        """Get details for a specific skill."""
        skill = registry.get(skill_name)
        if not skill:
            raise HTTPException(404, f"Skill '{skill_name}' not found")
        return {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "tags": skill.tags,
            "dependencies": skill.dependencies,
            "timeout_seconds": skill.timeout_seconds,
            "versions": registry.list_versions(skill_name),
            "active_version": registry._active.get(skill_name),
        }

    @app.post("/api/v1/skills/{skill_name}/activate")
    async def skills_activate(
        skill_name: str,
        version: str = Query(..., description="Semver version to activate"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Switch to a specific version of a skill."""
        ok = registry.activate(skill_name, version)
        if not ok:
            raise HTTPException(404, f"Version '{version}' not found for skill '{skill_name}'")
        return {"ok": True, "skill": skill_name, "version": version}

    @app.delete("/api/v1/skills/{skill_name}")
    async def skills_delete(
        skill_name: str,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Unregister a dynamic skill."""
        from skills.dynamic import unregister_dynamic_skill
        ok = unregister_dynamic_skill(registry, skill_name)
        if not ok:
            raise HTTPException(404, f"Skill '{skill_name}' not found")
        return {"ok": True, "skill": skill_name}

    # ── Harness routes ────────────────────────────────────────────────

    @app.get("/api/v1/harness/status")
    async def harness_status(auth=Depends(require_auth) if require_auth else None):
        """Health status of all active harnesses."""
        return harness_mgr.health_check()

    @app.get("/api/v1/harness/snapshot")
    async def harness_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Full HarnessManager snapshot."""
        return harness_mgr.snapshot()

    @app.post("/api/v1/harness/configure/{skill_name}")
    async def harness_configure(
        skill_name: str,
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Override harness config for a specific skill."""
        config = HarnessConfig(
            timeout=body.get("timeout", 30.0),
            max_retries=body.get("max_retries", 3),
            max_concurrent=body.get("max_concurrent", 1),
            circuit_breaker=body.get("circuit_breaker", False),
            circuit_threshold=body.get("circuit_threshold", 5),
            circuit_reset_seconds=body.get("circuit_reset_seconds", 60.0),
        )
        harness_mgr.configure_skill(skill_name, config)
        return {"ok": True, "skill": skill_name}

    @app.post("/api/v1/harness/reset-circuit/{skill_name}")
    async def harness_reset_circuit(
        skill_name: str,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Manually reset a skill's circuit breaker."""
        ok = harness_mgr.reset_circuit(skill_name)
        if not ok:
            raise HTTPException(404, f"No harness found for skill '{skill_name}'")
        return {"ok": True, "skill": skill_name}

    # ── Fidelity / Boundary routes ────────────────────────────────────

    @app.get("/api/v1/fidelity")
    async def fidelity_report(auth=Depends(require_auth) if require_auth else None):
        """Fidelity audit report for all agents."""
        return auditor.report()

    @app.get("/api/v1/fidelity/boundaries")
    async def fidelity_boundaries(auth=Depends(require_auth) if require_auth else None):
        """List all agent boundaries with fidelity scores."""
        return {
            "boundaries": {
                name: b.snapshot() for name, b in boundaries.items()
            },
            "count": len(boundaries),
        }

    # ── Vault routes ──────────────────────────────────────────────────

    @app.get("/api/v1/vault/list")
    async def vault_list(auth=Depends(require_auth) if require_auth else None):
        """List all notes in the brain vault."""
        import os
        vault_repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_vault")
        vault_hermes = os.path.expanduser("~/.hermes/brain_vault")

        notes = []
        for vault_dir in [vault_repo, vault_hermes]:
            if not os.path.isdir(vault_dir):
                continue
            source = "repo" if vault_dir == vault_repo else "hermes"
            for root, _dirs, files in os.walk(vault_dir):
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    filepath = os.path.join(root, f)
                    rel_path = os.path.relpath(filepath, vault_dir)
                    notes.append({
                        "path": rel_path,
                        "source": source,
                        "size": os.path.getsize(filepath),
                    })

        return {"notes": notes, "count": len(notes)}

    @app.get("/api/v1/vault/read/{path:path}")
    async def vault_read(
        path: str,
        max_chars: int = Query(5000, ge=100, le=50000),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Read a note from the brain vault."""
        import os
        vault_repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_vault")
        vault_hermes = os.path.expanduser("~/.hermes/brain_vault")

        for base in [vault_repo, vault_hermes]:
            full = os.path.normpath(os.path.join(base, path.lstrip("/")))
            if os.path.exists(full) and full.startswith(base):
                with open(full, "r") as f:
                    content = f.read(max_chars)
                return {
                    "content": content,
                    "path": path,
                    "size": len(content),
                }

        raise HTTPException(404, f"Vault note not found: {path}")

    @app.get("/api/v1/vault/search")
    async def vault_search(
        q: str = Query(..., description="Keyword to search for"),
        max_results: int = Query(10, ge=1, le=50),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Search vault notes by keyword."""
        import os
        vault_repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_vault")
        vault_hermes = os.path.expanduser("~/.hermes/brain_vault")

        results = []
        query = q.lower()

        for vault_dir in [vault_repo, vault_hermes]:
            if not os.path.isdir(vault_dir):
                continue
            for root, _dirs, files in os.walk(vault_dir):
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    filepath = os.path.join(root, f)
                    rel_path = os.path.relpath(filepath, vault_dir)
                    try:
                        with open(filepath, "r") as fh:
                            content = fh.read(5000)
                        if query in content.lower():
                            idx = content.lower().find(query)
                            start = max(0, idx - 80)
                            end = min(len(content), idx + len(query) + 160)
                            excerpt = content[start:end].replace("\n", " ")
                            results.append({
                                "path": rel_path,
                                "excerpt": f"...{excerpt}...",
                            })
                            if len(results) >= max_results:
                                break
                    except Exception:
                        continue
                if len(results) >= max_results:
                    break

        return {"results": results, "count": len(results), "query": q}

    log.info("[skills] REST routes registered")
