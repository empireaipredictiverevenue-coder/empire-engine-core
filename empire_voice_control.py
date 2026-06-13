"""
EMPIRE V49 · VOICE CONTROL (Phase 7)
======================================
Orchestrator that connects empire_brain_decide.py → voice scripts → call dispatch
→ sentiment tracking → brain_memory update.

Wraps BrainDecider, VoiceRouter, and BrainMemory into a single controller the
SPA and hub.py can use without wiring three separate modules.

ARCHITECTURE
────────────
  VoiceController
      │
      ├── BrainDecider    (GO/NO-GO + confidence)
      ├── VoiceRouter     (Vonage outbound / inbound)
      ├── BrainMemory     (embedding storage + few-shot retrieval)
      │
      ├── process_inbound_call()    — full inbound lifecycle
      ├── dispatch_outbound_strike() — full outbound lifecycle
      ├── record_call_sentiment()   — extract sentiment → brain_memory
      └── status()                  — SPA-friendly stats snapshot
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from empire_brain_decide import BrainDecider
from empire_brain_memory import BrainMemory, render_few_shot
from empire_voice import VoiceRouter, ncco_dynamic_inbound, ncco_dynamic_outbound

log = logging.getLogger("empire.voice.control")


# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENT EXTRACTOR — lightweight call-sentiment heuristics
# ─────────────────────────────────────────────────────────────────────────────
_CALL_SENTIMENT_KEYWORDS = {
    "positive": [
        "yes", "interested", "help", "thank", "schedule", "send",
        "okay", "sure", "please", "go ahead", "when", "how soon",
    ],
    "negative": [
        "no", "stop", "don't call", "remove", "unsubscribe", "opt out",
        "scam", "fraud", "lawsuit", "complaint", "wrong number",
        "never", "block", "harassing", "cease",
    ],
    "neutral": [
        "maybe", "not sure", "call back", "later", "busy", "can't talk",
    ],
}


def _classify_sentiment(transcript: str) -> dict:
    """Lightweight heuristic sentiment classification from call transcript."""
    if not transcript:
        return {"label": "unknown", "score": 0.0, "confidence": 0.0}
    lower = transcript.lower()
    pos_count = sum(1 for kw in _CALL_SENTIMENT_KEYWORDS["positive"] if kw in lower)
    neg_count = sum(1 for kw in _CALL_SENTIMENT_KEYWORDS["negative"] if kw in lower)
    neu_count = sum(1 for kw in _CALL_SENTIMENT_KEYWORDS["neutral"] if kw in lower)
    total = pos_count + neg_count + neu_count
    if total == 0:
        return {"label": "neutral", "score": 0.5, "confidence": 0.3}
    pos_score = pos_count / total
    neg_score = neg_count / total
    if pos_score > neg_score and pos_score > 0.35:
        return {"label": "positive", "score": round(pos_score, 2), "confidence": round(pos_score, 2)}
    elif neg_score > pos_score and neg_score > 0.35:
        return {"label": "negative", "score": round(neg_score, 2), "confidence": round(neg_score, 2)}
    return {"label": "neutral", "score": 0.5, "confidence": 0.4}


# ─────────────────────────────────────────────────────────────────────────────
# THE VOICE CONTROLLER
# ─────────────────────────────────────────────────────────────────────────────
class VoiceController:
    """
    High-level voice orchestrator. Initialized once in hub.py and used by
    the SPA, the bridge, and the webhook pipelines.
    """

    def __init__(
        self,
        *,
        voice_router: VoiceRouter,
        brain_decider: BrainDecider,
        brain_memory: BrainMemory,
        get_db: Callable,
        operator_number: str = "",
        broadcaster=None,
        ntfy_topic: str = "",
        ntfy_token: str = "",
    ):
        self.router = voice_router
        self.brain = brain_decider
        self.memory = brain_memory
        self.get_db = get_db
        self.operator_number = operator_number or os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
        self.broadcaster = broadcaster
        self.ntfy_topic = ntfy_topic
        self.ntfy_token = ntfy_token
        self.stats = {
            "inbound_processed": 0,
            "outbound_dispatched": 0,
            "sentiments_recorded": 0,
            "memory_retrievals": 0,
            "errors": 0,
            "last_inbound": None,
            "last_outbound": None,
        }
        # In-flight call registry (call_uuid → metadata for sentiment tracking)
        self._active_calls: dict[str, dict] = {}

    # ── INBOUND CALL LIFECYCLE ─────────────────────────────────────────
    async def process_inbound_call(
        self,
        *,
        from_number: str,
        to_number: str = "",
        call_uuid: str = "",
        conversation_uuid: str = "",
    ) -> dict:
        """
        Full inbound call lifecycle:
          1. Enrich caller from radar_targets
          2. Consult brain for GO/NO-GO decision
          3. Retrieve similar past decisions for few-shot learning
          4. Record decision in brain_memory
          5. Build dynamic NCCO based on brain decision
          6. Register in-flight call for sentiment tracking

        Returns: {ncco, brain_decision, target, enriched}
        """
        self.stats["inbound_processed"] += 1
        self.stats["last_inbound"] = {"from": from_number, "at": datetime.now(timezone.utc).isoformat()}

        target_address = ""
        severity = ""
        city = ""
        state = ""
        lead_id = None
        asset_val = 0.0
        brain_decision = None

        try:
            db = self.get_db()
            clean_phone = from_number.lstrip("+1").lstrip("+").strip()
            res = db.table("radar_targets").select(
                "id, warehouse_name, address, city, state, damage_severity, asset_value"
            ).or_(f"phone.ilike.%{clean_phone[-10:]},phone2.ilike.%{clean_phone[-10:]}")\
             .limit(1).execute()
            if res.data:
                row = res.data[0]
                target_address = row.get("address", "") or ""
                city = row.get("city", "") or ""
                state = row.get("state", "") or ""
                severity = row.get("damage_severity", "") or ""
                lead_id = row.get("id")
                asset_val = float(row.get("asset_value") or 0)

                target = {
                    "warehouse_name": row.get("warehouse_name") or "Caller",
                    "address": target_address or "unknown",
                    "city": city,
                    "phone": from_number,
                    "email": "",
                    "website": "",
                    "raw_tags": {"types": ["commercial"]},
                }
                alert_summary = {
                    "event": "Inbound Call",
                    "severity": severity or "Moderate",
                    "urgency": "",
                    "area": f"{city}, {state}" if city else "",
                }

                # Enrich with storm_forecast
                if city:
                    try:
                        sres = db.table("storm_forecasts").select(
                            "event, severity, urgency, area"
                        ).ilike("area", f"%{city}%").order("created_at", desc=True).limit(1).execute()
                        if sres.data:
                            s = sres.data[0]
                            alert_summary["event"] = s.get("event") or alert_summary["event"]
                            alert_summary["severity"] = s.get("severity") or alert_summary["severity"]
                    except Exception:
                        pass

                # Few-shot memory retrieval
                memory_context = ""
                if self.memory.enabled:
                    try:
                        similar = await self.memory.retrieve_similar(
                            address=target_address or "unknown",
                            city=city or "unknown",
                            severity=severity or "Moderate",
                            asset_value=asset_val,
                            urgency_signal=alert_summary.get("event", ""),
                            k=5,
                            only_with_outcomes=True,
                        )
                        if similar:
                            memory_context = render_few_shot(similar)
                            self.stats["memory_retrievals"] += 1
                    except Exception as e:
                        log.debug(f"[voice.control] memory retrieval: {e}")

                brain_decision = await self.brain.decide(target, alert_summary, memory_context=memory_context)

                # Record in brain_memory
                if lead_id and self.memory.enabled:
                    try:
                        urgency = round(float(brain_decision.get("confidence", 0)) * 10)
                        await self.memory.record_decision(
                            lead_id=lead_id,
                            decision=brain_decision.get("decision", "NO_GO"),
                            urgency=min(urgency, 10),
                            reasoning=brain_decision.get("reasoning", "")[:500],
                            address=target_address or "unknown",
                            city=city or "unknown",
                            severity=severity or "Moderate",
                            asset_value=asset_val,
                        )
                    except Exception as e:
                        log.debug(f"[voice.control] memory record: {e}")

        except Exception as e:
            log.warning(f"[voice.control] inbound enrichment failed: {e}")
            self.stats["errors"] += 1

        # Build dynamic NCCO
        ncco = ncco_dynamic_inbound(
            target_address=target_address,
            severity=severity,
            brain_decision=brain_decision,
            forward_to=self.operator_number,
        )

        # Register for sentiment tracking
        if call_uuid:
            self._active_calls[call_uuid] = {
                "direction": "inbound",
                "from": from_number,
                "to": to_number,
                "lead_id": lead_id,
                "target_address": target_address,
                "city": city,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "brain_decision": brain_decision,
            }

        return {
            "ncco": ncco,
            "brain_decision": brain_decision,
            "target": {"address": target_address, "city": city, "lead_id": lead_id},
            "enriched": bool(target_address),
        }

    # ── OUTBOUND STRIKE LIFECYCLE ───────────────────────────────────────
    async def dispatch_outbound_strike(
        self,
        *,
        to_number: str,
        target_address: str = "",
        asset_value: float = 0.0,
        severity: str = "",
        operator_number: str = "",
        lead_id: Optional[str] = None,
        si_strategy: Optional[str] = None,
        si_niche: Optional[str] = None,
    ) -> dict:
        """
        Full outbound strike lifecycle:
          1. Enrich target from radar_targets
          2. Consult brain for GO/NO-GO decision
          3. Few-shot memory retrieval
          4. Record decision in brain_memory
          5. Place call via VoiceRouter with dynamic NCCO
          6. Broadcast to live dashboards
          7. Register for sentiment tracking

        Returns: {ok, call_result, brain_decision, call_uuid}
        """
        self.stats["outbound_dispatched"] += 1
        self.stats["last_outbound"] = {"to": to_number, "at": datetime.now(timezone.utc).isoformat()}

        op = operator_number or self.operator_number
        brain_decision = None
        call_uuid = None
        resolved_address = target_address
        resolved_asset = asset_value
        resolved_severity = severity
        resolved_city = ""
        resolved_state = ""
        resolved_lead_id = lead_id

        try:
            db = self.get_db()
            clean = to_number.lstrip("+1").lstrip("+").strip()
            res = db.table("radar_targets").select(
                "id, warehouse_name, address, city, state, damage_severity, asset_value"
            ).or_(f"phone.ilike.%{clean[-10:]},phone2.ilike.%{clean[-10:]}")\
             .limit(1).execute()
            if res.data:
                row = res.data[0]
                resolved_lead_id = row.get("id") or lead_id
                resolved_address = row.get("address", "") or target_address
                resolved_city = row.get("city", "") or ""
                resolved_state = row.get("state", "") or ""
                resolved_severity = row.get("damage_severity", "") or severity
                resolved_asset = float(row.get("asset_value") or 0) or asset_value

                target = {
                    "warehouse_name": row.get("warehouse_name") or "Prospect",
                    "address": resolved_address or "unknown",
                    "city": resolved_city,
                    "phone": to_number,
                    "email": "",
                    "website": "",
                    "raw_tags": {"types": ["commercial"]},
                }
                alert_summary = {
                    "event": "Outbound Strike",
                    "severity": resolved_severity or "Moderate",
                    "urgency": "",
                    "area": f"{resolved_city}, {resolved_state}" if resolved_city else "",
                }

                if resolved_city:
                    try:
                        sres = db.table("storm_forecasts").select(
                            "event, severity, urgency, area"
                        ).ilike("area", f"%{resolved_city}%").order("created_at", desc=True).limit(1).execute()
                        if sres.data:
                            s = sres.data[0]
                            alert_summary["event"] = s.get("event") or alert_summary["event"]
                            alert_summary["severity"] = s.get("severity") or alert_summary["severity"]
                    except Exception:
                        pass

                memory_context = ""
                if self.memory.enabled:
                    try:
                        similar = await self.memory.retrieve_similar(
                            address=resolved_address or "unknown",
                            city=resolved_city or "unknown",
                            severity=resolved_severity or "Moderate",
                            asset_value=resolved_asset,
                            urgency_signal=alert_summary.get("event", ""),
                            k=5,
                            only_with_outcomes=True,
                        )
                        if similar:
                            memory_context = render_few_shot(similar)
                            self.stats["memory_retrievals"] += 1
                    except Exception as e:
                        log.debug(f"[voice.control] memory retrieval: {e}")

                brain_decision = await self.brain.decide(target, alert_summary, memory_context=memory_context)

                # Fold SI strategy/niche into brain decision for NCCO builder
                if isinstance(brain_decision, dict):
                    if si_strategy:
                        brain_decision["si_strategy"] = si_strategy
                    if si_niche:
                        brain_decision["si_niche"] = si_niche

                # Record in brain_memory
                if resolved_lead_id and self.memory.enabled:
                    try:
                        urg = round(float(brain_decision.get("confidence", 0)) * 10)
                        await self.memory.record_decision(
                            lead_id=resolved_lead_id,
                            decision=brain_decision.get("decision", "NO_GO"),
                            urgency=min(urg, 10),
                            reasoning=brain_decision.get("reasoning", "")[:500],
                            address=resolved_address or "unknown",
                            city=resolved_city or "unknown",
                            severity=resolved_severity or "Moderate",
                            asset_value=resolved_asset,
                        )
                    except Exception as e:
                        log.debug(f"[voice.control] memory record: {e}")
        except Exception as e:
            log.warning(f"[voice.control] outbound enrichment failed: {e}")
            self.stats["errors"] += 1

        # Place the call via VoiceRouter
        call_result = await self.router.place_strike_call(
            to_number=to_number,
            target_address=resolved_address,
            asset_value=resolved_asset,
            operator_number=op,
            broadcaster=self.broadcaster,
            brain_decision=brain_decision,
        )
        call_uuid = call_result.get("uuid")

        # Register for sentiment tracking
        if call_uuid:
            self._active_calls[call_uuid] = {
                "direction": "outbound",
                "from": self.router.vonage.from_number,
                "to": to_number,
                "lead_id": resolved_lead_id,
                "target_address": resolved_address,
                "city": resolved_city,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "brain_decision": brain_decision,
            }

        return {
            "ok": call_result.get("ok", False),
            "call_result": call_result,
            "brain_decision": brain_decision,
            "call_uuid": call_uuid,
            "target": {"address": resolved_address, "city": resolved_city, "lead_id": resolved_lead_id},
        }

    # ── CALL SENTIMENT TRACKING ─────────────────────────────────────────
    async def record_call_sentiment(
        self,
        *,
        call_uuid: str,
        transcript: str = "",
        duration: int = 0,
        status: str = "completed",
    ) -> dict:
        """
        Extract sentiment from a completed call and feed it back to
        BrainMemory for future few-shot learning. Also cleans up the
        in-flight call registry.

        Called by the Vonage event webhook when a call completes.
        """
        call = self._active_calls.pop(call_uuid, None)
        if not call:
            log.debug(f"[voice.control] no active call for {call_uuid}")
            return {"ok": False, "error": "unknown call"}

        sentiment = _classify_sentiment(transcript)

        # Update brain_memory with outcome + sentiment if we have a lead_id
        lead_id = call.get("lead_id")
        if lead_id and self.memory.enabled:
            try:
                # Map sentiment to outcome
                outcome_map = {
                    "positive": "settled",
                    "neutral": "pending",
                    "negative": "denied",
                }
                outcome = outcome_map.get(sentiment["label"], "pending")
                await self.memory.attach_outcome(
                    lead_id=lead_id,
                    outcome=outcome,
                    actual_fee=0.0,  # Not known yet; updated when claim settles
                )
                self.stats["sentiments_recorded"] += 1
            except Exception as e:
                log.debug(f"[voice.control] sentiment record: {e}")

        # Broadcast sentiment to live dashboards
        if self.broadcaster:
            try:
                await self.broadcaster.broadcast({
                    "type": "call_sentiment",
                    "call_uuid": call_uuid,
                    "direction": call.get("direction"),
                    "sentiment": sentiment,
                    "duration": duration,
                    "status": status,
                    "target": call.get("target_address"),
                })
            except Exception:
                pass

        log.info(
            f"[voice.control] sentiment: {call_uuid[:8]}... → {sentiment['label']} "
            f"(score={sentiment['score']}) · lead_id={lead_id}"
        )

        return {
            "ok": True,
            "sentiment": sentiment,
            "call": call,
        }

    # ── STATUS ──────────────────────────────────────────────────────────
    def status(self) -> dict:
        """SPA-friendly stats snapshot."""
        now_ts = datetime.now(timezone.utc).isoformat()
        return {
            "stats": {**self.stats},
            "active_calls": len(self._active_calls),
            "vonage_enabled": self.router.vonage.enabled,
            "brain_online": True,
            "memory_enabled": self.memory.enabled,
            "timestamp": now_ts,
        }

    # ── PROCESS VONAGE EVENT (bridge-friendly) ─────────────────────────
    async def process_event(self, event: dict) -> dict:
        """
        Process a Vonage call event. Handles call completion + AMD results
        for sentiment tracking. Returns a normalized event dict.
        """
        status = event.get("status", "unknown")
        call_uuid = event.get("uuid", "")
        duration = int(event.get("duration", 0) or 0)

        if status == "completed" and call_uuid:
            asyncio.create_task(self.record_call_sentiment(
                call_uuid=call_uuid,
                duration=duration,
                status=status,
            ))

        return {
            "ok": True,
            "status": status,
            "call_uuid": call_uuid,
            "duration": duration,
        }

    # ── NATURAL LANGUAGE COMMAND (bridge interface) ─────────────────────
    async def process_command(self, command: str, session_id: str = "") -> dict:
        """
        Process a natural-language command (from the Bridge view).
        Returns structured response: {text, action, data?}

        Examples:
          "show me hot leads in Dallas"
          "call +12145551234"
          "what's my revenue today?"
          "approve payout abc123"
        """
        lower = command.lower().strip()

        # Dispatch command
        if lower.startswith("call ") or lower.startswith("dial "):
            # Extract phone number
            import re
            nums = re.findall(r"\+?1?\d{10,15}", command)
            if nums:
                result = await self.dispatch_outbound_strike(to_number=nums[0])
                if result.get("ok"):
                    decision = result.get("brain_decision", {})
                    return {
                        "text": f"Call placed. Brain says {decision.get('decision', 'GO')} "
                                f"with {decision.get('confidence', 0)*100:.0f}% confidence.",
                        "action": "call_placed",
                        "data": result,
                    }
                return {"text": "Brain declined — NO_GO. Call not placed.", "action": "no_go", "data": result}
            return {"text": "I couldn't find a phone number in that command.", "action": "error"}

        if "revenue" in lower or "earnings" in lower or "pulse" in lower:
            return {"text": "Revenue pulse is strong. Check the Pulse tab for full breakdown.", "action": "navigate", "data": {"tab": "pulse"}}

        if "lead" in lower or "hot" in lower or "dallas" in lower or "target" in lower:
            try:
                db = self.get_db()
                city_hint = ""
                for c in ["dallas", "houston", "austin", "fort worth", "san antonio", "oklahoma city"]:
                    if c in lower:
                        city_hint = c.title()
                        break
                q = db.table("radar_targets").select("id, warehouse_name, address, city, damage_severity, asset_value, urgency_score") \
                    .eq("status", "active").not_.is_("phone", "null").order("urgency_score", desc=True).limit(5)
                if city_hint:
                    q = q.ilike("city", f"%{city_hint}%")
                leads = q.execute().data or []
                if leads:
                    lines = [f"**{l.get('warehouse_name') or 'Unknown'}** at {l.get('address', '')} — "
                             f"{l.get('city', '')} · severity={l.get('damage_severity', '?')} · "
                             f"${l.get('asset_value', 0):,.0f}" for l in leads[:3]]
                    return {"text": "Top leads:\n" + "\n".join(lines), "action": "leads_found", "data": {"leads": leads[:3]}}
                return {"text": "No leads found matching that criteria.", "action": "no_leads"}
            except Exception as e:
                return {"text": f"Error looking up leads: {e}", "action": "error"}

        if "approve" in lower:
            return {"text": "Approval requires a specific payout ID. Try 'approve payout abc123'.", "action": "info"}

        if "status" in lower or "health" in lower:
            s = self.status()
            return {
                "text": f"System online. {s['stats']['outbound_dispatched']} outbound calls, "
                        f"{s['stats']['inbound_processed']} inbound. "
                        f"{s['active_calls']} active calls. Memory={'enabled' if s['memory_enabled'] else 'disabled'}.",
                "action": "status",
                "data": s,
            }

        if "help" in lower:
            return {
                "text": "Try: 'call +12145551234', 'show hot leads in Dallas', "
                        "'what's my revenue?', 'system status', or 'approve payout <id>'.",
                "action": "help",
            }

        return {
            "text": f"I heard: \"{command[:100]}\". I'm not sure how to handle that yet. "
                    "Try 'help' for available commands.",
            "action": "unknown",
        }
