"""
EMPIRE V49 · PULSE
==================
Insight layer at /view/pulse. Queries the pulse_rollup_hourly materialized
view (refreshed every 5 min) and exposes four API endpoints that the SPA
and the standalone pulse page consume.

ARCHITECTURE
────────────
  pulse_rollup_hourly (materialized view, 7-day window)
      │
      ├─ GET  /api/pulse/summary?window=24h|7d|30d
      ├─ GET  /api/pulse/breakdown?dimension=niche|channel|contractor|corridor|hour
      ├─ GET  /api/pulse/lanes
      └─ POST /api/pulse/refresh  (owner-only)
      │
      └─ /view/pulse  (standalone HTML page)

API ENDPOINTS
─────────────
  summary:    Totals + deltas for revenue, spend, margin, calls.
              Compares current window to previous window of equal length.

  breakdown:  Grouped data by a single dimension. Returns top N groups
              sorted by revenue descending.

  lanes:      Per-hour per-niche matrix (24h × N niches) for the heatmap.

  refresh:    Force-refreshes the materialized view via Supabase REST API.
              Owner-only.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

log = logging.getLogger("empire.pulse")


# ─────────────────────────────────────────────────────────────────────
# PULSE ENGINE
# ─────────────────────────────────────────────────────────────────────

class PulseEngine:
    """Query engine for the pulse_rollup_hourly materialized view."""

    def __init__(
        self,
        *,
        get_db: Callable,
        refresh_interval_sec: int = 300,
    ):
        self.get_db = get_db
        self.refresh_interval_sec = refresh_interval_sec
        self._last_refresh: Optional[datetime] = None

    # ── HELPERS ──────────────────────────────────────────────────

    @staticmethod
    def _window_hours(window: str) -> int:
        """Return the number of hours for a window string."""
        return {"24h": 24, "7d": 168, "30d": 720}.get(window, 24)

    @staticmethod
    def _window_cutoff(window: str, offset_multiplier: int = 1) -> str:
        """Return an ISO timestamp for the start of a window.

        Args:
            window: "24h", "7d", or "30d"
            offset_multiplier: 1 for current window, 2 for current+previous
        """
        hours = PulseEngine._window_hours(window) * offset_multiplier
        return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    @staticmethod
    def _sum_rows(rows: list) -> dict:
        """Sum numeric columns across rows."""
        result = {"revenue": 0.0, "spend": 0.0, "margin": 0.0, "calls": 0}
        for row in rows:
            result["revenue"] += float(row.get("revenue") or 0)
            result["spend"]   += float(row.get("spend") or 0)
            result["margin"]  += float(row.get("margin") or 0)
            result["calls"]   += int(row.get("calls") or 0)
        return result

    @staticmethod
    def _group_by_key(rows: list, key: str) -> list:
        """Group rows by key, aggregating numeric columns."""
        groups: dict = {}
        for row in rows:
            k = row.get(key)
            if k is None:
                continue
            k = str(k)
            if k not in groups:
                groups[k] = {"key": k, "label": k, "revenue": 0.0, "spend": 0.0,
                             "margin": 0.0, "calls": 0}
            groups[k]["revenue"] += float(row.get("revenue") or 0)
            groups[k]["spend"]   += float(row.get("spend") or 0)
            groups[k]["margin"]  += float(row.get("margin") or 0)
            groups[k]["calls"]   += int(row.get("calls") or 0)
        return list(groups.values())

    # ── SUMMARY ──────────────────────────────────────────────────

    async def summary(self, window: str = "24h") -> dict:
        """Return totals + deltas for the given window.

        Returns:
            {revenue, spend, margin, calls, delta_revenue, delta_spend,
             delta_margin, delta_calls, margin_pct, window}
        """
        db = self.get_db()
        window = window if window in ("24h", "7d", "30d") else "24h"

        cur_cutoff  = self._window_cutoff(window, 1)
        prev_end    = cur_cutoff  # reuse — same boundary, no microsecond gap
        prev_cutoff = self._window_cutoff(window, 2)

        cur = (
            db.table("pulse_rollup_hourly")
            .select("revenue, spend, margin, calls")
            .gte("hour_bucket", cur_cutoff)
            .execute()
        )

        prev = (
            db.table("pulse_rollup_hourly")
            .select("revenue, spend, margin, calls")
            .gte("hour_bucket", prev_cutoff)
            .lt("hour_bucket", prev_end)
            .execute()
        )

        cur_total  = self._sum_rows(cur.data or [])
        prev_total = self._sum_rows(prev.data or [])

        margin_pct = (
            round((cur_total["margin"] / cur_total["revenue"]) * 100, 1)
            if cur_total["revenue"] > 0
            else 0.0
        )

        return {
            "revenue":       round(cur_total["revenue"], 2),
            "spend":         round(cur_total["spend"], 2),
            "margin":        round(cur_total["margin"], 2),
            "calls":         cur_total["calls"],
            "margin_pct":    margin_pct,
            "delta_revenue": round(cur_total["revenue"] - prev_total["revenue"], 2),
            "delta_spend":   round(cur_total["spend"] - prev_total["spend"], 2),
            "delta_margin":  round(cur_total["margin"] - prev_total["margin"], 2),
            "delta_calls":   cur_total["calls"] - prev_total["calls"],
            "window":        window,
            "queried_at":    datetime.now(timezone.utc).isoformat(),
        }

    # ── BREAKDOWN ────────────────────────────────────────────────

    async def breakdown(
        self,
        dimension: str = "niche",
        window: str = "7d",
        top_n: int = 10,
    ) -> dict:
        """Grouped data by a single dimension, sorted by revenue descending.

        Returns:
            {dimension, groups: [{key, label, revenue, spend, margin, calls, margin_pct}],
             total_groups, window}
        """
        valid_dims = {"niche", "channel", "contractor", "corridor", "hour"}
        if dimension not in valid_dims:
            dimension = "niche"

        window = window if window in ("24h", "7d", "30d") else "7d"
        cutoff = self._window_cutoff(window, 1)

        db = self.get_db()

        if dimension == "contractor":
            # Two-step: query rollup → group in memory → enrich with names
            r = (
                db.table("pulse_rollup_hourly")
                .select("contractor_id, revenue, spend, margin, calls")
                .gte("hour_bucket", cutoff)
                .not_.is_("contractor_id", "null")
                .order("revenue", desc=True)
                .limit(top_n * 3)
                .execute()
            )
            groups = self._group_by_key(r.data or [], "contractor_id")
            groups.sort(key=lambda g: g["revenue"], reverse=True)
            groups = groups[:top_n]

            # Enrich with contractor names
            if groups:
                cids = [g["key"] for g in groups]
                try:
                    cres = (
                        db.table("contractors")
                        .select("id, name")
                        .in_("id", cids)
                        .execute()
                    )
                    name_map = {
                        row["id"]: row.get("name") or row["id"]
                        for row in (cres.data or [])
                    }
                    for g in groups:
                        g["label"] = name_map.get(g["key"], g["key"])
                except Exception:
                    pass

        elif dimension == "hour":
            # hour_bucket is already a timestamp
            r = (
                db.table("pulse_rollup_hourly")
                .select("hour_bucket, revenue, spend, margin, calls")
                .gte("hour_bucket", cutoff)
                .order("hour_bucket", desc=True)
                .limit(top_n * 3)
                .execute()
            )
            groups = self._group_by_key(r.data or [], "hour_bucket")
            groups.sort(key=lambda g: g["key"], reverse=True)
            groups = groups[:top_n]
            for g in groups:
                g["label"] = str(g["key"])[:13]

        else:
            # niche, channel, or corridor — group by the dimension column
            r = (
                db.table("pulse_rollup_hourly")
                .select(f"{dimension}, revenue, spend, margin, calls")
                .gte("hour_bucket", cutoff)
                .order("revenue", desc=True)
                .limit(top_n * 5)
                .execute()
            )
            groups = self._group_by_key(r.data or [], dimension)
            groups.sort(key=lambda g: g["revenue"], reverse=True)
            groups = groups[:top_n]

        # Add margin_pct and round
        for g in groups:
            g["margin_pct"] = (
                round((g["margin"] / g["revenue"]) * 100, 1)
                if g["revenue"] > 0
                else 0.0
            )
            g["revenue"] = round(g["revenue"], 2)
            g["spend"] = round(g["spend"], 2)
            g["margin"] = round(g["margin"], 2)

        return {
            "dimension":    dimension,
            "groups":       groups,
            "total_groups": len(groups),
            "window":       window,
            "queried_at":   datetime.now(timezone.utc).isoformat(),
        }

    # ── LANES (HEATMAP DATA) ─────────────────────────────────────

    async def lanes(self) -> dict:
        """Return per-hour per-niche matrix for the heatmap.

        Returns:
            {niches: [...], hours: [...], matrix: [{hour, niche, revenue, calls, margin}],
             totals: {revenue, spend, margin, calls}}
        """
        cutoff = self._window_cutoff("7d", 1)
        db = self.get_db()

        r = (
            db.table("pulse_rollup_hourly")
            .select("hour_bucket, niche, revenue, spend, margin, calls")
            .gte("hour_bucket", cutoff)
            .order("hour_bucket", desc=True)
            .limit(2000)
            .execute()
        )

        rows = r.data or []

        niche_set = set()
        hour_set  = set()
        matrix    = []

        for row in rows:
            hb = str(row.get("hour_bucket", ""))[:13]
            n  = row.get("niche", "") or "other"
            niche_set.add(n)
            hour_set.add(hb)
            matrix.append({
                "hour":    hb,
                "niche":   n,
                "revenue": round(float(row.get("revenue") or 0), 2),
                "calls":   int(row.get("calls") or 0),
                "margin":  round(float(row.get("margin") or 0), 2),
            })

        niches = sorted(niche_set)
        hours  = sorted(hour_set, reverse=True)
        totals = self._sum_rows(rows)

        return {
            "niches":      niches,
            "hours":       hours,
            "hours_count": len(hours),
            "matrix":      matrix,
            "totals": {
                "revenue": round(totals["revenue"], 2),
                "spend":   round(totals["spend"], 2),
                "margin":  round(totals["margin"], 2),
                "calls":   totals["calls"],
            },
            "queried_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── REFRESH ──────────────────────────────────────────────────

    async def refresh(self) -> dict:
        """Force-refresh the materialized view via Supabase REST API."""
        db = self.get_db()
        try:
            supabase_url = os.environ.get("SUPABASE_URL", "")
            supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
            if supabase_url and supabase_key:
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    r = await client.post(
                        f"{supabase_url}/rest/v1/rpc/refresh_pulse_rollup",
                        headers={
                            "apikey": supabase_key,
                            "Authorization": f"Bearer {supabase_key}",
                        },
                    )
                now = datetime.now(timezone.utc)
                self._last_refresh = now
                return {
                    "ok": True,
                    "refreshed_at": now.isoformat(),
                    "status_code": r.status_code,
                }
            else:
                return {"ok": False, "error": "Supabase credentials not configured"}
        except Exception as e:
            log.warning(f"[pulse] RPC refresh failed: {e}")
            # Fallback: try direct SQL via the REST API
            try:
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    r = await client.post(
                        f"{supabase_url}/rest/v1/rpc/refresh_pulse_rollup",
                        headers={
                            "apikey": supabase_key,
                            "Authorization": f"Bearer {supabase_key}",
                            "Content-Type": "application/json",
                        },
                        json={},
                    )
                now = datetime.now(timezone.utc)
                self._last_refresh = now
                return {
                    "ok": True,
                    "refreshed_at": now.isoformat(),
                    "status_code": r.status_code,
                }
            except Exception as e2:
                return {"ok": False, "error": str(e2)[:200]}


# ─────────────────────────────────────────────────────────────────────
# STANDALONE VIEW PAGE
# ─────────────────────────────────────────────────────────────────────

def pulse_view_page() -> str:
    """Return the standalone /view/pulse HTML page.

    This is a focused insight page — no sidebar, no chrome, just the
    pulse data. Links back to /command for the full SPA.

    Handles 401 auth errors by redirecting to /command.
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Empire AI · Pulse</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0a0a0f; color: #e2e8f0; min-height: 100vh;
    }
    :root {
      --signal-teal: #44E5B8; --strike-cyan: #5AC8FA; --status-amber: #FFB800;
      --status-red: #FF4444; --surface: #0f0f17; --elevated: #14141e;
      --border: #1e293b; --divider: #1a1a2e; --mist: #94a3b8; --fog: #64748b;
      --white: #f8fafc; --silver: #cbd5e1;
    }

    .page { max-width: 1200px; margin: 0 auto; padding: 32px 40px; }
    @media (max-width: 768px) { .page { padding: 20px 16px; } }

    .head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 28px; }
    .head-title { font-size: 22px; font-weight: 200; letter-spacing: -0.02em; }
    .head-title em { color: var(--signal-teal); font-style: italic; font-weight: 500; }
    .head-sub { font-family: 'SF Mono', monospace; font-size: 10px; color: var(--mist); letter-spacing: 0.14em; text-transform: uppercase; margin-top: 4px; }
    .head-right { display: flex; gap: 8px; align-items: center; }
    .head-window-btn {
      padding: 6px 14px; font-family: monospace; font-size: 10px; letter-spacing: 0.12em;
      text-transform: uppercase; border: 1px solid var(--border); background: transparent;
      color: var(--mist); cursor: pointer; border-radius: 4px; transition: all 0.15s;
    }
    .head-window-btn:hover { color: var(--white); border-color: var(--mist); }
    .head-window-btn.active { color: var(--signal-teal); border-color: var(--signal-teal); background: rgba(68,229,184,0.06); }
    .head-back { color: var(--fog); text-decoration: none; font-family: monospace; font-size: 10px; letter-spacing: 0.1em; }

    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 28px; }
    @media (max-width: 768px) { .stats { grid-template-columns: repeat(2, 1fr); } }
    .stat-card {
      background: var(--surface); border: 1px solid var(--border); padding: 18px 20px;
      position: relative; overflow: hidden;
    }
    .stat-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, rgba(68,229,184,0.2), transparent); }
    .stat-label { font-family: monospace; font-size: 9px; color: var(--mist); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 12px; }
    .stat-value { font-family: monospace; font-weight: 500; font-size: 30px; color: var(--white); line-height: 1; }
    .stat-value.teal { color: var(--signal-teal); }
    .stat-delta { font-family: monospace; font-size: 10px; margin-top: 8px; }
    .stat-delta.up { color: var(--signal-teal); }
    .stat-delta.down { color: var(--status-red); }

    .tabs { display: flex; gap: 0; margin-bottom: 24px; border-bottom: 1px solid var(--divider); }
    .tab {
      padding: 10px 22px; font-family: monospace; font-size: 10px; letter-spacing: 0.14em;
      text-transform: uppercase; color: var(--mist); cursor: pointer;
      border-bottom: 2px solid transparent; transition: all 0.15s; background: none; border-top: none; border-left: none; border-right: none;
    }
    .tab:hover { color: var(--white); }
    .tab.active { color: var(--signal-teal); border-bottom-color: var(--signal-teal); }

    .panel { background: var(--surface); border: 1px solid var(--border); padding: 20px; margin-bottom: 24px; }
    .panel-h { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--divider); }
    .panel-title { font-weight: 500; font-size: 13px; letter-spacing: 0.02em; }
    .panel-tag { font-family: monospace; font-size: 9px; color: var(--fog); letter-spacing: 0.14em; }

    .bar-row { display: grid; grid-template-columns: 140px 1fr 80px; gap: 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--divider); font-family: monospace; }
    .bar-row:last-child { border-bottom: none; }
    .bar-label { font-size: 11px; color: var(--silver); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar-track { height: 10px; background: var(--elevated); border-radius: 4px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s ease-out; min-width: 2px; }
    .bar-val { font-size: 11px; color: var(--signal-teal); font-weight: 500; text-align: right; }

    .heatmap { overflow-x: auto; }
    .heatmap-table { border-collapse: collapse; font-family: monospace; font-size: 9px; width: 100%; }
    .heatmap-table th { padding: 4px 6px; color: var(--fog); font-weight: 400; letter-spacing: 0.08em; white-space: nowrap; position: sticky; top: 0; background: var(--surface); }
    .heatmap-table td { padding: 4px 6px; text-align: center; border: 1px solid var(--divider); }
    .heatmap-niche { text-align: left; color: var(--mist); white-space: nowrap; font-weight: 500; }
    .heatmap-cell { min-width: 36px; transition: background 0.15s; }
    .heatmap-cell.hot { background: rgba(68,229,184,0.35); color: var(--white); }
    .heatmap-cell.warm { background: rgba(68,229,184,0.15); color: var(--silver); }
    .heatmap-cell.cool { background: rgba(68,229,184,0.04); color: var(--fog); }
    .heatmap-cell.cold { color: var(--fog); opacity: 0.4; }

    .loading { padding: 60px 0; text-align: center; font-family: monospace; font-size: 11px; color: var(--fog); }
    .error { padding: 40px 20px; text-align: center; color: var(--status-red); font-family: monospace; font-size: 11px; }
    .unauth { padding: 60px 20px; text-align: center; }
    .unauth-title { font-size: 18px; font-weight: 200; margin-bottom: 12px; }
    .unauth-body { color: var(--mist); font-size: 13px; max-width: 400px; margin: 0 auto 24px; }
    .unauth-link { display: inline-block; padding: 10px 22px; background: var(--signal-teal); color: #000; text-decoration: none; font-weight: 700; letter-spacing: 0.04em; }

    .refresh-info { font-family: monospace; font-size: 9px; color: var(--fog); margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--divider); text-align: center; }
  </style>
</head>
<body>
  <div class="page" id="app">
    <div class="loading">Loading pulse data…</div>
  </div>

  <script>
    const API = {
      summary: (w) => fetch('/api/pulse/summary?window=' + w, {credentials:'same-origin'}).then(handleAuth),
      breakdown: (d, w) => fetch('/api/pulse/breakdown?dimension=' + d + '&window=' + w, {credentials:'same-origin'}).then(handleAuth),
      lanes: () => fetch('/api/pulse/lanes', {credentials:'same-origin'}).then(handleAuth),
    };

    function handleAuth(r) {
      if (r.status === 401 || r.status === 403) {
        document.getElementById('app').innerHTML =
          '<div class="unauth"><div class="unauth-title">Sign in to view Pulse</div>' +
          '<div class="unauth-body">Pulse requires operator authentication. Sign in at the Command deck to access the insight layer.</div>' +
          '<a href="/command" class="unauth-link">Go to Command</a></div>';
        throw new Error('unauthorized');
      }
      return r.json();
    }

    const fmt = n => '$' + Number(n || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
    const fmtDelta = n => (n >= 0 ? '+' : '') + fmt(n);
    const fmtPct = n => Number(n || 0).toFixed(1) + '%';

    let state = { window: '24h', dimension: 'niche', summary: null, breakdown: null, lanes: null, error: null };

    async function load() {
      try {
        const [s, b, l] = await Promise.all([
          API.summary(state.window),
          API.breakdown(state.dimension, state.window),
          API.lanes(),
        ]);
        state.summary = s; state.breakdown = b; state.lanes = l; state.error = null;
      } catch (e) {
        if (e.message !== 'unauthorized') state.error = String(e);
      }
      render();
    }

    function render() {
      const app = document.getElementById('app');
      if (state.error) {
        app.innerHTML = '<div class="error">Error: ' + state.error + '<br><br><a href="/command" style="color:var(--signal-teal)">Go to Command</a></div>';
        return;
      }
      if (!state.summary) return;

      const s = state.summary;
      const b = state.breakdown;
      const l = state.lanes;

      const maxRev = (b.groups || []).reduce((m, g) => Math.max(m, g.revenue || 0), 0);
      const deltaCls = s.delta_revenue >= 0 ? 'up' : 'down';
      const spendDeltaCls = s.delta_spend <= 0 ? 'up' : 'down';
      const callsDeltaCls = s.delta_calls >= 0 ? 'up' : 'down';

      app.innerHTML =
        '<div class="head">' +
          '<div class="head-left">' +
            '<div class="head-title">Empire AI <em>Pulse</em></div>' +
            '<div class="head-sub">' + s.window + ' snapshot</div>' +
          '</div>' +
          '<div class="head-right">' +
            ['24h','7d','30d'].map(function(w) {
              return '<button class="head-window-btn' + (state.window === w ? ' active' : '') + '" onclick="setWindow(\'' + w + '\')">' + w + '</button>';
            }).join('') +
            '<a href="/command" class="head-back">Command</a>' +
          '</div>' +
        '</div>' +

        '<div class="stats">' +
          '<div class="stat-card">' +
            '<div class="stat-label">Revenue</div>' +
            '<div class="stat-value teal">' + fmt(s.revenue) + '</div>' +
            '<div class="stat-delta ' + deltaCls + '">' + (s.delta_revenue >= 0 ? '▲ ' : '▼ ') + fmt(Math.abs(s.delta_revenue)) + '</div>' +
          '</div>' +
          '<div class="stat-card">' +
            '<div class="stat-label">Spend</div>' +
            '<div class="stat-value">' + fmt(s.spend) + '</div>' +
            '<div class="stat-delta ' + spendDeltaCls + '">' + (s.delta_spend <= 0 ? '▼ ' : '▲ ') + fmt(Math.abs(s.delta_spend)) + '</div>' +
          '</div>' +
          '<div class="stat-card">' +
            '<div class="stat-label">Margin</div>' +
            '<div class="stat-value teal">' + fmtPct(s.margin_pct) + '</div>' +
            '<div class="stat-delta">' + fmt(s.margin) + ' net</div>' +
          '</div>' +
          '<div class="stat-card">' +
            '<div class="stat-label">Calls</div>' +
            '<div class="stat-value">' + s.calls.toLocaleString() + '</div>' +
            '<div class="stat-delta ' + callsDeltaCls + '">' + (s.delta_calls >= 0 ? '▲ ' : '▼ ') + fmtDelta(Math.abs(s.delta_calls)) + '</div>' +
          '</div>' +
        '</div>' +

        '<div class="tabs">' +
          ['niche','channel','contractor','corridor','hour'].map(function(d) {
            return '<button class="tab' + (state.dimension === d ? ' active' : '') + '" onclick="setDim(\'' + d + '\')">' + d + '</button>';
          }).join('') +
        '</div>' +

        '<div class="panel">' +
          '<div class="panel-h">' +
            '<div class="panel-title">Breakdown by <strong>' + state.dimension + '</strong></div>' +
            '<div class="panel-tag">' + b.total_groups + ' groups</div>' +
          '</div>' +
          ((b.groups || []).map(function(g) {
            return '<div class="bar-row">' +
              '<div class="bar-label">' + (g.label || g.key || '—') + '</div>' +
              '<div class="bar-track"><div class="bar-fill" style="width:' + (maxRev > 0 ? Math.max(2, Math.round(g.revenue / maxRev * 100)) : 0) + '%;background:var(--signal-teal)"></div></div>' +
              '<div class="bar-val">' + fmt(g.revenue) + ' · ' + fmtPct(g.margin_pct) + ' margin</div>' +
            '</div>';
          }).join('') || '<div style="padding:24px;text-align:center;color:var(--fog);font-family:monospace;font-size:11px">No data for this window</div>') +
        '</div>' +

        '<div class="panel">' +
          '<div class="panel-h">' +
            '<div class="panel-title">Hourly Heatmap · 7d</div>' +
            '<div class="panel-tag">' + (l.niches || []).length + ' niches × ' + (l.hours || []).length + ' hours</div>' +
          '</div>' +
          '<div class="heatmap">' + renderHeatmap(l) + '</div>' +
        '</div>' +

        '<div class="refresh-info">Refreshes every 5 min · Last query: ' + new Date(s.queried_at).toLocaleString() + '</div>';
    }

    function renderHeatmap(l) {
      if (!l || !l.hours || !l.niches) return '<div style="padding:24px;text-align:center;color:var(--fog)">No heatmap data</div>';

      var niches = l.niches.slice(0, 8);
      var hours = l.hours.slice(0, 24);

      var lookup = {};
      (l.matrix || []).forEach(function(m) {
        lookup[m.niche + '|' + m.hour] = m;
      });

      var maxRev = (l.matrix || []).reduce(function(mx, m) { return Math.max(mx, m.revenue || 0); }, 0);

      var hourLabels = hours.map(function(h) { return h.slice(11, 13); });
      var headerCells = '<th></th>' + hourLabels.map(function(hl) { return '<th>' + hl + ':00</th>'; }).join('');

      var rows = niches.map(function(n) {
        var cells = hours.map(function(h) {
          var m = lookup[n + '|' + h];
          if (!m || m.revenue <= 0) return '<td class="heatmap-cell cold">·</td>';
          var pct = m.revenue / maxRev;
          var cls = pct > 0.4 ? 'hot' : pct > 0.15 ? 'warm' : pct > 0.02 ? 'cool' : 'cold';
          return '<td class="heatmap-cell ' + cls + '">' + fmt(m.revenue) + '</td>';
        }).join('');
        return '<tr><td class="heatmap-niche">' + n + '</td>' + cells + '</tr>';
      }).join('');

      return '<table class="heatmap-table"><thead><tr>' + headerCells + '</tr></thead><tbody>' + rows + '</tbody></table>';
    }

    function setWindow(w) { state.window = w; load(); }
    function setDim(d) { state.dimension = d; load(); }

    load();
  </script>
</body>
</html>"""
