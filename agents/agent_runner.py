"""
EMPIRE V49 · AGENT RUNNER (LOOP MODE)
======================================
Runs all cron-driven agents as concurrent asyncio loops instead of
relying on OS cron jobs. Each agent manages its own interval internally.

Replaces crontab entries. Start via PM2:
    pm2 start agents/agent_runner.py --name agent-runner --interpreter python3

Or directly:
    python3 agents/agent_runner.py

Interval defaults (can be overridden per agent in agent_config.config_json):
  - storm_alert:            1800s (30 min)
  - storm_log_to_targets:   3600s (1 hour)
  - warp_scout:             7200s (2 hours)
  - billing_daily_digest:   86400s (24 hours)
  - prospector:             21600s (6 hours)
  - lead_scanner:           3600s (1 hour)
  - lead_enricher:          3600s (1 hour)
  - lead_converter:         1800s (30 min)
  - dispatch:               300s  (5 min)
  - prospector_bridge:      3600s (1 hour)
  - contractor_outreach:   14400s (4 hours)
  - retarget:              21600s (6 hours)
  - fee_watcher:            900s  (15 min)

Usage:
    python3 -m agents.agent_runner           # run all agents
    python3 -m agents.agent_runner --list     # show configured agents
    python3 -m agents.agent_runner --agent storm_alert  # run one agent in loop
"""

import os
import sys
import json
import asyncio
import signal
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Callable, Optional, List

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

log = logging.getLogger("empire.agent_runner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [agent-runner] %(levelname)s %(message)s",
)

# ── Agent registration ────────────────────────────────────────────────
# Each entry: (module_import_path, agent_name, default_interval_seconds)
# Import path is used to dynamically import the module.

AGENT_REGISTRY: List[Dict] = [
    # ── Storm pipeline ──
    {
        "module": "agents.storm_alert",
        "function": "run_loop",
        "agent_name": "storm_alert",
        "default_interval": 1800,      # 30 min
        "description": "NWS alert spatial matching → radar_targets",
    },
    {
        "module": "agents.storm_log_to_targets",
        "function": "run_loop",
        "agent_name": "storm_log_to_targets",
        "default_interval": 3600,      # 1 hour
        "description": "Storm risk log → radar_targets severity/urgency",
    },
    {
        "module": "agents.warp_scout",
        "function": "run_loop",
        "agent_name": "warp_scout",
        "default_interval": 7200,      # 2 hours
        "description": "NOAA storm prediction → storm_risk_log",
    },
    # ── Revenue / billing ──
    {
        "module": "agents_billing_daily",
        "function": "run_loop",
        "agent_name": "billing_daily_digest",
        "default_interval": 86400,     # 24 hours
        "description": "Daily billing digest → Telegram",
    },
    # ── Lead pipeline ──
    {
        "module": "agents.prospector",
        "function": "run_loop",
        "agent_name": "prospector",
        "default_interval": 21600,     # 6 hours
        "description": "Contractor prospect discovery via Google Places",
    },
    {
        "module": "agents.lead_scanner",
        "function": "run_loop",
        "agent_name": "lead_scanner",
        "default_interval": 3600,      # 1 hour
        "description": "Scan radar_targets → enriched_leads",
    },
    {
        "module": "agents.lead_enricher",
        "function": "run_loop",
        "agent_name": "lead_enricher",
        "default_interval": 3600,      # 1 hour
        "description": "Enrich leads with scoring + storm risk",
    },
    {
        "module": "agents.lead_converter",
        "function": "run_loop",
        "agent_name": "lead_converter",
        "default_interval": 1800,      # 30 min
        "description": "SMS outreach to qualified leads",
    },
    {
        "module": "agents.dispatch",
        "function": "run_loop",
        "agent_name": "dispatch",
        "default_interval": 300,       # 5 min
        "description": "Route YES replies to contractors",
    },
    # ── Contractor pipeline ──
    {
        "module": "agents.prospector_bridge",
        "function": "run_loop",
        "agent_name": "prospector_bridge",
        "default_interval": 3600,      # 1 hour
        "description": "Prospects → contractors bridge",
    },
    {
        "module": "agents.contractor_outreach",
        "function": "run_loop",
        "agent_name": "contractor_outreach",
        "default_interval": 14400,     # 4 hours
        "description": "Contractor re-engagement + winback",
    },
    {
        "module": "agents.retarget",
        "function": "run_loop",
        "agent_name": "retarget",
        "default_interval": 21600,     # 6 hours
        "description": "Retarget soft-reply leads with follow-up",
    },
    # ── Monitoring ──
    {
        "module": "agents.fee_watcher",
        "function": "run_loop",
        "agent_name": "fee_watcher",
        "default_interval": 900,       # 15 min
        "description": "Carrier claims → fee events",
    },
]

# ── Dynamic import helper ─────────────────────────────────────────────

def _import_module(module_path: str):
    """Dynamically import a module by dotted path."""
    return __import__(module_path, fromlist=["run_loop"])


def _get_interval_from_config(sb, agent_name: str, default: int) -> int:
    """Read interval_seconds from agent_config.config_json if set."""
    try:
        r = sb.table("agent_config").select("config_json").eq("agent_name", agent_name).limit(1).execute()
        if r.data:
            cfg = r.data[0].get("config_json") or {}
            return int(cfg.get("interval_seconds", default))
    except Exception:
        pass
    return default


# ── Agent loop runner ─────────────────────────────────────────────────

async def run_agent_loop(
    entry: Dict,
    interval_seconds: Optional[int] = None,
    name: Optional[str] = None,
):
    """Run one agent's run_once() in an infinite loop with the given interval.

    Reads interval from agent_config.config_json.interval_seconds at startup,
    then sleeps for that interval after each successful run.
    """
    module_path = entry["module"]
    fn_name = entry["function"]
    agent_name = entry.get("agent_name", module_path)
    default_interval = entry["default_interval"]
    display_name = name or agent_name

    # Import the module and get the run_loop / run_once function
    try:
        mod = _import_module(module_path)
        run_fn = getattr(mod, fn_name, None)
        run_once_fn = getattr(mod, "run_once", None)
    except Exception as e:
        log.error(f"[{display_name}] failed to import {module_path}: {e}")
        return

    if not run_fn and not run_once_fn:
        log.error(
            f"[{display_name}] module {module_path} has neither {fn_name}() "
            f"nor run_once() — skipping"
        )
        return

    if run_fn:
        # Module has a dedicated run_loop() — use it directly
        log.info(f"[{display_name}] using module's own {fn_name}()")
        try:
            await run_fn(interval_seconds=interval_seconds or default_interval)
        except Exception as e:
            log.error(f"[{display_name}] {fn_name}() exited: {e}")
        return

    # Fallback: use run_once() in a generic loop
    interval = interval_seconds or default_interval
    log.info(
        f"[{display_name}] starting loop (interval={interval}s = "
        f"{interval/3600 if interval >= 3600 else interval/60:.1f}h)"
    )

    while True:
        started = datetime.now(timezone.utc)
        try:
            result = run_once_fn()
            status = result.get("status", "?") if isinstance(result, dict) else "ok"
            log.info(
                f"[{display_name}] run completed: status={status} "
                f"({(datetime.now(timezone.utc) - started).total_seconds():.1f}s)"
            )
        except Exception as e:
            log.error(f"[{display_name}] run failed: {e}")

        # Sleep for the interval (adjust for run time)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        sleep_for = max(10, interval - elapsed)
        log.debug(f"[{display_name}] sleeping {sleep_for:.0f}s until next run")
        await asyncio.sleep(sleep_for)


# ── Main entry point ──────────────────────────────────────────────────

async def main_loop(agent_filter: Optional[List[str]] = None):
    """Start all registered agents as concurrent asyncio tasks."""
    agents_to_run = AGENT_REGISTRY
    if agent_filter:
        agents_to_run = [e for e in AGENT_REGISTRY if e["agent_name"] in agent_filter]
        if not agents_to_run:
            log.error(f"no agents matched filter: {agent_filter}")
            print(f"Available agents: {', '.join(e['agent_name'] for e in AGENT_REGISTRY)}")
            return

    log.info(f"starting {len(agents_to_run)} agent loop(s)...")
    tasks = []
    for entry in agents_to_run:
        task = asyncio.create_task(
            run_agent_loop(entry),
            name=entry["agent_name"],
        )
        tasks.append(task)

    # Wait for all tasks (they run forever, so this blocks)
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        log.info("agent runner cancelled — shutting down")
        for task in tasks:
            task.cancel()


def main():
    p = argparse.ArgumentParser(description="Empire AI Agent Runner (loop mode)")
    p.add_argument("--list", action="store_true", help="list registered agents")
    p.add_argument("--agent", action="append", dest="agents",
                   help="run specific agent(s) only (can be repeated)")
    args = p.parse_args()

    if args.list:
        print(f"{'Agent Name':30s} {'Interval':12s}  Description")
        print("-" * 80)
        for e in AGENT_REGISTRY:
            iv = e["default_interval"]
            iv_str = f"{iv}s" if iv < 3600 else f"{iv/3600:.0f}h" if iv % 3600 == 0 else f"{iv/3600:.1f}h"
            print(f"{e['agent_name']:30s} {iv_str:12s}  {e['description']}")
        print()
        print(f"Total: {len(AGENT_REGISTRY)} agents registered")
        return

    asyncio.run(main_loop(agent_filter=args.agents))


if __name__ == "__main__":
    main()
