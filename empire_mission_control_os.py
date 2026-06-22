"""
EMPIRE V49 · AGENT OS MISSION CONTROL
=======================================
Unified bridge between system metrics (empire_mission_control), agent OS kernel
(empire_agent_os), skills registry, and autoresearch loops.

Provides:
  - agent_os_mission_snapshot() — unified snapshot combining all subsystems
  - agent_os_health() — traffic-light health per agent OS
  - agent_os_anomaly_detection() — cross-system anomaly correlation
  - agent_os_autoresearch_status() — autoresearch loop status from scratchpad
  - register_mission_control_os_routes() — FastAPI routes for /api/mc-os/*
  - mission_control_os_broadcast_loop() — WebSocket broadcast every 5s
"""

import os
import re
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

# FastAPI is optional — used by register_mission_control_os_routes and
# create_standalone_app. Import here for type annotations; the actual
# registration functions handle ImportError gracefully.
try:
    from fastapi import FastAPI
except ImportError:
    FastAPI = None  # type: ignore

log = logging.getLogger("empire.mission_control_os")

# ── Paths ───────────────────────────────────────────────────────────────
AGENT_OS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_os")
AUTORESEARCH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integrations", "autoresearch")
SCRATCHPAD_PATH = os.path.join(AUTORESEARCH_DIR, "scratchpad.md")

# ── Cache ───────────────────────────────────────────────────────────────
_SNAPSHOT_CACHE: dict = {"_payload": None, "_cached_at": 0.0}
_SNAPSHOT_TTL = 5.0
_SKILLS_CACHE: dict = {"_payload": None, "_cached_at": 0.0}
_SKILLS_TTL = 30.0

# ── Log once sentinel ──────────────────────────────────────────────────
_SKILLS_WARNED: bool = False

# ── Qdrant cache ────────────────────────────────────────────────────────
_QDRANT_STATUS_CACHE: dict = {"_payload": None, "_cached_at": 0.0}
_QDRANT_TTL = 60.0


def _get_qdrant_status() -> dict:
    """Check Qdrant connectivity and get skill collection stats.

    Cached for 60s. Returns a lightweight status dict without doing
    a full vector search — just pings the collection.
    """
    import time as _t
    now_epoch = _t.time()
    cached = _QDRANT_STATUS_CACHE.get("_payload")
    cached_at = _QDRANT_STATUS_CACHE.get("_cached_at", 0.0)
    if cached and (now_epoch - cached_at) < _QDRANT_TTL:
        return cached

    result = {
        "available": False,
        "skills_indexed": 0,
        "error": None,
    }

    try:
        from integrations.qdrant import get_client
        client = get_client()
        if client is None:
            result["error"] = "client_not_initialized"
        else:
            # Quick connectivity check via collection listing
            collections = client.get_collections()
            col_names = [c.name for c in collections.collections]
            result["available"] = "skills" in col_names
            if result["available"]:
                try:
                    info = client.get_collection(collection_name="skills")
                    result["skills_indexed"] = info.points_count or 0
                except Exception:
                    pass
    except ImportError:
        result["error"] = "qdrant_client_not_installed"
    except Exception as e:
        result["error"] = str(e)[:100]

    _QDRANT_STATUS_CACHE["_payload"] = result
    _QDRANT_STATUS_CACHE["_cached_at"] = now_epoch
    return result


# ═════════════════════════════════════════════════════════════════════════
# AGENT OS DISCOVERY
# ═════════════════════════════════════════════════════════════════════════

def discover_agent_os_instances() -> list[dict]:
    """Discover all agent OS instances from the agent_os/ directory.

    Each instance has SOUL.md, SKILLS.md, and knowledge/.
    Returns list of dicts with id, path, name, soul_summary, skill_count.
    """
    instances = []
    if not os.path.isdir(AGENT_OS_DIR):
        return instances

    for name in sorted(os.listdir(AGENT_OS_DIR)):
        os_path = os.path.join(AGENT_OS_DIR, name)
        if not os.path.isdir(os_path):
            continue

        soul_path = os.path.join(os_path, "SOUL.md")
        skills_path = os.path.join(os_path, "SKILLS.md")
        knowledge_path = os.path.join(os_path, "knowledge")

        soul_summary = ""
        if os.path.exists(soul_path):
            try:
                with open(soul_path) as f:
                    content = f.read(2000)
                # Extract the identity line
                for line in content.split("\n"):
                    if line.startswith("I am") or "I am the" in line:
                        soul_summary = line.strip()
                        break
                if not soul_summary:
                    soul_summary = content.split("\n")[0] if content else ""
            except Exception:
                soul_summary = "unreadable"

        skill_count = 0
        skill_names = []
        if os.path.exists(skills_path):
            try:
                with open(skills_path) as f:
                    content = f.read()
                # Count registered skills (lines like "### 1. `skill.name`")
                for match in re.finditer(r"###\s+\d+\.\s+`(.+?)`", content):
                    skill_names.append(match.group(1))
                skill_count = len(skill_names)
            except Exception:
                pass

        knowledge_count = 0
        if os.path.isdir(knowledge_path):
            try:
                knowledge_count = len([f for f in os.listdir(knowledge_path) if f.endswith(".md")])
            except Exception:
                pass

        instances.append({
            "id": name,
            "path": os_path,
            "name": name.replace("_os", "").replace("_", " ").title(),
            "soul_summary": soul_summary[:200],
            "skill_count": skill_count,
            "skill_names": skill_names[:10],
            "knowledge_count": knowledge_count,
            "has_soul": os.path.exists(soul_path),
            "has_skills": os.path.exists(skills_path),
        })

    return instances


# ═════════════════════════════════════════════════════════════════════════
# SYSTEM METRICS BRIDGE
# ═════════════════════════════════════════════════════════════════════════

def _get_mission_control_snapshot(get_db=None, broadcaster=None) -> dict:
    """Bridge to empire_mission_control's mission_control_snapshot()."""
    try:
        from empire_mission_control import mission_control_snapshot
        return mission_control_snapshot(get_db=get_db, broadcaster=broadcaster) or {}
    except Exception as e:
        log.debug(f"[mc-os] mission_control_snapshot unavailable: {e}")
        return {}


def _get_agent_os_snapshot(kernel=None) -> dict:
    """Bridge to empire_agent_os's AgentKernel snapshot()."""
    if kernel is None:
        return {"kernel": None, "processes": {}, "ipc": {}, "capabilities": {}}
    try:
        return kernel.snapshot() if hasattr(kernel, "snapshot") else {}
    except Exception as e:
        log.debug(f"[mc-os] agent_os snapshot unavailable: {e}")
        return {}


def _get_skills_snapshot() -> dict:
    """Bridge to the skills registry. Cached for 30s to avoid re-creating
    the registry on every API call."""
    import time as _t
    now_epoch = _t.time()
    cached = _SKILLS_CACHE.get("_payload")
    cached_at = _SKILLS_CACHE.get("_cached_at", 0.0)
    if cached and (now_epoch - cached_at) < _SKILLS_TTL:
        return cached

    global _SKILLS_WARNED
    try:
        from skills import ImmutableSkillRegistry, VaultSkillDiscoverer
        from skills.marketing_skills import get_marketing_skill_names
        registry = ImmutableSkillRegistry()
        discoverer = VaultSkillDiscoverer(registry)
        vault_result = discoverer.scan_and_register()

        # Don't re-register marketing skills here to avoid side effects
        marketing_names = get_marketing_skill_names()
        snapshot = registry.snapshot()

        # Check Qdrant vector search availability
        qdrant_status = _get_qdrant_status()

        result = {
            "total_skills": snapshot.get("total_skills", 0),
            "vault_skills": vault_result.get("skills", []),
            "marketing_skills": marketing_names,
            "all_skills": list(snapshot.get("skills", {}).keys()),
            "vector_search": {
                "available": qdrant_status["available"],
                "skills_indexed": qdrant_status["skills_indexed"],
                "error": qdrant_status["error"],
                "provider": "qdrant",
            },
        }

        _SKILLS_CACHE["_payload"] = result
        _SKILLS_CACHE["_cached_at"] = now_epoch
        _SKILLS_WARNED = False
        return result
    except Exception as e:
        if not _SKILLS_WARNED:
            log.warning(f"[mc-os] skills snapshot unavailable: {e}")
            _SKILLS_WARNED = True
        return {
            "total_skills": 0, "vault_skills": [], "marketing_skills": [],
            "all_skills": [], "vector_search": {
                "available": False, "skills_indexed": 0,
                "error": str(e)[:100], "provider": "qdrant",
            },
        }


def _get_autoresearch_status() -> dict:
    """Read scratchpad.md for autoresearch loop status."""
    if not os.path.exists(SCRATCHPAD_PATH):
        return {"status": "no_scratchpad", "targets": []}

    try:
        with open(SCRATCHPAD_PATH) as f:
            content = f.read()

        # Parse the system status table
        targets = []
        in_table = False
        for line in content.split("\n"):
            if line.startswith("| Target |"):
                in_table = True
                continue
            if in_table and line.startswith("|---"):
                continue
            if in_table and line.startswith("| ") and "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 6:
                    targets.append({
                        "name": parts[1] if len(parts) > 1 else "",
                        "dir": parts[2].strip("`") if len(parts) > 2 else "",
                        "description": parts[3] if len(parts) > 3 else "",
                        "latest_weighted": parts[4] if len(parts) > 4 else "",
                        "last_updated": parts[5] if len(parts) > 5 else "",
                    })
            if in_table and not line.startswith("|"):
                in_table = False

        return {"status": "active", "targets": targets, "scratchpad_length": len(content)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _get_agent_os_process_health(kernel=None) -> dict:
    """Get per-agent-OS health from the kernel's process manager."""
    health = {}
    if kernel is None:
        return health

    try:
        pm = kernel.processes
        snapshot = pm.snapshot() if hasattr(pm, "snapshot") else {}
        agents = snapshot.get("agents", {})

        for name, info in agents.items():
            status = info.get("status", "STOPPED")
            health[name] = {
                "status": status,
                "color": "green" if status == "RUNNING" else ("red" if status == "ERROR" else "amber"),
                "capabilities": info.get("capabilities", []),
                "interval": info.get("interval", 0),
                "retry_count": info.get("retry_count", 0),
            }

        return health
    except Exception:
        return {}


# ═════════════════════════════════════════════════════════════════════════
# ANOMALY DETECTION
# ═════════════════════════════════════════════════════════════════════════

def _detect_anomalies(system_snapshot: dict) -> list[dict]:
    """Cross-system anomaly detection based on correlation rules.

    Rules defined in agent_os/mission_control_os/knowledge/anomaly_rules.md
    """
    anomalies = []
    raw_mc = system_snapshot.get("mission_control", {})
    mc = raw_mc if isinstance(raw_mc, dict) else {}

    brain = mc.get("brain", {})
    agi = mc.get("agi", {})
    revenue = mc.get("revenue", {})
    compliance = mc.get("compliance", {})

    # Pattern 1: Funnel Blockage
    brain_no_go = brain.get("decisions_24h", 0)
    if brain_no_go > 5:
        anomalies.append({
            "pattern": "funnel_blockage",
            "severity": "amber",
            "message": f"Brain decisions 24h: {brain_no_go} — possible funnel blockage",
            "subsystem": "brain",
            "metrics": {"decisions_24h": brain_no_go},
        })

    # Pattern 2: Revenue Drop
    rev_24h = revenue.get("total_24h", 0)
    if rev_24h == 0 and revenue.get("calls_24h", 0) > 0:
        anomalies.append({
            "pattern": "revenue_drop",
            "severity": "amber",
            "message": "Revenue 24h is $0 with active calls — possible pipeline conversion failure",
            "subsystem": "revenue",
            "metrics": {"total_24h": rev_24h, "calls_24h": revenue.get("calls_24h")},
        })

    # Pattern 3: Stale Agents
    stale = agi.get("stale_count", 0)
    if stale > 3:
        anomalies.append({
            "pattern": "stale_agents",
            "severity": "red" if stale > 5 else "amber",
            "message": f"{stale} stale agents detected — possible kernel crash",
            "subsystem": "agi",
            "metrics": {"stale_count": stale, "healthy_count": agi.get("healthy_count", 0)},
        })

    # Pattern 4: Call Window
    if not compliance.get("call_window_open", True):
        anomalies.append({
            "pattern": "call_window_closed",
            "severity": "info",
            "message": f"Call window closed (local hour: {compliance.get('local_hour')})",
            "subsystem": "compliance",
            "metrics": {"local_hour": compliance.get("local_hour")},
        })

    # Pattern 5: AGI Status
    agi_status = agi.get("status", "UNKNOWN")
    if agi_status in ("HOLD", "MANUAL_HOLD"):
        anomalies.append({
            "pattern": "agi_hold",
            "severity": "amber",
            "message": f"AGI in {agi_status} state — strategies paused",
            "subsystem": "agi",
            "metrics": {"status": agi_status},
        })

    return anomalies


# ═════════════════════════════════════════════════════════════════════════
# UNIFIED SNAPSHOT
# ═════════════════════════════════════════════════════════════════════════

def agent_os_mission_snapshot(get_db=None, broadcaster=None, kernel=None) -> dict:
    """Assemble the unified Agent OS Mission Control snapshot.

    Combines:
      - System metrics (brain, AGI, revenue, compliance, network)
      - Agent OS instances (discovered from agent_os/)
      - Agent OS kernel state (processes, IPC, capabilities)
      - Skills registry (registered skills across all OS instances)
      - Autoresearch status (scratchpad.md)
      - Cross-system anomaly detection

    Returns dict suitable for JSON serialization and WebSocket broadcast.
    """
    import time as _t
    now_epoch = _t.time()
    cached = _SNAPSHOT_CACHE.get("_payload")
    cached_at = _SNAPSHOT_CACHE.get("_cached_at", 0.0)
    if cached and (now_epoch - cached_at) < _SNAPSHOT_TTL:
        return cached

    # Build snapshot from all sources
    mc = _get_mission_control_snapshot(get_db=get_db, broadcaster=broadcaster)
    agent_os_instances = discover_agent_os_instances()
    kernel_snap = _get_agent_os_snapshot(kernel=kernel)
    skills = _get_skills_snapshot()
    autoresearch = _get_autoresearch_status()
    process_health = _get_agent_os_process_health(kernel=kernel)

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    snap = {
        "ts": timestamp,
        "health": mc.get("health", "unknown"),
        "mission_control": mc,
        "agent_os": {
            "instances": agent_os_instances,
            "instance_count": len(agent_os_instances),
            "kernel": kernel_snap.get("kernel") or {
                "booted": False,
                "uptime_seconds": 0,
                "started_at": None,
            },
            "processes": process_health,
            "process_summary": {
                "total": kernel_snap.get("processes", {}).get("total_agents", 0),
                "running": kernel_snap.get("processes", {}).get("running", 0),
                "error": kernel_snap.get("processes", {}).get("error", 0),
                "stopped": kernel_snap.get("processes", {}).get("stopped", 0),
            },
            "ipc": {
                "total_events": kernel_snap.get("ipc", {}).get("total_events_tracked", 0),
                "recent": kernel_snap.get("ipc", {}).get("recent_events", [])[:10],
            },
            "capabilities": kernel_snap.get("capabilities", {}),
        },
        "skills": skills,
        "autoresearch": autoresearch,
        "anomalies": _detect_anomalies({"mission_control": mc}),
    }

    _SNAPSHOT_CACHE["_payload"] = snap
    _SNAPSHOT_CACHE["_cached_at"] = now_epoch
    return snap


# ═════════════════════════════════════════════════════════════════════════
# HEALTH
# ═════════════════════════════════════════════════════════════════════════

def agent_os_health(get_db=None, broadcaster=None, kernel=None) -> dict:
    """Get traffic-light health for all agent OS subsystems."""
    snap = agent_os_mission_snapshot(get_db=get_db, broadcaster=broadcaster, kernel=kernel)
    mc = snap.get("mission_control", {})

    return {
        "overall": snap.get("health", "unknown"),
        "brain": mc.get("brain", {}).get("up", False),
        "supabase": mc.get("brain", {}).get("supabase_up", False),
        "ollama": mc.get("brain", {}).get("up", False),
        "agi": mc.get("agi", {}).get("status", "UNKNOWN"),
        "revenue": mc.get("revenue", {}).get("health_status", "unknown"),
        "agent_kernel": snap.get("agent_os", {}).get("kernel", {}).get("booted", False),
        "anomalies": len(snap.get("anomalies", [])),
        "ts": snap.get("ts"),
    }


# ═════════════════════════════════════════════════════════════════════════
# AUTORESEARCH STATUS
# ═════════════════════════════════════════════════════════════════════════

def agent_os_autoresearch_status() -> dict:
    """Get parsed autoresearch loop status from scratchpad.md."""
    return _get_autoresearch_status()


# ═════════════════════════════════════════════════════════════════════════
# AGENT OS LANDING PAGE
# ═════════════════════════════════════════════════════════════════════════

def mission_control_os_page() -> str:
    """Return the Agent OS Mission Control landing page HTML.

    A self-contained dashboard showing:
      - Overall health status
      - All agent OS instances with their health
      - Skills registry summary
      - Autoresearch loop status
      - Live anomaly feed
    """
    return _MISSION_CONTROL_OS_HTML


# ═════════════════════════════════════════════════════════════════════════
# BROADCAST LOOP
# ═════════════════════════════════════════════════════════════════════════

async def mission_control_os_broadcast_loop(
    broadcaster=None,
    get_db=None,
    kernel=None,
    interval: float = 5.0,
):
    """Background task: emit `mission_control_os` event every `interval` seconds.

    Shares the same broadcaster as empire_mission_control so both snapshots
    flow through the same WebSocket connection.
    """
    log.info(f"[mc-os] broadcast loop started · {interval}s interval")
    while True:
        try:
            if broadcaster is not None:
                stats = getattr(broadcaster, "stats", {}) or {}
                clients = int(stats.get("connected", 0)) + int(stats.get("sse_connected", 0))
                if clients > 0:
                    snap = agent_os_mission_snapshot(get_db=get_db, broadcaster=broadcaster, kernel=kernel)
                    await broadcaster.broadcast({
                        "type": "mission_control_os",
                        **snap,
                    })
        except Exception as e:
            log.warning(f"[mc-os] broadcast error: {e}")
        await asyncio.sleep(interval)


# ═════════════════════════════════════════════════════════════════════════
# API ROUTES
# ═════════════════════════════════════════════════════════════════════════

def register_mission_control_os_routes(app, get_db=None, kernel=None):
    """Register Agent OS Mission Control REST API routes on a FastAPI app.

    Routes:
      GET /api/v1/mc-os/snapshot     — Full unified snapshot
      GET /api/v1/mc-os/health       — Traffic-light health summary
      GET /api/v1/mc-os/agent-os     — Agent OS instances list
      GET /api/v1/mc-os/autoresearch — Autoresearch loop status
      GET /api/v1/mc-os/skills       — Skills registry snapshot
      GET /api/v1/mc-os/anomalies    — Current anomalies
      GET /mc-os                     — Landing page (HTML)
    """
    try:
        from fastapi import Depends
    except ImportError:
        log.warning("[mc-os] fastapi not available — routes not registered")
        return

    if FastAPI is None:
        log.warning("[mc-os] FastAPI not importable — routes not registered")
        return

    require_dep = None
    try:
        from empire_auth import require_auth as _ra
        if callable(_ra):
            require_dep = _ra
    except Exception:
        pass

    @app.get("/api/v1/mc-os/snapshot")
    async def _mc_os_snapshot(auth=Depends(require_dep) if require_dep else None):
        return agent_os_mission_snapshot(get_db=get_db, kernel=kernel)

    @app.get("/api/v1/mc-os/health")
    async def _mc_os_health(auth=Depends(require_dep) if require_dep else None):
        return agent_os_health(get_db=get_db, kernel=kernel)

    @app.get("/api/v1/mc-os/agent-os")
    async def _mc_os_agent_os(auth=Depends(require_dep) if require_dep else None):
        instances = discover_agent_os_instances()
        return {"instances": instances, "count": len(instances)}

    @app.get("/api/v1/mc-os/autoresearch")
    async def _mc_os_autoresearch(auth=Depends(require_dep) if require_dep else None):
        return agent_os_autoresearch_status()

    @app.get("/api/v1/mc-os/skills")
    async def _mc_os_skills(auth=Depends(require_dep) if require_dep else None):
        return _get_skills_snapshot()

    @app.post("/api/v1/mc-os/skills/search")
    async def _mc_os_skills_search(body: dict, auth=Depends(require_dep) if require_dep else None):
        """Semantic skill search via Qdrant vector search.

        Body:
          query (str): Natural language search query (required)
          limit (int): Max results (default 10)
          score_threshold (float): Minimum similarity score (default 0.0)
          filter (dict): Optional payload filters

        Returns enriched results with registry metadata.
        """
        try:
            from integrations.qdrant import search_skills
            results = await search_skills(
                query=body.get("query", ""),
                limit=body.get("limit", 10),
                score_threshold=body.get("score_threshold"),
                filter_kwargs=body.get("filter"),
            )

            # Enrich results with registry metadata (tags, version, category)
            enriched = []
            try:
                from skills import ImmutableSkillRegistry
                reg = ImmutableSkillRegistry()
                reg_snap = reg.snapshot()
                reg_skills = reg_snap.get("skills", {})
                for r in results:
                    skill_name = (r.get("payload") or {}).get("skill_name", "")
                    if skill_name in reg_skills:
                        r["registry"] = reg_skills[skill_name]
                    enriched.append(r)
            except Exception:
                enriched = results

            return {"results": enriched, "query": body.get("query", ""), "count": len(enriched)}
        except ImportError:
            from fastapi import HTTPException
            raise HTTPException(status_code=501, detail="Qdrant integration not available")
        except Exception as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=502, detail=str(e)[:200])

    @app.get("/api/v1/mc-os/anomalies")
    async def _mc_os_anomalies(auth=Depends(require_dep) if require_dep else None):
        snap = agent_os_mission_snapshot(get_db=get_db, kernel=kernel)
        return {"anomalies": snap.get("anomalies", []), "count": len(snap.get("anomalies", []))}

    if require_dep is None:
        @app.get("/mc-os")
        async def _mc_os_page():
            from fastapi.responses import HTMLResponse
            return HTMLResponse(mission_control_os_page())

    log.info("[mc-os] routes registered: /api/v1/mc-os/*")


# ═════════════════════════════════════════════════════════════════════════
# LANDING PAGE HTML
# ═════════════════════════════════════════════════════════════════════════

_MISSION_CONTROL_OS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Mission Control · Agent OS</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
:root {
  --bg: #030812;
  --surface: #0B1729;
  --elevated: #11243F;
  --border: rgba(122,140,163,0.15);
  --text: #F0F4F8;
  --text-sec: #94A3B8;
  --text-muted: #4A5A72;
  --accent: #44E5B8;
  --accent-dim: rgba(68,229,184,0.08);
  --blue: #5AC8FA;
  --amber: #F59E0B;
  --red: #F43F5E;
  --font-mono: 'SF Mono','Fira Code','JetBrains Mono',monospace;
  --font-display: 'Geist','Inter',system-ui,sans-serif;
}
html,body { height:100%; background:var(--bg); color:var(--text); font-family:var(--font-display); }
body { display:flex; flex-direction:column; }

/* TOP BAR */
.topbar {
  display:flex; align-items:center; justify-content:space-between;
  padding:10px 24px; border-bottom:1px solid var(--border);
  background:var(--surface); flex-shrink:0;
}
.topbar-left { display:flex; align-items:center; gap:10px; }
.topbar-dot {
  width:8px; height:8px; border-radius:50%; background:var(--accent);
  animation:pulse 1.6s ease-in-out infinite;
}
@keyframes pulse {
  0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(68,229,184,0.4)}
  50%{opacity:.6;box-shadow:0 0 0 8px rgba(68,229,184,0)}
}
.topbar-title { font-family:var(--font-mono); font-size:10px; letter-spacing:.18em; text-transform:uppercase; color:var(--accent); }
.topbar-stats { display:flex; gap:16px; font-family:var(--font-mono); font-size:9px; color:var(--text-muted); }
.stat { display:flex; align-items:center; gap:4px; }
.stat strong { color:var(--text-sec); font-weight:500; }

/* GRID */
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:12px; padding:16px 24px; flex:1; overflow-y:auto; }

/* CARD */
.card {
  background:var(--surface); border:1px solid var(--border);
  padding:14px 16px; transition:border-color .2s;
}
.card:hover { border-color:rgba(122,140,163,0.3); }
.card-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }
.card-title { font-family:var(--font-mono); font-size:9px; letter-spacing:.14em; text-transform:uppercase; color:var(--accent); }
.card-badge {
  font-family:var(--font-mono); font-size:8px; letter-spacing:.12em; text-transform:uppercase;
  padding:2px 8px; border-radius:3px; border:1px solid;
}
.card-badge.green { color:var(--accent); border-color:var(--accent-dim); }
.card-badge.amber { color:var(--amber); border-color:rgba(245,158,11,0.25); }
.card-badge.red { color:var(--red); border-color:rgba(244,63,94,0.25); }
.card-badge.gray { color:var(--text-muted); border-color:var(--border); }

.card-body { font-size:11px; color:var(--text-sec); line-height:1.7; }
.card-row { display:flex; justify-content:space-between; padding:3px 0; }
.card-label { color:var(--text-muted); font-family:var(--font-mono); font-size:9px; letter-spacing:.06em; }
.card-value { font-family:var(--font-mono); font-size:10px; font-weight:500; }
.card-value.green { color:var(--accent); }
.card-value.amber { color:var(--amber); }
.card-value.red { color:var(--red); }
.card-value.blue { color:var(--blue); }

/* ANOMALY */
.anomaly { padding:8px 10px; margin-bottom:6px; border-left:3px solid; font-size:10px; line-height:1.6; }
.anomaly.red { border-color:var(--red); background:rgba(244,63,94,0.06); }
.anomaly.amber { border-color:var(--amber); background:rgba(245,158,11,0.06); }
.anomaly.info { border-color:var(--blue); background:rgba(90,200,250,0.06); }
.anomaly-label { font-family:var(--font-mono); font-size:8px; letter-spacing:.1em; text-transform:uppercase; color:var(--text-muted); }

/* LOADING */
.loading { display:flex; align-items:center; justify-content:center; height:60vh; color:var(--text-muted); flex-direction:column; gap:12px; }
.spinner { width:20px; height:20px; border-radius:50%; border:2px solid var(--border); border-top-color:var(--accent); animation:spin .8s linear infinite; }
@keyframes spin { to{transform:rotate(360deg)} }

/* SKILLS LIST */
.skills-list { display:flex; flex-wrap:wrap; gap:4px; }
.skill-chip {
  font-family:var(--font-mono); font-size:8px; letter-spacing:.04em;
  padding:2px 6px; background:rgba(90,200,250,0.08); color:var(--blue);
  border-radius:2px;
}

@media (max-width:700px) {
  .grid { grid-template-columns:1fr; padding:12px; }
  .topbar { padding:8px 12px; flex-wrap:wrap; gap:8px; }
}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-left">
    <span class="topbar-dot"></span>
    <span class="topbar-title">Agent OS · Mission Control</span>
  </div>
  <div class="topbar-stats" id="topbar-stats">
    <span class="stat">Agents: <strong id="stat-agents">—</strong></span>
    <span class="stat">Skills: <strong id="stat-skills">—</strong></span>
    <span class="stat">Running: <strong id="stat-running">—</strong></span>
    <span class="stat" style="color:var(--red)">Errors: <strong id="stat-errors">—</strong></span>
  </div>
</div>
<div class="grid" id="grid">
  <div class="loading"><div class="spinner"></div><div>Loading Agent OS Mission Control...</div></div>
</div>

<script>
async function load() {
  try {
    const r = await fetch('/api/v1/mc-os/snapshot');
    if (!r.ok) throw new Error(r.status);
    const data = await r.json();
    render(data);
  } catch(e) {
    document.getElementById('grid').innerHTML =
      '<div class="loading"><div style="color:var(--red);font-size:14px;">⚠ ' + e.message + '</div><div style="font-size:11px;color:var(--text-muted)">Retrying in 10s...</div></div>';
    setTimeout(load, 10000);
  }
}

function escape(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function render(data) {
  const mc = data.mission_control || {};
  const aos = data.agent_os || {};
  const skills = data.skills || {};
  const ar = data.autoresearch || {};
  const anomalies = data.anomalies || [];

  // Topbar stats
  document.getElementById('stat-agents').textContent = aos.instance_count || '—';
  document.getElementById('stat-skills').textContent = skills.total_skills || '—';
  document.getElementById('stat-running').textContent = (aos.process_summary||{}).running || '—';
  document.getElementById('stat-errors').textContent = (aos.process_summary||{}).error || '—';

  let html = '';

  // ── Mission Control Card ──
  const brain = mc.brain || {};
  const agi = mc.agi || {};
  const revenue = mc.revenue || {};
  const compliance = mc.compliance || {};
  html += '<div class="card"><div class="card-header">';
  html += '<span class="card-title">System Metrics</span>';
  html += '<span class="card-badge ' + (data.health||'gray') + '">' + (data.health||'unknown') + '</span></div>';
  html += '<div class="card-body">';
  html += '<div class="card-row"><span class="card-label">Brain</span><span class="card-value ' + (brain.up?'green':'red') + '">' + (brain.up?'Online':'Offline') + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Ollama</span><span class="card-value ' + (mc.brain&&mc.brain.up?'green':'red') + '">' + (mc.brain&&mc.brain.up?'Online':'Offline') + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Supabase</span><span class="card-value ' + (mc.brain&&mc.brain.supabase_up?'green':'red') + '">' + (mc.brain&&mc.brain.supabase_up?'Online':'Offline') + '</span></div>';
  html += '<div class="card-row"><span class="card-label">AGI Status</span><span class="card-value ' + (agi.status==='RUNNING'||agi.status==='EXPLORE'?'green':'amber') + '">' + (agi.status||'UNKNOWN') + '</span></div>';
  html += '<div class="card-row"><span class="card-label">AGI Cycles</span><span class="card-value">' + (agi.cycles||0) + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Revenue 24h</span><span class="card-value ' + ((revenue.total_24h||0) > 0 ? 'green' : 'amber') + '">$' + (revenue.total_24h||'0') + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Stale Agents</span><span class="card-value ' + ((agi.stale_count||0) > 0 ? 'red' : '') + '">' + (agi.stale_count||0) + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Blocked Today</span><span class="card-value ' + ((compliance.blocked_today||0) > 10 ? 'amber' : '') + '">' + (compliance.blocked_today||0) + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Call Window</span><span class="card-value ' + (compliance.call_window_open!==false?'green':'amber') + '">' + (compliance.call_window_open!==false?'Open':'Closed') + '</span></div>';
  html += '</div></div>';

  // ── Agent OS Instances Card ──
  const instances = aos.instances || [];
  const processes = aos.processes || {};
  html += '<div class="card"><div class="card-header">';
  html += '<span class="card-title">Agent OS Instances (' + instances.length + ')</span>';
  html += '<span class="card-badge ' + ((aos.process_summary||{}).error > 0 ? 'red' : 'green') + '">' + ((aos.process_summary||{}).running||0) + '/' + ((aos.process_summary||{}).total||0) + ' running</span></div>';
  html += '<div class="card-body">';
  instances.forEach(function(inst) {
    const proc = processes[inst.id] || {};
    const status = proc.status || '—';
    const color = status === 'RUNNING' ? 'green' : (status === 'ERROR' ? 'red' : 'amber');
    html += '<div class="card-row">';
    html += '<span class="card-label">' + escape(inst.name) + '</span>';
    html += '<span class="card-value ' + color + '">' + status + '</span>';
    html += '</div>';
  });
  html += '<div style="margin-top:8px;font-size:9px;color:var(--text-muted);font-family:var(--font-mono)">Kernel: ' + ((aos.kernel||{}).booted?'Booted':'Not booted') + ' · Uptime: ' + Math.floor(((aos.kernel||{}).uptime_seconds||0)/60) + 'm</div>';
  html += '</div></div>';

  // ── Skills Registry & Vector Search Card ──
  const allSkills = skills.all_skills || [];
  const vaultSkills = skills.vault_skills || [];
  const vs = skills.vector_search || {};
  html += '<div class="card"><div class="card-header">';
  html += '<span class="card-title">Skills Registry</span>';
  html += '<span class="card-badge">' + (skills.total_skills||0) + ' total</span></div>';
  html += '<div class="card-body">';
  html += '<div class="card-row"><span class="card-label">Marketing</span><span class="card-value blue">' + ((skills.marketing_skills||[]).length) + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Vault (custom)</span><span class="card-value blue">' + vaultSkills.length + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Total Registered</span><span class="card-value green">' + (skills.total_skills||0) + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Vector Search</span><span class="card-value ' + (vs.available ? 'green' : 'amber') + '">' + (vs.available ? 'Qdrant ✓' : 'Unavailable') + '</span></div>';
  if (vs.available) {
    html += '<div class="card-row"><span class="card-label">Skills Indexed</span><span class="card-value blue">' + (vs.skills_indexed||0) + ' vectors</span></div>';
  }
  if (vs.error) {
    html += '<div style="margin-top:4px;font-size:9px;color:var(--text-muted);font-family:var(--font-mono)">' + escape(vs.error) + '</div>';
  }
  if (vaultSkills.length) {
    html += '<div style="margin-top:8px"><div class="skills-list">';
    vaultSkills.forEach(function(s) { html += '<span class="skill-chip">' + escape(s) + '</span>'; });
    html += '</div></div>';
  }
  html += '</div></div>';

  // ── Skill Search Card (Qdrant vector search) ──
  html += '<div class="card" id="skill-search-card"><div class="card-header">';
  html += '<span class="card-title">Skill Search</span>';
  html += '<span class="card-badge ' + (vs.available ? 'green' : 'gray') + '">' + (vs.available ? 'Vector' : 'Offline') + '</span></div>';
  html += '<div class="card-body">';
  html += '<div style="display:flex;gap:8px;margin-bottom:10px">';
  html += '<input id="skill-search-input" type="text" placeholder="Search skills semantically…" onkeydown="if(event.key===\'Enter\')doSkillSearch()" style="flex:1;padding:8px 10px;background:var(--elevated);border:1px solid var(--border);color:var(--text);font-family:var(--font-mono);font-size:11px;outline:none;border-radius:2px">';
  html += '<button onclick="doSkillSearch()" style="padding:8px 14px;background:var(--accent-dim);border:1px solid var(--accent);color:var(--accent);font-family:var(--font-mono);font-size:9px;cursor:pointer;border-radius:2px;text-transform:uppercase;letter-spacing:.12em">Search</button>';
  html += '</div>';
  html += '<div id="skill-search-results" style="font-size:10px;color:var(--text-muted)">Enter a query to find skills by meaning, not just by name.</div>';
  html += '</div></div>';

  // ── Autoresearch Card ──
  const targets = ar.targets || [];
  html += '<div class="card"><div class="card-header">';
  html += '<span class="card-title">Autoresearch Loop</span>';
  html += '<span class="card-badge ' + (ar.status==='active'?'green':'amber') + '">' + (ar.status||'—') + '</span></div>';
  html += '<div class="card-body">';
  if (targets.length) {
    targets.forEach(function(t) {
      html += '<div class="card-row">';
      html += '<span class="card-label">' + escape(t.name) + '</span>';
      html += '<span class="card-value">' + escape(t.latest_weighted || '—') + '</span>';
      html += '</div>';
    });
  } else {
    html += '<div style="color:var(--text-muted)">No autoresearch targets found</div>';
  }
  html += '</div></div>';

  // ── Anomalies Card ──
  html += '<div class="card"><div class="card-header">';
  html += '<span class="card-title">Anomalies</span>';
  html += '<span class="card-badge ' + (anomalies.length > 0 ? 'red' : 'green') + '">' + anomalies.length + '</span></div>';
  html += '<div class="card-body">';
  if (anomalies.length) {
    anomalies.forEach(function(a) {
      html += '<div class="anomaly ' + a.severity + '">';
      html += '<div class="anomaly-label">' + a.severity + ' · ' + a.subsystem + ' · ' + a.pattern + '</div>';
      html += '<div>' + escape(a.message) + '</div></div>';
    });
  } else {
    html += '<div style="color:var(--text-muted)">No anomalies detected</div>';
  }
  html += '</div></div>';

  // ── Timestamp ──
  html += '<div class="card"><div class="card-header"><span class="card-title">Snapshot Info</span></div>';
  html += '<div class="card-body">';
  html += '<div class="card-row"><span class="card-label">Timestamp</span><span class="card-value">' + escape(data.ts || '—') + '</span></div>';
  html += '<div class="card-row"><span class="card-label">Refresh</span><span class="card-value">Every 10s</span></div>';
  html += '</div></div>';

  document.getElementById('grid').innerHTML = html;
}

// ── SKILL VECTOR SEARCH ─────────────────────────────────────────────
window.doSkillSearch = async function() {
  const input = document.getElementById('skill-search-input');
  const resultsEl = document.getElementById('skill-search-results');
  const query = input ? input.value.trim() : '';
  if (!query) {
    resultsEl.innerHTML = '<span style="color:var(--text-muted)">Enter a query to find skills by meaning, not just by name.</span>';
    return;
  }
  resultsEl.innerHTML = '<span style="color:var(--text-muted)">Searching…</span>';
  try {
    const r = await fetch('/api/v1/mc-os/skills/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query: query, limit: 12, score_threshold: 0.0}),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    const results = data.results || [];
    if (!results.length) {
      resultsEl.innerHTML = '<span style="color:var(--text-muted)">No results found for "' + escape(query) + '". Skills may not be indexed yet.</span>';
      return;
    }
    let html = '<div style="margin-bottom:6px;font-family:var(--font-mono);font-size:9px;color:var(--text-muted)">' + results.length + ' results for "' + escape(query) + '"</div>';
    results.forEach(function(r) {
      const payload = r.payload || {};
      const score = (r.score * 100).toFixed(0);
      const color = score > 70 ? 'var(--accent)' : (score > 40 ? 'var(--amber)' : 'var(--text-muted)');
      html += '<div style="padding:8px 10px;margin-bottom:6px;background:var(--elevated);border-left:3px solid ' + color + ';">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">';
      html += '<strong style="font-size:11px;color:var(--text)">' + escape(payload.skill_name || r.id) + '</strong>';
      html += '<span style="font-family:var(--font-mono);font-size:10px;color:' + color + ';font-weight:600">' + score + '%</span>';
      html += '</div>';
      if (payload.content_preview) {
        html += '<div style="font-size:9px;color:var(--text-sec);line-height:1.5;margin-bottom:4px">' + escape(payload.content_preview).slice(0, 200) + '</div>';
      }
      if (r.registry) {
        html += '<div style="font-size:8px;color:var(--text-muted);font-family:var(--font-mono)">v' + escape(r.registry.active || '?') + ' · ' + ((r.registry.versions||[]).length) + ' versions</div>';
      }
      html += '</div>';
    });
    resultsEl.innerHTML = html;
  } catch(e) {
    resultsEl.innerHTML = '<span style="color:var(--red)">Search failed: ' + escape(e.message) + '</span>';
  }
};

// Auto-refresh every 10s
load();
setInterval(load, 10000);
</script>
</body>
</html>
""".strip()

# ═════════════════════════════════════════════════════════════════════════
# STANDALONE APP (uvicorn port 8060)
# ═════════════════════════════════════════════════════════════════════════

def create_standalone_app() -> FastAPI:
    """Create a standalone FastAPI app for Agent OS Mission Control on port 8060.
    No auth required — designed for operator/SPA access behind the hub.
    """
    from fastapi.middleware.cors import CORSMiddleware
    app = FastAPI(title="Agent OS · Mission Control", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_mission_control_os_routes(app)
    return app


# ── Standalone entry point ─────────────────────────────────────────────
standalone_app = create_standalone_app()

if __name__ == "__main__":
    import uvicorn
    try:
        from fastapi import FastAPI
    except ImportError:
        pass
    port = int(os.environ.get("MC_OS_PORT", "8060"))
    host = os.environ.get("MC_OS_HOST", "0.0.0.0")
    log.info(f"[mc-os] Starting standalone on {host}:{port}")
    uvicorn.run(standalone_app, host=host, port=port, log_level="info")
