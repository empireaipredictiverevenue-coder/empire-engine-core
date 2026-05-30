"""
EMPIRE V49 · COMMAND SPA
========================
Single-page React app served at /command. Bearer-auth via
localStorage.hub_token (set by /auth/verify on magic-link login).

Architecture:
  - No build step. React 18 + htm via esm.sh import map.
  - Hash routes: #/pulse #/pipeline #/dispatch #/inbound #/payouts
                 #/contractors #/console #/audit #/operators
  - All API calls go through apiFetch() which attaches Authorization: Bearer.
  - WebSocket /ws/live for live event tail (uses same token in query string).

All sections are wired end-to-end to their /api endpoints.
"""

from empire_tokens import EMPIRE_FONTS, EMPIRE_TOKENS_CSS, EMPIRE_BASE_CSS


def command_spa_page() -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Empire AI · Command</title>
  {EMPIRE_FONTS}
  <style>{EMPIRE_TOKENS_CSS}</style>
  <style>{EMPIRE_BASE_CSS}</style>
  <style>{_SPA_CSS}</style>
</head>
<body>
  <div id="root"></div>
  <script type="importmap">
  {{
    "imports": {{
      "react":           "https://esm.sh/react@18.3.1",
      "react-dom/client":"https://esm.sh/react-dom@18.3.1/client",
      "htm":             "https://esm.sh/htm@3.1.1"
    }}
  }}
  </script>
  <script type="module">{_SPA_JS}</script>
</body>
</html>"""


_SPA_CSS = """
/* ── APP SHELL ────────────────────────────────────────────────────── */
.app { position: relative; z-index: 1; display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }
.boot { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 16px; z-index: 2; }
.boot-mark { font-family: var(--font-display); font-weight: 700; font-size: 22px; letter-spacing: 0.18em; }
.boot-mark span { color: var(--strike-cyan); }
.boot-tag { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.28em; text-transform: uppercase; }

/* ── SIDEBAR ──────────────────────────────────────────────────────── */
.nav { background: var(--empire-surface); border-right: 1px solid var(--empire-divider); padding: 24px 0; }
.nav-brand { padding: 0 24px 20px; border-bottom: 1px solid var(--empire-divider); margin-bottom: 16px; }
.nav-brand-row { display: flex; align-items: baseline; gap: 6px; }
.nav-brand-e { font-family: var(--font-display); font-weight: 700; font-size: 18px; letter-spacing: 0.18em; }
.nav-brand-ai { font-family: var(--font-display); font-weight: 700; font-size: 18px; letter-spacing: 0.18em; color: var(--strike-cyan); }
.nav-tag { font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog); letter-spacing: 0.28em; text-transform: uppercase; margin-top: 6px; }
.nav-item { display: flex; align-items: center; padding: 10px 24px; color: var(--empire-mist); text-decoration: none; font-size: 13px; transition: all 0.15s var(--ease-snap); cursor: pointer; border-left: 2px solid transparent; }
.nav-item:hover { color: var(--empire-white); background: var(--empire-elevated); }
.nav-item.active { color: var(--signal-teal); background: var(--signal-teal-soft); border-left-color: var(--signal-teal); }
.nav-item-dot { display: inline-block; width: 4px; height: 4px; border-radius: var(--radius-pill); background: var(--empire-fog); margin-right: 14px; flex-shrink: 0; }
.nav-item.active .nav-item-dot { background: var(--signal-teal); box-shadow: var(--glow-signal); }

/* ── TOP BAR ──────────────────────────────────────────────────────── */
.main { display: flex; flex-direction: column; min-width: 0; }
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 14px 32px; border-bottom: 1px solid var(--empire-divider); background: var(--empire-glass); backdrop-filter: blur(8px); }
.topbar-title { font-weight: 500; font-size: 13px; color: var(--empire-mist); letter-spacing: 0.04em; text-transform: uppercase; font-family: var(--font-mono); }
.topbar-title strong { color: var(--empire-white); font-weight: 600; }
.topbar-actions { display: flex; gap: 22px; align-items: center; font-family: var(--font-mono); font-size: 11px; color: var(--empire-mist); }
.topbar-ws { display: inline-flex; align-items: center; gap: 8px; }
.topbar-ws-dot { width: 8px; height: 8px; border-radius: var(--radius-pill); background: var(--status-amber); }
.topbar-ws.connected .topbar-ws-dot { background: var(--signal-teal); box-shadow: var(--glow-signal); animation: empire-pulse var(--pulse-duration) infinite; }
.topbar-who strong { color: var(--empire-white); font-weight: 500; }
.topbar-signout { color: var(--empire-mist); text-decoration: none; cursor: pointer; background: none; border: none; font-family: var(--font-mono); font-size: 11px; padding: 0; }
.topbar-signout:hover { color: var(--status-red); }

/* ── BODY ─────────────────────────────────────────────────────────── */
.body { padding: 28px 32px; flex: 1; }
.section-h { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 20px; }
.section-title { font-weight: 200; font-size: 26px; letter-spacing: -0.03em; }
.section-title em { font-style: italic; color: var(--signal-teal); font-weight: 500; }
.section-sub { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.14em; text-transform: uppercase; }

/* ── STAT CARDS ───────────────────────────────────────────────────── */
.pulse-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.stat-card { background: var(--empire-surface); border: 1px solid var(--empire-border); padding: 20px; position: relative; overflow: hidden; transition: border-color 0.2s var(--ease-snap); }
.stat-card:hover { border-color: var(--empire-border-hi); }
.stat-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, var(--signal-teal-soft), transparent); }
.stat-label { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 14px; }
.stat-value { font-family: var(--font-mono); font-weight: 500; font-size: 32px; letter-spacing: -0.02em; color: var(--empire-white); line-height: 1; }
.stat-value.teal { color: var(--signal-teal); }
.stat-value.cyan { color: var(--strike-cyan); }
.stat-value.dim { color: var(--empire-mist); }
.stat-meta { font-family: var(--font-mono); font-size: 10px; color: var(--empire-fog); margin-top: 10px; letter-spacing: 0.04em; }

/* ── LIVE EVENTS PANEL ────────────────────────────────────────────── */
.live-panel { background: var(--empire-surface); border: 1px solid var(--empire-border); padding: 20px; }
.panel-h { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; padding-bottom: 14px; border-bottom: 1px solid var(--empire-divider); }
.panel-title { font-weight: 500; font-size: 13px; letter-spacing: 0.02em; }
.panel-tag { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.14em; text-transform: uppercase; }
.events { font-family: var(--font-mono); font-size: 11px; max-height: 360px; overflow-y: auto; }
.event { padding: 9px 0; border-bottom: 1px solid var(--empire-divider); display: flex; gap: 14px; animation: empire-fade-up 0.25s var(--ease-out-empire); }
.event-time { color: var(--empire-fog); flex-shrink: 0; min-width: 60px; }
.event-type { color: var(--signal-teal); flex-shrink: 0; min-width: 88px; text-transform: uppercase; letter-spacing: 0.08em; }
.event-body { color: var(--empire-silver); flex: 1; word-break: break-word; }
.events-empty { color: var(--empire-fog); font-style: italic; padding: 28px 0; text-align: center; font-family: var(--font-ui); font-size: 12px; }

/* ── LOADING / ERROR STATES ──────────────────────────────────────────── */
.stub { background: var(--empire-surface); border: 1px dashed var(--empire-border); padding: 64px 32px; text-align: center; }
.stub-title { font-weight: 200; font-size: 22px; letter-spacing: -0.02em; margin-bottom: 10px; }
.stub-title em { font-style: italic; color: var(--strike-cyan); font-weight: 500; }
.stub-body { color: var(--empire-mist); font-size: 13px; max-width: 440px; margin: 0 auto; line-height: 1.7; }

/* ── DENIED ───────────────────────────────────────────────────────── */
.denied { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 40px; text-align: center; }
.denied-icon { font-size: 48px; color: var(--status-red); margin-bottom: 16px; }
.denied-title { font-weight: 200; font-size: 24px; margin-bottom: 8px; }
.denied-body { color: var(--empire-mist); font-size: 13px; max-width: 400px; }
.denied-cta { margin-top: 24px; display: inline-block; padding: 12px 24px; background: var(--signal-teal); color: #000; text-decoration: none; font-weight: 700; letter-spacing: 0.04em; }


/* ── TABLES ───────────────────────────────────────────────────────── */
.tbl { width: 100%; background: var(--empire-surface); border: 1px solid var(--empire-border); border-collapse: collapse; font-size: 12px; }
.tbl thead th { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.14em; text-transform: uppercase; text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--empire-divider); background: var(--empire-elevated); font-weight: 500; }
.tbl tbody td { padding: 12px 14px; border-bottom: 1px solid var(--empire-divider); color: var(--empire-silver); vertical-align: top; }
.tbl tbody tr:hover { background: var(--empire-elevated); }
.tbl tbody tr:last-child td { border-bottom: none; }
.tbl-empty { padding: 40px; text-align: center; color: var(--empire-fog); font-family: var(--font-ui); font-size: 12px; font-style: italic; }
.tbl-num { font-family: var(--font-mono); text-align: right; }
.tbl-mono { font-family: var(--font-mono); font-size: 11px; }
.tbl-action { display: inline-block; padding: 4px 10px; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; border: 1px solid var(--empire-border); background: transparent; color: var(--empire-silver); cursor: pointer; margin-right: 6px; }
.tbl-action:hover { color: var(--empire-white); border-color: var(--signal-teal); }
.tbl-action.go { color: var(--signal-teal); border-color: var(--signal-teal-soft); }
.tbl-action.go:hover { background: var(--signal-teal); color: #000; }
.tbl-action.danger { color: var(--status-red); border-color: var(--status-red); }
.tbl-action.danger:hover { background: var(--status-red); color: #000; }

/* ── BADGES ───────────────────────────────────────────────────────── */
.bdg { display: inline-block; padding: 3px 9px; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; border-radius: var(--radius-pill); border: 1px solid; }
.bdg.active   { color: var(--signal-teal); border-color: var(--signal-teal-soft); }
.bdg.paused   { color: var(--status-amber); border-color: var(--status-amber); }
.bdg.replied  { color: var(--strike-cyan); border-color: var(--strike-cyan); }
.bdg.complete { color: var(--empire-mist); border-color: var(--empire-border); }
.bdg.pending  { color: var(--status-amber); border-color: var(--status-amber); }
.bdg.approved { color: var(--signal-teal); border-color: var(--signal-teal-soft); }
.bdg.rejected { color: var(--status-red); border-color: var(--status-red); }
.bdg.failed   { color: var(--status-red); border-color: var(--status-red); }
.bdg.sent     { color: var(--strike-cyan); border-color: var(--strike-cyan); }

/* ── PANELS ───────────────────────────────────────────────────────── */
.split { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.panel { background: var(--empire-surface); border: 1px solid var(--empire-border); padding: 16px; }
.panel-head { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--empire-divider); }

/* ── FORMS ────────────────────────────────────────────────────────── */
.fld { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.fld-lbl { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.14em; text-transform: uppercase; }
.fld-in { background: var(--empire-elevated); border: 1px solid var(--empire-border); padding: 10px 12px; color: var(--empire-white); font-family: var(--font-ui); font-size: 13px; outline: none; }
.fld-in:focus { border-color: var(--signal-teal); }
.fld-in.mono { font-family: var(--font-mono); }
.btn { display: inline-block; padding: 10px 18px; background: var(--signal-teal); color: #000; font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; border: none; cursor: pointer; font-weight: 700; }
.btn:hover { background: var(--strike-cyan); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn.ghost { background: transparent; color: var(--empire-silver); border: 1px solid var(--empire-border); font-weight: 500; }
.btn.ghost:hover { background: var(--empire-elevated); color: var(--empire-white); }

/* ── CONSOLE CHAT ─────────────────────────────────────────────────── */
.console { background: var(--empire-surface); border: 1px solid var(--empire-border); padding: 18px; }
.console-msgs { max-height: 360px; overflow-y: auto; margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--empire-divider); }
.console-msg { padding: 10px 0; font-family: var(--font-mono); font-size: 12px; }
.console-msg.user { color: var(--empire-white); }
.console-msg.user::before { content: '> '; color: var(--signal-teal); }
.console-msg.parse { color: var(--strike-cyan); padding-left: 14px; }
.console-msg.exec  { color: var(--empire-mist); padding-left: 14px; }
.console-msg.err   { color: var(--status-red); padding-left: 14px; }
.console-row { display: flex; gap: 10px; }
.console-row .fld-in { flex: 1; }

.sec-meta { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 16px; }

/* ── RESPONSIVE ───────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .app { grid-template-columns: 1fr; }
  .nav { display: none; }
  .pulse-grid { grid-template-columns: repeat(2, 1fr); }
  .topbar { padding: 12px 18px; }
  .body { padding: 20px 18px; }
  .topbar-who { display: none; }
}
.agi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}
.agi-tile{background:var(--empire-surface);border:1px solid var(--empire-divider);border-radius:10px;padding:18px 20px;position:relative;overflow:hidden}
.agi-tile-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.18em;text-transform:uppercase;margin-bottom:12px}
.agi-tile-val{font-family:var(--font-display);font-weight:200;font-size:32px;color:var(--empire-white)}
.agi-tile-val em{font-style:normal;color:var(--signal-teal)}
.agi-tile-sub{font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);margin-top:6px}
.agi-decisions{background:var(--empire-surface);border:1px solid var(--empire-divider);border-radius:10px;overflow:hidden}
.agi-decisions-head{display:flex;justify-content:space-between;padding:14px 20px;border-bottom:1px solid var(--empire-divider)}
.agi-decisions-title{font-size:14px;color:var(--empire-white)}
.agi-decisions-count{font-family:var(--font-mono);font-size:10px;color:var(--signal-teal)}
.agi-row{display:grid;grid-template-columns:100px 1fr;gap:16px;padding:12px 20px;border-bottom:1px solid var(--empire-divider)}
.agi-row-weight{font-family:var(--font-mono);font-size:18px;color:var(--strike-cyan)}
.agi-row-reason{font-size:12px;color:var(--empire-mist)}
.agi-approve-btn{margin-top:6px;display:inline-block;font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;padding:4px 10px;border-radius:4px;border:1px solid #39FF14;background:transparent;color:#39FF14;cursor:pointer}
.agi-approve-btn.done{background:rgba(57,255,20,0.15)}
.agi-w-bar{height:3px;border-radius:2px;margin-top:4px;width:85%}
.agi-w-hi .agi-w-bar,.agi-w-hi.agi-w-bar{background:#39FF14}
.agi-w-mid .agi-w-bar,.agi-w-mid.agi-w-bar{background:#FFB800}
.agi-w-lo .agi-w-bar,.agi-w-lo.agi-w-bar{background:#FF4444}
.agi-w-bar{height:3px;border-radius:2px;margin-top:4px;width:85%}
.agi-w-hi .agi-w-bar,.agi-w-hi.agi-w-bar{background:#39FF14}
.agi-w-mid .agi-w-bar,.agi-w-mid.agi-w-bar{background:#FFB800}
.agi-w-lo .agi-w-bar,.agi-w-lo.agi-w-bar{background:#FF4444}
.agi-w-hi{color:#39FF14}
.agi-w-mid{color:#FFB800}
.agi-w-lo{color:#FF4444}
.agi-w-hi{color:#39FF14}
.agi-w-mid{color:#FFB800}
.agi-w-lo{color:#FF4444}
.agi-w-bar{height:3px;border-radius:2px;margin-top:4px;width:85%}
.agi-w-hi .agi-w-bar{background:#39FF14}
.agi-w-mid .agi-w-bar{background:#FFB800}
.agi-w-lo .agi-w-bar{background:#FF4444}
.agi-replay-btn{margin-left:6px;padding:2px 8px;border-radius:3px;font-size:10px;font-family:var(--font-mono);cursor:pointer;border:1px solid #555;background:transparent;color:inherit}.agi-replay-btn.active{border-color:#39FF14;background:rgba(57,255,20,0.1)}
.agi-meta{font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);margin-top:14px}
.gov-meta{font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);display:flex;align-items:center;gap:8px}
.gov-wd-dot{width:8px;height:8px;border-radius:50%;display:inline-block;background:#FFB800}
.gov-wd-dot.gov-ok{background:#39FF14;box-shadow:0 0 8px rgba(57,255,20,0.6)}
.gov-heal-btn{margin-left:10px;padding:5px 14px;border-radius:4px;font-size:10px;font-family:var(--font-mono);letter-spacing:.1em;cursor:pointer;border:1px solid #FF4444;background:rgba(255,68,68,0.08);color:#FF4444;text-transform:uppercase}
.gov-heal-btn:hover{background:rgba(255,68,68,0.18)}
.gov-heal-btn:disabled{opacity:.5;cursor:default}
.gov-healmsg{font-family:var(--font-mono);font-size:11px;color:#39FF14;border:1px solid var(--empire-divider);background:var(--empire-surface);border-radius:6px;padding:10px 14px;margin-bottom:16px}
.gov-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.gov-panel{background:var(--empire-surface);border:1px solid var(--empire-divider);border-radius:10px;overflow:hidden}
.gov-panel-h{display:flex;justify-content:space-between;align-items:baseline;padding:14px 18px;border-bottom:1px solid var(--empire-divider)}
.gov-panel-title{font-size:14px;color:var(--empire-white)}
.gov-panel-tag{font-family:var(--font-mono);font-size:10px;color:var(--signal-teal);letter-spacing:.1em;text-transform:uppercase}
.gov-empty{padding:28px;text-align:center;color:var(--empire-fog);font-size:12px;font-family:var(--font-mono)}
.gov-badge{font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;padding:3px 8px;border-radius:4px;border:1px solid currentColor}
.gov-ok{color:#39FF14}
.gov-warn{color:#FFB800}
.gov-bad{color:#FF4444}
.gov-log{max-height:340px;overflow-y:auto;font-family:var(--font-mono);font-size:11px}
.gov-log-row{display:flex;gap:10px;padding:9px 18px;border-bottom:1px solid var(--empire-divider);align-items:baseline}
.gov-log-time{color:var(--empire-fog);flex-shrink:0;min-width:54px}
.gov-log-lvl{flex-shrink:0;min-width:44px;font-size:9px;letter-spacing:.08em}
.gov-log-svc{color:var(--signal-teal);flex-shrink:0;min-width:96px}
.gov-log-detail{color:var(--empire-mist)}
.gov-res{padding:8px 0}
.gov-res-row{display:grid;grid-template-columns:160px 1fr;gap:16px;align-items:center;padding:10px 18px;border-bottom:1px solid var(--empire-divider)}
.gov-res-name{font-family:var(--font-mono);font-size:12px;color:var(--empire-silver)}
.gov-res-bars{display:flex;flex-direction:column;gap:8px}
.gov-res-bar-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-bottom:3px;letter-spacing:.08em}
.gov-res-track{height:6px;background:var(--empire-divider);border-radius:3px;overflow:hidden}
.gov-res-fill{height:100%;border-radius:3px;transition:width .3s}
.gov-res-fill.gov-ok{background:#39FF14}
.gov-res-fill.gov-warn{background:#FFB800}
.gov-res-fill.gov-bad{background:#FF4444}
"""


_SPA_JS = r"""
import { createElement as h, useState, useEffect, useRef, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import htm from 'htm';

const html = htm.bind(h);
const TOKEN_KEY = 'hub_token';

// ── AUTH ──────────────────────────────────────────────────────────────
function getToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; } }
function clearToken() { try { localStorage.removeItem(TOKEN_KEY); } catch {} }

async function apiFetch(path, opts = {}) {
  const token = getToken();
  const headers = Object.assign({}, opts.headers || {}, token ? { 'Authorization': 'Bearer ' + token } : {});
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  if (res.status === 401) {
    clearToken();
    window.location.href = '/auth/login';
    throw new Error('Unauthorized');
  }
  return res;
}

// ── ROUTING ───────────────────────────────────────────────────────────
const SECTIONS = [
  { id: 'pulse',       label: 'Pulse',       sub: 'Live overview' },
  { id: 'pipeline',    label: 'Pipeline',    sub: 'Email & SMS · state machine' },
  { id: 'dispatch',    label: 'Dispatch',    sub: 'Contractor matching' },
  { id: 'inbound',     label: 'Inbound',     sub: 'Calls · triage · recordings' },
  { id: 'payouts',     label: 'Payouts',     sub: 'Pending · approvals · history' },
  { id: 'contractors', label: 'Contractors', sub: 'Applications & approvals' },
  { id: 'console',     label: 'Console',     sub: 'Sovereign natural-language ops' },
  { id: 'audit',       label: 'Audit',       sub: 'Operator action history' },
  { id: 'operators',   label: 'Operators',   sub: 'Roster · roles · invites' },
  { id: 'neural-core', label: 'Neural Core', sub: 'Live brain · autonomous decisions' },
  { id: 'governor',    label: 'Governor',    sub: 'Autonomous control · self-healing · 60s watchdog' },
];

function currentSection() {
  const hash = (window.location.hash || '#/pulse').replace(/^#\//, '');
  return SECTIONS.find(s => s.id === hash) ? hash : 'pulse';
}

// ── LIVE TRANSPORT (WebSocket primary, SSE fallback) ──────────────────
// Tries WebSocket first. If it fails to open within 4 seconds — or if it
// drops repeatedly — falls back to EventSource at /api/v1/live/stream.
// Browsers handle EventSource auto-reconnect; we don't have to.
function useLiveSocket(onEvent) {
  const [connected, setConnected] = useState(false);
  const [transport, setTransport] = useState(null); // 'ws' | 'sse' | null
  const wsRef = useRef(null);
  const esRef = useRef(null);
  const wsFailedRef = useRef(false);
  const closedRef = useRef(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    function startSSE() {
      if (closedRef.current || esRef.current) return;
      const url = `/api/v1/live/stream?token=${encodeURIComponent(token)}`;
      const es = new EventSource(url);
      esRef.current = es;
      es.addEventListener('open', () => { setConnected(true); setTransport('sse'); });
      es.addEventListener('message', evt => {
        let data; try { data = JSON.parse(evt.data); } catch { return; }
        if (data && data.type) onEvent(data);
      });
      es.addEventListener('error', () => {
        // Browser will auto-reconnect; only mark disconnected during the gap.
        setConnected(false);
      });
    }

    function startWS() {
      if (closedRef.current) return;
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${proto}//${location.host}/ws/live?token=${encodeURIComponent(token)}`;
      let ws;
      try { ws = new WebSocket(url); } catch { wsFailedRef.current = true; startSSE(); return; }
      wsRef.current = ws;
      let pingTimer = null;
      // If WS doesn't open within 4s, give up and switch to SSE.
      const failoverTimer = setTimeout(() => {
        if (ws.readyState !== 1) {
          wsFailedRef.current = true;
          try { ws.close(); } catch {}
          startSSE();
        }
      }, 4000);

      ws.addEventListener('open', () => {
        clearTimeout(failoverTimer);
        setConnected(true);
        setTransport('ws');
        pingTimer = setInterval(() => { if (ws.readyState === 1) ws.send('ping'); }, 25000);
      });
      ws.addEventListener('message', evt => {
        let data; try { data = JSON.parse(evt.data); } catch { return; }
        if (data && data.type) onEvent(data);
      });
      ws.addEventListener('close', () => {
        clearTimeout(failoverTimer);
        if (pingTimer) clearInterval(pingTimer);
        setConnected(false);
        if (!closedRef.current && !wsFailedRef.current) {
          // WS opened then dropped — assume it's flaky, switch to SSE.
          wsFailedRef.current = true;
          startSSE();
        }
      });
      ws.addEventListener('error', () => {});
    }

    startWS();
    return () => {
      closedRef.current = true;
      if (wsRef.current) try { wsRef.current.close(); } catch {}
      if (esRef.current) try { esRef.current.close(); } catch {}
    };
  }, []);

  return { connected, transport };
}

// ── PULSE SECTION ─────────────────────────────────────────────────────
function Pulse({ events, wsConnected }) {
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [pb, em, sm, py, ib] = await Promise.all([
        apiFetch('/api/v1/playbook/summary').then(r => r.json()),
        apiFetch('/api/v1/email/stats').then(r => r.json()),
        apiFetch('/api/v1/sms/stats').then(r => r.json()),
        apiFetch('/api/v1/payouts/pending').then(r => r.json()),
        apiFetch('/api/v1/inbound/stats').then(r => r.json()),
      ]);
      setStats({ pb, em, sm, py, ib });
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 30000);
    return () => clearInterval(t);
  }, [reload]);

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Pulse</div><div class="stub-body">${err}</div></div>`;
  if (!stats) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const strikes = stats.pb?.today?.strikes ?? 0;
  const brain_go = stats.pb?.today?.brain_go ?? 0;
  const seqActive = (stats.em?.sequences_active ?? 0) + (stats.sm?.sequences_active ?? 0);
  const emailsSent = stats.em?.emails_sent ?? 0;
  const smsSent = stats.sm?.sms_sent ?? 0;
  const pendingPayouts = (stats.py?.pending ?? []).length;
  const inboundCalls = stats.ib?.calls_received ?? 0;
  const inboundForwarded = stats.ib?.calls_forwarded ?? 0;

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Live <em>Pulse</em></div>
          <div class="section-sub">Real-time situational awareness</div>
        </div>
        <div class="section-sub">Auto-refresh · 30s</div>
      </div>

      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">Strikes Today</div>
          <div class=${'stat-value ' + (strikes > 0 ? 'teal' : 'dim')}>${strikes}</div>
          <div class="stat-meta">${brain_go} brain · GO</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Active Sequences</div>
          <div class=${'stat-value ' + (seqActive > 0 ? 'cyan' : 'dim')}>${seqActive}</div>
          <div class="stat-meta">${emailsSent} email · ${smsSent} sms sent</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Pending Payouts</div>
          <div class=${'stat-value ' + (pendingPayouts > 0 ? 'teal' : 'dim')}>${pendingPayouts}</div>
          <div class="stat-meta">awaiting owner approval</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Inbound Calls</div>
          <div class=${'stat-value ' + (inboundCalls > 0 ? 'cyan' : 'dim')}>${inboundCalls}</div>
          <div class="stat-meta">${inboundForwarded} forwarded</div>
        </div>
      </div>

      <div class="live-panel">
        <div class="panel-h">
          <div class="panel-title">Live event tail</div>
          <div class="panel-tag">${wsConnected ? 'Streaming' : 'Disconnected'}</div>
        </div>
        ${events.length === 0
          ? html`<div class="events-empty">No events yet — connection ${wsConnected ? 'open, awaiting traffic' : 'pending'}.</div>`
          : html`<div class="events">
              ${events.map(e => html`
                <div class="event" key=${e._id}>
                  <span class="event-time">${e._t}</span>
                  <span class="event-type">${e.type}</span>
                  <span class="event-body">${JSON.stringify(stripMeta(e))}</span>
                </div>
              `)}
            </div>`}
      </div>
    </div>
  `;
}

function stripMeta(e) {
  const { _id, _t, type, ...rest } = e;
  return rest;
}


// ── PIPELINE ──────────────────────────────────────────────────────────
function Pipeline() {
  const [d, setD] = useState(null);
  const [e, setE] = useState(null);
  useEffect(() => {
    Promise.all([
      apiFetch('/api/v1/email/stats').then(r => r.json()),
      apiFetch('/api/v1/sms/stats').then(r => r.json()),
    ]).then(([em, sm]) => setD({ em, sm })).catch(x => setE(x.message));
  }, []);
  if (e) return html`<div class="stub"><div class="stub-body">${e}</div></div>`;
  if (!d) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;
  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Pipeline</div><div class="section-sub">Email & SMS sequence engines</div></div></div>
      <div class="split">
        <div class="panel">
          <div class="panel-head">Email Engine</div>
          <div class="sec-meta">Sequences active: <strong>${d.em.sequences_active ?? 0}</strong> · Sent today: <strong>${d.em.emails_sent ?? 0}</strong> · Replies: <strong>${d.em.replies ?? 0}</strong> · Unsubs: <strong>${d.em.unsubscribes ?? 0}</strong></div>
        </div>
        <div class="panel">
          <div class="panel-head">SMS Engine</div>
          <div class="sec-meta">Sequences active: <strong>${d.sm.sequences_active ?? 0}</strong> · Sent today: <strong>${d.sm.sms_sent ?? 0}</strong> · Replies: <strong>${d.sm.replies ?? 0}</strong> · Opt-outs: <strong>${d.sm.opt_outs ?? 0}</strong></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head">Engine status</div>
        <div class="sec-meta">Email dispatcher polling: <strong>every 5s</strong> · limit 12/min · SMS dispatcher: <strong>every 5s</strong> · limit 6/min</div>
      </div>
    </div>
  `;
}

// ── DISPATCH ──────────────────────────────────────────────────────────
function Dispatch() {
  const [board, setBoard] = useState(null);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    Promise.all([
      apiFetch('/api/v1/matching/leaderboard').then(r => r.json()),
      apiFetch('/api/v1/matching/stats').then(r => r.json()),
    ]).then(([b, s]) => { setBoard(b); setStats(s); }).catch(x => setErr(x.message));
  }, []);
  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!board) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;
  const rows = board.leaderboard || board.contractors || board || [];
  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Dispatch</div><div class="section-sub">Contractor leaderboard & matching</div></div></div>
      ${stats ? html`<div class="sec-meta">Active dispatches: <strong>${stats.active ?? 0}</strong> · Accepted: <strong>${stats.accepted ?? 0}</strong> · Completed: <strong>${stats.completed ?? 0}</strong> · Ghosted: <strong>${stats.ghosted ?? 0}</strong></div>` : ''}
      ${(rows.length === 0)
        ? html`<div class="tbl-empty">No contractors yet — onboard via /api/v1/contractors/apply.</div>`
        : html`<table class="tbl"><thead><tr>
            <th>Contractor</th><th>Metro</th><th class="tbl-num">Trust</th><th class="tbl-num">Jobs</th><th>Last dispatch</th>
          </tr></thead><tbody>
          ${rows.map(c => html`<tr key=${c.id || c.email}>
            <td><strong>${c.name || '—'}</strong><br/><span class="tbl-mono">${c.email || ''}</span></td>
            <td>${c.metro || '—'}</td>
            <td class="tbl-num">${c.trust_score ?? '—'}</td>
            <td class="tbl-num">${c.completed_jobs ?? 0}</td>
            <td class="tbl-mono">${(c.last_dispatched_at || '').slice(0,16).replace('T',' ') || '—'}</td>
          </tr>`)}
        </tbody></table>`}
    </div>
  `;
}

// ── INBOUND ───────────────────────────────────────────────────────────
function Inbound() {
  const [calls, setCalls] = useState(null);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    Promise.all([
      apiFetch('/api/v1/inbound/calls?limit=50').then(r => r.json()),
      apiFetch('/api/v1/inbound/stats').then(r => r.json()),
    ]).then(([c, s]) => { setCalls(c.calls || c || []); setStats(s); }).catch(x => setErr(x.message));
  }, []);
  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!calls) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;
  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Inbound</div><div class="section-sub">Calls · triage · recordings</div></div></div>
      ${stats ? html`<div class="sec-meta">Calls received: <strong>${stats.calls_received ?? 0}</strong> · Forwarded: <strong>${stats.calls_forwarded ?? 0}</strong> · Voicemail: <strong>${stats.voicemails ?? 0}</strong></div>` : ''}
      ${(calls.length === 0)
        ? html`<div class="tbl-empty">No inbound calls yet.</div>`
        : html`<table class="tbl"><thead><tr>
            <th>When</th><th>From</th><th>Disposition</th><th class="tbl-num">Urgency</th><th>Recording</th>
          </tr></thead><tbody>
          ${calls.map(c => html`<tr key=${c.id || c.call_uuid}>
            <td class="tbl-mono">${(c.created_at || '').slice(0,16).replace('T',' ')}</td>
            <td class="tbl-mono">${c.from_number || '—'}</td>
            <td><span class=${'bdg ' + (c.disposition || 'pending')}>${c.disposition || '—'}</span></td>
            <td class="tbl-num">${c.urgency_score ?? '—'}</td>
            <td>${c.recording_url ? html`<a href=${c.recording_url} target="_blank" class="tbl-action">Listen</a>` : html`<span class="tbl-mono">—</span>`}</td>
          </tr>`)}
        </tbody></table>`}
    </div>
  `;
}

// ── PAYOUTS ───────────────────────────────────────────────────────────
function Payouts() {
  const [pending, setPending] = useState(null);
  const [history, setHistory] = useState(null);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);

  const reload = async () => {
    try {
      const [p, h, s] = await Promise.all([
        apiFetch('/api/v1/payouts/pending').then(r => r.json()),
        apiFetch('/api/v1/payouts/history?limit=20').then(r => r.json()),
        apiFetch('/api/v1/payouts/stats').then(r => r.json()),
      ]);
      setPending(p.pending || (Array.isArray(p) ? p : []));
      setHistory(h.history || (Array.isArray(h) ? h : []));
      setStats(s || {});
    } catch (e) { setErr(e.message); }
  };
  useEffect(() => { reload(); }, []);

  const act = async (id, action) => {
    if (!confirm('Confirm ' + action + ' for payout ' + id.slice(0,8) + '?')) return;
    setBusy(id);
    try {
      await apiFetch('/api/v1/payouts/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ payout_id: id }) });
      await reload();
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!pending) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;
  const mode = (stats && stats.mode) || 'DRY-RUN';
  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Payouts</div><div class="section-sub">Pending · history · approvals</div></div></div>
      <div class="sec-meta">Mode: <strong>${mode}</strong> · Pending count: <strong>${pending.length}</strong></div>
      <div class="panel" style=${{marginBottom: '16px'}}>
        <div class="panel-head">Pending approval</div>
        ${pending.length === 0
          ? html`<div class="tbl-empty">No pending payouts.</div>`
          : html`<table class="tbl"><thead><tr>
              <th>Recipient</th><th>Type</th><th class="tbl-num">USDC</th><th>Created</th><th>Actions</th>
            </tr></thead><tbody>
            ${pending.map(p => html`<tr key=${p.id}>
              <td class="tbl-mono">${String(p.recipient_wallet || '').slice(0,16)}…</td>
              <td>${p.recipient_type || '—'}</td>
              <td class="tbl-num"><strong>${p.amount_usdc}</strong></td>
              <td class="tbl-mono">${String(p.created_at || '').slice(0,16).replace('T',' ')}</td>
              <td>
                <button class="tbl-action go" disabled=${busy === p.id} onClick=${() => act(p.id, 'approve')}>Approve</button>
                <button class="tbl-action danger" disabled=${busy === p.id} onClick=${() => act(p.id, 'cancel')}>Cancel</button>
              </td>
            </tr>`)}
          </tbody></table>`}
      </div>
      <div class="panel">
        <div class="panel-head">Recent history</div>
        ${(!history || history.length === 0)
          ? html`<div class="tbl-empty">No payouts yet.</div>`
          : html`<table class="tbl"><thead><tr>
              <th>When</th><th>Recipient</th><th class="tbl-num">USDC</th><th>Status</th>
            </tr></thead><tbody>
            ${history.map(p => html`<tr key=${p.id}>
              <td class="tbl-mono">${String(p.executed_at || p.created_at || '').slice(0,16).replace('T',' ')}</td>
              <td class="tbl-mono">${String(p.recipient_wallet || '').slice(0,16)}…</td>
              <td class="tbl-num">${p.amount_usdc}</td>
              <td>${p.status || '—'}</td>
            </tr>`)}
          </tbody></table>`}
      </div>
    </div>
  `;
}

// ── CONTRACTORS ───────────────────────────────────────────────────────
function Contractors() {
  const [apps, setApps] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);

  const reload = async () => {
    try {
      const r = await apiFetch('/api/v1/contractors/applications').then(x => x.json());
      setApps(r.applications || r || []);
    } catch (e) { setErr(e.message); }
  };
  useEffect(() => { reload(); }, []);

  const act = async (id, action) => {
    if (!confirm(`Confirm ${action} for application ${id.slice(0,8)}?`)) return;
    setBusy(id);
    try {
      await apiFetch(`/api/v1/contractors/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ application_id: id }) });
      await reload();
    } catch (e) { alert(`Failed: ${e.message}`); }
    setBusy(null);
  };

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!apps) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;
  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Contractors</div><div class="section-sub">Applications & approvals</div></div></div>
      ${(apps.length === 0)
        ? html`<div class="tbl-empty">No contractor applications.</div>`
        : html`<table class="tbl"><thead><tr>
            <th>Name</th><th>Metro</th><th>License</th><th>Applied</th><th>Status</th><th>Actions</th>
          </tr></thead><tbody>
          ${apps.map(a => html`<tr key=${a.id}>
            <td><strong>${a.name}</strong><br/><span class="tbl-mono">${a.email}</span></td>
            <td>${a.metro || '—'}</td>
            <td class="tbl-mono">${a.license_no ? `${a.license_no} ${a.license_state || ''}` : '—'}</td>
            <td class="tbl-mono">${(a.created_at || '').slice(0,10)}</td>
            <td><span class=${'bdg ' + (a.status)}>${a.status}</span></td>
            <td>
              ${a.status === 'pending_review' ? html`
                <button class="tbl-action go" disabled=${busy === a.id} onClick=${() => act(a.id, 'approve')}>Approve</button>
                <button class="tbl-action danger" disabled=${busy === a.id} onClick=${() => act(a.id, 'reject')}>Reject</button>
              ` : html`<span class="tbl-mono">—</span>`}
            </td>
          </tr>`)}
        </tbody></table>`}
    </div>
  `;
}

// ── CONSOLE ───────────────────────────────────────────────────────────
function Console() {
  const [actions, setActions] = useState(null);
  const [stats, setStats] = useState(null);
  const [input, setInput] = useState('');
  const [msgs, setMsgs] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiFetch('/api/v1/console/actions').then(r => r.json()).then(r => setActions(r.actions || (Array.isArray(r) ? r : []))).catch(() => setActions([]));
    apiFetch('/api/v1/console/stats').then(r => r.json()).then(r => setStats(r || {})).catch(() => setStats({}));
  }, []);

  const send = async () => {
    if (!input.trim() || busy) return;
    const userText = input;
    setInput('');
    setMsgs(m => [...m, { kind: 'user', t: userText }]);
    setBusy(true);
    try {
      const r = await apiFetch('/api/v1/console/parse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: userText }) });
      const parsed = await r.json();
      setMsgs(m => [...m, { kind: 'parse', t: JSON.stringify(parsed) }]);
      if (parsed && parsed.action && confirm('Execute action: ' + parsed.action + '?')) {
        const ex = await apiFetch('/api/v1/console/execute', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(parsed) });
        const exj = await ex.json();
        setMsgs(m => [...m, { kind: 'exec', t: JSON.stringify(exj) }]);
      }
    } catch (e) {
      setMsgs(m => [...m, { kind: 'err', t: e.message }]);
    }
    setBusy(false);
  };

  const total = (stats && stats.total) || 0;
  const executed = (stats && stats.executed) || 0;
  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Console</div><div class="section-sub">Natural-language sovereign ops</div></div></div>
      <div class="sec-meta">Total commands: <strong>${total}</strong> · Executed: <strong>${executed}</strong></div>
      <div class="console">
        <div class="console-msgs">
          ${msgs.length === 0
            ? html`<div class="console-msg" style=${{opacity: '0.5'}}>Type a command — e.g. "pause email sequences for flavag83" or "show pending payouts"</div>`
            : msgs.map((m, i) => html`<div class=${'console-msg ' + m.kind} key=${i}>${m.t}</div>`)}
        </div>
        <div class="console-row">
          <input class="fld-in mono" value=${input} onChange=${e => setInput(e.target.value)} onKeyDown=${e => { if (e.key === 'Enter') send(); }} placeholder="enter command…" />
          <button class="btn" disabled=${busy || !input.trim()} onClick=${send}>${busy ? 'Working…' : 'Run'}</button>
        </div>
      </div>
      ${actions && actions.length > 0 ? html`
        <div class="panel" style=${{marginTop: '16px'}}>
          <div class="panel-head">Supported actions (${actions.length})</div>
          <div class="sec-meta">${actions.map(a => typeof a === 'string' ? a : (a && a.name) || JSON.stringify(a)).join(' · ')}</div>
        </div>
      ` : ''}
    </div>
  `;
}

// ── AUDIT ─────────────────────────────────────────────────────────────
function Audit() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    apiFetch('/api/v1/auth/audit?limit=200').then(r => r.json())
      .then(d => setRows(d.audit || d.entries || d || []))
      .catch(x => setErr(x.message));
  }, []);
  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!rows) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;
  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Audit</div><div class="section-sub">Operator action log</div></div></div>
      ${(rows.length === 0)
        ? html`<div class="tbl-empty">No audit events yet.</div>`
        : html`<table class="tbl"><thead><tr>
            <th>When</th><th>Operator</th><th>Action</th><th>Resource</th><th>IP</th>
          </tr></thead><tbody>
          ${rows.map(r => html`<tr key=${r.id}>
            <td class="tbl-mono">${(r.created_at || '').slice(0,19).replace('T',' ')}</td>
            <td>${r.operator_name || r.operator_email || '—'}</td>
            <td class="tbl-mono">${r.action}</td>
            <td class="tbl-mono">${r.resource_type ? `${r.resource_type}:${(r.resource_id || '').slice(0,8)}` : (r.target_type || '—')}</td>
            <td class="tbl-mono">${r.ip || '—'}</td>
          </tr>`)}
        </tbody></table>`}
    </div>
  `;
}

// ── OPERATORS ─────────────────────────────────────────────────────────

function Sparkline({points,color}){
  return null;
  const w=120,h=32,pad=2;
  const min=Math.min(...points),max=Math.max(...points),range=max-min||1;
  const xs=points.map((_,i)=>pad+(i/(points.length-1))*(w-pad*2));
  const ys=points.map(v=>h-pad-((v-min)/range)*(h-pad*2));
  const d=xs.map((x,i)=>(i===0?'M':'L')+x.toFixed(1)+','+ys[i].toFixed(1)).join(' ');
  const fill=d+' L'+(w-pad)+','+(h-pad)+' L'+pad+','+(h-pad)+' Z';
  const gid='sg'+color.replace('#','');
  return html`<svg width=${w} height=${h} style="display:block;margin-top:8px"><defs><linearGradient id=${gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color=${color} stop-opacity="0.3"/><stop offset="100%" stop-color=${color} stop-opacity="0"/></linearGradient></defs><path d=${fill} fill=${'url(#'+gid+')'}/><path d=${d} fill="none" stroke=${color} stroke-width="1.5" stroke-linecap="round"/></svg>`;
}

function AgiLoop(){
  const [data,setData]=useState(null);
  const [err,setErr]=useState(null);
  const [tick,setTick]=useState(0);
  const [approved,setApproved]=useState([]);
  const [replayIdx,setReplayIdx]=useState(null);
  useEffect(()=>{
    let alive=true;
    async function poll(){
      try{
        const r=await apiFetch("/api/telemetry?lines=20");
        const j=await r.json();
        if(alive){setData(j);setErr(null);}
      }catch(e){if(alive)setErr(e.message);}
    }
    poll();
    const id=setInterval(()=>{poll();setTick(t=>t+1);},5000);
    return()=>{alive=false;clearInterval(id);};
  },[]);
  const hist=data?.snapshots??[]; const live=replayIdx===null; const snap=live?hist[0]:hist[replayIdx];
  const doApprove=(idx,w)=>{if(approved.includes(idx))return;setApproved(p=>[...p,idx]);apiFetch("/api/v1/storm/tick",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({auto_weight:parseFloat(w),source:"neural-core"})}).catch(e=>console.warn(e));};
  const decisions=(data?.actions??[]).map(a=>({weight:a.new_weight?.toFixed(2),reason:a.reasoning}));
  return html`<div class="section-header"><div><div class="section-title">Neural Core</div><div class="section-sub">Live brain · autonomous decisions · 5s refresh</div></div><div class="agi-meta">TICK ${tick} · LIVE<button class=${live?"agi-replay-btn active":"agi-replay-btn"} onClick=${()=>setReplayIdx(null)}>LIVE</button><button class="agi-replay-btn" onClick=${()=>setReplayIdx(r=>r===null?1:Math.min(r+1,hist.length-1))}>PREV</button><button class="agi-replay-btn" onClick=${()=>setReplayIdx(r=>r===null?null:r<=1?null:r-1)}>NEXT</button></div></div><div class="agi-grid"><div class="agi-tile"><div class="agi-tile-label">LEAD VELOCITY</div><div class="agi-tile-val"><em>${snap?.lead_velocity??"--"}</em></div><div class="agi-tile-sub">leads/hr</div></div><div class="agi-tile"><div class="agi-tile-label">REVENUE PULSE</div><div class="agi-tile-val"><em>${snap?.revenue_pulse!=null?(snap.revenue_pulse*100).toFixed(1)+"%":"--"}</em></div><div class="agi-tile-sub">AI confidence</div></div><div class="agi-tile"><div class="agi-tile-label">PROXY HEALTH</div><div class="agi-tile-val"><em>${snap?.proxy_health!=null?(snap.proxy_health*100).toFixed(1)+"%":"--"}</em></div><div class="agi-tile-sub">network health</div></div><div class="agi-tile"><div class="agi-tile-label">AI CALLS</div><div class="agi-tile-val"><em>${snap?.ai_calls_today??"--"}</em></div><div class="agi-tile-sub">brain activations</div></div></div><div class="agi-decisions"><div class="agi-decisions-head"><div class="agi-decisions-title">Decision Log</div><div class="agi-decisions-count">${decisions.length} entries</div></div>${decisions.map((d,i)=>html`<div class="agi-row"><div class=${"agi-row-weight "+(parseFloat(d.weight)>=1.5?"agi-w-hi":parseFloat(d.weight)>=1.0?"agi-w-mid":"agi-w-lo")}>${d.weight??"·"}<div class="agi-w-bar"></div></div><div class="agi-row-reason">${d.reason??"·"}<button class=${approved.includes(i)?"agi-approve-btn done":"agi-approve-btn"} onClick=${()=>doApprove(i,d.weight)}>${approved.includes(i)?"✓ APPROVED":"AUTO-APPROVE"}</button></div></div>`)}</div>`;
}

// ── GOVERNOR ──────────────────────────────────────────────────────────

function Governor() {
  const [status, setStatus] = useState(null);
  const [log, setLog] = useState(null);
  const [err, setErr] = useState(null);
  const [healing, setHealing] = useState(false);
  const [healMsg, setHealMsg] = useState(null);
  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const [sr, lr] = await Promise.all([
          apiFetch("/api/governor/status"),
          apiFetch("/api/governor/log?lines=20"),
        ]);
        const sj = await sr.json();
        const lj = await lr.json();
        if (alive) { setStatus(sj); setLog(lj); setErr(null); }
      } catch (e) { if (alive) setErr(e.message); }
    }
    poll();
    const id = setInterval(poll, 10000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  const forceHeal = async () => {
    setHealing(true); setHealMsg(null);
    try {
      const r = await apiFetch("/api/governor/heal", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const j = await r.json();
      setHealMsg(j.message || "Heal triggered");
    } catch (e) { setHealMsg("Error: " + e.message); }
    finally { setHealing(false); }
  };
  const svcCls = (s) => s === "online" ? "gov-ok" : (s === "stopped" || s === "errored" || s === "offline") ? "gov-bad" : "gov-warn";
  const fmtUp = (s) => { if (s == null) return "--"; const d=Math.floor(s/86400), h=Math.floor((s%86400)/3600), m=Math.floor((s%3600)/60); return d>0?(d+"d "+h+"h"):h>0?(h+"h "+m+"m"):(m+"m"); };
  const services = status?.services ?? [];
  const wd = status?.watchdog ?? {};
  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  return html`
    <div>
      <div class="section-h">
        <div><div class="section-title">Governor</div><div class="section-sub">Autonomous control · self-healing · 60s watchdog</div></div>
        <div class="gov-meta">
          <span class=${"gov-wd-dot " + (wd.healthy === wd.total ? "gov-ok" : "gov-warn")}></span>
          ${wd.healthy ?? "--"}/${wd.total ?? "--"} HEALTHY · WATCHDOG ${wd.interval_s ?? 60}s
          <button class="gov-heal-btn" disabled=${healing} onClick=${forceHeal}>${healing ? "HEALING…" : "FORCE HEAL"}</button>
        </div>
      </div>
      ${healMsg ? html`<div class="gov-healmsg">${healMsg}</div>` : null}
      <div class="gov-grid">
        <div class="gov-panel">
          <div class="gov-panel-h"><div class="gov-panel-title">PM2 Services</div><div class="gov-panel-tag">${services.length} processes</div></div>
          ${!status ? html`<div class="gov-empty">Loading…</div>` :
            html`<table class="tbl"><thead><tr><th>Service</th><th>Status</th><th>Uptime</th><th>↺</th><th>Memory</th></tr></thead><tbody>
              ${services.map(s => html`<tr key=${s.name}>
                <td class="tbl-mono">${s.name}</td>
                <td><span class=${"gov-badge " + svcCls(s.status)}>${(s.status || "?").toUpperCase()}</span></td>
                <td class="tbl-mono">${fmtUp(s.uptime_s)}</td>
                <td class=${"tbl-mono " + ((s.restarts ?? 0) >= 10 ? "gov-warn" : "")}>${s.restarts ?? 0}</td>
                <td class="tbl-mono">${s.mem_mb != null ? (s.mem_mb.toFixed(1) + " MB") : "--"}</td>
              </tr>`)}
            </tbody></table>`}
        </div>
        <div class="gov-panel">
          <div class="gov-panel-h"><div class="gov-panel-title">Self-Heal Log</div><div class="gov-panel-tag">${(log?.entries ?? []).length} entries</div></div>
          <div class="gov-log">
            ${(log?.entries ?? []).length === 0 ? html`<div class="gov-empty">No heal actions recorded.</div>` :
              log.entries.map((e, i) => html`<div class="gov-log-row" key=${i}>
                <span class="gov-log-time">${(e.ts || "").slice(11, 19)}</span>
                <span class=${"gov-log-lvl " + (e.level === "error" ? "gov-bad" : e.level === "warn" ? "gov-warn" : "gov-ok")}>${(e.level || "info").toUpperCase()}</span>
                <span class="gov-log-svc">${e.service || "—"}</span>
                <span class="gov-log-detail">${(e.action ? (e.action + " · ") : "") + (e.detail || "")}</span>
              </div>`)}
          </div>
        </div>
      </div>
      <div class="gov-panel">
        <div class="gov-panel-h"><div class="gov-panel-title">Resource Allocation</div><div class="gov-panel-tag">CPU · RAM per service</div></div>
        ${!status ? html`<div class="gov-empty">Loading…</div>` :
          html`<div class="gov-res">${services.map(s => {
            const cpu = s.cpu_pct ?? 0, mem = s.mem_mb ?? 0;
            const cpuCls = cpu >= 80 ? "gov-bad" : cpu >= 50 ? "gov-warn" : "gov-ok";
            const memCls = mem >= 600 ? "gov-bad" : mem >= 300 ? "gov-warn" : "gov-ok";
            return html`<div class="gov-res-row" key=${s.name}>
              <div class="gov-res-name">${s.name}</div>
              <div class="gov-res-bars">
                <div class="gov-res-bar"><div class="gov-res-bar-label">CPU ${cpu.toFixed(0)}%</div><div class="gov-res-track"><div class=${"gov-res-fill " + cpuCls} style=${"width:" + Math.min(cpu, 100) + "%"}></div></div></div>
                <div class="gov-res-bar"><div class="gov-res-bar-label">RAM ${mem.toFixed(0)}MB</div><div class="gov-res-track"><div class=${"gov-res-fill " + memCls} style=${"width:" + Math.min(mem / 8, 100) + "%"}></div></div></div>
              </div>
            </div>`;
          })}</div>`}
      </div>
    </div>
  `;
}

function Operators() {
  const [ops, setOps] = useState(null);
  const [err, setErr] = useState(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState('operator');
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    try {
      const r = await apiFetch('/api/v1/auth/operators').then(x => x.json());
      setOps(r.operators || (Array.isArray(r) ? r : []));
    } catch (e) { setErr(e.message); }
  };
  useEffect(() => { reload(); }, []);

  const invite = async () => {
    if (!inviteEmail.trim() || !inviteName.trim()) return;
    setBusy(true);
    try {
      await apiFetch('/api/v1/auth/invite', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: inviteEmail, name: inviteName, role: inviteRole }) });
      setInviteEmail(''); setInviteName(''); setInviteRole('operator');
      await reload();
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(false);
  };

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!ops) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;
  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Operators</div><div class="section-sub">Roster · roles · invites</div></div></div>
      <div class="panel" style=${{marginBottom: '16px'}}>
        <div class="panel-head">Invite operator</div>
        <div style=${{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '10px', alignItems: 'end'}}>
          <div class="fld" style=${{margin: '0'}}><label class="fld-lbl">Email</label><input class="fld-in mono" value=${inviteEmail} onChange=${e => setInviteEmail(e.target.value)} placeholder="name@empire-ai.co.uk" /></div>
          <div class="fld" style=${{margin: '0'}}><label class="fld-lbl">Name</label><input class="fld-in" value=${inviteName} onChange=${e => setInviteName(e.target.value)} placeholder="Full name" /></div>
          <div class="fld" style=${{margin: '0'}}><label class="fld-lbl">Role</label>
            <select class="fld-in mono" value=${inviteRole} onChange=${e => setInviteRole(e.target.value)}>
              <option value="operator">operator</option>
              <option value="viewer">viewer</option>
              <option value="owner">owner</option>
            </select>
          </div>
          <button class="btn" disabled=${busy || !inviteEmail.trim() || !inviteName.trim()} onClick=${invite}>${busy ? 'Sending…' : 'Invite'}</button>
        </div>
      </div>
      <table class="tbl"><thead><tr>
        <th>Name</th><th>Email</th><th>Role</th><th>Active</th><th>Last login</th>
      </tr></thead><tbody>
        ${ops.map(o => html`<tr key=${o.id}>
          <td><strong>${o.name}</strong></td>
          <td class="tbl-mono">${o.email}</td>
          <td>${o.role}</td>
          <td>${o.active ? '✓' : '—'}</td>
          <td class="tbl-mono">${String(o.last_login || '').slice(0,16).replace('T',' ') || 'never'}</td>
        </tr>`)}
      </tbody></table>
    </div>
  `;
}


// ── APP SHELL ────────────────────────────────────────────────────────
function App() {
  const [operator, setOperator] = useState(null);
  const [bootError, setBootError] = useState(null);
  const [section, setSection] = useState(currentSection());
  const [events, setEvents] = useState([]);
  const eventCounter = useRef(0);

  // Boot: validate token, fetch operator
  useEffect(() => {
    if (!getToken()) { window.location.href = '/auth/login'; return; }
    (async () => {
      try {
        const res = await apiFetch('/api/v1/auth/me');
        if (!res.ok) throw new Error('auth check failed');
        const op = await res.json();
        if (op.role !== 'owner') { setBootError('Owner role required'); return; }
        setOperator(op);
      } catch (e) {
        if (e.message !== 'Unauthorized') setBootError(e.message);
      }
    })();
  }, []);

  // Hash routing
  useEffect(() => {
    const onHash = () => setSection(currentSection());
    window.addEventListener('hashchange', onHash);
    if (!window.location.hash) window.location.hash = '#/pulse';
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // Live transport — only when authenticated
  const onEvent = useCallback((data) => {
    const now = new Date();
    const t = now.toTimeString().slice(0, 8);
    eventCounter.current += 1;
    setEvents(prev => [{ ...data, _id: eventCounter.current, _t: t }, ...prev].slice(0, 100));
  }, []);
  const { connected: liveConnected, transport: liveTransport } = useLiveSocket(operator ? onEvent : () => {});

  async function signOut() {
    try { await apiFetch('/api/v1/auth/logout', { method: 'POST' }); } catch {}
    clearToken();
    window.location.href = '/auth/login';
  }

  if (bootError) {
    return html`
      <div class="denied">
        <div class="denied-icon">✗</div>
        <div class="denied-title">Access denied</div>
        <div class="denied-body">${bootError}. The command deck is owner-only.</div>
        <a class="denied-cta" href="/auth/login" onClick=${(e) => { e.preventDefault(); signOut(); }}>Sign in again →</a>
      </div>
    `;
  }

  if (!operator) {
    return html`
      <div class="boot">
        <div class="boot-mark">EMPIRE<span>AI</span></div>
        <div class="boot-tag">Authenticating…</div>
      </div>
    `;
  }

  const active = SECTIONS.find(s => s.id === section) || SECTIONS[0];

  return html`
    <div class="app">
      <aside class="nav">
        <div class="nav-brand">
          <div class="nav-brand-row">
            <span class="nav-brand-e">EMPIRE</span>
            <span class="nav-brand-ai">AI</span>
          </div>
          <div class="nav-tag">Operator Console · V49</div>
        </div>
        ${SECTIONS.map(s => html`
          <a key=${s.id} class=${'nav-item ' + (s.id === section ? 'active' : '')} href=${'#/' + s.id}>
            <span class="nav-item-dot"></span>${s.label}
          </a>
        `)}
      </aside>
      <main class="main">
        <header class="topbar">
          <div class="topbar-title">/ <strong>${active.label}</strong></div>
          <div class="topbar-actions">
            <span class=${'topbar-ws ' + (liveConnected ? 'connected' : '')}>
              <span class="topbar-ws-dot"></span>${liveConnected ? ('LIVE · ' + (liveTransport || '').toUpperCase()) : 'CONNECTING'}
            </span>
            <span class="topbar-who"><strong>${operator.name}</strong> · ${operator.role}</span>
            <button class="topbar-signout" onClick=${signOut}>Sign out</button>
          </div>
        </header>
        <section class="body">
          ${
            active.id === 'pulse'       ? html`<${Pulse} events=${events} wsConnected=${liveConnected} />` :
            active.id === 'pipeline'    ? html`<${Pipeline} />` :
            active.id === 'dispatch'    ? html`<${Dispatch} />` :
            active.id === 'inbound'     ? html`<${Inbound} />` :
            active.id === 'payouts'     ? html`<${Payouts} />` :
            active.id === 'contractors' ? html`<${Contractors} />` :
            active.id === 'console'     ? html`<${Console} />` :
            active.id === 'audit'       ? html`<${Audit} />` :
            active.id === 'neural-core'    ? html`<${AgiLoop} />` :
            active.id === 'governor'    ? html`<${Governor} />` :
            active.id === 'operators'   ? html`<${Operators} />` :
            html`<div class="stub"><div class="stub-body">Unknown section: ${active.label}</div></div>`
          }
        </section>
      </main>
    </div>
  `;
}

createRoot(document.getElementById('root')).render(html`<${App} />`);
"""
