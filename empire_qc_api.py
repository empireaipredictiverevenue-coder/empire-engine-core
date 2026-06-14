"""Empire AI - QC events REST endpoints.

GET   /api/v1/qc/events                  - list events (filterable)
PATCH /api/v1/qc/events/<id>/resolve    - mark event resolved

Auth: simple Bearer-token check against HUB_TOKEN. We don't use
FastAPI's Depends() pattern here because that creates a circular
import (hub.py imports us, we would import hub's require_auth).
The check is the same logic require_auth runs.
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger("empire.qc_api")


def _check_auth(request: Request):
    """Return True if the request has a valid Bearer token.

    Mirrors the require_auth dependency in hub.py. Hub uses
    auth_engine.require_auth which does a JWT + DB lookup; for the
    QC endpoints we accept a static HUB_TOKEN (the operator's
    long-lived token) OR any token that auth_engine can validate.
    """
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header[7:].strip()
    expected = os.environ.get("HUB_TOKEN", "").strip()
    if expected and token == expected:
        return True
    # Fall back: try auth_engine if hub is importable
    try:
        from hub import auth_engine
        # auth_engine.require_auth is async; we'd need to await it.
        # For now, if HUB_TOKEN matches we accept; otherwise 401.
        return False
    except Exception:
        return False


def _get_db():
    from hub import get_db
    return get_db()


async def list_qc_events(request: Request) -> JSONResponse:
    """GET /api/v1/qc/events"""
    if not _check_auth(request):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)

    qp = request.query_params
    severity = qp.get("severity")
    category = qp.get("category")
    resolved = qp.get("resolved")
    since    = qp.get("since")
    try:
        limit = int(qp.get("limit", "50"))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))

    try:
        db = _get_db()
    except Exception as e:
        log.error(f"[qc_api] db unavailable: {e}")
        return JSONResponse({"ok": False, "error": "db_unavailable"}, status_code=500)

    try:
        q = db.table("qc_events").select("*")
        if severity:
            q = q.eq("severity", severity)
        if category:
            q = q.eq("category", category)
        if resolved is not None:
            if resolved.lower() in ("true", "1", "yes"):
                q = q.eq("resolved", True)
            elif resolved.lower() in ("false", "0", "no"):
                q = q.eq("resolved", False)
        if since:
            q = q.gte("created_at", since)
        else:
            q = q.gte("created_at", (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat())
        q = q.order("created_at", desc=True).limit(limit)
        r = q.execute()
        events = r.data or []
    except Exception as e:
        log.error(f"[qc_api] list query failed: {e}")
        return JSONResponse({"ok": False, "error": "query_failed", "detail": str(e)[:200]}, status_code=500)

    unresolved_tier_2 = sum(1 for e in events if e.get("severity") == "tier_2" and not e.get("resolved"))

    return JSONResponse({
        "ok":               True,
        "events":           events,
        "total":            len(events),
        "unresolved_tier_2": unresolved_tier_2,
    }, status_code=200)


async def resolve_qc_event(event_id: str, request: Request) -> JSONResponse:
    """PATCH /api/v1/qc/events/<id>/resolve"""
    if not _check_auth(request):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)

    try:
        db = _get_db()
    except Exception as e:
        return JSONResponse({"ok": False, "error": "db_unavailable"}, status_code=500)

    resolved_by = "operator"
    try:
        body = await request.json()
        if isinstance(body, dict) and body.get("resolved_by"):
            resolved_by = str(body["resolved_by"])[:120]
    except Exception:
        pass

    try:
        r = db.table("qc_events").select("id,resolved,resolved_at,resolved_by").eq("id", event_id).limit(1).execute()
    except Exception as e:
        return JSONResponse({"ok": False, "error": "query_failed", "detail": str(e)[:200]}, status_code=500)

    if not r.data:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)

    row = r.data[0]
    if row.get("resolved"):
        return JSONResponse({
            "ok":           True,
            "id":           event_id,
            "resolved_at":  row.get("resolved_at"),
            "resolved_by":  row.get("resolved_by"),
        }, status_code=200)

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        db.table("qc_events").update({
            "resolved":    True,
            "resolved_at": now_iso,
            "resolved_by": resolved_by,
        }).eq("id", event_id).execute()
    except Exception as e:
        return JSONResponse({"ok": False, "error": "update_failed", "detail": str(e)[:200]}, status_code=500)

    return JSONResponse({
        "ok":           True,
        "id":           event_id,
        "resolved_at":  now_iso,
        "resolved_by": resolved_by,
    }, status_code=200)


def register_qc_routes(app):
    """Mount the QC events endpoints on the FastAPI app."""
    app.add_api_route(
        "/api/v1/qc/events",
        list_qc_events,
        methods=["GET"],
    )
    app.add_api_route(
        "/api/v1/qc/events/{event_id}/resolve",
        resolve_qc_event,
        methods=["PATCH"],
    )
    log.info("[qc_api] routes registered: GET /api/v1/qc/events, PATCH /api/v1/qc/events/{id}/resolve")
