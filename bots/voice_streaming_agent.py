"""
EMPIRE V49 - VOICE STREAMING AGENT
==================================
Autonomous agent that orchestrates LIVE Kokoro TTS into Vonage phone
calls for high-value storm-strike targets. Driven by the AGI brain:
each candidate target is first scored by BrainDecider; if the brain
returns GO with confidence >= STREAM_CONFIDENCE_THRESHOLD we use the
streaming path (synthetic_brain WebSocket -> Vonage `stream` NCCO),
otherwise we fall back to the static NCCO (Vonage's built-in TTS).

AGI · SI · PREDICTIVE REVENUE INJECTION:
  - AGI Governor: strategy_for_niche() selects optimal call strategy
  - SI Strategy: best_for_niche() evolves genome per call outcome
  - Predictive Revenue: per-target revenue estimation for priority
    REVENUE = asset_value × 0.03 × niche_win_rate × urgency_multiplier

Pipeline per cycle:
  1. _next_target() pulls highest-asset unconverted radar_target
  2. BrainDecider.decide() returns GO/NO_GO + confidence + reasoning
  3. SI Strategy selects best genome for the niche
  4. GO + high conf -> _register_stream() then place_streaming_strike()
  5. GO + low conf  -> place_strike_call() (static NCCO)
  6. AGI Governor records outcome for strategy evolution
  7. Heartbeat to agent_registry every cycle
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client
import httpx

log = logging.getLogger("voice.streaming")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# synthetic_brain server (local) - we register streams here before
# placing the Vonage call. Vonage then opens a WebSocket to this
# server to pull the live Kokoro audio.
SYNTHETIC_BRAIN_URL = os.environ.get("SYNTHETIC_BRAIN_URL", "http://127.0.0.1:8005")
SYNTHETIC_BRAIN_API_KEY = os.environ.get("SYNTHETIC_BRAIN_API_KEY", "")

# Public URL of this synthetic_brain (used to build the wss:// URL
# that Vonage will connect to). If unset, defaults to the loopback
# address which only works for local dev with a tunnel.
EMPIRE_PUBLIC_BASE_URL = os.environ.get("EMPIRE_PUBLIC_BASE_URL", "")

# Only use the streaming path when the brain confidence is high.
# Lower-confidence strikes fall back to the static Vonage TTS NCCO
# (cheaper, no synthetic_brain WebSocket setup).
STREAM_CONFIDENCE_THRESHOLD = float(os.environ.get("STREAM_CONFIDENCE_THRESHOLD", "0.7"))

# How often the background loop polls for new strike targets.
STREAMING_INTERVAL_HOURS = float(os.environ.get("VOICE_STREAMING_INTERVAL_HOURS", "0.5"))


def _get_sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _script_for_target(target: dict, decision: dict) -> str:
    """
    Build the live-call pitch script based on the target + brain decision.
    Static templates (no LLM) for low latency - the LLM-rendered script
    path lives in synthetic_brain.py and is used for video ads, not the
    phone-call strike flow.
    """
    name = target.get("warehouse_name") or "your facility"
    city = target.get("city") or "your area"
    state = target.get("state") or ""
    location = f"{city}, {state}" if state else city
    confidence = float(decision.get("confidence", 0))

    if decision.get("decision") == "GO" and confidence >= STREAM_CONFIDENCE_THRESHOLD:
        return (
            f"Hello, this is Empire AI Predictive Cloud. "
            f"Our weather intelligence detected severe storm activity near {location}. "
            f"We specialize in commercial property storm response. "
            f"A specialist is available to assess your facility at {name}. "
            f"Please hold while we connect you."
        )
    if decision.get("decision") == "GO":
        return (
            f"Hello, this is Empire AI. "
            f"Our system has noted recent weather activity near {location}. "
            f"This is a paid commercial dispatch service. "
            f"Please hold while we connect you to a specialist."
        )
    return (
        "Thank you for calling Empire AI. "
        "Please hold while we connect you to a specialist."
    )


class VoiceStreamingAgent:
    """Orchestrates the AGI-brained streaming voice strike pipeline.

    AGI · SI · Predictive Revenue wired:
      - AGI Governor: strategy_for_niche() + record_strategy_outcome()
      - SI Strategy: best_for_niche() genome selection per niche
      - Predictive Revenue: prioritizes targets by estimated call value
    """

    def __init__(self, agi_governor=None, si_strategy=None):
        self._agi_governor = agi_governor
        self._si_strategy = si_strategy
        self.stats = {
            "cycles": 0,
            "targets_evaluated": 0,
            "brain_go": 0,
            "brain_no_go": 0,
            "streaming_strikes": 0,
            "static_strikes": 0,
            "errors": 0,
        }
        # Lazy-loaded so the agent can be imported without the full
        # voice + brain stack being available (for unit tests).
        self._brain_decider = None
        self._voice_router = None
        self._ai_router = None
        self._public_base_url = EMPIRE_PUBLIC_BASE_URL or ""

    async def _ensure_dependencies(self):
        if self._brain_decider is None:
            from empire_ai_router import AIRouter
            from empire_brain_decide import BrainDecider
            from empire_voice import VoiceRouter
            self._ai_router = AIRouter()
            self._brain_decider = BrainDecider(self._ai_router)
            self._voice_router = VoiceRouter(
                public_base_url=self._public_base_url,
            )
            log.info("[voice_streaming] brain + voice router initialized")

    async def heartbeat(self):
        try:
            sb = _get_sb()
            sb.table("agent_registry").upsert({
                "agent_name": "voice_streaming_agent",
                "role_name": "voice_streaming_agent",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": ["voice_streaming", "tts", "vonage", "agi_orchestrated"],
            }, on_conflict="agent_name").execute()
        except Exception as e:
            log.debug(f"[voice_streaming] heartbeat failed: {e}")

    def _next_target(self) -> dict | None:
        try:
            sb = _get_sb()
            r = sb.table("radar_targets") \
                .select("id,warehouse_name,address,city,state,phone,phone2,asset_value,damage_severity") \
                .order("asset_value", desc=True) \
                .limit(10).execute()
            for row in (r.data or []):
                phone = row.get("phone") or row.get("phone2")
                if phone:
                    return row
            return None
        except Exception as e:
            log.warning(f"[voice_streaming] target fetch failed: {e}")
            return None

    async def _register_stream(self, script: str, voice: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    f"{SYNTHETIC_BRAIN_URL}/api/v1/synthetic/register_stream",
                    json={
                        "script": script,
                        "voice": voice,
                        "public_base_url": self._public_base_url,
                    },
                    headers={"X-API-Key": SYNTHETIC_BRAIN_API_KEY},
                )
                if r.status_code == 200:
                    return r.json()
                log.warning(f"[voice_streaming] register_stream {r.status_code}: {r.text[:200]}")
                return None
        except Exception as e:
            log.warning(f"[voice_streaming] register_stream error: {e}")
            return None

    async def _brain_decide(self, target: dict) -> dict:
        alert = {
            "event": "Storm Activity",
            "severity": target.get("damage_severity") or "Moderate",
            "urgency": "",
            "area": f"{target.get('city', '')}, {target.get('state', '')}".strip(", "),
        }
        # ── SI Strategy: enrich target with genome context ──
        niche = None
        if self._si_strategy:
            try:
                city = target.get("city") or ""
                damage = target.get("damage_severity") or ""
                if "tornado" in damage.lower():
                    niche = "Tornado Damage Repair"
                elif "hail" in damage.lower():
                    niche = "Hail Damage Repair"
                elif "flood" in damage.lower():
                    niche = "Flood Damage Restoration"
                else:
                    niche = "Storm Damage Restoration"
                best = self._si_strategy.best_for_niche(niche)
                if best:
                    log.info(f"[voice_streaming] SI genome: {best} for {city} ({niche})")
            except Exception:
                pass
        try:
            decision = await self._brain_decider.decide(
                target={
                    "warehouse_name": target.get("warehouse_name") or "Target",
                    "address": target.get("address") or "unknown",
                    "city": target.get("city") or "unknown",
                    "phone": target.get("phone") or target.get("phone2") or "",
                    "email": "",
                    "website": "",
                    "raw_tags": {"types": ["commercial"]},
                },
                alert_summary=alert,
                memory_context="",
            )
            return decision
        except Exception as e:
            log.warning(f"[voice_streaming] brain.decide failed: {e}")
            return {"decision": "NO_GO", "confidence": 0.0, "reasoning": "brain unavailable"}

    async def run_cycle(self) -> dict:
        await self._ensure_dependencies()
        self.stats["cycles"] += 1
        target = self._next_target()
        if not target:
            return {"ok": True, "action": "no_target"}

        self.stats["targets_evaluated"] += 1

        # ── Predictive Revenue: estimate call value for logging ──
        asset_value = float(target.get("asset_value") or 0)
        niche = self._infer_niche(target)
        predicted_revenue = 0.0
        if asset_value > 0 and self._agi_governor:
            try:
                win_rate = self._agi_governor.get_niche_win_rate(niche) or 0.1
                urgency_mult = 1.8 if (target.get("damage_severity") or "").lower() in ("severe", "extreme") else 1.2
                predicted_revenue = round(asset_value * 0.03 * win_rate * urgency_mult, 2)
                log.info(f"[voice_streaming] predicted revenue: ${predicted_revenue:,.2f} for {target.get('warehouse_name', '?')}")
            except Exception:
                pass

        decision = await self._brain_decide(target)

        if decision.get("decision") != "GO":
            self.stats["brain_no_go"] += 1
            return {"ok": True, "action": "no_go", "decision": decision}

        self.stats["brain_go"] += 1

        # ── AGI Governor: select SI strategy for niche ──
        strategy = "AGGRESSIVE_STRIKE"
        if self._agi_governor:
            try:
                strategy = self._agi_governor.strategy_for_niche(niche) or strategy
            except Exception:
                pass

        confidence = float(decision.get("confidence", 0))
        phone = target.get("phone") or target.get("phone2")
        if not phone:
            return {"ok": False, "action": "no_phone"}

        result = {}
        if confidence >= STREAM_CONFIDENCE_THRESHOLD:
            script = _script_for_target(target, decision)
            reg = await self._register_stream(script, "am_michael")
            if not reg:
                self.stats["errors"] += 1
                return {"ok": False, "action": "register_failed"}
            result = await self._voice_router.place_streaming_strike(
                to_number=phone,
                ws_url=reg["ws_url"],
                target_address=target.get("address", ""),
                operator_number=os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
                brain_decision=decision,
            )
            self.stats["streaming_strikes"] += 1
        else:
            # Low confidence GO -> static NCCO (Vonage built-in TTS)
            result = await self._voice_router.place_strike_call(
                to_number=phone,
                target_address=target.get("address", ""),
                asset_value=asset_value,
                operator_number=os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
                brain_decision=decision,
            )
            self.stats["static_strikes"] += 1

        # ── AGI Governor: record outcome for strategy evolution ──
        success = result.get("ok", False)
        revenue = predicted_revenue if success else 0.0
        if self._agi_governor:
            try:
                self._agi_governor.record_strategy_outcome(strategy, niche, success, revenue)
                log.debug(f"[voice_streaming] AGI recorded: {strategy} {niche} success={success}")
            except Exception:
                pass

        action = "streaming_strike" if confidence >= STREAM_CONFIDENCE_THRESHOLD else "static_strike"
        return {
            "ok": result.get("ok", False),
            "action": action,
            "voice_id": reg.get("voice_id") if confidence >= STREAM_CONFIDENCE_THRESHOLD else None,
            "call_result": result,
            "decision": decision,
            "strategy": strategy,
            "niche": niche,
            "predicted_revenue": predicted_revenue,
        }

    @staticmethod
    def _infer_niche(target: dict) -> str:
        damage = (target.get("damage_severity") or "").lower()
        if "tornado" in damage or "nado" in damage:
            return "Tornado Damage Repair"
        if "hurricane" in damage:
            return "Hurricane Damage Restoration"
        if "hail" in damage:
            return "Hail Damage Repair"
        if "flood" in damage:
            return "Flood Damage Restoration"
        return "Storm Damage Restoration"

    async def trigger_strike(self, target: dict) -> dict:
        """One-shot trigger against an explicit target (skip the poll)."""
        await self._ensure_dependencies()
        decision = await self._brain_decide(target)
        if decision.get("decision") != "GO":
            return {"ok": True, "action": "no_go", "decision": decision}
        phone = target.get("phone") or target.get("phone2")
        if not phone:
            return {"ok": False, "action": "no_phone"}
        script = _script_for_target(target, decision)
        reg = await self._register_stream(script, "am_michael")
        if not reg:
            return {"ok": False, "action": "register_failed"}
        result = await self._voice_router.place_streaming_strike(
            to_number=phone,
            ws_url=reg["ws_url"],
            target_address=target.get("address", ""),
            operator_number=os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
            brain_decision=decision,
        )
        return {
            "ok": result.get("ok", False),
            "action": "streaming_strike",
            "voice_id": reg["voice_id"],
            "ws_url": reg["ws_url"],
            "call_result": result,
            "decision": decision,
        }


# Module-level interval (AGI governor reads this via _AGENT_INTERVAL_HOURS)
def get_streaming_interval() -> float:
    return STREAMING_INTERVAL_HOURS


async def run_loop():
    log.info(
        f"[voice_streaming] ONLINE - interval={STREAMING_INTERVAL_HOURS}h "
        f"- stream_threshold={STREAM_CONFIDENCE_THRESHOLD}"
    )
    # ── Lazy-wire AGI Governor + SI Strategy at runtime ──
    agi_gov = None
    si_strat = None
    try:
        from empire_agi_governor import governor as _gov
        agi_gov = _gov
    except Exception:
        log.debug("[voice_streaming] AGI Governor not available")
    try:
        from empire_si_strategy import StrategyEvolution
        si_strat = StrategyEvolution.get_shared_instance()
    except Exception:
        log.debug("[voice_streaming] SI Strategy not available")
    agent = VoiceStreamingAgent(agi_governor=agi_gov, si_strategy=si_strat)
    await agent.heartbeat()
    while True:
        try:
            result = await agent.run_cycle()
            log.info(f"[voice_streaming] cycle: {result.get('action', '?')}")
            await agent.heartbeat()
        except Exception as e:
            log.error(f"[voice_streaming] loop error: {e}")
        await asyncio.sleep(STREAMING_INTERVAL_HOURS * 3600)


def run():
    """Sync entry point for main.py / pm2."""
    asyncio.run(run_loop())


if __name__ == "__main__":
    if "--once" in sys.argv:
        agent = VoiceStreamingAgent()
        out = asyncio.run(agent.run_cycle())
        print(json.dumps(out, indent=2, default=str))
    elif "--trigger" in sys.argv:
        phone = sys.argv[sys.argv.index("--trigger") + 1] if len(sys.argv) > sys.argv.index("--trigger") + 1 else "+15551234567"
        agent = VoiceStreamingAgent()
        out = asyncio.run(agent.trigger_strike({
            "warehouse_name": "Test Facility",
            "address": "123 Test St",
            "city": "Wichita",
            "state": "KS",
            "phone": phone,
            "damage_severity": "Severe",
            "asset_value": 2500000,
        }))
        print(json.dumps(out, indent=2, default=str))
    else:
        run()
