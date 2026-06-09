"""
EMPIRE V49 - COPYWRITING AGENT
===============================
llama3.2:3b writes per-metro creative copy: reel scripts, banner headlines.
The brain where it BELONGS - creative generation (not templating/assembly).
Output feeds render_pro.py (script arg), ugly_banner.py, landing_generator.py.
Lane-agnostic. Falls back to safe defaults so it never blocks the pipeline.
"""
import os, sys, asyncio, logging
sys.path.insert(0, "/root/empire-v49")
from dotenv import load_dotenv
load_dotenv("/root/.env")
log = logging.getLogger("empire.copywriter")

def _default_reel_script(metro, niche="roofing"):
    return (f"Storm damage in {metro}? Do not call the first roofer who knocks. "
            f"Get a free inspection from a local roofer you can trust. Tap the link below.")

async def write_reel_script(metro, niche="roofing", state=""):
    """Brain writes a short punchy reel voiceover script for this metro."""
    try:
        from empire_ai_router import AIRouter
        from supabase import create_client
        db = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
        router = AIRouter(get_db=lambda: db)
        system = (
            "You write SHORT punchy voiceover scripts for vertical social ad reels for a "
            "storm-damage roofing lead service. Rules: 30-45 words MAX. Spoken in ~9 seconds. "
            "Hook in first 3 words. Mention the city. End with a call to action to tap/call. "
            "Plain spoken English, no emojis, no hashtags, no stage directions. "
            "NEVER include a phone number, address, price, or any specific contact detail - "
            "the viewer taps the on-screen link, so end with \"tap the link below\" not a number. "
            "Return ONLY JSON: {\"script\": \"the script text\"}"
        )
        st = (", " + state) if state else ""
        prompt = f"City: {metro}{st}. Service: {niche} (storm damage repair). Write the reel script. JSON only."
        result = await router.generate_json(prompt=prompt, task="copy.reel", system=system, temperature=0.7, max_tokens=150, context={"metro": metro, "niche": niche})
        if "_error" in result or not result.get("script"):
            log.warning("[copywriter] brain unavailable, default reel script")
            return _default_reel_script(metro, niche)
        script = str(result["script"]).strip()
        # safety: strip any hallucinated phone numbers / long digit sequences
        import re as _re
        if _re.search(r"\d{3}[-.\s]?\d{3,4}", script) or _re.search(r"\d{5,}", script):
            return _default_reel_script(metro, niche)
        if len(script.split()) > 60 or len(script) < 15:
            return _default_reel_script(metro, niche)
        return script
    except Exception as e:
        log.error(f"[copywriter] error: {e}")
        return _default_reel_script(metro, niche)

async def write_banner_headline(metro, niche="roofing"):
    """Brain writes a short high-impact banner headline. Falls back to default."""
    default = f"{metro.upper()} STORM DAMAGE?"
    try:
        from empire_ai_router import AIRouter
        from supabase import create_client
        db = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
        router = AIRouter(get_db=lambda: db)
        system = (
            "You write ULTRA-SHORT ad banner headlines (3-5 words). "
            "For storm-damage roofing. Must include the city. Urgent, plain. "
            "Return ONLY JSON: {\"headline\": \"text\"}"
        )
        prompt = f"City: {metro}. Write the banner headline. JSON only."
        result = await router.generate_json(prompt=prompt, task="copy.banner", system=system, temperature=0.7, max_tokens=50, context={"metro": metro})
        if "_error" in result or not result.get("headline"):
            return default
        h = str(result["headline"]).strip().upper()
        if len(h.split()) > 7 or len(h) < 5:
            return default
        return h
    except Exception as e:
        log.error(f"[copywriter] banner error: {e}")
        return default

if __name__ == "__main__":
    metro = sys.argv[1] if len(sys.argv) > 1 else "Wichita"
    async def _demo():
        print(f"=== COPYWRITER: {metro} ===")
        s = await write_reel_script(metro, "roofing")
        print(f"REEL SCRIPT ({len(s.split())} words): {s}")
        h = await write_banner_headline(metro, "roofing")
        print(f"BANNER HEADLINE: {h}")
    asyncio.run(_demo())