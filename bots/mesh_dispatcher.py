"""
EMPIRE V49 · MESH DISPATCHER (HERMES PROTOCOL · REVENUE TEAM A)
===============================================================
Revenue dispatcher agent. Connects qualified leads to buyers by:

1. Looking for 'revenue.connect_buyer' tasks in the queue
2. Querying radar_targets/prospects for qualified leads
3. Matching leads with available buyers (from buyers table)
4. Creating dispatch records and updating the task status

Local sovereignty: All LLM calls go through local Ollama.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("mesh.dispatcher")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)


async def query_ollama(prompt: str, system: str = "", temperature: float = 0.3) -> str:
    """Query local Ollama for dispatch analysis."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": os.environ.get("AI_MODEL_ENRICH", "llama3.2:3b"),
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": 256},
                },
            )
            if r.status_code == 200:
                return r.json().get("response", "")
    except Exception as e:
        log.error(f"[dispatcher] Ollama call failed: {e}")
    return ""


async def find_qualified_leads(limit: int = 10) -> List[Dict]:
    """Find qualified leads from radar_targets that haven't been dispatched yet."""
    leads = []
    try:
        # Look for active leads with phone numbers that haven't been dispatched
        r = _sb.table("radar_targets").select(
            "id,address,phone,city,status,damage_severity,urgency_score,created_at,meta"
        ).eq("status", "active").not_.is_("phone", "null") \
            .order("urgency_score", desc=True) \
            .order("created_at", desc=True) \
            .limit(limit).execute()

        # Filter out leads that already have dispatches
        for lead in (r.data or []):
            # Check if already dispatched
            try:
                existing = _sb.table("dispatches").select("id").eq("lead_id", lead["id"]).limit(1).execute()
                if existing.data:
                    continue
            except Exception:
                pass
            leads.append(lead)

    except Exception as e:
        log.error(f"[dispatcher] query leads error: {e}")

    return leads


async def find_available_buyers(metro: Optional[str] = None) -> List[Dict]:
    """Find buyers that can accept leads."""
    buyers = []
    try:
        q = _sb.table("buyers").select("id,buyer_name,metro,niche,daily_cap,calls_today")
        if metro:
            q = q.eq("metro", metro)
        r = q.execute()

        for buyer in (r.data or []):
            max_leads = buyer.get("daily_cap", 10) or 10
            accepted = buyer.get("calls_today", 0) or 0
            if accepted < max_leads:
                buyers.append(buyer)

    except Exception as e:
        log.error(f"[dispatcher] query buyers error: {e}")

    return buyers


async def score_lead_quality(lead: Dict) -> Dict:
    """Score lead quality through PanelCourt 5-panel consensus (CFO, Growth, Strategy, Purist, Judge).
    Falls back to single Ollama call if PanelCourt is unavailable."""
    try:
        from bots.panel_court import panel_court_score_lead
        result = await panel_court_score_lead(lead)
        log.info(f"[dispatcher] PanelCourt score={result.get('panel_court_score', '?')} verdict={result.get('panel_court_verdict', '?')}")
        return result
    except ImportError:
        log.warning(f"[dispatcher] PanelCourt not available, using legacy scoring")
    except Exception as e:
        log.error(f"[dispatcher] PanelCourt error: {e}, falling back to legacy scoring")

    # Legacy single-LLM fallback
    system_prompt = (
        "You are a lead quality assessor for a roofing dispatch service. "
        "Score the lead on a scale of 0-100 based on conversion potential. "
        "Return ONLY JSON: "
        '{"quality_score": 0-100, "reasoning": "brief note", "recommended_action": "dispatch|review|skip"}'
    )
    meta = lead.get("meta", {})
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    prompt = (
        f"Lead: {lead.get('address', 'unknown')}\n"
        f"City: {lead.get('city', 'unknown')}\n"
        f"Damage severity: {lead.get('damage_severity', 'unknown')}\n"
        f"Urgency score: {lead.get('urgency_score', 'N/A')}\n"
        f"Meta: {json.dumps(meta)[:200]}\n\n"
        "Score this lead. JSON only."
    )

    result = await query_ollama(prompt, system_prompt, temperature=0.2)
    if not result:
        return {"quality_score": 50, "reasoning": "ollama unavailable", "recommended_action": "review"}

    try:
        clean = result.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        return json.loads(clean)
    except (json.JSONDecodeError, IndexError):
        return {"quality_score": 50, "reasoning": "parse fallback", "recommended_action": "review"}


async def create_dispatch(lead: Dict, buyer: Dict, quality: Dict) -> Optional[str]:
    """Create a dispatch record linking lead to buyer.
    Uses the existing dispatches table schema — non-standard fields go in meta jsonb."""
    try:
        r = _sb.table("dispatches").insert({
            "lead_id": lead["id"],
            "status": "sent",
            "meta": json.dumps({
                "source": "mesh.dispatcher",
                "buyer_id": buyer.get("id"),                        "buyer_name": buyer.get("buyer_name"),
                "lead_phone": lead.get("phone"),
                "lead_address": lead.get("address"),
                "lead_city": lead.get("city"),
                "quality_score": quality.get("quality_score", 50),
                "reasoning": quality.get("reasoning", ""),
                "dispatched_at": datetime.now(timezone.utc).isoformat(),
            }),
        }).execute()

        if r.data:
            dispatch_id = r.data[0].get("id")
            log.info(f"[dispatcher] dispatch created: {dispatch_id[:8]} → {buyer.get('buyer_name')}")

            # Update the lead status
            _sb.table("radar_targets").update({
                "status": "converted",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", lead["id"]).execute()

            # ── Feed back to SEO learning loop ──────────────────────
            try:
                from bots.seo_agent import get_seo_agent
                seo = get_seo_agent()
                meta = lead.get("meta", {})
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                keyword = (
                    meta.get("keyword")
                    or meta.get("keyword_matched")
                    or lead.get("damage_severity", "")
                    or "lead"
                )
                await seo.record_outcome(
                    keyword=str(keyword),
                    lead_id=lead["id"],
                    success=True,
                    revenue=float(buyer.get("base_payout", 0) or 0),
                )
            except Exception as e:
                log.warning(f"[dispatcher] SEO outcome recording skipped: {e}")

            return dispatch_id
    except Exception as e:
        log.error(f"[dispatcher] create_dispatch error: {e}")
    return None


async def process_task(task: Dict, dry_run: bool = False) -> Dict:
    """
    Process one dispatch task: find a qualified lead, match with buyer, create dispatch.
    """
    ticket_id = task.get("ticket_id")

    # Get qualified leads
    leads = await find_qualified_leads(limit=5)
    if not leads:
        log.info(f"[dispatcher] no qualified leads available")
        if not dry_run:
            try:
                _sb.table("agent_task_queue").update({
                    "status": "Blocked",
                    "error": "No qualified leads available",
                }).eq("ticket_id", ticket_id).execute()
            except Exception:
                pass
        return {"ticket_id": ticket_id, "status": "blocked", "reason": "no leads"}

    # Get available buyers
    buyers = await find_available_buyers()
    if not buyers:
        log.info(f"[dispatcher] no available buyers")
        if not dry_run:
            try:
                _sb.table("agent_task_queue").update({
                    "status": "Blocked",
                    "error": "No available buyers",
                }).eq("ticket_id", ticket_id).execute()
            except Exception:
                pass
        return {"ticket_id": ticket_id, "status": "blocked", "reason": "no buyers"}

    dispatched = 0
    for lead in leads:
        if not buyers:
            break

        # Score the lead
        quality = await score_lead_quality(lead)
        if quality.get("recommended_action") == "skip":
            log.info(f"[dispatcher] skipping lead {lead['id'][:8]}: {quality.get('reasoning', '')}")
            continue

        if quality.get("quality_score", 0) < 30:
            log.info(f"[dispatcher] lead {lead['id'][:8]} score too low ({quality['quality_score']}), skipping")
            continue

        # Pick the best buyer for this lead
        buyer = buyers.pop(0)

        if dry_run:
            log.info(f"[dispatcher] DRY RUN: would dispatch lead {lead['id'][:8]} to {buyer.get('buyer_name')}")
            dispatched += 1
            continue

        # Create the dispatch
        dispatch_id = await create_dispatch(lead, buyer, quality)
        if dispatch_id:
            dispatched += 1
            log.info(f"[dispatcher] dispatched lead {lead['id'][:8]} → {buyer.get('buyer_name')}")

    # Mark the task
    if not dry_run:
        try:
            status = "Done" if dispatched > 0 else "Blocked"
            _sb.table("agent_task_queue").update({
                "status": status,
                "result": json.dumps({"dispatched": dispatched, "leads_available": len(leads)}),
                "completed_at": datetime.now(timezone.utc).isoformat() if dispatched > 0 else None,
            }).eq("ticket_id", ticket_id).execute()
        except Exception as e:
            log.error(f"[dispatcher] status update error: {e}")

    return {
        "ticket_id": ticket_id,
        "status": "done" if dispatched > 0 else "blocked",
        "dispatched": dispatched,
        "leads_reviewed": len(leads),
    }


async def run_once(dry_run: bool = False) -> Dict:
    """
    Main entry point: auto-create a dispatch task if none exists, then process.
    """
    results = {"dispatched": 0, "blocked": 0}

    # First ensure a dispatch task exists in the queue
    try:
        existing = _sb.table("agent_task_queue").select("ticket_id,status") \
            .eq("task_type", "revenue.connect_buyer") \
            .in_("status", ["To-Do", "In Progress"]) \
            .limit(1).execute()

        if not existing.data:
            if not dry_run:
                # Create a dispatch task
                _sb.table("agent_task_queue").insert({
                    "task_type": "revenue.connect_buyer",
                    "payload": json.dumps({"source": "mesh.dispatcher", "auto_created": True}),
                    "status": "To-Do",
                    "priority": 5,  # High priority — revenue!
                }).execute()
                log.info(f"[dispatcher] auto-created dispatch task")
    except Exception as e:
        log.error(f"[dispatcher] task creation error: {e}")

    # Heartbeat in agent_registry
    try:
        _sb.table("agent_registry").upsert({
            "agent_name": "mesh.dispatcher",
            "status": "ACTIVE",
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": ["dispatcher", "buyer", "revenue"],
            "task_types": ["revenue.connect_buyer"],
        }, on_conflict="agent_name").execute()
    except Exception as e:
        log.error(f"[dispatcher] heartbeat error: {e}")

    # Claim and process tasks
    try:
        r = _sb.rpc("claim_next_task", {
            "p_agent_name": "mesh.dispatcher",
            "p_task_types": ["revenue.connect_buyer"],
        }).execute()

        while r.data:
            task = r.data
            task["payload"] = json.loads(task.get("payload", "{}")) if isinstance(task.get("payload"), str) else task.get("payload", {})

            result = await process_task(task, dry_run=dry_run)
            if result.get("status") == "done":
                results["dispatched"] += result.get("dispatched", 0)
            else:
                results["blocked"] += 1

            # Try next
            r = _sb.rpc("claim_next_task", {
                "p_agent_name": "mesh.dispatcher",
                "p_task_types": ["revenue.connect_buyer"],
            }).execute()

    except Exception as e:
        log.error(f"[dispatcher] run_once error: {e}")
        results["error"] = str(e)

    log.info(f"[dispatcher] run complete: {results}")
    return results


async def run_loop(interval_sec: int = 120):
    """Run the dispatcher in a background loop."""
    log.info(f"[dispatcher] starting background loop (interval={interval_sec}s)")
    while True:
        try:
            results = await run_once()
            log.info(f"[dispatcher] cycle: {results}")
        except Exception as e:
            log.error(f"[dispatcher] cycle error: {e}")
        await asyncio.sleep(interval_sec)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    if "--loop" in sys.argv:
        asyncio.run(run_loop())
    else:
        results = asyncio.run(run_once(dry_run=dry))
        print(json.dumps(results, indent=2))
