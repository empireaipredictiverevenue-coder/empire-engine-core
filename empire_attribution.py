"""
EMPIRE V49 · ATTRIBUTION DASHBOARD
====================================
The operator's daily scorecard. Shows the complete revenue funnel:

  Scraped    → pipeline.py wrote to radar_targets
  Enrolled   → SMS sequence started OR voice call placed
  Contacted  → at least one touch landed
  Replied    → inbound SMS or callback received
  Dispatched → contractor accepted via magic link
  Completed  → contractor marked job done
  Settled    → claim settled, 1% fee earned

Funnel conversion at each stage. Per-corridor breakdown. Daily/weekly/monthly
time window. Auto-refreshes via WebSocket events.

Wire-up in hub.py:
    from empire_attribution import attribution_view, register_attribution_routes

    register_attribution_routes(app, require_auth=require_auth, get_db=get_db)

    @app.get("/view/attribution", response_class=HTMLResponse)
    async def view_attribution(token: str = Query("")):
        return HTMLResponse(attribution_view(token=token))

Add the route to MODULES in empire_layout.py:
    ("attribution", "09", "Attribution", "ti-chart-arrows", False),
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from fastapi import FastAPI, Depends, HTTPException, Query


log = logging.getLogger("empire.attribution")


# ─────────────────────────────────────────────────────────────────────────────
# API · funnel + breakdown queries
# ─────────────────────────────────────────────────────────────────────────────
def register_attribution_routes(
    app: FastAPI,
    *,
    require_auth: Callable,
    get_db: Callable,
):
    """Wire the attribution data endpoints."""

    @app.get("/api/v1/attribution/funnel")
    async def funnel(
        days: int = Query(7, ge=1, le=365),
        auth: bool = Depends(require_auth),
    ):
        """
        Full funnel snapshot for the trailing N days. Returns counts at each
        stage and stage-to-stage conversion rates.
        """
        try:
            db = get_db()
        except Exception as e:
            raise HTTPException(503, f"DB unavailable: {e}")

        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # ── STAGE 1: Scraped (radar_targets created) ────────────────────
        try:
            res = db.table("radar_targets").select("id", count="exact") \
                .gte("created_at", since).execute()
            scraped = res.count or 0
        except Exception:
            scraped = 0

        # ── STAGE 2: Enrolled (SMS sequence OR call placed) ─────────────
        try:
            res = db.table("sms_sequences").select("id", count="exact") \
                .gte("created_at", since).execute()
            enrolled = res.count or 0
        except Exception:
            enrolled = 0

        # ── STAGE 3: Contacted (at least one SMS sent) ──────────────────
        try:
            res = db.table("sms_log").select("phone", count="exact") \
                .eq("direction", "outbound") \
                .eq("delivered", True) \
                .gte("created_at", since).execute()
            sms_sent = res.count or 0
        except Exception:
            sms_sent = 0

        try:
            res = db.table("call_events").select("call_uuid", count="exact") \
                .eq("direction", "outbound") \
                .gte("created_at", since).execute()
            calls_placed = res.count or 0
        except Exception:
            calls_placed = 0

        contacted = sms_sent + calls_placed

        # ── STAGE 4: Replied (inbound SMS or call answered) ─────────────
        try:
            res = db.table("sms_log").select("phone", count="exact") \
                .eq("direction", "inbound") \
                .gte("created_at", since).execute()
            sms_replies = res.count or 0
        except Exception:
            sms_replies = 0

        try:
            res = db.table("call_events").select("call_uuid", count="exact") \
                .eq("status", "answered") \
                .gte("created_at", since).execute()
            calls_answered = res.count or 0
        except Exception:
            calls_answered = 0

        replied = sms_replies + calls_answered

        # ── STAGE 5: Dispatched (contractor accepted) ───────────────────
        try:
            res = db.table("dispatches").select("id", count="exact") \
                .gte("created_at", since).execute()
            dispatched_total = res.count or 0
        except Exception:
            dispatched_total = 0

        try:
            res = db.table("dispatches").select("id", count="exact") \
                .in_("status", ["accepted", "on_site", "completed"]) \
                .gte("created_at", since).execute()
            dispatched_accepted = res.count or 0
        except Exception:
            dispatched_accepted = 0

        # ── STAGE 6: Completed (contractor finished job) ────────────────
        try:
            res = db.table("dispatches").select("id", count="exact") \
                .eq("status", "completed") \
                .gte("created_at", since).execute()
            completed = res.count or 0
        except Exception:
            completed = 0

        # ── STAGE 7: Settled (1% fee paid) ──────────────────────────────
        try:
            res = db.table("claim_outcomes").select("id, actual_payout, actual_fee", count="exact") \
                .eq("outcome", "settled") \
                .gte("created_at", since).execute()
            settled_rows = res.data or []
            settled_count = len(settled_rows)
            total_payout = sum(float(r.get("actual_payout") or 0) for r in settled_rows)
            total_fees   = sum(float(r.get("actual_fee")    or 0) for r in settled_rows)
        except Exception:
            settled_count = 0
            total_payout  = 0
            total_fees    = 0

        # ── CONVERSION RATES ─────────────────────────────────────────────
        def pct(num, denom):
            if not denom:
                return None
            return round(num / denom * 100, 1)

        return {
            "window_days": days,
            "stages": {
                "scraped":    {"count": scraped,    "conv_from_prev": None},
                "enrolled":   {"count": enrolled,   "conv_from_prev": pct(enrolled, scraped)},
                "contacted":  {"count": contacted,  "conv_from_prev": pct(contacted, enrolled), "breakdown": {"sms": sms_sent, "calls": calls_placed}},
                "replied":    {"count": replied,    "conv_from_prev": pct(replied, contacted), "breakdown": {"sms": sms_replies, "calls": calls_answered}},
                "dispatched": {"count": dispatched_accepted, "conv_from_prev": pct(dispatched_accepted, replied), "breakdown": {"total_sent": dispatched_total}},
                "completed":  {"count": completed,  "conv_from_prev": pct(completed, dispatched_accepted)},
                "settled":    {"count": settled_count, "conv_from_prev": pct(settled_count, completed)},
            },
            "revenue": {
                "total_payout_captured": round(total_payout, 2),
                "total_fees_earned":     round(total_fees, 2),
                "avg_payout":            round(total_payout / settled_count, 2) if settled_count else 0,
                "avg_fee":               round(total_fees   / settled_count, 2) if settled_count else 0,
            },
            "end_to_end_conversion": pct(settled_count, scraped),
        }

    @app.get("/api/v1/attribution/by-corridor")
    async def by_corridor(
        days: int = Query(7, ge=1, le=365),
        auth: bool = Depends(require_auth),
    ):
        """Lead counts and settled outcomes broken down by city/corridor."""
        try:
            db = get_db()
        except Exception as e:
            raise HTTPException(503, f"DB unavailable: {e}")

        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Aggregate radar_targets by city (uses Supabase's group-by via PostgREST)
        try:
            res = db.table("radar_targets").select("city") \
                .gte("created_at", since).execute()
            rows = res.data or []
        except Exception:
            rows = []

        by_city: dict[str, dict] = {}
        for r in rows:
            city = r.get("city") or "Unknown"
            by_city.setdefault(city, {"scraped": 0, "settled": 0, "fees": 0})
            by_city[city]["scraped"] += 1

        # Overlay settled outcomes
        try:
            outcomes = db.table("claim_outcomes").select("target_addr, actual_fee") \
                .eq("outcome", "settled") \
                .gte("created_at", since).execute()
            settled_rows = outcomes.data or []
        except Exception:
            settled_rows = []

        # Map target_addr → city via radar_targets
        try:
            tgt_res = db.table("radar_targets").select("address, city") \
                .gte("created_at", since).execute()
            addr_to_city = {r["address"]: r.get("city", "Unknown") for r in (tgt_res.data or [])}
        except Exception:
            addr_to_city = {}

        for s in settled_rows:
            city = addr_to_city.get(s.get("target_addr"), "Unknown")
            if city not in by_city:
                by_city[city] = {"scraped": 0, "settled": 0, "fees": 0}
            by_city[city]["settled"] += 1
            by_city[city]["fees"]    += float(s.get("actual_fee") or 0)

        # Return sorted by fees desc
        result = [
            {"city": city, **stats}
            for city, stats in sorted(by_city.items(), key=lambda kv: -kv[1]["fees"])
        ]
        return {"window_days": days, "corridors": result[:20]}

    @app.get("/api/v1/attribution/timeseries")
    async def timeseries(
        days: int = Query(14, ge=1, le=90),
        auth: bool = Depends(require_auth),
    ):
        """Daily counts of scraped + settled for the time-series chart."""
        try:
            db = get_db()
        except Exception as e:
            raise HTTPException(503, f"DB unavailable: {e}")

        since = (datetime.now(timezone.utc) - timedelta(days=days))
        since_iso = since.isoformat()

        # Scraped per day
        try:
            res = db.table("radar_targets").select("created_at") \
                .gte("created_at", since_iso).execute()
            scraped_rows = res.data or []
        except Exception:
            scraped_rows = []

        # Settled per day
        try:
            res = db.table("claim_outcomes").select("created_at, actual_fee") \
                .eq("outcome", "settled") \
                .gte("created_at", since_iso).execute()
            settled_rows = res.data or []
        except Exception:
            settled_rows = []

        # Bucket by date string
        buckets: dict[str, dict] = {}
        for d in range(days + 1):
            day = (since + timedelta(days=d)).strftime("%Y-%m-%d")
            buckets[day] = {"date": day, "scraped": 0, "settled": 0, "fees": 0.0}

        for r in scraped_rows:
            day = r["created_at"][:10]
            if day in buckets:
                buckets[day]["scraped"] += 1

        for r in settled_rows:
            day = r["created_at"][:10]
            if day in buckets:
                buckets[day]["settled"] += 1
                buckets[day]["fees"]   += float(r.get("actual_fee") or 0)

        return {"window_days": days, "series": list(buckets.values())}


# ─────────────────────────────────────────────────────────────────────────────
# VIEW · the operator's dashboard page
# ─────────────────────────────────────────────────────────────────────────────
def attribution_view(token: str = "") -> str:
    """
    Render the /view/attribution page. Uses base_layout() chrome plus
    custom funnel-specific content and the WebSocket live client.
    """
    from empire_layout import base_layout
    from empire_live import LIVE_CLIENT_JS

    extra_css = """
    /* Funnel layout */
    .att-grid {
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 14px;
      margin-bottom: 16px;
    }
    @media (max-width: 1000px) {
      .att-grid { grid-template-columns: 1fr; }
    }

    /* Funnel stages */
    .funnel-stage {
      padding: 14px 16px;
      background: var(--empire-elevated);
      border-left: 3px solid;
      margin-bottom: 8px;
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 14px;
      align-items: center;
      transition: transform 0.2s var(--ease-snap);
    }
    .funnel-stage:hover { transform: translateX(2px); }
    .funnel-stage.scraped    { border-left-color: var(--strike-cyan); }
    .funnel-stage.enrolled   { border-left-color: var(--strike-cyan); }
    .funnel-stage.contacted  { border-left-color: var(--strike-cyan); }
    .funnel-stage.replied    { border-left-color: var(--signal-teal); }
    .funnel-stage.dispatched { border-left-color: var(--signal-teal); }
    .funnel-stage.completed  { border-left-color: var(--signal-teal); }
    .funnel-stage.settled    { border-left-color: var(--signal-teal); background: rgba(68,229,184,0.04); }
    .funnel-stage.dim        { opacity: 0.5; }

    .funnel-stage-name {
      font-family: var(--font-ui);
      font-size: 14px;
      font-weight: 500;
      color: var(--empire-white);
      letter-spacing: -0.02em;
    }
    .funnel-stage-meta {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      margin-top: 3px;
    }
    .funnel-stage-count {
      font-family: var(--font-mono);
      font-size: 22px;
      font-weight: 600;
      color: var(--empire-white);
      letter-spacing: -0.04em;
      font-feature-settings: 'tnum' 1;
      min-width: 60px;
      text-align: right;
    }
    .funnel-stage.settled .funnel-stage-count { color: var(--signal-teal); }
    .funnel-conv {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.1em;
      min-width: 60px;
      text-align: right;
    }
    .funnel-conv.good { color: var(--signal-teal); }
    .funnel-conv.warn { color: var(--status-amber); }

    /* Corridor table */
    .corridor-bar-thin {
      height: 3px;
      background: rgba(10, 26, 47, 0.6);
      margin-top: 4px;
      border-radius: 1px;
      overflow: hidden;
    }
    .corridor-bar-thin > div {
      height: 100%;
      background: linear-gradient(90deg, var(--signal-teal), var(--strike-cyan));
      transition: width 0.8s var(--ease-out-empire);
    }

    /* Time-series chart */
    .chart-canvas {
      width: 100%;
      height: 180px;
      display: block;
    }

    /* Window selector */
    .window-select {
      background: rgba(0,0,0,0.4);
      border: 1px solid var(--empire-border);
      color: var(--empire-white);
      font-family: var(--font-mono);
      font-size: 11px;
      padding: 8px 14px;
      outline: none;
      letter-spacing: 0.1em;
    }
    .window-select:focus { border-color: var(--signal-teal); }

    /* Revenue card */
    .rev-mega {
      padding: 24px 28px;
      background: rgba(68, 229, 184, 0.04);
      border: 1px solid rgba(68, 229, 184, 0.18);
      margin-bottom: 16px;
    }
    .rev-mega-label {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.28em;
      text-transform: uppercase;
      opacity: 0.8;
      margin-bottom: 8px;
    }
    .rev-mega-value {
      font-family: var(--font-mono);
      font-size: 38px;
      font-weight: 600;
      color: var(--signal-teal);
      letter-spacing: -0.04em;
      line-height: 1;
    }
    .rev-mega-sub {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      margin-top: 8px;
    }
    """

    content = """
    <div class="e-page">
      <div class="e-page-header">
        <div>
          <div class="e-page-title">Attribution <em>Funnel</em></div>
          <div class="e-page-sub">Scraped → Settled · Conversion at every stage</div>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <select class="window-select" id="window-select" onchange="loadAll()">
            <option value="1">24h</option>
            <option value="7" selected>7d</option>
            <option value="30">30d</option>
            <option value="90">90d</option>
          </select>
          <button class="e-btn-ghost" onclick="loadAll()">Refresh</button>
        </div>
      </div>

      <!-- Mega revenue ribbon -->
      <div class="rev-mega">
        <div style="display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:24px;">
          <div>
            <div class="rev-mega-label">Fees earned · this window</div>
            <div class="rev-mega-value" id="rev-fees">$0</div>
            <div class="rev-mega-sub" id="rev-sub">awaiting first settlement</div>
          </div>
          <div style="text-align:right;">
            <div class="e-stat-label" style="margin-bottom:8px;">End-to-end conversion</div>
            <div style="font-family:var(--font-mono); font-size:24px; color:var(--signal-teal); font-weight:600; letter-spacing:-0.02em;" id="e2e-conv">—</div>
            <div class="e-stat-label" style="margin-top:4px; color:var(--empire-fog);" id="e2e-sub">scraped → settled</div>
          </div>
        </div>
      </div>

      <!-- Two-column main area -->
      <div class="att-grid">
        <!-- FUNNEL -->
        <div class="e-panel">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid var(--empire-divider);">
            <span class="e-section-label" style="margin-bottom:0;">Conversion Funnel</span>
            <span class="e-stat-label" id="funnel-meta">7d</span>
          </div>
          <div id="funnel-list">
            <div class="funnel-stage scraped dim">
              <div>
                <div class="funnel-stage-name">Loading...</div>
              </div>
              <div class="funnel-stage-count">—</div>
              <div class="funnel-conv">—</div>
            </div>
          </div>
        </div>

        <!-- CORRIDORS + CHART -->
        <div style="display:flex; flex-direction:column; gap:14px;">
          <div class="e-panel">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid var(--empire-divider);">
              <span class="e-section-label" style="margin-bottom:0;">By Corridor</span>
              <span class="e-stat-label">Top 6</span>
            </div>
            <div id="corridor-list">
              <div style="text-align:center; padding:24px; color:var(--empire-fog); font-family:var(--font-mono); font-size:11px;">Loading...</div>
            </div>
          </div>

          <div class="e-panel">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid var(--empire-divider);">
              <span class="e-section-label" style="margin-bottom:0;">Daily Volume</span>
              <span class="e-stat-label">Scraped vs Settled</span>
            </div>
            <canvas id="ts-chart" class="chart-canvas"></canvas>
          </div>
        </div>
      </div>
    </div>
    """

    extra_js = LIVE_CLIENT_JS + """
    <script>
    (function() {
      const TOKEN = window.EMPIRE_TOKEN;

      const fmtMoney = n => n != null ? '$' + Math.round(n).toLocaleString() : '$0';
      const fmtNum   = n => n != null ? Number(n).toLocaleString() : '0';
      const fmtPct   = p => p != null ? p.toFixed(1) + '%' : '—';

      const STAGES = [
        { key: 'scraped',    name: 'Scraped',    desc: 'New radar_targets created' },
        { key: 'enrolled',   name: 'Enrolled',   desc: 'SMS sequence started' },
        { key: 'contacted',  name: 'Contacted',  desc: 'Outbound SMS or call placed' },
        { key: 'replied',    name: 'Replied',    desc: 'Inbound message or callback' },
        { key: 'dispatched', name: 'Dispatched', desc: 'Contractor accepted dispatch' },
        { key: 'completed',  name: 'Completed',  desc: 'Contractor finished job' },
        { key: 'settled',    name: 'Settled',    desc: 'Claim settled, 1% fee earned' },
      ];

      async function loadFunnel(days) {
        try {
          const r = await fetch('/api/v1/attribution/funnel?days=' + days, {
            headers: { Authorization: 'Bearer ' + TOKEN },
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const d = await r.json();
          renderFunnel(d, days);
        } catch (e) {
          console.error('funnel load failed:', e);
        }
      }

      function renderFunnel(d, days) {
        document.getElementById('funnel-meta').textContent = days + 'd';

        // Mega ribbon
        document.getElementById('rev-fees').textContent = fmtMoney(d.revenue.total_fees_earned);
        const settledCount = d.stages.settled.count;
        document.getElementById('rev-sub').textContent =
          settledCount > 0
            ? `${settledCount} settled · avg payout ${fmtMoney(d.revenue.avg_payout)}`
            : 'awaiting first settlement in this window';

        const e2e = d.end_to_end_conversion;
        document.getElementById('e2e-conv').textContent =
          e2e != null ? fmtPct(e2e) : '—';

        // Render each stage
        const list = document.getElementById('funnel-list');
        list.innerHTML = STAGES.map(stage => {
          const s = d.stages[stage.key] || {};
          const conv = s.conv_from_prev;
          const convClass = conv == null
            ? ''
            : (conv >= 30 ? 'good' : (conv >= 10 ? '' : 'warn'));
          const dim = s.count === 0 ? ' dim' : '';

          let meta = stage.desc;
          if (s.breakdown) {
            const parts = Object.entries(s.breakdown).map(([k, v]) => `${k}: ${fmtNum(v)}`);
            meta = parts.join(' · ');
          }

          return `
            <div class="funnel-stage ${stage.key}${dim}">
              <div>
                <div class="funnel-stage-name">${stage.name}</div>
                <div class="funnel-stage-meta">${meta}</div>
              </div>
              <div class="funnel-stage-count">${fmtNum(s.count)}</div>
              <div class="funnel-conv ${convClass}">${fmtPct(conv)}</div>
            </div>
          `;
        }).join('');
      }

      async function loadCorridors(days) {
        try {
          const r = await fetch('/api/v1/attribution/by-corridor?days=' + days, {
            headers: { Authorization: 'Bearer ' + TOKEN },
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const d = await r.json();
          renderCorridors(d);
        } catch (e) {}
      }

      function renderCorridors(d) {
        const list = document.getElementById('corridor-list');
        const corridors = (d.corridors || []).slice(0, 6);
        if (corridors.length === 0) {
          list.innerHTML = '<div style="text-align:center; padding:24px; color:var(--empire-fog); font-family:var(--font-mono); font-size:11px;">No corridor data yet</div>';
          return;
        }
        const maxFees = Math.max(1, ...corridors.map(c => c.fees));
        list.innerHTML = corridors.map(c => {
          const pct = (c.fees / maxFees) * 100;
          return `
            <div style="margin-bottom:14px;">
              <div style="display:flex; justify-content:space-between; align-items:baseline; font-size:12px;">
                <span style="color:var(--empire-silver); font-weight:500;">${c.city}</span>
                <span style="font-family:var(--font-mono); font-weight:600; color:${c.settled > 0 ? 'var(--signal-teal)' : 'var(--empire-mist)'};">${fmtMoney(c.fees)}</span>
              </div>
              <div class="corridor-bar-thin">
                <div style="width:${pct}%;"></div>
              </div>
              <div style="font-family:var(--font-mono); font-size:10px; color:var(--empire-fog); margin-top:3px;">
                ${fmtNum(c.scraped)} scraped · ${fmtNum(c.settled)} settled
              </div>
            </div>
          `;
        }).join('');
      }

      async function loadTimeseries(days) {
        try {
          const r = await fetch('/api/v1/attribution/timeseries?days=' + Math.min(days, 30), {
            headers: { Authorization: 'Bearer ' + TOKEN },
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const d = await r.json();
          drawTimeseries(d.series || []);
        } catch (e) {}
      }

      function drawTimeseries(series) {
        const canvas = document.getElementById('ts-chart');
        if (!canvas) return;
        const dpr = window.devicePixelRatio || 1;
        const W = canvas.clientWidth;
        const H = canvas.clientHeight;
        canvas.width  = W * dpr;
        canvas.height = H * dpr;
        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, W, H);

        if (!series.length) {
          ctx.fillStyle = '#4A5A72';
          ctx.font = '10px "JetBrains Mono", monospace';
          ctx.textAlign = 'center';
          ctx.fillText('No data', W/2, H/2);
          return;
        }

        const maxScraped = Math.max(1, ...series.map(s => s.scraped));
        const maxSettled = Math.max(1, ...series.map(s => s.settled));
        const padLeft = 30, padRight = 12, padTop = 18, padBottom = 20;
        const plotW = W - padLeft - padRight;
        const plotH = H - padTop - padBottom;
        const stepX = plotW / Math.max(1, series.length - 1);

        // Subtle grid
        ctx.strokeStyle = 'rgba(122, 140, 163, 0.08)';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 3; i++) {
          const y = padTop + (plotH * i / 3);
          ctx.beginPath();
          ctx.moveTo(padLeft, y);
          ctx.lineTo(W - padRight, y);
          ctx.stroke();
        }

        // Scraped line (cyan)
        ctx.strokeStyle = '#5AC8FA';
        ctx.lineWidth = 2;
        ctx.beginPath();
        series.forEach((s, i) => {
          const x = padLeft + stepX * i;
          const y = padTop + plotH - (s.scraped / maxScraped) * plotH;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Settled bars (teal)
        ctx.fillStyle = 'rgba(68, 229, 184, 0.6)';
        const barW = Math.max(2, stepX * 0.5);
        series.forEach((s, i) => {
          if (!s.settled) return;
          const x = padLeft + stepX * i - barW / 2;
          const h = (s.settled / maxSettled) * plotH;
          const y = padTop + plotH - h;
          ctx.fillRect(x, y, barW, h);
        });

        // Date labels (first, middle, last)
        ctx.fillStyle = '#4A5A72';
        ctx.font = '9px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        const shortDate = d => d.slice(5);
        ctx.fillText(shortDate(series[0].date), padLeft, H - 4);
        ctx.fillText(shortDate(series[Math.floor(series.length/2)].date), padLeft + plotW/2, H - 4);
        ctx.fillText(shortDate(series[series.length - 1].date), W - padRight, H - 4);

        // Legend
        ctx.textAlign = 'left';
        ctx.fillStyle = '#5AC8FA';
        ctx.fillText('— scraped', padLeft, padTop - 6);
        ctx.fillStyle = '#44E5B8';
        ctx.fillText('▮ settled', padLeft + 70, padTop - 6);
      }

      async function loadAll() {
        const days = parseInt(document.getElementById('window-select').value) || 7;
        await Promise.all([
          loadFunnel(days),
          loadCorridors(days),
          loadTimeseries(days),
        ]);
      }

      // Auto-refresh on live events
      if (window.EMPIRE_LIVE) {
        window.EMPIRE_LIVE.on('strike', () => loadAll());
        window.EMPIRE_LIVE.on('settlement', () => loadAll());
      }

      loadAll();
      setInterval(loadAll, 60000);
    })();
    </script>
    """

    return base_layout(
        title="Attribution",
        subtitle="Funnel",
        content=content,
        active_module="attribution",
        extra_css=extra_css,
        extra_js=extra_js,
    )
