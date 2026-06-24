
"""
Empire V49 · PPC voice forwarder
==================================
Bridges inbound Vonage calls to the PPC matrix.
When /webhook/vonage-answer fires, empire_voice.py returns NCCO JSON,
but we ALSO want to log the inbound call to PPC for routing/audit.
This endpoint accepts the call data and POSTs it to PPC matrix.
"""
import os, json, asyncio, logging
import httpx
from fastapi import Request, HTTPException, APIRouter
from pydantic import BaseModel

log = logging.getLogger("empire.ppc.forwarder")
router = APIRouter()
PPC_URL = os.environ.get("PPC_URL", "http://127.0.0.1:8045")


class VoiceForwardPayload(BaseModel):
    caller_number: str
    called_number: str
    traffic_source: str = "voice_inbound"
    ad_creative_id: str = "voice_strike"
    captured_zip_code: str = ""
    niche_category: str = "storm_damage"
    sub_niche_vertical: str = ""
    visitor_session_id: str = ""
    duration_hint: int = 0


@router.post("/api/v1/ppc/voice-forward")
async def voice_forward(payload: VoiceForwardPayload):
    """Bridge: voice inbound → PPC matrix."""
    if not payload.visitor_session_id:
        payload.visitor_session_id = f"voice_{payload.caller_number}_{payload.called_number}"
    body = {
        "visitor_session_id": payload.visitor_session_id,
        "incoming_phone_number": payload.caller_number,
        "traffic_source": payload.traffic_source,
        "ad_creative_id": payload.ad_creative_id,
        "captured_zip_code": payload.captured_zip_code,
        "niche_category": payload.niche_category,
        "sub_niche_vertical": payload.sub_niche_vertical or payload.niche_category,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{PPC_URL}/api/v6/ppc/inbound-route", json=body)
        if r.status_code == 200:
            result = r.json()
            log.info(f"voice_forward OK: caller={payload.caller_number} → {result.get('assigned_destination')} (${result.get('payout_tier')})")
            return {
                "ok": True,
                "ppc_call_id": result.get("call_id"),
                "assigned_destination": result.get("assigned_destination"),
                "payout_tier": result.get("payout_tier"),
            }
        else:
            log.warning(f"voice_forward PPC {r.status_code}: {r.text[:200]}")
            return {"ok": False, "ppc_status": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        log.warning(f"voice_forward exception: {e}")
        return {"ok": False, "error": str(e)[:200]}


@router.get("/api/v1/ppc/health")
async def ppc_bridge_health():
    """Health check that combines our status with PPC matrix."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{PPC_URL}/api/v6/ppc/health")
            return {"ok": True, "ppc_matrix": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
