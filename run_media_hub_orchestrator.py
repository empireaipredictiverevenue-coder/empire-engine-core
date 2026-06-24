#!/usr/bin/env python3
"""PM2 daemon wrapper for media-hub-orchestrator.

Polls the orchestrator for pipeline runs on MEDIA_HUB_POLL_SEC interval.
Ensures the project root is on sys.path so that `products` imports resolve.
"""
import sys, os, time, asyncio, json

# ── Ensure project root on sys.path ──────────────────────────────────
sys.path.insert(0, "/root/empire-v49")

POLL_SEC = int(os.getenv("MEDIA_HUB_POLL_SEC", "30"))


async def _poll_once():
    """Run one orchestrator cycle: check status + pipelines."""
    try:
        from products.media_automation_hub.orchestrator import get_orchestrator
        orch = get_orchestrator()
        status = orch.status()
        print(json.dumps(status, indent=2, default=str))
    except Exception as e:
        print(f"[media-hub-orchestrator] poll error: {e}")


async def _main_loop():
    """Continuous polling loop."""
    print(f"[media-hub-orchestrator] started (poll={POLL_SEC}s)")
    while True:
        await _poll_once()
        await asyncio.sleep(POLL_SEC)


if __name__ == "__main__":
    asyncio.run(_main_loop())
