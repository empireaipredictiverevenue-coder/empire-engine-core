"""
EMPIRE V49 · AGI REVENUE OPTIMIZER
====================================
Autonomous agent. Feeds revenue accuracy stats to the local LLM (Ollama)
every hour and applies suggested parameter adjustments to the predictive
revenue engine's calibration state.

Tunes: close_rate, commission_assumptions, lane priority weights,
        forecast confidence decay, and niche-specific adjustments.

Wire-up: Added to main.py AGENTS list as 'agi_revenue'.
Run standalone: `python bots/agi_revenue.py`
"""

import os
import sys
import json
import time as _time
import asyncio
import logging
from datetime import datetime, timezone

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("agi.revenue")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://localhost:11434")
INTERVAL     = int(os.environ.get("AGI_REVENUE_INTERVAL_SEC", "3600"))

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)

def _get_si_strategy_stats() -> dict:
    """Gather SI strategy evolution metrics for the AGI prompt.
    Retries fetching the singleton on every call (non-cached) so it
    becomes available as soon as hub.py wires it.
    """
    si_module = None
    try:
        from empire_si_strategy import StrategyEvolution
        si_module = StrategyEvolution.get_shared_instance()
    except ImportError:
        log.warning("[agi.revenue] empire_si_strategy not available — skipping SI stats")

    if si_module is None:
        return {}

    try:
        snap = si_module.snapshot()
        best = snap.get("best_per_niche", {})
        by_niche = snap.get("by_niche", {})
        evolution_events = snap.get("evolution_events", [])

        # Build per-niche SI metrics
        niche_metrics = {}
        for niche_name, strategies in by_niche.items():
            if niche_name == "__base__":
                continue
            active = [s for s in strategies if s.get("runs", 0) > 0]
            if not active:
                continue
            best_strat = max(active, key=lambda s: s["score"])
            niche_metrics[niche_name] = {
                "best_strategy": best_strat["name"],
                "win_rate": best_strat["win_rate"],
                "score": best_strat["score"],
                "runs": best_strat["runs"],
                "generation": best_strat["generation"],
                "active_strategies": len(active),
            }

        # Count recent evolution events (last 5)
        recent_events = []
        for ev in evolution_events[:5]:
            if isinstance(ev, dict):
                recent_events.append({
                    "type": ev.get("type", "?"),
                    "niche": ev.get("niche", ""),
                    "strategy": ev.get("strategy") or ev.get("new_strategy", ""),
                })

        return {
            "evolution_runs": snap.get("evolution_runs", 0),
            "active_strategies": snap.get("active_strategies", 0),
            "inactive_strategies": snap.get("inactive_strategies", 0),
            "best_per_niche": best,
            "niche_metrics": niche_metrics,
            "recent_events": recent_events,
        }
    except Exception as e:
        log.warning(f"[agi.revenue] SI strategy stats failed: {e}")
        return {}


# Lazy import for enrichment quality aggregates (may not be available at import time)
_enrichment_aggregator = None

def _get_enrichment_aggregates() -> dict:
    global _enrichment_aggregator
    if _enrichment_aggregator is None:
        try:
            from scripts.enrich_contractor_agent_reach import compute_enrichment_quality_aggregates
            _enrichment_aggregator = compute_enrichment_quality_aggregates
        except ImportError:
            log.warning("[agi.revenue] enrichment_aggregator not available — skipping enrichment stats")
            _enrichment_aggregator = lambda: {}
    try:
        return _enrichment_aggregator()
    except Exception as e:
        log.warning(f"[agi.revenue] enrichment aggregate query failed: {e}")
        return {}


def _format_enrichment_prompt(enrichment: dict) -> str:
    """Format enrichment quality aggregates into a readable prompt section."""
    if not enrichment or "error" in enrichment or not enrichment.get("archetypes"):
        return "  ENRICHMENT: No enrichment data available yet.\n"

    overall = enrichment.get("overall", {})
    parts = []
    parts.append(
        f"  ENRICHMENT QUALITY:\n"
        f"  Total enriched contractors: {overall.get('total_enriched', 0)}\n"
        f"  Enrichment health (0-1):    {overall.get('enrichment_health', 0.5):.4f}\n"
        f"  Mean overall score (0-1):   {overall.get('mean_overall', 0.5):.4f}\n"
        f"  Mean Bayesian quality:      {overall.get('mean_quality', 0.5):.4f}\n"
    )

    # Per-archetype breakdown
    archetypes = enrichment.get("archetypes", {})
    parts.append("  PER-ARCHETYPE:\n")
    for arch, a_stats in sorted(archetypes.items()):
        cnt = a_stats["count"]
        mo = a_stats["mean_overall"]
        mq = a_stats["mean_quality"]
        pd = a_stats.get("priority_distribution", {})
        h = pd.get("high", 0)
        m = pd.get("medium", 0)
        l = pd.get("low", 0)
        parts.append(
            f"    {arch:25s} n={cnt:4d} · overall={mo:.3f} · quality={mq:.3f} "
            f"· high={h} med={m} low={l}\n"
        )

    return "".join(parts)


def _get_sms_delivery_health() -> dict:
    """Query sms_log for SMS delivery health in the last 24 hours.

    Returns aggregate stats the AGI can use to detect delivery degradation
    and adjust revenue calibration accordingly.
    """
    try:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        r = _sb.table("sms_log").select("delivered").eq("direction", "outbound").gte("created_at", cutoff).execute()
        rows = r.data or []
        if not rows:
            return {"total": 0, "delivered": 0, "failed": 0, "pending": 0, "rate": 0.0}

        total = len(rows)
        delivered = sum(1 for r2 in rows if r2.get("delivered") is True)
        failed = sum(1 for r2 in rows if r2.get("delivered") is False)
        pending = sum(1 for r2 in rows if r2.get("delivered") is None)
        known = delivered + failed
        rate = round(delivered / known, 3) if known > 0 else 0.0

        return {
            "total": total,
            "delivered": delivered,
            "failed": failed,
            "pending": pending,
            "rate": rate,
        }
    except Exception as e:
        log.debug(f"[agi.revenue] sms delivery health query failed: {e}")
        return {"total": 0, "delivered": 0, "failed": 0, "pending": 0, "rate": 0.0}


def _format_delivery_prompt(delivery: dict) -> str:
    """Format SMS delivery health into a readable prompt section."""
    if not delivery or delivery.get("total", 0) == 0:
        return "  SMS DELIVERY: No delivery data available yet.\n"

    parts = []
    parts.append(
        f"  SMS DELIVERY HEALTH (24h):\n"
        f"  Total outbound:     {delivery['total']}\n"
        f"  Delivered:          {delivery['delivered']}\n"
        f"  Failed:             {delivery['failed']}\n"
        f"  Pending (unknown):  {delivery['pending']}\n"
        f"  Delivery rate:      {delivery['rate']:.1%}  (delivered / (delivered + failed))\n"
    )
    return "".join(parts)


def _format_si_prompt(si_stats: dict) -> str:
    """Format SI strategy evolution metrics into a readable prompt section."""
    if not si_stats or not si_stats.get("niche_metrics"):
        return "  SI STRATEGIES: No SI evolution data available yet.\n"

    parts = []
    parts.append(
        f"  SI STRATEGY EVOLUTION:\n"
        f"  Evolution runs:        {si_stats.get('evolution_runs', 0)}\n"
        f"  Active strategies:     {si_stats.get('active_strategies', 0)}\n"
        f"  Retired strategies:    {si_stats.get('inactive_strategies', 0)}\n"
    )

    # Per-niche best strategy breakdown
    niche_metrics = si_stats.get("niche_metrics", {})
    if niche_metrics:
        parts.append("  PER-NICHE BEST STRATEGY:\n")
        for n, nm in sorted(niche_metrics.items()):
            win_rate_pct = round(nm["win_rate"] * 100, 1)
            parts.append(
                f"    {n:30s} best={nm['best_strategy'][:20]:20s} "
                f"win_rate={win_rate_pct:5.1f}% score={nm['score']:.3f} "
                f"runs={nm['runs']} gen={nm['generation']}\n"
            )

    # Recent evolution events
    recent = si_stats.get("recent_events", [])
    if recent:
        parts.append("  RECENT EVOLUTION EVENTS:\n")
        for ev in recent:
            parts.append(f"    [{ev.get('type','?')}] {ev.get('niche','')}: {ev.get('strategy','')}\n")

    return "".join(parts)


AGI_SYSTEM = """You are the AGI Revenue Optimizer for Empire AI — a predictive revenue company
running 32 autonomous lead-generation lanes across 4 niches (Roofing Restoration,
Local SEO & HVAC, Mass Tort Legal, Consumer CPA).

Your job: review forecast accuracy stats AND SI strategy evolution metrics and suggest
parameter adjustments to improve the predictive revenue engine's performance.

Available tuning knobs:
  - close_rate: float 0.05-0.60 (probability a lead converts to revenue)
  - commission_rate: float 0.005-0.05 (whale fee percentage)
  - confidence_decay: float 0.5-1.5 (how much to trust the LLM narrative)
  - per_niche_adjustments: dict mapping niche name to close_rate multiplier (0.5-2.0)
  - min_enrichment_quality: float 0.3-0.7 (minimum enrichment score to consider a contractor actionable)
  - si_evolution_rate: float 0.01-0.25 (strategy mutation rate — how fast SI explores new approaches)
  - si_confidence_gate: float 0.3-0.7 (minimum SI score required before SI influences revenue params)

Rules (standard revenue):
  - If accuracy_7d < 0.6: reduce close_rate by 10-20% to be more conservative
  - If accuracy_7d > 0.85: slightly increase close_rate to capture more value
  - If one niche consistently underperforms: reduce its close_rate multiplier
  - If one niche's MRR far exceeds others: boost its close_rate multiplier
  - If enrichment_health is LOW (<0.4): reduce min_enrichment_quality by 5-15% to avoid starving the pipeline
  - If enrichment_health is HIGH (>0.7): increase min_enrichment_quality by 5-10% to filter for better data
  - If an archetype has LOW mean_quality (<0.4): reduce that archetype's effective close_rate contribution

Rules (SI-aware):
  - If a niche's SI best strategy has WIN_RATE > 0.6: boost that niche's close_rate multiplier by 10-20%
  - If a niche's SI best strategy has WIN_RATE < 0.2: reduce that niche's close_rate multiplier by 10-15%
  - If SI evolution is generating mutants FASTER than outcomes can evaluate (many creations, few runs):
    reduce si_evolution_rate to slow evolution until more outcomes accumulate
  - If a niche has NO SI data yet: keep its close_rate at default, don't boost or cut
  - If SI has retired many strategies (>20% inactive): rate of evolution may be too aggressive — reduce si_evolution_rate
  - If SI shows consistent improvement across generations (score increasing): keep si_evolution_rate steady

Rules (crossover — SI to revenue):
  - When si_confidence_gate is met (SI best_score >= gate), use SI win rates to influence per-niche multipliers
  - When si_confidence_gate is NOT met, ignore SI metrics and use only revenue + enrichment data

Rules (SMS delivery-aware):
  - If delivery_rate < 0.5 (under 50%): increase confidence_decay by 10-20%
    (less trust in forecast because SMS outreach isn't reaching contractors)
  - If delivery_rate < 0.2 (under 20%): increase confidence_decay by 15-25%
    AND reduce close_rate by 5-10% (delivery failure is actively hurting conversions)
  - If delivery_rate > 0.9 (over 90%): slightly reduce confidence_decay by 5-10%
    (SMS pipeline is healthy, forecasts are trustworthy)
  - If delivery_rate is 0.0 (no data yet): no changes to delivery-related params
  - If failed count is HIGH (>50) relative to delivered: delivery channel is degrading —
    flag in reasoning but don't change params yet (may be a transient issue)
  - Never move any parameter by more than 25% in one tick
  - Default close_rate is 0.15, commission_rate is 0.03, min_enrichment_quality is 0.5
  - Default confidence_decay is 1.0 (neutral)

Return ONLY JSON: {"close_rate": float, "commission_rate": float, "confidence_decay": float,
                    "per_niche": {"Nicole Name": float, ...},
                    "min_enrichment_quality": float,
                    "si_evolution_rate": float,
                    "si_confidence_gate": float,
                    "reasoning": "one sentence why"}
"""


def _load_calibration() -> dict:
    """Load current calibration state from the revenue engine."""
    try:
        from bots.predictive_revenue import _REVENUE_CALIBRATION
        return dict(_REVENUE_CALIBRATION)
    except Exception:
        return {"close_rate": 0.15, "commission_rate": 0.03, "confidence_decay": 1.0,
                "min_enrichment_quality": 0.5, "si_evolution_rate": 0.15,
                "si_confidence_gate": 0.4,
                "accuracy_7d": 0.0, "samples_7d": 0}


def _apply_calibration(tuned: dict) -> bool:
    """Apply AGI-suggested parameter adjustments to the revenue engine,
    including SI-related tuning knobs.
    """
    try:
        from bots import predictive_revenue as pr

        if "close_rate" in tuned:
            cr = float(tuned["close_rate"])
            cr = max(0.05, min(0.60, cr))
            old = pr._REVENUE_CALIBRATION.get("close_rate", 0.15)
            if old > 0:
                cr = max(old * 0.75, min(old * 1.25, cr))
            pr._REVENUE_CALIBRATION["close_rate"] = round(cr, 4)

        if "commission_rate" in tuned:
            cm = float(tuned["commission_rate"])
            cm = max(0.005, min(0.05, cm))
            old_cm = pr._REVENUE_CALIBRATION.get("commission_rate", 0.03)
            cm = max(old_cm * 0.75, min(old_cm * 1.25, cm))
            pr._REVENUE_CALIBRATION["commission_rate"] = round(cm, 4)
            pr.COMMISSION_RATE = round(cm, 4)

        if "confidence_decay" in tuned:
            cd = float(tuned["confidence_decay"])
            cd = max(0.5, min(1.5, cd))
            pr._REVENUE_CALIBRATION["confidence_decay"] = round(cd, 3)

        if "min_enrichment_quality" in tuned:
            meq = float(tuned["min_enrichment_quality"])
            meq = max(0.3, min(0.7, meq))
            old_meq = pr._REVENUE_CALIBRATION.get("min_enrichment_quality", 0.5)
            meq = max(old_meq * 0.75, min(old_meq * 1.25, meq))
            pr._REVENUE_CALIBRATION["min_enrichment_quality"] = round(meq, 4)

        # ── SI-specific knobs ──
        if "si_evolution_rate" in tuned:
            ser = float(tuned["si_evolution_rate"])
            ser = max(0.01, min(0.25, ser))
            old_ser = pr._REVENUE_CALIBRATION.get("si_evolution_rate", 0.15)
            ser = max(old_ser * 0.75, min(old_ser * 1.25, ser))
            pr._REVENUE_CALIBRATION["si_evolution_rate"] = round(ser, 4)
            # Push to shared SI singleton if available
            try:
                from empire_si_strategy import StrategyEvolution
                si = StrategyEvolution.get_shared_instance()
                if si:
                    log.info(f"[agi.revenue] SI evolution rate adjusted to {ser} — strategy mutation config")
            except Exception:
                pass

        if "si_confidence_gate" in tuned:
            scg = float(tuned["si_confidence_gate"])
            scg = max(0.3, min(0.7, scg))
            old_scg = pr._REVENUE_CALIBRATION.get("si_confidence_gate", 0.4)
            scg = max(old_scg * 0.75, min(old_scg * 1.25, scg))
            pr._REVENUE_CALIBRATION["si_confidence_gate"] = round(scg, 4)

        pr._REVENUE_CALIBRATION["tuned_at"] = datetime.now(timezone.utc).isoformat()
        pr._REVENUE_CALIBRATION["tuned_by"] = "agi_revenue"

        return True
    except Exception as e:
        log.error(f"[agi.revenue] apply calibration failed: {e}")
        return False


def _get_revenue_stats() -> dict:
    """Gather current revenue stats for the AGI prompt, including
    enrichment quality aggregates and SI strategy evolution metrics.
    """
    try:
        from bots.predictive_revenue import per_lane_forecast, _REVENUE_CALIBRATION

        forecast = per_lane_forecast()
        totals = forecast.get("totals", {})
        niche_summary = forecast.get("niche_summary", {})
        health = forecast.get("health", {})

        # Per-niche breakdown
        niche_stats = {}
        for niche, ns in niche_summary.items():
            niche_stats[niche] = {
                "mrr": ns.get("mrr_projected", 0),
                "revenue_24h": ns.get("revenue_24h", 0),
                "buyers": ns.get("active_buyers", 0),
                "calls": ns.get("calls_24h", 0),
            }

        # Enrichment quality aggregates
        enrichment = _get_enrichment_aggregates()
        if enrichment and "error" not in enrichment:
            # Store current aggregates in calibration for trend tracking
            aggs = enrichment.get("overall", {})
            if aggs.get("total_enriched", 0) > 0:
                try:
                    _REVENUE_CALIBRATION["enrichment_total"] = aggs["total_enriched"]
                    _REVENUE_CALIBRATION["enrichment_health"] = aggs["enrichment_health"]
                    _REVENUE_CALIBRATION["enrichment_mean_quality"] = aggs["mean_quality"]
                except Exception:
                    pass

        # SI strategy evolution stats
        si_stats = _get_si_strategy_stats()
        if si_stats and si_stats.get("niche_metrics"):
            # Store SI best scores in calibration for trend tracking
            try:
                best = si_stats.get("best_per_niche", {})
                if best:
                    # Average score across niches
                    scores = [b.get("score", 0) for b in best.values() if isinstance(b, dict)]
                    if scores:
                        _REVENUE_CALIBRATION["si_avg_best_score"] = round(sum(scores) / len(scores), 4)
                _REVENUE_CALIBRATION["si_active_strategies"] = si_stats.get("active_strategies", 0)
                _REVENUE_CALIBRATION["si_evolution_runs"] = si_stats.get("evolution_runs", 0)
            except Exception:
                pass

        # SMS delivery health (from sms_log, no event bus dependency)
        delivery_health = _get_sms_delivery_health()

        return {
            "totals": totals,
            "niche_summary": niche_stats,
            "health": health,
            "calibration": dict(_REVENUE_CALIBRATION),
            "enrichment": enrichment,
            "si_strategy": si_stats,
            "delivery": delivery_health,
        }
    except Exception as e:
        return {"error": str(e)}


async def _ollama_tune(stats: dict) -> dict:
    """Call Ollama LLM for parameter tuning suggestions."""
    import httpx

    prompt = (
        f"REVENUE STATS:\n"
        f"24h Revenue: ${stats.get('totals', {}).get('revenue_24h', 0)}\n"
        f"Projected MRR: ${stats.get('totals', {}).get('mrr_projected', 0)}\n"
        f"Active Lanes: {stats.get('totals', {}).get('lanes_active', 0)}\n"
        f"7d Accuracy: {stats.get('calibration', {}).get('accuracy_7d', 0):.1%}\n"
        f"Current close_rate: {stats.get('calibration', {}).get('close_rate', 0.15)}\n"
        f"Current si_evolution_rate: {stats.get('calibration', {}).get('si_evolution_rate', 0.15)}\n"
        f"Current si_confidence_gate: {stats.get('calibration', {}).get('si_confidence_gate', 0.4)}\n"
        f"Health: {stats.get('health', {}).get('status', '?')} "
        f"({stats.get('health', {}).get('pct_change', 0)}% vs 7d)\n\n"
        f"PER-NICHE:\n"
        + "\n".join(
            f"  {n}: MRR=${s['mrr']} · 24h=${s['revenue_24h']} · buyers={s['buyers']}"
            for n, s in stats.get("niche_summary", {}).items()
        )
        + "\n\n"
        + _format_enrichment_prompt(stats.get("enrichment", {}))
        + "\n\n"
        + _format_si_prompt(stats.get("si_strategy", {}))
        + "\n"
        + _format_delivery_prompt(stats.get("delivery", {}))
        + "\nSuggest parameter adjustments including delivery-aware tuning. JSON only."
    )

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": AGI_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
            )
            r.raise_for_status()
            data = r.json()
            return json.loads(data["message"]["content"])
    except Exception as e:
        log.warning(f"[agi.revenue] LLM tune failed: {e}")
        return {"_error": str(e)}


def run_tick() -> dict:
    """One AGI revenue optimization tick."""
    stats = _get_revenue_stats()
    if "error" in stats:
        return {"action": "error", "message": stats["error"]}

    # Call LLM synchronously (main.py runs in threads)
    tuned = asyncio.run(_ollama_tune(stats))

    if "_error" in tuned:
        log.warning(f"[agi.revenue] tune failed, keeping current params")
        return {"action": "llm_error", "error": tuned.get("_error")}

    # Apply the tuned parameters
    applied = _apply_calibration(tuned)
    reasoning = tuned.get("reasoning", "no reasoning")

    if applied:
        cal = _load_calibration()
        log.info(f"[agi.revenue] tuned: {reasoning}")
        # Build result including SI knobs
        result = {
            "action": "tuned",
            "reasoning": reasoning,
            "new_close_rate": cal.get("close_rate"),
            "new_min_enrichment_quality": cal.get("min_enrichment_quality"),
        }
        si_er = cal.get("si_evolution_rate")
        si_cg = cal.get("si_confidence_gate")
        if si_er is not None:
            result["new_si_evolution_rate"] = si_er
        if si_cg is not None:
            result["new_si_confidence_gate"] = si_cg
        return result
    return {"action": "no_change"}


def run():
    """Background loop — sync entry point for main.py."""
    log.info(f"[agi.revenue] AGI Revenue Optimizer ONLINE · interval={INTERVAL}s")

    # Register in agent_registry
    try:
        _sb.table("agent_registry").upsert({
            "agent_name": "agi.revenue",
            "role_name": "agi_revenue",
            "status": "ACTIVE",
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": json.dumps(["agi", "revenue", "optimizer", "tuning"]),
            "task_types": json.dumps(["revenue.agi_tune", "revenue.calibrate"]),
        }, on_conflict="agent_name").execute()
    except Exception:
        pass

    ticks = 0
    while True:
        try:
            ticks += 1
            result = run_tick()
            log.info(
                f"[agi.revenue] tick {ticks}: {result.get('action')} "
                f"{result.get('reasoning', '')[:100]}"
            )
        except Exception as e:
            log.error(f"[agi.revenue] tick error: {e}")
        _time.sleep(INTERVAL)


if __name__ == "__main__":
    run()
