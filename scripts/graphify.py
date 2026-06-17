#!/usr/bin/env python3
"""
EMPIRE V49 · ARCHITECTURE GRAPhIFY
====================================
Scans the empire-v49 codebase and generates a concise architecture digest
that agents (operator, predictive-revenue coder, etc.) can consume for
context about the system's structure, services, and relationships.

Usage:
    python3 scripts/graphify.py                    # full digest → stdout
    python3 scripts/graphify.py --json             # JSON output
    python3 scripts/graphify.py --format compact   # one-line summary
    python3 scripts/graphify.py --section agents   # just agent registry
"""

import os
import re
import sys
import json
import ast
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from collections import defaultdict
from typing import Any

REPO = Path(__file__).resolve().parent.parent


# ── Scanners ──────────────────────────────────────────────────────────

def _module_docstring(path: Path) -> str:
    """Extract the first line of a module's docstring."""
    try:
        with open(path) as f:
            tree = ast.parse(f.read())
        if tree.body and isinstance(tree.body[0], ast.Expr) and hasattr(tree.body[0], 'value'):
            if isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
                return tree.body[0].value.value.strip().split('\n')[0][:120]
    except Exception:
        pass
    return ""


def scan_top_level_modules() -> list[dict]:
    """Scan empire_*.py files in the repo root — the core domain modules."""
    modules = []
    for f in sorted(REPO.glob("empire_*.py")):
        doc = _module_docstring(f)
        name = f.stem
        modules.append({
            "name": name,
            "doc": doc or _infer_domain(name),
            "path": str(f.relative_to(REPO)),
        })
    return modules


def _infer_domain(name: str) -> str:
    """Simple heuristic: derive a human-readable domain from the module name."""
    lookup = {
        "empire_si_core": "SI core engine",
        "empire_brain": "LLM brain router",
        "empire_hub": "main FastAPI hub",
        "empire_matching": "lead-contractor matching",
        "empire_contractors": "contractor management",
        "empire_payouts": "payout settlement",
        "empire_compliance": "compliance checks",
        "empire_auth": "authentication",
        "empire_analytics": "analytics engine",
        "empire_sms": "SMS dispatch",
        "empire_voice": "voice call dispatch",
        "empire_email": "email dispatch",
        "empire_ppc": "PPC ad management",
        "empire_inbound": "inbound lead routing",
        "empire_outbound_dialer": "outbound call dialer",
        "empire_affiliate": "affiliate system",
        "empire_pricing": "pricing engine",
        "empire_tokens": "token/credit system",
        "empire_fee": "fee operator",
        "empire_revenue": "revenue tracking",
        "empire_bridge": "bridge (agent-router)",
        "empire_state_manager": "state persistence",
        "empire_brain_personality": "personality engine",
        "empire_brain_memory": "memory system",
        "empire_brain_learning": "learning module",
        "empire_sdr_agent": "SDR outbound agent",
        "empire_closing_agent": "closing/conversion agent",
        "empire_support_agent": "support agent",
        "empire_sales_agent": "sales agent",
        "empire_strategist": "strategic planner",
        "empire_reconnaissance": "market recon agent",
        "empire_competitor_intel": "competitor intel",
    }
    for key, val in lookup.items():
        if key in name:
            return val
    return ""


def scan_bots() -> list[dict]:
    """Scan bots/*.py — the fleet agents."""
    bots = []
    for f in sorted(REPO.glob("bots/*.py")):
        if f.name.startswith("_"):
            continue
        doc = _module_docstring(f)
        name = f.stem
        bots.append({
            "name": name,
            "doc": doc or "",
            "path": str(f.relative_to(REPO)),
        })
    return bots


def scan_pm2_services() -> list[dict]:
    """Parse ecosystem.config.js for PM2-managed services."""
    services = []
    eco_path = REPO / "ecosystem.config.js"
    if not eco_path.exists():
        return services
    try:
        content = eco_path.read_text()
        # Simple regex to extract PM2 service blocks
        pat = re.compile(r"name:\s*'([^']+)'[^}]*script:\s*'([^']+)'", re.DOTALL)
        for m in pat.finditer(content):
            services.append({"name": m.group(1), "script": m.group(2)})
    except Exception:
        pass
    return services


def scan_database_tables() -> list[str]:
    """Extract CREATE TABLE statements from migrations/*.sql."""
    tables = set()
    for f in sorted(REPO.glob("migrations/*.sql")):
        try:
            content = f.read_text()
            for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", content, re.I):
                tables.add(m.group(1))
        except Exception:
            pass
    return sorted(tables)


def scan_entry_points() -> list[dict]:
    """Identify main entry points (uvicorn, PM2 scripts, main loops)."""
    entries = [
        {"name": "hub.py", "type": "uvicorn/FastAPI", "port": 8000, "desc": "Main Empire API hub"},
        {"name": "main.py", "type": "background loop", "desc": "Fleet orchestrator (threaded agents)"},
        {"name": "agent_orchestrator.py", "type": "uvicorn/FastAPI", "port": 8042, "desc": "Agent mesh router"},
        {"name": "hook_analytics.py", "type": "uvicorn/FastAPI", "port": 8046, "desc": "Analytics event router"},
        {"name": "synthetic_brain.py", "type": "uvicorn/FastAPI", "port": 8005, "desc": "LLM brain endpoint"},
        {"name": "dashboard_api.py", "type": "FastAPI (in hub)", "desc": "Dashboard REST API"},
    ]
    return entries


def scan_agents_index() -> list[dict]:
    """Parse agents_INDEX.md if it exists, otherwise return empty."""
    idx_path = REPO / "agents_INDEX.md"
    if not idx_path.exists():
        return []
    agents = []
    try:
        content = idx_path.read_text()
        for line in content.splitlines():
            m = re.match(r"\|?\s*`(\w+)`\s*\|?\s*(.+)", line)
            if m:
                agents.append({"name": m.group(1), "desc": m.group(2).strip()[:100]})
    except Exception:
        pass
    return agents


def scan_hub_routes() -> list[dict]:
    """Scan hub.py for @app routes and /api/v1/ endpoints."""
    routes = []
    hub_path = REPO / "hub.py"
    if not hub_path.exists():
        return routes
    try:
        content = hub_path.read_text()
        for m in re.finditer(r'@(?:router|app)\.(get|post|put|delete|patch)\s*\([\"\']([^\"\']+)[\"\']', content):
            routes.append({"method": m.group(1).upper(), "path": m.group(2)})
    except Exception:
        pass
    return routes


def scan_agencies() -> list[dict]:
    """Scan agents/ subdirectory for modular agents."""
    agencies = []
    for f in sorted((REPO / "agents").glob("*.py")):
        if f.name.startswith("_"):
            continue
        doc = _module_docstring(f)
        agencies.append({
            "name": f.stem,
            "doc": doc or "",
            "path": f"agents/{f.name}",
        })
    return agencies


# ── Aggregation ───────────────────────────────────────────────────────

def build_graph() -> dict[str, Any]:
    """Assemble the full architecture graph."""
    return {
        "project": "empire-v49",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_py_files": len(list(REPO.rglob("*.py"))),
            "top_level_modules": len(list(REPO.glob("empire_*.py"))),
            "bots": len(list(REPO.glob("bots/*.py"))),
            "migrations": len(list(REPO.glob("migrations/*.sql"))),
            "tests": len(list(REPO.glob("tests/test_*.py"))),
            "scripts": len(list(REPO.glob("scripts/*.py"))),
        },
        "entry_points": scan_entry_points(),
        "pm2_services": scan_pm2_services(),
        "database_tables": scan_database_tables(),
        "hub_routes": scan_hub_routes(),
        "agents": {
            "index": scan_agents_index(),
            "bots": scan_bots(),
        },
        "modules": scan_top_level_modules(),
    }


# ── Formatting ────────────────────────────────────────────────────────

def format_compact(graph: dict) -> str:
    """One-line summary."""
    s = graph["summary"]
    return (
        f"empire-v49: {s['total_py_files']} .py files, {s['top_level_modules']} core modules, "
        f"{s['bots']} bots, {s['migrations']} migrations, {s['tests']} tests, "
        f"{s['scripts']} scripts, {len(graph['pm2_services'])} PM2 services, "
        f"{len(graph['database_tables'])} DB tables"
    )


def format_section(graph: dict, section: str) -> str:
    """Output just one section."""
    if section == "compact":
        return format_compact(graph)
    data = graph.get(section)
    if data is None:
        return f"Unknown section: {section}. Available: {', '.join(k for k in graph if k != 'project' and k != 'generated_at' and k != 'summary')}"
    return json.dumps(data, indent=2, default=str)


def format_text(graph: dict) -> str:
    """Human-readable architecture digest."""
    lines = []
    lines.append("╔══════════════════════════════════════════╗")
    lines.append("║  EMPIRE V49 · ARCHITECTURE DIGEST       ║")
    lines.append("╚══════════════════════════════════════════╝")
    lines.append("")

    s = graph["summary"]
    lines.append(f"Project: empire-v49  ({s['total_py_files']} .py files)")
    lines.append("")

    # Entry points
    lines.append("── Entry Points ──")
    for ep in graph["entry_points"]:
        port = f" :{ep['port']}" if ep.get("port") else ""
        lines.append(f"  {ep['name']}  {ep['type']}{port}  —  {ep['desc']}")
    lines.append("")

    # PM2 services
    lines.append("── PM2 Services ──")
    for svc in graph["pm2_services"]:
        lines.append(f"  {svc['name']}  →  {svc['script']}")
    lines.append("")

    # Core modules
    lines.append("── Core Modules ──")
    for m in graph["modules"]:
        doc = f" — {m['doc']}" if m["doc"] else ""
        lines.append(f"  {m['name']}{doc}")
    lines.append("")

    # Bots (agents)
    lines.append("── Bot Agents ──")
    for b in graph["agents"]["bots"]:
        doc = f" — {b['doc']}" if b["doc"] else ""
        lines.append(f"  {b['name']}{doc}")
    lines.append("")

    # DB tables
    lines.append("── Database Tables ({0}) ──".format(len(graph["database_tables"])))
    for tbl in graph["database_tables"]:
        lines.append(f"  {tbl}")
    lines.append("")

    # Hub routes
    lines.append("── API Routes ──")
    for r in graph["hub_routes"][:20]:
        lines.append(f"  {r['method']}  {r['path']}")
    if len(graph["hub_routes"]) > 20:
        lines.append(f"  ... and {len(graph['hub_routes']) - 20} more")
    lines.append("")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Empire V49 Architecture Graph")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--format", choices=["text", "compact", "json"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("--section", type=str, default=None,
                        help="Only output a specific section (e.g. agents, modules, pm2_services)")
    parser.add_argument("--save", type=str, default=None,
                        help="Save output to a file path")

    args = parser.parse_args()

    graph = build_graph()

    if args.section:
        output = format_section(graph, args.section)
    elif args.json or args.format == "json":
        output = json.dumps(graph, indent=2, default=str)
    elif args.format == "compact":
        output = format_compact(graph)
    else:
        output = format_text(graph)

    if args.save:
        Path(args.save).write_text(output)
        print(f"Graph saved to {args.save}")
    else:
        print(output)


if __name__ == "__main__":
    main()
