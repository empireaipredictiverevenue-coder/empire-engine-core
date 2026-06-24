"""
EMPIRE V49 · RESEND API EMAIL SENDER
=====================================
Direct HTTP API sender for Resend email, bypassing ListMonk's broken
SMTP implementation. ListMonk is kept for subscriber/list management,
but all actual email sending goes through Resend's REST API directly.

Provides:
  - POST /api/v1/resend/send — send a single email via Resend API
  - GET  /api/v1/resend/health — check Resend API key + domain status

Wired into hub.py:
    from empire_resend_sender import register_resend_sender_routes
    register_resend_sender_routes(app, require_auth=require_auth)
"""

import os
import logging
from datetime import datetime, timezone
from typing import List, Optional, Union

import httpx
from fastapi import Body, Depends, HTTPException

log = logging.getLogger("empire.resend_sender")

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_DOMAIN = "empire-ai.co.uk"


def _api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "")


def register_resend_sender_routes(app, require_auth=None):
    """Register Resend API email sender endpoints on the FastAPI app."""

    @app.get("/api/v1/resend/health")
    async def resend_health(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Check Resend API key health and domain verification status.

        Returns:
          - api_key_set: bool
          - domain: name and status (verified/not_found/error)
          - records: DNS record breakdown (DKIM, SPF, MX, Tracking)
          - healthy: true if API key is set AND domain is verified
        """
        key = _api_key()
        if not key:
            return {"healthy": False, "api_key_set": False, "error": "RESEND_API_KEY not set"}

        try:
            # Check domain status
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://api.resend.com/domains",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if r.status_code != 200:
                    return {
                        "healthy": False,
                        "api_key_set": True,
                        "error": f"Resend API returned HTTP {r.status_code}",
                        "body": r.text[:200],
                    }

                domains = r.json().get("data", [])
                our = next((d for d in domains if d.get("name") == RESEND_DOMAIN), None)
                if not our:
                    return {
                        "healthy": False,
                        "api_key_set": True,
                        "domain": {"name": RESEND_DOMAIN, "status": "not_found"},
                        "error": f"Domain {RESEND_DOMAIN} not found in Resend account",
                    }

                # Fetch detail with records
                dr = await client.get(
                    f"https://api.resend.com/domains/{our['id']}",
                    headers={"Authorization": f"Bearer {key}"},
                )
                detail = dr.json() if dr.status_code == 200 else {}
                records = detail.get("records", [])
                record_statuses = {}
                for rec in records:
                    rname = rec.get("record", rec.get("name", "?"))
                    rstatus = rec.get("status", "unknown")
                    rtype = rec.get("type", "?")
                    record_statuses[f"{rtype}:{rname}"] = rstatus

                domain_status = detail.get("status", our.get("status", "unknown"))

                return {
                    "healthy": domain_status == "verified",
                    "api_key_set": True,
                    "domain": {
                        "name": RESEND_DOMAIN,
                        "id": our["id"],
                        "status": domain_status,
                        "region": detail.get("region", ""),
                        "open_tracking": detail.get("open_tracking", False),
                        "click_tracking": detail.get("click_tracking", False),
                    },
                    "records": {
                        "total": len(records),
                        "verified": sum(1 for r in records if r.get("status") == "verified"),
                        "details": record_statuses,
                    },
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
        except httpx.HTTPError as e:
            return {"healthy": False, "api_key_set": True, "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"healthy": False, "api_key_set": True, "error": str(e)}

    @app.post("/api/v1/resend/send")
    async def resend_send(
        to: Union[str, List[str]] = Body(..., description="Recipient email(s)"),
        subject: str = Body(..., description="Email subject line"),
        html: Optional[str] = Body(None, description="HTML body"),
        text: Optional[str] = Body(None, description="Plain text body"),
        from_name: Optional[str] = Body(None, description="Sender name override"),
        tags: Optional[List[dict]] = Body(None, description="Tags e.g. [{'name':'campaign','value':'welcome'}]"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Send an email via the Resend HTTP API directly.

        Bypasses ListMonk SMTP entirely. Uses Resend's REST API which
        handles TLS, authentication, and delivery — no Go net/smtp issues.

        Args:
          to: Recipient email address (string)
          subject: Email subject line
          html: HTML body (optional if text is provided)
          text: Plain text body (optional if html is provided)
          from_name: Optional sender name override (default: 'Empire AI')
          tags: Optional list of tag dicts, e.g. [{"name": "campaign", "value": "welcome"}]

        Returns:
          {ok, id, error?}
        """
        key = _api_key()
        if not key:
            return {"ok": False, "id": None, "error": "RESEND_API_KEY not set"}

        if not html and not text:
            return {"ok": False, "id": None, "error": "Either html or text body is required"}

        # Normalize 'to' to a list and validate
        if isinstance(to, str):
            to_list = [to]
        else:
            to_list = to
        if not to_list or not any("@" in addr for addr in to_list):
            return {"ok": False, "id": None, "error": "At least one valid recipient email required"}

        if not subject:
            return {"ok": False, "id": None, "error": "Subject is required"}

        from_addr = f"{from_name or 'Empire AI'} <ops@{RESEND_DOMAIN}>"

        payload = {
            "from": from_addr,
            "to": to_list,
            "subject": subject,
        }
        if html:
            payload["html"] = html
        if text:
            payload["text"] = text
        if tags:
            payload["tags"] = tags

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    RESEND_API_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                ok = r.status_code < 300

                if ok:
                    log.info(f"[resend-sender] sent to {to}: subject='{subject[:60]}' id={data.get('id', '?')}")
                else:
                    log.warning(f"[resend-sender] failed to {to}: HTTP {r.status_code} {data.get('error', data.get('message', '?'))}")

                return {
                    "ok": ok,
                    "id": data.get("id"),
                    "status_code": r.status_code,
                    "error": data.get("error") or data.get("message") if not ok else None,
                }
        except httpx.HTTPError as e:
            log.warning(f"[resend-sender] HTTP error for {to}: {e}")
            return {"ok": False, "id": None, "error": f"HTTP error: {e}"}
        except Exception as e:
            log.warning(f"[resend-sender] error for {to}: {e}")
            return {"ok": False, "id": None, "error": str(e)}

    log.info("[resend-sender.routes] REST routes registered (2 endpoints)")
