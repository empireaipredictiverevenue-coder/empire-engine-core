"""
EMPIRE V49 · DATA BRIDGE ENGINE
================================
Ingests external payloads from automated triggers, scraper arrays, or
partner webhooks. Stores to local SQLite for durability, then processes
asynchronously into the Empire pipeline (inbound leads, storm alerts).

Route pattern (matches other empire_* modules):
    register_bridge_routes(app, ..., require_auth=...)

Endpoint:
    POST /api/v6/bridge/receive  — ingest external payload (public, auth via token)

Background loop:
    _bridge_processor_loop()     — polls unprocessed webhooks, forwards to Supabase
"""

import json as _json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

log = logging.getLogger("empire.bridge")

# ── Config ────────────────────────────────────────────────────────────
DB_PATH = Path(os.environ.get("BRIDGE_DB_PATH", "/root/empire-v49/data/storm_alerts.sqlite"))
BRIDGE_SECRET = os.environ.get("BRIDGE_SECRET", "")
PROCESSOR_INTERVAL_SEC = int(os.environ.get("BRIDGE_PROCESSOR_INTERVAL_SEC", "30"))
MAX_WEBHOOK_AGE_HOURS = int(os.environ.get("BRIDGE_MAX_WEBHOOK_AGE_HOURS", "72"))


# ── DB Init ───────────────────────────────────────────────────────────
def init_bridge_db():
    """Create the system_webhooks table if it doesn't exist.

    Lives in the same SQLite DB as storm_alerts (no conflict — different
    table name). File location is set by BRIDGE_DB_PATH env var.
    """
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_webhooks (
                event_id          TEXT PRIMARY KEY,
                event_type        TEXT,
                source_platform   TEXT,
                raw_payload       TEXT,
                processed_status  INTEGER DEFAULT 0,
                error             TEXT,
                timestamp         TEXT DEFAULT (datetime('now'))
            )
        """)
        # Index for the processor loop (unprocessed, ordered by age)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_system_webhooks_unprocessed
            ON system_webhooks (processed_status, timestamp)
        """)
        conn.commit()
        conn.close()
        log.info(f"[bridge] DB ready at {DB_PATH} (system_webhooks table)")
    except Exception as e:
        log.error(f"[bridge] DB init failed: {e}")


# ── Storage ───────────────────────────────────────────────────────────
def _store_webhook(event_id: str, event_type: str, source: str, payload: dict) -> dict:
    """Insert one webhook event into SQLite. Returns the stored row."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO system_webhooks
               (event_id, event_type, source_platform, raw_payload)
               VALUES (?, ?, ?, ?)""",
            (event_id, event_type, source, _json.dumps(payload)),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "event_id": event_id}
    except Exception as e:
        log.error(f"[bridge] store failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def _fetch_unprocessed(limit: int = 20) -> list[dict]:
    """Return up to `limit` unprocessed webhook rows, oldest first."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT event_id, event_type, source_platform, raw_payload, timestamp "
            "FROM system_webhooks "
            "WHERE processed_status = 0 "
            "ORDER BY timestamp ASC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log.warning(f"[bridge] fetch_unprocessed failed: {e}")
        return []


def _mark_processed(event_id: str, error: str = ""):
    """Mark a webhook as processed, optionally recording an error."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        if error:
            cursor.execute(
                "UPDATE system_webhooks SET processed_status = 2, error = ? WHERE event_id = ?",
                (error[:500], event_id),
            )
        else:
            cursor.execute(
                "UPDATE system_webhooks SET processed_status = 1 WHERE event_id = ?",
                (event_id,),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"[bridge] mark_processed failed: {e}")


def _count_by_status() -> dict:
    """Return counts of webhooks by processed_status."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT processed_status, count(*) FROM system_webhooks GROUP BY processed_status"
        )
        counts = {str(r[0]): r[1] for r in cursor.fetchall()}
        conn.close()
        return {
            "pending": int(counts.get("0", 0)),
            "processed": int(counts.get("1", 0)),
            "errored": int(counts.get("2", 0)),
            "total": sum(int(v) for v in counts.values()),
        }
    except Exception:
        return {"pending": 0, "processed": 0, "errored": 0, "total": 0}


# ── Processing: Ensure customer_profiles table exists ───────────────
def _ensure_customer_profiles_table():
    """Create the customer_profiles table if it doesn't exist.

    Schema matches database/pay_per_call_schema.sql. Runs on startup
    alongside init_bridge_db() so the processor loop always has a
    target table.
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_profiles (
                profile_id            TEXT PRIMARY KEY,
                associated_call_id    TEXT NOT NULL,
                phone_number          TEXT NOT NULL,
                niche_category        TEXT NOT NULL,
                lead_retention_data   TEXT NOT NULL,
                monetization_cycle_count INTEGER DEFAULT 0,
                last_sms_blast_time   TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_customer_profiles_phone
            ON customer_profiles(phone_number)
        """)
        conn.commit()
        conn.close()
        log.debug("[bridge] customer_profiles table ready")
    except Exception as e:
        log.warning(f"[bridge] customer_profiles table init failed: {e}")


# ── Processing: Forward to customer_profiles (local SQLite) ──────────
def _try_forward_to_customer_profiles(row: dict) -> str:
    """Try to convert a webhook payload into a local SQLite
    customer_profiles row. Returns empty string on success, or an
    error message on failure.
    """
    try:
        payload_str = row.get("raw_payload", "{}")
        payload = _json.loads(payload_str) if isinstance(payload_str, str) else payload_str
    except (json.JSONDecodeError, TypeError):
        return "invalid JSON payload"

    phone = payload.get("phone") or payload.get("contact_phone") or "UNKNOWN_LINE"
    vertical = payload.get("vertical") or payload.get("niche") or payload.get("niche_category") or "unassigned"
    event_id = row.get("event_id", "")

    # Use full event_id as profile_id (guaranteed unique UUID)
    profile_id = event_id or str(uuid.uuid4())
    # Use full event_id as the call reference (not truncated)
    associated_call_id = f"BRIDGE_EVENT_{event_id[:8]}" if event_id else f"BRIDGE_{uuid.uuid4().hex[:8]}"

    # Build retention data as enriched JSON
    retention_data = _json.dumps({
        "source_event_id": event_id,
        "source_platform": row.get("source_platform", ""),
        "event_type": row.get("event_type", ""),
        "vertical": vertical,
        "phone": phone,
        "raw_payload": payload,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO customer_profiles
                (profile_id, associated_call_id, phone_number, niche_category, lead_retention_data)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                lead_retention_data = json_set(
                    lead_retention_data,
                    '$.last_sync',
                    datetime('now')
                )
        """, (profile_id, associated_call_id, phone, vertical, retention_data))

        conn.commit()
        conn.close()
        log.debug(f"[bridge] customer_profiles upsert: {profile_id[:8]}... phone={phone[:10]} niche={vertical}")
        return ""  # success
    except Exception as e:
        return f"customer_profiles upsert failed: {str(e)[:200]}"


# ── Processing: Forward to Supabase Inbound Leads ────────────────────
def _try_forward_to_inbound(get_db: Callable, row: dict) -> str:
    """Try to convert a webhook payload into a Supabase inbound_lead.

    Returns empty string on success, or an error message on failure.
    Skips rows that don't contain recognisable lead data.
    """
    try:
        payload_str = row.get("raw_payload", "{}")
        payload = _json.loads(payload_str) if isinstance(payload_str, str) else payload_str
    except (json.JSONDecodeError, TypeError):
        return "invalid JSON payload"

    # Check if this looks like a lead (has name or phone or address)
    lead_name = payload.get("name") or payload.get("warehouse_name") or payload.get("lead_name") or ""
    lead_phone = payload.get("phone") or payload.get("contact_phone") or ""
    lead_address = payload.get("address") or payload.get("property_address") or ""
    lead_city = payload.get("city") or payload.get("metro", "")
    lead_source = f"bridge:{row.get('source_platform', 'unknown')}"

    if not lead_name and not lead_phone:
        return "skipped: no recognisable lead data"

    # Build the inbound lead record
    inbound_record = {
        "id": row.get("event_id", str(uuid.uuid4())),
        "name": lead_name[:200],
        "phone": lead_phone[:20] if lead_phone else None,
        "address": lead_address[:300] if lead_address else None,
        "city": lead_city[:100] if lead_city else None,
        "source": lead_source[:100],
        "meta": _json.dumps({
            "bridge_event_type": row.get("event_type", ""),
            "bridge_source": row.get("source_platform", ""),
            "raw_payload": payload,
        }),
        "notes": _json.dumps([{
            "text": f"Auto-ingested via bridge ({row.get('source_platform', '?')} · {row.get('event_type', '?')})",
            "operator": "bridge",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }]),
    }

    try:
        db = get_db()
        # Check for duplicate by source + event_id
        existing = db.table("inbound_leads").select("id").eq("id", inbound_record["id"]).limit(1).execute()
        if existing.data:
            return "skipped: duplicate event_id already in inbound_leads"

        result = db.table("inbound_leads").insert(inbound_record).execute()
        if not result.data:
            return "insert returned no data"
        log.info(
            f"[bridge] forwarded {row['event_id']} → inbound_leads "
            f"name={lead_name[:40]} source={lead_source}"
        )
        return ""  # success
    except Exception as e:
        return f"supabase insert failed: {str(e)[:200]}"


# ── Processor Loop ────────────────────────────────────────────────────
async def _bridge_processor_loop(get_db: Callable):
    """Background loop: polls unprocessed webhooks and forwards them.

    Runs every BRIDGE_PROCESSOR_INTERVAL_SEC (default 30s). For each
    unprocessed webhook:
      1. Forward to local SQLite customer_profiles (always)
      2. Forward to Supabase inbound_leads (if payload looks like a lead)
      3. Mark as processed (status=1) or errored (status=2)
    """
    import asyncio

    await asyncio.sleep(15)  # let the hub boot first
    while True:
        try:
            rows = _fetch_unprocessed(limit=20)
            for row in rows:
                errors = []

                # Step 1: Local customer_profiles (always)
                err1 = _try_forward_to_customer_profiles(row)
                if err1:
                    errors.append(err1)

                # Step 2: Supabase inbound_leads (if recognisable lead data)
                err2 = _try_forward_to_inbound(get_db, row)
                if err2 and "no recognisable" not in err2:
                    errors.append(err2)

                _mark_processed(row["event_id"], error="; ".join(errors) if errors else "")

            if rows:
                log.debug(f"[bridge] processor: {len(rows)} webhooks processed")
        except Exception as e:
            log.warning(f"[bridge] processor cycle error: {e}")
        await asyncio.sleep(PROCESSOR_INTERVAL_SEC)


# ═══════════════════════════════════════════════════════════════════════
# ROUTE REGISTRATION
# ═══════════════════════════════════════════════════════════════════════


def register_bridge_routes(
    app: FastAPI,
    *,
    get_db: Callable,
    require_auth: Optional[Callable] = None,
):
    """Wire Data Bridge Engine routes into the FastAPI app.

    Public endpoint (auth via BRIDGE_SECRET env var):
        POST /api/v6/bridge/receive  — external webhook ingestion

    Auth-required endpoints:
        GET  /api/v6/bridge/stats    — webhook counts by status
        GET  /api/v6/bridge/events   — recent webhook events
    """

    # ── Ingest Endpoint ────────────────────────────────────────────────

    @app.post("/api/v6/bridge/receive", status_code=201)
    async def ingest_external_data(request: Request):
        """Ingest an external payload from automated triggers or scrapers.

        Authenticate via the BRIDGE_SECRET env var. The caller passes it
        in the body's auth_token field or the X-Bridge-Token header.

        Body: {
            "event_type": "storm_alert" | "lead_capture" | "scraper_result" | ...,
            "source_platform": "partner_api" | "custom_scraper" | ...,
            "payload_data": { ... any structured data ... },
            "auth_token": "<matches BRIDGE_SECRET env var>"
        }
        """
        # Auth: check header first, then body
        header_token = request.headers.get("X-Bridge-Token", "").strip()
        body_token = ""

        try:
            body = await request.json()
            body_token = (body.get("auth_token") or "").strip()
        except Exception:
            body = {}
            body_token = ""

        if not BRIDGE_SECRET:
            log.warning("[bridge] BRIDGE_SECRET not set — blocking all requests")
            raise HTTPException(503, "Bridge not configured (BRIDGE_SECRET missing)")

        # Accept either header or body token
        if header_token != BRIDGE_SECRET and body_token != BRIDGE_SECRET:
            raise HTTPException(401, "Unauthorized: invalid auth token")

        event_type = (body.get("event_type") or "").strip()
        source_platform = (body.get("source_platform") or "").strip()
        payload_data = body.get("payload_data") or {}
        if not event_type or not source_platform:
            raise HTTPException(400, "event_type and source_platform are required")

        event_id = str(uuid.uuid4())
        result = _store_webhook(event_id, event_type, source_platform, payload_data)

        if not result.get("ok"):
            raise HTTPException(500, result.get("error", "Storage failed"))

        log.info(
            f"[bridge] ingested: type={event_type} source={source_platform} "
            f"id={event_id[:8]}..."
        )

        return JSONResponse({
            "status": "INGESTION_COMPLETE",
            "assigned_event_id": event_id,
            "queue_position": "IMMEDIATE",
        })

    # ── Stats Endpoint ─────────────────────────────────────────────────

    @app.get("/api/v6/bridge/stats")
    async def bridge_stats(auth: bool = Depends(require_auth)):
        """Return webhook counts by processing status."""
        return JSONResponse(_count_by_status())

    # ── Events List ────────────────────────────────────────────────────

    @app.get("/api/v6/bridge/events")
    async def bridge_events(
        limit: int = 50,
        status: str = "",
        auth: bool = Depends(require_auth),
    ):
        """Return recent webhook events, optionally filtered by status.

        ?status=pending   — unprocessed events
        ?status=processed — successfully forwarded
        ?status=errored   — processing failed
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row

            status_map = {"pending": 0, "processed": 1, "errored": 2}
            status_filter = status_map.get(status) if status else None

            if status_filter is not None:
                cursor = conn.execute(
                    "SELECT event_id, event_type, source_platform, "
                    "       processed_status, error, timestamp "
                    "FROM system_webhooks "
                    "WHERE processed_status = ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (status_filter, min(limit, 200)),
                )
            else:
                cursor = conn.execute(
                    "SELECT event_id, event_type, source_platform, "
                    "       processed_status, error, timestamp "
                    "FROM system_webhooks "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (min(limit, 200),),
                )

            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return JSONResponse({"events": rows, "count": len(rows)})
        except Exception as e:
            return JSONResponse({"events": [], "error": str(e)[:80]})

    log.info("[bridge] Routes registered · /api/v6/bridge/*")


# ═══════════════════════════════════════════════════════════════════════
# STARTUP HOOK (called from hub.py startup event)
# ═══════════════════════════════════════════════════════════════════════

def start_bridge_processor(get_db: Callable):
    """Start the background bridge processor loop. Call from startup event.

    Also ensures the customer_profiles table exists so the processor
    can write to it on the first cycle.

    Usage in hub.py:
        from empire_data_bridge import start_bridge_processor
        start_bridge_processor(get_db)
    """
    import asyncio

    # Ensure customer_profiles table exists before the loop starts
    _ensure_customer_profiles_table()

    asyncio.create_task(_bridge_processor_loop(get_db))
    log.info("[bridge] Processor loop scheduled")
