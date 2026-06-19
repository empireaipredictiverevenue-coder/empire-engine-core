"""
Event emitter for cron agents.

Replaces direct ``sb.table("agent_activity").insert(...)`` calls with event
bus emissions via the hub's ``POST /api/v1/events/emit`` endpoint. Falls
back to direct ``agent_activity`` insert if the hub is unreachable (so cron
agents are never blocked by a hub restart).

Usage::

    from agents.event_emitter import emit_agent_event

    emit_agent_event(
        sb=sb,
        agent_name="lead_scanner",
        run_id=run_id,
        started_at=started_at,
        status="ok",
        rows_seen=10,
        rows_processed=5,
        rows_errored=0,
        summary="scan complete",
    )
"""
import os
import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("empire.event_emitter")


def _hub_base() -> str:
    return os.getenv("HUB_URL", "http://127.0.0.1:8001").rstrip("/")


def _hub_token() -> str:
    return os.getenv("HUB_TOKEN", "") or os.getenv("HUB_API_KEY", "")


def emit_agent_event(
    sb: Any,
    agent_name: str,
    run_id: Any,
    started_at: datetime,
    status: str,
    rows_seen: int = 0,
    rows_processed: int = 0,
    rows_blocked: int = 0,
    rows_errored: int = 0,
    error: Optional[str] = None,
    summary: Optional[str] = None,
) -> str:
    """
    Emit an agent run event via the hub's event bus.

    **Primary path:** POST to ``/api/v1/events/emit`` on the hub.
    The hub's background persistence loop writes the event to the
    ``agent_activity`` table asynchronously (every 5s batch).

    **Fallback path:** Direct ``agent_activity`` insert via Supabase when
    the hub is unreachable — ensures cron agents are never blocked by a
    hub restart.

    Returns the ``finished_at`` ISO-8601 string.
    """
    finished_at = datetime.now(timezone.utc).isoformat()

    event_payload = {
        "event_type": f"agent.{agent_name}.run",
        "source": agent_name,
        "severity": (
            "error"
            if status in ("error",)
            else "warn"
            if status in ("partial", "ok_with_errors")
            else "info"
        ),
        "data": {
            "run_id": str(run_id),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at,
            "status": status,
            "rows_seen": rows_seen,
            "rows_processed": rows_processed,
            "rows_blocked": rows_blocked,
            "rows_errored": rows_errored,
            "error": error,
            "summary": summary,
        },
    }

    # ── Primary: POST to the hub's event bus ──────────────────────────
    hub_url = _hub_base()
    hub_token = _hub_token()
    if hub_url and hub_token:
        try:
            url = f"{hub_url}/api/v1/events/emit"
            data = json.dumps(event_payload).encode()
            req = urllib.request.Request(
                url,
                data=data,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {hub_token}",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    log.debug(
                        "[event_emitter] emitted %s via hub",
                        event_payload["event_type"],
                    )
                    return finished_at
                log.warning(
                    "[event_emitter] hub returned %s, falling back to agent_activity",
                    resp.status,
                )
        except Exception as exc:
            log.warning(
                "[event_emitter] hub unreachable (%s), falling back to agent_activity",
                exc,
            )

    # ── Fallback: direct Supabase insert ──────────────────────────────
    try:
        sb.table("agent_activity").insert(
            {
                "agent_name": agent_name,
                "run_id": str(run_id),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at,
                "status": status,
                "rows_seen": rows_seen,
                "rows_processed": rows_processed,
                "rows_blocked": rows_blocked,
                "rows_errored": rows_errored,
                "error": error,
                "summary": summary,
            }
        ).execute()
    except Exception as exc:
        log.warning("[event_emitter] agent_activity insert also failed: %s", exc)

    return finished_at
