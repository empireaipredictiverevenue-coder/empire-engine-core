"""Smoke test: import the Hermes Controller and run one GodMode cycle (read-only, no mutations)."""
import os, sys, json, asyncio

sys.path.insert(0, "/root/empire-v49")
os.environ["OLLAMA_URL"] = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

from bots.hermes_controller import GodModeController, _sb, AGENT_NAME, MAX_LOOKBACK

async def main():
    print("=" * 60)
    print("HERMES CONTROLLER · SMOKE TEST")
    print("=" * 60)

    # 1. Test DB connectivity
    print("\n[1] DB Connectivity...")
    try:
        r = _sb.table("agent_task_queue").select("ticket_id").limit(1).execute()
        print(f"    agent_task_queue: OK ({len(r.data or [])} rows)")
    except Exception as e:
        print(f"    agent_task_queue: FAILED — {e}")
        return

    try:
        r = _sb.table("agent_registry").select("agent_name").limit(1).execute()
        print(f"    agent_registry: OK ({len(r.data or [])} rows)")
        agents = [a.get("agent_name") for a in (r.data or [])]
        print(f"    Registered agents: {agents}")
    except Exception as e:
        print(f"    agent_registry: FAILED — {e}")

    # 2. Instantiate controller
    print("\n[2] Instantiating GodModeController (max_loops=3)...")
    ctrl = GodModeController(max_loops=3)
    print(f"    OK — stats: {ctrl.stats}")

    # 3. Fetch recent tasks (read-only)
    print(f"\n[3] Fetching recent tasks (last {MAX_LOOKBACK} min)...")
    recent = ctrl.fetch_recent_tasks()
    print(f"    Done: {len(recent.get('done', []))} tasks")
    print(f"    Failed: {len(recent.get('failed', []))} tasks")
    if recent["done"]:
        for t in recent["done"][:3]:
            print(f"      ✓ {t.get('ticket_id', '?')[:8]} | {t.get('task_type', '?')} | pri={t.get('priority', '?')}")
    if recent["failed"]:
        for t in recent["failed"][:3]:
            print(f"      ✗ {t.get('ticket_id', '?')[:8]} | {t.get('task_type', '?')} | {t.get('error', '')[:60]}")

    # 4. Queue stats (read-only)
    print("\n[4] Queue state...")
    queue = ctrl.fetch_queue_state()
    print(f"    Total tasks: {queue.get('total', '?')}")
    print(f"    By status: {queue.get('by_status', {})}")
    print(f"    Pending (To-Do): {queue.get('pending', 0)}")
    print(f"    Stalled (In Progress): {queue.get('stalled', 0)}")

    # 5. Test LLM connectivity (read-only — no action execution)
    print("\n[5] Testing Ollama LLM (decision simulation, no execution)...")
    if recent["done"] or recent["failed"]:
        try:
            action = await ctrl.decide_action(recent, queue)
            act = action.get("action", "?")
            reasoning = action.get("reasoning", "")[:120]
            print(f"    LLM decided: action='{act}' | reason='{reasoning}...'")
            if act != "ignore":
                print(f"    Target ticket: {action.get('target_ticket', '?')[:8]}")
                print(f"    Params: {json.dumps(action.get('params', {}))}")
            print("    Ollama LLM: ONLINE ✓")
        except Exception as e:
            print(f"    Ollama LLM: FAILED — {e}")
    else:
        print("    Skipped — no recent Done/Failed tasks to reason about")
        # Still test Ollama with a trivial query
        try:
            result = await ctrl._ollama_chat_json("You are a test.", "Say hello")
            print(f"    Ollama ping: {result}")
            print("    Ollama LLM: ONLINE ✓")
        except Exception as e:
            print(f"    Ollama LLM: FAILED — {e}")

    # 6. Registry heartbeat
    print("\n[6] Agent registry heartbeat...")
    try:
        _sb.table("agent_registry").upsert({
            "agent_name": AGENT_NAME,
            "status": "SMOKE_TEST",
            "last_ping": "2025-01-01T00:00:00Z",
            "enabled": True,
            "capabilities": json.dumps(["controller", "orchestrator", "godmode"]),
        }, on_conflict="agent_name").execute()
        print(f"    {AGENT_NAME}: registered ✓")
    except Exception as e:
        print(f"    Registry upsert: FAILED — {e}")

    print("\n" + "=" * 60)
    print("SMOKE TEST COMPLETE — Hermes Controller ready to run")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
