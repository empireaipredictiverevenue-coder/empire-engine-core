"""
EMPIRE V49 · AI CLOSER — AGI-BRAINED + SYNTHETIC INTELLIGENCE VOICE PIPELINE
==============================================================================
Replaces the VAPI_CLOSER stub with the in-house voice + brain stack:

  Lead Inbound → BrainDecider (GO/NO_GO) → Strategy Selection (AGI Governor)
                                           ↓
         ┌─────────────────────────────────┴─────────────────────────────────┐
         │  GO + high conf  │  GO + medium conf  │  GO + low conf  │  NO_GO  │
         │  Live Kokoro TTS │  Static NCCO call   │  SMS/Email      │  Nurture│
         │  (streaming)     │  (Vonage built-in)  │  follow-up      │  drip   │
         └────────────────────────────────────────────────────────────────────┘
                                           ↓
                          Outcome → AGI Governor → SI Strategy Evolution

Architecture:
  - BrainDecider scores every lead via Ollama LLM (Go/No-Go + confidence)
  - AGI Governor picks the best SI-evolved strategy per niche (genome-based)
  - VoiceStreamingAgent triggers live Kokoro TTS for high-confidence GOs
  - VoiceRouter handles static NCCO calls for medium-confidence GOs
  - SMSEngine / EmailEngine for nurture fallbacks
  - Compliance checks (TCPA, DNC, calling hours) before any call
  - Outcomes feed back to StrategyEvolution for continuous learning

Confidence thresholds:
  AGI_STREAM_THRESHOLD  = 0.7  → live Kokoro TTS streaming call
  STATIC_CALL_THRESHOLD = 0.4  → static NCCO call (Vonage built-in TTS)
  Below 0.4                    → nurture (email/SMS drip)

Supabase tables:
  - ai_closer_decisions: full decision trail with brain scores + strategy + outcomes
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Callable

sys.path.insert(0, "/root/empire-v49")

log = logging.getLogger("empire.ai.closer")

# ── Confidence thresholds for routing ───────────────────────────────
AGI_STREAM_THRESHOLD  = float(os.environ.get("CLOSER_AGI_STREAM_THRESHOLD", "0.7"))
STATIC_CALL_THRESHOLD = float(os.environ.get("CLOSER_STATIC_CALL_THRESHOLD", "0.4"))
# ── Voice profile for live TTS ──────────────────────────────────────
DEFAULT_VOICE = os.environ.get("CLOSER_DEFAULT_VOICE", "am_michael")

# ── Nurture sequence types ──────────────────────────────────────────
NURTURE_STORM = "storm_strike"
NURTURE_GENERIC = "generic_outreach"


class AICloser:
    """
    AGI-powered sales closer that orchestrates the full voice pipeline.

    Dependencies (all injected — no hard imports):
      - brain_decider:  BrainDecider instance (Go/No-Go scoring)
      - voice_router:   VoiceRouter instance (static NCCO + streaming calls)
      - sms_engine:     SMSEngine instance (nurture fallback, optional)
      - email_engine:   EmailEngine instance (nurture fallback, optional)
      - get_db:         Callable returning Supabase client (for logging)
      - operator_number: phone number for warm-forward connect (optional)
    """

    def __init__(
        self,
        *,
        brain_decider: Any = None,
        voice_router: Any = None,
        sms_engine: Any = None,
        email_engine: Any = None,
        get_db: Optional[Callable] = None,
        operator_number: str = "",
        stream_confidence: float = AGI_STREAM_THRESHOLD,
        static_confidence: float = STATIC_CALL_THRESHOLD,
        default_voice: str = DEFAULT_VOICE,
        pain_points: Any = None,
    ):
        self.brain_decider = brain_decider
        self.voice_router = voice_router
        self.sms_engine = sms_engine
        self.email_engine = email_engine
        self.get_db = get_db
        self.operator_number = operator_number or os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
        self.stream_confidence = stream_confidence
        self.static_confidence = static_confidence
        self.default_voice = default_voice
        self.pain_points = pain_points

        # Lazy-loaded deps (imported on first use so the module is importable
        # without the full stack being wired)
        self._agi_governor = None
        self._streaming_agent = None
        self._synthetic_brain_url = os.environ.get("SYNTHETIC_BRAIN_URL", "http://127.0.0.1:8005")
        self._synthetic_brain_key = os.environ.get("SYNTHETIC_BRAIN_API_KEY", "")
        self._public_base_url = os.environ.get("EMPIRE_PUBLIC_BASE_URL", "")

        self.stats = {
            "leads_processed": 0,
            "brain_go": 0,
            "brain_no_go": 0,
            "agi_stream_calls": 0,
            "static_calls": 0,
            "nurture_routed": 0,
            "errors": 0,
        }

    # ── LAZY DEP LOADING ────────────────────────────────────────────
    def _ensure_governor(self):
        """Load the AGI Governor singleton instance (not the class)."""
        if self._agi_governor is None:
            from empire_agi_governor import governor as _gov
            self._agi_governor = _gov

    # ── MAIN CLOSE METHOD ───────────────────────────────────────────
    async def close(
        self,
        lead: Dict,
        alert_summary: Optional[Dict] = None,
        niche: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the full AI closer pipeline on a lead.

        Args:
            lead: dict with keys: name/warehouse_name, phone, email, address,
                  city, state, asset_value, damage_severity, source, type_tags
            alert_summary: optional storm alert context (event, severity, area)
            niche: optional explicit niche override (auto-inferred if omitted)

        Returns:
            dict with: decision, action, confidence, strategy, reasoning,
                       call_result (if call placed), niche
        """
        self.stats["leads_processed"] += 1

        # ── Normalize lead shape ────────────────────────────────────
        name = lead.get("warehouse_name") or lead.get("name") or "Unknown"
        phone = lead.get("phone") or lead.get("phone2") or ""
        email = lead.get("email") or ""
        address = lead.get("address") or ""
        city = lead.get("city") or ""
        state = lead.get("state") or ""

        # ── Infer niche ─────────────────────────────────────────────
        if not niche:
            niche = self._infer_niche(lead, alert_summary)

        # ── Phase 1: BrainDecider scores the lead ───────────────────
        if not self.brain_decider:
            log.warning("[ai_closer] brain_decider not wired — defaulting to GO")
            decision = {"decision": "GO", "confidence": 0.5, "reasoning": "brain unavailable"}
        else:
            alert_ctx = alert_summary or {
                "event": "Inbound Lead",
                "severity": lead.get("damage_severity") or "Moderate",
                "urgency": "Normal",
                "area": f"{city}, {state}".strip(", "),
            }
            decision = await self.brain_decider.decide(
                target={
                    "warehouse_name": name,
                    "address": address,
                    "city": city,
                    "phone": phone,
                    "email": email,
                    "website": lead.get("website", ""),
                    "raw_tags": lead.get("type_tags") or {"types": ["commercial"]},
                },
                alert_summary=alert_ctx,
            )
            # Normalize decision keys
            decision["decision"] = (decision.get("decision") or "NO_GO").upper()
            try:
                decision["confidence"] = max(0.0, min(1.0, float(decision.get("confidence", 0))))
            except (TypeError, ValueError):
                decision["confidence"] = 0.5

        # ── Phase 2: Select SI-evolved strategy ─────────────────────
        strategy = await self._select_strategy(niche, decision)

        confidence = decision["confidence"]

        # Dynamic threshold adaptation per lane: successful lanes get
        # lower thresholds (more aggressive calls), struggling lanes get
        # higher thresholds (more conservative).
        self._ensure_governor()
        win_rate = 0.0
        if self._agi_governor and hasattr(self._agi_governor, "get_niche_win_rate"):
            win_rate = self._agi_governor.get_niche_win_rate(niche)
        adaptation_shift = 0.0
        if win_rate >= 0.20:
            adaptation_shift = -0.15  # more aggressive: lower thresholds
        elif win_rate >= 0.10:
            adaptation_shift = -0.05
        elif win_rate < 0.05:
            adaptation_shift = 0.10   # more conservative: raise thresholds
        dynamic_stream_thresh = max(0.4, min(0.95, self.stream_confidence + adaptation_shift))
        dynamic_static_thresh = max(0.2, min(0.80, self.static_confidence + adaptation_shift))

        # ── Phase 3: Route based on decision + confidence ───────────
        if decision["decision"] == "GO" and confidence >= dynamic_stream_thresh:
            result = await self._dispatch_agi_stream(lead, decision, strategy, niche)
            self.stats["brain_go"] += 1
            # Only count stream if it wasn't blocked or fell back
            if result.get("action") == "agi_stream_call":
                self.stats["agi_stream_calls"] += 1
            elif result.get("action") == "static_call":
                self.stats["static_calls"] += 1

        elif decision["decision"] == "GO" and confidence >= dynamic_static_thresh:
            result = await self._dispatch_static_call(lead, decision, strategy, niche)
            self.stats["brain_go"] += 1
            if result.get("action") == "static_call":
                self.stats["static_calls"] += 1

        elif decision["decision"] == "GO":
            # Low confidence GO → nurture (SMS/Email drip)
            result = await self._dispatch_nurture(lead, decision, strategy, niche)
            self.stats["brain_go"] += 1
            self.stats["nurture_routed"] += 1

        else:
            # NO_GO → log and skip
            self.stats["brain_no_go"] += 1
            result = {
                "action": "no_go",
                "decision": decision["decision"],
                "confidence": confidence,
                "reasoning": decision.get("reasoning", ""),
                "strategy": strategy,
                "niche": niche,
                "lead_name": name,
                "lead_phone": phone,
            }

        # ── Phase 4: Record outcome to SI strategy evolution ────────
        await self._record_outcome(strategy, niche, result)

        # ── Phase 5: Persist decision log ───────────────────────────
        self._log_decision(lead, decision, strategy, niche, result)

        return result

    # ── STRATEGY SELECTION (AGI GOVERNOR + SI GENOME) ───────────────
    async def _select_strategy(self, niche: str, decision: Dict) -> str:
        """Pick the best SI-evolved strategy for this niche."""
        self._ensure_governor()
        try:
            # Governor already delegates to the shared SI StrategyEvolution instance
            if self._agi_governor:
                best = self._agi_governor.strategy_for_niche(niche)
                if best:
                    return best
        except Exception as e:
            log.debug(f"[ai_closer] strategy lookup via governor failed: {e}")

        # Ultimate fallback
        return "AGGRESSIVE_STRIKE"

    # ── PAIN POINTS HELPER ─────────────────────────────────────
    def _get_pain_points_used(self, niche: str) -> list:
        """Return top pain point IDs for a niche. Safe no-op if library not wired."""
        if not self.pain_points:
            return []
        try:
            return self.pain_points.get_script_pain_points(niche)
        except Exception:
            return []

    # ── AGI STREAM DISPATCH (live Kokoro TTS) ───────────────────────
    async def _dispatch_agi_stream(
        self, lead: Dict, decision: Dict, strategy: str, niche: str
    ) -> Dict:
        """High-confidence GO → live Kokoro TTS via synthetic_brain WebSocket."""
        phone = lead.get("phone") or lead.get("phone2") or ""
        name = lead.get("warehouse_name") or lead.get("name") or "the property"
        city = lead.get("city") or "your area"
        state = lead.get("state") or ""
        location = f"{city}, {state}" if state else city

        # ── Compliance check before calling (same as static path) ───
        if phone:
            blocked = await self._run_compliance_check(phone)
            if blocked:
                return blocked

        # Build the live-call pitch script
        script = self._build_live_script(name, location, decision, strategy, niche)

        # Register the stream with synthetic_brain
        voice_id = None
        ws_url = None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    f"{self._synthetic_brain_url}/api/v1/synthetic/register_stream",
                    json={
                        "script": script,
                        "voice": self.default_voice,
                        "public_base_url": self._public_base_url,
                    },
                    headers={"X-API-Key": self._synthetic_brain_key},
                )
                if r.status_code == 200:
                    reg = r.json()
                    voice_id = reg.get("voice_id")
                    ws_url = reg.get("ws_url")
                    log.info(f"[ai_closer] stream registered: voice_id={voice_id}")
                else:
                    log.warning(f"[ai_closer] register_stream failed ({r.status_code}): {r.text[:200]}")
        except Exception as e:
            log.warning(f"[ai_closer] register_stream error: {e}")

        if not ws_url or not self.voice_router:
            log.warning("[ai_closer] stream registration failed — falling back to static call")
            return await self._dispatch_static_call(lead, decision, strategy, niche)

        # Place the streaming strike via VoiceRouter
        call_result = {}
        try:
            call_result = await self.voice_router.place_streaming_strike(
                to_number=phone,
                ws_url=ws_url,
                target_address=lead.get("address", ""),
                operator_number=self.operator_number,
                brain_decision=decision,
            )
        except Exception as e:
            log.error(f"[ai_closer] streaming strike failed: {e}")
            self.stats["errors"] += 1
            call_result = {"ok": False, "error": str(e)}

        # If streaming call failed, fall back to static NCCO
        if not call_result.get("ok"):
            log.warning("[ai_closer] streaming call failed — falling back to static call")
            return await self._dispatch_static_call(lead, decision, strategy, niche)

        # ── Track pain points used ──────────────────────────────────
        pain_points_used = self._get_pain_points_used(niche)

        return {
            "action": "agi_stream_call",
            "decision": decision["decision"],
            "confidence": decision["confidence"],
            "reasoning": decision.get("reasoning", ""),
            "strategy": strategy,
            "niche": niche,
            "script": script[:200],
            "voice": self.default_voice,
            "voice_id": voice_id,
            "ws_url": ws_url,
            "call_result": call_result,
            "pain_points_used": pain_points_used,
            "lead_name": name,
            "lead_phone": phone,
        }

    # ── STATIC CALL DISPATCH (Vonage built-in TTS) ──────────────────
    async def _dispatch_static_call(
        self, lead: Dict, decision: Dict, strategy: str, niche: str
    ) -> Dict:
        """Medium-confidence GO → static NCCO call via VoiceRouter."""
        phone = lead.get("phone") or lead.get("phone2") or ""
        name = lead.get("warehouse_name") or lead.get("name") or "Unknown"

        if not phone:
            return {
                "action": "no_phone",
                "decision": decision["decision"],
                "confidence": decision["confidence"],
                "reasoning": "no phone number available",
                "strategy": strategy,
                "niche": niche,
                "lead_name": name,
            }

        # Compliance check before calling
        blocked = await self._run_compliance_check(phone)
        if blocked:
            return blocked

        call_result = {}
        if self.voice_router:
            try:
                call_result = await self.voice_router.place_strike_call(
                    to_number=phone,
                    target_address=lead.get("address", ""),
                    asset_value=float(lead.get("asset_value") or 0),
                    operator_number=self.operator_number,
                    brain_decision=decision,
                )
            except Exception as e:
                log.error(f"[ai_closer] static call failed: {e}")
                self.stats["errors"] += 1
                call_result = {"ok": False, "error": str(e)}
        else:
            call_result = {"ok": False, "error": "voice_router not wired"}

        # ── Track pain points used ──────────────────────────────────
        pain_points_used = self._get_pain_points_used(niche)

        return {
            "action": "static_call",
            "decision": decision["decision"],
            "confidence": decision["confidence"],
            "reasoning": decision.get("reasoning", ""),
            "strategy": strategy,
            "niche": niche,
            "call_result": call_result,
            "pain_points_used": pain_points_used,
            "lead_name": name,
            "lead_phone": phone,
        }

    # ── NURTURE DISPATCH (SMS/Email) ────────────────────────────────
    async def _dispatch_nurture(
        self, lead: Dict, decision: Dict, strategy: str, niche: str
    ) -> Dict:
        """Low-confidence GO or NO_GO → nurture via SMS/Email drip."""
        phone = lead.get("phone") or lead.get("phone2") or ""
        email = lead.get("email") or ""
        name = lead.get("warehouse_name") or lead.get("name") or "Unknown"

        sms_result = None
        email_result = None

        # Try SMS if phone available and sms_engine wired
        if phone and self.sms_engine:
            try:
                body = (
                    f"Empire AI: Storm activity detected near your property. "
                    f"{name}, our {niche} program may apply. "
                    f"Reply STOP to opt out."
                )
                sms_result = await self.sms_engine.send_sms(phone, body)
            except Exception as e:
                log.warning(f"[ai_closer] SMS nurture failed: {e}")

        # Try email if available and email_engine wired
        if email and self.email_engine:
            try:
                email_result = await self.email_engine.enroll(
                    email=email,
                    target_addr=lead.get("address", ""),
                    sequence_type=NURTURE_STORM if "Storm" in niche else NURTURE_GENERIC,
                    meta={"niche": niche, "strategy": strategy},
                )
            except Exception as e:
                log.warning(f"[ai_closer] email nurture failed: {e}")

        # ── Track pain points used ──────────────────────────────────
        pain_points_used = self._get_pain_points_used(niche)

        return {
            "action": "nurture",
            "decision": decision["decision"],
            "confidence": decision["confidence"],
            "reasoning": decision.get("reasoning", ""),
            "strategy": strategy,
            "niche": niche,
            "sms_result": sms_result,
            "email_result": email_result,
            "pain_points_used": pain_points_used,
            "lead_name": name,
            "lead_phone": phone,
            "lead_email": email,
        }

    # ── OUTCOME RECORDING (SI STRATEGY EVOLUTION FEEDBACK) ──────────
    async def _record_outcome(self, strategy: str, niche: str, result: Dict):
        """Feed the outcome back to the AGI Governor → StrategyEvolution + PainPoints."""
        self._ensure_governor()
        action = result.get("action", "")
        success = action in ("agi_stream_call", "static_call")
        revenue = 0.0

        # Estimate revenue from call_result if available
        call_result = result.get("call_result", {})
        if isinstance(call_result, dict) and call_result.get("ok"):
            revenue = 500.0  # base estimate per connected call

        try:
            if self._agi_governor and hasattr(self._agi_governor, "record_strategy_outcome"):
                self._agi_governor.record_strategy_outcome(strategy, niche, success, revenue)
        except Exception as e:
            log.debug(f"[ai_closer] outcome recording failed: {e}")

        # ── Record pain point outcomes ──────────────────────────────
        if self.pain_points:
            pain_points_used = result.get("pain_points_used", [])
            if pain_points_used:
                try:
                    self.pain_points.record_outcome(niche, pain_points_used, success)
                except Exception as e:
                    log.debug(f"[ai_closer] pain point outcome failed: {e}")

    # ── DECISION LOGGING ────────────────────────────────────────────
    def _log_decision(
        self, lead: Dict, decision: Dict, strategy: str, niche: str, result: Dict
    ):
        """Persist the full closer decision to ai_closer_decisions."""
        if not self.get_db:
            return
        try:
            pain_points_used = result.get("pain_points_used", [])
            db = self.get_db()
            db.table("ai_closer_decisions").insert({
                "lead_name": lead.get("warehouse_name") or lead.get("name", ""),
                "lead_phone": lead.get("phone") or lead.get("phone2", ""),
                "lead_email": lead.get("email", ""),
                "lead_address": lead.get("address", ""),
                "lead_city": lead.get("city", ""),
                "niche": niche,
                "brain_decision": decision.get("decision", ""),
                "brain_confidence": decision.get("confidence", 0),
                "brain_reasoning": (decision.get("reasoning", "") or "")[:300],
                "selected_strategy": strategy,
                "action_taken": result.get("action", ""),
                "pain_points_used": pain_points_used,
                "result_summary": result,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.debug(f"[ai_closer] decision log failed (table may not exist): {e}")

    # ── LIVE SCRIPT BUILDER ─────────────────────────────────────────
    def _build_live_script(
        self, name: str, location: str, decision: Dict, strategy: str, niche: str = ""
    ) -> str:
        """Build the live-call pitch script based on strategy genome + pain points."""
        confidence = decision.get("confidence", 0)

        # Strategy-influenced tone
        if strategy == "AGGRESSIVE_STRIKE":
            opener = "urgent storm alert"
            tone = "We have crews standing by in your area and can dispatch immediately."
        elif strategy == "RECALL_SNIPER":
            opener = "targeted property assessment"
            tone = "Our predictive models identified your facility as high-priority for storm response."
        elif strategy == "FINANCIAL_STRIKE":
            opener = "verified insurance dispatch"
            tone = "We specialize in maximizing commercial claims — our average settlement is 3x higher."
        elif strategy == "UGLY_BANNER":
            opener = "storm response program"
            tone = "Our specialists are available to assess your property at no upfront cost."
        else:
            opener = "storm damage notification"
            tone = "A specialist is available to discuss your property's needs."

        if confidence >= 0.85:
            urgency = "This is time-sensitive — storm windows close fast."
        elif confidence >= 0.7:
            urgency = "Please hold while we connect you to a specialist."
        else:
            urgency = "We'll follow up with more details shortly."

        base_script = (
            f"Hello, this is Empire AI Predictive Cloud with an {opener}. "
            f"Our weather intelligence detected severe storm activity near {location}. "
            f"We've identified {name} as a match for our {strategy.replace('_', ' ').title()} program. "
            f"{tone} {urgency}"
        )

        # ── Inject pain points if library is wired ──────────────────
        if self.pain_points and niche:
            try:
                base_script = self.pain_points.inject_pain_points(niche, base_script)
            except Exception as e:
                log.debug(f"[ai_closer] pain point injection skipped: {e}")

        return base_script

    # ── NICHE INFERENCE ─────────────────────────────────────────────
    @staticmethod
    def _infer_niche(lead: Dict, alert_summary: Optional[Dict] = None) -> str:
        """Infer the niche from lead metadata or alert context."""
        # Explicit niche in lead metadata
        try:
            meta = lead.get("meta") or {}
            explicit = meta.get("niche") if isinstance(meta, dict) else None
            if explicit:
                return str(explicit)[:80]
        except Exception:
            pass

        # From alert_summary event
        if alert_summary:
            event = (alert_summary.get("event") or "").lower()
            niche_map = [
                (("tornado",), "Tornado Damage Repair"),
                (("hurricane",), "Hurricane Damage Restoration"),
                (("hail",), "Hail Damage Repair"),
                (("flood", "flash flood"), "Flood Damage Restoration"),
                (("thunderstorm", "severe storm", "wind"), "Storm Damage Restoration"),
            ]
            for keywords, niche in niche_map:
                if any(kw in event for kw in keywords):
                    return niche
            if any(kw in event for kw in ("storm", "warning", "watch")):
                return "Storm Damage Restoration"

        # From lead type tags
        types = lead.get("type_tags", {}).get("types", []) if isinstance(lead.get("type_tags"), dict) else []
        if "roofing" in types or "contractor" in types:
            return "Roofing Restoration"
        if "warehouse" in types or "industrial" in types:
            return "Storm Damage Restoration"
        if "legal" in types or "medical" in types:
            return "Legal Intake"

        return "Roofing Restoration"

    # ── COMPLIANCE CHECK HELPER ────────────────────────────────────
    async def _run_compliance_check(self, phone: str) -> Optional[Dict]:
        """Run TCPA/DNC/calling-hours compliance check. Returns block dict if blocked."""
        try:
            from empire_outbound_dialer import compliance_check, ComplianceBlock
            compliance_check(phone)
        except ImportError:
            pass  # compliance module not available
        except ComplianceBlock as e:
            log.info(f"[ai_closer] compliance blocked call to {phone}: {e}")
            return {
                "action": "compliance_blocked",
                "block_reason": str(e),
                "lead_phone": phone,
            }
        except Exception as e:
            # Non-ComplianceBlock error (e.g. Supabase timeout) — log but don't block
            log.warning(f"[ai_closer] compliance check errored (allowing): {e}")
        return None

    # ── SNAPSHOT FOR DASHBOARD ──────────────────────────────────────
    def snapshot(self) -> Dict:
        """Return closer stats for the SPA / mission control."""
        return {
            **self.stats,
            "stream_confidence": self.stream_confidence,
            "static_confidence": self.static_confidence,
            "voice_router_wired": self.voice_router is not None,
            "brain_decider_wired": self.brain_decider is not None,
            "sms_engine_wired": self.sms_engine is not None,
            "email_engine_wired": self.email_engine is not None,
            "synthetic_brain_url": self._synthetic_brain_url,
            "operator_number_configured": bool(self.operator_number),
        }


# ── CONVENIENCE: DIRECT SCORE + ROUTE (NO CALL) ─────────────────────
async def ai_closer_score_only(
    closer: AICloser,
    lead: Dict,
    alert_summary: Optional[Dict] = None,
    niche: Optional[str] = None,
) -> Dict:
    """
    Score a lead through brain + strategy selection without placing a call.
    Useful for pre-qualification (e.g. in the SPA pipeline view).
    """
    name = lead.get("warehouse_name") or lead.get("name") or "Unknown"
    if not niche:
        niche = closer._infer_niche(lead, alert_summary)

    # Brain score
    if not closer.brain_decider:
        decision = {"decision": "GO", "confidence": 0.5, "reasoning": "brain unavailable"}
    else:
        alert_ctx = alert_summary or {
            "event": "Inbound Lead",
            "severity": "Moderate",
            "urgency": "Normal",
            "area": f"{lead.get('city', '')}, {lead.get('state', '')}".strip(", "),
        }
        decision = await closer.brain_decider.decide(
            target={
                "warehouse_name": name,
                "address": lead.get("address", ""),
                "city": lead.get("city", ""),
                "phone": lead.get("phone") or lead.get("phone2", ""),
                "email": lead.get("email", ""),
                "website": lead.get("website", ""),
                "raw_tags": lead.get("type_tags") or {"types": ["commercial"]},
            },
            alert_summary=alert_ctx,
        )
        decision["decision"] = (decision.get("decision") or "NO_GO").upper()
        try:
            decision["confidence"] = max(0.0, min(1.0, float(decision.get("confidence", 0))))
        except (TypeError, ValueError):
            decision["confidence"] = 0.5

    # Strategy
    strategy = await closer._select_strategy(niche, decision)

    confidence = decision["confidence"]
    if confidence >= closer.stream_confidence:
        route = "agi_stream_call"
    elif confidence >= closer.static_confidence:
        route = "static_call"
    elif decision["decision"] == "GO":
        route = "nurture"
    else:
        route = "no_go"

    return {
        "lead_name": name,
        "niche": niche,
        "strategy": strategy,
        "brain_decision": decision["decision"],
        "brain_confidence": confidence,
        "brain_reasoning": decision.get("reasoning", ""),
        "route": route,
    }
