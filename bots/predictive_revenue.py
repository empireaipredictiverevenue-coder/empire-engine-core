"""
EMPIRE V49 · PREDICTIVE REVENUE ENGINE
========================================
Company-central nervous system. Feeds every downstream system with
revenue projections, per-lane forecasts, LLM-powered narrative, and
health alerts.

Data flow:  Supabase tables → per_niche aggregation → lane mapping
            → LLM narrative → comprehensive forecast → SPA dashboard
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, "/root/empire-v49")

load_dotenv("/root/.env")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

log = logging.getLogger("predictive.revenue")
logging.basicConfig(level=logging.INFO)

# Base job values (USD) — industry-standard ballpark for restoration leads
BASE_VALUE = {
    "storm damage": 9000, "water damage": 9000, "hail damage": 9000, "roof damage": 9000,
    "solar": 25000, "solar installation": 25000,
    "general repair": 4000, "roof repair": 4000, "repair": 4000, "restoration": 9000,
    "multi-niche": 6000, "multi": 6000, "insurance claim": 9000,
    "default": 6000,
}
COMMISSION_RATE = 0.03  # 3% whale fee (was 1%; bumped 2026-06-13 per Phil)

# ── Lane → Niche mapping (from mesh_orchestrator) ───────────────────
_NICHE_TO_LANES: dict = {}  # niche → [lane_id, ...]
_LANE_TO_NICHE: dict = {}   # lane_id → niche name
try:
    from mesh_orchestrator import LANES as _mesh_lanes
    _grp = defaultdict(list)
    for lid, data in _mesh_lanes.items():
        niche = data.get("niche", "Unknown")
        _grp[niche].append(lid)
        _LANE_TO_NICHE[lid] = niche
    _NICHE_TO_LANES = dict(_grp)
    log.info(f"[revenue] mapped {len(_LANE_TO_NICHE)} lanes → {len(_NICHE_TO_LANES)} niches")
except ImportError:
    # Minimal fallback — 4 niches × 8 lanes each
    for i in range(32):
        if i < 8:
            n = "Roofing Restoration"
        elif i < 16:
            n = "Local SEO & HVAC"
        elif i < 21:
            n = "Mass Tort Legal"
        else:
            n = "Consumer CPA"
        _LANE_TO_NICHE[i] = n
        _NICHE_TO_LANES.setdefault(n, []).append(i)


# ═══════════════════════════════════════════════════════════════════════
#   LEGACY FUNCTIONS (KEPT FOR BACKWARD COMPATIBILITY)
# ═══════════════════════════════════════════════════════════════════════

def get_close_rate():
    """Probability-to-close. Uses AGI-tuned calibration when available;
    falls back to brain_memory outcomes otherwise."""
    # If the AGI revenue optimizer or self-calibration has tuned the rate, use it
    cr = _REVENUE_CALIBRATION.get("close_rate", 0.15)
    tuned_by = _REVENUE_CALIBRATION.get("tuned_by", "default")
    if tuned_by != "default":
        return cr
    # Fallback: compute from brain_memory outcomes
    try:
        res = sb.table("brain_memory").select("outcome").execute()
        rows = res.data or []
        if len(rows) < 10:
            return cr  # use calibration default (0.15)
        closed = sum(1 for r in rows if (r.get("outcome") or "").lower() in ("won","closed","converted"))
        computed = max(0.05, min(0.6, closed / len(rows)))
        # Sync calibration dict so AGI/self-tuning starts from real baseline
        if _REVENUE_CALIBRATION.get("tuned_by") == "default":
            _REVENUE_CALIBRATION["close_rate"] = round(computed, 4)
        return computed
    except Exception:
        return cr


def base_for(keyword):
    """Return estimated job TCV from a damage keyword."""
    if not keyword:
        return BASE_VALUE["default"]
    k = keyword.lower()
    for key, val in BASE_VALUE.items():
        if key in k:
            return val
    return BASE_VALUE["default"]


def score_lead(lead, close_rate=None):
    """Enrich a lead dict with estimated_value + forecasted_revenue."""
    if close_rate is None:
        close_rate = get_close_rate()
    tcv = base_for(lead.get("damage_severity") or (lead.get("meta") or {}).get("keyword") or (lead.get("meta") or {}).get("keyword_matched"))
    intent = lead.get("urgency_score", 5) or 5
    intent_norm = intent / 10.0
    fee = tcv * COMMISSION_RATE * intent_norm * close_rate
    lead["tcv"] = round(tcv, 2)
    lead["forecasted_fee"] = round(fee, 2)
    lead["close_rate_used"] = round(close_rate, 3)
    return lead


def pipeline_forecast():
    """Aggregate TCV + forecasted 3% fee across today's radar_targets.
    Logs to pipeline_health. Kept for backward compatibility with hub.py
    and empire_switchboard.py."""
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        res = sb.table("radar_targets").select("damage_severity,urgency_score,meta").gte("created_at", today).execute()
        rows = res.data or []
        cr = get_close_rate()
        total_tcv = 0
        total_fee = 0
        for r in rows:
            scored = score_lead(dict(r), cr)
            total_tcv += scored["tcv"]
            total_fee += scored["forecasted_fee"]
        result = {
            "lead_count": len(rows),
            "close_rate": round(cr, 3),
            "total_tcv": round(total_tcv, 2),
            "total_forecasted_fee": round(total_fee, 2),
        }
        try:
            sb.table("pipeline_health").insert({
                "total_tcv": result["total_tcv"],
                "total_forecasted_fee": result["total_forecasted_fee"],
                "lead_count": result["lead_count"],
                "close_rate": result["close_rate"],
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            log.warning(f"[revenue] pipeline_health log error: {e}")
        return result
    except Exception as e:
        return {"error": str(e), "lead_count": 0, "total_tcv": 0, "total_forecasted_fee": 0}


# ═══════════════════════════════════════════════════════════════════════
#   ENHANCED REVENUE ENGINE
# ═══════════════════════════════════════════════════════════════════════

_LANE_METRICS_CACHE: dict = {}
_LANE_METRICS_CACHE_TS: float = 0.0
_LANE_METRICS_CACHE_TTL: float = 30.0  # seconds

# Persistent SI strategy instance (accumulates across revenue ticks)
_SI_INSTANCE = None


def get_si_instance():
    """
    Return the hub's live StrategyEvolution instance, or None if not wired.

    Mirrors the StrategyEvolution.get_shared_instance() / AGIGovernor.get_si_strategy()
    pattern so callers can read the shared singleton through a single API.
    """
    return _SI_INSTANCE


def set_si_instance(instance) -> None:
    """
    Register the hub's live StrategyEvolution as this module's shared SI singleton.

    Call this once at startup (e.g. `set_si_instance(si_strategy)`) so the
    `feed_si_evolution()` and adaptive-forecast paths can reuse the hub's
    authoritative instance instead of creating a parallel one. Passing `None`
    clears the registration.

    Symmetric with:
      - StrategyEvolution.set_shared_instance()
      - AGIGovernor.set_si_strategy()
    """
    global _SI_INSTANCE
    _SI_INSTANCE = instance


def get_lane_metrics() -> dict:
    """
    Query call_logs + buyers + payouts, group by niche, then distribute
    metrics to individual lanes. Returns {lane_id: {revenue_24h, mrr_projected,
    active_buyers, avg_payout, calls_24h, fee_24h}} for all 32 lanes.
    
    Results are cached for 30s to avoid hammering Supabase when called by
    per_lane_forecast(), revenue_health_check(), lane_revenue_score(), and
    comprehensive_forecast() in rapid succession.
    """
    import time as _time
    global _LANE_METRICS_CACHE, _LANE_METRICS_CACHE_TS
    
    now_epoch = _time.time()
    if _LANE_METRICS_CACHE and (now_epoch - _LANE_METRICS_CACHE_TS) < _LANE_METRICS_CACHE_TTL:
        return _LANE_METRICS_CACHE
    
    # ── Build fresh metrics ────────────────────────────────────────
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    day_ago_iso = day_ago.isoformat()

    # ── 1. Query recent call_logs ──────────────────────────────────
    call_metrics: dict = {}  # niche → {calls, fee, billable}
    try:
        r = sb.table("call_logs") \
            .select("niche,fee_earned,is_billable") \
            .gte("created_at", day_ago_iso) \
            .limit(1000).execute()
        for row in (r.data or []):
            niche = row.get("niche") or "Unknown"
            m = call_metrics.setdefault(niche, {"calls_24h": 0, "fee_24h": 0.0, "billable_24h": 0})
            m["calls_24h"] += 1
            fee = float(row.get("fee_earned") or 0)
            m["fee_24h"] += fee
            if row.get("is_billable"):
                m["billable_24h"] += 1
    except Exception as e:
        log.warning(f"[revenue] call_logs query failed: {e}")

    # ── 2. Query active buyers ─────────────────────────────────────
    buyer_metrics: dict = {}  # niche → {active_buyers, total_retainer, avg_payout}
    try:
        r = sb.table("buyers").select("niche,base_payout,fee_rate,monthly_retainer,is_active") \
            .eq("is_active", True).limit(200).execute()
        for row in (r.data or []):
            niche = row.get("niche") or "Unknown"
            m = buyer_metrics.setdefault(niche, {"active_buyers": 0, "total_retainer": 0.0, "payouts": []})
            m["active_buyers"] += 1
            m["total_retainer"] += float(row.get("monthly_retainer") or 0)
            m["payouts"].append(float(row.get("base_payout") or 0))
    except Exception as e:
        log.warning(f"[revenue] buyers query failed: {e}")

    # Compute avg_payout per niche
    for niche, m in buyer_metrics.items():
        payouts = m.get("payouts", [])
        m["avg_payout"] = round(sum(payouts) / len(payouts), 2) if payouts else 0.0
        m.pop("payouts", None)  # clean up temp list

    # ── 3. Query recent payouts ────────────────────────────────────
    payout_total: dict = {}  # niche → total_usdc_24h
    try:
        r = sb.table("payout_log").select("amount_usdc,niche") \
            .gte("created_at", day_ago_iso) \
            .eq("status", "completed").limit(200).execute()
        for row in (r.data or []):
            niche = row.get("niche") or "Unknown"
            payout_total[niche] = payout_total.get(niche, 0.0) + float(row.get("amount_usdc") or 0)
    except Exception as e:
        log.warning(f"[revenue] payouts query failed: {e}")

    # ── 4. Query 7-day pipeline_health for trend ───────────────────
    seven_day_avg: dict = {}  # niche → avg_daily_fee
    try:
        week_ago = (now - timedelta(days=7)).isoformat()
        r = sb.table("pipeline_health") \
            .select("total_forecasted_fee,created_at") \
            .gte("created_at", week_ago) \
            .limit(200).execute()
        rows = r.data or []
        if rows:
            total = sum(float(row.get("total_forecasted_fee") or 0) for row in rows)
            seven_day_avg["__global__"] = round(total / max(len(rows), 1), 2)
    except Exception as e:
        log.warning(f"[revenue] pipeline_health trend query failed: {e}")

    # ── 5. Build per-lane output ───────────────────────────────────
    lane_metrics: dict = {}
    for lid in range(32):
        niche = _LANE_TO_NICHE.get(lid, "Unknown")
        cm = call_metrics.get(niche, {})
        bm = buyer_metrics.get(niche, {})

        # Per-lane: divide niche-level metrics by lanes in niche
        lane_count = len(_NICHE_TO_LANES.get(niche, [1]))

        revenue_24h = round(cm.get("fee_24h", 0.0) / lane_count, 2)
        calls_24h = max(1, cm.get("calls_24h", 0)) // lane_count
        active_buyers = bm.get("active_buyers", 0)
        avg_payout = bm.get("avg_payout", 0.0)

        # MRR projected: (avg_payout * calls/day * 22 days * fee_rate) + retainer share
        daily_calls_est = max(1, calls_24h)
        per_call_revenue = avg_payout * COMMISSION_RATE
        mrr_projected = round(
            (per_call_revenue * daily_calls_est * 22)
            + (bm.get("total_retainer", 0.0) / lane_count),
            2
        )

        lane_metrics[lid] = {
            "lane_id": lid,
            "niche": niche,
            "revenue_24h": revenue_24h,
            "mrr_projected": mrr_projected,
            "calls_24h": calls_24h,
            "active_buyers": active_buyers,
            "avg_payout": avg_payout,
            "billable_24h": max(1, cm.get("billable_24h", 0)) // lane_count,
        }

    # ── Cache the result ──────────────────────────────────────────
    _LANE_METRICS_CACHE = lane_metrics
    _LANE_METRICS_CACHE_TS = now_epoch

    return lane_metrics


def per_lane_forecast() -> dict:
    """
    Full per-lane revenue forecast for API and dashboard.
    Returns {lanes: [...], totals: {...}, trend: {...}}.
    """
    lane_metrics = get_lane_metrics()

    # Aggregate totals across all lanes
    total_revenue_24h = sum(m["revenue_24h"] for m in lane_metrics.values())
    total_mrr = sum(m["mrr_projected"] for m in lane_metrics.values())
    total_calls = sum(m["calls_24h"] for m in lane_metrics.values())
    total_buyers = sum(m["active_buyers"] for m in lane_metrics.values())

    # Group by niche for summary
    niche_summary = defaultdict(lambda: {"revenue_24h": 0.0, "mrr": 0.0, "calls": 0, "buyers": 0, "lanes": 0})
    for lid, m in lane_metrics.items():
        n = m["niche"]
        ns = niche_summary[n]
        ns["revenue_24h"] += m["revenue_24h"]
        ns["mrr"] += m["mrr_projected"]
        ns["calls"] += m["calls_24h"]
        ns["buyers"] = m["active_buyers"]  # buyer count is per-niche
        ns["lanes"] += 1

    # Sort lanes by MRR descending
    sorted_lanes = sorted(lane_metrics.values(), key=lambda x: x["mrr_projected"], reverse=True)

    # Health trend
    trend = revenue_health_check(lane_metrics)

    return {
        "lanes": sorted_lanes,
        "niche_summary": {
            n: {
                "niche": n,
                "revenue_24h": round(ns["revenue_24h"], 2),
                "mrr_projected": round(ns["mrr"], 2),
                "calls_24h": ns["calls"],
                "active_buyers": ns["buyers"],
                "lane_count": ns["lanes"],
            }
            for n, ns in sorted(niche_summary.items(), key=lambda x: x[1]["mrr"], reverse=True)
        },
        "totals": {
            "revenue_24h": round(total_revenue_24h, 2),
            "mrr_projected": round(total_mrr, 2),
            "calls_24h": total_calls,
            "active_buyers": total_buyers,
            "lanes_active": sum(1 for m in lane_metrics.values() if m["calls_24h"] > 0 or m["active_buyers"] > 0),
        },
        "health": trend,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def revenue_health_check(lane_metrics: dict = None) -> dict:
    """
    Compare current revenue vs 7-day moving average. Returns alerts
    for any niche where revenue dipped >30% below its 7-day average.
    """
    if lane_metrics is None:
        lane_metrics = get_lane_metrics()

    # Get 7-day average from pipeline_health
    seven_day_avg: dict = {}
    try:
        now = datetime.now(timezone.utc)
        week_ago = (now - timedelta(days=7)).isoformat()
        r = sb.table("pipeline_health") \
            .select("total_forecasted_fee,created_at") \
            .gte("created_at", week_ago) \
            .limit(200).execute()
        rows = r.data or []
        if rows:
            total = sum(float(row.get("total_forecasted_fee") or 0) for row in rows)
            seven_day_avg["__global__"] = round(total / max(len(rows), 1), 2)
    except Exception as e:
        log.warning(f"[revenue] health trend query failed: {e}")

    current_total = round(sum(m["revenue_24h"] for m in lane_metrics.values()), 2)
    avg_7d = seven_day_avg.get("__global__", current_total or 1.0)

    # Percent change from 7-day average
    if avg_7d > 0:
        pct_change = round(((current_total - avg_7d) / avg_7d) * 100, 1)
    else:
        pct_change = 0.0

    alerts = []
    status = "healthy"

    if pct_change < -30:
        status = "critical"
        alerts.append({
            "level": "critical",
            "message": f"Revenue down {abs(pct_change)}% vs 7-day average (${avg_7d}/day → ${current_total})",
        })
    elif pct_change < -15:
        status = "warning"
        alerts.append({
            "level": "warning",
            "message": f"Revenue trending down {abs(pct_change)}% vs 7-day average",
        })
    elif pct_change > 15:
        status = "surging"

    # Per-niche health
    niche_health = {}
    for lid, m in lane_metrics.items():
        niche = m["niche"]
        if niche not in niche_health:
            niche_health[niche] = {"revenue": 0.0, "buyers": 0, "calls": 0}
        niche_health[niche]["revenue"] += m["revenue_24h"]
        niche_health[niche]["buyers"] = m["active_buyers"]
        niche_health[niche]["calls"] += m["calls_24h"]

    for niche, nh in niche_health.items():
        if nh["buyers"] == 0 and nh["calls"] > 0:
            alerts.append({
                "level": "warning",
                "niche": niche,
                "message": f"{niche}: {nh['calls']} calls but 0 active buyers — revenue leak",
            })

    return {
        "status": status,
        "current_24h": current_total,
        "average_7d": round(avg_7d, 2),
        "pct_change": pct_change,
        "alerts": alerts,
    }


def lane_revenue_score(lane_id: int) -> float:
    """
    Single-lane revenue potential score (0-10). Used by AGI Lane Engine
    for lane prioritization. Higher score = more revenue potential.
    """
    try:
        metrics = get_lane_metrics()
        m = metrics.get(lane_id, {})

        # Score components:
        #   - Revenue 24h: 0-4 pts (normalized against $100/day max)
        #   - Active buyers: 0-3 pts (1 pt per buyer, cap 3)
        #   - MRR projected: 0-3 pts (normalized against $5000/mo max)

        rev_score = min(4.0, (m.get("revenue_24h", 0) / 25.0))
        buyer_score = min(3.0, float(m.get("active_buyers", 0)))
        mrr_score = min(3.0, (m.get("mrr_projected", 0) / 1667.0))

        return round(rev_score + buyer_score + mrr_score, 1)
    except Exception:
        return 0.0


def generate_llm_narrative(metrics: dict = None) -> dict:
    """
    Feed lane metrics to local Ollama for a CRO-style narrative forecast.
    Returns {executive_summary, lane_highlights, actionable_advice, risks}.
    Falls back gracefully if Ollama is unreachable.
    """
    if metrics is None:
        metrics = per_lane_forecast()

    totals = metrics.get("totals", {})
    niche_summary = metrics.get("niche_summary", {})
    health = metrics.get("health", {})

    # Build a compact data blob for the LLM
    niche_lines = []
    for niche, ns in niche_summary.items():
        niche_lines.append(
            f"  {niche}: ${ns['revenue_24h']}/24h · ${ns['mrr_projected']}/mo MRR · "
            f"{ns['calls_24h']} calls · {ns['active_buyers']} buyers"
        )

    system = (
        "You are the Chief Revenue Officer of Empire AI, a predictive revenue company "
        "running 32 autonomous lead-generation lanes across 4 niches. "
        "Report to the CEO with a brief, data-driven revenue narrative. "
        "Return ONLY valid JSON with these keys:\n"
        '  "executive_summary": 1-2 sentence top-line, e.g. "24h revenue hit $X driven by Y."\n'
        '  "lane_highlights": ["Niche A: thriving (reason)", "Niche B: concern (reason)"]\n'
        '  "actionable_advice": 1 sentence recommendation\n'
        '  "risks": ["risk 1", "risk 2"]\n'
        "Be concise. Use dollar amounts from the data."
    )

    prompt = (
        f"REVENUE DATA:\n"
        f"Total 24h revenue: ${totals.get('revenue_24h', 0)}\n"
        f"Projected MRR: ${totals.get('mrr_projected', 0)}\n"
        f"Total active buyers: {totals.get('active_buyers', 0)}\n"
        f"Health status: {health.get('status', 'unknown')} "
        f"({health.get('pct_change', 0)}% vs 7d avg)\n"
        f"Alerts: {json.dumps(health.get('alerts', []))}\n\n"
        f"PER-NICHE BREAKDOWN:\n" + "\n".join(niche_lines) + "\n\n"
        f"Generate the CRO narrative. JSON only."
    )

    try:
        import httpx
        ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": system},
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
        log.warning(f"[revenue] LLM narrative failed, using fallback: {e}")
        # Graceful fallback — compute narrative from data
        top_niche = max(niche_summary.items(), key=lambda x: x[1]["mrr_projected"], default=("Unknown", {}))
        return {
            "executive_summary": (
                f"24h revenue: ${totals.get('revenue_24h', 0):,.2f}. "
                f"Projected MRR: ${totals.get('mrr_projected', 0):,.2f}. "
                f"{totals.get('active_buyers', 0)} active buyers across {totals.get('lanes_active', 0)} active lanes."
            ),
            "lane_highlights": [
                f"{top_niche[0]}: ${top_niche[1].get('mrr_projected', 0):,.2f}/mo projected",
            ],
            "actionable_advice": (
                "Focus dispatch on highest-MRR niche. "
                "Verify buyer coverage for lanes with calls but no buyers."
            ),
            "risks": [
                alert["message"] for alert in health.get("alerts", [])[:2]
            ] or ["No active revenue health alerts"],
        }


def comprehensive_forecast() -> dict:
    """
    Master orchestrator: legacy pipeline + per-lane + LLM narrative + health.
    Returns the complete revenue snapshot for the SPA dashboard.
    """
    legacy = pipeline_forecast()
    per_lane = per_lane_forecast()
    # Pass already-fetched lane_metrics to avoid double DB queries
    lane_metrics = per_lane.get("lanes", [])
    
    # Convert back to {lane_id: {...}} format for health check
    metrics_dict = {lm["lane_id"]: lm for lm in lane_metrics}
    health = revenue_health_check(metrics_dict if metrics_dict else None)
    
    narrative = generate_llm_narrative(per_lane)

    return {
        "pipeline": legacy,
        "per_lane": per_lane,
        "health": health,
        "narrative": narrative,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════
#   ADAPTIVE REVENUE BRAIN — Learning & Self-Tuning
# ═══════════════════════════════════════════════════════════════════════
# Stores revenue snapshots as embeddings for few-shot learning,
# compares forecasts vs actuals to self-calibrate, and feeds
# revenue outcomes into SI strategy evolution.

# Module-level calibration state (tuned by AGI and self-correction)
_REVENUE_CALIBRATION: dict = {
    "close_rate": 0.15,           # global close rate (adjusted by learning)
    "commission_rate": 0.01,      # whale fee rate
    "confidence_decay": 1.0,      # how much to trust the LLM narrative
    "tuned_at": None,
    "tuned_by": "default",
    "accuracy_7d": 0.0,           # forecast accuracy over last 7 days
    "samples_7d": 0,
}


def record_revenue_snapshot() -> Optional[str]:
    """
    Record today's revenue metrics as a brain_memory row.
    This enables retrieving past revenue days for trend comparison.
    (Embedding-based similarity search requires pgvector; we fall
    back to recent-snapshot retrieval.)
    Returns the snapshot id if successful.
    """
    try:
        forecast = per_lane_forecast()
        totals = forecast.get("totals", {})
        niche_summary = forecast.get("niche_summary", {})

        # Build context text
        # Also get the pipeline forecast for accuracy comparison
        pipe = pipeline_forecast()

        niche_parts = []
        for niche, ns in sorted(niche_summary.items()):
            niche_parts.append(
                f"{niche}: ${ns.get('revenue_24h', 0)}/24h "
                f"MRR ${ns.get('mrr_projected', 0)} "
                f"buyers={ns.get('active_buyers', 0)}"
            )

        context = (
            f"REVENUE SNAPSHOT | "
            f"total_24h=${totals.get('revenue_24h', 0)} "
            f"MRR=${totals.get('mrr_projected', 0)} "
            f"buyers={totals.get('active_buyers', 0)} "
            f"calls={totals.get('calls_24h', 0)} | "
            + " | ".join(niche_parts)
        )[:2000]

        snoop_row = {
            "context_text": context[:2000],
            "decision": "GO",  # pass brain_memory constraint (GO/NO_GO); marker is in city
            "urgency": int(totals.get("lanes_active", 0) or 0),
            "reasoning": json.dumps({
                "type": "revenue_snapshot",
                "totals": totals,
                "forecasted_fee": pipe.get("total_forecasted_fee", 0),
                "niches": list(niche_summary.keys()),
                "health": forecast.get("health", {}).get("status", "unknown"),
            })[:1000],
            "city": "revenue_snapshot",
            "severity": forecast.get("health", {}).get("status", "neutral"),
            "asset_value": totals.get("mrr_projected", 0),
        }

        r = sb.table("brain_memory").insert(snoop_row).execute()
        snapshot_id = r.data[0]["id"] if r.data else None
        log.info(f"[revenue] snapshot recorded: ${totals.get('revenue_24h', 0)}/24h")
        return snapshot_id
    except Exception as e:
        log.warning(f"[revenue] snapshot record failed: {e}")
        return None


def retrieve_similar_revenue_days(k: int = 5) -> list[dict]:
    """
    Retrieve the k most similar past revenue days from brain_memory.
    Falls back to most-recent revenue snapshots if pgvector not installed.
    """
    try:
        # Try to get recent revenue snapshots
        r = sb.table("brain_memory") \
            .select("context_text,reasoning,created_at,asset_value,severity") \
            .eq("city", "revenue_snapshot") \
            .order("created_at", desc=True) \
            .limit(k * 2).execute()

        rows = r.data or []
        if not rows:
            return []

        # Return most recent (since pgvector ANN may not be installed)
        results = []
        for row in rows[:k]:
            try:
                details = json.loads(row.get("reasoning", "{}"))
            except Exception:
                details = {}
            results.append({
                "ts": (row.get("created_at") or "")[:16],
                "context": row.get("context_text", "")[:300],
                "mrr": float(row.get("asset_value") or 0),
                "health": row.get("severity", "unknown"),
                "totals": details.get("totals", {}),
                "niches": details.get("niches", []),
            })
        return results
    except Exception as e:
        log.debug(f"[revenue] similar days retrieval failed: {e}")
        return []


def render_revenue_few_shot(memories: list[dict]) -> str:
    """Render past revenue snapshots as few-shot context for the LLM."""
    if not memories:
        return ""

    lines = ["", "PAST SIMILAR REVENUE DAYS (for calibration):"]
    for i, m in enumerate(memories, 1):
        lines.append(
            f"  {i}. {m.get('ts', '?')}: ${m.get('mrr', 0):,.0f} MRR "
            f"· health={m.get('health', '?')} "
            f"· niches={m.get('niches', [])}"
        )
    lines.append("")
    lines.append(
        "Use past revenue patterns to calibrate your forecast. "
        "If similar days showed strong revenue, project confidence. "
        "If similar days declined, note the risk."
    )
    return "\n".join(lines)


def adaptive_forecast() -> dict:
    """
    Full adaptive pipeline:
    1. Record today's snapshot to brain_memory
    2. Retrieve similar past days for few-shot context
    3. Generate LLM narrative with few-shot learning
    4. Return comprehensive forecast with adaptation metadata
    """
    # Standard forecast
    result = comprehensive_forecast()

    # Add few-shot learning
    memories = retrieve_similar_revenue_days(k=5)
    few_shot = render_revenue_few_shot(memories)

    if few_shot and result.get("narrative"):
        # Re-generate narrative with few-shot context if we have memories
        try:
            enhanced_narrative = _generate_narrative_with_memory(
                result.get("per_lane", {}),
                few_shot,
            )
            if enhanced_narrative:
                result["narrative"] = enhanced_narrative
        except Exception:
            pass  # keep original narrative

    result["adaptation"] = {
        "few_shot_days": len(memories),
        "calibration": dict(_REVENUE_CALIBRATION),
    }

    return result


def _generate_narrative_with_memory(per_lane: dict, few_shot: str) -> dict | None:
    """Generate LLM narrative with few-shot revenue memory."""
    totals = per_lane.get("totals", {})
    niche_summary = per_lane.get("niche_summary", {})
    health = per_lane.get("health", {})

    niche_lines = []
    for niche, ns in niche_summary.items():
        niche_lines.append(
            f"  {niche}: ${ns['revenue_24h']}/24h · ${ns['mrr_projected']}/mo MRR"
        )

    system = (
        "You are Empire AI's adaptive revenue brain. Use the past revenue patterns "
        "to calibrate your forecast. Note trends, risks, and opportunities. "
        "Return ONLY valid JSON with: executive_summary, lane_highlights, "
        "actionable_advice, risks, trend_analysis (1 sentence)."
    )

    prompt = (
        f"CURRENT REVENUE:\n"
        f"24h: ${totals.get('revenue_24h', 0)} | MRR: ${totals.get('mrr_projected', 0)}\n"
        f"Health: {health.get('status', '?')} ({health.get('pct_change', 0)}% vs 7d)\n\n"
        f"NICHES:\n" + "\n".join(niche_lines) + "\n"
        f"{few_shot}\n"
        f"Generate adaptive forecast. JSON only."
    )

    try:
        import httpx
        ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
            )
            r.raise_for_status()
            data = r.json()
            narrative = json.loads(data["message"]["content"])
            narrative["_adapted"] = True
            return narrative
    except Exception as e:
        log.debug(f"[revenue] adaptive narrative failed: {e}")
        return None


def calibrate_from_actuals() -> dict:
    """
    Compare yesterday's revenue snapshot vs today's actuals.
    Adjust internal close_rate based on revenue prediction accuracy.
    Uses MRR change as a proxy signal — sustained growth suggests
    close_rate may be conservative; sustained decline suggests the opposite.
    """
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()

    # Find yesterday's revenue snapshot
    try:
        r = sb.table("brain_memory") \
            .select("reasoning,asset_value,created_at") \
            .eq("city", "revenue_snapshot") \
            .lte("created_at", day_ago) \
            .order("created_at", desc=True) \
            .limit(2).execute()

        if not r.data or len(r.data) < 2:
            return {"action": "no_data", "message": "Need at least 2 snapshots to calibrate"}

        # Compare the two most recent snapshots
        recent = r.data[0]
        older = r.data[1]

        try:
            recent_totals = json.loads(recent.get("reasoning", "{}")).get("totals", {})
            older_totals = json.loads(older.get("reasoning", "{}")).get("totals", {})
        except Exception:
            return {"action": "no_data", "message": "Could not parse snapshot totals"}

        recent_mrr = float(recent.get("asset_value") or recent_totals.get("mrr_projected", 0))
        older_mrr = float(older.get("asset_value") or older_totals.get("mrr_projected", 0))

        if recent_mrr <= 0 or older_mrr <= 0:
            return {"action": "no_data", "message": "Zero MRR in snapshots"}

        # MRR change ratio
        ratio = recent_mrr / older_mrr

        # Update rolling accuracy tracker based on stability
        old_acc = _REVENUE_CALIBRATION.get("accuracy_7d", 0)
        old_n = _REVENUE_CALIBRATION.get("samples_7d", 0)
        # Accuracy = how close ratio is to 1.0 (stable revenue is good forecasting)
        stability = 1.0 - abs(1.0 - ratio)
        new_acc = round((old_acc * old_n + stability) / (old_n + 1), 3)
        _REVENUE_CALIBRATION["accuracy_7d"] = new_acc
        _REVENUE_CALIBRATION["samples_7d"] = min(old_n + 1, 30)  # cap at 30 samples

        # Adjust close_rate: if recent > older by >20%, we may be under-projecting
        current_cr = _REVENUE_CALIBRATION.get("close_rate", 0.15)
        if ratio > 1.25:
            new_cr = round(current_cr * 1.05, 4)
        elif ratio < 0.75:
            new_cr = round(current_cr * 0.9, 4)
        else:
            new_cr = current_cr

        _REVENUE_CALIBRATION["close_rate"] = max(0.05, min(0.6, new_cr))
        _REVENUE_CALIBRATION["tuned_at"] = now.isoformat()
        _REVENUE_CALIBRATION["tuned_by"] = "self_calibration"

        log.info(
            f"[revenue] calibrated: MRR ratio={ratio:.2f} "
            f"stability={stability:.2f} "
            f"close_rate {current_cr:.3f}→{_REVENUE_CALIBRATION['close_rate']:.3f}"
        )

        return {
            "action": "calibrated",
            "mrr_ratio": round(ratio, 3),
            "stability": round(stability, 3),
            "close_rate_before": current_cr,
            "close_rate_after": _REVENUE_CALIBRATION["close_rate"],
        }
    except Exception as e:
        log.warning(f"[revenue] calibration failed: {e}")
        return {"action": "error", "message": str(e)[:200]}


def feed_si_evolution() -> dict:
    """
    Feed revenue outcomes into the SI strategy evolution engine.
    Revenue dips → strategy failure signal. Revenue surges → strategy win.
    Uses persistent module-level SI instance so strategies accumulate
    outcomes across ticks and actually evolve over time.

    Resolution order:
      1. `get_si_instance()` — return the hub-registered singleton (preferred)
      2. Lazy construct a new StrategyEvolution() and cache it back via
         `set_si_instance()` so subsequent ticks reuse the same instance
         (and the same accumulated strategy state)
      3. Return an error if empire_si_strategy is not importable
    """
    # Resolve the SI instance via the public getter
    si_instance = get_si_instance()
    if si_instance is None:
        # Lazy fallback — cache it back so we don't re-construct on every tick
        try:
            from empire_si_strategy import StrategyEvolution
            si_instance = StrategyEvolution()
            set_si_instance(si_instance)
            log.info("[revenue] SI strategy instance constructed and cached for reuse")
        except ImportError:
            return {"action": "error", "message": "SI strategy module not available"}

    try:
        forecast = per_lane_forecast()
        niche_summary = forecast.get("niche_summary", {})

        events = []
        for niche, ns in niche_summary.items():
            mrr = ns.get("mrr_projected", 0)
            revenue_24h = ns.get("revenue_24h", 0)

            # Map niche to strategy name
            if "Roofing" in niche:
                strategy = "AGGRESSIVE_STRIKE"
            elif "SEO" in niche or "HVAC" in niche:
                strategy = "UGLY_BANNER"
            elif "Legal" in niche or "Tort" in niche:
                strategy = "RECALL_SNIPER"
            elif "CPA" in niche:
                strategy = "FINANCIAL_STRIKE"
            else:
                strategy = "STANDARD"

            # Success threshold: MRR > $200/lane or 24h revenue > $50
            lane_count = ns.get("lane_count", 8)
            mrr_per_lane = mrr / max(1, lane_count)
            revenue_per_lane = revenue_24h / max(1, lane_count)

            success = (mrr_per_lane > 200) or (revenue_per_lane > 50)
            si_instance.record_outcome(
                strategy_name=strategy,
                niche=niche,
                success=success,
                revenue=mrr,
            )
            events.append({
                "niche": niche,
                "strategy": strategy,
                "success": success,
                "mrr": round(mrr, 2),
                "mrr_per_lane": round(mrr_per_lane, 2),
            })

        # Run evolution cycle if enough data
        evolved = si_instance.evolve()
        if evolved:
            log.info(f"[revenue] SI evolution: {len(evolved)} events")

        return {
            "action": "fed_si",
            "niche_outcomes": events,
            "evolutions": len(evolved),
        }
    except Exception as e:
        log.warning(f"[revenue] SI evolution feed failed: {e}")
        return {"action": "error", "message": str(e)[:200]}


def get_accuracy_timeseries(days: int = 14) -> dict:
    """
    Query pipeline_health (forecast) and brain_memory revenue_snapshots (actual)
    to produce a forecast-vs-actual time-series.
    Returns {series: [{date, forecasted_fee, actual_mrr, accuracy_pct}, ...],
             summary: {avg_accuracy, trend}}.
    """
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()

    # 1. Query brain_memory for revenue snapshots (contains both forecast + actual)
    snapshots_by_date: dict = {}
    try:
        r = sb.table("brain_memory") \
            .select("reasoning,created_at") \
            .eq("city", "revenue_snapshot") \
            .gte("created_at", since) \
            .order("created_at", desc=True) \
            .limit(200).execute()
        for row in (r.data or []):
            date = (row.get("created_at") or "")[:10]
            if date not in snapshots_by_date:
                try:
                    details = json.loads(row.get("reasoning", "{}"))
                except Exception:
                    details = {}
                totals = details.get("totals", {})
                snapshots_by_date[date] = {
                    "forecasted_fee": float(details.get("forecasted_fee", 0)),
                    "actual_revenue": float(totals.get("revenue_24h", 0)),
                }
    except Exception as e:
        log.warning(f"[revenue] accuracy: brain_memory query failed: {e}")

    # 2. Merge into time-series
    all_dates = sorted(snapshots_by_date.keys())[-days:]

    series = []
    accuracies = []
    for date in all_dates:
        snap = snapshots_by_date[date]
        forecasted = snap["forecasted_fee"]
        actual = snap["actual_revenue"]

        # Accuracy: how close is forecast to actual? Both are in $.
        if forecasted > 0 and actual > 0:
            accuracy = round(min(forecasted, actual) / max(forecasted, actual), 3)
        else:
            accuracy = None

        series.append({
            "date": date,
            "forecasted_fee": round(forecasted, 2),
            "actual_revenue": round(actual, 2),
            "accuracy_pct": round(accuracy * 100, 1) if accuracy is not None else None,
        })
        if accuracy is not None:
            accuracies.append(accuracy)

    # Summary
    avg_accuracy = round(sum(accuracies) / len(accuracies), 3) if accuracies else 0.0
    trend = "improving" if len(accuracies) >= 3 and accuracies[-3:] and sum(accuracies[-3:]) / len(accuracies[-3:]) > avg_accuracy else \
            "declining" if len(accuracies) >= 3 and accuracies[-3:] and sum(accuracies[-3:]) / len(accuracies[-3:]) < avg_accuracy else \
            "stable"

    return {
        "series": series,
        "summary": {
            "avg_accuracy_pct": round(avg_accuracy * 100, 1),
            "trend": trend,
            "days_with_data": len(series),
            "days_with_accuracy": len(accuracies),
        },
        "generated_at": now.isoformat(),
    }


class RevenueBrain:
    """
    Adaptive revenue intelligence agent.
    Background loop: snapshot → calibrate → evolve → repeat.
    Wired into main.py as 'agi_revenue' agent.
    """

    def __init__(self, interval_sec: int = 3600):
        self.interval = interval_sec
        self.stats = {
            "ticks": 0,
            "snapshots_recorded": 0,
            "calibrations": 0,
            "si_evolutions": 0,
            "last_error": None,
        }

    def tick(self) -> dict:
        """One learning cycle."""
        self.stats["ticks"] += 1
        results = {}

        # 1. Record revenue snapshot for future few-shot learning
        snap = record_revenue_snapshot()
        if snap:
            self.stats["snapshots_recorded"] += 1
            results["snapshot"] = "ok"
        else:
            results["snapshot"] = "failed"

        # 2. Generate adaptive forecast (few-shot learning)
        try:
            adaptive = adaptive_forecast()
            results["adaptive_forecast"] = "ok"
        except Exception as e:
            results["adaptive_forecast"] = f"failed: {str(e)[:80]}"

        # 3. Calibrate from actuals (compare yesterday's forecast)
        cal = calibrate_from_actuals()
        if cal.get("action") == "calibrated":
            self.stats["calibrations"] += 1
        results["calibration"] = cal

        # 3. Feed SI strategy evolution
        si = feed_si_evolution()
        if si.get("evolutions", 0) > 0:
            self.stats["si_evolutions"] += si["evolutions"]
        results["si_evolution"] = si

        return results

    def run(self):
        """Background loop — sync entry point for main.py."""
        import time as _time
        log.info(f"[revenue.brain] ONLINE · interval={self.interval}s")

        # Register in agent_registry
        try:
            sb.table("agent_registry").upsert({
                "agent_name": "revenue.brain",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": json.dumps(["revenue", "learning", "adaptation", "si"]),
            }, on_conflict="agent_name").execute()
        except Exception:
            pass

        while True:
            try:
                results = self.tick()
                log.info(
                    f"[revenue.brain] tick {self.stats['ticks']}: "
                    f"snap={results.get('snapshot')} "
                    f"cal={results.get('calibration', {}).get('action')} "
                    f"si={results.get('si_evolution', {}).get('action')}"
                )
            except Exception as e:
                self.stats["last_error"] = str(e)[:200]
                log.error(f"[revenue.brain] tick error: {e}")
            _time.sleep(self.interval)


def run():
    """Entry point for main.py agent loop."""
    brain = RevenueBrain(interval_sec=3600)
    brain.run()


if __name__ == "__main__":
    import json
    print(json.dumps(pipeline_forecast(), indent=2))
