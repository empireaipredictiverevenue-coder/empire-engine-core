"""
EMPIRE V49 - CORRIDOR (wired: demand -> brain copy -> curated footage -> render)
"""
import os, sys, subprocess, asyncio
from bots import demand_intelligence as di
from bots import copywriter
# curated_footage lives in the media engine dir
sys.path.insert(0, "/root/empire_media_engine")
import curated_footage

MEDIA_ENGINE_DIR = "/root/empire_media_engine"
RENDER_SCRIPT = "render_pro.py"
DEFAULT_BG = "templates/videos/pexels_test.mp4"

async def run_corridor(lane_key="roofing", dry_run=True):
    # 1. BRAIN DECISION (demand intelligence: where to deploy)
    result = await di.run_lane(lane_key)
    if not result or not result.get("decision"):
        print("[CORRIDOR] no decision -> stand down")
        return
    deploy_list = result["decision"].get("deploy") or []
    top_metro = deploy_list[0] if deploy_list else None
    if not top_metro:
        print("[CORRIDOR] no triggered demand -> stand down")
        return

    # 2. BRAIN WRITES THE SCRIPT (copywriter), CURATED FOOTAGE PICKED
    try:
        dynamic_script = await copywriter.write_reel_script(top_metro, "roofing")
    except Exception as e:
        print(f"[CORRIDOR] copywriter fallback ({e})")
        dynamic_script = f"Storm damage in {top_metro}? Get a free inspection from a local roofer you can trust. Tap the link below."
    print(f"[CORRIDOR] Script for {top_metro}: {dynamic_script}")

    try:
        bg_path, footage_term = curated_footage.get_storm_footage()
        bg_arg = bg_path.replace(MEDIA_ENGINE_DIR + "/", "")
        print(f"[CORRIDOR] Footage: {footage_term} -> {bg_arg}")
    except Exception as e:
        print(f"[CORRIDOR] footage fallback ({e})")
        bg_arg = DEFAULT_BG

    print(f"[CORRIDOR] Generating media for {top_metro}...")
    if dry_run:
        print(f"[DRY RUN] Would run: python3 {RENDER_SCRIPT} {bg_arg} \x27{dynamic_script}\x27")
    else:
        proc = subprocess.run(["python3", RENDER_SCRIPT, bg_arg, dynamic_script],
                              capture_output=True, text=True, cwd=MEDIA_ENGINE_DIR)
        print(f"[CORRIDOR] Render status: {proc.returncode}")
        if proc.returncode != 0:
            print(f"[CORRIDOR] Render error tail: {(proc.stderr or chr(34)+chr(34))[-300:]}")
        else:
            print(f"[CORRIDOR] Reel rendered for {top_metro}. Output in builds/reel_test.mp4")

if __name__ == "__main__":
    lane = sys.argv[1] if len(sys.argv) > 1 else "roofing"
    live = "--live" in sys.argv
    asyncio.run(run_corridor(lane, dry_run=not live))