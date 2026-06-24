"""
EMPIRE V49 · MESH OUTREACH (HERMES PROTOCOL · SCOUTING TEAM B)
===============================================================
Monitors the agent_task_queue for 'scout.find_roofs' tickets that are
'To-Do'. Picks them up, drafts a personalized outreach email using
local Ollama, saves the draft, and moves the ticket to 'Done'.

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

log = logging.getLogger("mesh.outreach")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("AI_MODEL_DRAFT", "llama3.1:latest")
DRAFTS_DIR = "/root/empire-v49/outreach_drafts"

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)


async def query_ollama(prompt: str, system: str = "", temperature: float = 0.4) -> str:
    """Query local Ollama for email drafting."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": 1024},
                },
            )
            if r.status_code == 200:
                return r.json().get("response", "")
    except Exception as e:
        log.error(f"[outreach] Ollama call failed: {e}")
    return ""


async def draft_outreach_email(task: Dict) -> Optional[Dict]:
    """
    Draft a personalized outreach email for a scout task.
    Returns dict with subject, body, or None on failure.
    """
    payload = task.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}

    metro = payload.get("metro", "the area")
    niche = payload.get("niche", "roofing")
    damage = payload.get("damage_potential", "unknown")
    reasoning = payload.get("reasoning", "")

    system_prompt = (
        "You are an expert email copywriter for a storm damage restoration "
        "lead generation service. Write a SHORT, professional outreach email "
        "to a roofing contractor. The email should:\n"
        "1. Be personalized to their metro area\n"
        "2. Mention recent storm activity and damage potential\n"
        "3. Explain the Pay-Per-Call lead service briefly\n"
        "4. End with a clear call to action (reply or schedule a call)\n\n"
        "Rules:\n"
        "- MAX 150 words, keep it tight\n"
        "- Professional tone, not pushy\n"
        "- No placeholders like [Name] — write for 'Roofing Team'\n"
        "- No emojis or hashtags\n"
        "- Return ONLY JSON: {\"subject\": \"email subject\", \"body\": \"email body text\"}"
    )
    prompt = (
        f"Metro: {metro}\n"
        f"Niche: {niche}\n"
        f"Damage assessment: {damage} potential\n"
        f"Context: {reasoning}\n\n"
        "Write the outreach email. JSON only."
    )

    result = await query_ollama(prompt, system_prompt, temperature=0.5)
    if not result:
        log.warning(f"[outreach] no response from Ollama for {metro}")
        return None

    try:
        clean = result.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        draft = json.loads(clean)

        subject = draft.get("subject", f"Storm damage leads in {metro}")
        body = draft.get("body", "")

        if not body:
            log.warning(f"[outreach] empty body returned for {metro}")
            return None

        return {
            "subject": subject[:200],
            "body": body[:3000],
            "metro": metro,
            "niche": niche,
        }
    except (json.JSONDecodeError, IndexError) as e:
        log.warning(f"[outreach] JSON parse error: {e}")
        return None


async def save_draft(draft: Dict) -> Optional[str]:
    """
    Save the outreach email draft to disk and to Supabase email_drafts.
    Returns the file path or None.
    """
    metro = draft.get("metro", "unknown")
    safe_metro = metro.replace(" ", "_").replace("/", "_")[:30]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}__outreach__{safe_metro}.txt"
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    path = os.path.join(DRAFTS_DIR, filename)

    lines = [
        f"=== OUTREACH DRAFT (HERMES MESH) ===",
        f"Metro:      {metro}",
        f"Niche:      {draft.get('niche', 'roofing')}",
        f"Subject:    {draft['subject']}",
        f"Generated:  {datetime.now().isoformat()}",
        f"Status:     DRAFT — REVIEW BEFORE SENDING",
        f"",
        f"---",
        f"",
        draft["body"],
        f"",
        f"---",
        f"⚠  Auto-generated draft. Manual review required before sending.",
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines))

    # Also save to Supabase email_drafts table
    try:
        _sb.table("email_drafts").insert({
            "to_email": None,  # Will be filled by operator after review
            "subject": draft["subject"],
            "body": draft["body"],
            "status": "pending",
            "meta": json.dumps({
                "source": "hermes_mesh",
                "metro": metro,
                "agent": "mesh.outreach",
            }),
        }).execute()
        log.info(f"[outreach] draft saved to Supabase email_drafts")
    except Exception as e:
        log.warning(f"[outreach] Supabase save error: {e}")

    log.info(f"[outreach] draft saved: {path}")
    return path


async def process_task(task: Dict, dry_run: bool = False) -> Dict:
    """
    Process one scout task: draft email and mark complete.
    Returns result dict.
    """
    ticket_id = task.get("ticket_id")
    log.info(f"[outreach] processing task {ticket_id[:8]}...")

    # Draft the email
    draft = await draft_outreach_email(task)
    if not draft:
        log.warning(f"[outreach] failed to draft email for task {ticket_id[:8]}")
        if not dry_run:
            try:
                _sb.table("agent_task_queue").update({
                    "status": "Failed",
                    "error": "Failed to draft email via Ollama",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("ticket_id", ticket_id).execute()
            except Exception:
                pass
        return {"ticket_id": ticket_id, "status": "failed", "error": "draft failed"}

    if dry_run:
        log.info(f"[outreach] DRY RUN: would save draft for {draft.get('metro')}")
        log.info(f"  Subject: {draft['subject']}")
        log.info(f"  Body preview: {draft['body'][:200]}...")
        return {"ticket_id": ticket_id, "status": "dry_run", "draft": draft}

    # Save the draft
    path = await save_draft(draft)
    if not path:
        log.warning(f"[outreach] failed to save draft for task {ticket_id[:8]}")
        return {"ticket_id": ticket_id, "status": "failed", "error": "save failed"}

    # Mark task as Done
    try:
        _sb.table("agent_task_queue").update({
            "status": "Done",
            "result": json.dumps({
                "subject": draft["subject"],
                "draft_path": path,
                "metro": draft.get("metro"),
            }),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("ticket_id", ticket_id).execute()
        log.info(f"[outreach] task {ticket_id[:8]} completed → Done")
    except Exception as e:
        log.error(f"[outreach] status update error: {e}")

    return {
        "ticket_id": ticket_id,
        "status": "done",
        "draft_path": path,
        "subject": draft["subject"],
        "metro": draft.get("metro"),
    }


async def run_once(dry_run: bool = False, max_tasks: int = 3) -> Dict:
    """
    Main entry point: query for available scout tasks, process them.
    Returns summary dict.
    """
    results = {"claimed": 0, "completed": 0, "failed": 0}

    try:
        # Claim 'To-Do' scout tasks (using RPC for atomicity)
        r = _sb.rpc("claim_next_task", {
            "p_agent_name": "mesh.outreach",
            "p_task_types": ["scout.find_roofs"],
        }).execute()

        tasks_processed = 0
        while r.data and tasks_processed < max_tasks:
            task = r.data
            task["payload"] = json.loads(task.get("payload", "{}")) if isinstance(task.get("payload"), str) else task.get("payload", {})
            results["claimed"] += 1

            result = await process_task(task, dry_run=dry_run)
            if result.get("status") == "done":
                results["completed"] += 1
            else:
                results["failed"] += 1

            tasks_processed += 1

            # Try to claim next task
            if tasks_processed < max_tasks:
                r = _sb.rpc("claim_next_task", {
                    "p_agent_name": "mesh.outreach",
                    "p_task_types": ["scout.find_roofs"],
                }).execute()
            else:
                break

    except Exception as e:
        log.error(f"[outreach] run_once error: {e}")
        results["error"] = str(e)

    log.info(f"[outreach] run complete: {results}")
    return results


async def run_loop(interval_sec: int = 60):
    """Run the outreach agent in a background loop."""
    log.info(f"[outreach] starting background loop (interval={interval_sec}s)")
    while True:
        try:
            results = await run_once()
            log.info(f"[outreach] cycle: {results}")
        except Exception as e:
            log.error(f"[outreach] cycle error: {e}")
        await asyncio.sleep(interval_sec)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    if "--loop" in sys.argv:
        asyncio.run(run_loop())
    else:
        results = asyncio.run(run_once(dry_run=dry))
        print(json.dumps(results, indent=2))
