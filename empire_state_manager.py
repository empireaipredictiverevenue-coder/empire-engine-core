"""
EMPIRE V49 · STATE MANAGER
==========================
Supabase-backed state for the storm orchestrator.
Replaces the file-based JSON state of the demo stub.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable

log = logging.getLogger("empire.state")


class StateManager:
    """
    Tracks:
      - which warehouses we've already enrolled (dedup)
      - strike_log rows
      - storm_state row (autonomy + counters)
    """

    def __init__(self, get_db: Callable):
        self._get_db = get_db

    # ── state row ────────────────────────────────────────────────
    def get_state(self) -> Dict:
        try:
            db = self._get_db()
            r = db.table("storm_state").select("*").eq("id", 1).limit(1).execute()
            return (r.data or [{}])[0]
        except Exception as e:
            log.error(f"[state] get_state failed: {e}")
            return {}

    def update_state(self, patch: Dict):
        try:
            db = self._get_db()
            patch["updated_at"] = datetime.now(timezone.utc).isoformat()
            db.table("storm_state").update(patch).eq("id", 1).execute()
        except Exception as e:
            log.error(f"[state] update_state failed: {e}")

    def is_paused(self) -> bool:
        s = self.get_state()
        return not s.get("autonomy_enabled", True)

    def pause(self, reason: str):
        self.update_state({
            "autonomy_enabled": False,
            "paused_reason": reason,
            "paused_at": datetime.now(timezone.utc).isoformat(),
        })
        log.warning(f"[state] PAUSED: {reason}")

    def resume(self):
        self.update_state({
            "autonomy_enabled": True,
            "paused_reason": None,
            "paused_at": None,
        })
        log.info("[state] RESUMED")

    # ── dedup ────────────────────────────────────────────────────
    def has_processed_target(self, name: str, lat: float, lon: float) -> bool:
        """Check radar_targets for an existing entry matching this warehouse."""
        try:
            db = self._get_db()
            # match on name (case-insensitive) within ~100m
            r = (
                db.table("radar_targets")
                .select("id")
                .ilike("address", f"%{name}%")
                .limit(1)
                .execute()
            )
            return bool(r.data)
        except Exception as e:
            log.error(f"[state] has_processed_target failed: {e}")
            return False

    # ── radar_targets ────────────────────────────────────────────
    def stage_target(self, target: Dict, source: str = "storm_trigger") -> Optional[str]:
        """
        Insert a new target into radar_targets. Returns the new uuid or None.
        Skips if already present (dedup by address+name).
        """
        try:
            db = self._get_db()
            name = target.get("warehouse_name") or "Unknown"
            addr = target.get("address") or f"{target.get('lat')},{target.get('lon')}"
            row = {
                "address": addr,
                "phone": target.get("phone"),
                "email": target.get("email"),
                "source_url": target.get("website"),
                "city": target.get("city"),
                "location": f"POINT({target.get('lon')} {target.get('lat')})" if target.get("lat") else None,
                "status": "active",
                "damage_severity": target.get("severity"),
                "urgency_score": target.get("urgency_score"),
                "meta": {
                    "source": source,
                    "warehouse_name": name,
                    "raw": target.get("raw_tags"),
                },
            }
            r = db.table("radar_targets").insert(row).execute()
            new_id = (r.data or [{}])[0].get("id")
            return new_id
        except Exception as e:
            log.error(f"[state] stage_target failed for {target.get('warehouse_name')}: {e}")
            return None

    # ── strike_log ───────────────────────────────────────────────
    def log_strike(self, target_id: Optional[str], alert_summary: Dict, distance_km: Optional[float] = None,
                   niche: Optional[str] = None, strategy: Optional[str] = None) -> Optional[str]:
        """Insert a strike_log row tying a target to an alert.
        `niche` and `strategy` are written into the meta dict (the column
        doesn't exist in the base schema) so the SI Strategy Evolution
        engine can read them back on outcome via get_strike_strategy()."""
        try:
            db = self._get_db()
            meta = dict(alert_summary or {})
            if niche is not None:
                meta["niche"] = niche
            if strategy is not None:
                meta["strategy"] = strategy
            row = {
                "target_id": target_id,
                "alert_event": alert_summary.get("event"),
                "alert_area": alert_summary.get("area"),
                "severity": alert_summary.get("severity"),
                "distance_km": distance_km,
                "dispatch_status": "pending",
                "meta": meta,
            }
            r = db.table("strike_log").insert(row).execute()
            return (r.data or [{}])[0].get("id")
        except Exception as e:
            log.error(f"[state] log_strike failed: {e}")
            return None

    def update_strike_status(self, strike_id: str, status: str, extra_meta: Optional[Dict] = None):
        try:
            db = self._get_db()
            patch: Dict = {"dispatch_status": status}
            if extra_meta:
                # Merge extra_meta into the existing meta (don't overwrite)
                try:
                    import json as _j
                    cur = db.table("strike_log").select("meta").eq("id", strike_id).limit(1).execute()
                    existing = (cur.data or [{}])[0].get("meta") or {}
                    if isinstance(existing, str):
                        try: existing = _j.loads(existing)
                        except Exception: existing = {}
                    merged = {**(existing or {}), **(extra_meta or {})}
                    patch["meta"] = merged
                except Exception:
                    pass
            db.table("strike_log").update(patch).eq("id", strike_id).execute()
        except Exception as e:
            log.error(f"[state] update_strike_status failed: {e}")

    def get_strike_strategy(self, target_id: Optional[str] = None,
                            strike_id: Optional[str] = None) -> dict:
        """Look up the niche + strategy used for a strike (by target_id or strike_id).
        Returns {"niche": str|None, "strategy": str|None, "alert_event": str|None}.
        Used by the outcome path to feed record_strategy_outcome() and by the
        voice NCCO to align the script with the chosen strategy.

        Note: never raises. Returns Nones on miss (callers must handle).
        """
        try:
            db = self._get_db()
            q = db.table("strike_log").select("niche,strategy,alert_event,meta,target_id")
            if strike_id:
                q = q.eq("id", strike_id)
            elif target_id:
                q = q.eq("target_id", target_id).order("created_at", desc=True).limit(1)
            else:
                return {"niche": None, "strategy": None, "alert_event": None}
            r = q.execute()
            if not r.data:
                return {"niche": None, "strategy": None, "alert_event": None}
            row = r.data[0]
            # Strategy + niche are stored in the meta dict (no dedicated
            # columns in the base strike_log schema).
            _meta = row.get("meta") or {}
            if isinstance(_meta, str):
                try: _meta = __import__("json").loads(_meta)
                except Exception: _meta = {}
            return {
                "niche":       (_meta or {}).get("niche"),
                "strategy":    (_meta or {}).get("strategy"),
                "alert_event": row.get("alert_event"),
            }
        except Exception as e:
            log.debug(f"[state] get_strike_strategy failed: {e}")
            return {"niche": None, "strategy": None, "alert_event": None}
