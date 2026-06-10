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
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from supabase import create_client, Client
from empire_switchboard import _sb

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
from empire_switchboard import register_switchboard_routes
from empire_partner_onboarding import register_partner_routes


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
register_auth_routes(app, auth_engine=auth_engine, require_auth=require_auth)
register_inbound_routes(app, inbound_triage, require_auth=require_auth)
register_console_routes(app, console=console, require_auth=require_auth, get_db=get_db)
register_storm_routes(app, storm_orchestrator, require_auth=require_auth)
register_map_routes(app, scout=storm_orchestrator.scout, get_db=get_db, require_auth=require_auth)
register_switchboard_routes(app, require_auth=require_auth)
register_partner_routes(app, require_auth=require_auth)


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
_GOV_WATCH = {"empire-orchestrator", "empire-live", "empire-voice"}  # auto-heal allowlist
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


# ─── /api/v1/compliance/stats: Compliance dashboard data ──────────────────
from datetime import datetime as _cdt, timezone as _ctz
from supabase import create_client as _cc
import os as _cos

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


# ─── /api/agents: Sniper Fleet (in-memory MOCK STUB — no real agent backend yet) ──
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

def _get_agent_leads():
    leads = {"storm":0,"legal":0,"warehouse":0,"logistics":0,"reddit":0,"linkedin":0}
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
    try:
        from bots import predictive_revenue
        return JSONResponse(predictive_revenue.pipeline_forecast())
    except Exception as e:
        return JSONResponse({"error": str(e), "lead_count": 0, "pipeline_value": 0, "forecasted_revenue": 0})


@app.post("/api/agents/{agent_id}/toggle")
async def agents_toggle(agent_id: str):
    for a in _AGENTS:
        if a["id"] == agent_id:
            a["enabled"] = not a["enabled"]
            return JSONResponse(_agent_view(a))
    return JSONResponse({"error": "unknown agent: " + agent_id}, status_code=404)




# ─── Notes activity endpoint ──────────────────────────────────────
@app.get("/api/v1/notes/activity")
async def notes_activity(limit: int = 100, auth: bool = Depends(require_auth)):
    """Return all notes across all leads as a flat reverse-chronological feed."""
    from fastapi.responses import JSONResponse as _jr
    db = get_db()
    try:
        r = db.table("inbound_leads").select("id,name,notes,created_at").not_.is_("notes", "null").order("created_at", desc=True).limit(limit).execute()
    except Exception:
        try:
            r = db.table("inbound_leads").select("id,name,notes,created_at").not_.is_("notes", "null").execute()
        except Exception as e:
            return _jr({"entries": [], "error": str(e)[:80]})
    entries = []
    for lead in (r.data or []):
        raw = lead.get("notes")
        note_list = []
        if raw:
            if isinstance(raw, list):
                note_list = raw
            elif isinstance(raw, str):
                try:
                    p = _gjson.loads(raw)
                    if isinstance(p, list):
                        note_list = p
                    else:
                        note_list = [{"text": raw}]
                except Exception:
                    note_list = [{"text": raw}]
        for n in note_list:
            n["lead_id"] = lead.get("id")
            n["lead_name"] = lead.get("name") or "—"
            entries.append(n)
    entries.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return _jr({"entries": entries[:limit]})


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
        r = db.table("inbound_leads").select("notes").eq("id", lead_id).limit(1).execute()
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
        db.table("inbound_leads").update({"notes": _gjson.dumps(entries, ensure_ascii=False)}).eq("id", lead_id).execute()
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
    if "status" in body:
        update["status"] = body["status"][:50]
    if "notes" in body and body["notes"] is not None:
        # Notes history: store as JSON array [{text, operator, timestamp}, ...]
        operator_name = "operator"
        try:
            if isinstance(auth, dict):
                operator_name = auth.get("name") or auth.get("email", "operator")
        except Exception:
            pass
        new_text = str(body["notes"])[:1000].strip()
        if new_text:
            # Fetch existing notes
            existing = []
            try:
                r = db.table("inbound_leads").select("notes").eq("id", lead_id).limit(1).execute()
                if r.data and r.data[0].get("notes"):
                    raw = r.data[0]["notes"]
                    if isinstance(raw, list):
                        existing = raw
                    elif isinstance(raw, str):
                        try:
                            parsed = _gjson.loads(raw)
                            if isinstance(parsed, list):
                                existing = parsed
                            else:
                                existing = [{"text": raw, "operator": "system", "timestamp": _gdt.utcnow().isoformat(timespec="seconds")}]
                        except Exception:
                            existing = [{"text": raw, "operator": "system", "timestamp": _gdt.utcnow().isoformat(timespec="seconds")}]
            except Exception:
                pass
            entry = {
                "text": new_text,
                "operator": operator_name,
                "timestamp": _gdt.utcnow().isoformat(timespec="seconds"),
            }
            existing.append(entry)
            update["notes"] = _gjson.dumps(existing, ensure_ascii=False)
    try:
        if update:
            db.table("inbound_leads").update(update).eq("id", lead_id).execute()
        return _jr({"ok": True})
    except Exception as e:
        raise HTTPException(500, str(e))

import fastapi

@app.post("/webhook/lead")
async def webhook_lead(request: fastapi.Request, x_empire_secret: str = fastapi.Header(None)):
    import os
    from fastapi.responses import JSONResponse
    from supabase import create_client
    import compliance

    expected_secret = os.environ.get("WEBHOOK_SECRET", "empire_v49_secret")
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
        result = client.table("inbound_leads").insert(payload).execute()
        new_id = result.data[0]["id"] if result.data else None
        return JSONResponse({"status": "success", "id": new_id})
    except Exception as e:
        return JSONResponse({"error": f'Database write error: {str(e)}'}, status_code=500)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


