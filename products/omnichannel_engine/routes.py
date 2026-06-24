"""
EMPIRE V49 · OMNICHANNEL ENGINE — API Routes
==============================================
FastAPI endpoints for the 3-layer omnichannel engine.

Routes:
  GET  /api/v1/omni/status            — Engine health + stats
  GET  /api/v1/omni/leads             — Ingest leads from all sources
  POST /api/v1/omni/classify          — Classify a batch of leads (Groq LLM)
  POST /api/v1/omni/classify/single   — Classify a single lead
  GET  /api/v1/omni/agenda            — Get cadence definitions
  POST /api/v1/omni/agenda/schedule   — Build agenda for classified leads
  POST /api/v1/omni/run               — Full pipeline: ingest → classify → schedule
  POST /api/v1/omni/sync              — Sync classified leads to Twenty CRM + ListMonk

Wired into hub.py:
    from products.omnichannel_engine.routes import register_omni_routes
    register_omni_routes(app, require_auth=require_auth)
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query

log = logging.getLogger("empire.omni.routes")


def register_omni_routes(app, require_auth=None):
    """Register omnichannel engine endpoints on the FastAPI app."""

    from products.omnichannel_engine.leads_hub import LeadsHub
    from products.omnichannel_engine.classifier import GroqClassifier
    from products.omnichannel_engine.agenda_controller import AgendaController

    hub = LeadsHub()
    classifier = GroqClassifier()
    agenda = AgendaController()

    # ── Status ─────────────────────────────────────────────────────────

    @app.get("/api/v1/omni/status")
    async def omni_status(auth=Depends(require_auth) if require_auth else None):
        """Return engine health, layer stats, and configuration."""
        return {
            "ok": True,
            "engine": "3-Layer Omnichannel Engine",
            "layers": {
                "leads_hub": hub.snapshot(),
                "classifier": classifier.snapshot(),
                "agenda": agenda.snapshot(),
            },
        }

    # ── Layer 1: Leads Hub ─────────────────────────────────────────────

    @app.get("/api/v1/omni/leads")
    async def omni_leads(
        limit: int = Query(100, ge=1, le=500),
        source: Optional[str] = Query(None, description="Filter: radar_targets, enriched_leads, campaign_leads"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Ingest leads from Supabase across all sources with dedup."""
        sources = [source] if source else None
        leads = await hub.ingest_leads(limit=limit, sources=sources)
        return {"ok": True, "leads": leads, "count": len(leads), "stats": hub.snapshot()}

    # ── Layer 2: Classification ────────────────────────────────────────

    @app.post("/api/v1/omni/classify")
    async def omni_classify_batch(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Classify a batch of leads using Groq LLM.

        Body:
          leads: list[dict] — Array of unified lead records
          concurrency: int (optional, default 3) — Parallel classification limit
        """
        leads = body.get("leads", [])
        if not leads:
            raise HTTPException(400, "Missing required field: leads (array of lead objects)")

        concurrency = int(body.get("concurrency", 3))
        classified = await classifier.classify_batch(leads, concurrency=concurrency)

        hot = sum(1 for l in classified if l.get("temperature") == "hot")
        warm = sum(1 for l in classified if l.get("temperature") == "warm")
        return {
            "ok": True,
            "classified": len(classified),
            "hot": hot,
            "warm": warm,
            "cold": len(classified) - hot - warm,
            "leads": classified,
            "stats": classifier.snapshot(),
        }

    @app.post("/api/v1/omni/classify/single")
    async def omni_classify_single(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Classify a single lead using Groq LLM.

        Body:
          lead: dict — Single unified lead record
        """
        lead = body.get("lead")
        if not lead:
            raise HTTPException(400, "Missing required field: lead")
        if not isinstance(lead, dict):
            raise HTTPException(400, "lead must be a dict object")

        result = await classifier.classify_lead(lead)
        return {"ok": True, "lead": result, "stats": classifier.snapshot()}

    # ── Layer 3: Agenda ────────────────────────────────────────────────

    @app.get("/api/v1/omni/agenda")
    async def omni_agenda(
        temperature: Optional[str] = Query(None, description="Filter: hot, warm, cold"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Get cadence definitions and routing rules."""
        return {"ok": True, **agenda.get_cadence_report(temperature or "")}

    @app.post("/api/v1/omni/agenda/schedule")
    async def omni_agenda_schedule(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Build a multi-step outreach agenda for classified leads.

        Body:
          leads: list[dict] — Classified leads with temperature + key_message
        """
        leads = body.get("leads", [])
        if not leads:
            raise HTTPException(400, "Missing required field: leads")

        items = await agenda.schedule_batch(leads)
        return {
            "ok": True,
            "agenda_items": len(items),
            "leads_scheduled": len(leads),
            "items": items[:50],
            "stats": agenda.snapshot(),
        }

    # ── Full Pipeline ─────────────────────────────────────────────────

    @app.post("/api/v1/omni/run")
    async def omni_run(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Run the full 3-layer pipeline: ingest → classify → schedule.

        When dry_run=false, persists classified leads and agenda items to
        Supabase (agent_activity / omni_log) and auto-syncs to ListMonk.

        Body:
          limit: int (optional, default 50) — Max leads to ingest
          concurrency: int (optional, default 3) — Groq parallelism
          dry_run: bool (optional, default true) — If false, persist + sync
        """
        import os as _os, datetime as _dt, uuid as _uuid
        limit = int(body.get("limit", 50))
        concurrency = int(body.get("concurrency", 3))
        dry_run = bool(body.get("dry_run", True))

        # Layer 1: Ingest
        leads = await hub.ingest_leads(limit=limit)
        if not leads:
            return {"ok": False, "error": "No leads ingested"}

        # Layer 2: Classify
        classified = await classifier.classify_batch(leads, concurrency=concurrency)

        # Layer 3: Schedule
        items = await agenda.schedule_batch(classified)

        # ── If not dry_run: persist + sync ────────────────────────────
        persisted = 0
        sync_result = []
        if not dry_run:
            # Persist to Supabase agent_activity
            try:
                from supabase import create_client as _cc
                sb = _cc(_os.environ.get("SUPABASE_URL", ""), _os.environ.get("SUPABASE_SERVICE_KEY", ""))
                now = _dt.datetime.now(_dt.timezone.utc).isoformat()

                # Write pipeline summary record
                hot = sum(1 for l in classified if l.get("temperature") == "hot")
                warm = sum(1 for l in classified if l.get("temperature") == "warm")
                run_uuid = str(_uuid.uuid4())
                sb.table("agent_activity").insert({
                    "agent_name": "omni_pipeline",
                    "run_id": run_uuid,
                    "started_at": now,
                    "status": "ok",
                    "rows_processed": len(classified),
                    "summary": f"Omni run: {len(leads)} ingested, {len(classified)} classified, {len(items)} agenda",
                    "meta": {
                        "ingested": len(leads),
                        "classified": len(classified),
                        "hot": hot,
                        "warm": warm,
                        "agenda_items": len(items),
                    },
                }).execute()
                persisted += 1

                # Write individual classified lead records
                for cl in classified:
                    sb.table("agent_activity").insert({
                        "agent_name": f"omni_classified_{cl.get('temperature','?')}",
                        "run_id": str(_uuid.uuid4()),
                        "started_at": cl.get("classified_at", now),
                        "status": "ok",
                        "rows_processed": 1,
                        "summary": f"{cl.get('name','')[:40]} → {cl.get('temperature','?')} (conf={cl.get('confidence',0)})",
                        "meta": {
                            "confidence": cl.get("confidence", 0),
                            "email": (cl.get("email") or "")[:80],
                            "phone": cl.get("phone", ""),
                            "city": cl.get("city", ""),
                            "state": cl.get("state", ""),
                            "niche": cl.get("niche", ""),
                        },
                    }).execute()
                    persisted += 1

                # Write agenda items
                for item in items:
                    ts = item.get("scheduled_at", now)
                    sb.table("agent_activity").insert({
                        "agent_name": f"omni_agenda_{item.get('channel','?')}",
                        "run_id": str(_uuid.uuid4()),
                        "started_at": ts,
                        "status": "ok",
                        "rows_processed": 1,
                        "summary": f"{item.get('channel','?')}: {item.get('label','')} for {item.get('lead_name','')[:30]}",
                        "meta": {
                            "channel": item.get("channel", ""),
                            "step": item.get("step", 0),
                            "scheduled_at": ts,
                            "delay_hours": item.get("delay_hours", 0),
                            "temperature": item.get("temperature", ""),
                        },
                    }).execute()
            except Exception as e:
                log.warning(f"[omni] persist failed: {e}")

            # Auto-sync to ListMonk
            try:
                lm_count = await hub.sync_to_listmonk(classified)
                sync_result.append(f"listmonk={lm_count}")
            except Exception as e:
                sync_result.append(f"listmonk_error={e}")

        return {
            "ok": True,
            "pipeline": "ingest → classify → schedule",
            "dry_run": dry_run,
            "ingested": len(leads),
            "classified": len(classified),
            "hot": sum(1 for l in classified if l.get("temperature") == "hot"),
            "warm": sum(1 for l in classified if l.get("temperature") == "warm"),
            "cold": sum(1 for l in classified if l.get("temperature") == "cold"),
            "agenda_items": len(items),
            "persisted_to_db": persisted if not dry_run else 0,
            "auto_sync": ", ".join(sync_result) if sync_result else "dry_run",
            "stats": {
                "leads_hub": hub.snapshot(),
                "classifier": classifier.snapshot(),
                "agenda": agenda.snapshot(),
            },
        }

    # ── CRM Sync ───────────────────────────────────────────────────────

    @app.post("/api/v1/omni/sync")
    async def omni_sync(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Sync classified leads to Twenty CRM and ListMonk.

        Body:
          leads: list[dict] — Classified leads
          sync_targets: list[str] (optional) — ["twenty", "listmonk"], default both
        """
        leads = body.get("leads", [])
        if not leads:
            raise HTTPException(400, "Missing required field: leads")

        targets = body.get("sync_targets", ["twenty", "listmonk"])
        result = {"ok": True, "synced": {}}

        if "twenty" in targets:
            result["synced"]["twenty"] = await hub.sync_to_twenty(leads)
        if "listmonk" in targets:
            result["synced"]["listmonk"] = await hub.sync_to_listmonk(leads)

        # Also sync agenda items to Twenty as tasks
        items = await agenda.schedule_batch(leads)
        result["synced"]["agenda_tasks"] = await agenda.sync_agenda_to_twenty(items)

        return result

    log.info("[omni.routes] REST routes registered (8 endpoints)")
