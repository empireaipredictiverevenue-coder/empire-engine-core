"""
EMPIRE V49 · HUB
================
Main FastAPI application. Wires all modules together.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx as _httpx
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from supabase import create_client, Client

# Empire modules
from empire_tokens import EMPIRE_TOKENS_CSS, EMPIRE_FONTS
from empire_tokens import _sign_token as _hub_sign_token, _verify_token as _hub_verify_token
from empire_layout import base_layout, section_stub, MODULES
from empire_command_payouts import payouts_view
from empire_command_contractors import contractors_view
from empire_command_pipeline import pipeline_view
from empire_command_audit import audit_view
from empire_command_operators import operators_view
from empire_command_dispatch import dispatch_view
from empire_command_inbound import inbound_view
from empire_command_console import console_view
from empire_splash import splash_page
from empire_live import LiveBroadcaster, register_live_routes
from empire_command_deck import command_deck_page
from empire_command_spa import command_spa_page
from empire_voice import VoiceRouter, register_voice_routes
from empire_sms import SMSEngine, register_sms_routes
from empire_contractors import register_contractor_routes
from empire_attribution import register_attribution_routes
from empire_email import EmailEngine, register_email_routes
from empire_matching import ContractorMatcher, register_matching_routes
from empire_playbook import register_playbook_routes
from empire_payouts import PayoutEngine, register_payout_routes
from empire_auth import AuthEngine, register_auth_routes, require_role
from empire_inbound import InboundCallTriage, register_inbound_routes
from empire_brain_memory import BrainMemory
from empire_brain_learning import BrainLearning
from empire_console import SovereignConsole, register_console_routes
from empire_orchestrator import StormOrchestrator, register_storm_routes
from empire_ai_router import AIRouter
from empire_brain_decide import BrainDecider
from empire_email_drafter import EmailDrafter
from empire_enricher_ai import AIEnricher
from empire_reply_qualifier import ReplyQualifier
from empire_narrator import Narrator
from empire_3d_map import register_map_routes
from empire_voice_control import vonage_answer_webhook


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("empire.hub")


# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "dev-token-insecure")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
VONAGE_API_KEY = os.environ.get("VONAGE_API_KEY", "")
VONAGE_API_SECRET = os.environ.get("VONAGE_API_SECRET", "")
VONAGE_APPLICATION_ID = os.environ.get("VONAGE_APPLICATION_ID", "")
VONAGE_NUMBER = os.environ.get("VONAGE_NUMBER", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")


# ─────────────────────────────────────────────────────────────────────
# SUPABASE
# ─────────────────────────────────────────────────────────────────────
_supabase_client: Optional[Client] = None

def get_db() -> Client:
    global _supabase_client
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase_client


# ─────────────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="Empire AI · V49", version="49.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────
# RESEND SEND HELPER
# ─────────────────────────────────────────────────────────────────────
async def _send_email(to, subject, html):
    if not RESEND_API_KEY:
        return {"ok": False, "error": "RESEND_API_KEY missing"}
    from_addr = os.environ.get("FROM_ADDRESS", "noreply@empire-ai.co.uk")
    from_name = os.environ.get("FROM_NAME", "Empire AI Operations")
    try:
        async with _httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={"from": f"{from_name} <{from_addr}>", "to": [to], "subject": subject, "html": html},
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            return {"ok": r.status_code < 300, "id": data.get("id"), "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────
# ENGINES
# ─────────────────────────────────────────────────────────────────────
live_broadcaster = LiveBroadcaster()

voice_router = VoiceRouter(
    vonage_api_key=VONAGE_API_KEY,
    vonage_api_secret=VONAGE_API_SECRET,
    vonage_app_id=VONAGE_APPLICATION_ID,
    vonage_private_key_path=os.environ.get("VONAGE_PRIVATE_KEY_PATH", ""),
    vonage_number=VONAGE_NUMBER,
    public_base_url=PUBLIC_BASE_URL,
)

sms_engine = SMSEngine(
    voice_router=voice_router,
    get_db=get_db,
)

email_engine = EmailEngine(
    get_db=get_db,
    send_email=_send_email,
    sign_token=_hub_sign_token,
    verify_token=_hub_verify_token,
    public_base_url=PUBLIC_BASE_URL,
    physical_address=os.environ.get("EMPIRE_POSTAL_ADDRESS", "Empire AI Ltd"),
    sender_name=os.environ.get("EMPIRE_SENDER_NAME", "Empire AI Operations"),
)

matcher = ContractorMatcher(get_db=get_db)

payout_engine = PayoutEngine(
    get_db=get_db,
    empire_vault_wallet=os.environ.get("EMPIRE_VAULT_WALLET", ""),
    empire_ops_wallet=os.environ.get("EMPIRE_OPS_WALLET", ""),
    empire_signing_key=os.environ.get("EMPIRE_SIGNING_KEY", ""),
    solana_rpc_url=os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
    auto_approve_under_usd=float(os.environ.get("PAYOUT_AUTO_APPROVE_USD", "0")),
    broadcaster=live_broadcaster,
    ntfy_topic=NTFY_TOPIC,
    ntfy_token=NTFY_TOKEN,
)

auth_engine = AuthEngine(
    get_db=get_db,
    send_email=_send_email,
    sign_token=_hub_sign_token,
    verify_token=_hub_verify_token,
    public_base_url=PUBLIC_BASE_URL,
    legacy_hub_token=HUB_TOKEN,
    session_ttl_hours=12,
)

inbound_triage = InboundCallTriage(
    get_db=get_db,
    anthropic_key=ANTHROPIC_API_KEY,
    openai_key=OPENAI_API_KEY,
    operator_number=os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
    broadcaster=live_broadcaster,
    ntfy_topic=NTFY_TOPIC,
    ntfy_token=NTFY_TOKEN,
)

brain_memory = BrainMemory(
    get_db=get_db,
    openai_key=OPENAI_API_KEY,
    embedding_model="text-embedding-3-small",
)

brain_learning = BrainLearning(get_db=get_db)

console = SovereignConsole(
    anthropic_key=ANTHROPIC_API_KEY,
    get_db=get_db,
    model="claude-opus-4-7",
)


# AI Router + Brain (local Ollama, no external dependencies)
ai_router = AIRouter(get_db=get_db)
brain_decider = BrainDecider(router=ai_router)

# Agentic features layer
email_drafter = EmailDrafter(router=ai_router, get_db=get_db)
ai_enricher = AIEnricher(router=ai_router)
reply_qualifier = ReplyQualifier(router=ai_router)
narrator = Narrator(broadcaster=live_broadcaster)


storm_orchestrator = StormOrchestrator(
    get_db=get_db,
    email_engine=email_engine,
    brain=brain_decider,
    drafter=email_drafter,
    enricher=ai_enricher,
    narrator=narrator,
    broadcaster=live_broadcaster,
    poll_interval_sec=int(os.environ.get("STORM_POLL_INTERVAL_SEC", "300")),
    lane_count=int(os.environ.get("STORM_LANE_COUNT", "6")),
    max_sends_hour=int(os.environ.get("STORM_MAX_SENDS_PER_HOUR", "50")),
    max_sends_day=int(os.environ.get("STORM_MAX_SENDS_PER_DAY", "200")),
    bounce_breaker_pct=float(os.environ.get("STORM_BOUNCE_BREAKER_PCT", "5")),
)



# ─────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────
require_auth = auth_engine.require_auth
require_owner = require_role(auth_engine, "owner")
require_operator = require_role(auth_engine, "operator")


# ─────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(splash_page())


@app.get("/command", response_class=HTMLResponse)
async def command_deck():
    # Auth happens client-side: the SPA reads localStorage.hub_token,
    # calls /api/v1/auth/me, and redirects to /auth/login on 401.
    return HTMLResponse(command_spa_page())


# Legacy /command/<section> URLs (server-rendered HTML views, pre-SPA)
# now redirect to the SPA's hash route. Kept as redirects so any bookmarks,
# old emails, or external links keep working.
_LEGACY_SECTIONS = {
    "pulse", "pipeline", "dispatch", "inbound", "payouts",
    "contractors", "console", "audit", "operators",
}


@app.get("/command/{section}")
async def command_section_redirect(section: str):
    if section in _LEGACY_SECTIONS:
        return RedirectResponse(f"/command#/{section}", status_code=302)
    raise HTTPException(404, f"Unknown section: {section}")


@app.get("/api/market-pulse")
async def market_pulse():
    return {"status": "operational", "timestamp": datetime.now(timezone.utc).isoformat()}


register_live_routes(app, live_broadcaster, hub_token=HUB_TOKEN, auth_engine=auth_engine)
register_voice_routes(app, voice_router)
register_sms_routes(app, sms_engine, require_auth=require_auth)
register_contractor_routes(app, require_auth=require_auth, get_db=get_db, sign_token=_hub_sign_token, verify_token=_hub_verify_token, send_email=_send_email, public_base_url=PUBLIC_BASE_URL, broadcaster=live_broadcaster)
register_attribution_routes(app, require_auth=require_auth, get_db=get_db)
register_email_routes(app, email_engine, require_auth=require_auth)
register_matching_routes(app, matcher=matcher, require_auth=require_auth, sign_token=_hub_sign_token, verify_token=_hub_verify_token, send_email=_send_email)
register_playbook_routes(app, require_auth=require_auth, get_db=get_db)
register_payout_routes(app, engine=payout_engine, require_auth=require_auth, require_owner=require_owner)
register_auth_routes(app, auth_engine=auth_engine, require_auth=require_auth)
register_inbound_routes(app, inbound_triage, require_auth=require_auth)
register_console_routes(app, console=console, require_auth=require_auth, get_db=get_db)
register_storm_routes(app, storm_orchestrator, require_auth=require_auth)
register_map_routes(app, scout=storm_orchestrator.scout, get_db=get_db, require_auth=require_auth)
register_voice_routes(app, app)


# ─────────────────────────────────────────────────────────────────────
# STARTUP / SHUTDOWN
# ─────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    log.info("Empire V49 · Starting up")
    asyncio.create_task(brain_learning.nightly_tune_loop())
    asyncio.create_task(sms_engine.dispatcher_loop())
    asyncio.create_task(email_engine.dispatcher_loop())
    asyncio.create_task(storm_orchestrator.poll_loop())
    log.info("Empire V49 · Operational")


@app.on_event("shutdown")
async def shutdown():
    log.info("Empire V49 · Shutting down")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ── Drafts approval + narrate stream + reply qualify ────────
from fastapi import Depends, Body, HTTPException
from fastapi.responses import StreamingResponse
import asyncio as _asyncio
import json as _json

@app.get("/api/v1/drafts/pending")
async def drafts_pending(limit: int = 50, auth: bool = Depends(require_auth)):
    db = get_db()
    r = db.table("email_drafts").select("*").eq("status", "pending").order("created_at", desc=True).limit(limit).execute()
    return {"drafts": r.data or []}

@app.post("/api/v1/drafts/{draft_id}/approve")
async def drafts_approve(draft_id: str, auth: bool = Depends(require_auth)):
    db = get_db()
    r = db.table("email_drafts").select("*").eq("id", draft_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "draft not found")
    d = r.data[0]
    if d.get("status") != "pending":
        raise HTTPException(400, f"draft already {d.get('status')}")
    # Send via the existing email engine
    try:
        result = await email_engine.send_direct(
            to=d["to_email"], subject=d["subject"], body=d["body"],
            meta={"draft_id": draft_id, "storm_event": d.get("storm_event")},
        )
    except AttributeError:
        # If send_direct doesn't exist, enroll instead
        result = await email_engine.enroll(
            email=d["to_email"], target_addr=d.get("storm_area") or "",
            sequence_type="storm_strike", meta={"draft_id": draft_id},
        )
    from datetime import datetime, timezone
    db.table("email_drafts").update({
        "status": "sent" if result and result.get("ok") else "approved",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "sent_at": datetime.now(timezone.utc).isoformat() if result and result.get("ok") else None,
    }).eq("id", draft_id).execute()
    return {"ok": True, "draft_id": draft_id, "result": result}

@app.post("/api/v1/drafts/{draft_id}/reject")
async def drafts_reject(draft_id: str, auth: bool = Depends(require_auth)):
    from datetime import datetime, timezone
    db = get_db()
    db.table("email_drafts").update({
        "status": "rejected",
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", draft_id).execute()
    return {"ok": True, "draft_id": draft_id}

@app.get("/api/v1/narrate/recent")
async def narrate_recent(auth: bool = Depends(require_auth)):
    return narrator.snapshot()

@app.post("/api/v1/reply/qualify")
async def reply_qualify_route(payload: dict = Body(...), auth: bool = Depends(require_auth)):
    text = payload.get("text") or ""
    subject = payload.get("subject") or ""
    return await reply_qualifier.qualify(text, subject)

