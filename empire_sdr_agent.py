"""
EMPIRE V49 · SDR AGENT (SALES DEVELOPMENT REPRESENTATIVE)
==========================================================
Autonomous outbound prospecting agent. Scores inbound leads for ICP fit,
runs multi-touch outbound sequences (email → SMS → voice → follow-up),
and books qualified meetings for the closing agent.

Fleet parent: sales_director
Routes:
  GET    /api/sdr/overview        — SDR dashboard snapshot
  GET    /api/sdr/leads           — Scored ICP leads with outbound readiness
  POST   /api/sdr/sequence        — Trigger outbound sequence on a lead
  GET    /api/sdr/sequences       — Active sequence statuses
  POST   /api/sdr/book            — Book a meeting for a qualified lead
  GET    /api/sdr/bookings        — Booked meetings log
  GET    /api/sdr/snapshot        — Condensed fleet snapshot
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.sdr_agent")

# ── ICP scoring dimensions ─────────────────────────────────────────
ICP_DIMENSIONS = {
    "niche_fit":       {"weight": 0.25, "label": "Niche Fit"},
    "engagement":      {"weight": 0.20, "label": "Engagement Signal"},
    "data_quality":    {"weight": 0.15, "label": "Data Completeness"},
    "geo_fit":         {"weight": 0.15, "label": "Geographic Fit"},
    "business_scale":  {"weight": 0.15, "label": "Business Scale"},
    "timing":          {"weight": 0.10, "label": "Recency / Timing"},
}

HIGH_VALUE_NICHES = {
    "roofing": 90, "hvac": 85, "restoration": 88,
    "commercial roofing": 95, "industrial hvac": 92,
    "mass tort": 80, "debt relief": 78,
    "insurance": 82, "logistics": 75, "freight": 75,
}

SDR_OUTREACH_STAGES = [
    "queued",
    "emailing",        # Email sequence in progress
    "sms_followup",    # SMS follow-up after email
    "voice_drop",      # Voice call attempt
    "meeting_booked",  # Meeting confirmed
    "handed_off",      # Passed to closing agent
    "disqualified",    # Not a fit / opted out
    "completed",
]

# ── OUTBOUND SEQUENCE TEMPLATES ────────────────────────────────────
# Staged: email → SMS → voice → follow-up email → close/SDR handoff
SEQUENCE_TEMPLATES = {
    "initial_email": {
        "subject": "Maximising {niche} opportunities in {city}",
        "body": (
            "Hi {name},\n\n"
            "I noticed {company} is active in the {city} {niche} space. "
            "We're helping businesses in your area convert storm-damage leads "
            "into qualified opportunities — at an average of {avg_value} per lead.\n\n"
            "Would you be open to a 10-minute call this week to see if this fits?\n\n"
            "Best,\n{rep_name}, Empire AI"
        ),
    },
    "sms_followup": {
        "body": "Hi {name} — following up on my email. Quick question: are you currently getting enough {niche_short} leads in {city}? Happy to share what we're seeing in the market. Reply YES or call me.",
    },
    "voice_script": {
        "intro": "Hi {name}, this is {rep_name} from Empire AI. I sent you an email about how we're helping {niche} businesses in {city} convert more leads. Give me a call back at your convenience — be happy to share some market data.",
    },
    "followup_email": {
        "subject": "Quick question re: {city} {niche}",
        "body": (
            "Hi {name},\n\n"
            "Just following up on my previous message. We've helped {similar_count} similar "
            "businesses in {city} generate an average of {avg_opps} qualified opportunities "
            "this month alone.\n\n"
            "No pressure — but if you're curious, I have 15 minutes tomorrow at 2pm or "
            "Thursday at 10am. Which works?\n\n"
            "Best,\n{rep_name}, Empire AI"
        ),
    },
}


class SDRAgent:
    """Sales Development Representative — ICP scoring, outbound sequences, meeting booking.

    Three core capabilities:
      1. ICP Scoring — multi-dimensional fit analysis on inbound leads
      2. Outbound Sequences — staged multi-touch outreach (email → SMS → voice → follow-up)
      3. Meeting Booking — captures intent, schedules handoff to closing agent
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._sequences: list[dict] = []      # active outreach sequences
        self._bookings: list[dict] = []        # booked meetings
        self._scored_leads: list[dict] = []    # cached scored leads

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _days_ago(self, d: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()

    # ── DATA SOURCES ─────────────────────────────────────────────────

    def _fetch_inbound_leads(self, limit: int = 200) -> list[dict]:
        """Fetch leads from enriched_leads for ICP scoring."""
        try:
            r = self._db().table("enriched_leads") \
                .select("id, name, phone, email, city, state, niche, "
                        "warehouse_name, meta, created_at") \
                .limit(limit) \
                .order("created_at", desc=True) \
                .execute()
            return r.data or []
        except Exception as e:
            log.debug(f"[sdr] fetch leads: {e}")
            return []

    def _fetch_storm_targets(self, limit: int = 100) -> list[dict]:
        """Fetch radar_targets for storm-driven opportunities."""
        try:
            r = self._db().table("radar_targets") \
                .select("id, warehouse_name, address, city, state, "
                        "phone, email, niche, risk_level, risk_rank, created_at") \
                .limit(limit) \
                .order("created_at", desc=True) \
                .execute()
            return r.data or []
        except Exception as e:
            log.debug(f"[sdr] fetch targets: {e}")
            return []

    def _fetch_lead_counts_by_niche(self) -> dict:
        """Get lead volume stats per niche."""
        out = {}
        try:
            r = self._db().table("enriched_leads") \
                .select("niche", count="exact") \
                .execute()
            if r.data:
                for row in r.data:
                    n = (row.get("niche") or "unknown").lower()
                    out[n] = out.get(n, 0) + 1
        except Exception:
            pass
        return out

    # ── 1. ICP SCORING ───────────────────────────────────────────────

    def _score_icp_fit(self, lead: dict) -> dict:
        """Multi-dimensional ICP scoring.

        Returns a score 0-100 with dimension breakdown and outbound readiness.
        """
        niche = (lead.get("niche") or "").lower()
        city = (lead.get("city") or "").lower()
        meta = lead.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        # ── Niche Fit (25%) ─────────────────────────────────────────
        niche_score = 20  # baseline
        for kw, score in HIGH_VALUE_NICHES.items():
            if kw in niche:
                niche_score = max(niche_score, score)
                break
        niche_dim = niche_score * ICP_DIMENSIONS["niche_fit"]["weight"]

        # ── Engagement Signal (20%) ────────────────────────────────
        # Factors: has website, has company info in meta, has decision-maker name
        has_meta = isinstance(meta, dict) and len(meta) > 2
        has_email = bool(lead.get("email"))
        has_phone = bool(lead.get("phone"))
        has_warehouse = bool(lead.get("warehouse_name"))
        signal_count = sum([has_meta, has_email, has_phone, has_warehouse])
        engagement_score = min(signal_count * 22, 100)  # each signal = 22pts
        engagement_dim = engagement_score * ICP_DIMENSIONS["engagement"]["weight"]

        # ── Data Quality (15%) ──────────────────────────────────────
        fields = ["name", "phone", "email", "city", "state", "niche"]
        filled = sum(1 for f in fields if lead.get(f))
        quality_score = (filled / len(fields)) * 100
        quality_dim = quality_score * ICP_DIMENSIONS["data_quality"]["weight"]

        # ── Geographic Fit (15%) ────────────────────────────────────
        TOP_METROS = ["dallas", "houston", "austin", "san antonio",
                      "fort worth", "arlington", "plano", "irving",
                      "garland", "frisco", "mckinney", "denton"]
        geo_score = 85 if any(m in city for m in TOP_METROS) else \
                    70 if city else 30
        geo_dim = geo_score * ICP_DIMENSIONS["geo_fit"]["weight"]

        # ── Business Scale (15%) ────────────────────────────────────
        # Rough proxy: warehouse/commercial indicates larger operation
        scale_score = 90 if has_warehouse else \
                      70 if has_meta else 40
        scale_dim = scale_score * ICP_DIMENSIONS["business_scale"]["weight"]

        # ── Timing / Recency (10%) ──────────────────────────────────
        created = lead.get("created_at", "")
        timing_score = 70  # baseline
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - created_dt).days
                timing_score = max(10, 90 - age_days * 3)  # decays 3pts/day
            except Exception:
                pass
        timing_dim = timing_score * ICP_DIMENSIONS["timing"]["weight"]

        total = round(niche_dim + engagement_dim + quality_dim +
                      geo_dim + scale_dim + timing_dim, 1)
        total = min(total, 100)

        # ── Outbound readiness ──────────────────────────────────────
        outbound_ready = total >= 55 and has_phone

        return {
            "score": total,
            "score_breakdown": {
                "niche_fit":       round(niche_dim, 1),
                "engagement":      round(engagement_dim, 1),
                "data_quality":    round(quality_dim, 1),
                "geo_fit":         round(geo_dim, 1),
                "business_scale":  round(scale_dim, 1),
                "timing":          round(timing_dim, 1),
            },
            "raw_scores": {
                "niche_raw": niche_score,
                "engagement_raw": engagement_score,
                "quality_raw": quality_score,
                "geo_raw": geo_score,
                "scale_raw": scale_score,
                "timing_raw": timing_score,
            },
            "outbound_ready": outbound_ready,
            "tier": ("hot" if total >= 75 else
                     "warm" if total >= 55 else
                     "cool" if total >= 35 else "cold"),
            "recommended_action": (
                "sequence" if outbound_ready and total >= 75 else
                "enrich" if total >= 55 and not has_phone else
                "nurture" if total >= 35 else
                "archive"
            ),
        }

    # ── 2. OUTBOUND SEQUENCES ───────────────────────────────────────

    def _build_sequence(self, lead: dict, icp: dict) -> dict:
        """Build a multi-touch outbound sequence for a qualified lead."""
        niche = lead.get("niche", "").lower()
        city = lead.get("city", "your area")
        name = lead.get("name", lead.get("warehouse_name", "there"))
        company = lead.get("warehouse_name") or name

        # Fill templates
        templates = SEQUENCE_TEMPLATES
        email_body = templates["initial_email"]["body"].format(
            name=name, company=company, city=city,
            niche=niche.title(), niche_short=niche.split()[0] if niche else niche,
            avg_value=f"${icp['score'] * 5:.0f}",
            rep_name="Sarah, Empire AI SDR",
        )
        sms_body = templates["sms_followup"]["body"].format(
            name=name, city=city,
            niche_short=niche.split()[0] if niche else niche,
        )
        voice_intro = templates["voice_script"]["intro"].format(
            name=name, city=city, niche=niche.title(),
            rep_name="Sarah from Empire AI",
        )
        followup_body = templates["followup_email"]["body"].format(
            name=name, city=city, niche=niche.title(),
            similar_count=min(int(icp["score"] / 5), 50),
            avg_opps=min(int(icp["score"] / 3), 30),
            rep_name="Sarah, Empire AI SDR",
        )

        return {
            "sequence_id": f"SDR-{uuid.uuid4().hex[:8].upper()}",
            "lead_id": lead.get("id", ""),
            "target_name": name,
            "phone": lead.get("phone", ""),
            "email": lead.get("email", ""),
            "niche": niche,
            "icp_score": icp["score"],
            "tier": icp["tier"],
            "created_at": self._now(),
            "steps": [
                {
                    "step": 1,
                    "type": "email",
                    "channel": "email",
                    "subject": templates["initial_email"]["subject"].format(
                        niche=niche.title(), city=city,
                    ),
                    "body": email_body,
                    "status": "pending",
                    "delay_hours": 0,
                },
                {
                    "step": 2,
                    "type": "sms_followup",
                    "channel": "sms",
                    "body": sms_body,
                    "status": "pending",
                    "delay_hours": 24,
                },
                {
                    "step": 3,
                    "type": "voice_drop",
                    "channel": "voice",
                    "script": voice_intro,
                    "status": "pending",
                    "delay_hours": 48,
                },
                {
                    "step": 4,
                    "type": "followup_email",
                    "channel": "email",
                    "subject": templates["followup_email"]["subject"].format(
                        niche=niche.title(), city=city,
                    ),
                    "body": followup_body,
                    "status": "pending",
                    "delay_hours": 72,
                },
                {
                    "step": 5,
                    "type": "close_or_handoff",
                    "channel": "internal",
                    "note": "Sequence complete — book meeting or disqualify",
                    "status": "pending",
                    "delay_hours": 120,  # 5 days total
                },
            ],
            "current_step": 0,
            "overall_status": "queued",
        }

    async def trigger_outbound_sequence(self, lead_id: str = "",
                                         niche: str = "",
                                         target_name: str = "",
                                         force: bool = False) -> dict:
        """Trigger an outbound SDR sequence for a lead.

        Scores the lead first, then builds and queues the sequence.
        Records the action for dashboard tracking.
        """
        # Fetch lead from DB or use what we have
        lead_data = {"id": lead_id, "niche": niche, "name": target_name}
        try:
            r = self._db().table("enriched_leads") \
                .select("*") \
                .eq("id", lead_id) \
                .limit(1) \
                .execute()
            if r.data:
                lead_data = r.data[0]
        except Exception:
            pass

        # Score ICP fit
        icp = self._score_icp_fit(lead_data)

        # Only allow sequence if outbound_ready or forced
        if not icp["outbound_ready"] and not force:
            return {
                "ok": False,
                "error": f"Lead scored {icp['score']}/100 — below outbound threshold (55). "
                         f"Tier: {icp['tier']}. Recommended: {icp['recommended_action']}",
                "icp_score": icp,
                "sequence_created": False,
            }

        # Build and queue the sequence
        sequence = self._build_sequence(lead_data, icp)
        sequence["triggered_at"] = self._now()
        sequence["triggered_by"] = "sdr_agent"

        # Try to enroll via lead_converter
        enrolled = False
        try:
            from agents.lead_converter.converter import enroll_lead
            result = await enroll_lead(
                lead={"id": lead_id, "niche": niche, "name": target_name},
                niche=niche,
            )
            enrolled = result.get("ok", False)
        except (ImportError, AttributeError):
            pass

        sequence["enrolled"] = enrolled
        self._sequences.append(sequence)

        return {
            "ok": True,
            "sequence_id": sequence["sequence_id"],
            "icp_score": icp["score"],
            "tier": icp["tier"],
            "steps": len(sequence["steps"]),
            "total_delay_hours": sequence["steps"][-1]["delay_hours"],
            "enrolled": enrolled,
            "sequence_created": True,
        }

    # ── 3. MEETING BOOKING ───────────────────────────────────────────

    def _book_meeting(self, lead_id: str = "",
                      target_name: str = "",
                      phone: str = "",
                      email: str = "",
                      preferred_time: str = "",
                      notes: str = "") -> dict:
        """Book a meeting for a qualified lead. Creates a booking record
        that the closing agent can pick up."""
        booking = {
            "booking_id": f"MTG-{uuid.uuid4().hex[:8].upper()}",
            "lead_id": lead_id,
            "target_name": target_name,
            "phone": phone,
            "email": email,
            "preferred_time": preferred_time or "TBD",
            "notes": notes or "SDR-qualified lead",
            "status": "pending_handoff",
            "created_at": self._now(),
            "source": "sdr_agent",
        }
        self._bookings.append(booking)

        # Mark the related sequence as meeting_booked
        for seq in self._sequences:
            if seq.get("lead_id") == lead_id:
                seq["overall_status"] = "meeting_booked"
                break

        return booking

    async def book_meeting(self, lead_id: str = "",
                            target_name: str = "",
                            phone: str = "",
                            email: str = "",
                            preferred_time: str = "",
                            notes: str = "") -> dict:
        """Book a meeting. If the lead has an active sequence, advances it."""
        booking = self._book_meeting(
            lead_id=lead_id,
            target_name=target_name,
            phone=phone,
            email=email,
            preferred_time=preferred_time,
            notes=notes,
        )

        return {
            "ok": True,
            "booking": booking,
            "handoff_instructions": (
                f"Handoff to closing agent: Lead {target_name} ({phone}, {email}) "
                f"has been SDR-qualified and a meeting is booked for {preferred_time or 'TBD'}. "
                f"Prepare discovery brief and product demo."
            ),
        }

    # ── 4. OVERVIEW ──────────────────────────────────────────────────

    def overview(self) -> dict:
        """SDR dashboard — pipeline summary, ICP stats, booking activity."""
        leads = self._fetch_inbound_leads()
        targets = self._fetch_storm_targets()

        # Score all leads
        scored = [self._score_icp_fit(l) for l in leads]
        hot = [s for s in scored if s["tier"] == "hot"]
        warm = [s for s in scored if s["tier"] == "warm"]
        ready = [s for s in scored if s["outbound_ready"]]

        # Sequence stats
        active_seqs = [s for s in self._sequences
                       if s["overall_status"] not in ("completed", "disqualified")]
        meetings_booked = [b for b in self._bookings
                           if b["status"] != "cancelled"]
        handed_off = [b for b in self._bookings
                      if b["status"] == "handed_off"]

        # Niche breakdown
        niche_counts = self._fetch_lead_counts_by_niche()

        return {
            "ts": self._now(),
            "pipeline": {
                "total_leads": len(leads),
                "scored": len(scored),
                "hot": len(hot),
                "warm": len(warm),
                "outbound_ready": len(ready),
                "storm_targets": len(targets),
            },
            "outreach": {
                "active_sequences": len(active_seqs),
                "total_sequences_created": len(self._sequences),
                "meetings_booked": len(meetings_booked),
                "handed_off": len(handed_off),
            },
            "conversion_rates": {
                "lead_to_hot_pct": round(len(hot) / max(len(scored), 1) * 100, 1),
                "lead_to_ready_pct": round(len(ready) / max(len(scored), 1) * 100, 1),
                "sequence_to_meeting_pct": round(
                    len(meetings_booked) / max(len(self._sequences), 1) * 100, 1
                ),
                "meeting_to_handoff_pct": round(
                    len(handed_off) / max(len(meetings_booked), 1) * 100, 1
                ),
            },
            "avg_icp_score": round(
                sum(s["score"] for s in scored) / max(len(scored), 1), 1
            ) if scored else 0,
            "top_niches": dict(sorted(niche_counts.items(),
                                      key=lambda x: x[1], reverse=True)[:10]),
        }

    # ── 5. SCORED LEADS ──────────────────────────────────────────────

    def leads(self, tier_filter: str = "", limit: int = 50) -> dict:
        """Return scored ICP leads, optionally filtered by tier."""
        leads = self._fetch_inbound_leads(limit=limit * 2)
        scored = []

        for lead in leads:
            icp = self._score_icp_fit(lead)
            if tier_filter and icp["tier"] != tier_filter:
                continue
            scored.append({
                "lead_id": lead.get("id", ""),
                "name": lead.get("name", lead.get("warehouse_name", "Unknown")),
                "phone": lead.get("phone", ""),
                "email": lead.get("email", ""),
                "city": lead.get("city", ""),
                "state": lead.get("state", ""),
                "niche": lead.get("niche", ""),
                "created_at": lead.get("created_at", ""),
                **icp,
            })

        scored.sort(key=lambda s: s["score"], reverse=True)

        hot = [s for s in scored if s["tier"] == "hot"]
        warm = [s for s in scored if s["tier"] == "warm"]
        cool = [s for s in scored if s["tier"] == "cool"]
        cold = [s for s in scored if s["tier"] == "cold"]

        return {
            "ts": self._now(),
            "total": len(scored),
            "hot": hot[:limit],
            "warm": warm[:limit],
            "cool": cool[:limit],
            "cold": cold[:limit],
            "summary": {
                "view": tier_filter or "all",
                "hot_count": len(hot),
                "warm_count": len(warm),
                "cool_count": len(cool),
                "cold_count": len(cold),
                "ready_for_outreach": sum(1 for s in scored if s["outbound_ready"]),
            },
        }

    # ── 6. SEQUENCE STATUS ──────────────────────────────────────────

    def sequences(self, limit: int = 20) -> dict:
        """Active and recent outbound sequences with step progress."""
        active = [s for s in self._sequences
                  if s["overall_status"] not in ("completed", "disqualified")]
        completed = [s for s in self._sequences
                     if s["overall_status"] in ("completed", "disqualified")]

        # Show most recent first
        active.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        completed.sort(key=lambda s: s.get("created_at", ""), reverse=True)

        def _summarize(seq: dict) -> dict:
            steps = seq.get("steps", [])
            completed_steps = sum(1 for st in steps if st["status"] == "completed")
            return {
                "sequence_id": seq["sequence_id"],
                "lead_id": seq["lead_id"],
                "target_name": seq["target_name"],
                "niche": seq["niche"],
                "icp_score": seq.get("icp_score", 0),
                "tier": seq.get("tier", ""),
                "status": seq["overall_status"],
                "step_progress": f"{completed_steps}/{len(steps)}",
                "current_step_type": steps[seq["current_step"]]["type"]
                    if seq["current_step"] < len(steps) else "done",
                "created_at": seq.get("created_at", ""),
            }

        return {
            "ts": self._now(),
            "active": [_summarize(s) for s in active[:limit]],
            "completed": [_summarize(s) for s in completed[:limit]],
            "counts": {
                "active": len(active),
                "completed": len(completed),
                "total": len(self._sequences),
            },
        }

    # ── 7. BOOKINGS ─────────────────────────────────────────────────

    def bookings(self, limit: int = 20) -> dict:
        """Booked meetings log with handoff status."""
        pending = [b for b in self._bookings if b["status"] == "pending_handoff"]
        handed_off = [b for b in self._bookings if b["status"] == "handed_off"]
        cancelled = [b for b in self._bookings if b["status"] == "cancelled"]

        pending.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        handed_off.sort(key=lambda b: b.get("created_at", ""), reverse=True)

        return {
            "ts": self._now(),
            "pending_handoff": pending[:limit],
            "handed_off": handed_off[:limit],
            "cancelled_count": len(cancelled),
            "counts": {
                "pending": len(pending),
                "handed_off": len(handed_off),
                "total": len(self._bookings),
            },
        }

    # ── SNAPSHOT ─────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Condensed snapshot for fleet dashboard."""
        o = self.overview()
        return {
            "total_leads_scored": o.get("pipeline", {}).get("scored", 0),
            "hot_leads": o.get("pipeline", {}).get("hot", 0),
            "outbound_ready": o.get("pipeline", {}).get("outbound_ready", 0),
            "active_sequences": o.get("outreach", {}).get("active_sequences", 0),
            "meetings_booked": o.get("outreach", {}).get("meetings_booked", 0),
            "handed_off": o.get("outreach", {}).get("handed_off", 0),
            "avg_icp_score": o.get("avg_icp_score", 0),
            "lead_to_hot_pct": o.get("conversion_rates", {}).get("lead_to_hot_pct", 0),
            "modified": self._now(),
        }

    async def mark_handed_off(self, booking_id: str = "") -> dict:
        """Mark a booking as handed off to the closing agent."""
        for b in self._bookings:
            if b.get("booking_id") == booking_id:
                b["status"] = "handed_off"
                b["handed_off_at"] = self._now()
                return {"ok": True, "booking_id": booking_id, "status": "handed_off"}
        return {"ok": False, "error": f"Booking {booking_id} not found"}


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_sdr_routes(app, get_db=None, require_auth=None):
    """Register SDR Agent routes on a FastAPI app."""
    from fastapi import Depends, HTTPException, Query

    if get_db is None:
        log.warning("[sdr] No get_db — agent will return errors on DB calls")
    _sdr = SDRAgent(get_db=get_db) if get_db else None

    def _get_sdr():
        if _sdr is None:
            raise HTTPException(503, "SDR Agent not initialized (no get_db)")
        return _sdr

    @app.get("/api/sdr/overview")
    async def sdr_overview(auth=Depends(require_auth) if require_auth else None):
        """SDR dashboard — ICP pipeline, outreach stats, conversion rates."""
        return _get_sdr().overview()

    @app.get("/api/sdr/leads")
    async def sdr_leads(
        tier: str = Query("", description="Filter by tier: hot|warm|cool|cold"),
        limit: int = Query(50, ge=1, le=200),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Scored ICP leads with outbound readiness."""
        return _get_sdr().leads(tier_filter=tier, limit=limit)

    @app.post("/api/sdr/sequence")
    async def sdr_trigger_sequence(
        lead_id: str = Query("", description="Lead ID to target"),
        niche: str = Query("", description="Lead niche"),
        target_name: str = Query("", description="Lead/company name"),
        force: bool = Query(False, description="Bypass ICP threshold"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Trigger an SDR outbound sequence on a qualified lead."""
        result = await _get_sdr().trigger_outbound_sequence(
            lead_id=lead_id, niche=niche,
            target_name=target_name, force=force,
        )
        status = 200 if result.get("ok") else 400
        return result

    @app.get("/api/sdr/sequences")
    async def sdr_sequences(
        limit: int = Query(20, ge=1, le=100),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Active outbound sequences with step-by-step progress."""
        return _get_sdr().sequences(limit=limit)

    @app.post("/api/sdr/book")
    async def sdr_book_meeting(
        lead_id: str = Query("", description="Lead ID"),
        target_name: str = Query("", description="Lead/company name"),
        phone: str = Query("", description="Contact phone"),
        email: str = Query("", description="Contact email"),
        preferred_time: str = Query("", description="Preferred meeting time"),
        notes: str = Query("", description="Meeting context"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Book a meeting for a qualified lead. Hands off to closing agent."""
        result = await _get_sdr().book_meeting(
            lead_id=lead_id, target_name=target_name,
            phone=phone, email=email,
            preferred_time=preferred_time, notes=notes,
        )
        return result

    @app.get("/api/sdr/bookings")
    async def sdr_bookings(
        limit: int = Query(20, ge=1, le=100),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Booked meetings log with handoff status."""
        return _get_sdr().bookings(limit=limit)

    @app.post("/api/sdr/handoff")
    async def sdr_handoff(
        booking_id: str = Query("", description="Booking ID to mark as handed off"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Mark a booking as handed off to the closing agent."""
        result = await _get_sdr().mark_handed_off(booking_id=booking_id)
        status = 200 if result.get("ok") else 404
        return result

    @app.get("/api/sdr/snapshot")
    async def sdr_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Condensed snapshot for fleet dashboard."""
        return _get_sdr().snapshot()

    log.info("[sdr] Routes registered · /api/sdr/{overview,leads,sequence,sequences,book,bookings,handoff,snapshot}")
