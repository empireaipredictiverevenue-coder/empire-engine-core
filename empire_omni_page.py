"""
EMPIRE V49 · OMNI BRIDGE DASHBOARD (v2)
==========================================
Interactive dashboard at /omni with Chart.js pie/doughnut/bar charts,
animated stat counters, smooth transitions, and live auto-refresh.

Fetches live data from /api/v6/omni/stats with auth token from localStorage.
"""

from empire_tokens import empire_head

_PAGE_CSS = """
/* ── Base ── */
.omni-wrap {
  max-width: 1100px;
  margin: 0 auto;
  padding: 40px 32px 80px;
}

/* ── Hero ── */
.omni-hero {
  margin-bottom: 40px;
  position: relative;
}
.omni-hero h1 {
  font-family: var(--font-display);
  font-weight: 200;
  font-size: 36px;
  letter-spacing: -0.04em;
  color: var(--empire-white);
  margin-bottom: 8px;
  animation: omni-fade-in 0.6s ease-out;
}
.omni-hero h1 em {
  font-style: italic;
  font-weight: 700;
  color: var(--signal-teal);
}
.omni-hero p {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--empire-fog);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  animation: omni-fade-in 0.6s ease-out 0.1s both;
}
.omni-hero .status-badge {
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
  animation: omni-fade-in 0.6s ease-out 0.2s both;
}
.omni-hero .status-badge .dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--signal-teal);
  box-shadow: 0 0 8px rgba(68,229,184,0.4);
  animation: omni-pulse 1.6s ease-in-out infinite;
}
@keyframes omni-pulse {
  0%,100% { opacity: 1; }
  50% { opacity: .5; }
}
@keyframes omni-fade-in {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes omni-count-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Last updated ── */
.omni-timestamp {
  font-family: var(--font-mono);
  font-size: 8px;
  color: var(--empire-fog);
  letter-spacing: 0.12em;
  margin-top: 6px;
  opacity: 0.8;
  animation: omni-fade-in 0.6s ease-out 0.3s both;
}

/* ── Stats grid ── */
.omni-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 32px;
}
.omni-stat {
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: 20px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.25s, transform 0.2s, box-shadow 0.2s;
  cursor: default;
  animation: omni-fade-in 0.5s ease-out both;
}
.omni-stat:nth-child(1) { animation-delay: 0.05s; }
.omni-stat:nth-child(2) { animation-delay: 0.10s; }
.omni-stat:nth-child(3) { animation-delay: 0.15s; }
.omni-stat:nth-child(4) { animation-delay: 0.20s; }
.omni-stat:nth-child(5) { animation-delay: 0.25s; }
.omni-stat:nth-child(6) { animation-delay: 0.30s; }
.omni-stat:hover {
  border-color: var(--empire-border);
  transform: translateY(-2px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}
.omni-stat::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 2px; height: 100%;
  transition: width 0.2s;
}
.omni-stat:hover::before {
  width: 3px;
}
.omni-stat.green::before { background: var(--signal-teal); }
.omni-stat.blue::before  { background: var(--strike-cyan); }
.omni-stat.amber::before { background: var(--status-amber); }
.omni-stat.red::before   { background: #F43F5E; }

.omni-stat-icon {
  font-size: 24px;
  margin-bottom: 12px;
  opacity: 0.7;
  transition: transform 0.2s, opacity 0.2s;
}
.omni-stat:hover .omni-stat-icon {
  opacity: 1;
  transform: scale(1.1);
}
.omni-stat-label {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 4px;
}
.omni-stat-value {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 32px;
  line-height: 1;
  letter-spacing: -0.04em;
  color: var(--empire-white);
  font-feature-settings: 'tnum' 1;
  transition: color 0.3s;
}
.omni-stat-value.green { color: var(--signal-teal); }
.omni-stat-value.blue  { color: var(--strike-cyan); }
.omni-stat-value.amber { color: var(--status-amber); }
.omni-stat-value.red   { color: #F43F5E; }

/* ── Chart row ── */
.omni-charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 32px;
  animation: omni-fade-in 0.6s ease-out 0.35s both;
}
.omni-chart-card {
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: 20px;
  transition: border-color 0.25s, transform 0.2s;
}
.omni-chart-card:hover {
  border-color: var(--empire-border);
  transform: translateY(-1px);
}
.omni-chart-card .chart-title {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 16px;
}
.omni-chart-card .chart-wrap {
  position: relative;
  width: 100%;
  height: 220px;
}
.omni-chart-card .chart-wrap canvas {
  width: 100% !important;
  height: 100% !important;
}

/* ── Pipeline flow ── */
.omni-pipeline {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  margin-bottom: 40px;
  padding: 24px 20px;
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  animation: omni-fade-in 0.6s ease-out 0.4s both;
  transition: border-color 0.25s;
}
.omni-pipeline:hover {
  border-color: var(--empire-border);
}
.omni-pipeline-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 20px;
  min-width: 100px;
  position: relative;
  transition: transform 0.2s, background 0.2s;
  border-radius: var(--radius-sm);
  cursor: default;
}
.omni-pipeline-step:hover {
  transform: scale(1.05);
  background: rgba(122,140,163,0.06);
}
.omni-pipeline-step .icon {
  font-size: 28px;
  transition: transform 0.2s;
}
.omni-pipeline-step:hover .icon {
  transform: scale(1.15);
}
.omni-pipeline-step .label {
  font-family: var(--font-mono);
  font-size: 8px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--empire-mist);
  transition: color 0.2s;
}
.omni-pipeline-step:hover .label {
  color: var(--empire-silver);
}
.omni-pipeline-step .count {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 600;
  color: var(--empire-white);
  font-feature-settings: 'tnum' 1;
  transition: color 0.3s;
}
.omni-pipeline-step .count.green { color: var(--signal-teal); }
.omni-pipeline-step .count.amber { color: var(--status-amber); }
.omni-pipeline-step .count.red   { color: #F43F5E; }
.omni-pipeline-arrow {
  font-size: 20px;
  color: var(--empire-mist);
  opacity: 0.4;
  padding: 0 8px;
  transition: opacity 0.2s, transform 0.2s;
}
.omni-pipeline:hover .omni-pipeline-arrow {
  opacity: 0.7;
}

/* ── Detail table ── */
.omni-detail {
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  overflow: hidden;
  animation: omni-fade-in 0.6s ease-out 0.45s both;
  transition: border-color 0.25s;
}
.omni-detail:hover {
  border-color: var(--empire-border);
}
.omni-detail-header {
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
.omni-detail-header .refresh-btn {
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
.omni-detail-header .refresh-btn:hover {
  color: var(--empire-white);
  border-color: var(--empire-border-hi);
  background: rgba(68,229,184,0.06);
  transform: translateY(-1px);
}
.omni-detail-header .refresh-btn:active {
  transform: translateY(0);
}

.omni-table {
  width: 100%;
  border-collapse: collapse;
}
.omni-table th {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 600;
  padding: 12px 20px;
  border-bottom: 1px solid var(--empire-divider);
  text-align: left;
  background: rgba(0,0,0,0.15);
}
.omni-table td {
  padding: 12px 20px;
  border-bottom: 1px solid rgba(122,140,163,0.04);
  font-size: 13px;
  color: var(--empire-silver);
  font-family: var(--font-mono);
  font-feature-settings: 'tnum' 1;
  transition: background 0.2s;
}
.omni-table tr:hover td {
  background: rgba(122,140,163,0.03);
}
.omni-table tr:last-child td { border-bottom: none; }
.omni-table .val-green { color: var(--signal-teal); font-weight: 600; }
.omni-table .val-amber { color: var(--status-amber); font-weight: 600; }
.omni-table .val-red   { color: #F43F5E; font-weight: 600; }
.omni-table .val-dim   { color: var(--empire-mist); }

/* ── Auto-refresh indicator ── */
.omni-auto-refresh {
  font-family: var(--font-mono);
  font-size: 8px;
  color: var(--empire-fog);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}
.omni-auto-refresh .dot {
  width: 4px; height: 4px;
  border-radius: 50%;
  background: var(--signal-teal);
  animation: omni-pulse 1.6s ease-in-out infinite;
}

/* ── Empty / loading ── */
.omni-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  text-align: center;
  color: var(--empire-mist);
  font-family: var(--font-mono);
  font-size: 11px;
}
.omni-loading .spinner {
  width: 22px; height: 22px;
  border-radius: 50%;
  border: 2px solid var(--empire-border);
  border-top-color: var(--signal-teal);
  animation: omni-spin 0.8s linear infinite;
  margin-bottom: 16px;
}
@keyframes omni-spin { to { transform: rotate(360deg); } }

/* ── Refresh pulse overlay ── */
@keyframes omni-refresh-pulse {
  0% { opacity: 0; }
  30% { opacity: 0.08; }
  100% { opacity: 0; }
}
.omni-refreshing::after {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--signal-teal);
  animation: omni-refresh-pulse 0.6s ease-out;
  pointer-events: none;
  border-radius: var(--radius-md);
}

/* ── Footer ── */
.omni-foot {
  margin-top: 48px;
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
  animation: omni-fade-in 0.6s ease-out 0.5s both;
}
.omni-foot a {
  color: var(--empire-mist);
  text-decoration: none;
  transition: color 0.2s;
}
.omni-foot a:hover {
  color: var(--signal-teal);
}
.omni-foot a em {
  font-style: normal;
  color: var(--strike-cyan);
}

/* ── Responsive ── */
@media (max-width: 860px) {
  .omni-charts { grid-template-columns: 1fr; }
  .omni-stats { grid-template-columns: repeat(2, 1fr); }
  .omni-pipeline { flex-wrap: wrap; gap: 8px; }
  .omni-pipeline-arrow { transform: rotate(90deg); }
}
@media (max-width: 540px) {
  .omni-stats { grid-template-columns: 1fr; }
  .omni-wrap { padding: 24px 16px; }
  .omni-hero h1 { font-size: 28px; }
}
"""


def omni_dashboard_page() -> str:
    head = empire_head(
        title="Omni Bridge · Empire AI",
        extra=_PAGE_CSS,
        page="omni",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="omni-wrap" id="omni-wrap">

  <div class="omni-hero">
    <h1>Omni <em>Bridge</em></h1>
    <p>Audio → Transcript → Brand → Social Pipeline</p>
    <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
      <div class="status-badge">
        <span class="dot"></span>
        <span>Service running on port 8040</span>
      </div>
      <div class="omni-timestamp" id="omni-timestamp"></div>
    </div>
  </div>

  <!-- Stats grid (filled by JS) -->
  <div id="omni-stats-grid" class="omni-stats" style="position:relative">
    <div class="omni-loading" id="omni-loading">
      <div class="spinner"></div>
      <div>Loading Omni Bridge stats...</div>
    </div>
  </div>

  <!-- Charts row (hidden until data loads) -->
  <div class="omni-charts" id="omni-charts-row" style="display:none">
    <div class="omni-chart-card">
      <div class="chart-title">Pipeline Distribution</div>
      <div class="chart-wrap"><canvas id="chart-pie"></canvas></div>
    </div>
    <div class="omni-chart-card">
      <div class="chart-title">Success Rate</div>
      <div class="chart-wrap"><canvas id="chart-gauge"></canvas></div>
    </div>
  </div>

  <!-- Pipeline flow (filled by JS) -->
  <div class="omni-pipeline" id="omni-pipeline-flow" style="display:none">
    <div class="omni-pipeline-step">
      <div class="icon">🎤</div>
      <div class="label">Transcribed</div>
      <div class="count" id="pipe-transcribed">—</div>
    </div>
    <div class="omni-pipeline-arrow">→</div>
    <div class="omni-pipeline-step">
      <div class="icon">🔍</div>
      <div class="label">Brands Found</div>
      <div class="count" id="pipe-brands">—</div>
    </div>
    <div class="omni-pipeline-arrow">→</div>
    <div class="omni-pipeline-step">
      <div class="icon">📢</div>
      <div class="label">Posts Made</div>
      <div class="count" id="pipe-posts">—</div>
    </div>
    <div class="omni-pipeline-arrow">→</div>
    <div class="omni-pipeline-step">
      <div class="icon">⚠️</div>
      <div class="label">Errors</div>
      <div class="count" id="pipe-errors">—</div>
    </div>
  </div>

  <!-- Detail table -->
  <div class="omni-detail">
    <div class="omni-detail-header">
      <span>Pipeline Metrics</span>
      <div style="display:flex;align-items:center;gap:12px">
        <span class="omni-auto-refresh"><span class="dot"></span> Auto-refresh 15s</span>
        <button class="refresh-btn" onclick="window.location.href='/omni'">↻ Refresh</button>
      </div>
    </div>
    <table class="omni-table" id="omni-detail-table">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Value</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody id="omni-detail-body">
        <tr><td colspan="3" style="text-align:center;color:var(--empire-mist)">Waiting for data...</td></tr>
      </tbody>
    </table>
  </div>

  <div class="omni-foot">
    <span>
      <a href="/command">Command Deck</a>
      <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
      <a href="/fleet">Fleet Dashboard</a>
      <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
      <a href="/api/v6/omni/stats"><em>API → JSON</em></a>
    </span>
    <span>Empire AI · Omni Bridge Monitor</span>
  </div>

</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script>
(function() {{
  // ── Format numbers ──
  function fmt(n) {{
    if (n == null || n === undefined) return '—';
    return Number(n).toLocaleString();
  }}

  // ── Animated count-up ──
  function animateValue(el, target, duration, suffix) {{
    suffix = suffix || '';
    var start = 0;
    var startTime = null;
    function step(timestamp) {{
      if (!startTime) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      // Ease out cubic
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = Math.round(eased * target);
      el.textContent = fmt(current) + suffix;
      if (progress < 1) {{
        requestAnimationFrame(step);
      }} else {{
        el.textContent = fmt(target) + suffix;
      }}
    }}
    requestAnimationFrame(step);
  }}

  // ── Chart instances ──
  var pieChart = null;
  var gaugeChart = null;

  // ── Color palette ──
  var COLORS = {{
    teal: 'rgba(68,229,184,1)',
    cyan: 'rgba(6,182,212,1)',
    amber: 'rgba(245,158,11,1)',
    red: 'rgba(244,63,94,1)',
    slate: 'rgba(122,140,163,1)',
  }};
  var COLORS_ALPHA = {{
    teal: 'rgba(68,229,184,0.2)',
    cyan: 'rgba(6,182,212,0.2)',
    amber: 'rgba(245,158,11,0.2)',
    red: 'rgba(244,63,94,0.2)',
  }};

  // ── Create/update pie chart ──
  function updatePieChart(p, t, b, po, e) {{
    var ctx = document.getElementById('chart-pie').getContext('2d');
    var data = {{
      labels: ['Processed', 'Transcribed', 'Brands Found', 'Posts', 'Errors'],
      datasets: [{{
        data: [p, t, b, po, e],
        backgroundColor: [COLORS.teal, COLORS.cyan, COLORS.teal, COLORS.cyan, COLORS.red],
        borderColor: '#0a0e17',
        borderWidth: 2,
        hoverBorderColor: COLORS.teal,
        hoverBorderWidth: 3,
        hoverOffset: 12,
      }}]
    }};
    var config = {{
      type: 'doughnut',
      data: data,
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        cutout: '60%',
        plugins: {{
          legend: {{
            position: 'right',
            labels: {{
              color: '#c4cdd8',
              font: {{ family: "'Geist Mono',monospace", size: 9, weight: '600' }},
              boxWidth: 12,
              boxHeight: 8,
              padding: 12,
              usePointStyle: true,
              pointStyle: 'circle',
            }}
          }},
          tooltip: {{
            backgroundColor: 'rgba(10,14,23,0.95)',
            titleFont: {{ family: "'Geist Mono',monospace", size: 10 }},
            bodyFont: {{ family: "'Geist Mono',monospace", size: 11 }},
            padding: 12,
            cornerRadius: 6,
            borderColor: 'rgba(122,140,163,0.2)',
            borderWidth: 1,
            callbacks: {{
              label: function(ctx) {{
                var total = ctx.dataset.data.reduce((a,b) => a + b, 0);
                var pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                return ' ' + ctx.label + ': ' + fmt(ctx.parsed) + ' (' + pct + '%)';
              }}
            }}
          }}
        }},
        animation: {{
          animateRotate: true,
          duration: 1200,
          easing: 'easeOutQuart',
        }},
      }}
    }};
    if (pieChart) {{
      pieChart.data = data;
      pieChart.update('show');
    }} else {{
      pieChart = new Chart(ctx, config);
    }}
  }}

  // ── Create/update gauge (success rate doughnut) ──
  function updateGaugeChart(p, e) {{
    var success = p > 0 ? Math.max(0, Math.round(((p - e) / p) * 100)) : 0;
    var fail = 100 - success;
    var ctx = document.getElementById('chart-gauge').getContext('2d');
    var color = success >= 80 ? COLORS.teal : (success >= 50 ? COLORS.amber : COLORS.red);
    var data = {{
      labels: ['Success', 'Failure'],
      datasets: [{{
        data: [success, fail],
        backgroundColor: [color, 'rgba(122,140,163,0.12)'],
        borderColor: '#0a0e17',
        borderWidth: 2,
      }}]
    }};
    var config = {{
      type: 'doughnut',
      data: data,
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        cutout: '75%',
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            backgroundColor: 'rgba(10,14,23,0.95)',
            titleFont: {{ family: "'Geist Mono',monospace", size: 10 }},
            bodyFont: {{ family: "'Geist Mono',monospace", size: 11 }},
            padding: 12,
            cornerRadius: 6,
            borderColor: 'rgba(122,140,163,0.2)',
            borderWidth: 1,
          }}
        }},
        animation: {{
          animateRotate: true,
          duration: 1000,
          easing: 'easeOutQuart',
        }},
      }},
      plugins: [{{
        id: 'gaugeCenterText',
        afterDraw: function(chart) {{
          var w = chart.width, h = chart.height;
          var ctx2 = chart.ctx;
          ctx2.save();
          var centerX = w / 2;
          var centerY = h / 2 + 4;
          // Percentage text
          ctx2.font = '600 32px "Geist Mono",monospace';
          ctx2.textAlign = 'center';
          ctx2.textBaseline = 'middle';
          ctx2.fillStyle = color;
          ctx2.fillText(success + '%', centerX, centerY - 10);
          // Label
          ctx2.font = '400 9px "Geist Mono",monospace';
          ctx2.fillStyle = '#7a8ca3';
          ctx2.fillText('SUCCESS RATE', centerX, centerY + 20);
          ctx2.restore();
        }}
      }}]
    }};
    if (gaugeChart) {{
      gaugeChart.data = data;
      gaugeChart.update('show');
    }} else {{
      gaugeChart = new Chart(ctx, config);
    }}
  }}

  // ── Main load function ──
  function loadStats() {{
    // Refresh pulse on the stats grid
    var grid = document.getElementById('omni-stats-grid');
    grid.classList.add('omni-refreshing');
    setTimeout(function() {{ grid.classList.remove('omni-refreshing'); }}, 600);

    var TOKEN = window.EMPIRE_TOKEN || localStorage.getItem('hub_token') || '';
    fetch('/api/v6/omni/stats', {{
          headers: TOKEN ? {{ 'Authorization': 'Bearer ' + TOKEN }} : {{}}
        }})
      .then(function(r) {{ return r.json(); }})
      .then(function(data) {{
        var p = data.processed || 0;
        var t = data.transcribed || 0;
        var b = data.brands_found || 0;
        var po = data.posted || 0;
        var e = data.errors || 0;

        // ── Build stats grid with animated counters ──
        grid.innerHTML =
          '<div class="omni-stat green" id="stat-processed">' +
            '<div class="omni-stat-icon">🎤</div>' +
            '<div class="omni-stat-label">Processed</div>' +
            '<div class="omni-stat-value green" id="val-processed">0</div>' +
          '</div>' +
          '<div class="omni-stat blue" id="stat-transcribed">' +
            '<div class="omni-stat-icon">📝</div>' +
            '<div class="omni-stat-label">Transcribed</div>' +
            '<div class="omni-stat-value blue" id="val-transcribed">0</div>' +
          '</div>' +
          '<div class="omni-stat green" id="stat-brands">' +
            '<div class="omni-stat-icon">🏷️</div>' +
            '<div class="omni-stat-label">Brands Found</div>' +
            '<div class="omni-stat-value green" id="val-brands">0</div>' +
          '</div>' +
          '<div class="omni-stat blue" id="stat-posts">' +
            '<div class="omni-stat-icon">📢</div>' +
            '<div class="omni-stat-label">Posts</div>' +
            '<div class="omni-stat-value blue" id="val-posts">0</div>' +
          '</div>' +
          '<div class="omni-stat ' + (e > 0 ? 'red' : 'green') + '" id="stat-errors">' +
            '<div class="omni-stat-icon">' + (e > 0 ? '⚠️' : '✅') + '</div>' +
            '<div class="omni-stat-label">Errors</div>' +
            '<div class="omni-stat-value ' + (e > 0 ? 'red' : 'green') + '" id="val-errors">0</div>' +
          '</div>' +
          '<div class="omni-stat amber" id="stat-success">' +
            '<div class="omni-stat-icon">📊</div>' +
            '<div class="omni-stat-label">Success Rate</div>' +
            '<div class="omni-stat-value amber" id="val-success">0%</div>' +
          '</div>';

        // Animate count-up
        animateValue(document.getElementById('val-processed'), p, 800);
        animateValue(document.getElementById('val-transcribed'), t, 800);
        animateValue(document.getElementById('val-brands'), b, 800);
        animateValue(document.getElementById('val-posts'), po, 800);
        animateValue(document.getElementById('val-errors'), e, 800);
        // Success rate: reuse animateValue with suffix
        var successRate = p > 0 ? Math.max(0, Math.round(((p - e) / p) * 100)) : 0;
        animateValue(document.getElementById('val-success'), successRate, 800, '%');

        // ── Show charts and pipeline ──
        document.getElementById('omni-charts-row').style.display = 'grid';
        document.getElementById('omni-pipeline-flow').style.display = 'flex';

        // ── Update pipeline ──
        document.getElementById('pipe-transcribed').textContent = fmt(t);
        document.getElementById('pipe-brands').textContent = fmt(b);
        document.getElementById('pipe-posts').textContent = fmt(po);
        var pipeErrors = document.getElementById('pipe-errors');
        pipeErrors.textContent = fmt(e);
        pipeErrors.className = 'count' + (e > 0 ? ' red' : ' green');

        // ── Update charts ──
        updatePieChart(p, t, b, po, e);
        updateGaugeChart(p, e);

        // ── Update detail table ──
        var body = document.getElementById('omni-detail-body');
        body.innerHTML =
          '<tr><td class="val-dim">Processed</td><td class="val-green">' + fmt(p) + '</td><td class="val-dim">Total audio pipelines run</td></tr>' +
          '<tr><td class="val-dim">Transcribed</td><td class="val-green">' + fmt(t) + '</td><td class="val-dim">Successfully transcribed via Deepgram Nova-3</td></tr>' +
          '<tr><td class="val-dim">Brands Found</td><td class="val-green">' + fmt(b) + '</td><td class="val-dim">Brands identified via BuyerSpy analysis</td></tr>' +
          '<tr><td class="val-dim">Posts</td><td class="val-blue" style="color:var(--strike-cyan);font-weight:600">' + fmt(po) + '</td><td class="val-dim">Social posts syndicated via Zernio</td></tr>' +
          '<tr><td class="val-dim">Errors</td><td class="' + (e > 0 ? 'val-red' : 'val-dim') + '">' + fmt(e) + '</td><td class="val-dim">Pipeline failures</td></tr>' +
          '<tr><td class="val-dim">Success Rate</td><td class="val-amber">' + successRate + '%</td><td class="val-dim">Ratio of successful pipelines to total runs</td></tr>';

        // ── Update timestamp ──
        var ts = document.getElementById('omni-timestamp');
        var now = new Date();
        ts.textContent = 'Last updated: ' + now.toLocaleTimeString() + ' · ' + now.toLocaleDateString();
      }})
      .catch(function(err) {{
        // Hide charts and pipeline on error to avoid stale data
        document.getElementById('omni-charts-row').style.display = 'none';
        document.getElementById('omni-pipeline-flow').style.display = 'none';
        var grid = document.getElementById('omni-stats-grid');
        grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:60px 20px;color:var(--empire-mist)">' +
          '<div style="font-size:32px;margin-bottom:12px;opacity:0.5">🔌</div>' +
          '<div style="font-size:13px">Could not connect to Omni Bridge API</div>' +
          '<div style="font-size:10px;margin-top:8px;font-family:var(--font-mono);color:#F43F5E">' + String(err).replace(/</g,'&lt;') + '</div>' +
          '</div>';
      }});
  }}

  // ── Init ──
  loadStats();
  setInterval(loadStats, 15000);

  // Keyboard shortcut: R to refresh
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'r' && !e.ctrlKey && !e.metaKey && !e.target.closest('input,textarea,select')) {{
      window.location.href = '/omni';
    }}
  }});
}})();
</script>

</body>
</html>"""
