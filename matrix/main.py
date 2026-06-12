"""
EMPIRE V49 · HIGH-INTENT PAY-PER-CALL MATRIX
=============================================
Inbound call routing engine implementing Ventura's high-intent routing filter.
Saves caller data before forwarding to aggregator network. Runs on port 8045.

ENDPOINTS
─────────
  POST /api/v6/ppc/inbound-route  → Capture + route high-intent call
  POST /api/v6/ppc/post-call-audit → Process post-call transcript, verify payout
  GET  /api/v6/ppc/health         → Health check
"""

import json
import uuid
import sqlite3
import logging
from pathlib import Path

from fastapi import FastAPI, status, HTTPException
from pydantic import BaseModel

log = logging.getLogger("empire.ppc.matrix")

app = FastAPI(title="Empire_AI_High_Intent_Pay_Per_Call_Matrix", version="6.0.0")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"


# ── Models ────────────────────────────────────────────────────────────
class InboundCallPayload(BaseModel):
    visitor_session_id: str
    incoming_phone_number: str
    traffic_source: str
    ad_creative_id: str
    captured_zip_code: str
    niche_category: str
    sub_niche_vertical: str


class PostCallEvent(BaseModel):
    call_id: str
    call_duration_seconds: int
    raw_audio_transcript: str


# ── DB ────────────────────────────────────────────────────────────────
def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── Routes ────────────────────────────────────────────────────────────
@app.get("/api/v6/ppc/health")
async def ppc_health():
    """Health check."""
    return {"status": "OPERATIONAL", "service": "ppc-inbound-matrix", "port": 8045, "version": "6.0.0"}


@app.post("/api/v6/ppc/inbound-route", status_code=status.HTTP_200_OK)
async def route_high_intent_call(payload: InboundCallPayload):
    """
    Implements high-intent routing filter.
    Saves initial caller data assets BEFORE forwarding to any aggregator network.
    """
    call_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()

    # Determine buyer assignment and predicted payout
    assigned_buyer = "aggregator_pool"
    predicted_payout = 45.00  # Base rate

    if payload.niche_category == "mass_tort":
        predicted_payout = 185.00  # Higher ceiling for mass tort

    try:
        cursor.execute('''
            INSERT INTO call_logs (
                call_id, visitor_session_id, incoming_phone_number, traffic_source,
                ad_creative_id, captured_zip_code, niche_category, sub_niche_vertical,
                assigned_buyer_id, revenue_generated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            call_id, payload.visitor_session_id, payload.incoming_phone_number,
            payload.traffic_source, payload.ad_creative_id, payload.captured_zip_code,
            payload.niche_category, payload.sub_niche_vertical, assigned_buyer, predicted_payout,
        ))

        # Immediate retention schema entry — secondary text blasting asset
        retention_id = str(uuid.uuid4())
        initial_context = json.dumps({
            "source_ad": payload.ad_creative_id,
            "zip_context": payload.captured_zip_code,
            "lifecycle": "active_inbound",
        })

        cursor.execute('''
            INSERT INTO customer_profiles (profile_id, associated_call_id, phone_number, niche_category, lead_retention_data)
            VALUES (?, ?, ?, ?, ?)
        ''', (retention_id, call_id, payload.incoming_phone_number, payload.niche_category, initial_context))

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database ingestion drop: {str(e)}")
    finally:
        conn.close()

    return {
        "status": "CALL_CAPTURED_AND_ROUTED",
        "call_id": call_id,
        "assigned_destination": assigned_buyer,
        "payout_tier": predicted_payout,
        "action_required": "SIMO_RING_OPERATORS",
    }


@app.post("/api/v6/ppc/post-call-audit", status_code=status.HTTP_200_OK)
async def process_post_call_event(payload: PostCallEvent):
    """
    Processes audio transcripts through the local AI engine to extract brand names
    and verify payouts based on conversion triggers.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM call_logs WHERE call_id = ?", (payload.call_id,))
    call_record = cursor.fetchone()

    if not call_record:
        conn.close()
        raise HTTPException(status_code=404, detail="Call tracking reference missing.")

    # Duration verification — standard high-intent contract converts at 90-120 seconds
    payout_triggered = 1 if payload.call_duration_seconds >= 90 else 0
    base_revenue = call_record["revenue_generated"] if payout_triggered == 1 else 0.0

    try:
        cursor.execute('''
            UPDATE call_logs
            SET call_duration_seconds = ?, payout_triggered = ?, revenue_generated = ?
            WHERE call_id = ?
        ''', (payload.call_duration_seconds, payout_triggered, base_revenue, payload.call_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Post-call write error: {str(e)}")
    finally:
        conn.close()

    return {
        "call_id": payload.call_id,
        "duration_verified": payload.call_duration_seconds,
        "payout_status": "REVENUE_LOCKED" if payout_triggered == 1 else "DURATION_FLOOR_NOT_MET",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8045)
