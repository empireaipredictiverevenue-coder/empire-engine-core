"""
EMPIRE V49 · TWENTY CRM INTEGRATION
=====================================
Hub routes and sync for the self-hosted Twenty CRM (pipeline management).

Provides API endpoints for:
  - Status: docker health, instance URL, workspace info
  - Sync: import contractors into Twenty as companies/contacts
  - Pipeline: query deals, stages, and pipeline stats

Twenty runs on localhost:3003 via Docker Compose (scripts/deploy_crms.sh).
API auth is via JWT bearer token (obtained on first admin login).

Wired into hub.py:
    from empire_twenty_crm import register_twenty_crm_routes
    register_twenty_crm_routes(app, require_auth=require_auth)
"""

import os
import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Query

log = logging.getLogger("empire.twenty_crm")

TWENTY_URL = "http://localhost:3003"
TWENTY_DEPLOY_DIR = "/root/deploy/twenty-crm"


def _twenty_health() -> dict:
    """Check if Twenty containers are running."""
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

    server_ok = any("twenty" in name and "server" in name for name in containers)
    db_ok = any("twenty" in name and ("db" in name or "postgres" in name.lower()) for name in containers)
    worker_ok = any("twenty" in name and "worker" in name for name in containers)

    # Check API health endpoint
    api_ok = False
    try:
        import httpx as _httpx
        with _httpx.Client(timeout=5) as client:
            r = client.get(f"{TWENTY_URL}/healthz")
            api_ok = r.status_code == 200
    except Exception:
        pass

    return {
        "containers": {
            "server": server_ok,
            "database": db_ok,
            "worker": worker_ok,
        },
        "api_reachable": api_ok,
        "healthy": all([server_ok, db_ok, api_ok]),
        "url": TWENTY_URL,
        "deploy_dir": TWENTY_DEPLOY_DIR,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _get_twenty_token() -> Optional[str]:
    """Try to read Twenty API token from environment or cached file."""
    token = os.getenv("TWENTY_API_TOKEN", "")
    if token:
        return token
    token_file = os.path.expanduser("~/.twenty_token")
    if os.path.exists(token_file):
        try:
            with open(token_file) as f:
                token = f.read().strip()
                if token:
                    return token
        except Exception:
            pass
    return None


def register_twenty_crm_routes(app, require_auth=None):
    """Register Twenty CRM management endpoints on the FastAPI app."""

    @app.get("/api/v1/twenty/status")
    async def twenty_status(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return Twenty CRM health: containers, API reachability, URL."""
        health = _twenty_health()

        return {
            "ok": True,
            "healthy": health["healthy"],
            "health": health,
            "token_configured": bool(_get_twenty_token()),
            "note": (
                "Twenty is running" if health["healthy"]
                else "Twenty not running. Run: ./scripts/deploy_crms.sh --twenty-only"
            ),
        }

    @app.post("/api/v1/twenty/configure")
    async def twenty_configure(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Configure Twenty API token and workspace info.

        Body:
          api_token: str (required) — Twenty API bearer token
          workspace_id: str (optional) — Twenty workspace ID
        """
        api_token = body.get("api_token", "").strip()
        if not api_token:
            raise HTTPException(400, "Missing required field: api_token")

        # Save token
        token_file = os.path.expanduser("~/.twenty_token")
        try:
            with open(token_file, "w") as f:
                f.write(api_token)
            os.chmod(token_file, 0o600)
        except Exception as e:
            return {"ok": False, "error": f"Failed to save token: {e}"}

        # Update .env
        env_file = "/root/.env"
        try:
            with open(env_file, "r") as f:
                lines = f.readlines()
            found = False
            for i, line in enumerate(lines):
                if line.startswith("TWENTY_API_TOKEN="):
                    lines[i] = f"TWENTY_API_TOKEN={api_token}\n"
                    found = True
                    break
            if not found:
                lines.append(f"\nTWENTY_API_TOKEN={api_token}\n")
            with open(env_file, "w") as f:
                f.writelines(lines)
        except Exception as e:
            log.warning(f"[twenty] env update failed: {e}")

        # Verify token works
        health = _twenty_health()
        if health["api_reachable"]:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(
                        f"{TWENTY_URL}/rest/workspaces",
                        headers={"Authorization": f"Bearer {api_token}"},
                    )
                    workspaces = r.json() if r.status_code < 400 else None
            except Exception:
                workspaces = None
        else:
            workspaces = None

        return {
            "ok": True,
            "token_saved": True,
            "workspaces": workspaces,
            "note": "Token configured. Use /api/v1/twenty/sync to import contractors.",
        }

    @app.post("/api/v1/twenty/sync")
    async def twenty_sync(
        body: dict = None,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Import Empire AI contractors into Twenty as companies/contacts.

        Fetches active contractors from Supabase and creates them as
        companies in Twenty with name, email, phone, metro, and custom fields.
        Requires TWENTY_API_TOKEN to be configured.
        """
        token = _get_twenty_token()
        if not token:
            return {
                "ok": False,
                "error": "TWENTY_API_TOKEN not configured. "
                         "POST to /api/v1/twenty/configure with your token first.",
                "help": "Get your token from Twenty: Settings → API → Generate Token",
            }

        health = _twenty_health()
        if not health["api_reachable"]:
            return {"ok": False, "error": "Twenty API not reachable"}

        # Fetch contractors from Supabase
        try:
            from supabase import create_client
            sb = create_client(
                os.getenv("SUPABASE_URL", ""),
                os.getenv("SUPABASE_SERVICE_KEY", ""),
            )
            r = sb.table("contractors").select(
                "id,name,email,phone,metro,solana_wallet,active,created_at"
            ).eq("active", True).limit(500).execute()
            contractors = r.data or []
        except Exception as e:
            return {"ok": False, "error": f"Supabase query failed: {e}"}

        imported = 0
        errors = 0
        results = []

        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            for c in contractors:
                name = c.get("name", "").strip()
                email = c.get("email", "").strip()
                phone = c.get("phone", "").strip()
                metro = c.get("metro", "").strip()

                if not name or "@" not in (email or ""):
                    continue

                try:
                    # Create company in Twenty
                    company_payload = {
                        "name": name,
                        "domainName": email.split("@")[1] if "@" in email else "",
                        "address": metro,
                        "employees": 1,
                    }
                    r = await client.post(
                        f"{TWENTY_URL}/rest/companies",
                        headers=headers,
                        json=company_payload,
                    )
                    if r.status_code < 400:
                        company_data = r.json()
                        company_id = company_data.get("data", {}).get("company", {}).get("id", "")

                        # Create person (contact) linked to company
                        if company_id:
                            person_payload = {
                                "name": {"firstName": name.split()[0] if name.split() else name,
                                         "lastName": " ".join(name.split()[1:]) if len(name.split()) > 1 else ""},
                                "email": email,
                                "phone": phone,
                                "companyId": company_id,
                            }
                            await client.post(
                                f"{TWENTY_URL}/rest/people",
                                headers=headers,
                                json=person_payload,
                            )

                        imported += 1
                        results.append({"name": name, "email": email, "status": "imported"})
                    else:
                        errors += 1
                        results.append({"name": name, "status": "error", "detail": r.text[:100]})

                except Exception as e:
                    errors += 1
                    results.append({"name": name, "status": "error", "detail": str(e)[:100]})

        return {
            "ok": True,
            "total": len(contractors),
            "valid": len([c for c in contractors if c.get("name", "").strip() and "@" in (c.get("email") or "")]),
            "imported": imported,
            "errors": errors,
            "results": results[:20],
        }

    @app.get("/api/v1/twenty/workspaces")
    async def twenty_workspaces(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List available Twenty workspaces."""
        token = _get_twenty_token()
        if not token:
            return {"ok": False, "error": "TWENTY_API_TOKEN not configured"}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{TWENTY_URL}/rest/workspaces",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if r.status_code < 400:
                    return {"ok": True, "workspaces": r.json()}
                return {"ok": False, "error": f"HTTP {r.status_code}", "detail": r.text[:200]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    log.info("[twenty_crm.routes] REST routes registered (4 endpoints)")
