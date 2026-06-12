import os
import logging
from datetime import datetime, timezone
from typing import Dict, List

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

    def __init__(self):
        self.si = SyntheticIntelligence()

    def check_agent_staleness(self) -> Dict:
        """Query agent_registry. Flag any enabled agent whose last_ping is older
        than 3× its expected interval. Returns {stale: [...], healthy: [...], checked_at}."""
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

    def direct_strategy(self):
        # 1. Check for human intervention
        status = get_manual_override()
        if status.get("mode") == "MANUAL":
            return status.get("strategy", "HOLD")

        # 2. Refresh the cached health snapshot (auto-refresh on every decision)
        #    so /api/governor/health and the SPA always see fresh data without re-querying Supabase.
        try:
            health = refresh_health_snapshot()
        except Exception as e:
            log.warning(f"[agi.governor] snapshot refresh failed: {e}")
            health = {}

        # 3. Staleness gate — if any enabled agent hasn't pinged in 3× its interval, HOLD
        try:
            if health.get("stale"):
                stale_names = [a["agent_name"] for a in health["stale"]]
                log.warning(f"[agi.governor] HOLD — stale agents: {stale_names}")
                return "HOLD"
        except Exception as e:
            log.warning(f"[agi.governor] staleness gate error: {e}")

        # 4. Autonomous AGI Decisioning
        print("[AGI GOVERNOR] Autonomous mode active.")
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
# Run a single decision at import time to log the current strategy. In test
# mode (conftest.py sets EMPIRE_TESTING=1) skip the live Supabase/Ollama query
# so the module is importable without external services — otherwise the
# import would raise and tests using `from empire_agi_governor import ...`
# would silently skip via setUp's self.skipTest().
if os.environ.get("EMPIRE_TESTING") == "1":
    print(f"[AGI] Current Strategy: TEST_MODE (EMPIRE_TESTING=1, skipping direct_strategy)")
else:
    try:
        print(f"[AGI] Current Strategy: {governor.direct_strategy()}")
    except Exception as _e:
        print(f"[AGI] Current Strategy: <unavailable at import time: {_e}>")


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
