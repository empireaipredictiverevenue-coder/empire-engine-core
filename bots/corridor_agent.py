"""
EMPIRE V49 - CORRIDOR AGENT (mesh-compatible wrapper)
=====================================================
Sync run() wrapper so the async corridor fits the agent mesh (main.py calls mod.run()).
Runs the corridor once per hour: demand -> brain copy -> footage -> render (when storm triggers).
Stands down cheaply when no storm. This is how the autonomous pipeline runs in the LIVE process.
"""
import sys, time, asyncio, traceback
sys.path.insert(0, "/root/empire-v49")

INTERVAL = 3600  # run corridor at most once per hour

def run():
    print("[CORRIDOR-AGENT] starting (hourly demand->creative pipeline)")
    while True:
        try:
            import corridor
            # live render when a storm triggers; corridor stands down if quiet
            asyncio.run(corridor.run_corridor("roofing", dry_run=False))
        except Exception:
            print(f"[CORRIDOR-AGENT] error: {traceback.format_exc()}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()