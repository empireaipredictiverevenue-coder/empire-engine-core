"""
EMPIRE V49 · MESH STUDIO COPYWRITER (HERMES PROTOCOL · STUDIO TEAM A)
======================================================================
Drafts storm-based video reel scripts using local Ollama. Based on the
ugly banner strategy — short, punchy, direct-response ad copy.

Drops a 'studio.render_reel' ticket into the queue when the script is done,
which the Render Pro agent picks up to produce the final video.

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

log = logging.getLogger("mesh.studio.copy")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("AI_MODEL_DRAFT", "llama3.1:latest")

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Favorite metro targets for studio scripts
PRIMARY_METROS = ["Wichita", "Oklahoma City", "Kansas City", "Dallas-Fort Worth", "Houston", "Tulsa"]


async def query_ollama(prompt: str, system: str = "", temperature: float = 0.6) -> str:
    """Query local Ollama for script generation."""
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
                    "options": {"temperature": temperature, "num_predict": 512},
                },
            )
            if r.status_code == 200:
                return r.json().get("response", "")
    except Exception as e:
        log.error(f"[copywriter] Ollama call failed: {e}")
    return ""


async def write_reel_script(metro: str, niche: str = "roofing") -> Optional[Dict]:
    """
    Write a punchy reel script using Ollama.
    Returns dict with script, headline, and cta, or None on failure.
    """
    system_prompt = (
        "You write SHORT, punchy voiceover scripts for vertical social ad reels "
        "for a storm-damage roofing lead service. This is the 'ugly banner' strategy: "
        "direct, urgent, no fluff.\n\n"
        "Rules:\n"
        "- 25-40 words MAX. Spoken in ~7-9 seconds.\n"
        "- Hook in first 3 words.\n"
        "- Mention the city.\n"
        "- End with a call to action to 'tap the link below'.\n"
        "- Plain spoken English, no emojis, no hashtags, no stage directions.\n"
        "- NEVER include phone numbers, addresses, prices, or specific contact details.\n"
        "- Return ONLY JSON: {\"script\": \"text\", \"headline\": \"3-5 word urgent headline\", \"cta\": \"call to action\"}"
    )
    prompt = (
        f"City: {metro}. Service: {niche} (storm damage repair). "
        f"Write a punchy ugly-banner-style reel script. JSON only."
    )

    result = await query_ollama(prompt, system_prompt, temperature=0.7)
    if not result:
        log.warning(f"[copywriter] no response for {metro}")
        return None

    try:
        clean = result.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        script_data = json.loads(clean)

        script = script_data.get("script", "").strip()
        headline = script_data.get("headline", f"{metro.upper()} STORM DAMAGE?").strip()
        cta = script_data.get("cta", "Tap the link below for a free inspection.").strip()

        # Validate script length and safety
        import re
        if len(script.split()) > 60 or len(script) < 10:
            log.warning(f"[copywriter] script too long/short for {metro}, using default")
            script = f"Storm damage in {metro}? Get a free inspection from a local roofer. Tap the link below."
        if re.search(r"\d{3}[-.\s]?\d{3,4}", script) or re.search(r"\d{5,}", script):
            log.warning(f"[copywriter] phone number found in script for {metro}, sanitizing")
            script = f"Storm damage in {metro}? Tap the link for a free inspection."

        return {
            "script": script,
            "headline": headline.upper(),
            "cta": cta,
            "metro": metro,
            "niche": niche,
        }
    except (json.JSONDecodeError, IndexError) as e:
        log.warning(f"[copywriter] JSON parse error: {e}")
        return None


def _default_script_data(metro: str) -> Dict:
    """Return a safe default script when Ollama fails."""
    return {
        "script": f"Storm damage in {metro}? Get a free inspection from a local roofer. Tap the link below.",
        "headline": f"{metro.upper()} STORM DAMAGE?",
        "cta": "Tap the link below for a free inspection.",
        "metro": metro,
        "niche": "roofing",
    }


async def create_render_task(script_data: Dict, dry_run: bool = False) -> Optional[str]:
    """
    After writing the script, create a 'studio.render_reel' task in the queue
    for the Render Pro agent to pick up.
    """
    payload = {
        "metro": script_data.get("metro"),
        "niche": script_data.get("niche", "roofing"),
        "script": script_data.get("script"),
        "headline": script_data.get("headline"),
        "cta": script_data.get("cta"),
        "source": "mesh.copywriter",
    }

    if dry_run:
        log.info(f"[copywriter] DRY RUN: would create render task: {json.dumps(payload)[:200]}")
        return "dry-run"

    try:
        r = _sb.table("agent_task_queue").insert({
            "task_type": "studio.render_reel",
            "payload": json.dumps(payload),
            "status": "To-Do",
            "priority": 2,  # Render is higher priority
        }).execute()
        if r.data:
            ticket_id = r.data[0].get("ticket_id")
            log.info(f"[copywriter] created render task {ticket_id[:8]} for {script_data.get('metro')}")
            return ticket_id
    except Exception as e:
        log.error(f"[copywriter] task creation error: {e}")
    return None


async def run_once(metro: Optional[str] = None, dry_run: bool = False) -> Dict:
    """
    Main entry point: write a storm script and drop a render ticket.
    If no metro specified, writes for the highest-priority metro available.
    """
    metro = metro or PRIMARY_METROS[0]
    niche = "roofing"

    log.info(f"[copywriter] writing script for {metro} ({niche})...")

    # Write the script
    script_data = await write_reel_script(metro, niche)
    if not script_data:
        log.info(f"[copywriter] Ollama failed, using default script for {metro}")
        script_data = _default_script_data(metro)

    log.info(f"[copywriter] script: {script_data['script'][:80]}...")
    log.info(f"[copywriter] headline: {script_data['headline']}")

    # Create render task
    ticket_id = await create_render_task(script_data, dry_run=dry_run)

    return {
        "metro": metro,
        "niche": niche,
        "script": script_data["script"],
        "headline": script_data["headline"],
        "cta": script_data["cta"],
        "render_task_id": ticket_id,
        "status": "done" if ticket_id else "failed",
    }


async def run_loop(interval_sec: int = 1800):
    """Run the copywriter in a background loop. Default: every 30 min."""
    log.info(f"[copywriter] starting background loop (interval={interval_sec}s)")
    metro_index = 0
    while True:
        try:
            metro = PRIMARY_METROS[metro_index % len(PRIMARY_METROS)]
            results = await run_once(metro=metro)
            log.info(f"[copywriter] cycle: {results.get('status')} for {metro}")
            metro_index += 1
        except Exception as e:
            log.error(f"[copywriter] cycle error: {e}")
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
