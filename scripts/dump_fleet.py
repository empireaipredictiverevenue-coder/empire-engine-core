"""Dump the canonical fleet: PM2 services + non-PM2 long-running processes.

Outputs a Markdown list ready to paste into AGENTS.md. Run from the box.
"""
import json, subprocess, os
from pathlib import Path

# 1. PM2 services
out = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=10)
pm2_data = json.loads(out.stdout)

print("## PM2 services (managed, restart with `pm2 restart <name>`)")
for p in pm2_data:
    env = p.get("pm2_env", {})
    name = p.get("name")
    pid = p.get("pid")
    status = env.get("status")
    pm_exec_path = env.get("pm_exec_path", "")
    args = env.get("args", [])
    cwd = env.get("cwd", "")
    args_str = " ".join(args[:5]) if args else ""
    print(f"  - **{name}** (pid {pid}, {status})")
    print(f"    exec: `{pm_exec_path} {args_str}`. cwd: `{cwd or '/root/empire-v49'}`")

# 2. Non-PM2 long-running processes (hermes gateway, dashboard, etc.)
print("\n## Non-PM2 long-running")
out = subprocess.run(["ps", "-eo", "pid,etime,cmd"], capture_output=True, text=True)
ps_lines = out.stdout.splitlines()
KNOWN = {
    "hermes gateway run": "Hermes gateway (Telegram poller)",
    "hermes dashboard": "Hermes dashboard (:9119)",
}
seen = set()
for line in ps_lines[1:]:
    parts = line.split(None, 2)
    if len(parts) < 3:
        continue
    pid, etime, cmd = parts
    if "hermes" not in cmd and "uvicorn" not in cmd:
        continue
    for sig, label in KNOWN.items():
        if sig in cmd and pid not in seen:
            print(f"  - **{label}** (pid {pid}, up {etime}) — `{cmd.strip()[:100]}`")
            seen.add(pid)
            break
