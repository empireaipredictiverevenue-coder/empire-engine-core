"""
EMPIRE V49 · SYNTHETIC INTELLIGENCE STRATEGY EVOLUTION
========================================================
Each lane strategy has a genome of traits. As outcomes flow in through the
SI core, strategies get scored. Underperformers get mutated (exploration).
Consistent winners get reinforced (exploitation).

This creates an evolutionary loop: strategies compete, and over time the
system converges on the best approaches for each niche/region.

Archetypes (initial strategy DNA):
  AGGRESSIVE_STRIKE:  high risk, high outreach, aggressive
  UGLY_BANNER:        low risk, medium outreach, conservative  
  RECALL_SNIPER:      medium-high risk, high outreach, targeted
  FINANCIAL_STRIKE:   medium-high risk, medium outreach, aggressive
  STANDARD:           balanced (fallback)

Strategy Genome:
  - aggressiveness:   0.0-1.0  (how hard to push)
  - risk_tolerance:   0.0-1.0  (willingness to try borderline leads)
  - outreach_intensity: 0.0-1.0 (frequency/volume of outreach)
  - price_premium:    0.0-1.0  (willingness to bid higher for ad placement)
  - narrow_focus:     0.0-1.0  (0=cast wide net, 1=ultra-targeted)

Supabase table (created by migration):
  si_strategies:
    - id: uuid PK
    - name: text (e.g. "AGGRESSIVE_STRIKE")
    - niche: text
    - aggressiveness: numeric
    - risk_tolerance: numeric
    - outreach_intensity: numeric
    - price_premium: numeric
    - narrow_focus: numeric
    - runs: int (how many outcomes evaluated)
    - wins: int
    - total_revenue: numeric
    - current_score: numeric
    - parent_strategy: text (which archetype it evolved from)
    - generation: int (how many mutation cycles it's been through)
    - is_active: boolean
    - created_at: timestamptz
    - updated_at: timestamptz
"""

import json
import logging
import os
import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional, Any

log = logging.getLogger("empire.si.strategy")


# ── STRATEGY GENOME MUTATION CONFIG ──────────────────────────────────────
MUTATION_RATE = 0.15        # probability any single trait mutates
MUTATION_MAGNITUDE = 0.15   # max shift per mutation (in trait units)
EXPLORATION_FRACTION = 0.1  # how many new strategies we create when evolving
MIN_SAMPLES_FOR_EVOLUTION = 10  # need this many outcomes before evolving
MIN_SAMPLES_FOR_CONFIDENCE = 20  # need this many before discarding a strategy
WIN_RATE_TO_KEEP = 0.15     # below this, strategy gets discarded


GENOME_TRAITS = ["aggressiveness", "risk_tolerance", "outreach_intensity",
                 "price_premium", "narrow_focus"]

# Pain point traits are PREfixed with "pp_" and loaded dynamically from
# the PainPointLibrary. The evolve() method ignores pp_ traits during
# random mutation (they're managed by PainPointLibrary.record_outcome).
PAIN_POINT_TRAIT_PREFIX = "pp_"


# ── BASE STRATEGY DNA ─────────────────────────────────────────────────────
def _clone_dna(archetype: str) -> dict:
    """Return a fresh copy of the archetype's genome."""
    base = {
        "AGGRESSIVE_STRIKE": {"aggressiveness": 0.9, "risk_tolerance": 0.7, "outreach_intensity": 0.9, "price_premium": 0.8, "narrow_focus": 0.3},
        "UGLY_BANNER":       {"aggressiveness": 0.4, "risk_tolerance": 0.3, "outreach_intensity": 0.6, "price_premium": 0.2, "narrow_focus": 0.5},
        "RECALL_SNIPER":     {"aggressiveness": 0.7, "risk_tolerance": 0.5, "outreach_intensity": 0.8, "price_premium": 0.5, "narrow_focus": 0.8},
        "FINANCIAL_STRIKE":  {"aggressiveness": 0.8, "risk_tolerance": 0.6, "outreach_intensity": 0.7, "price_premium": 0.7, "narrow_focus": 0.4},
        "STANDARD":          {"aggressiveness": 0.5, "risk_tolerance": 0.5, "outreach_intensity": 0.5, "price_premium": 0.5, "narrow_focus": 0.5},
    }
    return dict(base.get(archetype, base["STANDARD"]))


class StrategyEvolution:
    """
    Manages strategy genomes, scores them from outcomes, and evolves them.

    Each strategy variant is tracked per-niche. When a strategy
    underperforms, we mutate it to explore new territory. When it
    overperforms, it becomes the baseline for its niche.
    """

    # Module-level singleton reference. hub.py assigns the live instance here
    # at startup so empire_mission_control (and any other read-only consumer)
    # can call get_shared_instance() instead of monkey-patching the class.
    _shared_instance: Optional["StrategyEvolution"] = None

    @classmethod
    def get_shared_instance(cls) -> Optional["StrategyEvolution"]:
        """Return the hub's live StrategyEvolution instance, or None if not wired."""
        return cls._shared_instance

    @classmethod
    def set_shared_instance(cls, instance: "StrategyEvolution") -> None:
        """
        Register the hub's live StrategyEvolution as the shared singleton.

        Call this once at startup (e.g. `StrategyEvolution.set_shared_instance(si_strategy)`)
        so any module can read the live instance via `get_shared_instance()`.
        Passing `None` clears the registration.
        """
        cls._shared_instance = instance

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        # strategy_id → {name, niche, genome, runs, wins, revenue, score, generation, parent, is_active}
        self._strategies: dict[str, dict] = {}
        # (niche, strategy_name) → strategy_id for fast lookup
        self._lookup: dict[tuple[str, str], str] = {}
        # Generation counter per niche
        self._generations: dict[str, int] = defaultdict(int)
        self._evolution_runs = 0
        self._last_evolution_ts: Optional[str] = None
        self._evolution_events: list[dict] = []  # recent evolution event history
        # Pain point reference — wired by hub.py after PainPointLibrary is created
        self._pain_points: Optional[Any] = None
        self._seed_strategies()

    def _seed_strategies(self):
        """Create initial strategy entries from the archetypes."""
        for archetype in ["AGGRESSIVE_STRIKE", "UGLY_BANNER", "RECALL_SNIPER",
                          "FINANCIAL_STRIKE", "STANDARD"]:
            sid = f"base_{archetype.lower()}"
            dna = _clone_dna(archetype)
            self._strategies[sid] = {
                "id": sid,
                "name": archetype,
                "genome": dna,
                "runs": 0,
                "wins": 0,
                "total_revenue": 0.0,
                "score": 0.0,
                "generation": 0,
                "parent": archetype,
                "is_active": True,
            }
            self._lookup[("__base__", archetype)] = sid

    # ── RECORD OUTCOME ────────────────────────────────────────────────────
    def record_outcome(self, strategy_name: str, niche: str, success: bool, revenue: float = 0):
        """
        Called by the SI core when an outcome flows in.
        Updates the strategy's score.
        """
        # Find or create a niche-specific variant
        key = (niche, strategy_name)
        sid = self._lookup.get(key)

        if not sid:
            # Clone base strategy for this niche
            base_sid = self._lookup.get(("__base__", strategy_name))
            if base_sid:
                base = self._strategies[base_sid]
                dna = dict(base["genome"])
            else:
                dna = _clone_dna(strategy_name)

            sid = f"evolved_{strategy_name.lower()}_{niche.lower().replace(' ','_')}_{self._generations[niche]}"
            self._strategies[sid] = {
                "id": sid,
                "name": strategy_name,
                "niche": niche,
                "genome": dna,
                "runs": 0,
                "wins": 0,
                "total_revenue": 0.0,
                "score": 0.0,
                "generation": 0,
                "parent": strategy_name,
                "is_active": True,
            }
            self._lookup[key] = sid

        s = self._strategies[sid]
        s["runs"] += 1
        if success:
            s["wins"] += 1
        s["total_revenue"] += revenue

        # Score = win rate * revenue factor * confidence (sample count)
        win_rate = s["wins"] / s["runs"] if s["runs"] > 0 else 0
        avg_revenue = s["total_revenue"] / s["runs"] if s["runs"] > 0 else 0
        confidence = min(1.0, s["runs"] / MIN_SAMPLES_FOR_CONFIDENCE)
        # Revenue bonus: scales score up for high-revenue outcomes
        revenue_bonus = min(2.0, avg_revenue / 100.0) if avg_revenue > 0 else 1.0
        s["score"] = win_rate * revenue_bonus * confidence

        # ── Pain point effectiveness bonus ──────────────────────
        # Strategies in niches with high-performing pain points get a
        # score multiplier, making them more likely to be selected and
        # less likely to be deactivated.
        if self._pain_points and niche != "__base__":
            try:
                pp_traits = self._pain_points.get_genome_traits(niche)
                if pp_traits:
                    avg_pp_weight = sum(pp_traits.values()) / max(len(pp_traits), 1)
                    # Multiplier: 0.9 (worst pain points) to 1.15 (best)
                    pp_bonus = 0.85 + (0.35 * avg_pp_weight)
                    s["score"] = s["score"] * pp_bonus
            except Exception:
                pass

    # ── EVOLVE ────────────────────────────────────────────────────────────
    async def evolve(self, niche: Optional[str] = None) -> list[dict]:
        """
        Run one evolution cycle. For each niche with enough data:
        1. Find the best-performing strategy
        2. Mark strategies below the keep threshold as inactive
        3. Create mutated variants of the best strategy (exploration)

        Fetches dream risk_flags from Dream Memory to adjust deactivation
        aggressiveness when risks are detected.

        Returns list of evolution events.
        """
        events = []
        # Fetch dream risk_flags via API (reduces Supabase dependency)
        dream_risk_flags = []
        try:
            import httpx
            base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{base}/api/dream/si-feed")
            if r.status_code == 200:
                data = r.json()
                if data.get("risk_flags") and not data.get("stale"):
                    dream_risk_flags = data["risk_flags"]
        except Exception:
            pass

        # Dream risk flags can adjust evolution aggressiveness
        adjusted_keep_threshold = WIN_RATE_TO_KEEP
        if dream_risk_flags:
            adjusted_keep_threshold = min(0.95, WIN_RATE_TO_KEEP + (len(dream_risk_flags) * 0.05))
            log.info(f"[si.strategy] dream has {len(dream_risk_flags)} risk flags → raising deactivation threshold to {adjusted_keep_threshold}")

        # Group strategies by niche
        niches: dict[str, list[dict]] = defaultdict(list)
        for sid, s in self._strategies.items():
            if not s.get("is_active", True):
                continue
            n = s.get("niche", "__base__")
            if niche and n != niche and n != "__base__":
                continue
            niches[n].append(s)

        for n, strategies in niches.items():
            if n == "__base__":
                continue

            # Need enough total data across the niche
            total_runs = sum(s["runs"] for s in strategies)
            if total_runs < MIN_SAMPLES_FOR_EVOLUTION:
                continue

            # Find best score
            scored = [(s["score"], s) for s in strategies if s["runs"] >= 3]
            if not scored:
                continue
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_strat = scored[0]

            # Deactivate low-performers (only if enough samples to be confident)
            deactivated = []
            for score, s in scored[1:]:
                if score < adjusted_keep_threshold and s["runs"] >= MIN_SAMPLES_FOR_CONFIDENCE:
                    s["is_active"] = False
                    deactivated.append(s["name"])

            # Create mutated variants of the best strategy
            self._generations[n] += 1
            gen = self._generations[n]
            new_count = max(1, int(EXPLORATION_FRACTION * len(strategies)))

            for i in range(new_count):
                new_dna = dict(best_strat["genome"])
                for trait in GENOME_TRAITS:
                    if random.random() < MUTATION_RATE:
                        shift = random.uniform(-MUTATION_MAGNITUDE, MUTATION_MAGNITUDE)
                        new_dna[trait] = max(0.0, min(1.0, new_dna[trait] + shift))

                new_name = f"{best_strat['name']}_gen{gen}"
                new_sid = f"evolved_{best_strat['name'].lower()}_{n.lower().replace(' ','_')}_gen{gen}_{i}"
                self._strategies[new_sid] = {
                    "id": new_sid,
                    "name": new_name,
                    "niche": n,
                    "genome": new_dna,
                    "runs": 0,
                    "wins": 0,
                    "total_revenue": 0.0,
                    "score": 0.0,
                    "generation": gen,
                    "parent": best_strat["name"],
                    "is_active": True,
                }
                self._lookup[(n, new_name)] = new_sid
                log.info(f"[si.strategy] evolved {new_name} for {n} (gen {gen})")
                events.append({
                    "type": "evolve",
                    "niche": n,
                    "new_strategy": new_name,
                    "parent": best_strat["name"],
                    "generation": gen,
                    "dna": new_dna,
                })

            if deactivated:
                log.info(f"[si.strategy] deactivated {deactivated} for {n} (below threshold)")
                events.append({
                    "type": "deactivate",
                    "niche": n,
                    "deactivated": deactivated,
                })

        if events:
            self._evolution_runs += 1
            self._last_evolution_ts = datetime.now(timezone.utc).isoformat()
            # Stamp events with timestamp for history
            ts = self._last_evolution_ts
            for ev in events:
                ev["ts"] = ts
            self._evolution_events.extend(events)
            # Cap at 100 to prevent unbounded growth
            if len(self._evolution_events) > 100:
                self._evolution_events = self._evolution_events[-100:]

        # Cross-lane transfer learning: seed globally best strategy into underperforming niches
        all_scored = [s for s in self._strategies.values() if s.get("is_active") and s["runs"] >= MIN_SAMPLES_FOR_CONFIDENCE]
        if all_scored:
            global_best = max(all_scored, key=lambda x: x["score"])
            for n, strategies in niches.items():
                if n == "__base__" or n == global_best["niche"]:
                    continue
                niche_best_score = max((s["score"] for s in strategies), default=0)
                if global_best["score"] > niche_best_score * 1.2:
                    self._generations[n] += 1
                    gen = self._generations[n]
                    new_name = f"XFER_{global_best['name']}_gen{gen}"
                    new_sid = f"evolved_{new_name.lower()}_{n.lower().replace(' ','_')}"
                    self._strategies[new_sid] = {
                        "id": new_sid, "name": new_name, "niche": n,
                        "genome": dict(global_best["genome"]),
                        "runs": 0, "wins": 0, "total_revenue": 0.0, "score": 0.0,
                        "generation": gen, "parent": global_best["name"], "is_active": True,
                    }
                    self._lookup[(n, new_name)] = new_sid
                    events.append({"type": "cross_pollinate", "from": global_best["niche"], "to": n, "strategy": new_name})

        return events

    # ── GET BEST STRATEGY FOR NICHE ──────────────────────────────────────
    def best_for_niche(self, niche: str) -> Optional[str]:
        """Return the name of the best active strategy for a niche."""
        best = None
        best_score = -1
        for sid, s in self._strategies.items():
            if s.get("niche") != niche or not s.get("is_active", True):
                continue
            if s["score"] > best_score and s["runs"] >= 3:
                best_score = s["score"]
                best = s["name"]
        return best

    # ── GET DANCE FOR STRATEGY ───────────────────────────────────────────

    def get_niche_win_rate(self, niche: str) -> float:
        """Return the win rate (0.0-1.0) of the best active strategy for a niche.
        
        Used by the AI Closer to dynamically adjust routing thresholds.
        High win rate -> lower thresholds (more aggressive calling).
        Low win rate -> raise thresholds (more conservative).
        """
        best = self.best_for_niche(niche)
        if not best:
            return 0.0
        key = (niche, best)
        sid = self._lookup.get(key)
        if sid and self._strategies[sid]["runs"] > 0:
            return min(1.0, self._strategies[sid]["wins"] / self._strategies[sid]["runs"])
        return 0.0

    # ── PAIN POINT GENOME INTEGRATION ───────────────────────────────
    def set_pain_points(self, pain_points: Any) -> None:
        """Wire the PainPointLibrary so strategy genomes include pain point weights."""
        self._pain_points = pain_points

    def get_genome_with_pain_points(self, strategy_name: str, niche: str = "__base__") -> dict:
        """Return the strategy genome merged with pain point weights for this niche.
        
        Used by the AI Closer's _select_strategy to choose strategies that
        align with the best-performing pain points for a niche.
        """
        genome = self.get_genome(strategy_name, niche)
        if self._pain_points and niche != "__base__":
            try:
                pp_traits = self._pain_points.get_genome_traits(niche)
                genome.update(pp_traits)
            except Exception:
                pass
        return genome

    def get_genome(self, strategy_name: str, niche: str = "__base__") -> dict:
        """Return the genome for a strategy, with fallback to base archetype."""
        key = (niche, strategy_name)
        sid = self._lookup.get(key)
        if sid and sid in self._strategies:
            return dict(self._strategies[sid]["genome"])

        # Fallback to base
        base_key = ("__base__", strategy_name)
        base_sid = self._lookup.get(base_key)
        if base_sid and base_sid in self._strategies:
            return dict(self._strategies[base_sid]["genome"])

        return _clone_dna(strategy_name)

    # ── SNAPSHOT ──────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        """Full strategy evolution snapshot for dashboard."""
        active = [s for s in self._strategies.values() if s.get("is_active", True)]
        inactive = [s for s in self._strategies.values() if not s.get("is_active", True)]

        # Group by niche
        by_niche = defaultdict(list)
        for s in active:
            n = s.get("niche", "__base__")
            by_niche[n].append({
                "id": s["id"],
                "name": s["name"],
                "runs": s["runs"],
                "wins": s["wins"],
                "win_rate": round(s["wins"] / s["runs"], 3) if s["runs"] > 0 else 0,
                "score": round(s["score"], 3),
                "generation": s["generation"],
                "parent": s["parent"],
                "genome": s["genome"],
            })

        return {
            "evolution_runs": self._evolution_runs,
            "last_evolution_ts": self._last_evolution_ts,
            "active_strategies": len(active),
            "inactive_strategies": len(inactive),
            "by_niche": dict(by_niche),
            "best_per_niche": {
                n: {"name": self.best_for_niche(n), "score": max(
                    (s["score"] for s in active if s.get("niche") == n), default=0
                )}
                for n in set(s.get("niche", "") for s in active if s.get("niche"))
            },
            "evolution_events": list(reversed(self._evolution_events[-50:])),  # newest first, last 50
        }
