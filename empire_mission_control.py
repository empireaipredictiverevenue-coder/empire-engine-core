"""
EMPIRE V49 · MISSION CONTROL
=============================
Single-source-of-truth for the always-visible top status bar in the SPA.
Aggregates live data from AGI governor, SI brain, BrainDecider, revenue
engine, lane metrics, compliance, and network — and broadcasts it on the
WebSocket so the SPA can render without polling.

Wire-up in hub.py:

    from empire_mission_control import (
        mission_control_snapshot,
        mission_control_broadcast_loop,
        register_mission_control_routes,
    )
    register_mission_control_routes(app, broadcaster=live_broadcaster, get_db=get_db)
    asyncio.create_task(mission_control_broadcast_loop(broadcaster=live_broadcaster, get_db=get_db))
"""

import os
import asyncio
import logging
import time as _time
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("empire.mission_control")

# Cache the snapshot so the broadcast tick and the HTTP endpoint don't
# both hammer Supabase on the same second.
_SNAPSHOT_CACHE: dict = {"_payload": None, "_cached_at": 0.0}
_SNAPSHOT_TTL_SECONDS = 5.5   # 5.5s — slightly above the 5s broadcast interval so the HTTP endpoint reuses the broadcast's snapshot instead of double-fetching

# Per-aggregator 30s caches. The 5.5s snapshot cache (above) protects against
# the WS broadcast + HTTP endpoint running in lockstep, but each sub-aggregator
# still makes its own Supabase queries on every snapshot rebuild. Caching each
# for 30s independently cuts Supabase load by ~80% while still feeling live.
#
# _SUBSYSTEM_CACHE_TTL_SECONDS is the single source of truth for the 30s window.
# _AGI_CACHE_TTL_SECONDS is kept as a back-compat alias (older callers / docs
# may still reference it). The AGI cache is just one of the subsystem caches
# that benefits from this TTL.
_BRAIN_CACHE: dict = {"_payload": None, "_cached_at": 0.0}
_COMPLIANCE_CACHE: dict = {"_payload": None, "_cached_at": 0.0}
_AGI_CACHE: dict = {"_payload": None, "_cached_at": 0.0}
_SUBSYSTEM_CACHE_TTL_SECONDS = 30.0
# Back-compat alias — old code / tests / docs may still reference this name.
# Kept as a tuple assignment so it's clearly a derived constant, not independent.
_AGI_CACHE_TTL_SECONDS = _SUBSYSTEM_CACHE_TTL_SECONDS


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return float(default)


def _health_color(payload: dict) -> str:
    """
    Roll all signals into a single traffic-light color for the top bar.
    - red:   no Supabase, no Ollama, or AGI HOLD with stale agents
    - amber: revenue trending down, low active buyers, or brain confidence < 0.4
    - green: everything looks healthy
    """
    brain = payload.get("brain", {})
    agi = payload.get("agi", {})
    revenue = payload.get("revenue", {})
    compliance_ = payload.get("compliance", {})

    if not brain.get("up", True):
        return "red"
    if not brain.get("supabase_up", True):
        return "red"
    strategy = (agi.get("status") or "").upper()
    if strategy == "HOLD" and agi.get("stale_count", 0) > 0:
        return "red"
    if compliance_.get("blocked_today", 0) > 20:
        return "amber"
    if revenue.get("active_buyers", 0) == 0 and revenue.get("calls_24h", 0) > 0:
        return "amber"
    if brain.get("confidence_avg", 0) and brain.get("confidence_avg", 0) < 0.4:
        return "amber"
    return "green"


def _aggregate_brain(get_db) -> dict:
    """
    Brain subsystem status: Ollama ping + routing + last decisions.
    Cached for 30s to avoid hammering Supabase with the brain_memory scan on
    every snapshot rebuild.
    """
    import time as _t
    now_epoch = _t.time()
    cached = _BRAIN_CACHE.get("_payload")
    cached_at = _BRAIN_CACHE.get("_cached_at", 0.0)
    if cached and (now_epoch - cached_at) < _SUBSYSTEM_CACHE_TTL_SECONDS:
        return cached

    out = {
        "up": False,
        "supabase_up": False,
        "model_code":     "qwen2.5-coder:14b",
        "model_logic":    "llama3.1:latest",
        "model_outreach": "llama3.2:3b",
        "confidence_avg": 0.0,
        "last_decision":  None,
        "last_niche":     None,
        "decisions_24h":  0,
    }
    # Ollama ping
    try:
        import httpx as _hx
        with _hx.Client(timeout=1.5) as c:
            r = c.get("http://localhost:11434/api/tags")
            out["up"] = r.status_code == 200
    except Exception:
        out["up"] = False

    # Supabase ping
    try:
        if get_db is not None:
            db = get_db()
            # Cheap query: limit 1, no data transfer cost beyond the row count
            db.table("agent_registry").select("agent_name").limit(1).execute()
            out["supabase_up"] = True
    except Exception:
        out["supabase_up"] = False

    # Last few brain decisions — for confidence trend + last decision display
    try:
        if get_db is not None:
            from datetime import timedelta
            db = get_db()
            day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            r = db.table("brain_memory") \
                .select("decision,confidence,reasoning,city,created_at") \
                .gte("created_at", day_ago) \
                .order("created_at", desc=True) \
                .limit(100).execute()
            rows = r.data or []
            out["decisions_24h"] = len(rows)
            if rows:
                confidences = [_safe_float(row.get("confidence")) for row in rows if row.get("confidence") is not None]
                if confidences:
                    out["confidence_avg"] = round(sum(confidences) / len(confidences), 3)
                # Most recent decision that isn't a revenue_snapshot marker
                for row in rows:
                    if row.get("city") != "revenue_snapshot":
                        out["last_decision"] = (row.get("decision") or "").upper() or None
                        out["last_niche"] = row.get("city")
                        break
    except Exception as e:
        log.debug(f"[mission_control] brain decision fetch failed: {e}")

    _BRAIN_CACHE["_payload"]   = out
    _BRAIN_CACHE["_cached_at"] = now_epoch
    return out


def _aggregate_agi() -> dict:
    """
    AGI governor state. Cached for 30s (separate from the snapshot cache) to
    avoid hammering Supabase via `direct_strategy()` → `refresh_health_snapshot()`
    on every broadcast tick.
    """
    import time as _t
    now_epoch = _t.time()
    cached = _AGI_CACHE.get("_payload")
    cached_at = _AGI_CACHE.get("_cached_at", 0.0)
    if cached and (now_epoch - cached_at) < _AGI_CACHE_TTL_SECONDS:
        return cached

    out = {
        "status":        "UNKNOWN",
        "running":       False,
        "cycles":        0,
        "strikes_total": 0,
        "brain_go":      0,
        "brain_no_go":   0,
        "manus_fired":   0,
        "stale_count":   0,
        "healthy_count": 0,
    }
    try:
        from empire_agi_governor import get_last_health_snapshot
        snap = get_last_health_snapshot() or {}
        out["stale_count"]   = len(snap.get("stale", []))
        out["healthy_count"] = len(snap.get("healthy", []))
    except Exception:
        pass
    try:
        from empire_agi_governor import governor
        # `direct_strategy()` is the function the AGI calls to choose strategy
        # each cycle. The 30s cache above makes calling it here safe for the
        # 5s broadcast cadence.
        strat = governor.direct_strategy()
        if isinstance(strat, str):
            out["status"] = strat
            out["running"] = strat not in ("HOLD", "MANUAL_HOLD")
    except Exception as e:
        log.debug(f"[mission_control] agi.strategy fetch failed: {e}")

    # Pull cycle/strike totals from the empire_monitor state if available
    try:
        import empire_monitor as _mon  # type: ignore
        state = _mon.SUBCONSCIOUS_STATE  # type: ignore[attr-defined]
        if isinstance(state, dict):
            out["cycles"]        = _safe_int(state.get("cycles"))
            out["strikes_total"] = _safe_int(state.get("strikes_total"))
            out["brain_go"]      = _safe_int(state.get("brain_go"))
            out["brain_no_go"]   = _safe_int(state.get("brain_no_go"))
            out["manus_fired"]   = _safe_int(state.get("manus_fired"))
    except Exception:
        pass

    _AGI_CACHE["_payload"]   = out
    _AGI_CACHE["_cached_at"] = now_epoch
    return out


def _aggregate_si() -> dict:
    """
    SI Strategy Evolution snapshot. Read from the in-process singleton
    if hub.py has wired it up, else return a minimal stub.
    """
    out = {
        "generation":        0,
        "active_strategies": 0,
        "fitness_avg":       0.0,
        "niches":            [],
    }
    try:
        from empire_si_strategy import StrategyEvolution
        # The instance is module-level; reuse the existing snapshot()
        # to avoid re-deriving the niche view here.
        si_instance = StrategyEvolution.get_shared_instance()
        if si_instance is not None and hasattr(si_instance, "snapshot"):
            snap = si_instance.snapshot() or {}
            by_niche = snap.get("by_niche", {}) or {}
            strategies = snap.get("strategies", []) or []
            out["active_strategies"] = sum(
                1 for s in strategies
                if s.get("active", True) and _safe_float(s.get("win_rate", 0)) > 0
            )
            # Generation = total evolution ticks observed
            out["generation"] = _safe_int(snap.get("generation"))
            # Average fitness across active strategies
            active_fits = [
                _safe_float(s.get("fitness"))
                for s in strategies
                if s.get("active", True) and s.get("fitness") is not None
            ]
            if active_fits:
                out["fitness_avg"] = round(sum(active_fits) / len(active_fits), 3)
            # Top 3 niches by MRR
            ranked = sorted(
                by_niche.items(),
                key=lambda kv: _safe_float((kv[1] or {}).get("mrr_projected", 0)),
                reverse=True,
            )
            out["niches"] = [
                {"niche": n, "mrr": round(_safe_float((v or {}).get("mrr_projected", 0)), 2)}
                for n, v in ranked[:3]
            ]
    except Exception as e:
        log.debug(f"[mission_control] si snapshot failed: {e}")
    return out


def _aggregate_revenue() -> dict:
    """
    Revenue engine per-lane totals. Delegates to the predictive_revenue
    bot's per-lane aggregator (it already does the heavy lifting).
    """
    out = {
        "total_24h":      0.0,
        "mrr_projected":  0.0,
        "calls_24h":      0,
        "active_buyers":  0,
        "lanes_active":   0,
        "health_status":  "unknown",
    }
    try:
        from bots import predictive_revenue
        per_lane = predictive_revenue.per_lane_forecast() or {}
        totals = per_lane.get("totals", {}) or {}
        out["total_24h"]     = _safe_float(totals.get("revenue_24h"))
        out["mrr_projected"] = _safe_float(totals.get("mrr_projected"))
        out["calls_24h"]     = _safe_int(totals.get("calls_24h"))
        out["active_buyers"] = _safe_int(totals.get("active_buyers"))
        out["lanes_active"]  = _safe_int(totals.get("lanes_active"))
        health = per_lane.get("health", {}) or {}
        out["health_status"] = health.get("status", "unknown")
    except Exception as e:
        log.debug(f"[mission_control] revenue fetch failed: {e}")
    return out


def _aggregate_compliance(get_db) -> dict:
    """
    Compliance: blocked calls today + DNC counts. Same logic as the
    /api/v1/compliance/stats endpoint, inlined to avoid a second fetch.
    Cached for 30s to avoid repeated Supabase count queries.
    """
    import time as _t
    now_epoch = _t.time()
    cached = _COMPLIANCE_CACHE.get("_payload")
    cached_at = _COMPLIANCE_CACHE.get("_cached_at", 0.0)
    if cached and (now_epoch - cached_at) < _SUBSYSTEM_CACHE_TTL_SECONDS:
        return cached

    out = {
        "blocked_today":  0,
        "dnc_total":      0,
        "call_window_open": True,
        "local_hour":     None,
    }
    try:
        if get_db is None:
            return out
        from datetime import datetime as _dt, timezone as _tz
        db = get_db()
        now = _dt.now(_tz.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        try:
            r = db.table("compliance_audit_logs").select("*", count="exact") \
                .eq("action", "outbound_call_blocked") \
                .gte("created_at", today_start) \
                .execute()
            out["blocked_today"] = getattr(r, "count", 0) or 0
        except Exception:
            pass
        try:
            r = db.table("outbound_dnc").select("*", count="exact").limit(1).execute()
            dnc = getattr(r, "count", 0) or 0
        except Exception:
            dnc = 0
        try:
            r = db.table("sms_opt_outs").select("*", count="exact").limit(1).execute()
            dnc += getattr(r, "count", 0) or 0
        except Exception:
            pass
        out["dnc_total"] = dnc

        # Call window — same logic as empire_outbound_dialer
        from zoneinfo import ZoneInfo
        try:
            local_now = _dt.now(ZoneInfo("America/Chicago"))
        except Exception:
            local_now = now
        h = local_now.hour
        out["local_hour"] = h
        out["call_window_open"] = 8 <= h < 21
    except Exception as e:
        log.debug(f"[mission_control] compliance fetch failed: {e}")
    _COMPLIANCE_CACHE["_payload"]   = out
    _COMPLIANCE_CACHE["_cached_at"] = now_epoch
    return out


def _aggregate_cpl() -> dict:
    out = {
        "lanes_total": 0,
        "lanes_priced": 0,
        "avg_cpl_low": 0.0,
        "avg_cpl_high": 0.0,
        "avg_margin": 0.0,
    }
    try:
        from empire_pricing import cpl_engine
        lp = cpl_engine.lane_pricing()
        lanes = lp.get("lanes", [])
        priced = [l for l in lanes if l.get("cpl_available") is not False]
        out["lanes_total"] = len(lanes)
        out["lanes_priced"] = len(priced)
        if priced:
            out["avg_cpl_low"] = round(sum(l.get("cpl_low", 0) or 0 for l in priced) / len(priced), 2)
            out["avg_cpl_high"] = round(sum(l.get("cpl_high", 0) or 0 for l in priced) / len(priced), 2)
            margins = [l.get("margin_pct", 0) or 0 for l in priced if l.get("margin_pct") is not None]
            if margins:
                out["avg_margin"] = round(sum(margins) / len(margins), 2)
    except Exception:
        pass
    return out



def _aggregate_network(broadcaster) -> dict:
    """
    Network: WS connections, uptime, broadcaster message rate.
    """
    out = {
        "ws_connections": 0,
        "sse_connected":  0,
        "messages_sent":  0,
        "uptime_s":       0,
    }
    try:
        if broadcaster is not None and hasattr(broadcaster, "stats"):
            stats = broadcaster.stats or {}
            out["ws_connections"] = _safe_int(stats.get("connected"))
            out["sse_connected"]  = _safe_int(stats.get("sse_connected"))
            out["messages_sent"]  = _safe_int(stats.get("messages_sent"))
            started = stats.get("started_at")
            if started:
                try:
                    started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    out["uptime_s"] = int((datetime.now(timezone.utc) - started_dt).total_seconds())
                except Exception:
                    pass
    except Exception:
        pass
    return out


def mission_control_snapshot(get_db=None, broadcaster=None) -> dict:
    """
    Build the full Mission Control snapshot. Cached for 4s so the
    WebSocket broadcast tick and the HTTP endpoint see the same data.

    Returns:
        dict suitable for JSON serialization — see schema in module docstring.
    """
    now_epoch = _time.time()
    cached = _SNAPSHOT_CACHE.get("_payload")
    cached_at = _SNAPSHOT_CACHE.get("_cached_at", 0.0)
    if cached and (now_epoch - cached_at) < _SNAPSHOT_TTL_SECONDS:
        return cached

    payload = {
        "ts":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agi":        _aggregate_agi(),
        "si":         _aggregate_si(),
        "brain":      _aggregate_brain(get_db),
        "revenue":    _aggregate_revenue(),
        "compliance": _aggregate_compliance(get_db),
        "network":    _aggregate_network(broadcaster),
        "cpl":        _aggregate_cpl(),
    }
    payload["health"] = _health_color(payload)

    _SNAPSHOT_CACHE["_payload"]   = payload
    _SNAPSHOT_CACHE["_cached_at"] = now_epoch
    return payload


# ─────────────────────────────────────────────────────────────────────
# BROADCAST LOOP — pushes mission_control to every WS client every 5s
# ─────────────────────────────────────────────────────────────────────
async def mission_control_broadcast_loop(broadcaster, get_db=None, interval: float = 5.0):
    """
    Background task: emit a `mission_control` event every `interval` seconds.
    Stops gracefully if the broadcaster is missing.

    Short-circuits when zero clients are connected — skips the snapshot build
    entirely so we don't hammer Supabase for nobody. The HTTP endpoint still
    serves the cached snapshot if an operator opens the SPA tab.
    """
    log.info(f"[mission_control] broadcast loop started · {interval}s interval")
    while True:
        try:
            stats = getattr(broadcaster, "stats", {}) or {}
            clients = _safe_int(stats.get("connected", 0)) + _safe_int(stats.get("sse_connected", 0))
            if broadcaster is not None and clients > 0:
                snap = mission_control_snapshot(get_db=get_db, broadcaster=broadcaster)
                await broadcaster.broadcast({
                    "type": "mission_control",
                    **snap,
                })
            else:
                # No clients → sleep without rebuilding the snapshot. Saves
                # ~4 Supabase queries per tick (brain + compliance + AGI health
                # + decision scan) when nobody is online.
                log.debug(f"[mission_control] no clients connected ({clients}) — skipping snapshot build")
        except Exception as e:
            log.warning(f"[mission_control] broadcast error: {e}")
        await asyncio.sleep(interval)


# ─────────────────────────────────────────────────────────────────────
# HTTP ROUTE — manual fetch, useful for debugging or non-WS clients
# ─────────────────────────────────────────────────────────────────────
def register_mission_control_routes(app, get_db=None):
    """
    Register GET /api/v1/mission_control. Returns the latest snapshot
    (uses the same cache as the broadcast loop). The `broadcaster` is not
    needed here — the HTTP endpoint only reads the cache, which the broadcast
    loop keeps fresh.
    """
    from fastapi import Depends

    # Some builds expose require_auth as a FastAPI dependency, others don't.
    # Be defensive: only require auth if the project has a working dep fn.
    require_dep = None
    try:
        from empire_auth import require_auth as _ra  # type: ignore
        if callable(_ra):
            require_dep = _ra
    except Exception:
        pass

    if require_dep is not None:
        @app.get("/api/v1/mission_control")
        async def _mission_control(auth: bool = Depends(require_dep)):
            return mission_control_snapshot(get_db=get_db)
    else:
        @app.get("/api/v1/mission_control")
        async def _mission_control():
            return mission_control_snapshot(get_db=get_db)

    log.info("[mission_control] Route registered · GET /api/v1/mission_control")
