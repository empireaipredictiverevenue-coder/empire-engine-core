import os, time, importlib, traceback
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("/root/.env", override=True)
os.chdir("/root/empire-v49")
import signal
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler('/var/log/empire.log'), logging.StreamHandler()]
)

_shutdown = False
def _handle_signal(signum, frame):
    global _shutdown
    print(f"[ORCHESTRATOR] Signal {signum} received, shutting down cleanly...")
    _shutdown = True

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

AGENTS = ["storm_predictor", "corridor_agent", "overseer", "contractor_sniper"]  # reddit_pulse parked (needs dev account)

def log_registry(agent, status, error=None):
    try:
        sb.table("agent_registry").upsert({
            "agent_name": agent,
            "status": status,
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True
        }, on_conflict="agent_name").execute()
        if error:
            print(f"[ORCHESTRATOR] {agent} error logged: {error}")
    except Exception as e:
        print(f"[ORCHESTRATOR] Registry write failed: {e}")

def run_agent(name):
    try:
        print(f"[ORCHESTRATOR] Starting {name}...")
        log_registry(name, "ACTIVE")
        mod = importlib.import_module(f"bots.{name}")
        mod.run()
    except Exception as e:
        log_registry(name, "ERROR")
        print(f"[ORCHESTRATOR] {name} crashed: {traceback.format_exc()}")

if __name__ == "__main__":
    import threading
    print("[ORCHESTRATOR] Empire AI agent mesh starting...")
    threads = []
    for agent in AGENTS:
        t = threading.Thread(target=run_agent, args=(agent,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(2)
    for t in threads:
        t.join()
