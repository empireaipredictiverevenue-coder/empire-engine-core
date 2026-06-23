"""
EMPIRE V49 · BUFFY BUFFER ANALYTICS DASHBOARD
==============================================
Dashboard page at /buffy showing Buffy Buffer queue analytics:
queue depth, throughput, failure rates, state distribution.

Provides two components:
  1. buffy_stats_json(get_db) — API endpoint data for /api/v1/buffy/stats
  2. buffy_dashboard_page() — HTML dashboard page

Wires into hub.py:
    from empire_buffy_page import buffy_dashboard_page, buffy_stats_json

    @app.get("/api/v1/buffy/stats")
    async def buffy_stats_route():
        from fastapi.responses import JSONResponse
        return JSONResponse(await buffy_stats_json(get_db))

    @app.get("/buffy", response_class=HTMLResponse)
    async def buffy_dashboard():
        return HTMLResponse(buffy_dashboard_page())
"""

import logging
from datetime import datetime, timezone, timedelta

from empire_tokens import empire_head

log = logging.getLogger("empire.buffy_page")


# ── API endpoint ────────────────────────────────────────────────────

async def buffy_stats_json(get_db) -> dict:
    """Return aggregated Buffy Buffer stats from video_automation_jobs."""
    try:
        db = get_db()
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # ── Counts by status ──
        statuses = [
            "BUFFY_BUFFERED", "RENDER_TRIGGERED", "PROCESSING",
            "QUALITY_APPROVED", "QUALITY_FAILED", "DONE", "FAILED",
        ]
        status_counts: dict[str, int] = {}
        total = 0
        for s in statuses:
            try:
                r = db.table("video_automation_jobs") \
                    .select("id", count="exact") \
                    .eq("status", s) \
                    .execute()
                c = r.count or 0
                status_counts[s] = c
                total += c
            except Exception:
                status_counts[s] = 0

        # ── Today's activity ──
        done_today = 0
        failed_today = 0
        try:
            r = db.table("video_automation_jobs") \
                .select("id", count="exact") \
                .eq("status", "DONE") \
                .gte("completed_at", today_start.isoformat()) \
                .execute()
            done_today = r.count or 0
        except Exception:
            pass
        try:
            r = db.table("video_automation_jobs") \
                .select("id", count="exact") \
                .eq("status", "FAILED") \
                .gte("completed_at", today_start.isoformat()) \
                .execute()
            failed_today = r.count or 0
        except Exception:
            pass

        # ── Voice provider distribution ──
        voice_providers: dict[str, int] = {"kokoro": 0, "deepgram": 0, "other": 0}
        try:
            r = db.table("video_automation_jobs") \
                .select("voice_provider", count="exact") \
                .execute()
            for row in (r.data or []):
                vp = (row.get("voice_provider") or "").strip().lower()
                if vp in voice_providers:
                    voice_providers[vp] += 1
                else:
                    voice_providers["other"] += 1
        except Exception:
            pass

        # ── Source distribution ──
        sources: dict[str, int] = {}
        try:
            r = db.table("video_automation_jobs") \
                .select("source", count="exact") \
                .execute()
            for row in (r.data or []):
                src = (row.get("source") or "unknown").strip().lower()
                sources[src] = sources.get(src, 0) + 1
        except Exception:
            pass

        # ── Daily throughput (last 7 days) ──
        daily_throughput: list[dict] = []
        for day_offset in range(7, -1, -1):
            day_start = today_start - timedelta(days=day_offset)
            day_end = day_start + timedelta(days=1)
            label = day_start.strftime("%a %m/%d")
            done_count = 0
            fail_count = 0
            try:
                r = db.table("video_automation_jobs") \
                    .select("id", count="exact") \
                    .eq("status", "DONE") \
                    .gte("completed_at", day_start.isoformat()) \
                    .lt("completed_at", day_end.isoformat()) \
                    .execute()
                done_count = r.count or 0
            except Exception:
                pass
            try:
                r = db.table("video_automation_jobs") \
                    .select("id", count="exact") \
                    .eq("status", "FAILED") \
                    .gte("completed_at", day_start.isoformat()) \
                    .lt("completed_at", day_end.isoformat()) \
                    .execute()
                fail_count = r.count or 0
            except Exception:
                pass
            daily_throughput.append({
                "label": label,
                "done": done_count,
                "failed": fail_count,
                "total": done_count + fail_count,
            })

        # ── Recent jobs (last 20) ──
        recent_jobs: list[dict] = []
        try:
            r = db.table("video_automation_jobs") \
                .select("id, topic, status, voice_provider, source, "
                        "priority, duration_s, size_kb, error, "
                        "created_at, completed_at") \
                .order("created_at", desc=True) \
                .limit(20) \
                .execute()
            for row in (r.data or []):
                recent_jobs.append({
                    "id": str(row.get("id", ""))[:8],
                    "topic": (row.get("topic") or "")[:80],
                    "status": row.get("status", ""),
                    "voice_provider": row.get("voice_provider", ""),
                    "source": row.get("source", ""),
                    "priority": row.get("priority", 0),
                    "duration_s": float(row.get("duration_s") or 0),
                    "size_kb": row.get("size_kb", 0),
                    "error": (row.get("error") or "")[:120],
                    "created_at": row.get("created_at", ""),
                    "completed_at": row.get("completed_at", ""),
                })
        except Exception:
            pass

        # ── Success rate ──
        done_total = status_counts.get("DONE", 0)
        failed_total = status_counts.get("FAILED", 0)
        completed_total = done_total + failed_total
        success_rate = round((done_total / max(completed_total, 1)) * 100, 1)

        return {
            "total": total,
            "by_status": status_counts,
            "done_today": done_today,
            "failed_today": failed_today,
            "success_rate": success_rate,
            "voice_providers": voice_providers,
            "sources": sources,
            "daily_throughput": daily_throughput,
            "recent_jobs": recent_jobs,
            "timestamp": now.isoformat(),
        }
    except Exception as e:
        log.warning(f"[buffy-stats] query failed: {e}")
        return {"error": str(e)[:200]}


# ── Dashboard page ──────────────────────────────────────────────────

_PAGE_CSS = """
.buffy-wrap {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 32px 80px;
}
.buffy-hero {
  margin-bottom: 40px;
}
.buffy-hero h1 {
  font-family: var(--font-display);
  font-weight: 200;
  font-size: 36px;
  letter-spacing: -0.04em;
  color: var(--empire-white);
  margin-bottom: 8px;
}
.buffy-hero h1 em {
  font-style: italic;
  font-weight: 700;
  color: #F4A261;
}
.buffy-hero p {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--empire-fog);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.buffy-hero .status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 6px 14px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-xs);
  color: var(--empire-mist);
}
.buffy-hero .status-badge .dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #F4A261;
  box-shadow: 0 0 8px rgba(244,162,97,0.4);
  animation: buffy-pulse 1.6s ease-in-out infinite;
}
@keyframes buffy-pulse {
  0%,100% { opacity: 1; }
  50% { opacity: .5; }
}

/* Section headers */
.buffy-section {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--empire-mist);
  font-weight: 600;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--empire-divider);
}

/* KPI cards */
.buffy-kpis {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 40px;
}
.buffy-kpi {
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: 20px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.25s;
}
.buffy-kpi:hover {
  border-color: var(--empire-border);
}
.buffy-kpi::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 2px; height: 100%;
}
.buffy-kpi.green::before { background: var(--signal-teal); }
.buffy-kpi.blue::before  { background: var(--strike-cyan); }
.buffy-kpi.amber::before { background: #F4A261; }
.buffy-kpi.red::before   { background: #F43F5E; }
.buffy-kpi.purple::before { background: #A78BFA; }

.buffy-kpi-icon {
  font-size: 20px;
  margin-bottom: 8px;
  opacity: 0.7;
}
.buffy-kpi-label {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 4px;
}
.buffy-kpi-value {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 28px;
  line-height: 1;
  letter-spacing: -0.04em;
  color: var(--empire-white);
  font-feature-settings: 'tnum' 1;
}
.buffy-kpi-value.green { color: var(--signal-teal); }
.buffy-kpi-value.blue  { color: var(--strike-cyan); }
.buffy-kpi-value.amber { color: #F4A261; }
.buffy-kpi-value.red   { color: #F43F5E; }

/* Two-column layout */
.buffy-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 32px;
}

/* Status breakdown bar */
.buffy-bar-section {
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: 20px;
}
.buffy-bar-title {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 16px;
}
.buffy-bar-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.buffy-bar-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--empire-silver);
  width: 130px;
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.buffy-bar-track {
  flex: 1;
  height: 8px;
  background: rgba(255,255,255,0.05);
  border-radius: 4px;
  overflow: hidden;
}
.buffy-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}
.buffy-bar-fill.green  { background: var(--signal-teal); }
.buffy-bar-fill.blue   { background: var(--strike-cyan); }
.buffy-bar-fill.amber  { background: #F4A261; }
.buffy-bar-fill.red    { background: #F43F5E; }
.buffy-bar-fill.purple { background: #A78BFA; }
.buffy-bar-fill.gray   { background: var(--empire-mist); }

.buffy-bar-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--empire-silver);
  width: 40px;
  text-align: right;
  font-feature-settings: 'tnum' 1;
}

/* Throughput chart */
.buffy-chart-section {
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: 20px;
}
.buffy-chart-title {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 16px;
}

.buffy-chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 120px;
  padding-top: 8px;
}
.buffy-chart-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  height: 100%;
  justify-content: flex-end;
}
.buffy-chart-bar-group {
  display: flex;
  gap: 2px;
  width: 100%;
  max-width: 36px;
  align-items: flex-end;
  flex: 1;
}
.buffy-chart-bar {
  flex: 1;
  border-radius: 2px 2px 0 0;
  transition: height 0.4s ease;
  min-height: 2px;
}
.buffy-chart-bar.done   { background: var(--signal-teal); }
.buffy-chart-bar.failed { background: #F43F5E; }
.buffy-chart-label {
  font-family: var(--font-mono);
  font-size: 8px;
  color: var(--empire-fog);
  letter-spacing: 0.04em;
  text-align: center;
}

/* Recent jobs table */
.buffy-table-section {
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-bottom: 32px;
}
.buffy-table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: var(--empire-surface);
  border-bottom: 1px solid var(--empire-divider);
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--empire-mist);
  font-weight: 600;
}
.buffy-table-header .refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 600;
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--empire-mist);
  cursor: pointer;
  transition: all 0.2s;
  text-decoration: none;
}
.buffy-table-header .refresh-btn:hover {
  color: var(--empire-white);
  border-color: var(--empire-border-hi);
}

.buffy-table {
  width: 100%;
  border-collapse: collapse;
}
.buffy-table th {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 600;
  padding: 10px 16px;
  border-bottom: 1px solid var(--empire-divider);
  text-align: left;
  background: rgba(0,0,0,0.15);
}
.buffy-table td {
  padding: 10px 16px;
  border-bottom: 1px solid rgba(122,140,163,0.04);
  font-size: 12px;
  color: var(--empire-silver);
  font-family: var(--font-mono);
  font-feature-settings: 'tnum' 1;
}
.buffy-table tr:last-child td { border-bottom: none; }
.buffy-table .status-dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.buffy-table .status-dot.green  { background: var(--signal-teal); }
.buffy-table .status-dot.blue   { background: var(--strike-cyan); }
.buffy-table .status-dot.amber  { background: #F4A261; }
.buffy-table .status-dot.red    { background: #F43F5E; }
.buffy-table .status-dot.gray   { background: var(--empire-mist); }
.buffy-table .status-dot.purple { background: #A78BFA; }

.buffy-table .topic-cell {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--empire-white);
}

/* Auto-refresh */
.buffy-auto-refresh {
  font-family: var(--font-mono);
  font-size: 8px;
  color: var(--empire-fog);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}
.buffy-auto-refresh .dot {
  width: 4px; height: 4px;
  border-radius: 50%;
  background: #F4A261;
  animation: buffy-pulse 1.6s ease-in-out infinite;
}

/* Loading */
.buffy-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 50vh;
  text-align: center;
  color: var(--empire-mist);
  font-family: var(--font-mono);
  font-size: 11px;
}
.buffy-loading .spinner {
  width: 22px; height: 22px;
  border-radius: 50%;
  border: 2px solid var(--empire-border);
  border-top-color: #F4A261;
  animation: buffy-spin 0.8s linear infinite;
  margin-bottom: 16px;
}
@keyframes buffy-spin { to { transform: rotate(360deg); } }

/* Footer */
.buffy-foot {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--empire-divider);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-fog);
  letter-spacing: 0.18em;
  text-transform: uppercase;
}
.buffy-foot a {
  color: var(--empire-mist);
  text-decoration: none;
  transition: color 0.2s;
}
.buffy-foot a:hover { color: #F4A261; }

/* Responsive */
@media (max-width: 900px) {
  .buffy-kpis { grid-template-columns: repeat(3, 1fr); }
  .buffy-cols { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
  .buffy-kpis { grid-template-columns: repeat(2, 1fr); }
  .buffy-wrap { padding: 24px 16px; }
}
"""


def buffy_dashboard_page() -> str:
    head = empire_head(
        title="Buffy Buffer \u00b7 Empire AI",
        extra=_PAGE_CSS,
        page="buffy",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="buffy-wrap">

  <div class="buffy-hero">
    <h1>Buffy <em>Buffer</em></h1>
    <p>Queue Controller \u00b7 Render Pipeline \u00b7 Concurrency Monitor</p>
    <div class="status-badge">
      <span class="dot"></span>
      <span>Polling every 3s \u00b7 Max 3 concurrent lanes</span>
    </div>
  </div>

  <!-- KPI cards -->
  <div class="buffy-kpis" id="buffy-kpis">
    <div class="buffy-loading" id="buffy-loading" style="grid-column:1/-1;height:200px">
      <div class="spinner"></div>
      <div>Loading Buffy Buffer stats...</div>
    </div>
  </div>

  <!-- Two-column: status breakdown + throughput chart -->
  <div class="buffy-cols">

    <!-- Status breakdown -->
    <div class="buffy-bar-section" id="buffy-bar-section">
      <div class="buffy-bar-title">Jobs by Status</div>
      <div id="buffy-bar-body">
        <div style="text-align:center;color:var(--empire-mist);font-family:var(--font-mono);font-size:11px;padding:20px">Loading...</div>
      </div>
    </div>

    <!-- Throughput chart -->
    <div class="buffy-chart-section">
      <div class="buffy-chart-title">Daily Throughput (7 days)</div>
      <div class="buffy-chart-bars" id="buffy-chart-body">
        <div style="text-align:center;color:var(--empire-mist);font-family:var(--font-mono);font-size:11px;width:100%;padding:20px">Loading...</div>
      </div>
    </div>

  </div>

  <!-- Recent jobs table -->
  <div class="buffy-table-section">
    <div class="buffy-table-header">
      <span>Recent Jobs</span>
      <div style="display:flex;align-items:center;gap:12px">
        <span class="buffy-auto-refresh"><span class="dot"></span> Auto-refresh 10s</span>
        <a href="/buffy" class="refresh-btn">\u21bb Refresh</a>
      </div>
    </div>
    <table class="buffy-table" id="buffy-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Topic</th>
          <th>Status</th>
          <th>Voice</th>
          <th>Source</th>
          <th>Duration</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody id="buffy-table-body">
        <tr><td colspan="7" style="text-align:center;color:var(--empire-mist)">Waiting for data...</td></tr>
      </tbody>
    </table>
  </div>

  <div class="buffy-foot">
    <span>
      <a href="/command">Command Deck</a>
      <span style="padding:0 8px;color:var(--empire-shadow)">\u00b7</span>
      <a href="/omni">Omni Bridge</a>
      <span style="padding:0 8px;color:var(--empire-shadow)">\u00b7</span>
      <a href="/fleet">Fleet Dashboard</a>
    </span>
    <span>Empire AI \u00b7 Buffy Buffer Monitor</span>
  </div>

</div>

<script>
(function() {{
  function fmt(n) {{        if (n == null || n === undefined) return '—';
    return Number(n).toLocaleString();
  }}

  function statusClass(s) {{
    var m = {{}};
    m['BUFFY_BUFFERED']   = 'gray';
    m['RENDER_TRIGGERED'] = 'blue';
    m['PROCESSING']       = 'amber';
    m['QUALITY_APPROVED'] = 'purple';
    m['QUALITY_FAILED']   = 'red';
    m['DONE']             = 'green';
    m['FAILED']           = 'red';
    return m[s] || 'gray';
  }}

  function statusLabel(s) {{
    var m = {{}};
    m['BUFFY_BUFFERED']   = 'Buffered';
    m['RENDER_TRIGGERED'] = 'Released';
    m['PROCESSING']       = 'Processing';
    m['QUALITY_APPROVED'] = 'Quality OK';
    m['QUALITY_FAILED']   = 'Quality Fail';
    m['DONE']             = 'Done';
    m['FAILED']           = 'Failed';
    return m[s] || s;
  }}

  function maxVal(arr, key) {{
    var mx = 0;
    for (var i = 0; i < arr.length; i++) {{
      var v = arr[i][key] || 0;
      if (v > mx) mx = v;
    }}
    return mx || 1;
  }}

  function loadStats() {{
    var TOKEN = window.EMPIRE_TOKEN || localStorage.getItem('hub_token') || '';
    fetch('/api/v1/buffy/stats', {{
          headers: TOKEN ? {{ 'Authorization': 'Bearer ' + TOKEN }} : {{}}
        }})
      .then(function(r) {{ return r.json(); }})
      .then(function(data) {{
        if (data.error) throw new Error(data.error);

        var byStatus = data.by_status || {{}};
        var total = data.total || 0;
        var doneToday = data.done_today || 0;
        var failedToday = data.failed_today || 0;
        var successRate = data.success_rate || 0;
        var daily = data.daily_throughput || [];
        var recent = data.recent_jobs || [];

        var buffered   = byStatus['BUFFY_BUFFERED']   || 0;
        var processing = byStatus['PROCESSING']       || 0;
        var released   = byStatus['RENDER_TRIGGERED'] || 0;
        var done       = byStatus['DONE']             || 0;
        var failed     = byStatus['FAILED']           || 0;

        // ── KPI cards ──
        document.getElementById('buffy-kpis').innerHTML =
          '<div class="buffy-kpi amber">' +
            '<div class="buffy-kpi-icon">⏳</div>' +
            '<div class="buffy-kpi-label">Processing</div>' +
            '<div class="buffy-kpi-value amber">' + fmt(processing) + '</div>' +
          '</div>' +
          '<div class="buffy-kpi blue">' +
            '<div class="buffy-kpi-icon">📤</div>' +
            '<div class="buffy-kpi-label">Buffered</div>' +
            '<div class="buffy-kpi-value blue">' + fmt(buffered) + '</div>' +
          '</div>' +
          '<div class="buffy-kpi green">' +
            '<div class="buffy-kpi-icon">✅</div>' +
            '<div class="buffy-kpi-label">Done Today</div>' +
            '<div class="buffy-kpi-value green">' + fmt(doneToday) + '</div>' +
          '</div>' +
          '<div class="buffy-kpi red">' +
            '<div class="buffy-kpi-icon">❌</div>' +
            '<div class="buffy-kpi-label">Failed Today</div>' +
            '<div class="buffy-kpi-value red">' + fmt(failedToday) + '</div>' +
          '</div>' +
          '<div class="buffy-kpi purple">' +
            '<div class="buffy-kpi-icon">📊</div>' +
            '<div class="buffy-kpi-label">Success Rate</div>' +
            '<div class="buffy-kpi-value" style="color:' + (successRate >= 80 ? 'var(--signal-teal)' : '#F43F5E') + '">' +
              (total > 0 ? successRate + '%' : '—') +
            '</div>' +
          '</div>';

        // ── Status breakdown bars ──
        var statusOrder = ['DONE', 'PROCESSING', 'RENDER_TRIGGERED', 'BUFFY_BUFFERED', 'QUALITY_APPROVED', 'QUALITY_FAILED', 'FAILED'];
        var barHtml = '';
        var maxCount = 0;
        for (var i = 0; i < statusOrder.length; i++) {{
          var c = byStatus[statusOrder[i]] || 0;
          if (c > maxCount) maxCount = c;
        }}
        maxCount = maxCount || 1;
        for (var i = 0; i < statusOrder.length; i++) {{
          var s = statusOrder[i];
          var c = byStatus[s] || 0;
          var pct = Math.round((c / maxCount) * 100);
          barHtml +=
            '<div class="buffy-bar-row">' +
              '<div class="buffy-bar-label">' + statusLabel(s) + '</div>' +
              '<div class="buffy-bar-track">' +
                '<div class="buffy-bar-fill ' + statusClass(s) + '" style="width:' + pct + '%"></div>' +
              '</div>' +
              '<div class="buffy-bar-count">' + fmt(c) + '</div>' +
            '</div>';
        }}
        document.getElementById('buffy-bar-body').innerHTML = barHtml;

        // ── Throughput chart ──
        var chartHtml = '';
        var mx = maxVal(daily, 'total');
        mx = mx || 1;
        for (var i = 0; i < daily.length; i++) {{
          var d = daily[i];
          var doneH = Math.round(((d.done || 0) / mx) * 100) || 2;
          var failH = Math.round(((d.failed || 0) / mx) * 100) || 2;
          chartHtml +=
            '<div class="buffy-chart-col">' +
              '<div class="buffy-chart-bar-group" style="height:' + Math.max(doneH, failH) + '%">' +
                '<div class="buffy-chart-bar done" style="height:' + doneH + '%"></div>' +
                '<div class="buffy-chart-bar failed" style="height:' + failH + '%"></div>' +
              '</div>' +
              '<div class="buffy-chart-label">' + d.label + '</div>' +
            '</div>';
        }}
        document.getElementById('buffy-chart-body').innerHTML = chartHtml;

        // ── Recent jobs table ──
        var tbody = '';
        for (var i = 0; i < recent.length; i++) {{
          var j = recent[i];
          var created = (j.created_at || '').slice(0, 19).replace('T', ' ');
          var dur = j.duration_s ? j.duration_s.toFixed(1) + 's' : '\u2014';
          tbody +=
            '<tr>' +
              '<td style="color:var(--empire-fog)">' + (j.id || '').slice(0, 8) + '</td>' +
              '<td class="topic-cell" title="' + j.topic.replace(/'/g, '\\u0027') + '">' + (j.topic || '\u2014').slice(0, 60) + '</td>' +
              '<td><span class="status-dot ' + statusClass(j.status) + '"></span>' + statusLabel(j.status) + '</td>' +
              '<td>' + (j.voice_provider || '\u2014') + '</td>' +
              '<td>' + (j.source || '\u2014') + '</td>' +
              '<td>' + dur + '</td>' +
              '<td style="color:var(--empire-fog);font-size:11px">' + created + '</td>' +
            '</tr>';
        }}
        if (!tbody) {{
          tbody = '<tr><td colspan="7" style="text-align:center;color:var(--empire-mist)">No jobs yet</td></tr>';
        }}
        document.getElementById('buffy-table-body').innerHTML = tbody;

      }})
      .catch(function(err) {{
        var kpis = document.getElementById('buffy-kpis');
        kpis.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:60px 20px;color:var(--empire-mist)">' +
          '<div style="font-size:32px;margin-bottom:12px;opacity:0.5">🔌</div>' +
          '<div style="font-size:13px">Could not connect to Buffy Buffer API</div>' +
          '<div style="font-size:10px;margin-top:8px;font-family:var(--font-mono);color:#F43F5E">' + String(err) + '</div>' +
          '</div>';
      }});
  }}

  // Initial load
  loadStats();

  // Auto-refresh every 10s
  setInterval(loadStats, 10000);

  // Keyboard shortcut: R to refresh
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'r' && !e.ctrlKey && !e.metaKey && !e.target.closest('input,textarea,select')) {{
      window.location.href = '/buffy';
    }}
  }});
}})();
</script>

</body>
</html>"""
