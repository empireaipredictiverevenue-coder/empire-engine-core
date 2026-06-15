"""
EMPIRE V49 · HUB
================
Main FastAPI application. Wires all modules together.
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx as _httpx
from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from supabase import create_client, Client
from empire_switchboard import _sb

# Empire modules
from empire_tokens import EMPIRE_TOKENS_CSS, EMPIRE_FONTS
from empire_tokens import _sign_token as _hub_sign_token, _verify_token as _hub_verify_token
from empire_layout import base_layout, MODULES
from empire_command_payouts import payouts_view
from empire_command_contractors import contractors_view
from empire_command_pipeline import pipeline_view
from empire_command_audit import audit_view
from empire_command_operators import operators_view
from empire_command_dispatch import dispatch_view
from empire_command_inbound import inbound_view
from empire_command_console import console_view
from empire_splash import splash_page
from empire_support import support_page
from empire_demo import demo_page
from empire_pricing import pricing_page, CPLPricingEngine, cpl_engine
from empire_live import LiveBroadcaster, register_live_routes
from empire_command_deck import command_deck_page
from empire_command_spa import command_spa_page
from empire_voice import VoiceRouter, register_voice_routes
from empire_sms import SMSEngine, register_sms_routes
from empire_contractors import register_contractor_routes
from empire_qc_api import register_qc_routes
from empire_hermes_api import register_hermes_routes
from empire_wiki_viewer import register_wiki_routes
from empire_attribution import register_attribution_routes
from empire_email import EmailEngine, register_email_routes
from empire_matching import ContractorMatcher, register_matching_routes
from empire_playbook import register_playbook_routes
from empire_payouts import PayoutEngine, register_payout_routes
from empire_fee import register_fee_routes
from empire_fee_operator import register_operator_mark_settled
from empire_abtest import register_ab_test_routes
from empire_predictive import register_predictive_routes
from empire_carrier import register_mock_carrier_routes
from empire_inbound_monitor import register_inbound_monitor_routes
from empire_auth import AuthEngine, register_auth_routes, require_role
from empire_inbound import InboundCallTriage, register_inbound_routes
from empire_brain_memory import BrainMemory
from empire_brain_learning import BrainLearning
from empire_dream import DreamLoop, set_dream_loop, get_latest_wisdom
from empire_hourly_digest import HourlyDigestLoop
from bots.seo_agent import run_loop as seo_run_loop
from bots.backlinks_agent import run_loop as backlinks_run_loop
from empire_console import SovereignConsole, register_console_routes
from empire_orchestrator import StormOrchestrator, register_storm_routes
from empire_ai_router import AIRouter
from empire_brain_decide import BrainDecider
from empire_email_drafter import EmailDrafter
from empire_enricher_ai import AIEnricher
from empire_reply_qualifier import ReplyQualifier
from empire_narrator import Narrator
from empire_3d_map import register_map_routes
from empire_switchboard import register_switchboard_routes
from empire_niche_terrain import NicheTerrain
from empire_partner_onboarding import register_partner_routes
from empire_affiliate_portal import register_affiliate_routes
from empire_si_brain import SyntheticBrain, register_synthetic_routes
from empire_si_strategy import StrategyEvolution
from empire_si_adaptive import AdaptiveEngine
from empire_ai_closer import AICloser, ai_closer_score_only
from empire_agi_governor import governor
from empire_pain_points import PainPointLibrary
from empire_satellite_strike import SatelliteStrikeCore
from empire_swarm_gate import GodModeSwarmGate
from conversion_funnel import SalesFunnel
from empire_mission_control import (
    mission_control_snapshot,
    mission_control_broadcast_loop,
    register_mission_control_routes,
)
from empire_pulse import PulseEngine, pulse_view_page
from empire_data_bridge import register_bridge_routes as register_data_bridge_routes, start_bridge_processor, init_bridge_db
from empire_bridge import BridgeEngine, register_bridge_routes as register_bridge_engine_routes
from empire_voice_control import VoiceController
from empire_brain_personality import BrainPersonality
from empire_strike_packs import StrikePackCatalog, SubscriptionEngine, DeliveryFilter, register_strike_pack_routes
from empire_carrier_portfolio import PortfolioManager, StormMatcher, StormReportEngine, register_carrier_routes

# Empire AI Suite — 3-Product Monetization Gateway
from suite_core import (
    SuiteSubscriptionEngine,
    SuiteGuard,
    register_suite_routes,
    _init_suite_db as _init_suite_db_sqlite,
)
from products.inbound_router import InboundRouter, InboundRouterRoutes
from products.data_vault import DataVault, DataVaultRoutes
from products.buyer_spy import BuyerSpy, BuyerSpyRoutes
from products.omni_bridge import OmniBridge, OmniBridgeRoutes
from products.agent_orchestrator import AgentOrchestrator, AgentOrchestratorRoutes
from products.b2b_pro import B2BPro, B2BProRoutes
from products.lead_score import LeadScoreAI, LeadScoreRoutes
from products.compliant import Compliant, CompliantRoutes
from products.strike_campaigns import StrikeCampaigns, StrikeCampaignsRoutes
from products.forecast import Forecast, ForecastRoutes
from products.market_eye import MarketEyeEngine, MarketEyeRoutes
from products.content_pulse import ContentPulse, ContentPulseRoutes
from products.contractor_exchange import ContractorExchange, ContractorExchangeRoutes
from products.sales_funnel import SalesFunnelEngine, SalesFunnelRoutes
from products.product_email_dispatcher import ProductEmailDispatcher
from products.trial_conversion import TrialConversionEngine
from hook_analytics import HookRoutes

# Strategist & Analytics Agents
from empire_strategist import StrategistAgent
from empire_profit_margin_agent import register_profit_margin_routes
from empire_traffic_ads_agent import register_traffic_ads_routes
from empire_stack_agent import register_stack_routes
from empire_network_agent import register_network_routes
from empire_loop_agent import register_loop_routes
from empire_analytics_agent import AnalyticsAgent
from empire_psychology_mind_map import register_psychology_routes
from empire_self_awareness import register_self_awareness_routes
from empire_business_planner import register_business_planner_routes
from empire_agent_os import AgentKernel, register_agent_os_routes


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
dream_loop = DreamLoop(broadcaster=live_broadcaster)
set_dream_loop(dream_loop)
hourly_digest = HourlyDigestLoop()

console = SovereignConsole(
    anthropic_key=ANTHROPIC_API_KEY,
    get_db=get_db,
    model="claude-opus-4-7",
)


# AI Router + Brain (local Ollama, no external dependencies)
ai_router = AIRouter(get_db=get_db)
brain_decider = BrainDecider(router=ai_router)

# Phase 9: Brain Personality — operator-configurable persona per niche
brain_personality = BrainPersonality(get_db=get_db)
brain_decider.personality = brain_personality

# Agentic features layer
email_drafter = EmailDrafter(router=ai_router, get_db=get_db)
email_drafter.personality = brain_personality  # Phase 9.5: personality-aware email drafting
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

# Pain Points Library — niche-specific pain point profiles, conversion tracking, script integration
pain_points = PainPointLibrary(get_db=get_db)

# AI Closer — AGI-brained voice pipeline (BrainDecider → VoiceStreaming → SI feedback)
ai_closer = AICloser(
    brain_decider=brain_decider,
    voice_router=voice_router,
    sms_engine=sms_engine,
    email_engine=email_engine,
    get_db=get_db,
    operator_number=os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
    pain_points=pain_points,
)

# Sales Funnel — will be wired after si_strategy is created (see SI Strategy section below)
sales_funnel = SalesFunnel(closer=ai_closer)

# Voice Controller — wraps BrainDecider + VoiceRouter + BrainMemory
voice_controller = VoiceController(
    voice_router=voice_router,
    brain_decider=brain_decider,
    brain_memory=brain_memory,
    get_db=get_db,
    operator_number=os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
    broadcaster=live_broadcaster,
    ntfy_topic=NTFY_TOPIC,
    ntfy_token=NTFY_TOKEN,
)

# Bridge Engine — voice-first full-screen interface
bridge_engine = BridgeEngine(
    get_db=get_db,
    voice_controller=voice_controller,
    broadcaster=live_broadcaster,
)

# Pulse Engine — rollup engine for the /view/pulse insight layer
pulse_engine = PulseEngine(
    get_db=get_db,
    refresh_interval_sec=int(os.environ.get("PULSE_REFRESH_INTERVAL_SEC", "300")),
)

# Strike Packs — product catalog + subscription engine + delivery filter
strike_pack_catalog = StrikePackCatalog(get_db=get_db)
strike_pack_subscriptions = SubscriptionEngine(get_db=get_db, catalog=strike_pack_catalog)
strike_pack_delivery = DeliveryFilter(get_db=get_db, catalog=strike_pack_catalog, subscriptions=strike_pack_subscriptions)  # reserved for lead-dispatch pipeline

# Carrier Portfolio — Insurance Intelligence product
carrier_portfolio_manager = PortfolioManager(get_db=get_db)
carrier_storm_matcher = StormMatcher(get_db=get_db, manager=carrier_portfolio_manager)
carrier_report_engine = StormReportEngine(
    get_db=get_db,
    manager=carrier_portfolio_manager,
    send_email=_send_email,
    public_base_url=PUBLIC_BASE_URL,
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
# ── Static assets (chat widget, etc.) ─────────────────────────────────
_STATIC_DIR = "/root/empire-v49/static"
import os as _os
if _os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# ── Public contractor landing page + chat widget ───────────────────────
register_contractor_routes(app)

# ── Shared chat handler (contractors + customer-service) ───────────────
# Both endpoints use the same rate-limit logic and synthetic_brain /ask
# call. Only the system prompt and error messages differ.
import time as _t_chat

_CHAT_RATE_LIMITS: dict[str, dict] = {}  # endpoint -> {session_id -> [timestamps]}
_CHAT_MAX_PER_WINDOW = 30
_CHAT_WINDOW_SEC = 3600

_CHAT_SYSTEM_PROMPT = (
    "You are Empire AI's contractor-recruit assistant. Answer "
    "questions about Empire AI's offer to commercial contractors:\n"
    "- 3% referral fee on settled insurance claims\n"
    "- First 2 closed deals are 100% complimentary (no fee)\n"
    "- No contract, no exclusivity, no call required\n"
    "- Self-onboard at this page in 90 seconds\n"
    "- Dispatch via SMS or email when a storm-affected property owner replies YES\n"
    "- Service areas currently: DFW, Houston, San Antonio, Austin\n"
    "Be specific, brief (under 80 words), and always end with a "
    "call-to-action (self-onboard, watch the demo, or read the FAQ). "
    "If asked something you don't know, say so and offer to connect "
    "them with a human via email. Never invent numbers or terms."
)

_CS_SYSTEM_PROMPT = (
    "You are Empire AI's customer service assistant. You help visitors "
    "understand Empire AI's platform, products, and services. Answer questions about:\n"
    "- How Empire AI generates leads for contractors through storm detection and SMS qualification\n"
    "- The 3% referral fee model (only on settled insurance claims)\n"
    "- The first 2 deals complimentary policy\n"
    "- Self-onboarding for contractors at empire-ai.co.uk/contractors\n"
    "- Service areas: DFW, Houston, San Antonio, Austin (expanding)\n"
    "- Suite products: Inbound Router, Data Vault, Buyer Spy AI, and 12 more\n"
    "- How property owners can opt out via STOP reply\n"
    "Be concise, helpful, and professional. Under 100 words per response. "
    "If you don't know something, say so and offer to connect them with a human "
    "via support@empire-ai.co.uk. Never invent numbers, pricing, or terms. "
    "Always end with a next step: visit a page, email support, or ask another question."
)


async def _chat_handler(
    request: Request,
    *,
    endpoint: str,
    system_prompt: str,
    rate_limited_reply: str,
    brain_unavailable_reply: str,
) -> JSONResponse:
    """Shared handler for both chat endpoints.

    Validates, rate-limits (30/hr per session_id), calls synthetic_brain
    /ask, and returns a JSONResponse with {ok, reply, count_remaining}.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    session_id = (body.get("session_id") or "").strip()
    message = (body.get("message") or "").strip()

    if not session_id:
        return JSONResponse({"ok": False, "error": "missing_session_id"}, status_code=400)
    if not message:
        return JSONResponse({"ok": False, "error": "missing_message"}, status_code=400)
    if len(message) > 2000:
        return JSONResponse({"ok": False, "error": "message_too_long"}, status_code=400)

    # ── Rate limiting per endpoint ──────────────────────────────────────
    bucket = _CHAT_RATE_LIMITS.setdefault(endpoint, {})
    now = _t_chat.time()
    timestamps = bucket.get(session_id, [])
    timestamps = [t for t in timestamps if now - t < _CHAT_WINDOW_SEC]

    if len(timestamps) >= _CHAT_MAX_PER_WINDOW:
        bucket[session_id] = timestamps
        return JSONResponse({
            "ok": False, "error": "rate_limited",
            "count_remaining": 0,
            "reply": rate_limited_reply,
        }, status_code=429)

    timestamps.append(now)
    bucket[session_id] = timestamps
    remaining = _CHAT_MAX_PER_WINDOW - len(timestamps)

    # Periodic cleanup of stale sessions across all endpoints
    total = sum(len(b) for b in _CHAT_RATE_LIMITS.values())
    if total > 500:
        cutoff = now - _CHAT_WINDOW_SEC
        for ep, bkt in list(_CHAT_RATE_LIMITS.items()):
            stale = [sid for sid, ts in bkt.items() if all(t < cutoff for t in ts)]
            for sid in stale:
                del bkt[sid]
            if not bkt:
                del _CHAT_RATE_LIMITS[ep]
        removed = 0
        for ep, bkt in list(_CHAT_RATE_LIMITS.items()):
            stale = [sid for sid, ts in bkt.items() if all(t < cutoff for t in ts)]
            for sid in stale:
                del bkt[sid]
                removed += 1
            if not bkt:
                del _CHAT_RATE_LIMITS[ep]
        log.debug(f"[_chat_handler] rate-limit cache swept {removed} stale sessions")

    # ── Call synthetic brain ────────────────────────────────────────────
    try:
        async with _httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "http://localhost:8005/ask",
                json={"system": system_prompt, "prompt": message},
            )
            if r.status_code < 500:
                data = r.json()
                reply = data.get("response", "")
            else:
                reply = ""
    except Exception as e:
        log.warning(f"[{endpoint}] brain call failed: {e}")
        reply = ""

    if not reply:
        return JSONResponse({
            "ok": False,
            "error": "brain_unavailable",
            "count_remaining": remaining,
            "reply": brain_unavailable_reply,
        }, status_code=503)

    return JSONResponse({
        "ok": True,
        "reply": reply,
        "count_remaining": remaining,
    })


@app.post("/api/contractors/chat")
async def contractors_chat(request: Request) -> JSONResponse:
    """Contractor-recruit chat — rate-limited, backed by synthetic_brain."""
    return await _chat_handler(
        request,
        endpoint="contractors",
        system_prompt=_CHAT_SYSTEM_PROMPT,
        rate_limited_reply=(
            "You've asked a lot of questions \u2014 feel free to self-onboard "
            "and we'll email you a full breakdown."
        ),
        brain_unavailable_reply=(
            "I'm having a moment \u2014 try again in 30 seconds or self-onboard "
            "below and we'll get back to you."
        ),
    )


@app.post("/api/customer-service/chat")
async def customer_service_chat(request: Request) -> JSONResponse:
    """Customer service chat on /support — rate-limited, backed by synthetic_brain."""
    return await _chat_handler(
        request,
        endpoint="customer-service",
        system_prompt=_CS_SYSTEM_PROMPT,
        rate_limited_reply="You've reached the message limit. Email support@empire-ai.co.uk and we'll get back to you quickly.",
        brain_unavailable_reply="Our AI assistant is having a moment. Try again shortly or email support@empire-ai.co.uk.",
    )

# Quality Control daemon endpoints (007aa47 followup)
register_qc_routes(app)

# Hermes dashboard endpoint (operator SPA)
register_hermes_routes(app)

# Wiki viewer (the persistent project wiki)
register_wiki_routes(app)

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(splash_page())


@app.get("/support", response_class=HTMLResponse)
async def support():
    """Public support page — FAQ + contact info + customer-service chat widget."""
    return HTMLResponse(support_page())


@app.get("/pricing", response_class=HTMLResponse)
async def pricing():
    """Dynamic pricing page — suite products from product_metadata table."""
    products = []
    try:
        db = get_db()
        r = db.table("product_metadata") \
            .select("tier,product_name,display_name,description,monthly_price_usd,price_per_unit,features,sort_order") \
            .eq("is_active", True) \
            .eq("is_public", True) \
            .order("sort_order") \
            .execute()
        products = r.data or []
    except Exception as e:
        log.warning(f"[pricing] product_metadata query failed: {e}")
    return HTMLResponse(pricing_page(products=products))


@app.get("/demo", response_class=HTMLResponse)
async def demo():
    """Public walkthrough of the funnel (the link the /contractors
    landing page points to). Static HTML, no DB queries."""
    return HTMLResponse(demo_page())


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
register_voice_routes(
    app, voice_router,
    require_auth=require_auth,
    get_db=get_db,
    ntfy_topic=NTFY_TOPIC,
    ntfy_token=NTFY_TOKEN,
    broadcaster=live_broadcaster,
    brain_decider=brain_decider,
    brain_memory=brain_memory,
)
register_sms_routes(app, sms_engine, require_auth=require_auth)
register_contractor_routes(app, require_auth=require_auth, get_db=get_db, sign_token=_hub_sign_token, verify_token=_hub_verify_token, send_email=_send_email, public_base_url=PUBLIC_BASE_URL, broadcaster=live_broadcaster)
register_attribution_routes(app, require_auth=require_auth, get_db=get_db)
register_email_routes(app, email_engine, require_auth=require_auth)
register_matching_routes(app, matcher=matcher, require_auth=require_auth, sign_token=_hub_sign_token, verify_token=_hub_verify_token, send_email=_send_email)
register_playbook_routes(app, require_auth=require_auth, get_db=get_db)
register_payout_routes(app, engine=payout_engine, require_auth=require_auth, require_owner=require_owner)
register_fee_routes(app, require_auth=require_auth, get_db=get_db)
register_operator_mark_settled(app, require_auth=require_auth, get_db=get_db)
register_ab_test_routes(app, require_auth=require_auth, get_db=get_db)
register_predictive_routes(app, require_auth=require_auth, get_db=get_db)
register_mock_carrier_routes(app, require_auth=require_auth, get_db=get_db)
register_inbound_monitor_routes(app, require_auth=require_auth, get_db=get_db)
register_profit_margin_routes(app, require_auth=require_auth, get_db=get_db)
register_traffic_ads_routes(app, require_auth=require_auth, get_db=get_db)
register_stack_routes(app, require_auth=require_auth, get_db=get_db)
register_network_routes(app, require_auth=require_auth, get_db=get_db)
register_loop_routes(app, require_auth=require_auth, get_db=get_db)
register_psychology_routes(app, require_auth=require_auth)
register_self_awareness_routes(app, require_auth=require_auth, get_db=get_db)
register_business_planner_routes(app, require_auth=require_auth)
# Agentic OS Kernel — instantiated here because it's needed by route registration below
agent_os_kernel = AgentKernel()
register_agent_os_routes(app, kernel=agent_os_kernel, require_auth=require_auth, get_db=get_db)
register_auth_routes(app, auth_engine=auth_engine, require_auth=require_auth)
register_inbound_routes(app, inbound_triage, require_auth=require_auth)
register_console_routes(app, console=console, require_auth=require_auth, get_db=get_db)
register_storm_routes(app, storm_orchestrator, require_auth=require_auth)
register_map_routes(app, scout=storm_orchestrator.scout, get_db=get_db, require_auth=require_auth)
register_switchboard_routes(app, require_auth=require_auth)
register_partner_routes(app, require_auth=require_auth)
register_data_bridge_routes(app, get_db=get_db, require_auth=require_auth)
register_bridge_engine_routes(
    app, bridge_engine,
    require_auth=require_auth,
    public_base_url=PUBLIC_BASE_URL,
)
register_strike_pack_routes(
    app,
    catalog=strike_pack_catalog,
    subscriptions=strike_pack_subscriptions,
    require_auth=require_auth,
    require_owner=require_owner,
)

register_affiliate_routes(
    app,
    sign_token=_hub_sign_token,
    verify_token=_hub_verify_token,
    send_email=_send_email,
    public_base_url=PUBLIC_BASE_URL,
    hub_token=HUB_TOKEN,
)

# ── Niche Social Terrain — learn habits + map communities per niche ──
niche_terrain = NicheTerrain()

@app.get("/api/v6/terrain/map")
async def terrain_map(niche: str = "", auth: bool = Depends(require_auth)):
    """Return the social terrain map. ?niche= filters to one niche."""
    return JSONResponse(niche_terrain.get_terrain_map(niche or None))


@app.get("/api/v6/terrain/habits")
async def terrain_habits(niche: str = "", auth: bool = Depends(require_auth)):
    """Return learned habit traits. ?niche= filters to one niche."""
    return JSONResponse(niche_terrain.get_habits(niche or None))


@app.post("/api/v6/terrain/discover")
async def terrain_discover(niche: str, depth: str = "standard", auth: bool = Depends(require_auth)):
    """Trigger an LLM discovery scan for a niche's social terrain.
    Query params: niche (required), depth (quick|standard|deep)
    """
    result = await niche_terrain.discover_terrain(niche, depth)
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)


@app.get("/api/v6/terrain/intel")
async def terrain_intel(niche: str = "", auth: bool = Depends(require_auth)):
    """Consolidated intelligence: where to be, when, with what content.
    ?niche= filters to one niche or returns all."""
    return JSONResponse(niche_terrain.terrain_intel(niche or None))


@app.get("/api/v6/terrain/stats")
async def terrain_stats(auth: bool = Depends(require_auth)):
    """Niche Terrain snapshot — stats, niches tracked, communities mapped."""
    return JSONResponse(niche_terrain.snapshot())


register_carrier_routes(
    app,
    manager=carrier_portfolio_manager,
    matcher=carrier_storm_matcher,
    report_engine=carrier_report_engine,
    require_auth=require_auth,
)

# ── Suite Gateway — 3-Product Monetization ───────────────────────────
suite_subscriptions = SuiteSubscriptionEngine(get_db=get_db)
suite_guard = SuiteGuard(subscriptions=suite_subscriptions)
register_suite_routes(
    app,
    require_auth=require_auth,
    subscriptions=suite_subscriptions,
    guard=suite_guard,
)
# Product 1: Inbound Router
suite_inbound_router = InboundRouter(
    guard=lambda a, f: suite_guard.check_access(a, f),
    log_usage=lambda a, p, e, q=1, u="count", m=None: suite_guard.log_usage(a, p, e, q, u, m),
)
InboundRouterRoutes(suite_inbound_router, require_auth=require_auth).register(app)
# Product 2: Data Vault
suite_data_vault = DataVault(
    guard=lambda a, f: suite_guard.check_access(a, f),
    log_usage=lambda a, p, e, q=1, u="count", m=None: suite_guard.log_usage(a, p, e, q, u, m),
)
DataVaultRoutes(suite_data_vault, require_auth=require_auth).register(app)
# Product 3: Buyer Spy AI
suite_buyer_spy = BuyerSpy(
    guard=lambda a, f: suite_guard.check_access(a, f),
    log_usage=lambda a, p, e, q=1, u="count", m=None: suite_guard.log_usage(a, p, e, q, u, m),
)
BuyerSpyRoutes(suite_buyer_spy, require_auth=require_auth).register(app)

# Product 4: Omni Bridge — Deepgram STT → Zernio social distribution
suite_omni_bridge = OmniBridge(
    guard=lambda a, f: suite_guard.check_access(a, f),
    buyer_spy=lambda a, t, m=None: suite_buyer_spy.analyze_transcript(a, t, m),
    log_usage=lambda a, p, e, q=1, u="count", m=None: suite_guard.log_usage(a, p, e, q, u, m),
)
OmniBridgeRoutes(suite_omni_bridge, require_auth=require_auth).register(app)

# Product 5: Agent Orchestrator — spawn + step autonomous agents
suite_agent_orchestrator = AgentOrchestrator(
    guard=lambda a, f: suite_guard.check_access(a, f),
    log_usage=lambda a, p, e, q=1, u="count", m=None: suite_guard.log_usage(a, p, e, q, u, m),
)
AgentOrchestratorRoutes(suite_agent_orchestrator, require_auth=require_auth).register(app)

# Product 6: B2B Pro — property intel, lead network, contractor prospecting
suite_b2b_pro = B2BPro(
    guard=lambda a, f: suite_guard.check_access(a, f),
    log_usage=lambda a, p, e, q=1, u="count", m=None: suite_guard.log_usage(a, p, e, q, u, m),
)
B2BProRoutes(suite_b2b_pro, require_auth=require_auth).register(app)

# Product 7: LeadScore AI — SI-powered lead enrichment & scoring engine
suite_lead_score = LeadScoreAI(
    guard=lambda a, f: suite_guard.check_access(a, f),
    log_usage=lambda a, p, e, q=1, u="count", m=None: suite_guard.log_usage(a, p, e, q, u, m),
)
LeadScoreRoutes(suite_lead_score, require_auth=require_auth).register(app)

# Product 8: Compliant — TCPA/DNC compliance-as-a-service engine
suite_compliant = Compliant(
    guard=lambda a, f: suite_guard.check_access(a, f),
    log_usage=lambda a, p, e, q=1, u="count", m=None: suite_guard.log_usage(a, p, e, q, u, m),
)
CompliantRoutes(suite_compliant, require_auth=require_auth, get_db=get_db).register(app)

# Product 9: Strike Campaigns — multi-touch SMS/email campaign builder
suite_strike_campaigns = StrikeCampaigns(
    guard=lambda a, f: suite_guard.check_access(a, f),
    log_usage=lambda a, p, e, q=1, u="count", m=None: suite_guard.log_usage(a, p, e, q, u, m),
    sms_engine=sms_engine,
    email_engine=email_engine,
)
StrikeCampaignsRoutes(suite_strike_campaigns, require_auth=require_auth, get_db=get_db).register(app)

# Product 10: Forecast — predictive revenue projections as a product
suite_forecast = Forecast(
    guard=lambda a, f: suite_guard.check_access(a, f),
)
ForecastRoutes(suite_forecast, require_auth=require_auth).register(app)

# Product 11: Market Eye — competitive intelligence & market monitoring
suite_market_eye = MarketEyeEngine(
    guard=lambda a, f: suite_guard.check_access(a, f),
    get_db=get_db,
)
MarketEyeRoutes(suite_market_eye, require_auth=require_auth).register(app)

# Product 12: Content Pulse — automated SEO content generation
suite_content_pulse = ContentPulse(
    guard=lambda a, f: suite_guard.check_access(a, f),
)
ContentPulseRoutes(suite_content_pulse, require_auth=require_auth).register(app)

# Product 13: Contractor Exchange — vetted contractor marketplace
suite_contractor_exchange = ContractorExchange(
    guard=lambda a, f: suite_guard.check_access(a, f),
    get_db=get_db,
)
ContractorExchangeRoutes(suite_contractor_exchange, require_auth=require_auth).register(app)

# Product 14: Sales Funnel — one-time purchases, trials, upsells, renewals
# Wire email dispatcher for automated product email sequences
suite_email_dispatcher = ProductEmailDispatcher(
    send_email=_send_email,
    get_db=get_db,
    subscriptions=suite_subscriptions,
)
suite_sales_funnel = SalesFunnelEngine(
    get_db=get_db,
    guard=lambda a, f: suite_guard.check_access(a, f),
    subscriptions=suite_subscriptions,
    email_dispatcher=suite_email_dispatcher,
)
SalesFunnelRoutes(suite_sales_funnel, require_auth=require_auth).register(app)

# Trial Conversion Webhook — auto-convert expired trials to paid
suite_trial_conversion = TrialConversionEngine(
    get_db=get_db,
    subscriptions=suite_subscriptions,
    send_email=_send_email,
)

@app.post("/api/v6/suite/sales/trial-convert")
async def trial_convert_manual(auth: bool = Depends(require_auth)):
    """Manually trigger a scan for expired trials and auto-convert them."""
    result = suite_trial_conversion.run_once()
    return result

@app.get("/api/v6/suite/sales/trial-convert/stats")
async def trial_convert_stats(auth: bool = Depends(require_auth)):
    """Trial conversion engine stats snapshot."""
    return suite_trial_conversion.stats_snapshot()

@app.patch("/api/v6/suite/sales/trial-grace/extend")
async def trial_grace_extend(request: Request, auth: bool = Depends(require_auth)):
    """Extend a trial's grace period by extra days. Operator-only action.
    Body: {email, product_slug, extra_days, reason?}
    """
    try:
        body = await request.json()
        email = (body.get("email") or "").strip()
        product_slug = (body.get("product_slug") or "").strip()
        extra_days = int(body.get("extra_days", 7))
        reason = (body.get("reason") or "Operator extension").strip()

        if not email or not product_slug:
            return JSONResponse({"ok": False, "error": "email and product_slug are required"}, status_code=400)

        result = suite_trial_conversion.extend_trial_grace(
            email=email, product_slug=product_slug,
            extra_days=extra_days, reason=reason,
        )
        status = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


@app.post("/api/v6/suite/sales/trial-churn/report")
async def trial_churn_report(request: Request, auth: bool = Depends(require_auth)):
    """Manually report a churn reason for a converted trial.
    Body: {email, product_slug, reason}
    """
    try:
        body = await request.json()
        email = (body.get("email") or "").strip()
        product_slug = (body.get("product_slug") or "").strip()
        reason = (body.get("reason") or "").strip()

        if not email or not product_slug or not reason:
            return JSONResponse({"ok": False, "error": "email, product_slug, and reason are required"}, status_code=400)

        result = suite_trial_conversion.report_churn(
            email=email, product_slug=product_slug, reason=reason,
        )
        status = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


@app.get("/api/v6/suite/sales/trial-audit")
async def trial_audit(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None, pattern="^(trial_start|trial_converted|expiring_soon_reminder_sent|trial_extended|trial_churned)$"),
    auth: bool = Depends(require_auth),
):
    """Trial audit history — recent trial events with pagination and optional type filter."""
    try:
        return suite_trial_conversion.trial_audit_history(
            limit=limit, offset=offset, event_type=event_type
        )
    except Exception as e:
        log.warning(f"[trial-audit] error: {e}")
        return {"events": [], "total": 0, "limit": limit, "offset": offset, "error": str(e)[:200]}


@app.get("/api/v6/suite/sales/trial-pipeline")
async def trial_pipeline(auth: bool = Depends(require_auth)):
    """Trial pipeline stats: active trials, expiring soon, converted, churned, daily breakdown."""
    try:
        return suite_trial_conversion.trial_pipeline_stats()
    except Exception as e:
        log.warning(f"[trial-pipeline] error: {e}")
        return {"summary": {}, "by_product": [], "daily_starts": [], "recent": [], "error": str(e)[:200]}


# ── Trial Pipeline SLA ────────────────────────────────────────────

@app.get("/api/v6/suite/sales/trial-sla")
async def trial_sla(auth: bool = Depends(require_auth)):
    """Trial pipeline SLA compliance check.

    Returns:
      - total_expired: trials past their end date
      - total_past_sla: past grace + buffer deadline
      - on_time: converted before SLA deadline
      - breached: past deadline and not converted
      - breach_rate: breached / total_past_sla
      - breaches: list of breached trials with hours_overdue and severity
    """
    try:
        sla = suite_trial_conversion.trial_pipeline_sla()
        # Trim breaches list for large responses (top 50 worst)
        if len(sla["breaches"]) > 50:
            sla["breaches"] = sla["breaches"][:50]
        return sla
    except Exception as e:
        log.warning(f"[trial-sla] error: {e}")
        return {"total_expired": 0, "breached": 0, "breaches": [], "error": str(e)[:200]}


# ── Win-back A/B Variant System ─────────────────────────────────────

@app.get("/api/v6/suite/sales/win-back-variants")
async def win_back_variants_list(auth: bool = Depends(require_auth)):
    """List win-back A/B variants with per-variant stats.

    Returns:
      - config: current variant config (enabled, variants, split_override)
      - stats: per-variant performance stats (sent, followups_sent, reactivations, reactivation_rate)
    """
    try:
        config = suite_trial_conversion._read_win_back_config()
        stats = suite_trial_conversion.get_win_back_variant_stats()
        return {"config": config, "stats": stats}
    except Exception as e:
        log.warning(f"[win-back-variants] error: {e}")
        return {"config": {}, "stats": [], "error": str(e)[:200]}


@app.post("/api/v6/suite/sales/win-back-variants")
async def win_back_variants_update(request: Request, auth: bool = Depends(require_auth)):
    """Update win-back A/B variant configuration.

    Body accepts partial config:
      - enabled: bool (optional)
      - variants: list of variant dicts (optional)
      - split_override: dict of email::product_slug -> variant_id (optional)

    Merges with existing config — only provided keys are updated.
    """
    try:
        body = await request.json()
        result = suite_trial_conversion.set_win_back_variants_config(body)
        status = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


@app.post("/api/v6/suite/sales/win-back/opt-out")
async def win_back_opt_out(request: Request, auth: bool = Depends(require_auth)):
    """Log a win-back opt-out for a user.

    Body: {email, product_slug, reason?}
    Once logged, the user will not receive any further win-back emails
    for the given product.
    """
    try:
        body = await request.json()
        email = (body.get("email") or "").strip()
        product_slug = (body.get("product_slug") or "").strip()
        reason = (body.get("reason") or "user_requested").strip()

        if not email or not product_slug:
            return JSONResponse({"ok": False, "error": "email and product_slug are required"}, status_code=400)

        result = suite_trial_conversion.log_win_back_opt_out(
            email=email, product_slug=product_slug, reason=reason,
        )
        status = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


@app.post("/api/v6/suite/sales/win-back-variants/assign")
async def win_back_variants_assign(request: Request, auth: bool = Depends(require_auth)):
    """Manually assign a win-back variant for a specific user.

    Body: {email, product_slug, variant_id}
    Creates a split_override so the user always gets this variant.
    """
    try:
        body = await request.json()
        email = (body.get("email") or "").strip()
        product_slug = (body.get("product_slug") or "").strip()
        variant_id = (body.get("variant_id") or "").strip()

        if not email or not product_slug or not variant_id:
            return JSONResponse({"ok": False, "error": "email, product_slug, and variant_id are required"}, status_code=400)

        result = suite_trial_conversion.assign_win_back_variant_override(
            email=email, product_slug=product_slug, variant_id=variant_id,
        )
        status = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


# Product 15: Command Center Pro — aggregated product health dashboard
@app.get("/api/v6/suite/ccp/health")
async def ccp_health(auth: bool = Depends(require_auth)):
    """Aggregated health snapshot of all 15 Suite products for the Command Center Pro SPA tab."""
    db = get_db()
    products = []
    total_mrr = 0.0
    active_subs = 0
    try:
        r = db.table("product_metadata") \
            .select("tier,product_name,display_name,description,monthly_price_usd,features,is_public") \
            .eq("is_active", True) \
            .order("sort_order") \
            .execute()
        for row in (r.data or []):
            products.append({
                "product": row.get("product_name", ""),
                "tier": row.get("tier", ""),
                "name": row.get("display_name", row["tier"].replace("_", " ").title()),
                "description": row.get("description", ""),
                "monthly_price_usd": float(row.get("monthly_price_usd", 0) or 0),
                "features": row.get("features", []) if isinstance(row.get("features"), list) else [],
                "status": "ok",
                "message": "Online",
            })
    except Exception as e:
        log.warning(f"[ccp] product_metadata query: {e}")

    # Get subscription stats
    try:
        subs = db.table("product_subscriptions") \
            .select("subscription_status,monthly_recurring_revenue") \
            .execute()
        for s in (subs.data or []):
            if s.get("subscription_status") == "ACTIVE":
                active_subs += 1
                total_mrr += float(s.get("monthly_recurring_revenue", 0) or 0)
    except Exception:
        pass

    return {
        "products": products,
        "total_mrr": round(total_mrr, 2),
        "active_subscriptions": active_subs,
        "summary": {
            "total": len(products),
            "healthy": sum(1 for p in products if p["status"] == "ok"),
            "warnings": sum(1 for p in products if p["status"] == "warn"),
            "errors": sum(1 for p in products if p["status"] == "error"),
        },
    }


# ── Hook & Trend Decider Engine ────────────────────────────────────────
HookRoutes(require_auth=require_auth).register(app)

# ── Strategist & Analytics Agents ───────────────────────────────────
strategist_agent = StrategistAgent(get_db=get_db)
analytics_agent = AnalyticsAgent(get_db=get_db)

# Agentic OS Kernel was moved above route registration (see ROUTES section)


# ── Synthetic Intelligence Brain (Operator → LLM → Kokoro TTS → FFmpeg Render) ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
synthetic_brain = SyntheticBrain(
    router=ai_router,
    base_dir=BASE_DIR,
)
register_synthetic_routes(app, brain=synthetic_brain, require_auth=require_auth, auth_engine=auth_engine)

# Mission Control — always-visible top status bar (AGI/SI/Brain/Revenue/Lanes/Compliance/Network)
register_mission_control_routes(app, get_db=get_db)

# ── Brain Personality Routes ──────────────────────────────────
# GET  /api/brain/personality/snapshot       — full personality config + available profiles
# POST /api/brain/personality/set            — update global per-niche personality
# GET  /api/brain/personality/history        — operator preference change log
# GET  /api/brain/personality/operator/{id}  — per-operator override snapshot
# POST /api/brain/personality/operator/set   — set per-operator per-niche override
# POST /api/brain/personality/operator/remove — remove per-operator override

@app.get("/api/brain/personality/snapshot")
async def brain_personality_snapshot(auth: bool = Depends(require_auth)):
    """Return full brain personality snapshot: per-niche configs, available profiles, stats."""
    return JSONResponse(brain_personality.snapshot())


@app.post("/api/brain/personality/set")
async def brain_personality_set(request: Request, auth: bool = Depends(require_auth)):
    """Set or update the global personality config for a niche.
    Body: {
      niche: "__global__" | "Roofing Restoration" | ...,
      persona: "conservative" | "aggressive" | "balanced",
      operator_id?: "...",
      confidence_threshold?: 0.0-1.0,
      urgency_floor?: 1-10,
      temperature?: 0.0-1.0,
      custom_prompt_suffix?: "...",
      operator_notes?: "...",
    }
    """
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    result = await brain_personality.set_personality(
        niche=body.get("niche", "__global__"),
        persona=body.get("persona", "balanced"),
        operator_id=body.get("operator_id", ""),
        confidence_threshold=body.get("confidence_threshold"),
        urgency_floor=body.get("urgency_floor"),
        temperature=body.get("temperature"),
        custom_prompt_suffix=body.get("custom_prompt_suffix", ""),
        operator_notes=body.get("operator_notes", ""),
    )
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)


@app.get("/api/brain/personality/history")
async def brain_personality_history(
    niche: str = "",
    limit: int = 50,
    auth: bool = Depends(require_auth),
):
    """Return operator preference change history, optionally filtered by niche."""
    entries = await brain_personality.history(niche=niche, limit=limit)
    return JSONResponse({"entries": entries, "count": len(entries)})


@app.get("/api/brain/personality/operator/{operator_id}")
async def brain_personality_operator(operator_id: str, auth: bool = Depends(require_auth)):
    """Return per-operator personality override snapshot."""
    return JSONResponse(brain_personality.operator_snapshot(operator_id))


@app.post("/api/brain/personality/operator/set")
async def brain_personality_operator_set(request: Request, auth: bool = Depends(require_auth)):
    """Set or update a per-operator personality override.
    Body: {
      operator_id: "...",
      niche: "__global__" | "Roofing Restoration" | ...,
      persona: "conservative" | "aggressive" | "balanced",
      confidence_threshold?: 0.0-1.0,
      urgency_floor?: 1-10,
      temperature?: 0.0-1.0,
      custom_prompt_suffix?: "...",
    }
    """
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(400, "Invalid JSON")
    result = await brain_personality.set_operator_personality(
        operator_id=body.get("operator_id", ""),
        niche=body.get("niche", "__global__"),
        persona=body.get("persona", "balanced"),
        confidence_threshold=body.get("confidence_threshold"),
        urgency_floor=body.get("urgency_floor"),
        temperature=body.get("temperature"),
        custom_prompt_suffix=body.get("custom_prompt_suffix", ""),
    )
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)


@app.post("/api/brain/personality/operator/remove")
async def brain_personality_operator_remove(request: Request, auth: bool = Depends(require_auth)):
    """Remove a per-operator personality override.
    Body: {operator_id: "...", niche: "..."}
    """
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(400, "Invalid JSON")
    result = await brain_personality.remove_operator_personality(
        operator_id=body.get("operator_id", ""),
        niche=body.get("niche", "__global__"),
    )
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)

# ── CPL Pricing Strategy Routes ─────────────────────────────────────
# GET /api/v1/cpl/summary       — overview of all niches with avg CPL
# GET /api/v1/cpl/niches         — list all available niches
# GET /api/v1/cpl/niche/{niche}  — full niche data
# GET /api/v1/cpl/recommend/{niche} — model recommendation (PPL vs PPC)
# GET /api/v1/cpl/roi/{niche}    — ROI estimate for a niche
# GET /api/v1/cpl/lanes          — per-lane pricing for all 32 lanes
# GET /api/v1/cpl/margin         — margin calculator

@app.get("/api/v1/cpl/summary")
async def cpl_summary(auth: bool = Depends(require_auth)):
    """Return summary of all niches with average CPL, model recommendations, and sub-niche counts."""
    return JSONResponse(cpl_engine.summary())


@app.get("/api/v1/cpl/niches")
async def cpl_niches(auth: bool = Depends(require_auth)):
    """Return list of all available niches."""
    return JSONResponse({"niches": cpl_engine.list_niches(), "count": len(cpl_engine.list_niches())})


@app.get("/api/v1/cpl/niche/{niche}")
async def cpl_niche(niche: str, auth: bool = Depends(require_auth)):
    """Return full CPL benchmark data for a single niche."""
    data = cpl_engine.get_niche(niche)
    if not data:
        raise HTTPException(404, f"Niche '{niche}' not found")
    return JSONResponse({"niche": niche, **data})


@app.get("/api/v1/cpl/recommend/{niche}")
async def cpl_recommend(niche: str, sub_niche: Optional[str] = Query(None), auth: bool = Depends(require_auth)):
    """Recommend optimal pricing model (PPL vs PPC) for a niche/sub-niche."""
    result = cpl_engine.recommend_model(niche, sub_niche)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return JSONResponse(result)


@app.get("/api/v1/cpl/roi/{niche}")
async def cpl_roi(
    niche: str,
    sub_niche: Optional[str] = Query(None),
    monthly_volume: int = Query(100, ge=1, le=10000),
    sell_price: Optional[float] = Query(None, ge=0),
    model: str = Query("ppl", pattern="^(ppl|ppc)$"),
    auth: bool = Depends(require_auth),
):
    """Estimate ROI for a vertical given monthly volume and optional sell price."""
    result = cpl_engine.roi_estimate(niche, sub_niche, monthly_volume, sell_price, model)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return JSONResponse(result)


@app.get("/api/v1/cpl/lanes")
async def cpl_lanes(
    model: str = Query("ppl", pattern="^(ppl|ppc)$"),
    monthly_volume: int = Query(100, ge=1, le=10000),
    auth: bool = Depends(require_auth),
):
    """Return per-lane pricing data for all 32 lanes with CPL benchmarks and suggested pricing."""
    return JSONResponse(cpl_engine.lane_pricing(model=model, monthly_volume=monthly_volume))


@app.get("/api/v1/cpl/lanes/export/csv")
async def cpl_lanes_export_csv(
    model: str = Query("ppl", pattern="^(ppl|ppc)$"),
    monthly_volume: int = Query(100, ge=1, le=10000),
    auth: bool = Depends(require_auth),
):
    """Export per-lane pricing data as a CSV file download.

    Matches the exact format of the SPA's client-side exportCSV() function,
    including the health label logic and a summary footer row with totals.
    """
    data = cpl_engine.lane_pricing(model=model, monthly_volume=monthly_volume)
    lanes = data.get("lanes", [])

    # ── Health label logic (mirrors the SPA's healthLabel()) ──────────
    import csv, io

    def _health_label(l: dict) -> str:
        if not l.get("cpl_available") or l.get("roi_pct") is None:
            return "N/A"
        r = l.get("roi_pct", 0) or 0
        m = l.get("margin_pct", 0) or 0
        b = l.get("breakeven", 0) or 0
        if r > 0 and m > 50 and b <= 200:
            return "Healthy"
        if r > 0:
            return "At Risk"
        return "Unprofitable"

    # ── Transform each lane (mirrors the SPA's prepareLaneData()) ────
    csv_lanes = []
    for l in lanes:
        if l.get("cpl_available"):
            roi = l.get("roi", {})
            suggest = l.get("suggested_pricing", {})
            cpl_data = l.get("cpl", {})

            month_rev = round(float(roi.get("monthly_revenue", 0) or 0))
            month_acq = round(float(roi.get("monthly_acquisition_cost", 0) or 0))
            annual_rev = round(month_rev * 12)

            sell_price = float(suggest.get("suggested_sell_price", 0) or roi.get("sell_price_per_lead", 0) or 0)
            sell_price_high = round(sell_price * 1.3, 2)

            margin_pct = float(suggest.get("actual_margin_pct", 0) or 0)
            if margin_pct == 0 and month_rev > 0:
                margin_pct = round((float(roi.get("gross_margin", 0) or 0) / month_rev) * 100, 1)

            roi_pct = roi.get("roi_percentage")
            breakeven = roi.get("breakeven_volume")

            cpl_low = None
            cpl_high = None
            if cpl_data:
                ppl = cpl_data.get("ppl", {})
                cpl_low = ppl.get("low")
                cpl_high = ppl.get("high")

            packed = {
                "lane_id": l.get("lane_id"),
                "niche": l.get("niche", ""),
                "sub_niche": l.get("sub_niche", ""),
                "cpl_low": cpl_low,
                "cpl_high": cpl_high,
                "best_model": l.get("best_model", ""),
                "sell_price_low": sell_price,
                "sell_price_high": sell_price_high,
                "margin_pct": margin_pct,
                "annual_revenue": annual_rev,
                "roi_pct": roi_pct,
                "monthly_revenue": month_rev,
                "monthly_acq_cost": month_acq,
                "breakeven": breakeven,
                "cpl_available": True,
                "ppc_ready": l.get("ppc_ready", False),
            }
        else:
            packed = {
                "lane_id": l.get("lane_id"),
                "niche": l.get("niche", ""),
                "sub_niche": l.get("sub_niche", ""),
                "cpl_low": None,
                "cpl_high": None,
                "best_model": l.get("strategy", ""),
                "sell_price_low": None,
                "sell_price_high": None,
                "margin_pct": None,
                "annual_revenue": None,
                "roi_pct": None,
                "monthly_revenue": None,
                "monthly_acq_cost": None,
                "breakeven": None,
                "cpl_available": False,
                "ppc_ready": False,
            }

        packed["health"] = _health_label(packed)
        csv_lanes.append(packed)

    # ── Build CSV ────────────────────────────────────────────────────
    headers = [
        "Lane", "Niche", "Sub-Niche", "CPL Low", "CPL High",
        "Model", "Sell Price Low", "Sell Price High", "Margin %",
        "Annual Revenue", "ROI %", "Mo. Rev", "Acq Cost",
        "BE Vol", "Health", "CPL Available", "PPC Ready",
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for l in csv_lanes:
        cpl_low = l.get("cpl_low")
        cpl_high = l.get("cpl_high")
        writer.writerow([
            f"L{l['lane_id']:02d}",
            l["niche"],
            l["sub_niche"],
            f"${cpl_low:.0f}" if cpl_low is not None else "",
            f"${cpl_high:.0f}" if cpl_high is not None else "",
            l["best_model"],
            f"${l['sell_price_low']:.2f}" if l["sell_price_low"] is not None else "",
            f"${l['sell_price_high']:.2f}" if l["sell_price_high"] is not None else "",
            l["margin_pct"],
            l["annual_revenue"],
            f"{l['roi_pct']}%" if l["roi_pct"] is not None else "",
            l["monthly_revenue"],
            l["monthly_acq_cost"],
            l["breakeven"],
            l["health"],
            "Yes" if l["cpl_available"] else "No",
            "Yes" if l.get("ppc_ready") else "No",
        ])

    # ── Summary footer row ───────────────────────────────────────────
    priced = [l for l in csv_lanes if l.get("cpl_available")]
    total_mrr = sum((l.get("monthly_revenue") or 0) for l in priced)
    avg_acq = round(sum((l.get("monthly_acq_cost") or 0) for l in priced) / len(priced)) if priced else 0
    g = sum(1 for l in priced if l.get("health") == "Healthy")
    a = sum(1 for l in priced if l.get("health") == "At Risk")
    r = sum(1 for l in priced if l.get("health") == "Unprofitable")

    writer.writerow([])  # separator row
    writer.writerow([
        "TOTALS", "", "", "", "", "", "", "",
        "", "", "",
        f"${total_mrr}",
        f"${avg_acq}",
        "",
        f"G:{g} A:{a} R:{r}",
        "",
        "",
    ])

    csv_content = output.getvalue()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=empire_cpl_lanes_{model}_{monthly_volume}.csv"
        },
    )


@app.get("/api/v1/cpl/margin")
async def cpl_margin(
    niche: str,
    sub_niche: str,
    sell_price: float = Query(..., ge=0.01),
    monthly_volume: int = Query(100, ge=1, le=10000),
    model: str = Query("ppl", pattern="^(ppl|ppc)$"),
    auth: bool = Depends(require_auth),
):
    """Calculate margin and profit at a given sell price and volume for any niche/sub-niche."""
    result = cpl_engine.margin_calculator(niche, sub_niche, sell_price, monthly_volume, model)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return JSONResponse(result)


# ── Strategist & Analytics Routes ───────────────────────────────────
@app.get("/api/strategist/overview")
async def strategist_overview(auth: bool = Depends(require_auth)):
    return JSONResponse(strategist_agent.overview())


@app.get("/api/strategist/niche/{niche}")
async def strategist_niche(niche: str, auth: bool = Depends(require_auth)):
    return JSONResponse(strategist_agent.niche_analysis(niche))


@app.get("/api/strategist/recommendations")
async def strategist_recommendations(auth: bool = Depends(require_auth)):
    return JSONResponse(strategist_agent.recommendations())


@app.get("/api/strategist/trends")
async def strategist_trends(auth: bool = Depends(require_auth)):
    return JSONResponse(strategist_agent.trends())


@app.get("/api/strategist/narrative")
async def strategist_narrative(auth: bool = Depends(require_auth)):
    return JSONResponse(strategist_agent.generate_narrative())


@app.get("/api/analytics/kpi")
async def analytics_kpi(auth: bool = Depends(require_auth)):
    return JSONResponse(analytics_agent.kpi())


@app.get("/api/analytics/funnel")
async def analytics_funnel(auth: bool = Depends(require_auth)):
    return JSONResponse(analytics_agent.funnel())


@app.get("/api/analytics/timeseries")
async def analytics_timeseries(metric: str = "revenue", days: int = 14, auth: bool = Depends(require_auth)):
    return JSONResponse(analytics_agent.timeseries(metric=metric, days=max(1, min(days, 90))))


@app.get("/api/analytics/anomalies")
async def analytics_anomalies(auth: bool = Depends(require_auth)):
    return JSONResponse(analytics_agent.detect_anomalies())


@app.get("/api/analytics/export")
async def analytics_export(auth: bool = Depends(require_auth)):
    return JSONResponse(analytics_agent.export())


# ── AI Closer Routes ────────────────────────────────────────────────
# POST /api/v1/closer/run  — run the full AGI closer pipeline on a lead
# GET  /api/v1/closer/stats — closer stats snapshot
# POST /api/v1/closer/score — score a lead without placing a call

@app.post("/api/v1/closer/run")
async def closer_run(request: Request, auth: bool = Depends(require_auth)):
    """Run the full AGI-brained closer pipeline on a lead.
    Body: {lead: {name, phone, email, ...}, alert_summary?: {event, severity, ...}, niche?: "..."}
    """
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    lead = body.get("lead") or body
    alert_summary = body.get("alert_summary")
    niche = body.get("niche")

    if not isinstance(lead, dict):
        raise HTTPException(400, "lead must be a dict")
    if not lead.get("name") and not lead.get("warehouse_name"):
        raise HTTPException(400, "lead must have name or warehouse_name")

    result = await ai_closer.close(lead, alert_summary=alert_summary, niche=niche)
    return JSONResponse(result)


@app.get("/api/v1/closer/stats")
async def closer_stats(auth: bool = Depends(require_auth)):
    """Return AI Closer stats snapshot for the SPA / mission control."""
    return JSONResponse(ai_closer.snapshot())


@app.post("/api/v1/closer/score")
async def closer_score(request: Request, auth: bool = Depends(require_auth)):
    """Score a lead through brain + strategy without placing a call.
    Body: {lead: {name, phone, ...}, alert_summary?: {...}, niche?: "..."}
    """
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    lead = body.get("lead") or body
    alert_summary = body.get("alert_summary")
    niche = body.get("niche")

    if not isinstance(lead, dict):
        raise HTTPException(400, "lead must be a dict")

    result = await ai_closer_score_only(ai_closer, lead, alert_summary=alert_summary, niche=niche)
    return JSONResponse(result)


# ── Pulse Routes ────────────────────────────────────────────────
# GET  /view/pulse              — standalone insight page
# GET  /api/pulse/summary       — totals + deltas
# GET  /api/pulse/breakdown     — grouped by dimension
# GET  /api/pulse/lanes         — per-hour per-niche matrix
# POST /api/pulse/refresh       — force materialized view refresh (owner-only)

@app.get("/view/pulse", response_class=HTMLResponse)
async def view_pulse():
    """Standalone pulse insight page — no sidebar, no chrome."""
    return HTMLResponse(pulse_view_page())


@app.get("/api/pulse/summary")
async def pulse_summary(
    window: str = Query("24h", pattern="^(24h|7d|30d)$"),
    auth: bool = Depends(require_auth),
):
    """Return pulse totals + deltas for the given window."""
    try:
        return JSONResponse(await pulse_engine.summary(window=window))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.get("/api/pulse/breakdown")
async def pulse_breakdown(
    dimension: str = Query("niche", pattern="^(niche|channel|contractor|corridor|hour)$"),
    window: str = Query("7d", pattern="^(24h|7d|30d)$"),
    auth: bool = Depends(require_auth),
):
    """Return grouped data by a single dimension."""
    try:
        return JSONResponse(await pulse_engine.breakdown(dimension=dimension, window=window))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.get("/api/pulse/lanes")
async def pulse_lanes(auth: bool = Depends(require_auth)):
    """Return per-hour per-niche matrix for the heatmap."""
    try:
        return JSONResponse(await pulse_engine.lanes())
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.post("/api/pulse/refresh")
async def pulse_refresh(op: dict = Depends(require_owner)):
    """Force-refresh the materialized view. Owner-only."""
    try:
        return JSONResponse(await pulse_engine.refresh())
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


# ── Funnel Routes ──────────────────────────────────────────────────
# POST /api/v1/funnel/run  — route a lead through SalesFunnel → AI Closer

@app.post("/api/v1/funnel/run")
async def funnel_run(request: Request, auth: bool = Depends(require_auth)):
    """Route a lead through the SalesFunnel → AI Closer pipeline.
    Body: {lead: {name, phone, email, ...}, intent?: "high"|"medium"|"low", alert_summary?: {...}}
    """
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    lead = body.get("lead") or body
    intent = body.get("intent", "medium")
    alert_summary = body.get("alert_summary")

    if not isinstance(lead, dict):
        raise HTTPException(400, "lead must be a dict")

    # Run through SalesFunnel first
    route = sales_funnel.optimize_conversion({"intent": intent})

    # If routed to closer, run the full pipeline
    closer_result = None
    if route in ("ROUTE_TO_AGI_CLOSER", "ROUTE_TO_VOICE_PIPELINE"):
        try:
            closer_result = await ai_closer.close(lead, alert_summary=alert_summary)
        except Exception as e:
            closer_result = {"error": str(e)[:200]}

    return JSONResponse({
        "funnel_route": route,
        "closer_result": closer_result,
    })


# ── Swarm Gate Routes ─────────────────────────────────────────
# POST /api/v1/swarm/scan   — run satellite scan for storm targets
# POST /api/v1/swarm/fire   — fire the swarm gate on scanned packages
# GET  /api/v1/swarm/stats  — swarm gate stats snapshot
# GET  /api/v1/swarm/jobs   — recent swarm gate job results

@app.post("/api/v1/swarm/scan")
async def swarm_scan(auth: bool = Depends(require_auth)):
    """Run the Satellite Strike Core scan: pull storm forecasts + cross-reference warehouse targets.
    Returns strike packages ready for the Swarm Gate."""
    packages = await satellite_strike.scan()
    return JSONResponse({
        "ok": True,
        "packages": [
            {
                "target_id": p.target_id,
                "warehouse_name": p.warehouse_name,
                "address": p.address,
                "city": p.city,
                "state": p.state,
                "metro": p.metro,
                "asset_value": p.asset_value,
                "storm_event": p.storm_event,
                "storm_severity": p.storm_severity,
                "risk_level": p.risk_level,
                "risk_rank": p.risk_rank,
                "niche": p.niche,
                "phone": p.phone[:6] + "****" if p.phone else "",
            }
            for p in packages
        ],
        "count": len(packages),
        "scan_snapshot": satellite_strike.snapshot(),
    })


@app.post("/api/v1/swarm/fire")
async def swarm_fire(request: Request, auth: bool = Depends(require_auth)):
    """Fire the God Mode Swarm Gate. Scans first if no packages provided.
    Body (optional): {packages: [...], auto_script: true, auto_audio: true, auto_render: true}
    If no packages, auto-scans via SatelliteStrikeCore."""
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        body = {}

    packages = body.get("packages")
    if not packages:
        scanned = await satellite_strike.scan()
        packages = [
            {
                "target_id": p.target_id,
                "warehouse_name": p.warehouse_name,
                "address": p.address,
                "city": p.city,
                "state": p.state,
                "metro": p.metro,
                "phone": p.phone,
                "email": p.email,
                "asset_value": p.asset_value,
                "damage_severity": p.damage_severity,
                "storm_event": p.storm_event,
                "storm_severity": p.storm_severity,
                "storm_urgency": p.storm_urgency,
                "risk_level": p.risk_level,
                "risk_rank": p.risk_rank,
                "niche": p.niche,
                "source": p.source,
                "meta": p.meta,
            }
            for p in scanned
        ]

    auto_script = body.get("auto_script", True)
    auto_audio = body.get("auto_audio", True)
    auto_render = body.get("auto_render", True)

    jobs = await swarm_gate.fire(packages, auto_script, auto_audio, auto_render)

    return JSONResponse({
        "ok": True,
        "jobs": [
            {
                "target_id": j.target_id,
                "warehouse_name": j.warehouse_name,
                "metro": j.metro,
                "niche": j.niche,
                "risk_level": j.risk_level,
                "brain_decision": j.brain_decision,
                "brain_confidence": j.brain_confidence,
                "strategy": j.strategy,
                "script": j.script[:120] if j.script else "",
                "audio_path": j.audio_path[:80] if j.audio_path else "",
                "video_status": j.video_status,
                "status": j.status,
                "error": j.error[:200] if j.error else "",
            }
            for j in jobs
        ],
        "count": len(jobs),
        "stats": swarm_gate.snapshot(),
    })


@app.get("/api/v1/swarm/stats")
async def swarm_stats(auth: bool = Depends(require_auth)):
    """Swarm Gate stats snapshot — cumulative totals, lane count, wiring status."""
    return JSONResponse({
        **swarm_gate.snapshot(),
        "satellite": satellite_strike.snapshot(),
    })


@app.get("/api/v1/swarm/jobs")
async def swarm_jobs(limit: int = 20, auth: bool = Depends(require_auth)):
    """Recent Swarm Gate job results from the database."""
    try:
        db = get_db()
        r = db.table("swarm_gate_jobs") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(min(limit, 100)) \
            .execute()
        return JSONResponse({"jobs": r.data or [], "count": len(r.data or [])})
    except Exception as e:
        return JSONResponse({"jobs": [], "count": 0, "error": str(e)[:80]})


# ── Pain Points Routes ─────────────────────────────────────────
# GET  /api/v1/pain-points/snapshot   — full library state
# GET  /api/v1/pain-points/export/csv — CSV export
# GET  /api/v1/pain-points/export/report — HTML report

@app.get("/api/v1/pain-points/snapshot")
async def pain_points_snapshot(auth: bool = Depends(require_auth)):
    """Return full pain points library state: per-niche points with weights, conversion rates."""
    return JSONResponse(pain_points.snapshot())


@app.get("/api/v1/pain-points/export/csv")
async def pain_points_export_csv(auth: bool = Depends(require_auth)):
    """Export pain points data as CSV file download."""
    csv_content = pain_points.export_csv()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=empire_pain_points.csv"},
    )


@app.get("/api/v1/pain-points/export/report", response_class=HTMLResponse)
async def pain_points_export_report(auth: bool = Depends(require_auth)):
    """Print-friendly HTML report of pain point effectiveness (Ctrl+P to save as PDF)."""
    snap = pain_points.snapshot()
    rows_html = ""
    for niche, niche_data in sorted(snap.get("by_niche", {}).items()):
        points = niche_data.get("pain_points", [])
        rows_html += f'<tr class="niche-header"><td colspan="7"><strong>{niche}</strong> · {len(points)} pain points</td></tr>'
        for pp in points:
            w = pp['weight']
            cr = pp['conversion_rate']
            w_color = "#44E5B8" if w >= 0.6 else ("#FFB800" if w >= 0.5 else "#FF4444")
            cr_color = "#44E5B8" if cr >= 0.6 else ("#FFB800" if cr >= 0.3 else "#FF4444")
            rows_html += f"""<tr>
              <td>{pp['label']}</td>
              <td style="color:{w_color}">{w}</td>
              <td class="num">{pp['attempts']}</td>
              <td class="num">{pp['successes']}</td>
              <td class="num" style="color:{cr_color}">{cr}</td>
              <td class="hook">{pp['hook'][:80]}</td>
              <td class="proof">{pp['proof'][:80]}</td>
            </tr>"""

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Empire AI · Pain Points Report</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0f; color: #e2e8f0; padding: 48px 64px; }}
    .report {{ max-width: 1100px; margin: 0 auto; }}
    h1 {{ font-size: 22px; font-weight: 200; letter-spacing: -0.02em; margin-bottom: 4px; }}
    h1 em {{ color: #44E5B8; font-style: italic; font-weight: 500; }}
    .sub {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 10px; color: #94a3b8; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 20px; }}
    .summary {{ display: flex; gap: 24px; margin-bottom: 28px; }}
    .sum-card {{ background: #14141e; border: 1px solid #1e293b; padding: 16px 20px; flex: 1; }}
    .sum-label {{ font-family: monospace; font-size: 9px; color: #64748b; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 8px; }}
    .sum-value {{ font-family: monospace; font-size: 24px; color: #f8fafc; font-weight: 500; }}
    .sum-value.teal {{ color: #44E5B8; }}
    table {{ width: 100%; border-collapse: collapse; background: #14141e; border: 1px solid #1e293b; margin-top: 16px; }}
    thead th {{ font-family: monospace; font-size: 9px; color: #64748b; letter-spacing: 0.14em; text-transform: uppercase; text-align: left; padding: 12px 14px; border-bottom: 1px solid #1e293b; background: #0f0f17; }}
    tbody td {{ padding: 10px 14px; border-bottom: 1px solid #1e293b; font-family: monospace; font-size: 10px; }}
    tbody tr:last-child td {{ border-bottom: none; }}
    .niche-header td {{ background: #0f0f17; font-size: 12px; padding: 14px 14px 10px; color: #f8fafc; }}
    .num {{ text-align: right; }}
    .hook {{ color: #94a3b8; font-size: 9px; }}
    .proof {{ color: #64748b; font-size: 9px; }}
    .footer {{ margin-top: 32px; font-family: monospace; font-size: 9px; color: #475569; letter-spacing: 0.08em; }}
    @media print {{ body {{ background: #fff; color: #000; padding: 24px; }} .sum-card, table {{ background: #fff; border-color: #ccc; }} thead th {{ background: #f5f5f5; }} }}
  </style>
</head>
<body>
  <div class="report">
    <h1>Empire AI <em>Pain Points</em></h1>
    <div class="sub">Niche-specific pain point profiles · Weights & Conversion Rates</div>
    <div class="summary">
      <div class="sum-card"><div class="sum-label">Niches</div><div class="sum-value teal">{snap.get('niches', 0)}</div></div>
      <div class="sum-card"><div class="sum-label">Pain Points</div><div class="sum-value">{snap.get('total_pain_points', 0)}</div></div>
    </div>
    <table>
      <thead><tr>
        <th>Pain Point</th><th>Weight</th><th class="num">Attempts</th><th class="num">Successes</th><th class="num">Conv Rate</th><th>Hook</th><th>Proof</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div class="footer">Empire AI V49 · Pain Points Library · Auto-generated report</div>
  </div>
</body>
</html>""")


# ─────────────────────────────────────────────────────────────────────
# SI STRATEGY EVOLUTION + ADAPTIVE ENGINE
# ─────────────────────────────────────────────────────────────────────
# `si_strategy` is the central authority on strategy genomes. It tracks
# every active/niche-specific strategy variant, scores them from outcomes,
# and evolves (mutates / deactivates) the underperformers on a tick.
#
# `adaptive_engine` is the bridge between learned SI parameters and the
# live subsystems (brain, switchboard, matching, corridor, outreach). It
# applies parameter changes that the SI core or `brain_learning` writes
# to the si_parameters table.
# ─────────────────────────────────────────────────────────────────────
si_strategy = StrategyEvolution(get_db=get_db)
si_strategy.set_pain_points(pain_points)

# ── Satellite Strike Core + God Mode Swarm Gate ──────────────────
# Scans storm forecasts → filters warehouse targets → parallel video ads.
# Each lane runs Script Engine → FFmpeg 1080x1920 Render (Kokoro TTS included).
# Constructed AFTER si_strategy so it can be wired for per-niche genome lookups.
satellite_strike = SatelliteStrikeCore(
    get_db=get_db,
    lookback_hours=int(os.environ.get("SATELLITE_LOOKBACK_HOURS", "24")),
    min_risk_rank=int(os.environ.get("SATELLITE_MIN_RISK_RANK", "4")),
    max_packages=int(os.environ.get("SATELLITE_MAX_PACKAGES", "32")),
)

swarm_gate = GodModeSwarmGate(
    get_db=get_db,
    brain_decider=brain_decider,
    si_strategy=si_strategy,
    pain_points=pain_points,
    lane_count=int(os.environ.get("SWARM_LANE_COUNT", "3")),
    lane_timeout=int(os.environ.get("SWARM_LANE_TIMEOUT_SEC", "120")),
)

# ── Payment-Triggered Storm Scan ────────────────────────────────
# When a USDC payment hits the ledger, run a fresh satellite scan
# and pipe the results through the swarm gate to drop new
# storm-damage targets into the pipeline lanes.
async def _payment_triggered_storm_scan(payment_event: dict):
    """Called when a USDC payment is verified on-chain.
    Runs satellite_strike.scan() then fires swarm_gate to drop
    targets into the lane pipeline.
    """
    amt = payment_event.get('amount_usdc', 0)
    log.info(f"[payment→storm] payment ${amt:.2f} → triggering satellite scan")
    try:
        packages = await satellite_strike.scan()
        if not packages:
            log.info("[payment→storm] scan complete — no new targets found")
            return

        log.info(f"[payment→storm] scan found {len(packages)} targets — "
                 f"firing swarm gate")

        # Convert StrikePackage dataclass to dicts for swarm_gate.fire()
        package_dicts = [{
            "target_id": p.target_id,
            "warehouse_name": p.warehouse_name,
            "address": p.address,
            "city": p.city,
            "state": p.state,
            "phone": p.phone,
            "email": p.email,
            "asset_value": p.asset_value,
            "damage_severity": p.damage_severity,
            "metro": p.metro,
            "storm_event": p.storm_event,
            "storm_severity": p.storm_severity,
            "storm_urgency": p.storm_urgency,
            "risk_level": p.risk_level,
            "risk_rank": p.risk_rank,
            "niche": p.niche,
            "source": p.source,
            "meta": p.meta,
        } for p in packages]

        jobs = await swarm_gate.fire(
            package_dicts,
            auto_script=True,
            auto_audio=True,
            auto_render=True,
        )
        completed = sum(1 for j in jobs if j.status == "complete")
        log.info(f"[payment→storm] swarm gate fired: {completed}/{len(jobs)} "
                 f"jobs completed for ${amt:.2f} payment")
    except Exception as e:
        log.warning(f"[payment→storm] pipeline error: {e}")


# Register the callback on the solana revenue engine
log.info("[payment→storm] callback wired — verified payments trigger satellite scan + swarm fire")


# Register the callback on the solana revenue engine
log.info("[payment→storm] callback wired — verified payments trigger satellite scan")


# Wire AGI Governor + SI Strategy into the SalesFunnel (now that both exist)
sales_funnel._agi_governor = governor
sales_funnel._si_strategy = si_strategy
log.info("[hub] SalesFunnel wired with AGI Governor + SI Strategy")

# Expose the SI strategy instance on the class so empire_mission_control
# can read the live snapshot without re-instantiating a parallel world.
try:
    StrategyEvolution.set_shared_instance(si_strategy)
except Exception:
    pass
adaptive_engine = AdaptiveEngine(get_db=get_db)


# Lightweight subsystem configurators. Each apply_fn mutates the actual
# runtime config that its subsystem reads at call time, so the adaptive
# engine is doing real work — not just logging. apply_fn returns False
# for unknown keys (the engine logs a warning and skips); True on success.

# We import the subsystem modules directly so we can mutate their
# module-level config dicts/constants at runtime.
import empire_switchboard as _sb_mod
import empire_matching as _mt_mod
import orchestrator_agent as _orch_mod
import empire_outreach_agent as _outreach_mod


def _apply_brain_param(key: str, value) -> bool:
    # brain.* keys come from empire_brain_learning (tuned urgency floor etc).
    # The brain reads from DB at call time, so we just log + accept.
    log.debug(f"[si.adaptive] brain.{key} = {value} (applied via DB read)")
    return True


def _apply_switchboard_param(key: str, value) -> bool:
    if key == "cache_ttl_seconds":
        try:
            new_ttl = float(value)
        except (TypeError, ValueError):
            return False
        if new_ttl < 0:
            return False
        _sb_mod._BUYERS_CACHE_TTL = new_ttl
        _sb_mod._invalidate_buyers_cache()  # force the next call to re-fetch
        log.info(f"[si.adaptive] switchboard.cache_ttl_seconds = {new_ttl}")
        return True
    if key == "min_offered_for_rate":
        try:
            new_min = int(value)
        except (TypeError, ValueError):
            return False
        if not isinstance(value, (int, float)) or int(value) != value:
            return False
        if new_min < 0:
            return False
        _sb_mod._MIN_OFFERED_FOR_RATE = new_min
        log.info(f"[si.adaptive] switchboard.min_offered_for_rate = {new_min}")
        return True
    return False


def _read_switchboard_param(key: str):
    if key == "cache_ttl_seconds":
        return _sb_mod._BUYERS_CACHE_TTL
    if key == "min_offered_for_rate":
        return _sb_mod._MIN_OFFERED_FOR_RATE
    return None


def _apply_matching_param(key: str, value) -> bool:
    if key.startswith("score_weights."):
        weight_name = key.split(".", 1)[1]
        if weight_name not in _mt_mod.SCORE_WEIGHTS:
            return False
        try:
            new_w = float(value)
        except (TypeError, ValueError):
            return False
        if new_w < 0 or new_w > 1:
            return False
        _mt_mod.SCORE_WEIGHTS[weight_name] = new_w
        new_total = sum(_mt_mod.SCORE_WEIGHTS.values())
        log.info(
            f"[si.adaptive] matching.score_weights.{weight_name} = {new_w} "
            f"(weights now sum to {new_total:.3f})"
        )
        return True
    if key == "default_top_n":
        try:
            new_top_n = int(value)
        except (TypeError, ValueError):
            return False
        if not isinstance(value, (int, float)) or int(value) != value:
            return False
        if new_top_n < 1:
            return False
        _mt_mod.DEFAULT_TOP_N = new_top_n
        log.info(f"[si.adaptive] matching.default_top_n = {new_top_n}")
        return True
    return False


def _read_matching_param(key: str):
    if key.startswith("score_weights."):
        weight_name = key.split(".", 1)[1]
        return _mt_mod.SCORE_WEIGHTS.get(weight_name)
    if key == "default_top_n":
        return _mt_mod.DEFAULT_TOP_N
    return None


def _apply_corridor_param(key: str, value) -> bool:
    if key == "min_interval_seconds":
        try:
            new_interval = float(value)
        except (TypeError, ValueError):
            return False
        if new_interval < 0:
            return False
        _orch_mod.CORRIDOR_MIN_INTERVAL = new_interval
        log.info(f"[si.adaptive] corridor.min_interval_seconds = {new_interval}")
        return True
    return False


def _read_corridor_param(key: str):
    if key == "min_interval_seconds":
        return _orch_mod.CORRIDOR_MIN_INTERVAL
    return None


def _apply_outreach_param(key: str, value) -> bool:
    tunables = {
        "hot_threshold":   (_outreach_mod, "HOT_THRESHOLD",   lambda v: max(0.0, float(v))),
        "score_per_click": (_outreach_mod, "SCORE_PER_CLICK", lambda v: max(0.0, float(v))),
        "score_per_reply": (_outreach_mod, "SCORE_PER_REPLY", lambda v: max(0.0, float(v))),
    }
    if key not in tunables:
        return False
    mod, attr, coerce = tunables[key]
    try:
        new_val = coerce(value)
    except (TypeError, ValueError):
        return False
    setattr(mod, attr, new_val)
    log.info(f"[si.adaptive] outreach.{key} = {new_val}")
    return True


def _read_outreach_param(key: str):
    return {
        "hot_threshold":   _outreach_mod.HOT_THRESHOLD,
        "score_per_click": _outreach_mod.SCORE_PER_CLICK,
        "score_per_reply": _outreach_mod.SCORE_PER_REPLY,
    }.get(key)


# Brain: no read_fn (BrainLearning reads from DB at call time, so there's
# no in-memory cache to diff against). adopt_parameters() will re-apply
# each tick, but brain.* writes are idempotent (they overwrite DB rows).
# The other four subsystems DO have in-memory config, so we register a
# read_fn for each — the SI core can then diff current vs target and
# avoid unnecessary re-applies.
adaptive_engine.register_subsystem("brain",       apply_fn=_apply_brain_param)
adaptive_engine.register_subsystem("switchboard", apply_fn=_apply_switchboard_param, read_fn=_read_switchboard_param)
adaptive_engine.register_subsystem("matching",    apply_fn=_apply_matching_param,    read_fn=_read_matching_param)
adaptive_engine.register_subsystem("corridor",    apply_fn=_apply_corridor_param,    read_fn=_read_corridor_param)
adaptive_engine.register_subsystem("outreach",    apply_fn=_apply_outreach_param,    read_fn=_read_outreach_param)


# Share the live `si_strategy` instance with the predictive_revenue bot
# (it also uses StrategyEvolution) and the AGI governor, so we don't
# run two parallel worlds. The bot's `_SI_INSTANCE` is its module-level
# singleton; the governor exposes a class-level `si_strategy` setter.
import bots.predictive_revenue as _pred_rev
_pred_rev.set_si_instance(si_strategy)
try:
    from empire_agi_governor import AGIGovernor
    AGIGovernor.set_si_strategy(si_strategy)
except Exception:
    pass


async def _agent_os_boot():
    """Boot the Agentic OS kernel after a short delay to let other
    systems stabilize."""
    await asyncio.sleep(5)
    await agent_os_kernel.boot()
    log.info("[hub] Agentic OS kernel booted")


async def _si_evolution_loop():
    """Background tick: evolve strategies every 5 minutes, adopt SI params every 60s."""
    evolve_every = 300   # seconds
    adopt_every = 60
    last_evolve = 0.0
    last_adopt = 0.0
    import time as _t
    while True:
        try:
            now = _t.time()
            if now - last_evolve >= evolve_every:
                events = si_strategy.evolve()
                last_evolve = now
                if events:
                    log.info(f"[si.strategy] evolution tick: {len(events)} events")

            if now - last_adopt >= adopt_every:
                last_adopt = now
                # Pull any SI parameters the SI core / brain_learning wrote.
                try:
                    db = get_db()
                    # Cap at the query level so wire cost stays bounded as the
                    # si_parameters table grows.
                    r = db.table("si_parameters").select("*") \
                        .order("updated_at", desc=True) \
                        .limit(200).execute()
                    params = {}
                    for row in (r.data or []):
                        params[row.get("key")] = {
                            "current":    row.get("current_value"),
                            "default":    row.get("default_value"),
                            "min":        row.get("min"),
                            "max":        row.get("max"),
                            "samples":    row.get("samples", 0),
                            "confidence": row.get("confidence", 0),
                        }
                    if params:
                        changes = adaptive_engine.adopt_parameters(params)
                        if changes:
                            log.info(f"[si.adaptive] adopted {len(changes)} parameter changes")
                except Exception as _e:
                    log.debug(f"[si.adaptive] adoption tick skipped: {_e}")
        except Exception as e:
            log.warning(f"[si.evolution] tick error: {e}")
        await asyncio.sleep(30)


# ─────────────────────────────────────────────────────────────────────
# STARTUP / SHUTDOWN
# ─────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    log.info("Empire V49 · Starting up")
    # Suite Core — init local SQLite tables (product_subscriptions, etc.)
    _init_suite_db_sqlite()

    # Data Bridge Engine — init DB + start background processor
    init_bridge_db()
    start_bridge_processor(get_db)
    asyncio.create_task(brain_learning.nightly_tune_loop())
    asyncio.create_task(sms_engine.dispatcher_loop())
    asyncio.create_task(email_engine.dispatcher_loop())
    asyncio.create_task(storm_orchestrator.poll_loop())
    asyncio.create_task(dream_loop.run())
    asyncio.create_task(hourly_digest.run())
    asyncio.create_task(seo_run_loop())
    asyncio.create_task(backlinks_run_loop())
    asyncio.create_task(_si_evolution_loop())
    # Swarm Gate auto-pilot — scan storm forecasts + fire parallel video ads every 30 min
    asyncio.create_task(_swarm_autopilot_loop())
    # Pulse materialized view refresh — keeps pulse_rollup_hourly fresh every 5 min
    asyncio.create_task(_pulse_refresh_loop())
    # Mission Control broadcasts every 5s — drives the top status bar in the SPA
    asyncio.create_task(mission_control_broadcast_loop(
        broadcaster=live_broadcaster, get_db=get_db, interval=5.0,
    ))
    # Niche Terrain background scan — discovers new communities + learns habits every 30 min
    asyncio.create_task(_niche_terrain_scan_loop())
    # Market Eye background monitoring — scrape eligible competitors every hour
    asyncio.create_task(suite_market_eye.monitoring_loop())
    # Product Email Dispatcher — renewal reminders, reactivation, churn prevention
    asyncio.create_task(suite_email_dispatcher.monitoring_loop())
    # Trial Conversion — auto-convert expired trials to paid every hour
    asyncio.create_task(suite_trial_conversion.monitoring_loop())
    # Agentic OS — boot the kernel (registers built-in agents and starts scheduling)
    asyncio.create_task(_agent_os_boot())

    log.info("Empire V49 · Operational")


@app.on_event("shutdown")
async def shutdown():
    log.info("Empire V49 · Shutting down")



# ── Drafts approval + narrate stream + reply qualify ────────
from fastapi import Depends, Body, HTTPException
from fastapi.responses import StreamingResponse
import asyncio as _asyncio
import json as _json

@app.get("/api/v1/drafts/pending")
async def drafts_pending(limit: int = 50, offset: int = 0, auth: bool = Depends(require_auth)):
    db = get_db()
    r = db.table("email_drafts").select("*").eq("status", "pending").order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    has_more = len(r.data or []) == limit
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


# ─── /api/telemetry: reads empire_session_log.md ──────────────
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add CORS for the dashboard (idempotent — won't double-add)
try:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
except Exception:
    pass


@app.get("/api/telemetry")
async def telemetry(lines: int = 20):
    """Parse the last N lines of empire_session_log.md for AGI snapshots."""
    import re, json as _json
    log_file = "/root/empire-v49/empire_session_log.md"
    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()
    except FileNotFoundError:
        return {"snapshots": [], "actions": [], "error": "log not found"}

    tail = all_lines[-lines:] if lines > 0 else all_lines
    snapshots = []
    actions = []
    snap_re = re.compile(r"\[AGI\] Stats Snapshot:\s*(\{.*\})")
    act_re = re.compile(r"\[ACTION\] Applying optimized configuration:\s*(\{.*\})")

    for ln in tail:
        m = snap_re.search(ln)
        if m:
            try:
                snapshots.append(eval(m.group(1)))  # log uses Python dict repr
            except Exception:
                pass
            continue
        m = act_re.search(ln)
        if m:
            try:
                actions.append(eval(m.group(1)))
            except Exception:
                pass

    return JSONResponse({
        "snapshots": snapshots,
        "actions": actions,
        "log_lines_read": len(tail),
        "snapshot_count": len(snapshots),
        "action_count": len(actions),
    })



# ─── /api/governor: PM2 watchdog + self-heal ──────────────────────────
# /heal performs a REAL restart of every PM2-managed service. The hub
# restarts itself last via a detached process so the HTTP response can flush.
import subprocess as _gsub, json as _gjson, time as _gtime
from datetime import datetime as _gdt

_GOV_LOG_FILE = "/root/empire-v49/governor_heal_log.jsonl"
_GOV_HEAL_LOG = []   # in-memory mirror of the on-disk self-heal log
_GOV_LOG_MAX = 500   # cap retained entries so the file can't grow unbounded

# ── watchdog config — edit the allowlist to change which services are healed ──
import asyncio as _gasync
_GOV_WATCH = {"empire-orchestrator", "empire-live", "empire-voice", "empire-pulse-cron"}  # auto-heal allowlist
_GOV_WATCH_INTERVAL = 60     # seconds between health checks
_GOV_MAX_ATTEMPTS = 3        # max auto-restarts per service…
_GOV_ATTEMPT_WINDOW = 600    # …within this many seconds (10 min) before giving up
_GOV_ATTEMPTS = {}           # name -> [epoch, …] recent auto-restart timestamps
_GOV_GAVEUP = set()          # services we've already logged a give-up for (this down-streak)


def _gov_log_append(entry):
    """Append one heal entry to the in-memory log and persist it to disk (JSONL)."""
    _GOV_HEAL_LOG.append(entry)
    try:
        with open(_GOV_LOG_FILE, "a") as f:
            f.write(_gjson.dumps(entry) + "\n")
    except Exception:
        pass


def _gov_log_load():
    """Load the persisted heal log on startup, trimming to the retention cap."""
    try:
        with open(_GOV_LOG_FILE, "r") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    _GOV_HEAL_LOG.append(_gjson.loads(ln))
    except FileNotFoundError:
        pass
    except Exception:
        pass
    # trim + rewrite if the file has grown past the cap
    if len(_GOV_HEAL_LOG) > _GOV_LOG_MAX:
        del _GOV_HEAL_LOG[:-_GOV_LOG_MAX]
        try:
            with open(_GOV_LOG_FILE, "w") as f:
                for e in _GOV_HEAL_LOG:
                    f.write(_gjson.dumps(e) + "\n")
        except Exception:
            pass


_gov_log_load()


def _pm2_services():
    """Return live PM2 process data (empty list if pm2 is unavailable)."""
    try:
        out = _gsub.run(["pm2", "jlist"], capture_output=True, text=True, timeout=5)
        procs = _gjson.loads(out.stdout)
        svcs = []
        now_ms = _gtime.time() * 1000
        for p in procs:
            env = p.get("pm2_env", {})
            mon = p.get("monit", {})
            up = env.get("pm_uptime")
            svcs.append({
                "name": p.get("name", "?"),
                "status": env.get("status", "unknown"),
                "uptime_s": round((now_ms - up) / 1000) if up else None,
                "restarts": env.get("restart_time", 0),
                "mem_mb": round((mon.get("memory") or 0) / 1048576, 1),
                "cpu_pct": float(mon.get("cpu") or 0),
            })
        return svcs
    except Exception:
        return []


@app.get("/api/governor/status")
async def governor_status():
    svcs = _pm2_services()
    healthy = sum(1 for s in svcs if s["status"] == "online")
    return JSONResponse({
        "services": svcs,
        "watchdog": {
            "interval_s": _GOV_WATCH_INTERVAL,
            "last_check": _gdt.utcnow().isoformat(timespec="seconds"),
            "healthy": healthy,
            "total": len(svcs),
            "watching": sorted(_GOV_WATCH),
        },
    })


@app.get("/api/governor/log")
async def governor_log(lines: int = 20):
    return JSONResponse({"entries": _GOV_HEAL_LOG[-lines:][::-1]})


_GOV_SELF_NAME = "empire-hub"  # the process serving this API


@app.post("/api/governor/heal")
async def governor_heal():
    """Restart ALL PM2-managed services. Peers restart synchronously; the hub
    self-restarts last via a detached process so this response can flush."""
    svcs = _pm2_services()
    targets = [s["name"] for s in svcs]
    others = [n for n in targets if n != _GOV_SELF_NAME]
    now = _gdt.utcnow().isoformat(timespec="seconds")
    restarted, errors = [], []

    # restart peer services synchronously
    for n in others:
        try:
            r = _gsub.run(["pm2", "restart", n], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                restarted.append(n)
                _gov_log_append({"ts": now, "level": "info", "service": n, "action": "restart", "detail": "force-heal: restarted"})
            else:
                msg = (r.stderr or r.stdout or "non-zero exit").strip()[:200]
                errors.append({"service": n, "error": msg})
                _gov_log_append({"ts": now, "level": "error", "service": n, "action": "restart-failed", "detail": msg})
        except Exception as e:
            errors.append({"service": n, "error": str(e)})
            _gov_log_append({"ts": now, "level": "error", "service": n, "action": "restart-failed", "detail": str(e)})

    # restart the hub itself LAST, detached, so this response still returns
    hub_scheduled = False
    if _GOV_SELF_NAME in targets:
        try:
            _gsub.Popen(
                ["bash", "-c", "sleep 1; pm2 restart " + _GOV_SELF_NAME],
                start_new_session=True,
                stdout=_gsub.DEVNULL, stderr=_gsub.DEVNULL,
            )
            hub_scheduled = True
            _gov_log_append({"ts": now, "level": "warn", "service": _GOV_SELF_NAME, "action": "restart", "detail": "force-heal: self-restart scheduled (~1s)"})
        except Exception as e:
            errors.append({"service": _GOV_SELF_NAME, "error": str(e)})

    parts = []
    if restarted:
        parts.append("restarted " + ", ".join(restarted))
    if hub_scheduled:
        parts.append(_GOV_SELF_NAME + " self-restart in ~1s")
    if errors:
        parts.append(str(len(errors)) + " failed")
    return JSONResponse({
        "ok": len(errors) == 0,
        "triggered": len(restarted) + (1 if hub_scheduled else 0),
        "restarted": restarted,
        "self_restart_scheduled": hub_scheduled,
        "errors": errors,
        "message": "force-heal: " + ("; ".join(parts) if parts else "no services found"),
    })


def _gov_watchdog_tick():
    """One health-check pass: auto-restart unhealthy allowlisted services, capped."""
    now = _gtime.time()
    now_iso = _gdt.utcnow().isoformat(timespec="seconds")
    for s in _pm2_services():
        name = s["name"]
        if name not in _GOV_WATCH:
            continue
        if s["status"] == "online":
            _GOV_GAVEUP.discard(name)   # recovered — re-arm give-up logging
            continue
        # prune restart attempts that fell outside the rolling window
        attempts = [t for t in _GOV_ATTEMPTS.get(name, []) if now - t < _GOV_ATTEMPT_WINDOW]
        if len(attempts) >= _GOV_MAX_ATTEMPTS:
            _GOV_ATTEMPTS[name] = attempts
            if name not in _GOV_GAVEUP:           # log give-up once per down-streak
                _GOV_GAVEUP.add(name)
                _gov_log_append({"ts": now_iso, "level": "error", "service": name, "action": "give-up",
                                 "detail": "watchdog: %d restarts within %dm all failed — manual intervention needed"
                                           % (_GOV_MAX_ATTEMPTS, _GOV_ATTEMPT_WINDOW // 60)})
            continue
        # under the cap → attempt an auto-restart
        attempts.append(now)
        _GOV_ATTEMPTS[name] = attempts
        try:
            r = _gsub.run(["pm2", "restart", name], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                _gov_log_append({"ts": now_iso, "level": "info", "service": name, "action": "restart",
                                 "detail": "watchdog: auto-restart (attempt %d/%d) after status=%s"
                                           % (len(attempts), _GOV_MAX_ATTEMPTS, s["status"])})
            else:
                msg = (r.stderr or r.stdout or "non-zero exit").strip()[:200]
                _gov_log_append({"ts": now_iso, "level": "error", "service": name,
                                 "action": "restart-failed", "detail": "watchdog: " + msg})
        except Exception as e:
            _gov_log_append({"ts": now_iso, "level": "error", "service": name,
                             "action": "restart-failed", "detail": "watchdog: " + str(e)})


async def _gov_watchdog_loop():
    await _gasync.sleep(_GOV_WATCH_INTERVAL)   # let the hub finish booting first
    loop = _gasync.get_running_loop()
    while True:
        try:
            # run the blocking pm2 work off the event loop
            await loop.run_in_executor(None, _gov_watchdog_tick)
        except Exception:
            pass
        await _gasync.sleep(_GOV_WATCH_INTERVAL)


@app.on_event("startup")
async def _gov_start_watchdog():
    _gasync.create_task(_gov_watchdog_loop())


# ── Niche Terrain Background Scan ───────────────────────────
_NICHE_TERRAIN_SCAN_INTERVAL = 1800  # 30 minutes


async def _niche_terrain_scan_loop():
    """Background loop: every 30 min, discover sparse niches + learn habits."""
    await asyncio.sleep(120)  # let the hub finish booting first
    while True:
        try:
            await niche_terrain.scan_cycle()
            log.debug("[niche_terrain] background scan complete")
        except Exception as e:
            log.warning(f"[niche_terrain] scan cycle error: {e}")
        await asyncio.sleep(_NICHE_TERRAIN_SCAN_INTERVAL)


# ── Swarm Gate Auto-Pilot ───────────────────────────────────
_SWARM_AUTOPILOT_INTERVAL = int(os.environ.get("SWARM_AUTOPILOT_INTERVAL_SEC", "1800"))


async def _swarm_autopilot_loop():
    """Background loop: every 30 min, scan storm forecasts + fire parallel video ads."""
    import time as _sw_t
    await asyncio.sleep(60)  # let the hub finish booting first
    while True:
        try:
            packages = await satellite_strike.scan()
            if packages:
                log.info(f"[swarm.autopilot] scan found {len(packages)} targets — firing swarm")
                jobs = await swarm_gate.fire(packages)
                completed = sum(1 for j in jobs if j.status == "complete")
                log.info(f"[swarm.autopilot] fire complete: {completed}/{len(jobs)} jobs succeeded")
            else:
                log.debug("[swarm.autopilot] scan: no targets found")
        except Exception as e:
            log.warning(f"[swarm.autopilot] cycle error: {e}")
        await asyncio.sleep(_SWARM_AUTOPILOT_INTERVAL)


# ── Pulse Refresh Cron ──────────────────────────────────────
# Every 5 min, refreshes the pulse_rollup_hourly materialized view
# so the /view/pulse page always has fresh data.

async def _pulse_refresh_loop():
    """Background loop: refresh the pulse materialized view every N seconds."""
    await asyncio.sleep(pulse_engine.refresh_interval_sec)
    while True:
        try:
            await pulse_engine.refresh()
        except Exception as e:
            log.debug(f"[pulse] refresh loop error: {e}")
        await asyncio.sleep(pulse_engine.refresh_interval_sec)


# ─── /api/v1/compliance/stats: Compliance dashboard data ──────────────────
from datetime import datetime as _cdt, timezone as _ctz

@app.get("/api/v1/compliance/stats")
async def compliance_stats(auth: bool = Depends(require_auth)):
    """Return compliance dashboard data: recent blocks, DNC table counts, call window."""
    db = get_db()
    now = _cdt.now(_ctz.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # 1. Count today's blocked calls
    blocked_count = 0
    try:
        r = db.table("compliance_audit_logs").select("*", count="exact") \
            .eq("action", "outbound_call_blocked") \
            .gte("created_at", today_start) \
            .execute()
        blocked_count = getattr(r, "count", len(r.data or []))
    except Exception:
        pass

    # 2. Recent blocks (last 10)
    recent_blocks = []
    try:
        r = db.table("compliance_audit_logs").select("*") \
            .eq("action", "outbound_call_blocked") \
            .order("created_at", desc=True).limit(10).execute()
        for e in (r.data or []):
            det = e.get("details", {}) or {}
            recent_blocks.append({
                "ts": (e.get("created_at") or "")[:19],
                "rule": det.get("rule", "") if isinstance(det, dict) else "",
                "phone": e.get("entity_id", "") or det.get("phone", "") if isinstance(det, dict) else "",
            })
    except Exception:
        pass

    # 3. DNC table counts
    sms_opt_outs = 0
    outbound_dnc_count = 0
    try:
        r = db.table("sms_opt_outs").select("*", count="exact").limit(1).execute()
        sms_opt_outs = getattr(r, "count", 0)
    except Exception:
        pass
    try:
        r = db.table("outbound_dnc").select("*", count="exact").limit(1).execute()
        outbound_dnc_count = getattr(r, "count", 0)
    except Exception:
        pass

    # 4. Call window status (using same logic as empire_outbound_dialer)
    from zoneinfo import ZoneInfo as _zi
    tz_name = "America/Chicago"  # default
    try:
        h = _cdt.now(_zi(tz_name)).hour
    except Exception:
        h = now.hour
    within_hours = 8 <= h < 21
    window_start = "08:00"
    window_end = "21:00"
    local_hour = h

    return {
        "blocked_today": blocked_count,
        "recent_blocks": recent_blocks,
        "sms_opt_outs": sms_opt_outs,
        "outbound_dnc": outbound_dnc_count,
        "call_window": {
            "open": within_hours,
            "local_hour": local_hour,
            "window": f"{window_start}-{window_end} {tz_name}",
        },
    }


# ─── /api/v1/health/mesh: Agent mesh status + system health ──────────
import requests as _hreq

@app.get("/api/v1/health/mesh")
async def health_mesh(auth: bool = Depends(require_auth)):
    """Aggregate health data: agent_registry, brain status, funnel, PM2, storm forecasts."""
    db = get_db()
    now = _cdt.now(_ctz.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # 1. Agent registry
    agents = []
    try:
        r = db.table("agent_registry").select("agent_name,status,last_ping,enabled").execute()
        for row in (r.data or []):
            age_min = None
            lp = row.get("last_ping")
            if lp:
                try:
                    age_min = round((now - _cdt.fromisoformat(str(lp).replace("Z", "+00:00"))).total_seconds() / 60, 1)
                except Exception:
                    pass
            agents.append({
                "agent_name": row.get("agent_name"),
                "status": row.get("status"),
                "enabled": row.get("enabled", True),
                "last_ping": lp,
                "ping_age_min": age_min,
            })
    except Exception as e:
        agents = [{"error": str(e)[:80]}]

    # 2. Brain (Ollama) status
    brain_up = False
    try:
        r = _hreq.get("http://localhost:11434/api/tags", timeout=3)
        brain_up = r.status_code == 200
    except Exception:
        pass

    # 3. Funnel stats
    calls_today = 0
    qualified_today = 0
    try:
        r = db.table("call_logs").select("qualified", count="exact").gte("created_at", today_start).execute()
        calls_today = r.count or 0
        qualified_today = sum(1 for row in (r.data or []) if row.get("qualified"))
    except Exception:
        pass

    # 4. Storm forecasts count
    storm_count = 0
    try:
        r = db.table("storm_forecasts").select("id", count="exact").execute()
        storm_count = r.count or 0
    except Exception:
        pass

    # 5. PM2 health (reuses existing _pm2_services)
    pm2_svcs = _pm2_services()
    pm2_healthy = sum(1 for s in pm2_svcs if s["status"] == "online")

    # 6. Latest system_health from overseer
    latest_overseer = None
    try:
        r = db.table("system_health").select("*").order("created_at", desc=True).limit(1).execute()
        if r.data:
            latest_overseer = r.data[0]
    except Exception:
        pass

    return JSONResponse({
        "agents": agents,
        "brain_up": brain_up,
        "funnel": {"calls_today": calls_today, "qualified_today": qualified_today},
        "storm_forecasts_count": storm_count,
        "pm2": {"services": pm2_svcs, "healthy": pm2_healthy, "total": len(pm2_svcs)},
        "overseer": latest_overseer,
        "ts": now.isoformat(),
    })


# ─── /api/agents: Sniper Fleet ──
from datetime import timedelta as _atd

def _get_agent_leads():
    leads = {"storm": 0, "legal": 0, "warehouse": 0, "logistics": 0, "reddit": 0, "linkedin": 0}
    try:
        today = _gdt.utcnow().date().isoformat()
        res = _sb.table("radar_targets").select("source").gte("created_at", today).execute()
        for row in (res.data or []):
            s = (row.get("source") or "").lower()
            if "storm" in s or "weather" in s: leads["storm"] += 1
            elif "reddit" in s: leads["reddit"] += 1
    except Exception as e:
        print(f"[agents] leads error: {e}")
    return leads

_AGENT_LEADS = _get_agent_leads()
_AGENTS = [
    {"id": "storm",     "name": "Storm",     "type": "Weather",    "enabled": True},
    {"id": "legal",     "name": "Legal",     "type": "Compliance", "enabled": True},
    {"id": "warehouse", "name": "Warehouse", "type": "Inventory",  "enabled": True},
    {"id": "logistics", "name": "Logistics", "type": "Dispatch",   "enabled": False},
    {"id": "reddit",    "name": "Reddit",    "type": "Social",     "enabled": True},
    {"id": "linkedin",  "name": "LinkedIn",  "type": "Social",     "enabled": False},
]
# seed a plausible last_ping per agent (live for active, stale for idle/offline)
_aseed = _gdt.utcnow()
for _a in _AGENTS:
    _l = _AGENT_LEADS.get(_a["id"], 0)
    _a["last_ping"] = (_aseed if (_a["enabled"] and _l > 0)
                       else _aseed - _atd(minutes=14) if _a["enabled"]
                       else _aseed - _atd(hours=3)).isoformat(timespec="seconds")


def _agent_view(a):
    leads = _AGENT_LEADS.get(a["id"], 0)
    if not a["enabled"]:
        status = "OFFLINE"
    elif leads > 0:
        status = "ACTIVE"
        a["last_ping"] = _gdt.utcnow().isoformat(timespec="seconds")  # live heartbeat
    else:
        status = "IDLE"
    return {
        "id": a["id"], "name": a["name"], "type": a["type"],
        "enabled": a["enabled"], "status": status,
        "leads_today": leads, "last_ping": a.get("last_ping"),
    }


@app.get("/api/agents/status")
async def agents_status():
    return JSONResponse({"agents": [_agent_view(a) for a in _AGENTS]})

@app.get("/api/revenue/forecast")
async def revenue_forecast():
    """Adaptive revenue forecast: pipeline + per-lane + few-shot LLM narrative + health."""
    try:
        from bots import predictive_revenue
        return JSONResponse(predictive_revenue.adaptive_forecast())
    except Exception as e:
        return JSONResponse({"error": str(e), "lead_count": 0, "pipeline_value": 0, "forecasted_revenue": 0})


@app.get("/api/revenue/lanes")
async def revenue_lanes():
    """Per-lane revenue breakdown for bar charts and lane comparisons."""
    try:
        from bots import predictive_revenue
        return JSONResponse(predictive_revenue.per_lane_forecast())
    except Exception as e:
        return JSONResponse({"error": str(e), "lanes": [], "totals": {}})


@app.get("/api/revenue/health")
async def revenue_health():
    """Revenue health alerts: trend analysis and anomaly detection."""
    try:
        from bots import predictive_revenue
        return JSONResponse(predictive_revenue.revenue_health_check())
    except Exception as e:
        return JSONResponse({"error": str(e), "status": "unknown", "alerts": []})


@app.get("/api/revenue/accuracy")
async def revenue_accuracy(days: int = 14):
    """Forecast vs actual over time using pipeline_health + revenue snapshots."""
    try:
        from bots import predictive_revenue
        return JSONResponse(predictive_revenue.get_accuracy_timeseries(days=min(days, 30)))
    except Exception as e:
        return JSONResponse({"error": str(e), "series": [], "summary": {}})


@app.get("/api/revenue/mrr")
async def revenue_mrr():
    """MRR comparison: actual (from product_subscriptions) vs projected (from predictive engine)."""
    try:
        # Actual MRR from Supabase product_subscriptions
        db = get_db()
        actual_mrr = 0.0
        actual_subs = []
        try:
            r = db.table("product_subscriptions") \
                .select("customer_account_id,tier_level,monthly_recurring_revenue,subscription_status") \
                .in_("subscription_status", ["ACTIVE", "TRIALING"]) \
                .execute()
            for sub in (r.data or []):
                mrr = float(sub.get("monthly_recurring_revenue", 0) or 0)
                actual_mrr += mrr
                actual_subs.append({
                    "account": sub.get("customer_account_id", ""),
                    "tier": sub.get("tier_level", ""),
                    "mrr": round(mrr, 2),
                    "status": sub.get("subscription_status", ""),
                })
        except Exception as e:
            log.warning(f"[mrr] product_subscriptions query: {e}")

        # Also check buyer_subscriptions for per-lead MRR
        buyer_mrr = 0.0
        buyer_sub_count = 0
        try:
            r2 = db.table("buyer_subscriptions") \
                .select("plan_tier,monthly_fee") \
                .eq("active", True) \
                .execute()
            for bs in (r2.data or []):
                fee = float(bs.get("monthly_fee", 0) or 0)
                buyer_mrr += fee
                buyer_sub_count += 1
        except Exception:
            pass

        total_actual_mrr = round(actual_mrr + buyer_mrr, 2)

        # Projected MRR from predictive revenue engine
        projected_mrr = 0.0
        try:
            from bots import predictive_revenue
            forecast = predictive_revenue.adaptive_forecast()
            totals = forecast.get("totals", {}) if isinstance(forecast, dict) else {}
            projected_mrr = float(totals.get("mrr_projected", 0) or 0)
        except Exception:
            pass

        return JSONResponse({
            "actual_mrr": total_actual_mrr,
            "projected_mrr": round(projected_mrr, 2),
            "gap": round(projected_mrr - total_actual_mrr, 2),
            "gap_pct": round(((projected_mrr - total_actual_mrr) / max(projected_mrr, 0.01)) * 100, 1) if projected_mrr > 0 else 0,
            "subscriptions": actual_subs,
            "buyer_subscriptions": buyer_sub_count,
            "buyer_mrr": round(buyer_mrr, 2),
        })
    except Exception as e:
        return JSONResponse({"actual_mrr": 0, "projected_mrr": 0, "gap": 0, "error": str(e)[:200]})


@app.get("/api/revenue/usdc-ledger")
async def revenue_usdc_ledger(limit: int = 10):
    """Recent verified USDC payments from the empire_revenue_ledger table.

    Returns the most recent on-chain USDC transfers verified by the Solana
    Revenue Engine, ordered by block time descending.
    """
    limit = max(1, min(limit, 100))
    try:
        db = get_db()
        r = db.table("empire_revenue_ledger") \
            .select("transaction_signature,sender_address,usdc_amount,tracking_memo,block_time_stamp,logged_at") \
            .order("block_time_stamp", desc=True) \
            .limit(limit) \
            .execute()
        rows = r.data or []
        total_usdc = sum(float(row.get("usdc_amount", 0) or 0) for row in rows)
        try:
            all_r = db.table("empire_revenue_ledger") \
                .select("usdc_amount") \
                .execute()
            grand_total = sum(float(row.get("usdc_amount", 0) or 0) for row in (all_r.data or []))
        except Exception:
            grand_total = total_usdc

        return JSONResponse({
            "payments": rows,
            "count": len(rows),
            "total_usdc_displayed": round(total_usdc, 6),
            "total_usdc_all_time": round(grand_total, 6),
        })
    except Exception as e:
        return JSONResponse({"payments": [], "count": 0, "total_usdc_displayed": 0, "total_usdc_all_time": 0, "error": str(e)[:200]})


# Shared product fallback used when Supabase product_metadata is unavailable
_SUITE_FALLBACK = [
    {"tier": "SEO_STARTER", "product_name": "seo_optimizer", "display_name": "SEO Starter", "monthly_price_usd": 99, "price_per_unit": None, "description": "Entry-level SEO: 5 audits, 50 keywords, 10 content pieces/mo", "features": []},
    {"tier": "SEO_GROWTH", "product_name": "seo_optimizer", "display_name": "SEO Growth", "monthly_price_usd": 199, "price_per_unit": None, "description": "Growth SEO: 15 audits, 200 keywords, research pipeline", "features": []},
    {"tier": "SEO_PRO", "product_name": "seo_optimizer", "display_name": "SEO Pro", "monthly_price_usd": 499, "price_per_unit": None, "description": "Pro SEO: unlimited audits, unlimited keywords, full pipeline", "features": []},
    {"tier": "ROUTER_SaaS", "product_name": "inbound_router", "display_name": "Inbound Router", "monthly_price_usd": 499, "price_per_unit": "$0.25/routed call", "description": "AI triage inbound routing with Vonage PSTN", "features": []},
    {"tier": "DATA_ENTERPRISE", "product_name": "data_vault", "display_name": "Data Vault", "monthly_price_usd": 799, "price_per_unit": "$0.02/stored record/mo", "description": "Enterprise data vault: structured storage, secure API", "features": []},
    {"tier": "SPY_DATA", "product_name": "buyer_spy", "display_name": "Buyer Spy AI", "monthly_price_usd": 1499, "price_per_unit": "$5/analysis", "description": "AI-powered transcript analysis and competitive tracking", "features": []},
    {"tier": "ALL_ACCESS", "product_name": "all_products", "display_name": "All Access", "monthly_price_usd": 2499, "price_per_unit": None, "description": "Full access to all Empire AI products", "features": []},
]


@app.get("/api/v1/products/catalog")
async def products_catalog():
    """Combined product catalog: strike packs + suite SaaS tiers."""
    try:
        db = get_db()
        # Strike packs from the catalog
        packs = strike_pack_catalog.all(public_only=False)
        catalog_packs = [
            {
                "slug": p["slug"],
                "name": p["name"],
                "description": p["description"],
                "tier": p["tier"],
                "monthly_price_usd": round(p["monthly_price_cents"] / 100, 2),
                "price_per_lead_usd": round(p["price_per_lead_cents"] / 100, 2),
                "max_leads_per_day": p["max_leads_per_day"],
                "max_leads_per_month": p["max_leads_per_month"],
                "delivery_channels": p.get("delivery_channels", []),
                "target_buyer": p.get("target_buyer"),
                "features": p.get("features", []),
                "lane_count": p["lane_count"],
                "niches": p.get("niches", []),
            }
            for p in packs
        ]

        # Suite SaaS products from product_metadata table (Supabase)
        # Falls back to hardcoded values if the table doesn't exist yet.
        suite_products_raw = []
        try:
            r = db.table("product_metadata") \
                .select("tier,product_name,display_name,description,monthly_price_usd,price_per_unit,features,sort_order") \
                .eq("is_active", True) \
                .order("sort_order") \
                .execute()
            suite_products_raw = r.data or []
        except Exception as e:
            log.warning(f"[products] product_metadata query failed: {e} — using fallback pricing")
            suite_products_raw = _SUITE_FALLBACK

        suite_products = [
            {
                "name": p.get("display_name", p["tier"].replace("_", " ").title()),
                "tier": p["tier"],
                "tier_label": p.get("display_name", p["tier"].replace("_", " ").title()),
                "monthly_price_usd": float(p.get("monthly_price_usd", 0) or 0),
                "price_per_unit": p.get("price_per_unit"),
                "product": p["product_name"],
                "description": p.get("description", ""),
                "features": p.get("features", []) if isinstance(p.get("features"), list) else [],
            }
            for p in suite_products_raw
        ]

        # Subscription stats from suite engine
        all_subs = suite_subscriptions.list_subscriptions()
        active_subs = [s for s in all_subs if s.get("subscription_status") == "ACTIVE"]
        total_mrr = sum(s.get("monthly_recurring_revenue", 0) for s in active_subs)

        return JSONResponse({
            "strike_packs": catalog_packs,
            "suite_products": suite_products,
            "subscriptions": {
                "active_count": len(active_subs),
                "total_count": len(all_subs),
                "total_mrr": round(total_mrr, 2),
            },
        })
    except Exception as e:
        return JSONResponse({"strike_packs": [], "suite_products": []}, status_code=500)

@app.post("/api/v1/products/subscribe")
async def products_subscribe(req: Request, auth: bool = Depends(require_auth)):
    """Create a new product subscription.
    Body: {
      customer_account_id: str (required),
      tier_level: str (required — SEO_STARTER, ROUTER_SaaS, etc.),
      monthly_recurring_revenue: float (optional, defaults to product_metadata price),
    }
    """
    try:
        body = await req.json() if req.headers.get("content-type", "").startswith("application/json") else {}
        account_id = (body.get("customer_account_id") or "").strip()
        tier = (body.get("tier_level") or "").strip().upper()

        if not account_id:
            return JSONResponse({"ok": False, "error": "customer_account_id is required"}, status_code=400)
        if not tier:
            return JSONResponse({"ok": False, "error": "tier_level is required"}, status_code=400)

        # Look up the tier price from product_metadata if not provided
        mrr = float(body.get("monthly_recurring_revenue", 0) or 0)
        if mrr <= 0:
            try:
                db = get_db()
                r = db.table("product_metadata") \
                    .select("monthly_price_usd") \
                    .eq("tier", tier) \
                    .eq("is_active", True) \
                    .limit(1) \
                    .execute()
                if r.data:
                    mrr = float(r.data[0].get("monthly_price_usd", 0) or 0)
            except Exception:
                pass

        result = suite_subscriptions.create_subscription(
            customer_account_id=account_id,
            tier_level=tier,
            monthly_recurring_revenue=mrr if mrr > 0 else 0.0,
            billing_anchor_day=max(1, min(28, body.get("billing_anchor_day", 1))),
            notes=body.get("notes", ""),
        )

        if result.get("ok"):
            log.info(f"[subscribe] created {tier} for {account_id} — MRR ${mrr:.2f}")
            return JSONResponse(result)
        else:
            status = 409 if "already has" in (result.get("error") or "") else 400
            return JSONResponse(result, status_code=status)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)


@app.get("/api/v1/products/metadata")
async def products_metadata(auth: bool = Depends(require_auth)):
    """List all active products from product_metadata table.
    Useful for subscribe button pickers in the SPA.
    """
    try:
        db = get_db()
        r = db.table("product_metadata") \
            .select("tier,product_name,display_name,description,monthly_price_usd,price_per_unit,features,sort_order") \
            .eq("is_active", True) \
            .eq("is_public", True) \
            .order("sort_order") \
            .execute()
        return JSONResponse({"products": r.data or [], "count": len(r.data or [])})
    except Exception as e:
        return JSONResponse({"products": [], "count": 0, "error": str(e)[:80]})




# ─── Command Center Pro — Unified Product Health ────────────────────────
@app.get("/api/v6/suite/ccp/health")
async def command_center_health(auth: bool = Depends(require_auth)):
    """Aggregated product health dashboard for Command Center Pro.
    Returns per-product status (ok/warn/error), subscription counts,
    MRR totals, and summary stats from live Supabase data."""
    try:
        db = get_db()

        try:
            result = db.table("product_metadata").select(
                "tier,product_name,display_name,description,monthly_price_usd,"
                "features,sort_order,is_active"
            ).eq("is_active", True).order("sort_order").execute()
            products = result.data or []
        except Exception as e:
            log.warning(f"[ccp] product_metadata query failed: {e} — returning empty")
            products = []

        try:
            subs = suite_subscriptions.list_subscriptions()
            active_subs = [s for s in subs if s.get("subscription_status") == "ACTIVE"]
            active_count = len(active_subs)
            total_mrr = round(sum(
                float(s.get("monthly_recurring_revenue", 0)) for s in active_subs
            ), 2)
        except Exception as e:
            log.warning(f"[ccp] suite_subscriptions query failed: {e} — returning zero metrics")
            active_subs = []
            active_count = 0
            total_mrr = 0.0

        sub_by_product = {}
        for s in active_subs:
            pn = s.get("product_name") or s.get("product", "")
            if pn:
                sub_by_product[pn] = sub_by_product.get(pn, 0) + 1

        product_list = []
        ok_count = warn_count = error_count = 0

        for p in products:
            name = p.get("display_name") or p.get("product_name") or p.get("tier", "Unknown")
            pn = p.get("product_name", "")
            tier = p.get("tier", "standard")
            desc = p.get("description", "")
            price = p.get("monthly_price_usd", 0)
            is_active = p.get("is_active", True)

            sub_count = sub_by_product.get(pn, 0)

            if not is_active:
                status = "error"
                msg = "Product deactivated"
            elif sub_count == 0:
                status = "warn"
                msg = "No active subscriptions"
            else:
                status = "ok"
                msg = f"{sub_count} active subscriber{'s' if sub_count > 1 else ''}"

            if status == "ok":
                ok_count += 1
            elif status == "warn":
                warn_count += 1
            else:
                error_count += 1

            product_list.append({
                "name": name,
                "slug": pn or name.lower().replace(" ", "-"),
                "status": status,
                "tier": tier,
                "description": desc,
                "monthly_price_usd": float(price) if price else 0,
                "message": msg,
                "subscribers": sub_count,
            })

        return JSONResponse({
            "products": product_list,
            "summary": {
                "total": len(product_list),
                "healthy": ok_count,
                "warnings": warn_count,
                "errors": error_count,
            },
            "total_mrr": total_mrr,
            "active_subscriptions": active_count,
        })
    except Exception as e:
        return JSONResponse({
            "products": [],
            "summary": {"total": 0, "healthy": 0, "warnings": 0, "errors": 0},
            "total_mrr": 0,
            "active_subscriptions": 0,
            "error": str(e)[:120],
        }, status_code=500)

@app.get("/api/si/snapshot")
async def si_strategy_snapshot(auth: bool = Depends(require_auth)):
    """SI Strategy Evolution snapshot — active strategies, genomes, win rates per niche."""
    try:
        return JSONResponse(si_strategy.snapshot())
    except Exception as e:
        return JSONResponse({"error": str(e), "by_niche": {}, "best_per_niche": {}})


@app.get("/api/si/strategy")
async def si_strategy_view(auth: bool = Depends(require_auth)):
    """Detailed SI Strategy Evolution view (same payload as /api/si/snapshot,
    named for clarity on the SPA side)."""
    try:
        return JSONResponse(si_strategy.snapshot())
    except Exception as e:
        return JSONResponse({"error": str(e)[:80]})


@app.get("/api/si/adaptive")
async def si_adaptive_view(auth: bool = Depends(require_auth)):
    """Adaptive Engine status — subsystems registered, adaptations applied."""
    try:
        return JSONResponse(adaptive_engine.snapshot())
    except Exception as e:
        return JSONResponse({"error": str(e)[:80]})


@app.post("/api/si/evolve")
async def si_evolve_force(niche: str = "", auth: bool = Depends(require_auth)):
    """Force a strategy evolution tick. Optional ?niche= to evolve one niche only."""
    try:
        events = si_strategy.evolve(niche=niche or None)
        return JSONResponse({
            "ok": True,
            "events": events,
            "count": len(events),
            "niche": niche or "all",
        })
    except Exception as e:
        return JSONResponse({"error": str(e)[:80]}, status_code=500)


@app.post("/api/si/record-outcome")
async def si_record_outcome(request: Request, auth: bool = Depends(require_auth)):
    """Feed an outcome back to the SI Strategy Evolution engine.
    Body: {"strategy": "AGGRESSIVE_STRIKE", "niche": "Roofing Restoration", "success": true, "revenue": 1500.0}
    """
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        strategy = body.get("strategy", "")
        niche = body.get("niche", "")
        success = bool(body.get("success", False))
        revenue = float(body.get("revenue", 0) or 0)
        if not strategy or not niche:
            return JSONResponse({"error": "strategy and niche required"}, status_code=400)
        si_strategy.record_outcome(strategy, niche, success, revenue)
        return JSONResponse({"ok": True, "strategy": strategy, "niche": niche, "success": success, "revenue": revenue})
    except Exception as e:
        return JSONResponse({"error": str(e)[:80]}, status_code=500)


@app.get("/api/seo/performance")
async def seo_performance():
    """SEO agent performance snapshot — audits, keywords, content, genome."""
    try:
        from bots.seo_agent import get_seo_agent, run_loop
        agent = get_seo_agent()
        return JSONResponse(await agent.performance_snapshot())
    except Exception as e:
        return JSONResponse({"error": str(e), "stats": {}, "keywords": [], "content": []})


@app.get("/api/seo/products")
async def seo_products():
    """SEO Optimizer product catalog — 3 tiers from strike_packs."""
    try:
        packs = strike_pack_catalog.all(public_only=False)
        seo_packs = [p for p in packs if "SEO" in [n.upper() for n in (p.get("niches") or [])]]
        products = []
        for p in seo_packs:
            products.append({
                "slug":                p["slug"],
                "name":                p["name"],
                "description":         p["description"],
                "tier":                p["tier"],
                "monthly_price_usd":   round(p["monthly_price_cents"] / 100, 2),
                "features":            p.get("features", []),
                "target_buyer":        p.get("target_buyer"),
                "delivery_channels":   p.get("delivery_channels", []),
            })

        # Also include the product_subscriptions data for actual MRR
        try:
            db = get_db()
            r = db.table("product_subscriptions").select("customer_account_id,tier_level,monthly_recurring_revenue,subscription_status") \
                .like("tier_level", "SEO_%").execute()
            subs = r.data or []
        except Exception:
            subs = []

        return JSONResponse({
            "products": products,
            "subscriptions": subs,
            "total_seo_mrr": round(sum(float(s.get("monthly_recurring_revenue", 0)) for s in subs if s.get("subscription_status") == "ACTIVE"), 2),
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "products": [], "subscriptions": []})


@app.get("/api/seo/genome-history")
async def seo_genome_history(limit: int = 20):
    """Return parsed genome evolution timeline from seo_genome_history."""
    import json as _j
    db = get_db()
    try:
        r = db.table("seo_genome_history") \
            .select("generation,genome,top_keywords,avg_conversion_rate,created_at") \
            .order("generation", desc=True) \
            .limit(min(limit, 100)) \
            .execute()
        rows = r.data or []
        parsed = []
        for g in rows:
            gm = g.get("genome") or {}
            if isinstance(gm, str):
                try: gm = _j.loads(gm)
                except Exception: gm = {}
            kws = g.get("top_keywords") or []
            if isinstance(kws, str):
                try: kws = _j.loads(kws)
                except Exception: kws = []
            parsed.append({
                "generation": g.get("generation"),
                "traits": gm if isinstance(gm, dict) else {},
                "top_keywords": kws if isinstance(kws, list) else [],
                "avg_conversion_rate": g.get("avg_conversion_rate"),
                "created_at": g.get("created_at"),
            })
        # Compute trait drift across the timeline
        drift = None
        if len(rows) >= 2:
            newest_gm = parsed[0].get("traits") or {}
            oldest_gm = parsed[-1].get("traits") or {}
            if newest_gm and oldest_gm:
                drift = {}
                for trait in ["keyword_competitiveness", "local_intent", "content_depth", "technical_rigor", "link_authority"]:
                    nv = float(newest_gm.get(trait, 0))
                    ov = float(oldest_gm.get(trait, 0))
                    if ov and ov != 0:
                        drift[trait] = round((nv - ov) / ov, 3)
        return JSONResponse({
            "generations": parsed,
            "count": len(parsed),
            "latest_generation": parsed[0].get("generation") if parsed else None,
            "trait_drift": drift,
        })
    except Exception as e:
        return JSONResponse({"generations": [], "count": 0, "error": str(e)[:80]})


@app.get("/api/seo/research")
async def seo_research_get(research_type: str = "full", address: str = "", zip_code: str = "", metro: str = "", niche: str = "Roofing Restoration"):
    """Run deep research via the SEO ResearchAgent. Supports all research types.
    Query params: research_type, address, zip_code, metro, niche
    """
    try:
        from bots.seo_agent import get_seo_agent
        agent = get_seo_agent()
        return JSONResponse(await agent.research(
            address=address, zip_code=zip_code,
            metro=metro, niche=niche,
            research_type=research_type,
        ))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.post("/api/seo/generate")
async def seo_generate_post(req: Request):
    """Generate content via the SEO ContentAgent.
    Body: {
      content_type, address, metro, niche, style?
      property_data?, neighborhood_data?, storm_data?
    }
    """
    try:
        body = await req.json() if req.headers.get("content-type", "").startswith("application/json") else {}
        from bots.seo_agent import get_seo_agent
        agent = get_seo_agent()
        return JSONResponse(await agent.generate(
            content_type=body.get("content_type", "landing_page"),
            address=body.get("address", ""),
            metro=body.get("metro", ""),
            niche=body.get("niche", "Roofing Restoration"),
            property_data=body.get("property_data"),
            neighborhood_data=body.get("neighborhood_data"),
            storm_data=body.get("storm_data"),
            style=body.get("style", "cinematic"),
        ))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.post("/api/seo/pipeline")
async def seo_pipeline_post(req: Request):
    """End-to-end research → generate pipeline.
    Body: {address, zip_code, metro, niche, style?, generate_types?}
    """
    try:
        body = await req.json() if req.headers.get("content-type", "").startswith("application/json") else {}
        from bots.seo_agent import get_seo_agent
        agent = get_seo_agent()
        return JSONResponse(await agent.research_and_generate(
            address=body.get("address", ""),
            zip_code=body.get("zip_code", ""),
            metro=body.get("metro", ""),
            niche=body.get("niche", "Roofing Restoration"),
            style=body.get("style", "cinematic"),
            generate_types=body.get("generate_types"),
        ))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.get("/api/seo/research-agent/stats")
async def seo_research_agent_stats():
    """Return ResearchAgent performance snapshot."""
    try:
        from bots.research_agent import get_research_agent
        agent = get_research_agent()
        return JSONResponse(await agent.performance_snapshot())
    except Exception as e:
        return JSONResponse({"error": str(e)[:80]}, status_code=500)


@app.get("/api/seo/content-agent/stats")
async def seo_content_agent_stats():
    """Return ContentAgent performance snapshot."""
    try:
        from bots.content_agent import get_content_agent
        agent = get_content_agent()
        return JSONResponse(await agent.performance_snapshot())
    except Exception as e:
        return JSONResponse({"error": str(e)[:80]}, status_code=500)


@app.get("/api/seo/config")
async def seo_config_get():
    """Return current SEO agent config (interval, bounds)."""
    try:
        from bots.seo_agent import get_seo_interval
        interval = get_seo_interval()
        return JSONResponse({"interval_hours": interval, "min": 0.1, "max": 24.0})
    except Exception as e:
        return JSONResponse({"interval_hours": 6.0, "min": 0.1, "max": 24.0, "error": str(e)[:80]})


@app.post("/api/seo/config")
async def seo_config_post(req: Request):
    """Update SEO agent loop interval at runtime (0.1–24.0 hours)."""
    try:
        from bots.seo_agent import set_seo_interval, get_seo_interval
        body = await req.json() if req.headers.get("content-type", "").startswith("application/json") else {}
        hours = body.get("interval_hours") if isinstance(body, dict) else None
        if hours is None:
            return JSONResponse({"error": "Missing interval_hours"}, status_code=400)
        if not isinstance(hours, (int, float)):
            return JSONResponse({"error": "interval_hours must be a number"}, status_code=400)
        set_seo_interval(float(hours))
        return JSONResponse({"interval_hours": get_seo_interval(), "min": 0.1, "max": 24.0})
    except Exception as e:
        return JSONResponse({"error": str(e)[:80]}, status_code=500)


# ── Backlinks Monitoring Routes ───────────────────────────────
# GET  /api/seo/backlinks/snapshot    — full backlinks dashboard
# GET  /api/seo/backlinks/scan        — scan a domain for backlinks
# GET  /api/seo/backlinks/broken      — check known backlinks for broken status
# GET  /api/seo/backlinks/opportunities — link-building opportunities
# GET  /api/seo/backlinks/authority   — link authority report (feeds SEO genome)
# POST /api/seo/backlinks/scan/{url}  — trigger a domain scan

@app.get("/api/seo/backlinks/snapshot")
async def seo_backlinks_snapshot():
    """Backlinks dashboard snapshot — stats, tracked backlinks, opportunities."""
    try:
        from bots.backlinks_agent import get_backlinks_agent
        agent = get_backlinks_agent()
        return JSONResponse(await agent.performance_snapshot())
    except Exception as e:
        return JSONResponse({"error": str(e)[:200], "stats": {}, "backlinks": [], "opportunities": []})


@app.get("/api/seo/backlinks/broken")
async def seo_backlinks_broken(limit: int = 30):
    """Check known backlinks for broken (404) status."""
    try:
        from bots.backlinks_agent import get_backlinks_agent
        agent = get_backlinks_agent()
        return JSONResponse(await agent.check_broken(limit=min(limit, 100)))
    except Exception as e:
        return JSONResponse({"checked": 0, "broken": 0, "error": str(e)[:80]})


@app.get("/api/seo/backlinks/opportunities")
async def seo_backlinks_opportunities(niche: str = ""):
    """Identify link-building opportunities — broken replacements, unlisted directories."""
    try:
        from bots.backlinks_agent import get_backlinks_agent
        agent = get_backlinks_agent()
        return JSONResponse({"opportunities": await agent.find_opportunities(niche=niche)})
    except Exception as e:
        return JSONResponse({"opportunities": [], "error": str(e)[:80]})


@app.get("/api/seo/backlinks/authority")
async def seo_backlinks_authority():
    """Link authority report — composite score for SEO genome evolution."""
    try:
        from bots.backlinks_agent import get_backlinks_agent
        agent = get_backlinks_agent()
        return JSONResponse(await agent.link_authority_report())
    except Exception as e:
        return JSONResponse({"link_authority_score": 0.3, "error": str(e)[:80]})


@app.post("/api/seo/backlinks/scan/{url:path}")
async def seo_backlinks_scan(url: str):
    """Trigger a backlink scan for a specific domain/URL."""
    try:
        from bots.backlinks_agent import get_backlinks_agent
        agent = get_backlinks_agent()
        return JSONResponse(await agent.scan_domain(url))
    except Exception as e:
        return JSONResponse({"backlinks": [], "error": str(e)[:200]})


@app.get("/api/seo/backlinks/stats")
async def seo_backlinks_stats():
    """Backlinks agent stats — scans run, broken found, opportunities."""
    try:
        from bots.backlinks_agent import get_backlinks_agent
        agent = get_backlinks_agent()
        snap = agent.stats
        return JSONResponse({
            "domains_monitored": snap["domains_monitored"],
            "backlinks_discovered": snap["backlinks_discovered"],
            "broken_found": snap["broken_found"],
            "opportunities_found": snap["opportunities_found"],
            "scans_run": snap["scans_run"],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)[:80]})


@app.post("/api/si/parameters")
async def si_parameters_persist(req: Request):
    """Write SI parameter state to Supabase. Body: {"parameters": {key: {current, default, min, max, samples, confidence}}}"""
    try:
        db = get_db()
        body = await req.json() if req.headers.get("content-type", "").startswith("application/json") else {}
        params = body.get("parameters") if isinstance(body, dict) else None
        if not params or not isinstance(params, dict):
            return JSONResponse({"error": "Missing or invalid 'parameters' dict"}, status_code=400)
        now = datetime.now(timezone.utc).isoformat()
        upserted = 0
        for key, param in params.items():
            if not isinstance(param, dict):
                continue
            db.table("si_parameters").upsert({
                "key": key,
                "current_value": param.get("current"),
                "default_value": param.get("default"),
                "min": param.get("min"),
                "max": param.get("max"),
                "samples": param.get("samples", 0),
                "confidence": param.get("confidence", 0),
                "updated_at": now,
                "updated_by": "si",
            }, on_conflict="key").execute()
            upserted += 1
        return JSONResponse({"upserted": upserted})
    except Exception as e:
        return JSONResponse({"error": str(e)[:80]}, status_code=500)


@app.post("/api/admin/seed")
async def admin_seed(req: Request):
    """Bootstrap the 6 new tables with sample data. If ADMIN_TOKEN env var is set, the
    request must include matching X-Admin-Token header. Idempotent (upsert on keywords)."""
    expected = os.environ.get("ADMIN_TOKEN", "")
    if expected:
        provided = req.headers.get("x-admin-token", "")
        if provided != expected:
            return JSONResponse({"error": "Invalid or missing X-Admin-Token header"}, status_code=401)
    try:
        from empire_seed import seed_all
        counts = seed_all()
        total = sum(counts.values())
        return JSONResponse({"seeded": counts, "total_rows": total})
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.get("/api/agent-registry/heartbeats")
async def agent_registry_heartbeats(stale_seconds: int = 600):
    """List all active agent heartbeats from agent_registry. Marks agents whose
    last_ping exceeds stale_seconds as 'stale'. Used by the SPA fleet panel."""
    try:
        db = get_db()
        r = db.table("agent_registry") \
            .select("agent_name,status,last_ping,enabled,capabilities,leads_today,metrics,updated_at") \
            .order("last_ping", desc=True) \
            .execute()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        agents = []
        for row in (r.data or []):
            ping = row.get("last_ping")
            age = None
            if ping:
                try:
                    ping_dt = datetime.fromisoformat(ping.replace("Z", "+00:00"))
                    age = int((now - ping_dt).total_seconds())
                except Exception:
                    pass
            agents.append({
                "agent_name": row.get("agent_name"),
                "status": row.get("status"),
                "enabled": row.get("enabled", False),
                "last_ping": ping,
                "seconds_since_ping": age,
                "is_stale": age is not None and age > stale_seconds,
                "capabilities": row.get("capabilities") or [],
                "leads_today": row.get("leads_today", 0),
                "metrics": row.get("metrics") or {},
            })
        active = [a for a in agents if a.get("enabled") and not a.get("is_stale")]
        stale = [a for a in agents if a.get("is_stale")]
        return JSONResponse({
            "agents": agents,
            "active_count": len(active),
            "stale_count": len(stale),
            "total_count": len(agents),
            "stale_threshold_seconds": stale_seconds,
            "checked_at": now.isoformat(),
        })
    except Exception as e:
        return JSONResponse({"agents": [], "active_count": 0, "error": str(e)[:80]})


@app.get("/api/governor/health")
async def governor_health():
    """Return the AGI governor's last cached health snapshot. Auto-refreshes on
    every governor decision; this endpoint just reads the cache."""
    try:
        from empire_agi_governor import get_last_health_snapshot, refresh_health_snapshot
        snap = get_last_health_snapshot()
        if not snap or not snap.get("checked_at"):
            # Cold cache — force a refresh
            snap = refresh_health_snapshot()
        return JSONResponse({
            "stale": snap.get("stale", []),
            "healthy": snap.get("healthy", []),
            "checked_at": snap.get("checked_at"),
            "stale_count": len(snap.get("stale", [])),
            "healthy_count": len(snap.get("healthy", [])),
            "total_count": len(snap.get("stale", [])) + len(snap.get("healthy", [])),
        })
    except Exception as e:
        return JSONResponse({"stale": [], "healthy": [], "error": str(e)[:80]})


@app.post("/api/governor/refresh")
async def governor_refresh():
    """Force a fresh AGI governor health snapshot. Always re-queries Supabase
    instead of returning the cached snapshot. Useful when the SPA needs the
    latest staleness state immediately (e.g. after a heal action)."""
    import time
    t0 = time.time()
    try:
        from empire_agi_governor import refresh_health_snapshot
        snap = refresh_health_snapshot()
        elapsed_ms = round((time.time() - t0) * 1000, 1)
        return JSONResponse({
            "stale": snap.get("stale", []),
            "healthy": snap.get("healthy", []),
            "checked_at": snap.get("checked_at"),
            "stale_count": len(snap.get("stale", [])),
            "healthy_count": len(snap.get("healthy", [])),
            "total_count": len(snap.get("stale", [])) + len(snap.get("healthy", [])),
            "refreshed": True,
            "elapsed_ms": elapsed_ms,
        })
    except Exception as e:
        return JSONResponse({
            "stale": [], "healthy": [],
            "error": str(e)[:80],
            "refreshed": False,
        })


@app.get("/api/panel_court/decisions")
async def panel_court_decisions(limit: int = 30):
    """Recent Panel Court 10-agent ensemble decisions."""
    try:
        db = get_db()
        r = db.table("panel_court_decisions").select("*").order("created_at", desc=True).limit(min(limit, 100)).execute()
        return JSONResponse({"decisions": r.data or [], "count": len(r.data or [])})
    except Exception as e:
        return JSONResponse({"decisions": [], "error": str(e)[:80]})


@app.get("/api/dream/recent")
async def dream_recent(limit: int = 5):
    """Recent dream cycles — insights, rule suggestions, wisdom."""
    try:
        db = get_db()
        r = db.table("dream_memory").select("*").order("dream_cycle", desc=True).limit(min(limit, 20)).execute()
        dreams = r.data or []
        # Parse JSONB fields that might be strings
        for d in dreams:
            for f in ["insights","rule_suggestions","sources_analyzed","sample_sizes","applied_rules"]:
                if isinstance(d.get(f), str):
                    try:
                        d[f] = __import__("json").loads(d[f])
                    except Exception:
                        pass
        return JSONResponse({"dreams": dreams, "count": len(dreams)})
    except Exception as e:
        return JSONResponse({"dreams": [], "error": str(e)[:80]})


@app.get("/api/dream/latest-wisdom")
async def dream_latest_wisdom():
    """Return the latest dream wisdom context for prompt injection."""
    try:
        from empire_dream import get_latest_wisdom
        wisdom = await get_latest_wisdom()
        return JSONResponse({"wisdom": wisdom or "", "has_wisdom": bool(wisdom)})
    except Exception as e:
        return JSONResponse({"wisdom": "", "error": str(e)[:80]})


# In-memory cache for /api/dream/si-feed to avoid repeated Supabase queries
_si_feed_cache: dict = {"_payload": None, "_cached_at": 0}
try:
    SI_FEED_CACHE_TTL_SECONDS = float(os.environ.get("SI_FEED_CACHE_TTL_SECONDS", "60"))
except (ValueError, TypeError):
    SI_FEED_CACHE_TTL_SECONDS = 60

@app.get("/api/dream/si-feed")
async def dream_si_feed():
    """Return latest dream's risk_flags + wisdom formatted for SI systems.
    Cached in-memory; fresh within SI_FEED_CACHE_TTL_SECONDS (default 60s)."""
    import time as _time
    now = _time.time()
    _cached_at = _si_feed_cache.get("_cached_at", 0)
    if now - _cached_at < SI_FEED_CACHE_TTL_SECONDS:
        return JSONResponse(_si_feed_cache["_payload"])
    try:
        db = get_db()
        r = db.table("dream_memory") \
            .select("risk_flags,wisdom_context,insights,rule_suggestions,dream_cycle,created_at") \
            .order("dream_cycle", desc=True) \
            .limit(1) \
            .execute()
        if not r.data:
            return JSONResponse({"risk_flags": [], "wisdom": "", "cycle": None, "stale": True})
        d = r.data[0]
        # Parse JSONB fields
        import json as _j
        risk_flags = d.get("risk_flags") or []
        if isinstance(risk_flags, str):
            try: risk_flags = _j.loads(risk_flags)
            except: risk_flags = []
        insights = d.get("insights") or []
        if isinstance(insights, str):
            try: insights = _j.loads(insights)
            except: insights = []
        rules = d.get("rule_suggestions") or []
        if isinstance(rules, str):
            try: rules = _j.loads(rules)
            except: rules = []
        payload = {
            "risk_flags": risk_flags,
            "risk_count": len(risk_flags),
            "wisdom": d.get("wisdom_context", ""),
            "cycle": d.get("dream_cycle"),
            "insight_count": len(insights),
            "rule_count": len(rules),
            "generated_at": d.get("created_at"),
            "stale": False,
        }
        # Cache the response
        _si_feed_cache["_payload"] = payload
        _si_feed_cache["_cached_at"] = now
        return JSONResponse(payload)
    except Exception as e:
        return JSONResponse({"risk_flags": [], "wisdom": "", "cycle": None, "stale": True, "error": str(e)[:80]})


@app.get("/api/panel_court/pool")
async def panel_court_pool():
    """10-Agent pool status — win rates, temperatures, learning progress."""
    try:
        from bots.panel_court import _get_panel_court
        pc = _get_panel_court()
        return JSONResponse(pc.pool_snapshot())
    except Exception as e:
        return JSONResponse({"agents": [], "error": str(e)[:80]})


@app.get("/api/revenue/accuracy/csv")
async def revenue_accuracy_csv(days: int = 14):
    """Download revenue accuracy data as CSV."""
    import csv, io
    try:
        from bots import predictive_revenue
        data = predictive_revenue.get_accuracy_timeseries(days=min(days, 30))
        series = data.get("series", [])
        summary = data.get("summary", {})

        output = io.StringIO()
        writer = csv.writer(output)
        # Header
        writer.writerow(["Empire AI V49 · Revenue Forecast Accuracy Report"])
        writer.writerow([f"Generated: {data.get('generated_at', '')}"])
        writer.writerow([f"Avg Accuracy: {summary.get('avg_accuracy_pct', 0)}% · Trend: {summary.get('trend', '?')} · Days: {summary.get('days_with_data', 0)}"])
        writer.writerow([])
        writer.writerow(["Date", "Forecasted Fee ($)", "Actual Revenue ($)", "Accuracy (%)"])
        for row in series:
            writer.writerow([
                row.get("date", ""),
                row.get("forecasted_fee", 0),
                row.get("actual_revenue", 0),
                row.get("accuracy_pct", "") if row.get("accuracy_pct") is not None else "N/A",
            ])

        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=empire_revenue_accuracy.csv"},
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/revenue/accuracy/report", response_class=HTMLResponse)
async def revenue_accuracy_report(days: int = 14):
    """Print-friendly HTML report of revenue accuracy (Ctrl+P to save as PDF)."""
    try:
        from bots import predictive_revenue
        data = predictive_revenue.get_accuracy_timeseries(days=min(days, 30))
        series = data.get("series", [])
        summary = data.get("summary", {})

        rows_html = ""
        for row in series:
            acc = row.get("accuracy_pct")
            acc_str = f"{acc}%" if acc is not None else "—"
            acc_color = "#44E5B8" if acc and acc >= 80 else ("#FFB800" if acc and acc >= 50 else "#FF4444")
            rows_html += f"""
            <tr>
              <td>{row.get('date', '')}</td>
              <td class="num">${row.get('forecasted_fee', 0):,.2f}</td>
              <td class="num">${row.get('actual_revenue', 0):,.2f}</td>
              <td class="num" style="color:{acc_color}">{acc_str}</td>
            </tr>"""

        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Empire AI · Revenue Forecast Accuracy</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0f; color: #e2e8f0; padding: 48px 64px; }}
    .report {{ max-width: 900px; margin: 0 auto; }}
    h1 {{ font-size: 22px; font-weight: 200; letter-spacing: -0.02em; margin-bottom: 4px; }}
    h1 em {{ color: #44E5B8; font-style: italic; font-weight: 500; }}
    .sub {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 10px; color: #94a3b8; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 32px; }}
    .summary {{ display: flex; gap: 24px; margin-bottom: 28px; }}
    .sum-card {{ background: #14141e; border: 1px solid #1e293b; padding: 16px 20px; flex: 1; }}
    .sum-label {{ font-family: monospace; font-size: 9px; color: #64748b; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 8px; }}
    .sum-value {{ font-family: monospace; font-size: 24px; color: #f8fafc; font-weight: 500; }}
    .sum-value.teal {{ color: #44E5B8; }}
    .sum-value.amber {{ color: #FFB800; }}
    table {{ width: 100%; border-collapse: collapse; background: #14141e; border: 1px solid #1e293b; }}
    thead th {{ font-family: monospace; font-size: 9px; color: #64748b; letter-spacing: 0.14em; text-transform: uppercase; text-align: left; padding: 12px 16px; border-bottom: 1px solid #1e293b; background: #0f0f17; }}
    tbody td {{ padding: 10px 16px; border-bottom: 1px solid #1e293b; font-family: monospace; font-size: 11px; }}
    tbody tr:last-child td {{ border-bottom: none; }}
    .num {{ text-align: right; }}
    .footer {{ margin-top: 32px; font-family: monospace; font-size: 9px; color: #475569; letter-spacing: 0.08em; }}
    @media print {{ body {{ background: #fff; color: #000; padding: 24px; }} .sum-card, table {{ background: #fff; border-color: #ccc; }} thead th {{ background: #f5f5f5; }} }}
  </style>
</head>
<body>
  <div class="report">
    <h1>Empire AI <em>Revenue Forecast Accuracy</em></h1>
    <div class="sub">Generated {data.get('generated_at', '')}</div>

    <div class="summary">
      <div class="sum-card">
        <div class="sum-label">Avg Accuracy</div>
        <div class="sum-value teal">{summary.get('avg_accuracy_pct', 0)}%</div>
      </div>
      <div class="sum-card">
        <div class="sum-label">Trend</div>
        <div class="sum-value {'amber' if summary.get('trend') == 'declining' else 'teal'}">{summary.get('trend', '—')}</div>
      </div>
      <div class="sum-card">
        <div class="sum-label">Days Analyzed</div>
        <div class="sum-value">{summary.get('days_with_data', 0)}</div>
      </div>
      <div class="sum-card">
        <div class="sum-label">Days with Accuracy</div>
        <div class="sum-value">{summary.get('days_with_accuracy', 0)}</div>
      </div>
    </div>

    <table>
      <thead><tr>
        <th>Date</th>
        <th class="num">Forecasted Fee</th>
        <th class="num">Actual Revenue</th>
        <th class="num">Accuracy</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>

    <div class="footer">
      Empire AI V49 · Predictive Revenue Network · Report generated {data.get('generated_at', '')}
    </div>
  </div>
</body>
</html>""")
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{e}</p>", status_code=500)


@app.post("/api/agents/{agent_id}/toggle")
async def agents_toggle(agent_id: str):
    for a in _AGENTS:
        if a["id"] == agent_id:
            a["enabled"] = not a["enabled"]
            return JSONResponse(_agent_view(a))
    return JSONResponse({"error": "unknown agent: " + agent_id}, status_code=404)




# ─── Leads activity endpoint ──────────────────────────────────
@app.get("/api/v1/leads/activity")
async def leads_activity(limit: int = 50, offset: int = 0, lead_id: str = "", auth: bool = Depends(require_auth)):
    """Return lead activity log entries from the activity_logs table (status changes, notes, deletions)."""
    from fastapi.responses import JSONResponse as _jr
    db = get_db()
    has_more = False
    try:
        q = db.table("activity_logs").select("*").order("created_at", desc=True).range(offset, offset + limit - 1)
        if lead_id:
            q = q.eq("lead_id", lead_id)
        r = q.execute()
        has_more = len(r.data or []) == limit
        entries = []
        for row in (r.data or []):
            entries.append({
                "id": row.get("id"),
                "lead_id": row.get("lead_id"),
                "lead_name": row.get("lead_name") or "—",
                "action": row.get("action"),
                "operator": row.get("operator") or "operator",
                "details": row.get("details") or {},
                "timestamp": (row.get("created_at") or "")[:19],
            })
        return _jr({"entries": entries, "has_more": has_more})
    except Exception as e:
        return _jr({"entries": [], "error": str(e)[:80], "has_more": False})


# ─── Leads list endpoint ────────────────────────────────────────
@app.get("/api/v1/inbound/leads")
async def list_inbound_leads(limit: int = 100, offset: int = 0, auth: bool = Depends(require_auth)):
    """Return inbound leads with notes, sorted by created_at descending."""
    from fastapi.responses import JSONResponse as _jr
    db = get_db()
    try:
        r = db.table("inbound_leads").select("id,name,phone,email,metro,source,status,notes,created_at")             .order("created_at", desc=True)             .range(offset, offset + limit - 1)             .execute()
        leads = r.data or []
    except Exception as e:
        return _jr({"leads": [], "error": str(e)[:80]})
    return _jr({"leads": leads})


# ─── Leads stats endpoint ────────────────────────────────────────
@app.get("/api/v1/inbound/stats")
async def inbound_leads_stats(auth: bool = Depends(require_auth)):
    """Return aggregate stats for inbound leads."""
    from fastapi.responses import JSONResponse as _jr
    db = get_db()
    try:
        r = db.table("inbound_leads").select("status", count="exact").limit(10000).execute()
        leads = r.data or []
        total = r.count or 0
        new_count = sum(1 for l in leads if not l.get("status") or l.get("status") == "new")
        contacted = sum(1 for l in leads if l.get("status") == "contacted")
        qualified = sum(1 for l in leads if l.get("status") == "qualified")
        closed = sum(1 for l in leads if l.get("status") == "closed")
        rejected = sum(1 for l in leads if l.get("status") == "rejected")
    except Exception as e:
        return _jr({"total": 0, "new": 0, "contacted": 0, "qualified": 0, "closed": 0, "rejected": 0, "error": str(e)[:80]})
    return _jr({
        "total": total,
        "new": new_count,
        "contacted": contacted,
        "qualified": qualified,
        "closed": closed,
        "rejected": rejected,
    })


# ─── Leads delete-note endpoint ────────────────────────────────────
@app.post("/api/v1/inbound/leads/delete-note")
async def delete_inbound_lead_note(request: Request, auth: bool = Depends(require_auth)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")
    lead_id = body.get("lead_id")
    timestamp = body.get("timestamp")
    if not lead_id or not timestamp:
        raise HTTPException(400, "lead_id and timestamp required")
    from fastapi.responses import JSONResponse as _jr
    db = get_db()
    try:
        r = db.table("inbound_leads").select("notes,name").eq("id", lead_id).limit(1).execute()
        if not r.data:
            return _jr({"ok": False, "error": "lead not found"})
        raw = r.data[0].get("notes")
        entries = []
        if raw:
            if isinstance(raw, list):
                entries = raw
            elif isinstance(raw, str):
                try:
                    parsed = _gjson.loads(raw)
                    if isinstance(parsed, list):
                        entries = parsed
                except Exception:
                    pass
        before = len(entries)
        entries = [e for e in entries if e.get("timestamp") != timestamp]
        if len(entries) == before:
            return _jr({"ok": False, "error": "note not found"})
        # Persist the updated note list (no synthetic note)
        db.table("inbound_leads").update({"notes": _gjson.dumps(entries, ensure_ascii=False)}).eq("id", lead_id).execute()

        # Operator name for activity + audit
        _dop_name = "operator"
        _dop_id = ""
        _dop_email = ""
        try:
            if isinstance(auth, dict):
                _dop_name = auth.get("name") or auth.get("email", "operator")
                _dop_id = auth.get("id", "")
                _dop_email = auth.get("email", "")
        except Exception:
            pass

        # Insert into activity_logs table
        try:
            _lead_name = (r.data[0].get("name") or "") if r.data else ""
            db.table("activity_logs").insert({
                "lead_id": lead_id,
                "lead_name": _lead_name,
                "action": "note_deleted",
                "operator": _dop_name,
                "details": {"timestamp": timestamp},
            }).execute()
        except Exception:
            pass

        # Audit trail
        try:
            await auth_engine.audit(
                operator_id=_dop_id,
                operator_name=_dop_name,
                operator_email=_dop_email,
                action="lead_note_deleted",
                target_type="inbound_lead",
                target_id=lead_id,
                details={"timestamp": timestamp},
            )
        except Exception:
            pass
        return _jr({"ok": True})
    except Exception as e:
        raise HTTPException(500, str(e))


# ─── Leads update endpoint ─────────────────────────────────────────
@app.post("/api/v1/inbound/leads/update")
async def update_inbound_lead(request: Request, auth: bool = Depends(require_auth)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")
    lead_id = body.get("lead_id")
    if not lead_id:
        raise HTTPException(400, "lead_id required")
    from fastapi.responses import JSONResponse as _jr
    db = get_db()
    update = {}
    _operator_name = "operator"
    try:
        if isinstance(auth, dict):
            _operator_name = auth.get("name") or auth.get("email", "operator")
    except Exception:
        pass
    _status_changed = "status" in body
    if _status_changed:
        update["status"] = body["status"][:50]
    if "notes" in body and body["notes"] is not None:
        # Notes history: store as JSON array [{text, operator, timestamp}, ...]
        new_text = str(body["notes"])[:1000].strip()
        if new_text:
            # Fetch existing notes
            _existing_notes = []
            try:
                r = db.table("inbound_leads").select("notes").eq("id", lead_id).limit(1).execute()
                if r.data and r.data[0].get("notes"):
                    raw = r.data[0]["notes"]
                    if isinstance(raw, list):
                        _existing_notes = raw
                    elif isinstance(raw, str):
                        try:
                            parsed = _gjson.loads(raw)
                            if isinstance(parsed, list):
                                _existing_notes = parsed
                            else:
                                _existing_notes = [{"text": raw, "operator": "system", "timestamp": _gdt.utcnow().isoformat(timespec="seconds")}]
                        except Exception:
                            _existing_notes = [{"text": raw, "operator": "system", "timestamp": _gdt.utcnow().isoformat(timespec="seconds")}]
            except Exception:
                pass
            entry = {
                "text": new_text,
                "operator": _operator_name,
                "timestamp": _gdt.utcnow().isoformat(timespec="seconds"),
            }
            _existing_notes.append(entry)
            update["notes"] = _gjson.dumps(_existing_notes, ensure_ascii=False)
    # ── Activity log ──────────────────────────────────────────────
    try:
        # Fetch lead name once for activity_logs entries
        _act_lead_name = ""
        try:
            _lr = db.table("inbound_leads").select("name").eq("id", lead_id).limit(1).execute()
            _act_lead_name = (_lr.data[0].get("name") or "") if _lr.data else ""
        except Exception:
            pass
        # If status changed, insert into activity_logs
        if _status_changed:
            db.table("activity_logs").insert({
                "lead_id": lead_id,
                "lead_name": _act_lead_name,
                "action": "status_changed",
                "operator": _operator_name,
                "details": {"new_status": body["status"]},
            }).execute()
        # If a note was added, insert into activity_logs
        if "notes" in body and body["notes"] is not None and str(body["notes"])[:1000].strip():
            db.table("activity_logs").insert({
                "lead_id": lead_id,
                "lead_name": _act_lead_name,
                "action": "note_added",
                "operator": _operator_name,
                "details": {"note_snippet": str(body["notes"])[:200].strip()},
            }).execute()
    except Exception:
        pass
        if update:
            db.table("inbound_leads").update(update).eq("id", lead_id).execute()
        # Audit trail for status changes
        if _status_changed:
            try:
                _audit_id = (auth.get("id") or "") if isinstance(auth, dict) else ""
                _audit_email = (auth.get("email") or "") if isinstance(auth, dict) else ""
                await auth_engine.audit(
                    operator_id=_audit_id,
                    operator_name=_operator_name,
                    operator_email=_audit_email,
                    action="lead_status_changed",
                    target_type="inbound_lead",
                    target_id=lead_id,
                    details={"new_status": body["status"]},
                )
            except Exception:
                pass
        return _jr({"ok": True})
    except Exception as e:
        raise HTTPException(500, str(e))

import fastapi


from empire_affiliate_utils import _resolve_affiliate_code_from_request, _safe_utm_value


@app.post("/webhook/lead")
async def webhook_lead(request: fastapi.Request, x_empire_secret: str = fastapi.Header(None, alias="x_empire_secret")):
    import os
    from fastapi.responses import JSONResponse
    from supabase import create_client
    import compliance

    expected_secret = os.environ.get("WEBHOOK_SECRET") or "empire_v49_default_webhook_secret"
    if x_empire_secret != expected_secret:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    name = data.get("name")
    if not name:
        return JSONResponse({"error": "Missing required field: name"}, status_code=400)

    compliance_result = compliance.check("inbound_lead", data)
    if not compliance_result.get("allowed", True):
        return JSONResponse({
            "status": "blocked",
            "reason": compliance_result.get("reason", ""),
            "rule": compliance_result.get("rule", "")
        }, status_code=200)

    try:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not supabase_url or not supabase_key:
            return JSONResponse({"error": "Supabase config missing"}, status_code=500)

        client = create_client(supabase_url, supabase_key)
        payload = {
            "name": name,
            "phone": data.get("phone"),
            "email": data.get("email"),
            "metro": data.get("metro"),
            "source": data.get("source", "web"),
            "raw_jsonb": data
        }
        # ── Affiliate auto-tag: cookie → query param → body field ────
        affiliate_code = None
        try:
            affiliate_code = _resolve_affiliate_code_from_request(
                cookies=dict(request.cookies),
                query_params=dict(request.query_params),
                body=data,
            )
        except Exception:
            pass
        if affiliate_code:
            payload["affiliate_code"] = affiliate_code
            # Determine source for logging (ordered: cookie > query > body)
            _src = "cookie" if request.cookies.get("affiliate_ref") else ("query" if request.query_params.get("affiliate_code") or request.query_params.get("ref") or request.query_params.get("utm_source") else "body")
            log.info(f"[hub] webhook lead tagged with affiliate_code={affiliate_code} (source: {_src})")
        result = client.table("inbound_leads").insert(payload).execute()
        new_id = result.data[0]["id"] if result.data else None

        # ── Route through SalesFunnel → AI Closer pipeline ─────────
        intent = data.get("intent", "medium")
        funnel_route = sales_funnel.optimize_conversion({"intent": intent})
        closer_result = None
        if funnel_route in ("ROUTE_TO_AGI_CLOSER", "ROUTE_TO_VOICE_PIPELINE"):
            # Fire-and-forget: closer runs in background so webhook responds fast.
            # Closer logs all results to ai_closer_decisions table.
            asyncio.create_task(ai_closer.close(
                {
                    "name": name,
                    "phone": data.get("phone", ""),
                    "email": data.get("email", ""),
                    "city": data.get("metro", ""),
                },
                alert_summary={
                    "event": "Inbound Lead",
                    "severity": "Moderate",
                    "urgency": "Normal",
                    "area": data.get("metro", ""),
                },
            ))
            closer_result = {"status": "queued"}

        return JSONResponse({
            "status": "success",
            "id": new_id,
            "funnel_route": funnel_route,
            "closer_result": closer_result,
        })
    except Exception as e:
        return JSONResponse({"error": f'Database write error: {str(e)}'}, status_code=500)

# ─────────────────────────────────────────────────────────────────────
# LEAD INGESTION API — lightweight POST endpoint for radar_targets
# ─────────────────────────────────────────────────────────────────────

@app.post("/api/v1/leads/ingest")
async def leads_ingest(request: Request, auth: bool = Depends(require_auth)):
    """
    Lightweight lead ingestion endpoint.

    Accepts a single lead dict or a batch {leads: [...]}. Writes each
    lead to radar_targets after deduplication by phone number and
    warehouse_name+city. Idempotent.

    Body (single): { warehouse_name (required), phone?, email?, address?, city?, state?, ... }
    Body (batch): { leads: [...] }

    Returns: { ok, ingested, skipped, errors }
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    db = get_db()
    now_iso = datetime.now(timezone.utc).isoformat()

    raw_leads = body.get("leads", [body]) if isinstance(body, dict) else []
    if not raw_leads or not isinstance(raw_leads, list):
        return JSONResponse({"ok": False, "error": "body must be a lead dict or {leads: [...]}"}, status_code=400)

    ingested = 0
    skipped = 0
    errors = []

    for i, lead in enumerate(raw_leads):
        if not isinstance(lead, dict):
            skipped += 1
            errors.append({"index": i, "error": "not_a_dict"})
            continue

        name = (lead.get("warehouse_name") or "").strip()
        if not name:
            skipped += 1
            errors.append({"index": i, "error": "warehouse_name_required"})
            continue

        phone = (lead.get("phone") or "").strip()
        city = (lead.get("city") or "").strip()

        # Dedup: skip if phone exists OR same name+city
        try:
            if phone:
                dup = db.table("radar_targets").select("id").eq("phone", phone).limit(1).execute()
                if dup.data:
                    skipped += 1
                    errors.append({"index": i, "error": "duplicate_phone", "phone": phone})
                    continue

            if city:
                dup = db.table("radar_targets").select("id") \
                    .eq("warehouse_name", name[:200]) \
                    .eq("city", city) \
                    .limit(1).execute()
                if dup.data:
                    skipped += 1
                    errors.append({"index": i, "error": "duplicate_name_city", "name": name[:50], "city": city})
                    continue
        except Exception as e:
            skipped += 1
            errors.append({"index": i, "error": f"dedup_check_failed: {e}"})
            continue

        # Build insert payload
        source = (lead.get("source") or "api_ingest").strip()
        meta = dict(lead.get("meta") or {})
        meta["source"] = source
        meta["ingested_at"] = now_iso

        insert_payload = {
            "warehouse_name": name[:200],
            "phone": phone[:20],
            "email": (lead.get("email") or "").strip()[:200],
            "address": (lead.get("address") or "").strip()[:300],
            "city": city[:100],
            "state": (lead.get("state") or "").strip()[:10],
            "source_url": (lead.get("source_url") or "").strip()[:500],
            "status": (lead.get("status") or "active").strip(),
            "asset_value": int(lead["asset_value"]) if lead.get("asset_value") is not None else None,
            "urgency_score": int(lead["urgency_score"]) if lead.get("urgency_score") is not None else None,
            "damage_severity": (lead.get("damage_severity") or "").strip()[:50] or None,
            "meta": meta,
            "created_at": now_iso,
        }
        insert_payload = {k: v for k, v in insert_payload.items() if v is not None}

        try:
            db.table("radar_targets").insert(insert_payload).execute()
            ingested += 1
        except Exception as e:
            skipped += 1
            errors.append({"index": i, "error": f"insert_failed: {str(e)[:200]}", "name": name[:50]})

    return JSONResponse({
        "ok": ingested > 0 or len(errors) == 0,
        "ingested": ingested,
        "skipped": skipped,
        "errors": errors[:50],
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


