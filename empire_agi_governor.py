import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from supabase import create_client

from empire_override import get_manual_override
from empire_si_core import SyntheticIntelligence

log = logging.getLogger("empire.agi.governor")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Map agent_name → expected interval lookup function (returns hours).
# Agents not listed here fall back to AGENT_DEFAULT_INTERVAL_HOURS × 3.
_AGENT_INTERVAL_HOURS = {
    "seo_agent": lambda: _safe_call("bots.seo_agent", "get_seo_interval", 6.0),
    "dream_loop": lambda: _safe_call("empire_dream", "get_dream_interval", 6.0),
    "hourly_digest": lambda: _safe_call("empire_hourly_digest", "get_digest_interval", 3600.0) / 3600.0,
    "voice_streaming_agent": lambda: _safe_call("bots.voice_streaming_agent", "get_streaming_interval", 0.5),
}
AGENT_DEFAULT_INTERVAL_HOURS = 6.0
STALENESS_MULTIPLIER = 3.0


def _safe_call(module_name: str, func_name: str, default: float) -> float:
    """Import a module and call a function, returning `default` on any failure."""
    try:
        import importlib
        mod = importlib.import_module(module_name)
        return float(getattr(mod, func_name)())
    except Exception:
        return float(default)


class AGIGovernor:
    # Class-level slot for the shared StrategyEvolution instance. hub.py
    # assigns the live instance here at startup (now via set_si_strategy()).
    # Kept as a class attribute (not a method) for back-compat with any
    # existing readers that do `AGIGovernor.si_strategy` directly.
    si_strategy = None

    # Class-level slot for the shared SelfAwarenessEngine instance. hub.py
    # assigns the live instance here at startup via set_self_awareness().
    # If None, direct_strategy() falls back to the legacy staleness check.
    self_awareness = None

    @classmethod
    def get_si_strategy(cls):
        """Return the hub's live StrategyEvolution instance, or None if not wired."""
        return cls.si_strategy

    @classmethod
    def set_si_strategy(cls, instance) -> None:
        """
        Register the hub's live StrategyEvolution as the shared singleton.

        Call this once at startup (e.g. `AGIGovernor.set_si_strategy(si_strategy)`)
        so any module can read the live instance via `get_si_strategy()` or the
        legacy `AGIGovernor.si_strategy` class attribute. Passing `None` clears
        the registration.
        """
        cls.si_strategy = instance

    # ── Self-Awareness Engine integration ────────────────────────────

    @classmethod
    def get_self_awareness(cls):
        """Return the live SelfAwarenessEngine instance, or None if not wired."""
        return cls.self_awareness

    @classmethod
    def set_self_awareness(cls, instance) -> None:
        """
        Register the hub's live SelfAwarenessEngine as the shared singleton.

        Call this once at startup (e.g. `AGIGovernor.set_self_awareness(sa_engine)`)
        so the governor can consult the self-awareness layer for anomaly-aware
        strategy decisions. Passing `None` clears the registration (falls back
        to legacy staleness check).
        """
        cls.self_awareness = instance

    def __init__(self):
        self.si = SyntheticIntelligence()
        self._sa_cache_ts: Optional[float] = None
        self._sa_cache_ctx: Optional[Dict] = None
        self._sa_cache_ttl: float = float(os.environ.get("SA_CACHE_TTL_SEC", "60"))

    def check_agent_staleness(self) -> Dict:
        """[LEGACY] Query agent_registry. Flag any enabled agent whose last_ping
        is older than 3× its expected interval.

        Prefer using the SelfAwarenessEngine.get_anomalies() for anomaly-aware
        decision making when self_awareness is wired. This method remains for
        backward compatibility when the SA engine is not available.

        Returns {stale: [...], healthy: [...], checked_at}."""
        result: Dict = {"stale": [], "healthy": [], "checked_at": datetime.now(timezone.utc).isoformat()}
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.warning("[agi.governor] supabase creds missing — skipping staleness check")
            return result
        try:
            sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            r = sb.table("agent_registry") \
                .select("agent_name,status,last_ping,enabled,capabilities") \
                .execute()
            now = datetime.now(timezone.utc)
            for row in (r.data or []):
                if not row.get("enabled", False):
                    continue
                name = row.get("agent_name") or "unknown"
                interval_h = _AGENT_INTERVAL_HOURS.get(name, lambda: AGENT_DEFAULT_INTERVAL_HOURS)()
                max_age_seconds = interval_h * 3600.0 * STALENESS_MULTIPLIER
                ping = row.get("last_ping")
                age = None
                if ping:
                    try:
                        ping_dt = datetime.fromisoformat(ping.replace("Z", "+00:00"))
                        age = (now - ping_dt).total_seconds()
                    except Exception:
                        pass
                entry = {
                    "agent_name": name,
                    "status": row.get("status"),
                    "last_ping": ping,
                    "seconds_since_ping": age,
                    "max_age_seconds": max_age_seconds,
                    "interval_hours": interval_h,
                    "capabilities": row.get("capabilities") or [],
                }
                if age is None or age > max_age_seconds:
                    result["stale"].append(entry)
                else:
                    result["healthy"].append(entry)
        except Exception as e:
            log.warning(f"[agi.governor] staleness check failed: {e}")
        return result

    # ── Self-Awareness consultation ─────────────────────────────────

    def consult_self_awareness(self) -> Dict:
        """Consult the Self-Awareness Engine for anomaly-informed strategy context.

        Queries the SA engine for anomalies, system health, and lane performance.
        Results are cached for _SA_CACHE_TTL_SEC seconds (default 60) to avoid
        excessive Supabase queries on repeated calls within the same decision cycle.

        Returns a dict with:
          anomalies: list of all detected anomalies
          critical_count: number of critical-severity anomalies
          warning_count: number of warning-severity anomalies
          health_overall: 'healthy' | 'degraded' | 'critical'
          agent_health_pct: fraction of agents healthy
          lane_win_rate: overall lane win rate (0.0-1.0)
          wired: True if SA engine is available, False if fallback
        """
        sa = AGIGovernor.get_self_awareness()
        if sa is None:
            return {
                "anomalies": [],
                "critical_count": 0,
                "warning_count": 0,
                "health_overall": "unknown",
                "agent_health_pct": 1.0,
                "lane_win_rate": 1.0,
                "wired": False,
            }

        # TTL cache — avoid rebuilding the full system model on every call
        now_ts = datetime.now(timezone.utc).timestamp()
        if (
            self._sa_cache_ctx is not None
            and self._sa_cache_ts is not None
            and (now_ts - self._sa_cache_ts) < self._sa_cache_ttl
        ):
            return self._sa_cache_ctx

        try:
            # Use the SA engine's public detect_anomalies() with a pre-built model
            # to avoid double-building system_model() inside get_anomalies().
            model = sa.system_model()
            anomalies = sa.detect_anomalies(model)
            health = model.get("health", {})
            lanes = model.get("lanes", {})

            critical = [a for a in anomalies if a.get("severity") == "critical"]
            warnings = [a for a in anomalies if a.get("severity") == "warning"]

            ctx = {
                "anomalies": anomalies,
                "critical_count": len(critical),
                "warning_count": len(warnings),
                "health_overall": health.get("overall", "unknown"),
                "agent_health_pct": health.get("health_pct", 1.0),
                "lane_win_rate": lanes.get("overall_win_rate", 1.0),
                "wired": True,
            }

            # Write-through cache
            self._sa_cache_ctx = ctx
            self._sa_cache_ts = now_ts

            return ctx
        except Exception as e:
            log.warning(f"[agi.governor] self-awareness consultation failed: {e}")
            return {
                "anomalies": [],
                "critical_count": 0,
                "warning_count": 0,
                "health_overall": "error",
                "agent_health_pct": 1.0,
                "lane_win_rate": 1.0,
                "wired": True,
                "error": str(e)[:200],
            }

    def direct_strategy(self):
        """Determine the current global strategy.

        Decision pipeline:
          1. Manual override — if operator has taken manual control, obey.
          2. Self-awareness anomaly gate — if wired, consult the SA engine:
             - Critical anomalies (agent_critical, lane_win_rate_critical) → HOLD
             - Warning anomalies with degraded health → CAUTIOUS_PROCEED
             - Warning anomalies only → AGGRESSIVE_STRIKE (logged)
             - No anomalies → AGGRESSIVE_STRIKE
          3. Legacy staleness fallback — if SA engine is not wired, use the
             old agent_registry staleness check.
          4. Default → AGGRESSIVE_STRIKE
        """
        # 1. Check for human intervention
        status = get_manual_override()
        if status.get("mode") == "MANUAL":
            return status.get("strategy", "HOLD")

        # 2. Self-awareness anomaly gate (if wired)
        sa_ctx = self.consult_self_awareness()
        if sa_ctx.get("wired"):
            critical_count = sa_ctx.get("critical_count", 0)
            warning_count = sa_ctx.get("warning_count", 0)
            health = sa_ctx.get("health_overall", "healthy")
            win_rate = sa_ctx.get("lane_win_rate", 1.0)

            # Critical anomalies → immediate HOLD
            if critical_count > 0:
                critical_types = [a.get("type") for a in sa_ctx.get("anomalies", [])
                                  if a.get("severity") == "critical"]
                log.warning(
                    f"[agi.governor] HOLD — {critical_count} critical anomaly(s): "
                    f"{critical_types}"
                )
                print(f"[AGI GOVERNOR] HOLD — {critical_count} critical anomaly(s) detected by self-awareness")
                return "HOLD"

            # Warning anomalies + degraded health → CAUTIOUS_PROCEED
            if warning_count > 0 and health in ("degraded", "critical"):
                log.warning(
                    f"[agi.governor] CAUTIOUS_PROCEED — {warning_count} warning(s), "
                    f"health={health}, agent_pct={sa_ctx.get('agent_health_pct', 0):.0%}"
                )
                print("[AGI GOVERNOR] CAUTIOUS_PROCEED — degraded health with warnings")
                return "CAUTIOUS_PROCEED"

            # Warning anomalies only with healthy system → AGGRESSIVE but logged
            if warning_count > 0:
                log.info(
                    f"[agi.governor] AGGRESSIVE_STRIKE — {warning_count} warning(s) "
                    f"present but system is {health}"
                )

            # Lane win rate below threshold → still aggressive but log
            if win_rate < 0.15:
                log.warning(
                    f"[agi.governor] AGGRESSIVE_STRIKE — lane win rate "
                    f"({win_rate:.1%}) below threshold but no critical anomalies"
                )

            print(f"[AGI GOVERNOR] AGGRESSIVE_STRIKE — self-aware (health={health}, "
                  f"anomalies: {critical_count} critical, {warning_count} warning, "
                  f"win_rate={win_rate:.0%})")
            return "AGGRESSIVE_STRIKE"

        # 3. Legacy staleness fallback (SA engine not wired)
        try:
            health = refresh_health_snapshot()
        except Exception as e:
            log.warning(f"[agi.governor] snapshot refresh failed: {e}")
            health = {}

        try:
            if health.get("stale"):
                stale_names = [a["agent_name"] for a in health["stale"]]
                log.warning(f"[agi.governor] HOLD — stale agents: {stale_names}")
                return "HOLD"
        except Exception as e:
            log.warning(f"[agi.governor] staleness gate error: {e}")

        # 4. Autonomous AGI Decisioning
        print("[AGI GOVERNOR] Autonomous mode active (legacy staleness check).")
        return "AGGRESSIVE_STRIKE"

    def strategy_for_niche(self, niche: str) -> str:
        """Return the best-performing evolved strategy for a given niche.
        Falls back to AGGRESSIVE_STRIKE if SI strategy engine has no signal yet.
        """
        try:
            si_instance = AGIGovernor.get_si_strategy()
            if si_instance is not None:
                best = si_instance.best_for_niche(niche)
                if best:
                    return best
        except Exception as e:
            log.debug(f"[agi.governor] niche strategy lookup failed: {e}")
        return "AGGRESSIVE_STRIKE"

    def record_strategy_outcome(self, strategy: str, niche: str, success: bool, revenue: float = 0):
        """Feed an outcome back to the SI Strategy Evolution engine."""
        try:
            si_instance = AGIGovernor.get_si_strategy()
            if si_instance is not None:
                si_instance.record_outcome(strategy, niche, success, revenue)
        except Exception as e:
            log.debug(f"[agi.governor] outcome record failed: {e}")

    def get_niche_win_rate(self, niche: str) -> float:
        """Pass-through to SI StrategyEvolution for closer threshold adaptation."""
        try:
            si_instance = AGIGovernor.get_si_strategy()
            if si_instance is not None:
                return si_instance.get_niche_win_rate(niche)
        except Exception:
            pass
        return 0.0


# Cache the latest health snapshot so the SPA /api/agents/status can read it
# without re-querying Supabase on every request.
_last_health_snapshot: Dict = {}


def get_last_health_snapshot() -> Dict:
    """Return the most recent staleness check result, refreshing if empty."""
    global _last_health_snapshot
    if not _last_health_snapshot:
        _last_health_snapshot = governor.check_agent_staleness()
    return _last_health_snapshot


def refresh_health_snapshot() -> Dict:
    """Force a refresh of the staleness snapshot and return the new value."""
    global _last_health_snapshot
    _last_health_snapshot = governor.check_agent_staleness()
    return _last_health_snapshot


governor = AGIGovernor()
# Import-time note: the first strategy decision is deferred to first use
# (lazy) because direct_strategy() queries Supabase synchronously, which
# blocks the event loop and prevents uvicorn from binding. The hub calls
# governor.direct_strategy() explicitly in its startup handler.
#
# In test mode (EMPIRE_TESTING=1) skip everything.
if os.environ.get("EMPIRE_TESTING") == "1":
    print(f"[AGI] Current Strategy: TEST_MODE (EMPIRE_TESTING=1, strategy deferred)")
else:
    print(f"[AGI] Governor initialized. Strategy decision deferred to first use.")


def get_local_brain(task_type):
    """
    Routes tasks to the optimal local model based on intent.
    qwen2.5-coder:14b: Complex Architecture & Code
    llama3.1:latest: Strategic Logic & Negotiation
    llama3.2:3b: High-Speed Outreach & Mining
    """
    if task_type == "code":
        return "qwen2.5-coder:14b"
    elif task_type == "negotiation":
        return "llama3.1:latest"
    else:
        return "llama3.2:3b"


print(f"[GOVERNOR] Brain routing initialized. Ready to execute Strategy Strike.")
