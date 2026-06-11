"""
EMPIRE V49 · SYNTHETIC INTELLIGENCE ADAPTIVE ENGINE
====================================================
Reads learned parameters from the SI Core and applies them to
every subsystem: brain, buyer routing, matching, corridor, outreach.

This is the bridge between what the SI learns and what the system does.

Unlinke the brain_learning module (which runs nightly), this engine
applies parameter changes in real-time as the SI adjusts them.

Supabase table (created by migration):
  si_parameters:
    - key: text PK (e.g. "brain.min_urgency")
    - current_value: numeric
    - default_value: numeric
    - min: numeric
    - max: numeric
    - samples: int
    - confidence: numeric
    - updated_at: timestamptz
    - updated_by: text ('si' | 'operator' | 'agi')

  si_adaptation_log:
    - id: uuid PK
    - parameter_key: text
    - old_value: numeric
    - new_value: numeric
    - trigger: text ('outcome' | 'meta_cog' | 'operator' | 'agi')
    - outcome_id: text (optional, links to the outcome that triggered this)
    - created_at: timestamptz
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

log = logging.getLogger("empire.si.adaptive")


class AdaptiveEngine:
    """
    Reads SI parameters and pushes them to subsystem consumers.

    Each subsystem (brain, switchboard, matching, corridor) registers
    a getter and setter for its parameters. The adaptive engine polls
    the SI core and applies changes.

    This is the glue layer: SI core learns → AdaptiveEngine propagates.
    """

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        # Registered subsystem configurators: key → {"apply": callable, "read": callable}
        self._subsystems: dict[str, dict] = {}
        self._adoption_log: list[dict] = []
        self._max_log = 500
        self._adaptations_applied = 0
        self._last_apply_ts: Optional[str] = None

    # ── REGISTER A SUBSYSTEM CONFIGURATOR ────────────────────────────────
    def register_subsystem(
        self,
        name: str,
        apply_fn: Callable[[str, Any], bool],
        read_fn: Optional[Callable[[str], Any]] = None,
    ):
        """
        Register a subsystem that can have its parameters adjusted.

        apply_fn(key, value) → bool — applies a parameter change.
        read_fn(key) → value — reads current value (optional).
        """
        self._subsystems[name] = {"apply": apply_fn, "read": read_fn}
        log.info(f"[si.adaptive] registered subsystem: {name}")

    def _get_subsystem(self, key: str) -> Optional[str]:
        """Determine which subsystem owns a parameter key (prefix match)."""
        prefix_map = {
            "brain.": "brain",
            "buyer.": "switchboard",
            "matching.": "matching",
            "corridor.": "corridor",
            "outreach.": "outreach",
        }
        for prefix, sub_name in prefix_map.items():
            if key.startswith(prefix):
                return sub_name
        return None

    # ── APPLY PARAMETER CHANGES ──────────────────────────────────────────
    def adopt_parameters(self, si_params: dict) -> list[dict]:
        """
        Called regularly (e.g., every 60s in the overseer loop or on feedback).
        Reads all parameters from SI, compares with subsystem current values,
        and applies any differences.

        Returns: list of changes applied.
        """
        changes = []
        for key, param in si_params.items():
            if not isinstance(param, dict):
                continue
            target_val = param.get("current")
            if target_val is None:
                continue
            sub_name = self._get_subsystem(key)
            if not sub_name or sub_name not in self._subsystems:
                continue
            subsystem = self._subsystems[sub_name]
            read_fn = subsystem.get("read")
            # Get current value from subsystem if available
            if read_fn:
                try:
                    current_val = read_fn(key)
                    if current_val is not None and abs(float(current_val) - float(target_val)) < 0.01:
                        continue  # already applied
                except Exception:
                    pass  # can't read, try applying anyway
            # Apply the change
            try:
                apply_fn = subsystem["apply"]
                success = apply_fn(key, target_val)
                if success:
                    changes.append({
                        "key": key,
                        "value": target_val,
                        "subsystem": sub_name,
                    })
                    self._adaptations_applied += 1
                    log.debug(f"[si.adaptive] {sub_name}.{key} → {target_val}")
            except Exception as e:
                log.warning(f"[si.adaptive] apply failed {sub_name}.{key}: {e}")

        if changes:
            self._adoption_log.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "changes": changes,
                "count": len(changes),
            })
            if len(self._adoption_log) > self._max_log:
                self._adoption_log = self._adoption_log[-self._max_log:]
            self._last_apply_ts = datetime.now(timezone.utc).isoformat()

        return changes

    # ── PERSIST PARAMETERS VIA HTTP ─────────────────────────────────────────
    async def persist_parameters(self, si_params: dict):
        """Write current SI parameter state via HTTP endpoint (avoids Supabase dep)."""
        import os as _os
        try:
            import httpx
        except ImportError:
            log.warning("[si.adaptive] httpx not available, skip persist")
            return
        try:
            base = _os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
            async with httpx.AsyncClient(timeout=10.0) as _client:
                r = await _client.post(f"{base}/api/si/parameters", json={"parameters": si_params})
                if r.status_code >= 400:
                    log.warning(f"[si.adaptive] persist HTTP {r.status_code}: {r.text[:120]}")
                else:
                    result = r.json()
                    log.info(f"[si.adaptive] persisted {result.get('upserted', 0)} parameters via HTTP")
        except Exception as e:
            log.warning(f"[si.adaptive] persist HTTP failed: {e}")

    # ── SNAPSHOT ──────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        return {
            "subsystems_registered": list(self._subsystems.keys()),
            "adaptations_applied": self._adaptations_applied,
            "last_apply_ts": self._last_apply_ts,
            "recent_changes": self._adoption_log[-10:][::-1],
        }

    # ── DB PERSISTENCE FOR ADAPTATION LOG ─────────────────────────────────
    async def log_adaptation(self, parameter_key: str, old_value: float,
                              new_value: float, trigger: str = "outcome",
                              outcome_id: Optional[str] = None):
        """Write a single adaptation event to Supabase."""
        if not self.get_db:
            return
        try:
            db = self.get_db()
            db.table("si_adaptation_log").insert({
                "parameter_key": parameter_key,
                "old_value": old_value,
                "new_value": new_value,
                "trigger": trigger,
                "outcome_id": outcome_id,
            }).execute()
        except Exception:
            pass


# ── SUBSYSTEM CONFIGURATORS (injectable into the adaptive engine) ────────
# Each subsystem needs a small configurator that maps SI parameter keys
# to actual in-memory or DB configuration.
#
# These are provided as reference. To wire them, call:
#   adaptive_engine.register_subsystem("brain", *brain_configurator(si_core))
#   adaptive_engine.register_subsystem("switchboard", *switchboard_configurator())
#   adaptive_engine.register_subsystem("matching", *matching_configurator())
