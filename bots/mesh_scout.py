"""
EMPIRE V49 · MESH SCOUT (HERMES PROTOCOL · SCOUTING TEAM A)
=============================================================
Prospector satellite agent. Scrapes weather/satellite data for areas
with recent storm activity and roof damage potential. Drops findings
as 'To-Do' tickets in the agent_task_queue for the Outreach agent
to pick up.

Runs standalone: python3 bots/mesh_scout.py --metro Wichita
Runs via mesh:   spawned by agent_mesh mesh_loop when a task exists

Local sovereignty: All LLM calls go through local Ollama.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client
from config.metros import METROS as _SHARED_METROS, metro_state

log = logging.getLogger("mesh.scout")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Metro centroids for satellite analysis — imported from shared config
# Convert from {metro: {lat, lon, state}} to the format mesh_scout expects
METROS: Dict[str, Dict[str, Any]] = {
    name: {
        "lat": float(m["lat"]),
        "lon": float(m["lon"]),
        "state": str(m.get("state", "")),
    }
    for name, m in _SHARED_METROS.items()
}


async def query_ollama(
    prompt: str,
    system: str = "",
    temperature: float = 0.2,
) -> str:
    """Query local Ollama for analysis."""
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
                    "options": {"temperature": temperature, "num_predict": 512},
                },
            )
            if r.status_code == 200:
                return str(r.json().get("response", ""))
            else:
                log.warning(f"[scout] Ollama error: HTTP {r.status_code}")
                return ""
    except Exception as e:
        log.error(f"[scout] Ollama call failed: {e}")
        return ""


async def analyze_damage_potential(
    metro: str,
    niche: str = "roofing",
) -> Optional[Dict[str, Any]]:
    """Use Ollama + existing storm data to assess damage potential in a metro."""
    # First check if there are active storm alerts in the area
    active_storms = False
    try:
        r = _sb.table("storm_forecasts").select("severity,area_desc,event,issued_at") \
            .gte("issued_at", datetime.now(timezone.utc).isoformat()) \
            .limit(10).execute()
        for row in (r.data or []):
            area: str = (row.get("area_desc") or "").lower()  # type: ignore[union-attr]
            metro_lower: str = metro.lower()
            if metro_lower in area or metro_lower in area:
                active_storms = True
                log.info(f"[scout] Active storm in {metro}: {row.get('event')} ({row.get('severity')})")  # type: ignore[union-attr]
    except Exception as e:
        log.debug(f"[scout] storm_forecasts query: {e}")

    # Check radar_targets for recent activity in this metro
    recent_targets: int = 0
    try:
        r = (
            _sb.table("radar_targets")
            .select("id", count="exact")  # type: ignore[arg-type]
            .gte("created_at", f"{(datetime.now(timezone.utc).isoformat())}")
            .execute()
        )
        recent_targets = (r.count or 0) if hasattr(r, "count") else len(r.data or [])
    except Exception:
        pass

    # Use Ollama to analyze if there's damage potential
    system_prompt: str = (
        "You are a storm damage assessment AI. Analyze whether a metro area has "
        "high roof damage potential based on the data provided. "
        "Return ONLY valid JSON: "
        '{"damage_potential": "high|medium|low", "confidence": 0.0-1.0, '
        '"reasoning": "brief reason", "estimated_leads": number}'
    )
    prompt: str = (
        f"Metro: {metro}\n"
        f"Niche: {niche}\n"
        f"Active storms in area: {active_storms}\n"
        f"Recent radar targets: {recent_targets}\n\n"
        "Assess the roof damage potential. JSON only."
    )
    result: str = await query_ollama(prompt, system_prompt, temperature=0.2)
    if not result:
        return None

    # Parse JSON from Ollama response
    try:
        clean: str = result.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        parsed: Any = json.loads(clean)
        assert isinstance(parsed, dict) or parsed is None
        return parsed
    except (json.JSONDecodeError, IndexError, AttributeError) as e:
        log.warning(f"[scout] JSON parse error: {e} | raw: {result[:100]}")
        # Default to low if parsing fails
        return {"damage_potential": "low", "confidence": 0.1, "reasoning": "parse fallback", "estimated_leads": 0}


async def scout_metro(
    metro: str = "Wichita",
    niche: str = "roofing",
    dry_run: bool = False,
) -> Optional[str]:
    """
    Scout a metro for roof damage potential. Returns ticket_id if a task was created.
    This is the main entry point called by the mesh loop or run directly.
    """
    log.info(f"[scout] analyzing {metro} for {niche} damage potential...")

    analysis: Optional[Dict[str, Any]] = await analyze_damage_potential(metro, niche)
    if not analysis:
        log.warning(f"[scout] no analysis returned for {metro}")
        return None

    damage: str = str(analysis.get("damage_potential", "low") or "low")
    confidence: float = float(analysis.get("confidence", 0) or 0)
    estimated_leads: int = int(analysis.get("estimated_leads", 0) or 0)
    reasoning: str = str(analysis.get("reasoning", "") or "")

    log.info(f"[scout] {metro}: damage={damage}, confidence={confidence:.2f}, leads={estimated_leads}")

    # Only create a task if damage potential is medium or high with decent confidence
    if damage not in ("high", "medium") or confidence < 0.3:
        log.info(f"[scout] {metro}: not enough damage potential, skipping")
        return None

    # Check for existing scout tasks for this metro to avoid duplicates
    try:
        existing = _sb.table("agent_task_queue").select("ticket_id") \
            .eq("task_type", "scout.find_roofs") \
            .eq("status", "To-Do") \
            .execute()
        for t in (existing.data or []):
            t_payload: Any = t.get("payload") or {}  # type: ignore[union-attr]
            if isinstance(t_payload, str):
                try:
                    t_payload = json.loads(t_payload)
                except Exception:
                    continue
            if isinstance(t_payload, dict) and t_payload.get("metro") == metro:
                log.info(f"[scout] {metro}: duplicate task exists, skipping")
                return None
    except Exception:
        pass

    # Create the task ticket
    metro_meta: Dict[str, Any] = METROS.get(metro, {})
    payload: Dict[str, Any] = {
        "metro": metro,
        "niche": niche,
        "damage_potential": damage,
        "confidence": confidence,
        "estimated_leads": estimated_leads,
        "reasoning": reasoning,
        "lat": metro_meta.get("lat"),
        "lon": metro_meta.get("lon"),
    }

    if dry_run:
        log.info(f"[scout] DRY RUN: would create task: {json.dumps(payload)[:200]}")
        return "dry-run"

    try:
        r = _sb.table("agent_task_queue").insert({
            "task_type": "scout.find_roofs",
            "payload": json.dumps(payload),
            "status": "To-Do",
            "priority": 3 if damage == "high" else 1,
        }).execute()
        if r.data:
            raw_ticket: Any = r.data[0].get("ticket_id")  # type: ignore[union-attr]
            ticket_id: str = str(raw_ticket) if raw_ticket else ""
            log.info(f"[scout] created task {ticket_id[:8]} for {metro} (damage={damage})")
            return ticket_id
    except Exception as e:
        log.error(f"[scout] task creation error: {e}")

    return None


async def scout_all_metros(
    niche: str = "roofing",
    dry_run: bool = False,
) -> List[str]:
    """Scout all configured metros for damage potential. Returns list of ticket_ids."""
    results = []
    for metro in METROS:
        ticket_id = await scout_metro(metro, niche, dry_run)
        if ticket_id:
            results.append(ticket_id)
        await asyncio.sleep(1)  # Rate limit between metros
    log.info(f"[scout] scout complete: {len(results)} tasks created")
    return results


async def run_once(
    metro: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run the scout pipeline once. Returns summary dict."""
    if metro:
        ticket_id = await scout_metro(metro, dry_run=dry_run)
        return {"ticket_id": ticket_id, "metro": metro, "tasks_created": 1 if ticket_id else 0}
    else:
        tickets = await scout_all_metros(dry_run=dry_run)
        return {"tickets": tickets, "metros_scouted": len(METROS), "tasks_created": len(tickets)}


async def run_loop(interval_sec: int = 3600):
    """Run the scout in a background loop. Default: check every hour."""
    log.info(f"[scout] starting background loop (interval={interval_sec}s)")
    while True:
        try:
            results = await run_once()
            log.info(f"[scout] cycle complete: {results}")
        except Exception as e:
            log.error(f"[scout] cycle error: {e}")
        await asyncio.sleep(interval_sec)


if __name__ == "__main__":
    metro = None
    for i, arg in enumerate(sys.argv):
        if arg == "--metro" and i + 1 < len(sys.argv):
            metro = sys.argv[i + 1]
    dry = "--dry-run" in sys.argv
    if "--loop" in sys.argv:
        asyncio.run(run_loop())
    else:
        results = asyncio.run(run_once(metro=metro, dry_run=dry))
        print(json.dumps(results, indent=2))
