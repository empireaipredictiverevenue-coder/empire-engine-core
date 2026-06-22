"""
EMPIRE V49 · OUTREACH PERFORMANCE VIEW
========================================
Standalone page at /view/outreach — auto-fetches /api/v1/outreach/template-stats
and renders a stat-cards + table view. Uses localStorage.hub_token for auth
(the same as the Command SPA). Links back to /command.
"""


def outreach_view_page() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Empire AI · Outreach Performance</title>
  <meta name="description" content="Empire AI outreach performance dashboard. Template A/B testing, reply rates, conversion rates, and per-variant breakdown across all pipelines.">
  <meta name="keywords" content="outreach performance, A/B testing, reply rate, conversion rate, template analytics">
  <meta name="robots" content="index, follow">
  <meta property="og:type" content="website">
  <meta property="og:title" content="Empire AI · Outreach Performance">
  <meta property="og:description" content="Empire AI outreach performance dashboard. Template A/B testing, reply rates, and conversion analytics.">
  <meta property="og:url" content="https://empire-ai.co.uk/view/outreach">
  <meta property="og:site_name" content="Empire AI">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Empire AI · Outreach Performance">
  <meta name="twitter:description" content="Empire AI outreach A/B test analytics, reply rates, and conversion tracking.">
  <link rel="canonical" href="https://empire-ai.co.uk/view/outreach">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
      background: #0A1A2F; color: #F8FAFD; min-height: 100vh;
      background-image:
        radial-gradient(ellipse at top right, rgba(68,229,184,0.06), transparent 50%),
        radial-gradient(ellipse at bottom left, rgba(90,200,250,0.05), transparent 50%);
    }
    :root {
      --teal: #44E5B8; --cyan: #5AC8FA; --amber: #FFB800; --red: #FF4444;
      --surface: #15263F; --elevated: #1A2D4A; --border: rgba(122,140,163,0.18);
      --divider: rgba(122,140,163,0.1); --mist: #7A8CA3; --fog: #4A5A72;
      --white: #F8FAFD; --silver: #A0B4C8;
    }
    .page { max-width: 960px; margin: 0 auto; padding: 40px 32px; }
    @media (max-width: 768px) { .page { padding: 20px 16px; } }

    .head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 30px; flex-wrap: wrap; gap: 12px; }
    .head-left { }
    .head-title { font-size: 24px; font-weight: 200; letter-spacing: -0.03em; }
    .head-title em { color: var(--teal); font-style: italic; font-weight: 500; }
    .head-sub { font-family: 'JetBrains Mono', 'SF Mono', monospace; font-size: 10px; color: var(--mist); letter-spacing: 0.18em; text-transform: uppercase; margin-top: 6px; }
    .head-right { display: flex; gap: 10px; align-items: center; }
    .head-back {
      color: var(--fog); text-decoration: none; font-family: 'JetBrains Mono', monospace;
      font-size: 10px; letter-spacing: 0.12em; padding: 8px 14px;
      border: 1px solid rgba(122,140,163,0.18); border-radius: 4px; transition: all 0.15s;
    }
    .head-back:hover { color: var(--white); border-color: var(--mist); }
    .refresh-btn {
      padding: 8px 14px; font-family: 'JetBrains Mono', monospace; font-size: 10px;
      letter-spacing: 0.12em; text-transform: uppercase; border: 1px solid rgba(68,229,184,0.25);
      background: transparent; color: var(--teal); cursor: pointer; border-radius: 4px;
      transition: all 0.15s;
    }
    .refresh-btn:hover { background: rgba(68,229,184,0.08); }
    .refresh-btn:disabled { opacity: 0.4; cursor: wait; }

    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 28px; }
    @media (max-width: 768px) { .stats { grid-template-columns: repeat(2, 1fr); } }
    .stat-card {
      background: var(--surface); border: 1px solid var(--border); padding: 18px 20px;
      position: relative; overflow: hidden; transition: border-color 0.2s;
    }
    .stat-card:hover { border-color: var(--mist); }
    .stat-card::before {
      content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
      background: linear-gradient(90deg, transparent, rgba(68,229,184,0.25), transparent);
    }
    .stat-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--mist); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 14px; }
    .stat-value { font-family: 'JetBrains Mono', monospace; font-weight: 500; font-size: 28px; color: var(--white); line-height: 1; }
    .stat-value.teal { color: var(--teal); }
    .stat-value.cyan { color: var(--cyan); }
    .stat-value.amber { color: var(--amber); }
    .stat-meta { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--fog); margin-top: 8px; letter-spacing: 0.04em; }

    .panel { background: var(--surface); border: 1px solid var(--border); padding: 20px; margin-bottom: 24px; }
    .panel-h { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--divider); }
    .panel-title { font-weight: 500; font-size: 13px; letter-spacing: 0.02em; }
    .panel-tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--fog); letter-spacing: 0.14em; text-transform: uppercase; }

    .tbl-full { width: 100%; border-collapse: collapse; font-size: 12px; }
    .tbl-full thead th {
      font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--mist);
      letter-spacing: 0.14em; text-transform: uppercase; text-align: left;
      padding: 12px 14px; border-bottom: 1px solid var(--divider);
      background: var(--elevated); font-weight: 500;
    }
    .tbl-full thead th.numeric { text-align: right; }
    .tbl-full tbody td {
      padding: 12px 14px; border-bottom: 1px solid var(--divider);
      color: var(--silver); font-family: 'JetBrains Mono', monospace; font-size: 11px;
    }
    .tbl-full tbody td.numeric { text-align: right; }
    .tbl-full tbody tr:hover { background: var(--elevated); }
    .tbl-full tbody tr:last-child td { border-bottom: none; }

    .variant-name { font-weight: 600; color: var(--white); font-size: 12px; letter-spacing: 0.02em; }
    .rate-bar-wrap { height: 8px; background: var(--elevated); border-radius: 4px; overflow: hidden; min-width: 80px; }
    .rate-bar { height: 100%; border-radius: 4px; transition: width 0.6s ease-out; min-width: 2px; }
    .rate-bar.reply { background: var(--cyan); }
    .rate-bar.conv { background: var(--teal); }

    .totals-row td { border-top: 2px solid rgba(68,229,184,0.15); font-weight: 600; color: var(--white); }

    .loading { text-align: center; padding: 64px 0; }
    .loading-spinner {
      display: inline-block; width: 36px; height: 36px; border: 2px solid var(--divider);
      border-top-color: var(--teal); border-radius: 50%; animation: spin 0.8s linear infinite;
      margin-bottom: 16px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .loading-text { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--mist); letter-spacing: 0.08em; }

    .error { text-align: center; padding: 64px 0; }
    .error-icon { font-size: 36px; color: var(--red); margin-bottom: 12px; }
    .error-title { font-size: 16px; color: var(--red); margin-bottom: 8px; }
    .error-body { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--mist); }

    .foot { margin-top: 32px; text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--fog); letter-spacing: 0.14em; }
  </style>
</head>
<body>
<div class="page">
  <div class="head">
    <div class="head-left">
      <div class="head-title">Outreach <em>Performance</em></div>
      <div class="head-sub">Template A/B Test · Reply & Conversion Rates</div>
    </div>
    <div class="head-right">
      <button class="refresh-btn" onclick="load()" id="refreshBtn">↻ Refresh</button>
      <a class="head-back" href="/command">← Command Deck</a>
    </div>
  </div>

  <div id="content"><div class="loading"><div class="loading-spinner"></div><div class="loading-text">Fetching template stats...</div></div></div>

  <div class="foot">Empire AI V49 · Outreach Performance View</div>
</div>

<script>
const API = '/api/v1/outreach/template-stats';

async function apiFetch(path) {
  const token = localStorage.getItem('hub_token') || '';
  if (!token) { window.location.href = '/command'; return; }
  const headers = { 'Authorization': `Bearer ${token}` };
  const r = await fetch(path, { headers });
  if (r.status === 401) { window.location.href = '/command'; return; }
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
  return r.json();
}

function fmtPct(n) {
  return (n * 100).toFixed(1) + '%';
}

function render(data) {
  const variants = data.variants || [];
  const totalOutreach = data.total_outreach || 0;
  const totalVariants = data.total_variants || 0;
  const totalReplied = variants.reduce((s, v) => s + (v.replied || 0), 0);
  const totalConverted = variants.reduce((s, v) => s + (v.converted || 0), 0);
  const overallReply = totalOutreach > 0 ? totalReplied / totalOutreach : 0;
  const overallConv = totalOutreach > 0 ? totalConverted / totalOutreach : 0;

  let html = '';

  // Stat cards
  html += '<div class="stats">';
  html += `<div class="stat-card"><div class="stat-label">Variants</div><div class="stat-value">${totalVariants}</div><div class="stat-meta">template strategies active</div></div>`;
  html += `<div class="stat-card"><div class="stat-label">Total Outreach</div><div class="stat-value cyan">${totalOutreach}</div><div class="stat-meta">across all pipelines</div></div>`;
  html += `<div class="stat-card"><div class="stat-label">Replied</div><div class="stat-value amber">${totalReplied}</div><div class="stat-meta">${fmtPct(overallReply)} reply rate</div></div>`;
  html += `<div class="stat-card"><div class="stat-label">Converted</div><div class="stat-value teal">${totalConverted}</div><div class="stat-meta">${fmtPct(overallConv)} conversion rate</div></div>`;
  html += '</div>';

  // Table
  html += '<div class="panel">';
  html += '<div class="panel-h"><div class="panel-title">Per-Variant Breakdown</div><div class="panel-tag">idle_asset_outreach + gas_station_outreach</div></div>';
  html += '<table class="tbl-full"><thead><tr>';
  html += '<th>Variant</th>';
  html += '<th class="numeric">Total</th>';
  html += '<th class="numeric">Email</th>';
  html += '<th class="numeric">SMS</th>';
  html += '<th class="numeric">Replied</th>';
  html += '<th class="numeric">Converted</th>';
  html += '<th class="numeric">Reply Rate</th>';
  html += '<th class="numeric">Conv Rate</th>';
  html += '</tr></thead><tbody>';

  for (const v of variants) {
    const replyPct = v.reply_rate || 0;
    const convPct = v.conversion_rate || 0;
    html += '<tr>';
    html += `<td><span class="variant-name">${v.template_variant}</span></td>`;
    html += `<td class="numeric">${v.total}</td>`;
    html += `<td class="numeric">${v.email_sent}</td>`;
    html += `<td class="numeric">${v.sms_sent}</td>`;
    html += `<td class="numeric" style="color: var(--cyan)">${v.replied}</td>`;
    html += `<td class="numeric" style="color: var(--teal)">${v.converted}</td>`;
    html += `<td class="numeric">${fmtPct(replyPct)}</td>`;
    html += `<td class="numeric">${fmtPct(convPct)}</td>`;
    html += '</tr>';
  }

  // Totals row
  html += '<tr class="totals-row">';
  html += '<td><strong>TOTAL</strong></td>';
  html += `<td class="numeric"><strong>${totalOutreach}</strong></td>`;
  html += `<td class="numeric"></td>`;
  html += `<td class="numeric"></td>`;
  html += `<td class="numeric" style="color: var(--cyan)"><strong>${totalReplied}</strong></td>`;
  html += `<td class="numeric" style="color: var(--teal)"><strong>${totalConverted}</strong></td>`;
  html += `<td class="numeric"><strong>${fmtPct(overallReply)}</strong></td>`;
  html += `<td class="numeric"><strong>${fmtPct(overallConv)}</strong></td>`;
  html += '</tr>';

  html += '</tbody></table></div>';

  // Visual bar chart
  html += '<div class="panel">';
  html += '<div class="panel-h"><div class="panel-title">Reply & Conversion Rates</div><div class="panel-tag">visual comparison</div></div>';

  for (const v of variants) {
    const replyPct = (v.reply_rate || 0) * 100;
    const convPct = (v.conversion_rate || 0) * 100;
    html += `<div style="margin-bottom: 16px;">`;
    html += `<div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--white); font-weight: 500;">${v.template_variant} <span style="color: var(--mist); font-weight: 400;">${v.total} records</span></div>`;

    html += `<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">`;
    html += `<span style="font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--cyan); width: 60px; text-align: right;">Reply</span>`;
    html += `<div class="rate-bar-wrap" style="flex:1"><div class="rate-bar reply" style="width:${Math.max(replyPct, 2)}%"></div></div>`;
    html += `<span style="font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--cyan); width: 45px; text-align: left;">${replyPct.toFixed(1)}%</span>`;
    html += `</div>`;

    html += `<div style="display: flex; align-items: center; gap: 8px;">`;
    html += `<span style="font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--teal); width: 60px; text-align: right;">Conv</span>`;
    html += `<div class="rate-bar-wrap" style="flex:1"><div class="rate-bar conv" style="width:${Math.max(convPct, 2)}%"></div></div>`;
    html += `<span style="font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--teal); width: 45px; text-align: left;">${convPct.toFixed(1)}%</span>`;
    html += `</div>`;

    html += `</div>`;
  }
  html += '</div>';

  return html;
}

function renderError(msg) {
  return `<div class="error">
    <div class="error-icon">⚠</div>
    <div class="error-title">Could not load data</div>
    <div class="error-body">${msg}<br><br>Make sure you're signed in at <a href="/command" style="color: var(--teal);">/command</a> first.</div>
  </div>`;
}

async function load() {
  const btn = document.getElementById('refreshBtn');
  if (btn) btn.disabled = true;
  const el = document.getElementById('content');
  el.innerHTML = '<div class="loading"><div class="loading-spinner"></div><div class="loading-text">Fetching...</div></div>';

  try {
    const data = await apiFetch(API);
    el.innerHTML = render(data);
  } catch (e) {
    el.innerHTML = renderError(e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Auto-load on page open
load();
</script>
</body>
</html>"""
