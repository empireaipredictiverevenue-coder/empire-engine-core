"""
EMPIRE V49 · SELF-AWARENESS ENGINE
====================================
Meta-cognitive layer that gives Empire AI a model of itself.

Pulls data from every introspection source across the system and
synthesizes a unified self-model, natural-language self-narratives,
anomaly detection, root cause analysis, and self-improvement suggestions.

Integration points:
  - agent_registry (heartbeat, status per agent)
  - system_health (overseer reports)
  - SI Core (Bayesian performance, regime shifts)
  - Strategy Evolution (self-scoring)
  - Brain Learning (threshold tuning)
  - LoopAgent learning (lane outcomes, Rank & Rent)
  - Psychology Mind Map (persuasion effectiveness)
  - Predictive Revenue (lane health)
  - PM2/Stack Agent (service health)

Wire-up in hub.py:
    from empire_self_awareness import register_self_awareness_routes
    register_self_awareness_routes(app, require_auth=require_auth, get_db=get_db)
"""

import logging
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

log = logging.getLogger("empire.self_awareness")

# ── SYSTEM DEPENDENCY GRAPH ──────────────────────────────────────
# Maps each agent to its dependencies (agents it depends on to function)
_SYSTEM_DEPENDENCIES = {
    "hub": [],
    "mesh": ["hub"],
    "orchestrator": ["hub", "storm_predictor"],
    "empire-ppc-inbound": ["hub"],
    "empire-matrix-agi": ["hub"],
    "empire-matrix-strategy": ["hub"],
    "empire-matrix-landing": ["hub"],
    "empire-matrix-universal": ["hub"],
    "contractor-sniper": ["hub"],
    "empire-pulse-cron": ["hub"],
    "storm_predictor": ["hub"],
    "seo_agent": ["hub"],
    "voice_streaming_agent": ["hub", "synthetic_brain"],
    "synthetic_brain": [],
    "hermes_controller": ["hub"],
    "agi_lane_engine": ["hub", "orchestrator"],
    "agi_revenue": ["hub", "predictive_revenue"],
    "predictive_revenue": ["hub"],
    "overseer": ["hub"],
    "swarm_worker": ["hub", "storm_predictor"],
    "brain_memory": [],
    "dream_loop": ["hub", "brain_memory"],
    "brain_learning": ["hub", "brain_memory"],
}

_AGENT_CAPABILITIES = {
    "hub": "API gateway, route dispatch, auth",
    "mesh": "Fleet orchestrator, signal handler",
    "orchestrator": "Storm tracking, lane dispatch, agent_interface",
    "empire-ppc-inbound": "Pay-per-call inbound routing, high-intent filter",
    "contractor-sniper": "Contractor matching from inbound leads",
    "storm_predictor": "Storm polygon→metro target prediction",
    "seo_agent": "SEO content creation, genome strategy",
    "voice_streaming_agent": "Vonage outbound calls, Kokoro TTS",
    "synthetic_brain": "Kokoro TTS, video rendering, LLM strategy",
    "hermes_controller": "Telegram bot, operator DMs",
    "agi_lane_engine": "Lane execution, strategy routing",
    "agi_revenue": "Revenue prediction, AGI calibration",
    "predictive_revenue": "Per-lane MRR forecast, health checks",
    "overseer": "System health, agent staleness, reports",
    "swarm_worker": "Parallel ad generation, video assembly",
    "brain_memory": "Past decisions, embedding search, few-shot learning",
    "dream_loop": "Brain memory, autonomous decisions",
    "brain_learning": "Threshold auto-tuning from outcomes",
}

# ── HEALTH THRESHOLDS ───────────────────────────────────────────
_HEALTH_THRESHOLDS = {
    "stale_seconds": 600,         # 10 min without ping → stale
    "critical_stale_seconds": 3600,  # 1 hour → critical
    "min_active_agents": 8,       # fewer than this → system degraded
    "min_lane_win_rate": 0.15,    # below this → lane critical
    "lane_slow_pacing_hours": 12,  # above this → lane slow
    "revenue_drop_pct": -20,      # month-over-month drop → alert
    "min_agent_health_pct": 0.6,  # below 60% agents healthy → system warning
}

# ══════════════════════════════════════════════════════════════════
# SELF-AWARENESS ENGINE
# ══════════════════════════════════════════════════════════════════

class SelfAwarenessEngine:
    """Meta-cognitive layer for Empire AI.

    Provides:
      - Unified system model (agents, services, lanes, revenue, strategies)
      - Natural-language self-narratives via template-based reasoning
      - Anomaly detection across system dimensions
      - Root cause analysis tracing symptoms through dependency graph
      - Self-improvement suggestions based on observed patterns
    """

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        self._anomaly_history: list[dict] = []
        self._last_snapshot_ts: Optional[str] = None

    # ═══════════════════════════════════════════════════════════════
    # 1. UNIFIED SYSTEM MODEL
    # ═══════════════════════════════════════════════════════════════

    def system_model(self, force_refresh: bool = False) -> dict:
        """Build a unified model of the entire system state.

        Combines agent health, service status, lane performance, revenue,
        strategy portfolio, and the dependency graph into a single model.
        """
        agents = self._agent_catalog()
        services = self._service_health()
        lanes = self._lane_model()
        revenue = self._revenue_state()
        strategies = self._strategy_portfolio()

        # Compute overall health
        agent_healthy = sum(1 for a in agents if a.get("status") == "ACTIVE" and not a.get("stale"))
        agent_total = len(agents)
        health_pct = agent_healthy / max(agent_total, 1)

        # Find degradeads
        stale_agents = [a["name"] for a in agents if a.get("stale")]
        critical_agents = [a["name"] for a in agents if a.get("critical")]

        return {
            "agents": agents,
            "services": services,
            "lanes": lanes,
            "revenue": revenue,
            "strategies": strategies,
            "dependencies": _SYSTEM_DEPENDENCIES,
            "capabilities": _AGENT_CAPABILITIES,
            "health": {
                "overall": "healthy" if health_pct >= _HEALTH_THRESHOLDS["min_agent_health_pct"] else (
                    "degraded" if health_pct >= 0.3 else "critical"),
                "agent_healthy": agent_healthy,
                "agent_total": agent_total,
                "health_pct": round(health_pct, 3),
                "stale_agents": stale_agents,
                "critical_agents": critical_agents,
            },
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def _agent_catalog(self) -> list[dict]:
        """Read agent_registry and build catalog with staleness detection."""
        agents = []
        if not self.get_db:
            # Fallback: return static agent list with unknown status
            for name, caps in _AGENT_CAPABILITIES.items():
                agents.append({
                    "name": name,
                    "status": "UNKNOWN",
                    "capabilities": caps,
                    "stale": False,
                    "critical": False,
                    "last_ping": None,
                })
            return agents

        try:
            db = self.get_db()
            r = db.table("agent_registry") \
                .select("agent_name,status,last_ping,enabled,capabilities,metrics") \
                .execute()
            rows = r.data or []
        except Exception as e:
            log.warning(f"[self.aware] agent_registry query failed: {e}")
            return self._agent_catalog()  # fallback

        now = datetime.now(timezone.utc)
        for row in rows:
            name = row.get("agent_name", "unknown")
            status = row.get("status", "UNKNOWN")
            caps = row.get("capabilities") or _AGENT_CAPABILITIES.get(name, "")
            last_ping = row.get("last_ping")
            stale = False
            critical = False

            if last_ping:
                try:
                    ping_dt = datetime.fromisoformat(str(last_ping).replace("Z", "+00:00"))
                    age = (now - ping_dt).total_seconds()
                    stale = age > _HEALTH_THRESHOLDS["stale_seconds"]
                    critical = age > _HEALTH_THRESHOLDS["critical_stale_seconds"]
                except Exception:
                    pass

            agents.append({
                "name": name,
                "status": "CRITICAL" if critical else ("STALE" if stale else status),
                "capabilities": caps if isinstance(caps, str) else ", ".join(caps) if isinstance(caps, list) else str(caps),
                "stale": stale,
                "critical": critical,
                "last_ping": last_ping,
                "enabled": row.get("enabled", True),
                "metrics": row.get("metrics", {}),
            })

        # Add any missing agents from the capability registry
        existing = {a["name"] for a in agents}
        for name, caps in _AGENT_CAPABILITIES.items():
            if name not in existing:
                agents.append({
                    "name": name,
                    "status": "UNREGISTERED",
                    "capabilities": caps,
                    "stale": True,
                    "critical": True,
                    "last_ping": None,
                    "enabled": True,
                    "metrics": {},
                })

        return agents

    def _service_health(self) -> dict:
        """Return PM2 service health (reads from Stack Agent if available)."""
        try:
            # Try to read PM2 status via subprocess
            import subprocess as _sp
            r = _sp.run(["pm2", "jlist"], capture_output=True, timeout=5)
            if r.returncode == 0:
                import json as _json
                services = _json.loads(r.stdout)
                online = sum(1 for s in services if s.get("pm2_env", {}).get("status") == "online")
                return {
                    "total": len(services),
                    "online": online,
                    "offline": len(services) - online,
                    "services": [{
                        "name": s.get("name", "?"),
                        "status": s.get("pm2_env", {}).get("status", "?"),
                        "uptime": s.get("pm2_env", {}).get("pm_uptime"),
                    } for s in services],
                }
        except Exception:
            pass
        return {"total": 0, "online": 0, "offline": 0, "services": [], "error": "pm2_unavailable"}

    def _lane_model(self) -> dict:
        """Build lane performance model. Tries LoopAgent, falls back to mock."""
        try:
            from empire_loop_agent import LoopAgent
            loop = LoopAgent(get_db=self.get_db)
            overview = loop.loop_overview()
            return {
                "total": overview.get("total_lanes", 36),
                "active": overview.get("active_lanes", 0),
                "total_runs": overview.get("total_runs", 0),
                "total_wins": overview.get("total_wins", 0),
                "overall_win_rate": overview.get("overall_win_rate", 0),
                "learning_enabled": overview.get("learning_enabled", False),
                "evolutions_run": overview.get("evolutions_run", 0),
                "deactivated": overview.get("deactivated_lanes", 0),
                "niches": overview.get("niches", {}),
            }
        except Exception as e:
            log.debug(f"[self.aware] loop agent unavailable: {e}")
            return {"total": 36, "active": 0, "error": str(e)[:100]}

    def _revenue_state(self) -> dict:
        """Build revenue state model. Tries predictive revenue, falls back."""
        try:
            from bots.predictive_revenue import per_lane_forecast
            forecast = per_lane_forecast()
            return {
                "total_revenue_24h": forecast.get("total_revenue_24h", 0),
                "total_revenue_7d": forecast.get("total_revenue_7d", 0),
                "lane_count": forecast.get("lane_count", 0),
                "health": forecast.get("trend", {}),
                "top_lanes": forecast.get("lanes", [])[:5],
            }
        except Exception as e:
            log.debug(f"[self.aware] predictive revenue unavailable: {e}")
            return {"error": str(e)[:100]}

    def _strategy_portfolio(self) -> dict:
        """Build strategy portfolio model."""
        try:
            from empire_si_strategy import StrategyEvolution
            si = StrategyEvolution.get_shared_instance()
            if si:
                snap = si.snapshot()
                return {
                    "active_strategies": snap.get("active_strategies", 0),
                    "inactive_strategies": snap.get("inactive_strategies", 0),
                    "evolution_runs": snap.get("evolution_runs", 0),
                    "best_per_niche": snap.get("best_per_niche", {}),
                }
        except Exception:
            pass
        return {"active_strategies": 0, "evolution_runs": 0}

    # ═══════════════════════════════════════════════════════════════
    # 2. SELF-NARRATIVE
    # ═══════════════════════════════════════════════════════════════

    def self_narrative(self, depth: str = "executive") -> dict:
        """Generate a structured self-assessment using rule-based reasoning.

        Produces a coherent assessment of:
          - What's working, what's not, and why
          - What the system is learning and adapting
          - What it recommends changing
        """
        model = self.system_model(force_refresh=True)
        health = model.get("health", {})
        lanes = model.get("lanes", {})
        revenue = model.get("revenue", {})

        # ── Build narrative sections ──

        # 1. Overall state
        overall = health.get("overall", "unknown")
        if overall == "healthy":
            state_summary = "System is operating normally. All critical subsystems are responsive."
        elif overall == "degraded":
            stale = health.get("stale_agents", [])
            state_summary = f"System is degraded. {len(stale)} agent(s) stale: {', '.join(stale[:5])}."
        else:
            critical = health.get("critical_agents", [])
            state_summary = f"System is critical. {len(critical)} agent(s) unresponsive: {', '.join(critical[:5])}."

        # 2. Agent health
        agent_summary = (
            f"{health.get('agent_healthy', 0)}/{health.get('agent_total', 0)} agents healthy "
            f"({round(health.get('health_pct', 0) * 100)}%)"
        )

        # 3. Lane performance
        wr = lanes.get("overall_win_rate", 0)
        if wr >= 0.6:
            lane_summary = f"Lane performance is strong ({wr:.0%} win rate across {lanes.get('active', 0)} active lanes)."
        elif wr >= 0.3:
            lane_summary = f"Lane performance is moderate ({wr:.0%} win rate). Room for improvement."
        else:
            lane_summary = f"Lane performance is weak ({wr:.0%} win rate). Strategy evolution may be needed."

        # 4. Revenue
        rev_24h = revenue.get("total_revenue_24h", 0)
        rev_7d = revenue.get("total_revenue_7d", 0)
        revenue_summary = f"${rev_24h:,.0f} last 24h, ${rev_7d:,.0f} last 7d."

        # 5. Learning & adaptation
        learning_items = []
        if lanes.get("learning_enabled"):
            learning_items.append(f"LoopAgent has run {lanes.get('evolutions_run', 0)} evolution cycles")
        try:
            from empire_psychology_mind_map import PsychologyMindMap
            mm = PsychologyMindMap()
            eff = mm.get_effectiveness_summary()
            if eff.get("total_attempts", 0) > 0:
                learning_items.append(
                    f"Psychology Mind Map tracking {eff['total_attempts']} strategy outcomes "
                    f"({eff['overall_conversion_rate']:.0%} conversion)")
        except Exception:
            pass
        learning_summary = " | ".join(learning_items) if learning_items else "Learning systems active, awaiting more data."

        # 6. Anomalies
        anomalies = self._detect_anomalies(model)
        anomaly_summary = f"{len(anomalies)} anomaly(s) detected." if anomalies else "No anomalies detected."

        # 7. Recommendations
        recommendations = self._self_improve(model)

        return {
            "overall_state": state_summary,
            "agent_health": agent_summary,
            "lane_performance": lane_summary,
            "revenue": revenue_summary,
            "learning_status": learning_summary,
            "anomalies": anomaly_summary,
            "recommendations": recommendations[:5],
            "depth": depth,
            "model_snapshot": {
                "health_overall": overall,
                "agent_healthy": health.get("agent_healthy", 0),
                "agent_total": health.get("agent_total", 0),
                "active_lanes": lanes.get("active", 0),
                "win_rate": wr,
                "revenue_24h": rev_24h,
                "revenue_7d": rev_7d,
                "anomaly_count": len(anomalies),
                "recommendation_count": len(recommendations),
            },
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════
    # 3. ANOMALY DETECTION
    # ═══════════════════════════════════════════════════════════════

    def _detect_anomalies(self, model: Optional[dict] = None) -> list[dict]:
        """Detect system-wide anomalies across multiple dimensions."""
        if model is None:
            model = self.system_model()

        anomalies = []
        health = model.get("health", {})
        lanes = model.get("lanes", {})
        revenue = model.get("revenue", {})
        agents = model.get("agents", [])

        # Agent-level anomalies
        for agent in agents:
            if agent.get("critical"):
                anomalies.append({
                    "type": "agent_critical",
                    "severity": "critical",
                    "source": "agent_registry",
                    "message": f"Agent '{agent['name']}' is critically stale (no ping in >1h).",
                    "agent": agent["name"],
                    "recommendation": f"Restart {agent['name']} or check its host.",
                })
            elif agent.get("stale"):
                anomalies.append({
                    "type": "agent_stale",
                    "severity": "warning",
                    "source": "agent_registry",
                    "message": f"Agent '{agent['name']}' is stale (no ping in >10m).",
                    "agent": agent["name"],
                    "recommendation": f"Check if {agent['name']} is still running.",
                })

        # Lane-level anomalies
        wr = lanes.get("overall_win_rate", 1)
        if wr < _HEALTH_THRESHOLDS["min_lane_win_rate"]:
            anomalies.append({
                "type": "lane_win_rate_critical",
                "severity": "critical",
                "source": "loop_agent",
                "message": f"Overall lane win rate ({wr:.1%}) below critical threshold.",
                "recommendation": "Run strategy evolution cycle to improve performance.",
            })

        # Revenue anomalies
        if revenue.get("total_revenue_24h", 0) == 0 and revenue.get("error") is None:
            anomalies.append({
                "type": "zero_revenue_24h",
                "severity": "warning",
                "source": "predictive_revenue",
                "message": "No revenue recorded in the last 24 hours.",
                "recommendation": "Check lane execution and contractor activity.",
            })

        # System-level anomalies
        total_agents = len(agents)
        if total_agents < _HEALTH_THRESHOLDS["min_active_agents"]:
            anomalies.append({
                "type": "low_agent_count",
                "severity": "warning",
                "source": "agent_registry",
                "message": f"Only {total_agents} agents registered (minimum expected: {_HEALTH_THRESHOLDS['min_active_agents']}).",
                "recommendation": "Check PM2 and restart any missing services.",
            })

        # Cap anomaly history
        self._anomaly_history.extend(anomalies)
        if len(self._anomaly_history) > 200:
            self._anomaly_history = self._anomaly_history[-200:]

        return anomalies

    def get_anomalies(self, severity: Optional[str] = None) -> list[dict]:
        """Return detected anomalies, optionally filtered by severity."""
        anomalies = self._detect_anomalies()
        if severity:
            anomalies = [a for a in anomalies if a.get("severity") == severity]
        return anomalies

    def detect_anomalies(self, model: Optional[dict] = None) -> list[dict]:
        """Public wrapper around _detect_anomalies that accepts a pre-built model.

        If a model is provided, anomalies are derived from it without rebuilding.
        If no model is provided, builds system_model() internally.

        This is the preferred public API for callers that already have a model
        (e.g. AGI Governor consulting the SA engine).
        """
        return self._detect_anomalies(model)

    # ═══════════════════════════════════════════════════════════════
    # 4. ROOT CAUSE ANALYSIS
    # ═══════════════════════════════════════════════════════════════

    def root_cause_analysis(self, symptom: str = "") -> list[dict]:
        """Trace a symptom through the dependency graph to find root causes.

        If no symptom is provided, analyzes all current anomalies.
        Returns a list of (symptom, root_cause, chain) tuples.
        """
        if symptom:
            # Analyze a specific symptom
            return self._trace_symptom(symptom)

        # Analyze all current anomalies
        anomalies = self._detect_anomalies()
        results = []
        for a in anomalies:
            traces = self._trace_symptom(a["message"])
            results.extend(traces)
        return results

    def _trace_symptom(self, symptom: str) -> list[dict]:
        """Trace a single symptom to root causes."""
        results = []
        model = self.system_model()
        agents = model.get("agents", [])

        # Check if symptom relates to a specific agent
        for name in _SYSTEM_DEPENDENCIES:
            if name.lower() in symptom.lower():
                # Build the chain: symptom → affected agent → dependencies → root causes
                deps = _SYSTEM_DEPENDENCIES.get(name, [])
                dep_statuses = []
                for dep in deps:
                    dep_agent = next((a for a in agents if a["name"] == dep), None)
                    if dep_agent:
                        dep_statuses.append({
                            "agent": dep,
                            "status": dep_agent.get("status", "UNKNOWN"),
                            "capabilities": dep_agent.get("capabilities", ""),
                        })

                # Find root cause
                root_causes = []
                if dep_statuses:
                    for ds in dep_statuses:
                        if ds["status"] in ("CRITICAL", "STALE", "UNREGISTERED"):
                            root_causes.append({
                                "agent": ds["agent"],
                                "issue": f"{ds['agent']} is {ds['status']}",
                                "why": f"'{name}' depends on '{ds['agent']}' for {ds['capabilities'][:80]}",
                            })
                    if not root_causes:
                        root_causes.append({
                            "agent": name,
                            "issue": f"'{name}' itself is the likely root cause",
                            "why": "No upstream dependencies are degraded",
                        })
                else:
                    root_causes.append({
                        "agent": name,
                        "issue": f"'{name}' has no tracked dependencies",
                        "why": "Check this agent directly",
                    })

                results.append({
                    "symptom": symptom[:200],
                    "affected_agent": name,
                    "dependency_chain": dep_statuses,
                    "root_causes": root_causes,
                })

        if not results:
            results.append({
                "symptom": symptom[:200],
                "affected_agent": "system",
                "dependency_chain": [],
                "root_causes": [{"agent": "unknown", "issue": "Could not trace this symptom", "why": "No matching agent found in dependency graph"}],
            })

        return results

    # ═══════════════════════════════════════════════════════════════
    # 5. SELF-IMPROVEMENT SUGGESTIONS
    # ═══════════════════════════════════════════════════════════════

    def _self_improve(self, model: Optional[dict] = None) -> list[dict]:
        """Generate self-improvement suggestions based on observed patterns."""
        if model is None:
            model = self.system_model()

        suggestions = []
        health = model.get("health", {})
        lanes = model.get("lanes", {})
        agents = model.get("agents", [])
        services = model.get("services", {})

        # Agent-related suggestions
        unregistered = [a for a in agents if a.get("status") == "UNREGISTERED"]
        if unregistered:
            suggestions.append({
                "type": "register_missing_agents",
                "priority": "medium",
                "message": f"{len(unregistered)} agent(s) never registered with agent_registry: {', '.join(a['name'] for a in unregistered[:5])}",
                "action": "Add heartbeat calls to these agents or remove them from the registry.",
            })

        stale = [a for a in agents if a.get("stale")]
        if len(stale) > len(agents) * 0.3:
            suggestions.append({
                "type": "high_stale_ratio",
                "priority": "high",
                "message": f"{len(stale)}/{len(agents)} agents stale ({round(len(stale)/max(len(agents),1)*100)}%)",
                "action": "Restart all stale agents. Consider adding auto-restart to PM2 config.",
            })

        # Lane-related suggestions
        evolutions = lanes.get("evolutions_run", 0)
        if evolutions == 0:
            suggestions.append({
                "type": "no_evolution",
                "priority": "medium",
                "message": "LoopAgent has never run a self-evolution cycle.",
                "action": "Trigger a self-evolution cycle via POST /api/loop/evolve to begin adaptive strategy optimization.",
            })

        wr = lanes.get("overall_win_rate", 1)
        if wr < 0.3:
            suggestions.append({
                "type": "low_win_rate",
                "priority": "high",
                "message": f"Overall win rate ({wr:.1%}) is below effective threshold.",
                "action": "Review lane strategies and consider switching underperforming lanes to higher-performing strategies.",
            })

        # Service-related suggestions
        if services.get("offline", 0) > 0:
            suggestions.append({
                "type": "offline_services",
                "priority": "high",
                "message": f"{services['offline']} PM2 service(s) offline.",
                "action": f"Run 'pm2 restart {services.get('services', [{}])[0].get('name', '<all>')}' to restore services.",
            })

        # System architecture suggestions
        if len(agents) > 25:
            suggestions.append({
                "type": "agent_count_high",
                "priority": "low",
                "message": f"System has {len(agents)} registered agents — consider consolidating.",
                "action": "Audit agent overlap. Agents with >70% capability overlap could be merged.",
            })

        return suggestions

    def get_self_improve(self) -> list[dict]:
        """Public method: detect and return self-improvement suggestions."""
        model = self.system_model(force_refresh=True)
        return self._self_improve(model)

    # ═══════════════════════════════════════════════════════════════
    # SNAPSHOT
    # ═══════════════════════════════════════════════════════════════

    def snapshot(self) -> dict:
        """Full self-awareness snapshot for SPA dashboard."""
        model = self.system_model(force_refresh=True)
        narrative = self.self_narrative(depth="executive")
        anomalies = self._detect_anomalies(model)
        rca = self.root_cause_analysis()
        improve = self._self_improve(model)

        self._last_snapshot_ts = datetime.now(timezone.utc).isoformat()

        return {
            "system_model": model,
            "narrative": narrative,
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "critical_count": sum(1 for a in anomalies if a.get("severity") == "critical"),
            "warning_count": sum(1 for a in anomalies if a.get("severity") == "warning"),
            "root_cause_analyses": rca,
            "improvements": improve,
            "improvement_count": len(improve),
            "ts": self._last_snapshot_ts,
        }

    # ═══════════════════════════════════════════════════════════════
    # STATE RESET (for testing)
    # ═══════════════════════════════════════════════════════════════

    def reset_state(self):
        """Reset internal state (for tests)."""
        self._anomaly_history = []
        self._last_snapshot_ts = None


# ══════════════════════════════════════════════════════════════════
# FASTAPI ROUTES
# ══════════════════════════════════════════════════════════════════

__all__ = [
    "SelfAwarenessEngine",
    "_SYSTEM_DEPENDENCIES",
    "_AGENT_CAPABILITIES",
    "_HEALTH_THRESHOLDS",
]


def register_self_awareness_routes(app, require_auth=None, get_db=None):
    """Register Self-Awareness Engine API endpoints on a FastAPI app."""
    from fastapi import Depends

    engine = SelfAwarenessEngine(get_db=get_db)

    @app.get("/api/self-awareness/system-model")
    async def sa_system_model(auth=Depends(require_auth) if require_auth else None):
        """Return the unified system model."""
        return engine.system_model()

    @app.get("/api/self-awareness/narrative")
    async def sa_narrative(
        depth: str = "executive",
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return a self-narrative assessment of the system."""
        return engine.self_narrative(depth=depth)

    @app.get("/api/self-awareness/anomalies")
    async def sa_anomalies(
        severity: str = "",
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return detected anomalies, optionally filtered by severity."""
        return {
            "anomalies": engine.get_anomalies(severity=severity or None),
            "count": len(engine._anomaly_history),
        }

    @app.get("/api/self-awareness/root-cause")
    async def sa_root_cause(
        symptom: str = "",
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return root cause analysis for symptoms or current anomalies."""
        return {"analyses": engine.root_cause_analysis(symptom=symptom)}

    @app.get("/api/self-awareness/improvements")
    async def sa_improvements(auth=Depends(require_auth) if require_auth else None):
        """Return self-improvement suggestions."""
        return {"improvements": engine.get_self_improve()}

    @app.get("/api/self-awareness/snapshot")
    async def sa_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Return the full self-awareness snapshot for the SPA."""
        return engine.snapshot()

    log.info("[self.awareness] Routes registered: /api/self-awareness/*")
