"""
EMPIRE V49 · BRAIN PERSONALITY (Phase 9 + Polish)
===================================================
Operator-configurable brain persona per niche. Defines three base
personalities and manages per-niche overrides (global + per-operator)
stored in Supabase.

ARCHITECTURE
────────────
  BrainPersonality
      │
      ├── Three base profiles: CONSERVATIVE, AGGRESSIVE, BALANCED
      ├── Global per-niche overrides in brain_personality table
      ├── Per-operator overrides in operator_personality table
      ├── Operator preference change history in operator_preference_log
      │
      ├── personality_for_niche(niche, operator_id?)  → profile dict
      ├── build_system_prompt(niche, operator_id?)     → adjusted BRAIN_SYSTEM_PROMPT
      ├── recommended_temperature(niche)               → adjusted temperature
      ├── set_personality(...)                         → update global per-niche config
      ├── set_operator_personality(...)                → update per-operator per-niche config
      ├── remove_operator_personality(...)             → remove per-operator override
      ├── history(niche)                               → operator preference change log
      └── snapshot()                                   → full state for SPA

RESOLUTION ORDER
────────────────
  operator + niche → operator.__global__ → global niche → global.__global__ → default profile

PERSONALITY PROFILES
────────────────────
  CONSERVATIVE:  Stricter GO criteria · higher confidence threshold ·
                 lower urgency floor · more deterministic (low temp).
                 "When in doubt, NO_GO. Reputation > revenue."

  AGGRESSIVE:    Looser GO criteria · lower confidence threshold ·
                 higher urgency floor · more exploratory (higher temp).
                 "When uncertain, lean GO with lower confidence."

  BALANCED:      Default · moderate criteria · standard thresholds.
                 "Assess each lead on its merits — no systematic bias."
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("empire.brain.personality")


# ─────────────────────────────────────────────────────────────────────────────
# PERSONALITY PROFILES
# ─────────────────────────────────────────────────────────────────────────────

PERSONALITY_PROFILES = {
    "conservative": {
        "label": "Conservative",
        "description": "Strict · low risk · high confidence required",
        "tone_instruction": (
            "You are a CONSERVATIVE decision engine. Be strict in your criteria. "
            "Only return GO when ALL of the following are clearly true:\n"
            "  1. Storm severity is Severe or Extreme\n"
            "  2. Target is clearly commercial/industrial "
            "(warehouse, distribution, logistics, manufacturing, retail)\n"
            "  3. At least one working contact channel is confirmed\n"
            "  4. Geographic match to the storm area is strong\n\n"
            "When in doubt, NO_GO. Reputation damage from wrong outreach "
            "outweighs the revenue from a marginal lead. A single complaint "
            "can cost more than 100 missed opportunities.\n"
            "Default to NO_GO unless you are highly confident."
        ),
        "confidence_threshold": 0.75,   # minimum confidence to call it GO
        "urgency_floor": 6,              # minimum urgency score (1-10)
        "temperature": 0.05,             # very deterministic
        "go_fallback": "NO_GO",          # what to return on error/uncertainty
    },
    "aggressive": {
        "label": "Aggressive",
        "description": "Expansive · higher volume · accepts more risk",
        "tone_instruction": (
            "You are an AGGRESSIVE decision engine. You prioritize volume "
            "and speed. Return GO if:\n"
            "  1. Storm severity is Moderate or higher\n"
            "  2. Target COULD be commercial (warehouse, retail, office, "
            "mixed-use, apartment complex with commercial units)\n"
            "  3. Any contact channel exists (phone, email, website, "
            "social media, or even a contact form)\n"
            "  4. Geographic overlap with the storm area is plausible\n\n"
            "It's better to reach out and discover the lead is wrong than "
            "to miss a high-value opportunity. Volume is how we find the "
            "winners. A 10% hit rate with 1000 calls beats a 50% hit rate "
            "with 50 calls.\n"
            "When uncertain, lean GO with appropriately reduced confidence."
        ),
        "confidence_threshold": 0.40,   # lower bar for GO
        "urgency_floor": 3,              # lower minimum urgency
        "temperature": 0.25,             # more variation in reasoning
        "go_fallback": "GO",             # what to return on error/uncertainty
    },
    "balanced": {
        "label": "Balanced",
        "description": "Default · moderate risk · standard criteria",
        "tone_instruction": (
            "You are a BALANCED decision engine. Assess each lead on its "
            "merits with no systematic bias toward GO or NO_GO.\n\n"
            "Favor GO when:\n"
            "  - Storm severity is Severe or Extreme\n"
            "  - Target is commercial/industrial\n"
            "  - Contact channel exists\n"
            "  - Geographic match is strong\n\n"
            "Favor NO_GO when:\n"
            "  - Property is clearly non-commercial\n"
            "  - Storm is Minor only\n"
            "  - No contact channels at all\n"
            "  - Duplicate or already-processed\n\n"
            "Weigh the evidence and decide. There is no systematic bias."
        ),
        "confidence_threshold": 0.60,   # middle ground
        "urgency_floor": 5,              # default urgency minimum
        "temperature": 0.10,             # slight variation
        "go_fallback": "NO_GO",          # safe default
    },
}

# Cache the module-level profile references for fast lookup
PROFILE_KEYS = set(PERSONALITY_PROFILES.keys())
VALID_PERSONAS = list(PERSONALITY_PROFILES.keys())


# ─────────────────────────────────────────────────────────────────────────────
# THE PERSONALITY ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class BrainPersonality:
    """
    Manages per-niche brain personalities with operator-configurable overrides.
    Supports global (system-wide) overrides and per-operator overrides that
    take precedence.
    """

    def __init__(
        self,
        *,
        get_db: Callable,
        default_persona: str = "balanced",
    ):
        self.get_db = get_db
        self.default_persona = default_persona if default_persona in PROFILE_KEYS else "balanced"
        self.stats = {
            "configs_loaded": 0,
            "operator_configs_loaded": 0,
            "preferences_logged": 0,
            "errors": 0,
        }
        # In-memory cache: niche -> profile dict (global overrides from brain_personality)
        self._cache: dict[str, dict] = {}
        self._cache_loaded = False
        # Per-operator cache: operator_id -> {niche -> profile dict}
        self._op_cache: dict[str, dict[str, dict]] = {}
        self._op_cache_loaded = False

    # ── GLOBAL CACHE MANAGEMENT ────────────────────────────────────────
    def _load_cache(self):
        """Load all active global personality configs from Supabase into memory."""
        if self._cache_loaded:
            return
        try:
            db = self.get_db()
            res = db.table("brain_personality").select("*") \
                .eq("is_active", True).execute()
            for row in (res.data or []):
                niche = row.get("niche", "__global__")
                self._cache[niche] = self._row_to_profile(row)
            self.stats["configs_loaded"] = len(self._cache)
            self._cache_loaded = True
        except Exception as e:
            log.warning(f"[brain.personality] cache load failed: {e}")
            self.stats["errors"] += 1

    def _row_to_profile(self, row: dict) -> dict:
        """Convert a DB row to a standard profile dict."""
        persona = row.get("persona", self.default_persona)
        base = PERSONALITY_PROFILES.get(persona, PERSONALITY_PROFILES[self.default_persona])
        return {
            "persona": persona,
            "confidence_threshold": float(row.get("confidence_threshold") or
                base["confidence_threshold"]),
            "urgency_floor": int(row.get("urgency_floor") or
                base["urgency_floor"]),
            "temperature": float(row.get("temperature") or
                base["temperature"]),
            "custom_prompt_suffix": row.get("custom_prompt_suffix", "") or "",
            "operator_notes": row.get("operator_notes", "") or "",
        }

    def _invalidate_cache(self):
        """Force cache reload on next access."""
        self._cache_loaded = False
        self._cache.clear()

    # ── OPERATOR CACHE MANAGEMENT ──────────────────────────────────────
    def _load_operator_cache(self):
        """Load all active operator personality overrides into memory."""
        if self._op_cache_loaded:
            return
        try:
            db = self.get_db()
            res = db.table("operator_personality").select("*") \
                .eq("is_active", True).execute()
            for row in (res.data or []):
                op_id = row.get("operator_id", "")
                niche = row.get("niche", "__global__")
                if op_id not in self._op_cache:
                    self._op_cache[op_id] = {}
                self._op_cache[op_id][niche] = self._row_to_profile(row)
            self.stats["operator_configs_loaded"] = sum(
                len(niches) for niches in self._op_cache.values()
            )
            self._op_cache_loaded = True
        except Exception as e:
            log.warning(f"[brain.personality] operator cache load failed: {e}")
            self.stats["errors"] += 1

    def _invalidate_operator_cache(self):
        """Force operator cache reload on next access."""
        self._op_cache_loaded = False
        self._op_cache.clear()

    # ── PROFILE RESOLUTION ─────────────────────────────────────────────
    def personality_for_niche(
        self,
        niche: str,
        operator_id: Optional[str] = None,
    ) -> dict:
        """
        Return the effective personality profile for a given niche.

        Resolution order:
          1. operator + niche          (per-operator per-niche override)
          2. operator.__global__       (operator global default)
          3. global niche              (system-wide per-niche override)
          4. global.__global__         (system global default)
          5. hardcoded default profile (balanced)
        """
        self._load_cache()
        override = None
        persona_name = self.default_persona

        # Level 1: operator + niche
        if operator_id:
            self._load_operator_cache()
            op_configs = self._op_cache.get(operator_id, {})
            if niche in op_configs:
                override = op_configs[niche]

        # Level 2: operator.__global__
        if override is None and operator_id:
            self._load_operator_cache()
            op_configs = self._op_cache.get(operator_id, {})
            if "__global__" in op_configs:
                override = op_configs["__global__"]

        # Level 3: global niche
        if override is None and niche in self._cache:
            override = self._cache[niche]

        # Level 4: global.__global__
        if override is None and "__global__" in self._cache:
            override = self._cache["__global__"]

        # Resolve persona from override, or default
        if override:
            persona_name = override.get("persona", self.default_persona)

        # Get the base profile
        base = PERSONALITY_PROFILES.get(persona_name, PERSONALITY_PROFILES[self.default_persona])
        profile = dict(base)

        # Apply overrides from DB (any field explicitly set)
        if override:
            for key in ("confidence_threshold", "urgency_floor", "temperature", "custom_prompt_suffix"):
                if key in override and override[key]:
                    profile[key] = override[key]

        profile["persona"] = persona_name
        profile["niche"] = niche
        # Determine the source of the override for UI visibility
        if operator_id and override:
            op_configs = self._op_cache.get(operator_id, {})
            if niche in op_configs:
                profile["override_source"] = "operator"
            elif "__global__" in op_configs:
                profile["override_source"] = "operator_global"
            else:
                profile["override_source"] = "global"
        else:
            profile["override_source"] = "global"
        return profile

    def build_system_prompt(self, niche: str, base_prompt: str = "",
                            operator_id: Optional[str] = None) -> str:
        """
        Build the brain system prompt adjusted for the niche's personality.
        Accepts optional operator_id for per-operator overrides.
        Replaces the default BE_CONSERVATIVE instruction with the personality's
        tone instruction, and appends any custom prompt suffix.
        """
        profile = self.personality_for_niche(niche, operator_id=operator_id)
        tone = profile.get("tone_instruction", "")

        if not base_prompt:
            base_prompt = (
                "You are the decision engine for a B2B storm-damage "
                "lead-generation system. Given a storm alert and a target "
                "business, decide whether to enroll them in outreach.\n\n"
                "Return ONLY valid JSON with these keys:\n"
                "  - decision: \"GO\" or \"NO_GO\"\n"
                "  - confidence: float 0.0-1.0\n"
                "  - reasoning: one sentence explaining your decision\n"
            )

        # Remove any existing "Be conservative" instruction from base
        marker = "Be conservative"
        if marker in base_prompt:
            idx = base_prompt.find(marker)
            end_of_line = base_prompt.find("\n", idx)
            if end_of_line == -1:
                end_of_line = len(base_prompt)
            else:
                end_of_line += 1
            base_clean = (base_prompt[:idx] + base_prompt[end_of_line:]).strip()
        else:
            base_clean = base_prompt.strip()

        custom_suffix = profile.get("custom_prompt_suffix", "")
        suffix_block = f"\n\nOperator note: {custom_suffix}" if custom_suffix else ""

        return f"{base_clean}\n\n{tone}{suffix_block}"

    def recommended_temperature(self, niche: str,
                                 operator_id: Optional[str] = None) -> float:
        """Return the LLM temperature to use for this niche."""
        profile = self.personality_for_niche(niche, operator_id=operator_id)
        return float(profile.get("temperature", 0.1))

    def confidence_threshold(self, niche: str,
                              operator_id: Optional[str] = None) -> float:
        """Return the minimum confidence to consider a GO for this niche."""
        profile = self.personality_for_niche(niche, operator_id=operator_id)
        return float(profile.get("confidence_threshold", 0.6))

    def go_fallback(self, niche: str,
                     operator_id: Optional[str] = None) -> str:
        """Return the fallback decision when brain is unavailable."""
        profile = self.personality_for_niche(niche, operator_id=operator_id)
        return profile.get("go_fallback", "NO_GO")

    # ── MUTATION: SET GLOBAL PERSONALITY ───────────────────────────────
    async def set_personality(
        self,
        *,
        niche: str,
        persona: str,
        operator_id: str = "",
        confidence_threshold: Optional[float] = None,
        urgency_floor: Optional[int] = None,
        temperature: Optional[float] = None,
        custom_prompt_suffix: str = "",
        operator_notes: str = "",
    ) -> dict:
        """
        Set or update the global personality config for a niche.
        Logs the change to operator_preference_log.
        """
        if persona not in VALID_PERSONAS:
            return {"ok": False, "error": f"Invalid persona: {persona}. Valid: {VALID_PERSONAS}"}

        # Fetch existing config for diff
        try:
            db = self.get_db()
            res = db.table("brain_personality").select("*") \
                .eq("niche", niche).limit(1).execute()
            existing = res.data[0] if res.data else {}
        except Exception:
            existing = {}

        now_iso = datetime.now(timezone.utc).isoformat()
        profile = PERSONALITY_PROFILES[persona]
        update_data = {
            "niche": niche,
            "persona": persona,
            "updated_at": now_iso,
            "confidence_threshold": confidence_threshold if confidence_threshold is not None else profile["confidence_threshold"],
            "urgency_floor": urgency_floor if urgency_floor is not None else profile["urgency_floor"],
            "temperature": temperature if temperature is not None else profile["temperature"],
            "custom_prompt_suffix": custom_prompt_suffix,
            "operator_notes": operator_notes,
            "is_active": True,
        }

        try:
            db = self.get_db()
            db.table("brain_personality").upsert(
                update_data, on_conflict="niche"
            ).execute()
            await self._log_preference_changes(niche, operator_id, existing, update_data)
            self._invalidate_cache()
            return {"ok": True, "niche": niche, "persona": persona}
        except Exception as e:
            log.error(f"[brain.personality] set failed: {e}")
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)}

    # ── MUTATION: SET OPERATOR PERSONALITY ─────────────────────────────
    async def set_operator_personality(
        self,
        *,
        operator_id: str,
        niche: str,
        persona: str,
        confidence_threshold: Optional[float] = None,
        urgency_floor: Optional[int] = None,
        temperature: Optional[float] = None,
        custom_prompt_suffix: str = "",
    ) -> dict:
        """
        Set or update a per-operator personality override.
        Does NOT log to operator_preference_log (that's for global changes only).
        """
        if not operator_id:
            return {"ok": False, "error": "operator_id required"}
        if persona not in VALID_PERSONAS:
            return {"ok": False, "error": f"Invalid persona: {persona}. Valid: {VALID_PERSONAS}"}

        profile = PERSONALITY_PROFILES[persona]
        now_iso = datetime.now(timezone.utc).isoformat()
        update_data = {
            "operator_id": operator_id,
            "niche": niche,
            "persona": persona,
            "updated_at": now_iso,
            "custom_prompt_suffix": custom_prompt_suffix,
            "is_active": True,
        }
        if confidence_threshold is not None:
            update_data["confidence_threshold"] = confidence_threshold
        if urgency_floor is not None:
            update_data["urgency_floor"] = urgency_floor
        if temperature is not None:
            update_data["temperature"] = temperature

        try:
            db = self.get_db()
            db.table("operator_personality").upsert(
                update_data, on_conflict="operator_id,niche"
            ).execute()
            self._invalidate_operator_cache()
            return {"ok": True, "operator_id": operator_id, "niche": niche, "persona": persona}
        except Exception as e:
            log.error(f"[brain.personality] set operator failed: {e}")
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)}

    # ── MUTATION: REMOVE OPERATOR PERSONALITY ─────────────────────────
    async def remove_operator_personality(
        self,
        *,
        operator_id: str,
        niche: str,
    ) -> dict:
        """Remove a per-operator personality override (set is_active=False)."""
        if not operator_id:
            return {"ok": False, "error": "operator_id required"}
        try:
            db = self.get_db()
            db.table("operator_personality").update({"is_active": False}) \
                .eq("operator_id", operator_id).eq("niche", niche).execute()
            self._invalidate_operator_cache()
            return {"ok": True, "operator_id": operator_id, "niche": niche}
        except Exception as e:
            log.error(f"[brain.personality] remove operator failed: {e}")
            return {"ok": False, "error": str(e)}

    # ── PREFERENCE LOGGING ─────────────────────────────────────────────
    async def _log_preference_changes(
        self, niche: str, operator_id: str,
        existing: dict, update_data: dict
    ):
        """Log changed fields to operator_preference_log."""
        if not operator_id:
            return
        field_map = [
            ("persona", str(update_data.get("persona", "")),
             str(existing.get("persona", ""))),
            ("confidence_threshold", str(update_data.get("confidence_threshold", "")),
             str(existing.get("confidence_threshold", ""))),
            ("urgency_floor", str(update_data.get("urgency_floor", "")),
             str(existing.get("urgency_floor", ""))),
            ("temperature", str(update_data.get("temperature", "")),
             str(existing.get("temperature", ""))),
        ]
        try:
            db = self.get_db()
            for field_name, new_val, old_val in field_map:
                if new_val != old_val:
                    db.table("operator_preference_log").insert({
                        "operator_id": operator_id,
                        "niche": niche,
                        "field": field_name,
                        "old_value": old_val,
                        "new_value": new_val,
                    }).execute()
                    self.stats["preferences_logged"] += 1
        except Exception as e:
            log.debug(f"[brain.personality] preference log: {e}")

    # ── HISTORY ────────────────────────────────────────────────────────
    async def history(self, niche: str = "", limit: int = 50) -> list:
        """Return operator preference change history, optionally filtered by niche."""
        try:
            db = self.get_db()
            q = db.table("operator_preference_log").select(
                "created_at, operator_id, niche, field, old_value, new_value"
            ).order("created_at", desc=True).limit(min(limit, 200))
            if niche:
                q = q.eq("niche", niche)
            return q.execute().data or []
        except Exception as e:
            log.debug(f"[brain.personality] history fetch: {e}")
            return []

    # ── OPERATOR SNAPSHOT ─────────────────────────────────────────────
    def operator_snapshot(self, operator_id: str) -> dict:
        """Return per-operator override snapshot for the SPA."""
        self._load_operator_cache()
        op_configs = self._op_cache.get(operator_id, {})
        return {
            "operator_id": operator_id,
            "overrides": dict(op_configs),
            "override_count": len(op_configs),
        }

    # ── FULL SNAPSHOT ─────────────────────────────────────────────────
    def snapshot(self) -> dict:
        """Full snapshot for the SPA dashboard with global + operator data."""
        self._load_cache()
        configs = dict(self._cache)

        # Ensure global default is always present
        if "__global__" not in configs:
            global_profile = PERSONALITY_PROFILES[self.default_persona]
            configs["__global__"] = {
                "persona": self.default_persona,
                "confidence_threshold": global_profile["confidence_threshold"],
                "urgency_floor": global_profile["urgency_floor"],
                "temperature": global_profile["temperature"],
                "custom_prompt_suffix": "",
                "operator_notes": "Default profile - no override set",
            }

        # Build a system prompt preview for the default niche
        prompt_preview = self.build_system_prompt("__global__")

        return {
            "configs": configs,
            "profiles_available": VALID_PERSONAS,
            "profile_details": {
                k: {
                    "label": v["label"],
                    "description": v["description"],
                    "confidence_threshold": v["confidence_threshold"],
                    "temperature": v["temperature"],
                    "urgency_floor": v["urgency_floor"],
                    "go_fallback": v["go_fallback"],
                    "tone_instruction": v["tone_instruction"],
                }
                for k, v in PERSONALITY_PROFILES.items()
            },
            "stats": self.stats,
            "default_persona": self.default_persona,
            "prompt_preview": prompt_preview[:500] + "..." if len(prompt_preview) > 500 else prompt_preview,
        }
