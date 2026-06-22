"""
EMPIRE V49 · PRODUCT: AGENT ORCHESTRATOR
=========================================
Autonomous agent lifecycle management — spawns agents, tracks task execution
via step-wise updates, runs local Ollama reasoning for next-step analysis.
Part of the Suite Gateway monetization.

Endpoints:
    POST /api/v6/agents/spawn       — spawn an autonomous agent with initial task
    POST /api/v6/agents/step-update — append execution record to active task
    GET  /api/v6/agents/stats       — agent lifecycle stats snapshot

Integration:
    orchestrator = AgentOrchestrator(suite_guard, log_usage_fn)
    result = await orchestrator.spawn(account_id, agent_name, niche, instruction)
"""
import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI

log = logging.getLogger("empire.product.agent_orchestrator")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"


class AgentOrchestrator:
    """Manage autonomous agent spawn, task execution, and lifecycle tracking.
    Each operation is gated by suite entitlement and metered for billing."""

    def __init__(
        self,
        guard: Optional[Callable] = None,      # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,  # SuiteGuard.log_usage
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {
            "spawned": 0,
            "tasks_completed": 0,
            "steps_logged": 0,
            "ollama_calls": 0,
            "errors": 0,
        }

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has the inbound_router feature enabled
        (agent orchestration is a premium automation product).
        In standalone mode (no guard), always grants access."""
        if not self.guard:
            return {"ok": True, "tier": "standalone"}
        if not account_id:
            return {"ok": False, "error": "customer_account_id required"}
        return self.guard(account_id, "inbound_router")

    # ── Local Ollama reasoning (async via httpx) ──────────────────────

    async def run_reasoning(self, prompt: str) -> str:
        """Run a local reasoning pass via Ollama to generate next-step actions.
        Falls back to a default step if the call fails."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "http://localhost:11434/api/chat",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": "llama3.2:3b",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an autonomous tactical agent. Output step actions clearly.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                if response.status_code < 300:
                    self.stats["ollama_calls"] += 1
                    data = response.json()
                    return data.get("message", {}).get("content", "")
                else:
                    log.warning(f"[agent-orch] Ollama error {response.status_code}: {response.text[:200]}")
                    self.stats["errors"] += 1
                    return "Fallback Step: Audit telephony log tables and check routing targets."
        except Exception as e:
            log.debug(f"[agent-orch] Ollama reasoning failed: {e}")
            self.stats["errors"] += 1
            return "Fallback Step: Audit telephony log tables and check routing targets."

    # ── Database helpers ──────────────────────────────────────────────

    def _get_conn(self):
        """Open a connection to the local SQLite suite database."""
        return sqlite3.connect(str(DB_PATH))

    # ── Spawn an autonomous agent ─────────────────────────────────────

    async def spawn(
        self,
        account_id: str,
        agent_name: str,
        assigned_niche: str,
        task_instruction: str,
    ) -> dict:
        """Spawn an autonomous agent: register in DB, create initial task,
        run first reasoning pass, and meter usage."""
        # 1. Entitlement
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["errors"] += 1
            return {
                "ok": False,
                "error": entitlement.get("error", "Access denied"),
                "step": "entitlement",
            }

        agent_id = "agent_" + str(uuid.uuid4())[:8]
        task_id = "task_" + str(uuid.uuid4())[:8]

        conn = self._get_conn()
        try:
            # Register agent state
            conn.execute(
                """INSERT INTO autonomous_agents
                   (agent_id, agent_name, assigned_niche, current_status)
                   VALUES (?, ?, ?, 'EXECUTING')""",
                (agent_id, agent_name.strip(), assigned_niche.strip()),
            )

            # Initialize task roadmap
            conn.execute(
                """INSERT INTO agent_task_ledger
                   (task_id, associated_agent_id, task_instruction, execution_log)
                   VALUES (?, ?, ?, 'Agent initialized to production server matrix.')""",
                (task_id, agent_id, task_instruction.strip()),
            )

            conn.commit()
        except Exception as e:
            conn.rollback()
            self.stats["errors"] += 1
            return {"ok": False, "error": f"Agent initialization blocked: {str(e)}"}
        finally:
            conn.close()

        # Run initial reasoning pass
        initial_analysis = await self.run_reasoning(task_instruction)

        # Persist the analysis
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE agent_task_ledger
                   SET execution_log = ?
                   WHERE task_id = ?""",
                (initial_analysis, task_id),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

        # Meter usage
        if self.log_usage:
            try:
                self.log_usage(
                    account_id,
                    "inbound_router",
                    "agent_spawn",
                    quantity=1,
                    metadata={
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "niche": assigned_niche,
                        "task_id": task_id,
                    },
                )
            except Exception:
                pass

        self.stats["spawned"] += 1
        return {
            "ok": True,
            "status": "AGENT_SPAWNED_AND_ROUTING",
            "account_id": account_id,
            "agent_id": agent_id,
            "active_task_id": task_id,
            "first_step_analysis": initial_analysis,
            "tier": entitlement.get("tier", "unknown"),
        }

    # ── Update agent step ─────────────────────────────────────────────

    async def step_update(
        self,
        account_id: str,
        task_id: str,
        agent_id: str,
        step_log: str,
        is_final: bool,
    ) -> dict:
        """Append an execution record to an agent's task history and manage
        lifecycle state (IDLE on final step, EXECUTING otherwise)."""
        # 1. Entitlement
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["errors"] += 1
            return {
                "ok": False,
                "error": entitlement.get("error", "Access denied"),
                "step": "entitlement",
            }

        status_marker = "IDLE" if is_final else "EXECUTING"
        conn = self._get_conn()
        try:
            # Append step to execution log and increment counters
            conn.execute(
                """UPDATE agent_task_ledger
                   SET execution_log = execution_log || '\n' || ?,
                       step_count = step_count + 1,
                       billing_cost_units = billing_cost_units + 0.0045,
                       completed_at = CASE WHEN ? = 1 THEN datetime('now') ELSE completed_at END
                   WHERE task_id = ?""",
                (step_log.strip(), 1 if is_final else 0, task_id),
            )

            # Update agent status and completion counter
            conn.execute(
                """UPDATE autonomous_agents
                   SET current_status = ?,
                       total_tasks_completed = total_tasks_completed + (CASE WHEN ? = 1 THEN 1 ELSE 0 END)
                   WHERE agent_id = ?""",
                (status_marker, 1 if is_final else 0, agent_id),
            )

            conn.commit()

            # Meter usage
            if self.log_usage:
                try:
                    self.log_usage(
                        account_id,
                        "inbound_router",
                        "agent_step",
                        quantity=1,
                        metadata={
                            "task_id": task_id,
                            "agent_id": agent_id,
                            "is_final": is_final,
                            "step_length": len(step_log),
                        },
                    )
                except Exception:
                    pass

            self.stats["steps_logged"] += 1
            if is_final:
                self.stats["tasks_completed"] += 1

            return {
                "ok": True,
                "status": "STATE_SYNCHRONIZED",
                "current_agent_status": status_marker,
                "tier": entitlement.get("tier", "unknown"),
            }

        except Exception as e:
            conn.rollback()
            self.stats["errors"] += 1
            return {"ok": False, "error": f"Step update failed: {str(e)}"}
        finally:
            conn.close()

    # ── Stats ─────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {**self.stats}


class AgentOrchestratorRoutes:
    """Wire AgentOrchestrator endpoints into the FastAPI app."""

    def __init__(self, orchestrator: AgentOrchestrator, require_auth: Optional[Callable] = None):
        self.orchestrator = orchestrator
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel

        class SpawnAgentPayload(BaseModel):
            customer_account_id: Optional[str] = "standalone_user"
            agent_name: str
            assigned_niche: str
            task_instruction: str

        class TaskStepUpdatePayload(BaseModel):
            customer_account_id: Optional[str] = "standalone_user"
            task_id: str
            agent_id: str
            step_log: str
            is_final: bool = False

        @app.post("/api/v6/agents/spawn")
        async def spawn_autonomous_agent(
            payload: SpawnAgentPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Spawn an autonomous agent, seed its core task, and register
            its execution state with an initial reasoning pass.

            Body: {
                customer_account_id: "client_alpha_operator",
                agent_name: "Storm Scout v3",
                assigned_niche: "commercial_roofing",
                task_instruction: "Scan NWS alerts for zip codes in Dallas-Fort Worth metro"
            }
            """
            # Use default if customer_account_id is None/null
            account_id = (payload.customer_account_id or "standalone_user").strip()
            result = await self.orchestrator.spawn(
                account_id=account_id,
                agent_name=payload.agent_name.strip(),
                assigned_niche=payload.assigned_niche.strip(),
                task_instruction=payload.task_instruction.strip(),
            )
            status = 403 if result.get("step") == "entitlement" else (
                201 if result.get("ok") else 400
            )
            return JSONResponse(result, status_code=status)

        @app.post("/api/v6/agents/step-update")
        async def update_agent_step(
            payload: TaskStepUpdatePayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Append an execution record to an agent's history and manage
            lifecycle states.

            Body: {
                customer_account_id: "client_alpha_operator",
                task_id: "task_a1b2c3d4",
                agent_id: "agent_e5f6g7h8",
                step_log: "Found 12 new NWS alerts for ZIP 75201",
                is_final: false
            }
            """
            # Use default if customer_account_id is None/null
            account_id = (payload.customer_account_id or "standalone_user").strip()
            result = await self.orchestrator.step_update(
                account_id=account_id,
                task_id=payload.task_id.strip(),
                agent_id=payload.agent_id.strip(),
                step_log=payload.step_log.strip(),
                is_final=payload.is_final,
            )
            status = 403 if result.get("step") == "entitlement" else (
                200 if result.get("ok") else 400
            )
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/agents/stats")
        async def agent_orchestrator_stats(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Agent Orchestrator lifecycle stats."""
            return JSONResponse(self.orchestrator.snapshot())

        log.info("[agent-orch] Routes registered · /api/v6/agents/*")


# ═════════════════════════════════════════════════════════════════════════
# STANDALONE APP (uvicorn port 8042)
# ═════════════════════════════════════════════════════════════════════════


def create_standalone_app() -> FastAPI:
    """Create a standalone FastAPI app with the agent orchestrator routes.
    No suite guard in standalone mode."""
    standalone = FastAPI(
        title="Empire AI · Agent Orchestrator", version="1.0.0"
    )

    from fastapi.middleware.cors import CORSMiddleware

    standalone.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    orchestrator = AgentOrchestrator()
    AgentOrchestratorRoutes(orchestrator).register(standalone)

    @standalone.get("/")
    async def root():
        return {
            "service": "Empire AI Agent Orchestrator",
            "version": "1.0.0",
            "endpoints": [
                "POST /api/v6/agents/spawn",
                "POST /api/v6/agents/step-update",
                "GET  /api/v6/agents/stats",
            ],
        }

    return standalone


app = create_standalone_app()

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("AGENT_ORCH_PORT", "8042"))
    host = os.environ.get("AGENT_ORCH_HOST", "0.0.0.0")
    log.info(f"[agent-orch] Starting standalone on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
