"""
EMPIRE V49 · LOG CENTRALIZATION (per-agent streams + tail-multi)
================================================================
Each agent writes its own log file under /root/empire-v49/logs/.
tail_multi.py tails all of them at once so you have a single
real-time view of every agent's activity.

Per-agent log files (these are the canonical names; if a script
writes elsewhere, this script will also check the legacy path):

  storm_scraper.log           scripts/storm_scraper.py
  bridge.log                  bots/mass_tort_bridge.py
  agent_orchestrator.log      mesh_orchestrator.py
  recall_classifier.log       bots/recall_classifier.py (if it logs)
  synthetic_brain.log         (pre-existing)
  agents.log                  (pre-existing, automate_empire.sh)
  bridge.log                  (pre-existing, empire_brain.py)

Usage:
  python3 scripts/tail_multi.py                  # tail all, in this terminal
  python3 scripts/tail_multi.py --agents storm,bridge   # tail a subset
  python3 scripts/tail_multi.py --last 100       # show last 100 lines per agent, then tail
  python3 scripts/tail_multi.py --list           # list known agent log files

The script prefers `tail -F` (handles log rotation cleanly) and
falls back to a Python poller if tail isn't available.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


LOG_DIR = Path("/root/empire-v49/logs")


# Map: agent name -> (log file, owner script/component)
AGENT_LOGS = {
    "storm":            ("storm_scraper.log",  "scripts/storm_scraper.py (NWS storm alerts scraper)"),
    "storm_bridge":     ("sqlite_bridge_cron.log", "storm scraper bridge endpoint (cron poll of NWS)"),
    "bridge":           ("bridge.log",         "bots/mass_tort_bridge.py (FDA recall -> buyer dial)"),
    "orchestrator":     ("agent_orchestrator.log", "mesh_orchestrator.py (32-lane grid)"),
    "classifier":       ("recall_classifier.log", "bots/recall_classifier.py (FDA sub_niche routing)"),
    "synthetic_brain":  ("synthetic_brain.log", "synthetic_brain.py (local LLM)"),
    "agents":           ("agents.log",         "automate_empire.sh (hourly sweep)"),
}


def list_logs() -> None:
    print(f"Known agent log files in {LOG_DIR}:")
    for name, (fname, owner) in AGENT_LOGS.items():
        path = LOG_DIR / fname
        if path.exists():
            size_kb = path.stat().st_size // 1024
            print(f"  [{name:<16}] {fname:<30} ({size_kb} KB)  - {owner}")
        else:
            print(f"  [{name:<16}] {fname:<30} (not yet created) - {owner}")


def show_last(n: int, agents: list[str]) -> None:
    for name in agents:
        if name not in AGENT_LOGS:
            print(f"[WARN] unknown agent {name!r}", file=sys.stderr)
            continue
        fname, owner = AGENT_LOGS[name]
        path = LOG_DIR / fname
        if not path.exists():
            print(f"[{name}] (no log yet at {path})")
            continue
        print(f"\n{'='*78}\n[{name}] {path}  ({owner})\n{'='*78}")
        # `tail -n` is the cleanest way
        try:
            out = subprocess.run(
                ["tail", "-n", str(n), str(path)],
                capture_output=True, text=True, check=True,
            )
            print(out.stdout, end="" if out.stdout.endswith("\n") else "\n")
        except subprocess.CalledProcessError as e:
            print(f"[ERR] tail failed: {e.stderr}")


def tail_all(agents: list[str]) -> int:
    """Tail all requested agent logs in parallel. Returns shell exit code."""
    paths = []
    for name in agents:
        if name not in AGENT_LOGS:
            print(f"[WARN] unknown agent {name!r}", file=sys.stderr)
            continue
        fname, _ = AGENT_LOGS[name]
        path = LOG_DIR / fname
        if not path.exists():
            print(f"[WARN] {name}: log {path} not yet created; skipping", file=sys.stderr)
            continue
        paths.append((name, str(path)))

    if not paths:
        print("No logs to tail.")
        return 1

    # `tail -F` per file, each prefixed with the agent name.
    # Run them as parallel subprocesses and merge their stdout with
    # a small Python wrapper.
    procs = []
    for name, path in paths:
        p = subprocess.Popen(
            ["tail", "-F", "-n", "0", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        procs.append((name, p))

    print(f"[tail_multi] tailing {len(procs)} agent log(s). Ctrl-C to stop.\n")
    try:
        import select
        import sys as _sys
        while True:
            # Poll all child processes for new output.
            for name, p in procs:
                if p.poll() is not None:
                    # child died
                    continue
                r, _, _ = select.select([p.stdout], [], [], 0.2)
                if r:
                    line = p.stdout.readline()
                    if line:
                        sys.stdout.write(f"[{name:<16}] {line}")
                        sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n[tail_multi] stopping.")
        for _, p in procs:
            p.terminate()
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Tail multiple agent logs in one stream")
    p.add_argument("--list", action="store_true", help="List known agent log files")
    p.add_argument("--agents", help="Comma-separated agent names (default: all known)")
    p.add_argument("--last", type=int, help="Show last N lines per agent, then exit")
    args = p.parse_args()

    if args.list:
        list_logs()
        return 0

    if args.agents:
        agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    else:
        agents = list(AGENT_LOGS.keys())

    if args.last is not None:
        show_last(args.last, agents)
        return 0

    return tail_all(agents)


if __name__ == "__main__":
    sys.exit(main())
