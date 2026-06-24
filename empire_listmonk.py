"""
EMPIRE V49 · LISTMONK INTEGRATION
===================================
Hub routes for the self-hosted ListMonk email campaign manager.

Provides API endpoints for:
  - Status: docker health, subscriber count, list count, campaign stats
  - Sync: trigger contractor → ListMonk subscriber import
  - Lists: list all subscriber lists with counts
  - Campaign: create and send campaigns

Wired into hub.py:
    from empire_listmonk import register_listmonk_routes
    register_listmonk_routes(app, require_auth=require_auth)
"""

import os
import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query

log = logging.getLogger("empire.listmonk")

LISTMONK_URL = "http://localhost:9000"
PSQL_EXEC = ["docker", "exec", "-t", "listmonk-db", "psql", "-U", "listmonk", "-d", "listmonk", "-c"]


def _sql(query: str) -> str:
    """Run SQL on ListMonk DB. Returns stdout or empty string on failure."""
    try:
        result = subprocess.run(
            PSQL_EXEC + [query],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=10,
        )
        return result.stdout
    except Exception as e:
        log.debug(f"[listmonk] SQL failed: {e}")
        return ""


def _listmonk_health() -> dict:
    """Check if ListMonk containers are running and DB is reachable."""
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=5,
    )
    containers = {}
    for line in out.stdout.strip().split("\n"):
        if "\t" in line:
            name, status = line.split("\t", 1)
            containers[name] = status

    db_ok = "listmonk-db" in containers
    app_ok = "listmonk-q" in containers
    db_reachable = "1" in _sql("SELECT 1;") if db_ok else False

    return {
        "container_db": {"running": db_ok, "name": "listmonk-db"},
        "container_app": {"running": app_ok, "name": "listmonk-q", "port": 9000},
        "db_reachable": db_reachable,
        "healthy": all([db_ok, app_ok, db_reachable]),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _subscriber_count() -> int:
    """Get total enabled subscribers."""
    out = _sql("SELECT COUNT(*) FROM subscribers WHERE status = 'enabled';")
    for line in out.split("\n"):
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


def _list_summary() -> list:
    """Get all lists with subscriber counts."""
    out = _sql(
        "SELECT l.id, l.name, l.type, COUNT(sl.subscriber_id) as cnt "
        "FROM lists l LEFT JOIN subscriber_lists sl ON l.id = sl.list_id "
        "AND sl.status = 'confirmed' GROUP BY l.id, l.name, l.type ORDER BY l.name;"
    )
    lists = []
    for line in out.split("\n"):
        parts = line.strip().split("|")
        if len(parts) >= 4:
            try:
                lists.append({
                    "id": int(parts[0].strip()),
                    "name": parts[1].strip(),
                    "type": parts[2].strip(),
                    "subscribers": int(parts[3].strip()),
                })
            except (ValueError, IndexError):
                continue
    return lists


def _campaign_summary() -> list:
    """Get recent campaigns with send stats."""
    out = _sql(
        "SELECT c.id, c.name, c.subject, c.status, c.sent_at, "
        "COALESCE(c.stats->>'views', '0') as views, "
        "COALESCE(c.stats->>'clicks', '0') as clicks "
        "FROM campaigns c ORDER BY c.created_at DESC LIMIT 20;"
    )
    campaigns = []
    for line in out.split("\n"):
        parts = line.strip().split("|")
        if len(parts) >= 5:
            try:
                campaigns.append({
                    "id": int(parts[0].strip()),
                    "name": parts[1].strip(),
                    "subject": parts[2].strip(),
                    "status": parts[3].strip(),
                    "sent_at": parts[4].strip() if parts[4].strip() else None,
                    "views": int(parts[5].strip()) if len(parts) > 5 else 0,
                    "clicks": int(parts[6].strip()) if len(parts) > 6 else 0,
                })
            except (ValueError, IndexError):
                continue
    return campaigns


def register_listmonk_routes(app, require_auth=None):
    """Register ListMonk management endpoints on the FastAPI app."""

    @app.get("/api/v1/listmonk/status")
    async def listmonk_status(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return ListMonk health: containers, DB, subscriber count, lists."""
        health = _listmonk_health()

        if not health["healthy"]:
            return {
                "ok": True,
                "healthy": False,
                "health": health,
                "note": "ListMonk not running. Run: ./scripts/deploy_crms.sh --listmonk-only",
            }

        return {
            "ok": True,
            "healthy": True,
            "health": health,
            "subscribers": _subscriber_count(),
            "lists": len(_list_summary()),
            "url": f"{LISTMONK_URL}/admin",
        }

    @app.get("/api/v1/listmonk/lists")
    async def listmonk_lists(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return all subscriber lists with counts."""
        health = _listmonk_health()
        if not health["healthy"]:
            return {"ok": False, "error": "ListMonk not running"}

        lists = _list_summary()
        return {"ok": True, "lists": lists, "count": len(lists)}

    @app.get("/api/v1/listmonk/campaigns")
    async def listmonk_campaigns(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return recent campaigns with send stats."""
        health = _listmonk_health()
        if not health["healthy"]:
            return {"ok": False, "error": "ListMonk not running"}

        campaigns = _campaign_summary()
        return {"ok": True, "campaigns": campaigns, "count": len(campaigns)}

    @app.post("/api/v1/listmonk/sync")
    async def listmonk_sync(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Trigger a contractor → ListMonk subscriber sync.

        Runs scripts/import_listmonk.py and returns the results.
        """
        health = _listmonk_health()
        if not health["healthy"]:
            return {"ok": False, "error": "ListMonk not running — cannot sync"}

        import time
        t0 = time.time()

        try:
            result = subprocess.run(
                ["python3", "/root/empire-v49/scripts/sync_listmonk.py"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=120,
                cwd="/root/empire-v49",
            )
            duration_ms = (time.time() - t0) * 1000

            return {
                "ok": result.returncode == 0,
                "output": result.stdout.strip()[-1000:],
                "duration_ms": duration_ms,
                "subscribers_after": _subscriber_count(),
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Sync timed out (120s)"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    log.info("[listmonk.routes] REST routes registered (4 endpoints)")
