"""
EMPIRE V49 · MESH SCRAPER WORKER (HERMES PROTOCOL)
===================================================
Polls agent_task_queue for scrape.web and scrape.crawl tasks assigned to
mesh.scraper, claims them atomically, executes via the hub's skill API
or direct firecrawl invocation, and updates task status.

Designed as a standalone PM2 process.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("/root/.env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mesh.scraper] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("mesh.scraper")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
HUB_URL = os.environ.get("EMPIRE_HUB_URL", "http://localhost:8001")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "dev-token-insecure")
POLL_INTERVAL = int(os.environ.get("MESH_SCRAPER_POLL_SEC", "60"))
AGENT_NAME = "mesh.scraper"

TASK_TYPES = ["scrape.web", "scrape.crawl"]


class MeshScraperWorker:
    """Poll Supabase agent_task_queue for scrape.* tasks and execute them."""

    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
            sys.exit(1)
        self.db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        self.running = True

    # ── Heartbeat ────────────────────────────────────────────────────

    def heartbeat(self) -> bool:
        """Register/ping in agent_registry table."""
        try:
            self.db.table("agent_registry").upsert({
                "agent_name": AGENT_NAME,
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": [
                    "scraper", "web", "extract", "crawl",
                ],
                "task_types": TASK_TYPES,
            }, on_conflict="agent_name").execute()
            return True
        except Exception as e:
            log.warning(f"Heartbeat failed: {e}")
            return False

    # ── Task claim ──────────────────────────────────────────────────

    def claim_task(self, ticket_id: str) -> bool:
        """Atomically claim a task by setting status to 'In Progress'.

        Returns True if we successfully claimed it (status was To-Do).
        Returns False if another worker already claimed it.
        """
        try:
            r = self.db.table("agent_task_queue").update({
                "status": "In Progress",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).eq("status", "To-Do").execute()
            return bool(r.data)
        except Exception as e:
            log.error(f"Claim failed for {ticket_id[:8]}: {e}")
            return False

    def complete_task(self, ticket_id: str, result: dict):
        """Mark a task as Done."""
        try:
            self.db.table("agent_task_queue").update({
                "status": "Done",
                "result": json.dumps(result, default=str),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).execute()
        except Exception as e:
            log.error(f"Failed to complete {ticket_id[:8]}: {e}")

    def fail_task(self, ticket_id: str, error: str):
        """Mark a task as Failed."""
        try:
            self.db.table("agent_task_queue").update({
                "status": "Failed",
                "error": str(error)[:2000],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).execute()
        except Exception as e:
            log.error(f"Failed to mark {ticket_id[:8]} as Failed: {e}")

    # ── Poll loop ───────────────────────────────────────────────────

    def find_next_task(self) -> dict | None:
        """Find the highest-priority To-Do task assigned to mesh.scraper."""
        try:
            r = self.db.table("agent_task_queue") \
                .select("*") \
                .eq("assigned_agent", AGENT_NAME) \
                .eq("status", "To-Do") \
                .order("priority", desc=True) \
                .order("created_at") \
                .limit(1) \
                .execute()
            return r.data[0] if r.data else None
        except Exception as e:
            log.error(f"Poll query failed: {e}")
            return None

    # ── Skill execution via hub ──────────────────────────────────────

    async def execute_skill_via_hub(self, skill_name: str, params: dict) -> dict:
        """Call the hub's /api/hermes/execute-skill endpoint."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{HUB_URL}/api/hermes/execute-skill",
                    json={
                        "skill_name": skill_name,
                        "params": params,
                    },
                    headers={"Authorization": f"Bearer {HUB_TOKEN}"},
                    timeout=120.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                return {
                    "ok": False,
                    "error": f"Hub returned {resp.status_code}: {resp.text[:300]}",
                }
        except httpx.ConnectError:
            return {"ok": False, "error": f"Hub not reachable at {HUB_URL}"}
        except httpx.TimeoutException:
            return {"ok": False, "error": "Hub request timed out after 120s"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:500]}

    # ── Direct firecrawl execution (fallback) ────────────────────────

    async def execute_firecrawl(self, url: str, action: str = "scrape", params: dict = None) -> dict:
        """Execute a web scrape directly via firecrawl if hub is unavailable."""
        params = params or {}
        try:
            if action == "scrape":
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        "http://localhost:3002/v1/scrape",
                        json={"url": url, "formats": params.get("formats", ["markdown", "text"])},
                        timeout=60.0,
                    )
                    if resp.status_code == 200:
                        return {"ok": True, "result": resp.json().get("data", {})}
                    return {"ok": False, "error": f"firecrawl HTTP {resp.status_code}"}
            elif action == "crawl":
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(
                        "http://localhost:3002/v1/crawl",
                        json={
                            "url": url,
                            "maxPages": params.get("max_pages", 10),
                            "formats": params.get("formats", ["markdown"]),
                        },
                        timeout=300.0,
                    )
                    if resp.status_code == 200:
                        return {"ok": True, "result": resp.json()}
                    return {"ok": False, "error": f"firecrawl HTTP {resp.status_code}"}
        except httpx.ConnectError:
            return {"ok": False, "error": "Firecrawl not reachable at localhost:3002"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:500]}

    # ── Process one task ────────────────────────────────────────────

    async def process_task(self, task: dict):
        """Claim and execute a single task."""
        ticket_id = task["ticket_id"]
        task_type = task["task_type"]
        raw_payload = task.get("payload", "{}")

        # Parse payload
        if isinstance(raw_payload, str):
            try:
                params = json.loads(raw_payload)
            except json.JSONDecodeError:
                params = {}
        elif isinstance(raw_payload, dict):
            params = raw_payload
        else:
            params = {}

        log.info(f"Claiming {ticket_id[:8]} — {task_type}")

        # Atomic claim
        if not self.claim_task(ticket_id):
            log.info(f"{ticket_id[:8]} already claimed elsewhere")
            return

        log.info(f"Executing {task_type}")

        # Try hub first, fall back to direct firecrawl
        result = await self.execute_skill_via_hub(task_type, params)

        # If hub failed (not running), try direct firecrawl
        if not result.get("ok") and "not reachable" in str(result.get("error", "")):
            url = params.get("url", "")
            action = "crawl" if task_type == "scrape.crawl" else "scrape"
            result = await self.execute_firecrawl(url, action, params)

        if result.get("ok"):
            self.complete_task(ticket_id, result.get("result", {}))
            log.info(f"{ticket_id[:8]} completed successfully")
        else:
            error = result.get("error", "Unknown error")
            self.fail_task(ticket_id, error)
            log.error(f"{ticket_id[:8]} failed: {error}")

    # ── Main loop ───────────────────────────────────────────────────

    async def run_loop(self):
        """Main polling loop — heartbeat, check for tasks, execute, sleep."""
        log.info(f"Starting (poll interval={POLL_INTERVAL}s, hub={HUB_URL})")

        # Initial heartbeat
        self.heartbeat()

        while self.running:
            try:
                # Heartbeat every cycle
                self.heartbeat()

                # Find and process next task
                task = self.find_next_task()
                if task:
                    await self.process_task(task)
                else:
                    await asyncio.sleep(1)

            except Exception as e:
                log.error(f"Loop error: {e}")

            await asyncio.sleep(POLL_INTERVAL)

    def stop(self):
        self.running = False
        log.info("Stopping")


if __name__ == "__main__":
    worker = MeshScraperWorker()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(worker.run_loop())
    except KeyboardInterrupt:
        worker.stop()
        log.info("mesh.scraper worker stopped")
