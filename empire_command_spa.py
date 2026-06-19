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

Phase 1 wires Pulse end-to-end; other sections render a placeholder.
"""

from empire_tokens import EMPIRE_FONTS, EMPIRE_TOKENS_CSS, EMPIRE_BASE_CSS
from conversion_funnel import COMMISSION_RATE


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
  <script>const EMPIRE_FEE_RATE = {COMMISSION_RATE};</script>
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
.nav { background: var(--empire-surface); border-right: 1px solid var(--empire-divider); padding: 16px 0 24px; overflow-y: auto; max-height: 100vh; scrollbar-width: thin; scrollbar-color: var(--empire-divider) transparent; }
.nav-brand { padding: 0 20px 16px; border-bottom: 1px solid var(--empire-divider); margin-bottom: 8px; }
.nav-brand-row { display: flex; align-items: baseline; gap: 6px; }
.nav-brand-e { font-family: var(--font-display); font-weight: 700; font-size: 18px; letter-spacing: 0.18em; }
.nav-brand-ai { font-family: var(--font-display); font-weight: 700; font-size: 18px; letter-spacing: 0.18em; color: var(--strike-cyan); }
.nav-tag { font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog); letter-spacing: 0.28em; text-transform: uppercase; margin-top: 6px; }
.nav-item { display: flex; align-items: center; padding: 10px 24px; color: var(--empire-mist); text-decoration: none; font-size: 13px; transition: all 0.15s var(--ease-snap); cursor: pointer; border-left: 2px solid transparent; }
.nav-item:hover { color: var(--empire-white); background: var(--empire-elevated); }
.nav-item.active { color: var(--signal-teal); background: var(--signal-teal-soft); border-left-color: var(--signal-teal); }
.nav-item-dot { display: inline-block; width: 4px; height: 4px; border-radius: var(--radius-pill); background: var(--empire-fog); margin-right: 14px; flex-shrink: 0; }
.nav-item.active .nav-item-dot { background: var(--signal-teal); box-shadow: var(--glow-signal); }
/* ── NAV GROUPS (collapsible) ───────────────────────────────── */
.nav-group { margin-bottom: 2px; }
.nav-group-header { display: flex; align-items: center; gap: 8px; width: 100%; padding: 9px 20px 9px 16px; background: transparent; border: none; cursor: pointer; transition: all 0.15s var(--ease-snap); font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog); letter-spacing: 0.18em; text-transform: uppercase; border-left: 2px solid transparent; }
.nav-group-header:hover { background: var(--empire-elevated); color: var(--empire-mist); }
.nav-group-icon { font-size: 11px; flex-shrink: 0; opacity: 0.7; }
.nav-group-label { flex: 1; text-align: left; }
.nav-group-count { font-size: 8px; color: var(--empire-fog); opacity: 0.5; background: var(--empire-elevated); padding: 1px 5px; border-radius: 3px; }
.nav-group-chevron { font-size: 7px; transition: transform 0.2s var(--ease-snap); opacity: 0.4; }
.nav-group-header.collapsed .nav-group-chevron { transform: rotate(-90deg); }
.nav-group-items { overflow: hidden; max-height: 2000px; transition: max-height 0.25s var(--ease-out-empire), opacity 0.2s var(--ease-snap); opacity: 1; }
.nav-group-items.collapsed { max-height: 0; opacity: 0; }
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
/* ── PULSE TABS ──────────────────────────────────────────────────── */
.pulse-tabs { display: flex; gap: 0; margin-bottom: 24px; border-bottom: 1px solid var(--empire-divider); }
.pulse-tab { padding: 10px 22px; font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--empire-mist); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s var(--ease-snap); background: none; border-top: none; border-left: none; border-right: none; }
.pulse-tab:hover { color: var(--empire-white); }
.pulse-tab.active { color: var(--signal-teal); border-bottom-color: var(--signal-teal); }
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
/* ── STUB SECTIONS ────────────────────────────────────────────────── */
.stub { background: var(--empire-surface); border: 1px dashed var(--empire-border); padding: 64px 32px; text-align: center; }
.stub-title { font-weight: 200; font-size: 22px; letter-spacing: -0.02em; margin-bottom: 10px; }
.stub-title em { font-style: italic; color: var(--strike-cyan); font-weight: 500; }
.stub-body { color: var(--empire-mist); font-size: 13px; max-width: 440px; margin: 0 auto; line-height: 1.7; }
.stub-tag { display: inline-block; margin-top: 18px; font-family: var(--font-mono); font-size: 10px; color: var(--signal-teal); letter-spacing: 0.18em; text-transform: uppercase; border: 1px solid var(--signal-teal-soft); padding: 6px 14px; border-radius: var(--radius-pill); }
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
.bdg.pending_review { color: var(--status-amber); border-color: var(--status-amber); }
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
.agi-w-hi{color:#39FF14}
.agi-w-mid{color:#FFB800}
.agi-w-lo{color:#FF4444}
.agi-w-hi .agi-w-bar{background:#39FF14}
.agi-w-mid .agi-w-bar{background:#FFB800}
.agi-w-lo .agi-w-bar{background:#FF4444}
.agi-replay-btn{margin-left:6px;padding:2px 8px;border-radius:3px;font-size:10px;font-family:var(--font-mono);cursor:pointer;border:1px solid #555;background:transparent;color:inherit}.agi-replay-btn.active{border-color:#39FF14;background:rgba(57,255,20,0.1)}
.agi-meta{font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);margin-top:14px}
/* ── PIPELINE ORBITAL LAYOUT ──────────────────────────────────── */
@keyframes pipe-orbit-rotate{from{stroke-dashoffset:0}to{stroke-dashoffset:-1131}}
@keyframes pipe-boss-glow{0%,100%{box-shadow:0 0 10px rgba(68,229,184,0.12),0 0 20px rgba(68,229,184,0.04)}50%{box-shadow:0 0 18px rgba(68,229,184,0.25),0 0 36px rgba(68,229,184,0.08)}}
@keyframes pipe-node-enter{0%{opacity:0}100%{opacity:1}}
@keyframes pipe-line-draw{0%{stroke-dashoffset:200}100%{stroke-dashoffset:0}}
.pipe-orbital-wrapper{position:relative;width:100%;min-height:480px;display:flex;align-items:center;justify-content:center;margin:10px 0}
.pipe-orbital-svg{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;z-index:1}
.pipe-orbit-ring{fill:none;stroke:rgba(68,229,184,0.06);stroke-width:1px}
.pipe-orbit-ring.outer{stroke:rgba(255,255,255,0.02);stroke-width:1px}
.pipe-orbit-ring.pulse{stroke:rgba(68,229,184,0.1);stroke-width:2px;stroke-dasharray:16 8;animation:pipe-orbit-rotate 25s linear infinite}
.pipe-orbit-line{fill:none;stroke:rgba(68,229,184,0.08);stroke-width:1px;stroke-dasharray:200;stroke-dashoffset:200;animation:pipe-line-draw 1.2s var(--ease-out-empire) forwards}
.pipe-orbit-line.active{stroke:rgba(68,229,184,0.25);stroke-width:2px}
.pipe-orbit-arrow{fill:rgba(68,229,184,0.15);stroke:none;animation:pipe-node-enter .5s var(--ease-out-empire) both}
/* ── Boss card (conversion rate) ── */
.pipe-boss-card{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:3;width:120px;height:120px;border-radius:50%;background:radial-gradient(circle,rgba(68,229,184,0.06) 0%,rgba(68,229,184,0.01) 55%,transparent 100%);border:2px solid rgba(68,229,184,0.2);display:flex;flex-direction:column;align-items:center;justify-content:center;animation:pipe-boss-glow 4s ease-in-out infinite;transition:all .3s var(--ease-snap)}
.pipe-boss-card:hover{border-color:rgba(68,229,184,0.4);transform:translate(-50%,-50%) scale(1.05)}
.pipe-boss-label{font-family:var(--font-mono);font-size:7px;color:var(--signal-teal);letter-spacing:.18em;text-transform:uppercase;margin-bottom:2px}
.pipe-boss-rate{font-family:var(--font-display);font-weight:200;font-size:26px;color:var(--signal-teal);line-height:1}
.pipe-boss-sub{font-family:var(--font-mono);font-size:7px;color:var(--empire-fog);letter-spacing:.08em;margin-top:2px}
/* ── Pipeline stage nodes ── */
.pipe-stage-node{position:absolute;top:50%;left:50%;z-index:2;width:80px;height:56px;background:var(--empire-elevated);border:1px solid var(--empire-divider);border-radius:10px;padding:5px 8px;text-align:center;transition:all .2s var(--ease-snap);animation:pipe-node-enter .35s var(--ease-out-empire) backwards}
.pipe-stage-node:hover{border-color:var(--signal-teal-soft);z-index:4;box-shadow:0 3px 16px rgba(0,0,0,0.25)}
.pipe-stage-node.sent{border-color:rgba(90,200,250,0.2);background:rgba(90,200,250,0.03)}
.pipe-stage-node.replied{border-color:rgba(68,229,184,0.2);background:rgba(68,229,184,0.03)}
.pipe-stage-node.converted{border-color:rgba(68,229,184,0.3);background:rgba(68,229,184,0.04);animation:pipe-boss-glow 3s ease-in-out infinite,pipe-node-enter .35s var(--ease-out-empire) backwards}
.pipe-stage-icon{font-size:11px;display:block;margin-bottom:1px}
.pipe-stage-count{font-family:var(--font-display);font-weight:200;font-size:17px;color:var(--empire-white);line-height:1;display:block}
.pipe-stage-label{font-family:var(--font-mono);font-size:6px;color:var(--empire-fog);letter-spacing:.12em;text-transform:uppercase;margin-top:1px;display:block}
/* ── Responsive ── */
@media (max-width:768px){
  .pipe-orbital-wrapper{min-height:380px}
  .pipe-stage-node{width:64px;height:46px;padding:3px 6px}
  .pipe-boss-card{width:96px;height:96px}
  .pipe-boss-rate{font-size:22px}
}

/* ── PIPELINE BREAKDOWN ──────────────────────────────────────────── */
.pipeline-breakdown{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:24px}
.pipeline-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.pipeline-title{font-weight:500;font-size:13px;letter-spacing:.02em}
.pipeline-total{font-family:var(--font-mono);font-size:11px;color:var(--signal-teal);letter-spacing:.04em}
.pipeline-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.pipeline-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px;transition:border-color .15s var(--ease-snap)}
.pipeline-card:hover{border-color:var(--empire-border-hi)}
.pipeline-card-name{font-weight:500;font-size:14px;color:var(--empire-white);margin-bottom:4px}
.pipeline-card-detail{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.04em;margin-bottom:10px}
.pipeline-card-payout{font-family:var(--font-mono);font-size:18px;color:var(--signal-teal);font-weight:500}
.pipeline-card-per{font-size:10px;color:var(--empire-fog);font-weight:400;margin-left:4px}
.pipeline-card-fees{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.pipeline-fee-tag{font-family:var(--font-mono);font-size:9px;color:var(--signal-teal);letter-spacing:.06em;padding:3px 7px;background:rgba(68,229,184,0.06);border:1px solid rgba(68,229,184,0.2);border-radius:4px}
.pipeline-fee-tag.retainer{color:var(--strike-cyan);border-color:rgba(90,200,250,0.2);background:rgba(90,200,250,0.06)}
    .fee-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
    @media(max-width:900px){.fee-stats{grid-template-columns:repeat(2,1fr)}}
    .fee-stat{background:var(--empire-surface);border:1px solid var(--empire-divider);border-radius:8px;padding:14px 16px}
    .fee-stat-label{font-family:var(--font-mono);font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--empire-mist);margin-bottom:6px}
    .fee-stat-value{font-size:22px;font-weight:300;letter-spacing:-.02em}
    .fee-stat-value.teal{color:var(--signal-teal)}
    .fee-stat-value.dim{color:var(--empire-mist)}
    .fee-status{font-family:var(--font-mono);font-size:10px;letter-spacing:.06em;padding:2px 7px;border-radius:3px}
    .fee-status.pending{color:var(--strike-cyan);background:rgba(90,200,250,0.08);border:1px solid rgba(90,200,250,0.2)}
    .fee-status.paid{color:var(--signal-teal);background:rgba(68,229,184,0.08);border:1px solid rgba(68,229,184,0.2)}
    .settle-form{margin-top:8px}
    .settle-row{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
    .settle-row label{font-family:var(--font-mono);font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--empire-mist)}
    .settle-row input{background:var(--empire-canvas);border:1px solid var(--empire-divider);color:var(--empire-silver);padding:8px 10px;border-radius:4px;font-family:var(--font-mono);font-size:13px}
    .settle-actions{display:flex;gap:8px;margin-top:8px}
    .settle-hint{font-size:11px;color:var(--empire-mist);margin-top:8px;line-height:1.5}
    .settle-hint{font-size:11px;color:var(--empire-mist);margin-top:8px;line-height:1.5}
    .dispatch-status{font-family:var(--font-mono);font-size:10px;letter-spacing:.06em;padding:2px 7px;border-radius:3px}
    .dispatch-status.sent{color:var(--empire-mist);background:rgba(100,116,139,0.1);border:1px solid rgba(100,116,139,0.2)}
    .dispatch-status.accepted{color:var(--strike-cyan);background:rgba(90,200,250,0.08);border:1px solid rgba(90,200,250,0.2)}
    .dispatch-status.completed{color:var(--signal-teal);background:rgba(68,229,184,0.08);border:1px solid rgba(68,229,184,0.2)}
    .dispatch-status.ghosted{color:#ff7b72;background:rgba(255,123,114,0.08);border:1px solid rgba(255,123,114,0.2)}
    .settled-badge{font-family:var(--font-mono);font-size:9px;color:var(--signal-teal);padding:2px 7px;background:rgba(68,229,184,0.06);border:1px solid rgba(68,229,184,0.2);border-radius:3px}
    .live-inbox{margin-top:8px}
    .inbox-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}
    .inbox-stat{font-family:var(--font-mono);font-size:10px;padding:4px 10px;border-radius:4px;letter-spacing:.06em}
    .inbox-yes{color:var(--signal-teal);background:rgba(68,229,184,0.1);border:1px solid rgba(68,229,184,0.3)}
    .inbox-stop{color:#ff7b72;background:rgba(255,123,114,0.1);border:1px solid rgba(255,123,114,0.3)}
    .inbox-no{color:#f59e0b;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3)}
    .inbox-other{color:var(--empire-mist);background:rgba(100,116,139,0.1);border:1px solid rgba(100,116,139,0.3)}
    .inbox-intent{font-family:var(--font-mono);font-size:9px;letter-spacing:.06em;padding:2px 7px;border-radius:3px;text-transform:uppercase}
    .inbox-intent.yes{color:var(--signal-teal);background:rgba(68,229,184,0.08);border:1px solid rgba(68,229,184,0.2)}
    .inbox-intent.stop{color:#ff7b72;background:rgba(255,123,114,0.08);border:1px solid rgba(255,123,114,0.2)}
    .inbox-intent.no{color:#f59e0b;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2)}
    .inbox-intent.notnow{color:var(--empire-mist);background:rgba(100,116,139,0.1);border:1px solid rgba(100,116,139,0.2)}
    .inbox-intent.freeform{color:var(--empire-mist);background:rgba(100,116,139,0.05);border:1px solid rgba(100,116,139,0.1)}
    .inbox-empty{color:var(--empire-mist);font-size:12px;padding:8px 0}
    .tbl-body{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .sec-actions{display:flex;gap:8px}
.pipeline-card-monthly{font-family:var(--font-mono);font-size:11px;color:var(--empire-white);font-weight:500}
/* ── COMPLIANCE PANEL ────────────────────────────────────────────── */
.compliance-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:24px}
.compliance-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.compliance-title{font-weight:500;font-size:13px;letter-spacing:.02em}
.compliance-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase}
.compliance-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.compliance-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px}
.compliance-card-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.18em;text-transform:uppercase;margin-bottom:8px}
.compliance-card-value{font-family:var(--font-mono);font-weight:500;font-size:24px;color:var(--empire-white);line-height:1}
.compliance-card-value.warn{color:var(--status-amber)}
.compliance-card-value.bad{color:var(--status-red)}
.compliance-card-value.ok{color:var(--signal-teal)}
.compliance-card-value.dim{color:var(--empire-mist)}
.compliance-card-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:6px}
.compliance-window-open{display:inline-flex;align-items:center;gap:8px;font-family:var(--font-mono);font-size:10px}
.compliance-window-dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.compliance-window-dot.open{background:var(--signal-teal);box-shadow:0 0 8px rgba(68,229,184,0.6)}
.compliance-window-dot.closed{background:var(--status-red);box-shadow:0 0 8px rgba(255,68,68,0.4)}
.compliance-blocks{max-height:200px;overflow-y:auto}
.compliance-block-row{display:grid;grid-template-columns:100px 80px 1fr;gap:12px;padding:8px 0;border-bottom:1px solid var(--empire-divider);font-family:var(--font-mono);font-size:10px;color:var(--empire-mist)}
.compliance-block-row:last-child{border-bottom:none}
.compliance-block-ts{color:var(--empire-fog)}
.compliance-block-rule{text-transform:uppercase;letter-spacing:.08em}
.compliance-block-rule.hours{color:var(--status-amber)}
.compliance-block-rule.dnc{color:var(--status-red)}
.compliance-block-rule.format{color:var(--empire-mist)}
.compliance-block-phone{color:var(--empire-silver)}
.compliance-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:16px 0;text-align:center}
/* ── LEADS ─────────────────────────────────────────────────────── */
.ld-filter{display:flex;gap:14px;align-items:center;margin-bottom:20px;flex-wrap:wrap}
.ld-filter-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.08em}
.ld-filter-btn{padding:6px 14px;font-family:var(--font-mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;border:1px solid var(--empire-border);background:transparent;color:var(--empire-mist);cursor:pointer;border-radius:4px}
.ld-filter-btn:hover{color:var(--empire-white);border-color:var(--empire-border-hi)}
.ld-filter-btn.active{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.ld-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.ld-stat{background:var(--empire-surface);border:1px solid var(--empire-border);padding:14px 16px}
.ld-stat-val{font-family:var(--font-display);font-weight:200;font-size:28px;color:var(--empire-white);line-height:1}
.ld-stat-val.teal{color:var(--signal-teal)}
.ld-stat-val.dim{color:var(--empire-mist)}
.ld-stat-lbl{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:4px}
.ld-lead{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:14px 18px;margin-bottom:10px;transition:border-color .15s var(--ease-snap)}
.ld-lead:hover{border-color:var(--empire-border-hi)}
.ld-lead-row{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.ld-lead-name{font-weight:500;font-size:14px;color:var(--empire-white)}
.ld-lead-contact{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);margin-top:2px}
.ld-lead-meta{display:flex;gap:14px;flex-wrap:wrap;font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.08em;margin-bottom:10px}
.ld-bdg{display:inline-block;padding:3px 8px;font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;border-radius:4px;border:1px solid}
.ld-bdg.new{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.ld-bdg.pending{color:var(--status-amber);border-color:var(--status-amber)}
.ld-bdg.contacted{color:var(--strike-cyan);border-color:rgba(90,200,250,0.2)}
.ld-bdg.qualified{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.ld-bdg.closed{color:var(--empire-mist);border-color:var(--empire-border)}
.ld-bdg.rejected{color:var(--status-red);border-color:var(--status-red)}
.ld-bdg.source{color:var(--empire-fog);border-color:var(--empire-divider)}
.ld-actions{display:flex;gap:8px;margin-top:8px;padding-top:10px;border-top:1px solid var(--empire-divider)}
.ld-action-btn{padding:5px 12px;font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;border-radius:4px;cursor:pointer;font-weight:600}
.ld-action-btn.go{color:#000;background:var(--signal-teal);border:1px solid var(--signal-teal)}
.ld-action-btn.go:hover{background:var(--strike-cyan)}
.ld-action-btn.ghost{color:var(--empire-mist);background:transparent;border:1px solid var(--empire-border)}
.ld-action-btn.ghost:hover{color:var(--empire-white);border-color:var(--empire-border-hi)}
.ld-action-btn.danger{color:var(--status-red);border:1px solid var(--status-red);background:transparent}
.ld-action-btn.danger:hover{background:rgba(255,68,68,0.1)}
.ld-action-btn:disabled{opacity:.5;cursor:default}
.ld-notes-history{margin-bottom:6px;padding:6px 0;border-bottom:1px solid var(--empire-divider)}
.ld-note-entry{padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.03);font-family:var(--font-mono);font-size:10px}
.ld-note-entry:last-child{border-bottom:none}
.ld-note-meta{color:var(--empire-fog);font-size:9px;display:flex;gap:6px;align-items:center;margin-bottom:3px}
.ld-note-op{color:var(--strike-cyan);font-weight:500}
.ld-note-text{color:var(--empire-silver);line-height:1.5}
.ld-note-del{background:none;border:none;color:var(--empire-fog);cursor:pointer;font-family:var(--font-mono);font-size:9px;padding:2px 5px;margin-left:auto;border-radius:3px;line-height:1;transition:color .15s var(--ease-snap),background .15s var(--ease-snap)}
.ld-note-del:hover{color:var(--status-red);background:rgba(255,68,68,0.1)}
.ld-note-del:disabled{opacity:.4;cursor:default}
.ld-notes{display:flex;gap:8px;align-items:center;margin-bottom:10px;padding:8px 0 4px;border-top:1px solid var(--empire-divider);margin-top:4px}
.ld-notes-in{flex:1;background:var(--empire-elevated);border:1px solid var(--empire-border);padding:6px 10px;color:var(--empire-mist);font-family:var(--font-mono);font-size:10px;outline:none;transition:border-color .15s var(--ease-snap),color .15s var(--ease-snap)}
.ld-notes-in:focus{border-color:var(--strike-cyan);color:var(--empire-white)}
.ld-notes-in::placeholder{color:var(--empire-fog);font-style:italic}
.ld-note-save{padding:6px 12px;font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;border-radius:4px;cursor:pointer;font-weight:600;color:#000;background:var(--signal-teal);border:1px solid var(--signal-teal);flex-shrink:0}
.ld-note-save:hover{background:var(--strike-cyan)}
.ld-note-save:disabled{opacity:.5;cursor:default}
.ld-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:32px 0;text-align:center}

/* ── SMS PERFORMANCE DASHBOARD ─────────────────────────────────── */
.sms-niche-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:24px}
.sms-niche-card{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:16px 18px;position:relative;overflow:hidden;transition:border-color .2s var(--ease-snap)}
.sms-niche-card:hover{border-color:var(--empire-border-hi)}
.sms-niche-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.sms-niche-val{font-family:var(--font-display);font-weight:200;font-size:28px;color:var(--empire-white);line-height:1}
.sms-niche-val.teal{color:var(--signal-teal)}
.sms-niche-val.cyan{color:var(--strike-cyan)}
.sms-niche-val.dim{color:var(--empire-mist)}
.sms-niche-val.warn{color:var(--status-amber)}
.sms-niche-lbl{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:6px}
.sms-niche-table-wrap{background:var(--empire-surface);border:1px solid var(--empire-border);overflow:hidden}
.sms-niche-bar{height:6px;border-radius:3px;transition:width .6s var(--ease-out-empire);min-width:2px}
.sms-niche-bar.active{background:var(--signal-teal)}
.sms-niche-bar.replied{background:var(--strike-cyan)}
.sms-niche-bar.opted_out{background:var(--status-amber)}
.sms-niche-bar.completed{background:rgba(68,229,184,0.3)}

/* ── ACTIVITY LOG ────────────────────────────────────────────────── */
.act-feed{max-height:70vh;overflow-y:auto;background:var(--empire-surface);border:1px solid var(--empire-border);padding:4px 0}
.act-day{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;padding:14px 18px 8px;border-bottom:1px solid var(--empire-divider)}
.act-entry{padding:10px 18px;border-bottom:1px solid var(--empire-divider);display:grid;grid-template-columns:auto 1fr 40px;gap:14px;align-items:center;animation:empire-fade-up .2s var(--ease-out-empire)}
.act-entry:last-child{border-bottom:none}
.act-entry:hover{background:var(--empire-elevated)}
.act-entry-ts{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);white-space:nowrap}
.act-entry-body{font-family:var(--font-mono);font-size:11px;color:var(--empire-silver);line-height:1.5}
.act-entry-operator{font-family:var(--font-mono);font-size:9px;color:var(--strike-cyan);text-align:right}
.act-entry-lead{font-size:10px;color:var(--signal-teal);font-weight:500;cursor:pointer}
.act-entry-lead:hover{text-decoration:underline}
.act-entry-text{color:var(--empire-white)}
.act-empty{padding:48px 18px;text-align:center;font-family:var(--font-ui);font-size:12px;color:var(--empire-fog);font-style:italic}
.act-clear{background:none;border:none;color:var(--empire-fog);cursor:pointer;font-family:var(--font-mono);font-size:12px;padding:2px 8px;border-radius:4px;line-height:1;transition:color .15s var(--ease-snap),background .15s var(--ease-snap)}
.act-clear:hover{color:var(--empire-white);background:var(--empire-elevated)}
.act-meta{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em;margin-bottom:16px}
/* ── SNIPER FLEET ───────────────────────────────────────────────── */
.sf-summary{display:flex;gap:18px;align-items:center;margin-bottom:18px;flex-wrap:wrap}
.sf-summary-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.08em}
.sf-summary-tag strong{color:var(--empire-white);font-weight:500}
.sf-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}
.sf-card{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:18px 20px;position:relative;overflow:hidden;transition:border-color .15s var(--ease-snap)}
.sf-card:hover{border-color:var(--empire-border-hi)}
.sf-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.sf-card-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px}
.sf-card-info{display:flex;flex-direction:column;gap:4px}
.sf-card-name{font-weight:500;font-size:16px;color:var(--empire-white)}
.sf-card-type{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.12em;text-transform:uppercase}
.sf-bdg{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:4px 10px;border-radius:var(--radius-pill);border:1px solid}
.sf-bdg.ACTIVE{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.sf-bdg.IDLE{color:var(--status-amber);border-color:var(--status-amber)}
.sf-bdg.OFFLINE{color:var(--empire-mist);border-color:var(--empire-border)}
.sf-bdg-dot{width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 6px currentColor}
.sf-leads{font-family:var(--font-display);font-weight:200;font-size:40px;color:var(--signal-teal);line-height:1;margin-bottom:14px}
.sf-leads-lbl{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.18em;text-transform:uppercase;margin-top:4px}
.sf-card-meta{font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding-top:12px;border-top:1px solid var(--empire-divider)}
.sf-toggle{padding:6px 16px;font-family:var(--font-mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;border-radius:6px;cursor:pointer;font-weight:700;transition:all .15s var(--ease-snap)}
.sf-toggle.on{background:var(--signal-teal);color:#000;border:1px solid var(--signal-teal)}
.sf-toggle.off{background:transparent;color:var(--empire-mist);border:1px solid var(--empire-border)}
.sf-toggle.off:hover{color:var(--empire-white);border-color:var(--empire-border-hi)}
.sf-toggle:disabled{opacity:.5;cursor:default}
/* ── HOLO MAP ────────────────────────────────────────────────────── */
@keyframes holo-sweep{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
@keyframes holo-ping{0%{transform:scale(1);opacity:1}100%{transform:scale(2.5);opacity:0}}
@keyframes holo-fade-in{0%{opacity:0;transform:translateY(8px)}100%{opacity:1;transform:translateY(0)}}
.holo-radar-wrap{background:var(--empire-surface);border:1px solid var(--empire-border);padding:24px;margin-bottom:20px;text-align:center}
.holo-radar{position:relative;width:360px;height:360px;margin:0 auto;border-radius:50%;background:radial-gradient(circle,rgba(0,245,255,0.03) 0%,rgba(0,245,255,0.01) 60%,transparent 100%);border:1px solid rgba(0,245,255,0.15);overflow:hidden}
.holo-radar-ring{position:absolute;border-radius:50%;border:1px solid rgba(0,245,255,0.07);pointer-events:none}
.holo-radar-ring.r1{top:12.5%;left:12.5%;width:75%;height:75%}
.holo-radar-ring.r2{top:25%;left:25%;width:50%;height:50%}
.holo-radar-ring.r3{top:37.5%;left:37.5%;width:25%;height:25%}
.holo-radar-cross{position:absolute;top:50%;left:50%;pointer-events:none}
.holo-radar-cross::before,.holo-radar-cross::after{content:'';position:absolute;background:rgba(0,245,255,0.06)}
.holo-radar-cross::before{width:1px;height:100%;left:0;top:-50%}
.holo-radar-cross::after{width:100%;height:1px;top:0;left:-50%}
.holo-radar-sweep{position:absolute;top:-2px;left:-2px;width:calc(100% + 4px);height:calc(100% + 4px);border-radius:50%;background:conic-gradient(from 0deg,transparent 60%,rgba(0,245,255,0.04) 80%,rgba(0,245,255,0.08) 85%,rgba(0,245,255,0.12) 88%,rgba(0,245,255,0.02) 92%,transparent 100%);animation:holo-sweep 4s linear infinite;pointer-events:none;mask:radial-gradient(circle at center,transparent 30%,#000 31%,#000 100%);-webkit-mask:radial-gradient(circle at center,transparent 30%,#000 31%,#000 100%)}
.holo-radar-center{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:2;text-align:center;pointer-events:none}
.holo-radar-count{font-family:var(--font-display);font-weight:200;font-size:42px;color:var(--signal-teal);line-height:1}
.holo-radar-lbl{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.18em;text-transform:uppercase;margin-top:4px}
.holo-blip{position:absolute;border-radius:50%;z-index:1;pointer-events:none;animation:holo-fade-in .5s var(--ease-out-empire)}
.holo-blip-dot{width:8px;height:8px;border-radius:50%;position:relative;left:-4px;top:-4px}
.holo-blip-dot.storm{background:var(--strike-cyan);box-shadow:0 0 10px rgba(90,200,250,0.6)}
.holo-blip-dot.target{background:var(--signal-teal);box-shadow:0 0 8px rgba(68,229,184,0.5)}
.holo-blip-ping{position:absolute;width:12px;height:12px;border-radius:50%;left:-2px;top:-2px;animation:holo-ping 2s ease-out infinite}
.holo-blip-ping.storm{background:var(--strike-cyan)}
.holo-blip-ping.target{background:var(--signal-teal)}
.holo-badges{display:flex;gap:12px;justify-content:center;margin-top:12px;flex-wrap:wrap}
.holo-badge{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:4px 10px;border-radius:var(--radius-pill);border:1px solid}
.holo-badge.storm{color:var(--strike-cyan);border-color:rgba(90,200,250,0.2)}
.holo-badge.target{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.holo-split{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:20px}
.holo-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px}
.holo-panel-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--empire-divider)}
.holo-panel-title{font-weight:500;font-size:13px;letter-spacing:.02em}
.holo-panel-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em}
.holo-storm-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:12px 14px;margin-bottom:10px;animation:holo-fade-in .4s var(--ease-out-empire)}
.holo-storm-card:last-child{margin-bottom:0}
.holo-storm-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.holo-storm-name{font-size:12px;color:var(--empire-white);font-weight:500}
.holo-storm-sev{font-family:var(--font-mono);font-size:9px;padding:2px 7px;border-radius:4px;text-transform:uppercase;letter-spacing:.1em}
.holo-storm-sev.Extreme{color:#FF4444;background:rgba(255,68,68,0.1)}
.holo-storm-sev.Severe{color:#FFB800;background:rgba(255,184,0,0.1)}
.holo-storm-sev.Moderate{color:#FFB800;background:rgba(255,184,0,0.06)}
.holo-storm-sev.Minor{color:var(--empire-mist);background:rgba(255,255,255,0.04)}
.holo-storm-area{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog)}
.holo-storm-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:4px}
.holo-target-scroll{max-height:400px;overflow-y:auto}
.holo-target-row{display:grid;grid-template-columns:1fr 80px;gap:10px;padding:9px 0;border-bottom:1px solid var(--empire-divider);font-family:var(--font-mono);font-size:10px;animation:holo-fade-in .3s var(--ease-out-empire)}
.holo-target-row:last-child{border-bottom:none}
.holo-target-name{color:var(--empire-silver)}
.holo-target-status{text-align:right;text-transform:uppercase;letter-spacing:.08em;font-size:9px}
.holo-target-status.new{color:var(--signal-teal)}
.holo-target-status.contacted{color:var(--status-amber)}
.holo-target-status.qualified{color:var(--strike-cyan)}
.holo-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:20px 0;text-align:center}
/* ── HEALTH MONITOR ──────────────────────────────────────────────── */
.hm-split{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:20px}
.hm-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px}
.hm-panel-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--empire-divider)}
.hm-panel-title{font-weight:500;font-size:13px;letter-spacing:.02em}
.hm-panel-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em}
.hm-agent-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.hm-agent-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:12px 14px;transition:border-color .15s var(--ease-snap)}
.hm-agent-card:hover{border-color:var(--empire-border-hi)}
.hm-agent-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.hm-agent-name{font-size:12px;color:var(--empire-white);font-weight:500}
.hm-bdg{display:inline-flex;align-items:center;gap:5px;font-family:var(--font-mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;padding:3px 8px;border-radius:var(--radius-pill);border:1px solid}
.hm-bdg.ACTIVE{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.hm-bdg.ERROR{color:var(--status-red);border-color:var(--status-red)}
.hm-bdg.IDLE{color:var(--status-amber);border-color:var(--status-amber)}
.hm-bdg.OFFLINE{color:var(--empire-mist);border-color:var(--empire-border)}
.hm-bdg-dot{width:5px;height:5px;border-radius:50%;background:currentColor;box-shadow:0 0 5px currentColor}
.hm-agent-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog)}
.hm-health-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.hm-health-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px;text-align:center}
.hm-health-val{font-family:var(--font-display);font-weight:200;font-size:28px;color:var(--empire-white);line-height:1}
.hm-health-val.ok{color:var(--signal-teal)}
.hm-health-val.warn{color:var(--status-amber)}
.hm-health-val.bad{color:var(--status-red)}
.hm-health-lbl{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:6px}
.hm-overseer{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px;margin-top:20px}
.hm-overseer-body{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);max-height:260px;overflow-y:auto;white-space:pre-wrap;word-break:break-word}
.hm-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:20px 0;text-align:center}
/* ── GOVERNOR ────────────────────────────────────────────────────── */
.gov-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}
.gov-card{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:16px 18px;position:relative;overflow:hidden;transition:border-color .15s var(--ease-snap)}
.gov-card:hover{border-color:var(--empire-border-hi)}
.gov-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.gov-card-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.gov-card-name{font-weight:500;font-size:14px;color:var(--empire-white)}
.gov-bdg{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:4px 10px;border-radius:var(--radius-pill);border:1px solid}
.gov-bdg.online{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.gov-bdg.errored{color:var(--status-red);border-color:var(--status-red)}
.gov-bdg.stopped{color:var(--status-amber);border-color:var(--status-amber)}
.gov-bdg.unknown{color:var(--empire-mist);border-color:var(--empire-border)}
.gov-bdg-dot{width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 6px currentColor}
.gov-card-stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.gov-stat{font-family:var(--font-mono)}
.gov-stat-val{font-size:16px;color:var(--empire-white);font-weight:500}
.gov-stat-lbl{font-size:9px;color:var(--empire-fog);letter-spacing:.12em;text-transform:uppercase;margin-top:2px}
.gov-watchdog{display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.gov-watch-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.08em}
.gov-watch-tag strong{color:var(--empire-white);font-weight:500}
.gov-heal-btn{padding:8px 18px;font-family:var(--font-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;border:1px solid var(--status-red);background:transparent;color:var(--status-red);cursor:pointer;border-radius:6px;font-weight:700}
.gov-heal-btn:hover{background:rgba(255,68,68,0.1)}
.gov-heal-btn:disabled{opacity:.5;cursor:default}
.gov-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px;margin-top:20px}
.gov-panel-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--empire-divider)}
.gov-panel-title{font-weight:500;font-size:13px;letter-spacing:.02em}
.gov-panel-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em}
.gov-log{max-height:300px;overflow-y:auto;font-family:var(--font-mono);font-size:11px}
.gov-log-row{display:grid;grid-template-columns:100px 56px 100px 1fr;gap:12px;padding:9px 0;border-bottom:1px solid var(--empire-divider);align-items:baseline}
.gov-log-row:last-child{border-bottom:none}
.gov-log-ts{color:var(--empire-fog);min-width:60px}
.gov-log-lvl{font-size:9px;letter-spacing:.1em;text-transform:uppercase}
.gov-log-lvl.info{color:var(--signal-teal)}
.gov-log-lvl.warn{color:var(--status-amber)}
.gov-log-lvl.error{color:var(--status-red)}
.gov-log-svc{color:var(--strike-cyan)}
.gov-log-detail{color:var(--empire-silver);word-break:break-word}
.gov-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:16px 0;text-align:center}
.gov-result{font-family:var(--font-mono);font-size:11px;color:var(--signal-teal);margin-top:12px;padding:10px 14px;background:var(--empire-elevated);border:1px solid var(--empire-divider)}
/* ── CHARTS ─────────────────────────────────────────────────────── */
.chart-empty{padding:16px 0;text-align:center;font-family:var(--font-ui);font-size:10px;color:var(--empire-fog);font-style:italic}
.chart-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px;margin-bottom:16px}
.chart-panel-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--empire-divider)}
.chart-panel-title{font-weight:500;font-size:12px;letter-spacing:.02em;color:var(--empire-white)}
.chart-panel-tag{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em}
/* ── USDC Revenue Panel ──────────────────────────────────────────── */
.rv-usdc-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:20px;margin-top:20px}
.rv-usdc-panel .tbl thead th{background:var(--empire-elevated)}
.rv-usdc-panel .stat-value{font-size:22px;line-height:1.2}
.rv-referral-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:20px;margin-top:20px}
.rv-referral-panel .tbl thead th{background:var(--empire-elevated)}

.chart-bar:hover{opacity:1 !important;filter:brightness(1.2)}
.chart-donut{display:flex;align-items:center;gap:16px}
.chart-donut-svg{flex-shrink:0}
.chart-legend{display:flex;flex-direction:column;gap:4px}
.chart-legend-item{display:flex;align-items:center;gap:6px;font-family:var(--font-mono);font-size:9px;color:var(--empire-mist)}
.chart-legend-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.chart-legend-val{color:var(--empire-white);margin-left:auto;font-weight:500}
/* ── KANBAN BOARD ────────────────────────────────────────────────── */
.kb-board{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-bottom:20px}
.kb-col{background:var(--empire-surface);border:1px solid var(--empire-border);padding:0;min-height:240px;display:flex;flex-direction:column}
.kb-col-h{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--empire-divider)}
.kb-col-title{font-weight:500;font-size:12px;color:var(--empire-white);letter-spacing:.02em}
.kb-col-count{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.12em}
.kb-col-body{flex:1;overflow-y:auto;max-height:60vh;padding:10px 12px}
.kb-col-body.drag-over{background:var(--empire-elevated)}
.kb-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:12px 14px;margin-bottom:8px;transition:border-color .15s var(--ease-snap),transform .1s var(--ease-snap);cursor:pointer}
.kb-card:hover{border-color:var(--empire-border-hi);transform:translateY(-1px)}
.kb-card:last-child{margin-bottom:0}
.kb-card-id{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.06em;margin-bottom:6px}
.kb-card-type{font-family:var(--font-mono);font-size:10px;color:var(--empire-silver);font-weight:500;margin-bottom:4px}
.kb-card-agent{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);margin-bottom:6px;letter-spacing:.04em}
.kb-card-meta{display:flex;align-items:center;justify-content:space-between;padding-top:8px;border-top:1px solid var(--empire-divider)}
.kb-card-pri{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.06em}
.kb-card-pri strong{color:var(--strike-cyan)}
.kb-card-ts{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog)}
.kb-col-h.To-Do{border-bottom-color:var(--signal-teal-soft)}
.kb-col-h.To-Do .kb-col-title{color:var(--signal-teal)}
.kb-col-h.In-Progress{border-bottom-color:rgba(255,184,0,0.3)}
.kb-col-h.In-Progress .kb-col-title{color:var(--status-amber)}
.kb-col-h.Done{border-bottom-color:rgba(90,200,250,0.2)}
.kb-col-h.Done .kb-col-title{color:var(--strike-cyan)}
.kb-col-h.Failed{border-bottom-color:rgba(255,68,68,0.3)}
.kb-col-h.Failed .kb-col-title{color:var(--status-red)}
.kb-col-h.Blocked{border-bottom-color:rgba(128,128,128,0.3)}
.kb-col-h.Blocked .kb-col-title{color:var(--empire-mist)}
.kb-col-h.Retried{border-bottom-color:rgba(57,255,20,0.2)}
.kb-col-h.Retried .kb-col-title{color:#39FF14}
.kb-col-h.Promoted{border-bottom-color:rgba(200,162,200,0.3)}
.kb-col-h.Promoted .kb-col-title{color:#c8a2c8}
.kb-summary{display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.kb-summary-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.08em}
.kb-summary-tag strong{color:var(--empire-white)}
.kb-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:14px 0;text-align:center}
/* ── REVENUE ─────────────────────────────────────────────────────── */
.rv-alerts{display:flex;flex-direction:column;gap:8px;margin-bottom:20px}
.rv-alert{display:flex;align-items:center;gap:12px;padding:10px 16px;font-family:var(--font-mono);font-size:10px;border-radius:6px;border:1px solid}
.rv-alert.critical{background:rgba(255,68,68,0.06);border-color:rgba(255,68,68,0.25);color:var(--status-red)}
.rv-alert.warning{background:rgba(255,184,0,0.06);border-color:rgba(255,184,0,0.2);color:var(--status-amber)}
.rv-alert.info{background:rgba(90,200,250,0.04);border-color:rgba(90,200,250,0.15);color:var(--strike-cyan)}
.rv-alert-lvl{text-transform:uppercase;letter-spacing:.12em;font-weight:700;flex-shrink:0}
.rv-alert-msg{color:var(--empire-silver);flex:1}
.rv-alert-niche{color:var(--empire-fog);font-size:9px;flex-shrink:0}
.rv-split{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:20px}
.rv-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px}
.rv-bar-row{display:grid;grid-template-columns:120px 1fr 70px 50px;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--empire-divider);font-family:var(--font-mono)}
.rv-bar-row:last-child{border-bottom:none}
.rv-bar-label{display:flex;flex-direction:column;gap:2px}
.rv-bar-lane{font-size:10px;color:var(--empire-white);font-weight:500}
.rv-bar-niche{font-size:8px;color:var(--empire-fog);letter-spacing:.04em}
.rv-bar-track{height:10px;background:var(--empire-elevated);border-radius:4px;overflow:hidden}
.rv-bar-fill{height:100%;border-radius:4px;transition:width .6s var(--ease-out-empire);min-width:2px}
.rv-bar-val{font-size:11px;color:var(--signal-teal);font-weight:500;text-align:right}
.rv-bar-meta{font-size:8px;color:var(--empire-fog);text-align:right;letter-spacing:.04em}
.rv-niche-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:12px 14px;margin-bottom:10px;transition:border-color .15s var(--ease-snap)}
.rv-niche-card:last-child{margin-bottom:0}
.rv-niche-card:hover{border-color:var(--empire-border-hi)}
.rv-niche-name{font-weight:500;font-size:13px;color:var(--empire-white);margin-bottom:8px}
.rv-niche-stats{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:6px}
.rv-niche-stat{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.04em}
.rv-niche-stat strong{color:var(--signal-teal);font-weight:600}
.rv-niche-lanes{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.08em;text-transform:uppercase}
/* ── REVENUE NARRATIVE ──────────────────────────────────────────── */
.rv-narrative-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-top:20px}
.rv-narrative-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.rv-narrative-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.rv-narrative-badge{font-family:var(--font-mono);font-size:9px;color:var(--strike-cyan);letter-spacing:.1em;text-transform:uppercase;padding:4px 10px;border:1px solid rgba(90,200,250,0.2);border-radius:var(--radius-pill)}
.rv-narrative-summary{font-size:13px;color:var(--empire-silver);line-height:1.7;margin-bottom:18px;padding:14px 16px;background:var(--empire-elevated);border-left:3px solid var(--signal-teal)}
.rv-narrative-section{margin-bottom:16px}
.rv-narrative-section:last-child{margin-bottom:0}
.rv-narrative-section-h{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;margin-bottom:8px}
.rv-narrative-item{font-size:12px;color:var(--empire-silver);padding:6px 0 6px 12px;border-left:2px solid var(--empire-divider);line-height:1.5}
.rv-narrative-item.advice{color:var(--signal-teal);border-left-color:var(--signal-teal-soft);font-weight:500}
.rv-narrative-item.risk{color:var(--status-amber);border-left-color:rgba(255,184,0,0.2)}
.rv-narrative-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:18px;padding-top:12px;border-top:1px solid var(--empire-divider);letter-spacing:.04em}
/* ── ACCURACY CHART ─────────────────────────────────────────────── */
.rv-accuracy-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-top:20px}
.rv-accuracy-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.rv-accuracy-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.rv-accuracy-summary{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.04em}
.rv-accuracy-chart{display:flex;flex-direction:column;gap:6px;max-height:50vh;overflow-y:auto}
.rv-acc-row{display:grid;grid-template-columns:56px 1fr 52px;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--empire-divider)}
.rv-acc-row:last-child{border-bottom:none}
.rv-acc-date{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.04em}
.rv-acc-bars{display:flex;flex-direction:column;gap:4px}
.rv-acc-bar-wrap{position:relative;height:14px;background:var(--empire-elevated);border-radius:3px;overflow:hidden;display:flex;align-items:center}
.rv-acc-bar{height:100%;border-radius:3px;transition:width .6s var(--ease-out-empire);min-width:2px;opacity:.85}
.rv-acc-bar.forecast{background:var(--strike-cyan)}
.rv-acc-bar.actual{background:var(--signal-teal)}
.rv-acc-bar-label{position:absolute;left:8px;font-family:var(--font-mono);font-size:8px;color:var(--empire-white);letter-spacing:.04em;white-space:nowrap}
.rv-acc-pct{font-family:var(--font-mono);font-size:11px;font-weight:500;text-align:right}
.rv-accuracy-legend{display:flex;gap:18px;align-items:center;margin-top:14px;padding-top:12px;border-top:1px solid var(--empire-divider);font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);flex-wrap:wrap}
.rv-acc-legend-item{display:flex;align-items:center;gap:6px}
.rv-acc-legend-swatch{width:10px;height:10px;border-radius:2px;display:inline-block}
.rv-acc-legend-swatch.forecast{background:var(--strike-cyan)}
.rv-acc-legend-swatch.actual{background:var(--signal-teal)}
/* ── PAIN POINTS ─────────────────────────────────────────────── */
.pp-niches-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
.pp-niche-tab { display: flex; align-items: center; gap: 10px; padding: 10px 18px; background: var(--empire-surface); border: 1px solid var(--empire-border); cursor: pointer; transition: all 0.15s var(--ease-snap); border-radius: 6px; font-family: var(--font-mono); }
.pp-niche-tab:hover { border-color: var(--empire-border-hi); background: var(--empire-elevated); }
.pp-niche-tab.active { border-color: var(--signal-teal-soft); background: rgba(68,229,184,0.04); }
.pp-niche-name { font-size: 12px; color: var(--empire-white); font-weight: 500; }
.pp-niche-count { font-size: 9px; color: var(--empire-mist); letter-spacing: 0.08em; }
.pp-niche-cr { font-size: 11px; color: var(--signal-teal); font-weight: 500; }
.pp-card { background: var(--empire-elevated); border: 1px solid var(--empire-divider); padding: 16px 18px; transition: border-color 0.15s var(--ease-snap); }
.pp-card:hover { border-color: var(--empire-border-hi); }
.pp-card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.pp-card-label { font-weight: 500; font-size: 14px; color: var(--empire-white); }
.pp-card-weight { font-family: var(--font-mono); font-size: 12px; font-weight: 600; }
.pp-card-hook { font-size: 11px; color: var(--strike-cyan); line-height: 1.5; margin-bottom: 6px; }
.pp-card-resolution { font-size: 11px; color: var(--empire-silver); line-height: 1.5; margin-bottom: 6px; }
.pp-card-proof { font-family: var(--font-mono); font-size: 9px; color: var(--empire-mist); letter-spacing: 0.04em; margin-bottom: 12px; padding: 6px 10px; background: var(--empire-surface); border-radius: 4px; }
.pp-card-stats { display: flex; gap: 16px; margin-bottom: 8px; }
.pp-card-stat { font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog); letter-spacing: 0.04em; }
.pp-w-bar-wrap { height: 4px; background: var(--empire-surface); border-radius: 2px; overflow: hidden; }
.pp-w-bar { height: 100%; border-radius: 2px; transition: width 0.6s var(--ease-out-empire); min-width: 2px; }
.pp-export-bar { display: flex; gap: 10px; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--empire-divider); align-items: center; }
/* ── EXPORT BUTTONS ────────────────────────────────────────────────────────────── */
.rv-accuracy-actions{display:flex;gap:8px;align-items:center}
.rv-export-btn{font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:5px 12px;border-radius:4px;cursor:pointer;font-weight:600;transition:all .15s var(--ease-snap);background:transparent}
.rv-export-btn.csv{color:var(--strike-cyan);border:1px solid rgba(90,200,250,0.2)}
.rv-export-btn.csv:hover{background:rgba(90,200,250,0.08)}
.rv-export-btn.pdf{color:var(--status-amber);border:1px solid rgba(255,184,0,0.2)}
.rv-export-btn.pdf:hover{background:rgba(255,184,0,0.06)}
/* ── SI STRATEGY EVOLUTION ────────────────────────────────────── */
.si-niche-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:20px}
.si-niche-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.si-niche-name{font-weight:500;font-size:16px;color:var(--empire-white);letter-spacing:.02em}
.si-niche-meta{display:flex;gap:16px;align-items:center;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist)}
.si-niche-meta strong{color:var(--empire-white);font-weight:500}
.si-niche-score{font-family:var(--font-mono);font-size:11px;color:var(--signal-teal);font-weight:500}
.si-strategy-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.si-strat-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:16px 18px;transition:border-color .15s var(--ease-snap);position:relative}
.si-strat-card:hover{border-color:var(--empire-border-hi)}
.si-strat-card.best{border-color:rgba(68,229,184,0.25);background:rgba(68,229,184,0.03)}
.si-strat-card.best::before{content:'★ BEST';position:absolute;top:-1px;right:16px;font-family:var(--font-mono);font-size:8px;letter-spacing:.12em;color:var(--signal-teal);padding:2px 8px;border:1px solid var(--signal-teal-soft);border-top:none;border-radius:0 0 4px 4px;background:var(--empire-surface)}
.si-strat-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;gap:8px}
.si-strat-name{font-weight:500;font-size:14px;color:var(--empire-white);word-break:break-word}
.si-gen-bdg{display:inline-block;font-family:var(--font-mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;padding:2px 6px;border-radius:3px;background:rgba(90,200,250,0.12);color:var(--strike-cyan);border:1px solid rgba(90,200,250,0.2);margin-right:4px}
.si-parent-bdg{display:inline-block;font-family:var(--font-mono);font-size:8px;letter-spacing:.08em;padding:2px 6px;border-radius:3px;color:var(--empire-fog);border:1px solid var(--empire-divider)}
.si-strat-stats{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-bottom:14px}
.si-stat{display:flex;flex-direction:column;align-items:center;gap:2px}
.si-stat-val{font-family:var(--font-mono);font-size:16px;color:var(--empire-white);font-weight:500}
.si-stat-val.teal{color:var(--signal-teal)}
.si-stat-val.cyan{color:var(--strike-cyan)}
.si-stat-val.dim{color:var(--empire-mist)}
.si-stat-lbl{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.1em;text-transform:uppercase}
.si-genome{padding-top:12px;border-top:1px solid var(--empire-divider)}
.si-genome-label{font-family:var(--font-mono);font-size:8px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;margin-bottom:10px}
.si-trait{margin-bottom:8px}
.si-trait:last-child{margin-bottom:0}
.si-trait-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}
.si-trait-name{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist)}
.si-trait-pct{font-family:var(--font-mono);font-size:9px;font-weight:500}
.si-trait-track{height:5px;background:var(--empire-surface);border-radius:3px;overflow:hidden}
.si-trait-fill{height:100%;border-radius:3px;transition:width .6s var(--ease-out-empire);min-width:2px}
.si-evo-footer{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:16px;padding-top:12px;border-top:1px solid var(--empire-divider);display:flex;justify-content:space-between}
/* ── SI EVOLUTION HISTORY ─────────────────────────────────────── */
/* ── SI ADAPTIVE ENGINE ──────────────────────────────────────── */
.sia-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.sia-tile{background:var(--empire-surface);border:1px solid var(--empire-divider);border-radius:10px;padding:18px 20px;position:relative;overflow:hidden}
.sia-tile::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--strike-cyan-soft),transparent)}
.sia-tile-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.18em;text-transform:uppercase;margin-bottom:12px}
.sia-tile-val{font-family:var(--font-display);font-weight:200;font-size:32px;color:var(--signal-teal);line-height:1}
.sia-tile-val.dim{color:var(--empire-mist)}
.sia-tile-sub{font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);margin-top:6px}
.sia-subsystem-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:20px}
.sia-subsystem-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.sia-subsystem-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.sia-subsystem-count{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em}
.sia-subsystem-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.sia-sub-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px;display:flex;align-items:center;gap:12px;transition:border-color .15s var(--ease-snap);position:relative}
.sia-sub-card:hover{border-color:var(--empire-border-hi)}
.sia-sub-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;background:var(--signal-teal);box-shadow:0 0 8px rgba(68,229,184,0.5);animation:empire-pulse var(--pulse-duration) infinite}
.sia-sub-body{flex:1;min-width:0}
.sia-sub-name{font-size:13px;color:var(--empire-white);font-weight:500;font-family:var(--font-mono);letter-spacing:.04em;word-break:break-word}
.sia-sub-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:3px;letter-spacing:.04em}
.sia-adoption-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:20px}
.sia-adoption-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.sia-adoption-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.sia-adoption-count{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em}
.sia-adoption-feed{max-height:500px;overflow-y:auto}
.sia-adoption-batch{padding:14px 0;border-bottom:1px solid var(--empire-divider);animation:empire-fade-up .25s var(--ease-out-empire)}
.sia-adoption-batch:last-child{border-bottom:none}
.sia-adoption-head-row{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;gap:10px;flex-wrap:wrap}
.sia-adoption-ts{font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);letter-spacing:.04em}
.sia-adoption-bdg{display:inline-block;font-family:var(--font-mono);font-size:8px;letter-spacing:.12em;text-transform:uppercase;padding:3px 9px;border-radius:var(--radius-pill);border:1px solid var(--signal-teal-soft);color:var(--signal-teal);background:rgba(68,229,184,0.05)}
.sia-adoption-changes{display:flex;flex-direction:column;gap:6px;padding-left:12px;border-left:2px solid var(--empire-divider)}
.sia-adoption-change{font-family:var(--font-mono);font-size:10px;color:var(--empire-silver);padding:4px 0;line-height:1.5;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.sia-change-key{color:var(--strike-cyan);font-weight:500;letter-spacing:.04em}
.sia-change-sub{color:var(--empire-fog);font-size:9px;letter-spacing:.08em;text-transform:uppercase;padding:1px 6px;border:1px solid var(--empire-divider);border-radius:3px}
.sia-change-val{color:var(--empire-white);font-weight:500}
.sia-adoption-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:24px 0;text-align:center}
@media(max-width:768px){.sia-grid{grid-template-columns:repeat(2,1fr)}.sia-subsystem-grid{grid-template-columns:1fr}}
.si-evo-history{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px;margin-top:20px}
.si-evo-history-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--empire-divider)}
.si-evo-history-title{font-weight:500;font-size:13px;color:var(--empire-white);letter-spacing:.02em}
.si-evo-history-count{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em}
.si-evo-events{max-height:400px;overflow-y:auto}
.si-evo-event{display:grid;grid-template-columns:140px 72px 120px 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--empire-divider);align-items:baseline;font-family:var(--font-mono);font-size:9px}
.si-evo-event:last-child{border-bottom:none}
.si-evo-event-ts{color:var(--empire-fog)}
.si-evo-event-type{font-size:8px;letter-spacing:.12em;text-transform:uppercase;padding:2px 6px;border-radius:3px;font-weight:600;text-align:center}
.si-evo-event-type.evolve{color:var(--strike-cyan);border:1px solid rgba(90,200,250,0.2);background:rgba(90,200,250,0.06)}
.si-evo-event-type.deactivate{color:var(--status-red);border:1px solid rgba(255,68,68,0.2);background:rgba(255,68,68,0.04)}
.si-evo-event-niche{color:var(--empire-mist)}
.si-evo-event-detail{color:var(--empire-silver)}
/* ── PANEL_COURT 5-PANEL CONSENSUS ───────────────────────────────── */
.pc-summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.pc-summary-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;text-align:center}
.pc-summary-val{font-family:var(--font-display);font-weight:200;font-size:32px;color:var(--empire-white);line-height:1}
.pc-summary-val.teal{color:var(--signal-teal)}
.pc-summary-val.amber{color:var(--status-amber)}
.pc-summary-val.red{color:var(--status-red)}
.pc-summary-val.dim{color:var(--empire-mist)}
.pc-summary-lbl{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:6px}
.pc-decision-list{display:flex;flex-direction:column;gap:8px}
.pc-decision-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:14px 18px;transition:border-color .15s var(--ease-snap);cursor:pointer}
.pc-decision-card:hover{border-color:var(--empire-border-hi)}
.pc-decision-card.expanded{border-color:var(--signal-teal-soft)}
.pc-decision-row{display:grid;grid-template-columns:1fr 140px 56px 80px;gap:14px;align-items:center}
.pc-decision-lead{display:flex;flex-direction:column;gap:2px;min-width:0}
.pc-decision-lead-name{font-size:12px;color:var(--empire-white);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pc-decision-lead-id{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.06em}
.pc-decision-panels-mini{display:flex;gap:4px}
.pc-mini-vote{font-family:var(--font-mono);font-size:7px;letter-spacing:.1em;padding:2px 5px;border-radius:3px;text-transform:uppercase;font-weight:600;border:1px solid}
.pc-mini-vote.approve{color:var(--signal-teal);border-color:rgba(68,229,184,0.2);background:rgba(68,229,184,0.04)}
.pc-mini-vote.reject{color:var(--status-red);border-color:rgba(255,68,68,0.2);background:rgba(255,68,68,0.04)}
.pc-mini-vote.push{color:var(--strike-cyan);border-color:rgba(90,200,250,0.2);background:rgba(90,200,250,0.04)}
.pc-mini-vote.hold{color:var(--status-amber);border-color:rgba(255,184,0,0.2);background:rgba(255,184,0,0.04)}
.pc-mini-vote.skip{color:var(--empire-fog);border-color:var(--empire-divider)}
.pc-mini-vote.pri{color:var(--strike-cyan);border-color:rgba(90,200,250,0.2);background:rgba(90,200,250,0.04)}
.pc-mini-vote.dep{color:var(--status-amber);border-color:rgba(255,184,0,0.2);background:rgba(255,184,0,0.04)}
.pc-mini-vote.std{color:var(--empire-fog);border-color:var(--empire-divider)}
.pc-mini-vote.auth{color:var(--signal-teal);border-color:rgba(68,229,184,0.2);background:rgba(68,229,184,0.04)}
.pc-mini-vote.inauth{color:var(--status-red);border-color:rgba(255,68,68,0.2);background:rgba(255,68,68,0.04)}
.pc-decision-score{display:flex;justify-content:center}
.pc-score-circle{width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);font-size:13px;font-weight:600;border:2px solid}
.pc-score-ok{color:var(--signal-teal);border-color:rgba(68,229,184,0.3);background:rgba(68,229,184,0.06)}
.pc-score-warn{color:var(--status-amber);border-color:rgba(255,184,0,0.3);background:rgba(255,184,0,0.06)}
.pc-score-bad{color:var(--status-red);border-color:rgba(255,68,68,0.3);background:rgba(255,68,68,0.06)}
.pc-decision-verdict{text-align:center}
.pc-verdict-badge{display:inline-block;font-family:var(--font-mono);font-size:8px;letter-spacing:.12em;text-transform:uppercase;padding:3px 10px;border-radius:4px;font-weight:600}
.pc-verdict-badge.dispatch{color:var(--signal-teal);border:1px solid var(--signal-teal-soft)}
.pc-verdict-badge.reject{color:var(--status-red);border:1px solid rgba(255,68,68,0.2)}
.pc-decision-detail{margin-top:16px;padding-top:14px;border-top:1px solid var(--empire-divider)}
.pc-detail-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.pc-detail-panel{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:12px 14px;border-radius:4px}
.pc-detail-panel.vetoed{border-color:rgba(255,68,68,0.2);background:rgba(255,68,68,0.03)}
.pc-detail-panel-head{display:flex;align-items:center;gap:6px;margin-bottom:8px}
.pc-detail-panel-icon{font-size:12px;flex-shrink:0}
.pc-detail-panel-name{font-size:10px;color:var(--empire-white);font-weight:500}
.pc-detail-decision{font-family:var(--font-mono);font-size:7px;letter-spacing:.1em;text-transform:uppercase;padding:1px 5px;border-radius:3px;font-weight:600;margin-left:auto}
.pc-detail-decision.approve{color:var(--signal-teal);border:1px solid rgba(68,229,184,0.2)}
.pc-detail-decision.reject{color:var(--status-red);border:1px solid rgba(255,68,68,0.2)}
.pc-detail-decision.push{color:var(--strike-cyan);border:1px solid rgba(90,200,250,0.2)}
.pc-detail-decision.hold{color:var(--status-amber);border:1px solid rgba(255,184,0,0.2)}
.pc-detail-decision.pri{color:var(--strike-cyan);border:1px solid rgba(90,200,250,0.2)}
.pc-detail-decision.std{color:var(--empire-fog);border:1px solid var(--empire-divider)}
.pc-detail-decision.auth{color:var(--signal-teal);border:1px solid rgba(68,229,184,0.2)}
.pc-detail-decision.inauth{color:var(--status-red);border:1px solid rgba(255,68,68,0.2)}
.pc-detail-stat{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.04em}
.pc-judge-block{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px;border-radius:4px;border-left:3px solid var(--strike-cyan)}
.pc-judge-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.pc-judge-weighted{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.08em;margin-left:auto}
.pc-judge-reasoning{font-size:11px;color:var(--empire-silver);line-height:1.6}
/* ── PANEL COURT ORBITAL LAYOUT ──────────────────────────────── */
@keyframes pc-orbit-pulse{0%,100%{box-shadow:0 0 8px rgba(68,229,184,0.2)}50%{box-shadow:0 0 18px rgba(68,229,184,0.5)}}
@keyframes pc-orbit-rotate{from{stroke-dashoffset:0}to{stroke-dashoffset:-1131}}
@keyframes pc-boss-glow{0%,100%{box-shadow:0 0 12px rgba(90,200,250,0.15),0 0 24px rgba(90,200,250,0.05)}50%{box-shadow:0 0 20px rgba(90,200,250,0.3),0 0 40px rgba(90,200,250,0.1)}}
@keyframes pc-agent-enter{0%{opacity:0}100%{opacity:1}}
@keyframes pc-line-draw{0%{stroke-dashoffset:200}100%{stroke-dashoffset:0}}
.pc-pool-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:20px}
.pc-pool-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.pc-pool-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.pc-pool-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em}
/* ── Orbital wrapper ── */
.pc-orbital-wrapper{position:relative;width:100%;min-height:540px;display:flex;align-items:center;justify-content:center;margin:10px 0}
.pc-orbital-svg{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;z-index:1}
.pc-orbit-ring{fill:none;stroke:rgba(255,255,255,0.04);stroke-width:1px}
.pc-orbit-ring.outer{stroke:rgba(255,255,255,0.03);stroke-width:1px}
.pc-orbit-ring.inner{stroke:rgba(68,229,184,0.06);stroke-width:1px;stroke-dasharray:4 8}
.pc-orbit-ring.pulse{stroke:rgba(68,229,184,0.08);stroke-width:2px;stroke-dasharray:20 10;animation:pc-orbit-rotate 20s linear infinite}
.pc-orbit-line{fill:none;stroke:rgba(90,200,250,0.1);stroke-width:1px;stroke-dasharray:200;stroke-dashoffset:200;animation:pc-line-draw 1.5s var(--ease-out-empire) forwards}
.pc-orbit-line.winner{stroke:rgba(68,229,184,0.25);stroke-width:1.5px}
/* ── Critique arrows ── */
.pc-critique-arrow{fill:none;stroke:rgba(255,184,0,0.25);stroke-width:1.2px;stroke-dasharray:5 4;stroke-linecap:round;pointer-events:none}
.pc-critique-arrow.severe{stroke:rgba(255,68,68,0.35);stroke-width:1.8px}
.pc-critique-arrow.mild{stroke:rgba(68,229,184,0.18);stroke-width:1px;stroke-dasharray:2 6}
.pc-critique-arrowhead{fill:rgba(255,184,0,0.3)}
.pc-critique-arrowhead.severe{fill:rgba(255,68,68,0.4)}
.pc-critique-arrowhead.mild{fill:rgba(68,229,184,0.2)}
/* ── Critique detail ── */
.pc-critique-detail{margin-top:14px;padding-top:14px;border-top:1px solid var(--empire-divider)}
.pc-critique-title{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;margin-bottom:10px}
.pc-critique-card{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:10px 12px;margin-bottom:8px;border-radius:4px;border-left:3px solid rgba(255,184,0,0.3)}
.pc-critique-card.severe{border-left-color:rgba(255,68,68,0.4)}
.pc-critique-card.mild{border-left-color:rgba(68,229,184,0.3)}
.pc-critique-head{display:flex;gap:10px;align-items:center;margin-bottom:6px;font-family:var(--font-mono);font-size:8px}
.pc-critique-flow{color:var(--status-amber)}
.pc-critique-sev{color:var(--empire-mist);letter-spacing:.08em}
.pc-critique-sev.high{color:var(--status-red)}
.pc-critique-sev.low{color:var(--signal-teal)}
.pc-critique-adj{color:var(--strike-cyan);margin-left:auto}
.pc-critique-text{font-size:10px;color:var(--empire-silver);line-height:1.5}
/* ── Boss agent (center) ── */
.pc-boss-card{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:3;width:130px;height:130px;border-radius:50%;background:radial-gradient(circle,rgba(90,200,250,0.08) 0%,rgba(90,200,250,0.02) 60%,transparent 100%);border:2px solid rgba(90,200,250,0.2);display:flex;flex-direction:column;align-items:center;justify-content:center;animation:pc-boss-glow 3s ease-in-out infinite;transition:all .3s var(--ease-snap)}
.pc-boss-card:hover{border-color:rgba(90,200,250,0.4);transform:translate(-50%,-50%) scale(1.05)}
.pc-boss-label{font-family:var(--font-mono);font-size:7px;color:var(--strike-cyan);letter-spacing:.18em;text-transform:uppercase;margin-bottom:4px}
.pc-boss-title{font-weight:500;font-size:13px;color:var(--empire-white);letter-spacing:.02em;margin-bottom:2px}
.pc-boss-sub{font-family:var(--font-mono);font-size:7px;color:var(--empire-fog);letter-spacing:.1em}
.pc-boss-roles{display:flex;gap:3px;margin-top:6px;flex-wrap:wrap;justify-content:center}
.pc-boss-role{font-family:var(--font-mono);font-size:6px;letter-spacing:.08em;text-transform:uppercase;padding:1px 4px;border-radius:2px;border:1px solid;color:var(--empire-mist);border-color:var(--empire-divider)}
/* ── Orbiting agent cards ── */
.pc-orbital-agent{position:absolute;top:50%;left:50%;z-index:2;width:82px;height:52px;background:var(--empire-elevated);border:1px solid var(--empire-divider);border-radius:8px;padding:6px 8px;text-align:center;transition:all .2s var(--ease-snap);animation:pc-agent-enter .4s var(--ease-out-empire) backwards}
.pc-orbital-agent:hover{border-color:var(--empire-border-hi);z-index:4;box-shadow:0 4px 20px rgba(0,0,0,0.3)}
.pc-orbital-agent.winner{border-color:rgba(68,229,184,0.35);background:rgba(68,229,184,0.04);animation:pc-orbit-pulse 2s ease-in-out infinite,pc-agent-enter .4s var(--ease-out-empire) backwards}
.pc-orbital-agent-id{font-family:var(--font-mono);font-size:9px;color:var(--empire-white);font-weight:500;display:block;margin-bottom:1px}
.pc-orbital-agent-temp{font-family:var(--font-mono);font-size:7px;letter-spacing:.08em;padding:0 3px;border-radius:2px;display:inline-block}
.pc-orbital-agent-temp.cold{color:var(--strike-cyan);border:1px solid rgba(90,200,250,0.2);background:rgba(90,200,250,0.04)}
.pc-orbital-agent-temp.warm{color:var(--status-amber);border:1px solid rgba(255,184,0,0.2);background:rgba(255,184,0,0.04)}
.pc-orbital-agent-temp.hot{color:var(--status-red);border:1px solid rgba(255,68,68,0.2);background:rgba(255,68,68,0.04)}
.pc-orbital-agent-wr{font-family:var(--font-display);font-weight:200;font-size:15px;color:var(--signal-teal);line-height:1;display:block}
.pc-orbital-agent-wl{font-family:var(--font-mono);font-size:6px;color:var(--empire-fog);letter-spacing:.06em}
.pc-orbital-agent-won{font-family:var(--font-mono);font-size:6px;letter-spacing:.08em;text-transform:uppercase;color:var(--signal-teal);position:absolute;top:-8px;left:50%;transform:translateX(-50%);background:var(--empire-surface);padding:1px 5px;border-radius:3px;border:1px solid rgba(68,229,184,0.2);white-space:nowrap}
/* ── Convergence Chart ───────────────────────────────────── */
.pc-converge-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-top:20px}
.pc-converge-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.pc-converge-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.pc-converge-count{font-family:var(--font-mono);font-size:10px;color:var(--signal-teal)}
.pc-converge-chart{position:relative;width:100%;height:220px;padding:0 8px}
.pc-converge-svg{width:100%;height:100%}
.pc-converge-grid{stroke:var(--empire-divider);stroke-width:0.5px;stroke-dasharray:3 4}
.pc-converge-line{fill:none;stroke-width:2px;stroke-linecap:round;transition:opacity .2s var(--ease-snap)}
.pc-converge-line:hover{stroke-width:3px;opacity:1 !important}
.pc-converge-label{font-family:var(--font-mono);font-size:7px;fill:var(--empire-fog)}
.pc-converge-y-label{font-family:var(--font-mono);font-size:6px;fill:var(--empire-fog);letter-spacing:.08em}
.pc-converge-legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;padding-top:12px;border-top:1px solid var(--empire-divider);justify-content:center}
.pc-converge-legend-item{display:flex;align-items:center;gap:4px;font-family:var(--font-mono);font-size:7px;color:var(--empire-mist);cursor:pointer;transition:opacity .2s var(--ease-snap)}
.pc-converge-legend-item.dimmed{opacity:.35}
.pc-converge-legend-swatch{width:10px;height:2px;border-radius:1px;flex-shrink:0}
/* ── Hover tooltip ── */
.pc-hover-tooltip{background:var(--empire-elevated);border:1px solid var(--strike-cyan);border-radius:8px;padding:12px 14px;max-width:320px;box-shadow:0 8px 32px rgba(0,0,0,0.5);pointer-events:none;animation:pc-agent-enter .15s var(--ease-out-empire)}
.pc-tooltip-framing{font-size:10px;color:var(--empire-silver);line-height:1.5;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid var(--empire-divider)}
.pc-tooltip-stats{display:flex;gap:12px;flex-wrap:wrap;font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);margin-bottom:4px}
.pc-tooltip-stats span{white-space:nowrap}
/* ── Selected agent ── */
.pc-orbital-agent.selected{border-color:var(--strike-cyan)!important;box-shadow:0 0 16px rgba(90,200,250,0.3);z-index:5!important}
/* ── Agent detail panel ── */
.pc-agent-detail{background:var(--empire-surface);border:1px solid var(--strike-cyan);border-radius:10px;padding:0;margin:16px 0;overflow:hidden;animation:pc-agent-enter .3s var(--ease-out-empire)}
.pc-agent-detail-head{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;background:rgba(90,200,250,0.06);border-bottom:1px solid var(--empire-divider)}
.pc-agent-detail-title{font-weight:500;font-size:14px;color:var(--strike-cyan);letter-spacing:.02em}
.pc-agent-detail-close{background:none;border:1px solid var(--empire-divider);color:var(--empire-mist);cursor:pointer;font-size:14px;padding:4px 10px;border-radius:4px;line-height:1;transition:all .15s var(--ease-snap)}
.pc-agent-detail-close:hover{color:var(--status-red);border-color:var(--status-red)}
.pc-agent-detail-body{padding:16px 18px}
.pc-agent-detail-framing{font-size:11px;color:var(--empire-silver);line-height:1.6;margin-bottom:14px;padding:10px 14px;background:var(--empire-elevated);border-radius:6px;border-left:3px solid var(--strike-cyan)}
.pc-agent-detail-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}
.pc-agent-stat{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:10px 12px;text-align:center;border-radius:6px}
.pc-agent-stat-val{font-family:var(--font-mono);font-size:16px;color:var(--empire-white);font-weight:500;display:block}
.pc-agent-stat-lbl{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.12em;text-transform:uppercase;display:block;margin-top:4px}
.pc-agent-detail-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);padding-top:8px;border-top:1px solid var(--empire-divider)}
@keyframes pc-chart-draw{0%{stroke-dashoffset:1000}100%{stroke-dashoffset:0}}
  .pc-orbital-wrapper{min-height:440px}
  .pc-orbital-agent{width:65px;height:44px;padding:4px 6px}
  .pc-boss-card{width:100px;height:100px}
  .pc-boss-title{font-size:11px}
.pc-decision-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px}
.pc-decision-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.pc-decision-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.pc-decision-count{font-family:var(--font-mono);font-size:10px;color:var(--signal-teal)}
.pc-decision-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 18px;transition:border-color .15s var(--ease-snap);cursor:pointer}
.pc-decision-row{display:grid;grid-template-columns:1fr 80px 48px 72px;gap:12px;align-items:center}
.pc-decision-winner{text-align:center}
.pc-winner-badge{font-family:var(--font-mono);font-size:8px;letter-spacing:.08em;text-transform:uppercase;color:var(--signal-teal);border:1px solid rgba(68,229,184,0.2);padding:2px 6px;border-radius:3px}
.pc-score-circle{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);font-size:12px;font-weight:600;border:2px solid}
.pc-detail-title{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;margin-bottom:12px}
.pc-detail-scores{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:14px}
.pc-detail-score{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:8px;text-align:center;border-radius:4px}
.pc-detail-score.winner{border-color:rgba(68,229,184,0.3);background:rgba(68,229,184,0.04)}
.pc-detail-aid{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.08em;display:block;margin-bottom:2px}
.pc-detail-pts{font-family:var(--font-mono);font-size:14px;color:var(--empire-white);font-weight:500}
.pc-judge-block{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px;border-radius:4px;border-left:3px solid var(--strike-cyan);margin-top:12px}
.pc-judge-head{font-family:var(--font-mono);font-size:9px;color:var(--strike-cyan);letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px}
/* ── SEO PERFORMANCE ─────────────────────────────────────────── */
.seo-kw-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--empire-divider)}
.seo-kw-row:last-child{border-bottom:none}
.seo-kw-name{font-size:11px;color:var(--empire-silver);font-family:var(--font-mono)}
.seo-kw-meta{display:flex;gap:10px;align-items:center}
.seo-kw-stat{font-family:var(--font-mono);font-size:10px;color:var(--signal-teal);font-weight:500}
.seo-kw-stat.dim{color:var(--empire-fog);font-weight:400}
.seo-kw-comp{font-family:var(--font-mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;padding:1px 6px;border-radius:3px;border:1px solid}
.seo-kw-comp.low{color:var(--signal-teal);border-color:rgba(68,229,184,0.2)}
.seo-kw-comp.medium{color:var(--status-amber);border-color:rgba(255,184,0,0.2)}
.seo-kw-comp.high{color:var(--status-red);border-color:rgba(255,68,68,0.2)}
.seo-content-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:10px 14px;margin-bottom:8px;border-radius:4px}
.seo-content-card:last-child{margin-bottom:0}
.seo-content-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.seo-content-kw{font-family:var(--font-mono);font-size:10px;color:var(--strike-cyan);font-weight:500}
.seo-content-niche{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog)}
.seo-content-title{font-size:11px;color:var(--empire-white);font-weight:500;margin-bottom:3px}
.seo-content-meta{font-size:10px;color:var(--empire-mist);line-height:1.4}
.seo-content-attrib{font-family:var(--font-mono);font-size:8px;color:var(--signal-teal);margin-top:6px;padding-top:5px;border-top:1px solid var(--empire-divider)}
.seo-audit-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--empire-divider)}
.seo-audit-row:last-child{border-bottom:none}
.seo-audit-url{font-family:var(--font-mono);font-size:10px;color:var(--empire-silver)}
.seo-audit-scores{display:flex;gap:10px}
.seo-audit-score{font-family:var(--font-mono);font-size:10px;font-weight:500}
.seo-audit-score.ok{color:var(--signal-teal)}
.seo-audit-score.warn{color:var(--status-amber)}
.seo-audit-score.bad{color:var(--status-red)}
.seo-audit-score.dim{color:var(--empire-fog);font-weight:400}
/* ── AGENT FLEET ────────────────────────────────────────────────────── */
.af-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px;margin-top:20px}
.af-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--empire-divider)}
.af-title{font-weight:500;font-size:13px;letter-spacing:.02em}
.af-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase}
.af-summary{display:flex;gap:18px;margin-bottom:16px;flex-wrap:wrap}
.af-stat{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.06em}
.af-stat strong{color:var(--empire-white);font-weight:500;margin-left:4px}
.af-stat.stale strong{color:var(--status-red)}
.af-stat.healthy strong{color:var(--signal-teal)}
.af-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.af-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:12px 14px;display:flex;align-items:center;gap:12px;transition:border-color .15s var(--ease-snap)}
.af-card:hover{border-color:var(--empire-border-hi)}
.af-card.stale{border-color:rgba(255,68,68,0.3);background:rgba(255,68,68,0.04)}
.af-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.af-dot.green{background:var(--signal-teal);box-shadow:0 0 8px rgba(68,229,184,0.6);animation:empire-pulse var(--pulse-duration) infinite}
.af-dot.red{background:var(--status-red);box-shadow:0 0 8px rgba(255,68,68,0.5)}
.af-card-body{flex:1;min-width:0}
.af-card-name{font-size:12px;color:var(--empire-white);font-weight:500;margin-bottom:2px}
.af-card-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.04em}
.af-card-meta.stale{color:var(--status-red)}
.af-card-caps{display:flex;flex-wrap:wrap;gap:3px;margin-top:6px}
.af-cap{font-family:var(--font-mono);font-size:7px;letter-spacing:.08em;text-transform:uppercase;padding:2px 5px;border-radius:2px;border:1px solid var(--empire-divider);color:var(--empire-fog)}
.af-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:24px 0;text-align:center}
.gh-refresh{margin-left:auto;display:flex;align-items:center}
.gh-refresh-btn{padding:6px 14px;font-family:var(--font-mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;border:1px solid var(--signal-teal-soft);background:transparent;color:var(--signal-teal);cursor:pointer;border-radius:4px;font-weight:600;transition:all .15s var(--ease-snap)}
.gh-refresh-btn:hover{background:rgba(68,229,184,0.08);border-color:var(--signal-teal)}
.gh-refresh-btn:disabled{opacity:.5;cursor:default}
.af-stat{display:inline-flex;align-items:center;gap:6px}
/* ── AGENT DETAIL MODAL ─────────────────────────────────────────────── */
.af-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(4px);z-index:100;display:flex;align-items:center;justify-content:center;padding:40px 20px;animation:af-fade-in .15s var(--ease-snap)}
@keyframes af-fade-in{from{opacity:0}to{opacity:1}}
.af-modal{background:var(--empire-surface);border:1px solid var(--empire-border);width:100%;max-width:680px;max-height:calc(100vh - 80px);overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.6);animation:af-slide-up .2s var(--ease-out-empire)}
@keyframes af-slide-up{from{transform:translateY(12px);opacity:0}to{transform:translateY(0);opacity:1}}
.af-modal-head{display:flex;justify-content:space-between;align-items:flex-start;padding:18px 22px;border-bottom:1px solid var(--empire-divider);background:var(--empire-elevated)}
.af-modal-eyebrow{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.18em;text-transform:uppercase;margin-bottom:4px}
.af-modal-title{font-weight:500;font-size:18px;color:var(--empire-white);display:flex;align-items:center;gap:10px}
.af-modal-close{background:none;border:1px solid var(--empire-divider);color:var(--empire-mist);cursor:pointer;font-size:20px;line-height:1;padding:4px 12px;border-radius:4px;transition:all .15s var(--ease-snap);font-family:var(--font-ui)}
.af-modal-close:hover{color:var(--status-red);border-color:var(--status-red)}
.af-modal-body{padding:20px 22px}
.af-modal-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.af-modal-section{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px}
.af-modal-section-wide{grid-column:1 / -1}
.af-modal-section-h{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.18em;text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--empire-divider)}
.af-modal-kv{display:flex;justify-content:space-between;align-items:baseline;padding:5px 0;font-family:var(--font-mono);font-size:11px}
.af-modal-kv span{color:var(--empire-fog);letter-spacing:.04em}
.af-modal-kv strong{color:var(--empire-white);font-weight:500;text-align:right}
.af-modal-kv strong.teal{color:var(--signal-teal)}
.af-modal-kv strong.red{color:var(--status-red)}
.af-modal-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:6px 0}
.af-modal-metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}
.af-modal-metric{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:8px 10px}
.af-modal-metric-k{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px;word-break:break-word}
.af-modal-metric-v{font-family:var(--font-mono);font-size:11px;color:var(--empire-white);word-break:break-word}
@media (max-width:640px){.af-modal-grid{grid-template-columns:1fr}.af-modal{max-width:100%}}
/* ── COMMAND CENTER PRO ───────────────────────────────────────── */
/* ── QC DASHBOARD ──────────────────────────────────────────────── */
.qc-summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.qc-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;position:relative;overflow:hidden}
.qc-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.qc-card-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.18em;text-transform:uppercase;margin-bottom:8px}
.qc-card-val{font-family:var(--font-display);font-weight:200;font-size:32px;color:var(--empire-white);line-height:1}
.qc-card-val.teal{color:var(--signal-teal)}
.qc-card-val.amber{color:#FFB800}
.qc-card-val.red{color:#FF4444}
.qc-card-val.dim{color:var(--empire-mist)}
.qc-card-sub{font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);margin-top:6px}
.qc-filter-bar{display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.qc-filter-group{display:flex;align-items:center;gap:6px}
.qc-filter-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.12em;text-transform:uppercase}
.qc-filter-select{padding:5px 10px;border:1px solid var(--empire-border);border-radius:4px;background:var(--empire-raised);color:var(--empire-white);font-family:var(--font-mono);font-size:10px;outline:none;cursor:pointer;transition:border-color .12s var(--ease-snap)}
.qc-filter-select:hover{border-color:var(--empire-border-hi)}
.qc-filter-select:focus{border-color:var(--signal-teal)}
.qc-filter-toggle{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border:1px solid var(--empire-border);border-radius:4px;cursor:pointer;font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);background:transparent;transition:all .12s var(--ease-snap)}
.qc-filter-toggle:hover{border-color:var(--empire-border-hi);color:var(--empire-white)}
.qc-filter-toggle.active{border-color:var(--signal-teal-soft);color:var(--signal-teal);background:rgba(68,229,184,0.04)}
.qc-refresh-btn{padding:6px 14px;border:1px solid var(--signal-teal-soft);border-radius:4px;cursor:pointer;font-family:var(--font-mono);font-size:9px;color:var(--signal-teal);background:transparent;transition:all .12s var(--ease-snap);margin-left:auto}
.qc-refresh-btn:hover{background:rgba(68,229,184,0.08)}
.qc-refresh-btn:disabled{opacity:.5;cursor:default}
.qc-table-wrap{overflow-x:auto;background:var(--empire-surface);border:1px solid var(--empire-border)}
.qc-table{width:100%;border-collapse:collapse;font-size:11px;min-width:900px}
.qc-table th{text-align:left;padding:10px 12px;color:var(--empire-fog);font-weight:500;border-bottom:1px solid var(--empire-border);text-transform:uppercase;font-size:9px;letter-spacing:.08em;background:var(--empire-elevated);white-space:nowrap}
.qc-table td{padding:9px 12px;border-bottom:1px solid var(--empire-divider);color:var(--empire-white);vertical-align:middle}
.qc-table tr:hover td{background:var(--empire-elevated)}
.qc-table tr.qc-expanded td{background:var(--empire-elevated)}
.qc-table tr:last-child td{border-bottom:none}
.qc-severity{display:inline-block;padding:2px 8px;border-radius:4px;font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.08em}
.qc-severity.tier_1{color:var(--signal-teal);background:rgba(68,229,184,0.1)}
.qc-severity.tier_2{color:#FFB800;background:rgba(255,184,0,0.1)}
.qc-severity.tier_3{color:#FF4444;background:rgba(255,68,68,0.1)}
.qc-category{font-size:10px;color:var(--empire-mist);letter-spacing:.04em;font-family:var(--font-mono)}
.qc-subject-id{font-family:var(--font-mono);font-size:10px;color:var(--strike-cyan);max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:middle}
.qc-summary{font-size:11px;color:var(--empire-silver);max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:middle}
.qc-check{font-family:var(--font-mono);font-size:9px;text-align:center}
.qc-check.yes{color:var(--signal-teal)}
.qc-check.no{color:var(--empire-fog)}
.qc-resolve-btn{padding:4px 12px;border:1px solid var(--signal-teal-soft);border-radius:4px;cursor:pointer;font-family:var(--font-mono);font-size:9px;color:var(--signal-teal);background:transparent;transition:all .12s var(--ease-snap);font-weight:600;white-space:nowrap}
.qc-resolve-btn:hover{background:rgba(68,229,184,0.1)}
.qc-resolve-btn:disabled{opacity:.4;cursor:not-allowed;border-color:var(--empire-border);color:var(--empire-fog)}
.qc-resolve-btn.done{opacity:.5;border-color:var(--empire-border);color:var(--empire-mist);cursor:default}
.qc-detail-panel{padding:14px 16px;background:var(--empire-elevated);border:1px solid var(--empire-divider);margin:4px 12px 12px;border-radius:6px;animation:empire-fade-up .2s var(--ease-out-empire)}
.qc-detail-head{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.qc-detail-json{font-family:var(--font-mono);font-size:10px;color:var(--empire-silver);white-space:pre-wrap;word-break:break-word;line-height:1.5;max-height:300px;overflow-y:auto;background:var(--empire-surface);padding:10px 12px;border-radius:4px;border:1px solid var(--empire-divider)}
.qc-detail-meta{display:flex;gap:16px;flex-wrap:wrap;font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid var(--empire-divider)}
.qc-detail-meta span strong{color:var(--empire-white)}
.qc-empty{text-align:center;padding:48px 0;color:var(--empire-fog);font-family:var(--font-ui);font-size:12px;font-style:italic}
.qc-loading{text-align:center;padding:48px 0;color:var(--empire-fog);font-family:var(--font-mono);font-size:11px}
.qc-error{background:rgba(255,68,68,0.08);border:1px solid rgba(255,68,68,0.2);border-radius:6px;padding:14px 18px;color:#FF4444;font-size:12px;margin-bottom:20px}

.ccp-dash{padding:0 4px}
.ccp-summary-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-bottom:24px}
.ccp-summary-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;text-align:center;transition:border-color .15s var(--ease-snap)}
.ccp-summary-card:hover{border-color:var(--empire-border-hi)}
.ccp-summary-val{font-family:var(--font-display);font-weight:200;font-size:28px;color:var(--empire-white);line-height:1}
.ccp-summary-val.teal{color:var(--signal-teal)}
.ccp-summary-val.amber{color:var(--status-amber)}
.ccp-summary-val.red{color:var(--status-red)}
.ccp-summary-val.dim{color:var(--empire-mist)}
.ccp-summary-lbl{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:6px}
.ccp-product-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.ccp-product-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;position:relative;overflow:hidden;transition:border-color .15s var(--ease-snap)}
.ccp-product-card:hover{border-color:var(--empire-border-hi)}
.ccp-product-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.ccp-product-card.error::before{background:linear-gradient(90deg,transparent,var(--status-red),transparent)}
.ccp-product-card.error{border-color:rgba(255,68,68,0.2)}
.ccp-product-card.warn::before{background:linear-gradient(90deg,transparent,var(--status-amber),transparent)}
.ccp-product-card.warn{border-color:rgba(255,184,0,0.15)}
.ccp-product-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;gap:8px}
.ccp-product-name{font-weight:500;font-size:14px;color:var(--empire-white);word-break:break-word}
.ccp-product-tier{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.08em;margin-bottom:6px}
.ccp-product-desc{font-size:11px;color:var(--empire-silver);line-height:1.5;margin-bottom:8px}
.ccp-product-meta{display:flex;justify-content:space-between;align-items:center;padding-top:10px;border-top:1px solid var(--empire-divider);font-family:var(--font-mono);font-size:10px}
.ccp-product-price{color:var(--signal-teal);font-weight:600}
.ccp-product-msg{color:var(--empire-fog);font-size:9px}
.ccp-bdg{display:inline-flex;align-items:center;gap:5px;font-family:var(--font-mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;padding:3px 8px;border-radius:var(--radius-pill);border:1px solid;flex-shrink:0}
.ccp-bdg.ok{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.ccp-bdg.error{color:var(--status-red);border-color:var(--status-red)}
.ccp-bdg.warn{color:var(--status-amber);border-color:var(--status-amber)}
.ccp-bdg-dot{width:5px;height:5px;border-radius:50%;background:currentColor;box-shadow:0 0 5px currentColor}
@media(max-width:768px){.ccp-summary-grid{grid-template-columns:repeat(3,1fr)}.ccp-product-grid{grid-template-columns:1fr}}

/* ── TRIAL PIPELINE ─────────────────────────────────────────────── */
.tp-summary-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-bottom:24px}
.tp-summary-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;text-align:center;transition:border-color .15s var(--ease-snap)}
.tp-summary-card:hover{border-color:var(--empire-border-hi)}
.tp-summary-val{font-family:var(--font-display);font-weight:200;font-size:28px;color:var(--empire-white);line-height:1}
.tp-summary-val.teal{color:var(--signal-teal)}
.tp-summary-val.amber{color:var(--status-amber)}
.tp-summary-val.red{color:var(--status-red)}
.tp-summary-val.dim{color:var(--empire-mist)}
.tp-summary-lbl{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:8px}
.tp-summary-sub{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);margin-top:4px;letter-spacing:.04em}
.tp-product-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px;margin-bottom:24px}
.tp-product-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;transition:border-color .15s var(--ease-snap)}
.tp-product-card:hover{border-color:var(--empire-border-hi)}
.tp-product-name{font-weight:500;font-size:14px;color:var(--empire-white);margin-bottom:4px}
.tp-product-meta{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.04em;margin-bottom:10px;display:flex;justify-content:space-between}
.tp-stat-teal{color:var(--signal-teal)}
.tp-stat-dim{color:var(--empire-fog)}
.tp-product-bar{margin-bottom:8px}
.tp-bar-track{height:8px;background:var(--empire-elevated);border-radius:4px;overflow:hidden;display:flex}
.tp-bar-fill{height:100%;transition:width .6s var(--ease-out-empire);min-width:2px}
.tp-bar-fill.active{background:var(--signal-teal)}
.tp-bar-fill.converted{background:var(--strike-cyan)}
.tp-bar-fill.expired{background:var(--status-amber)}
.tp-bar-legend{display:flex;gap:12px;font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.04em}
.tp-legend-dot{display:flex;align-items:center;gap:4px}
.tp-legend-dot::before{content:'';width:6px;height:6px;border-radius:2px;flex-shrink:0}
.tp-legend-dot.active::before{background:var(--signal-teal)}
.tp-legend-dot.converted::before{background:var(--strike-cyan)}
.tp-legend-dot.expired::before{background:var(--status-amber)}
.tp-bar-row{display:grid;grid-template-columns:40px 1fr 36px;gap:10px;align-items:center;padding:4px 0;font-family:var(--font-mono);font-size:10px}
.tp-bar-date{color:var(--empire-fog);letter-spacing:.04em}
.tp-small-bar-track{height:6px;background:var(--empire-elevated);border-radius:3px;overflow:hidden}
.tp-small-bar-fill{height:100%;border-radius:3px;background:var(--signal-teal);transition:width .6s var(--ease-out-empire);min-width:2px}
.tp-bar-val{color:var(--empire-white);font-weight:500;text-align:right}
.tp-recent-row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--empire-divider)}
.tp-recent-row:last-child{border-bottom:none}
.tp-recent-left{min-width:0;flex:1}
.tp-recent-email{font-size:12px;color:var(--empire-white);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tp-recent-prod{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);margin-top:2px}
.tp-recent-right{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0;margin-left:12px}
.tp-status-bdg{display:inline-flex;align-items:center;gap:4px;font-family:var(--font-mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;padding:3px 8px;border-radius:var(--radius-pill);border:1px solid}
.tp-status-bdg.active{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.tp-status-bdg.grace{color:var(--status-amber);border-color:var(--status-amber)}
.tp-status-bdg.expired{color:var(--empire-mist);border-color:var(--empire-border)}
.tp-status-bdg.converted{color:var(--strike-cyan);border-color:rgba(90,200,250,0.2)}
.tp-bdg-dot{width:5px;height:5px;border-radius:50%;background:currentColor;box-shadow:0 0 5px currentColor}
.tp-recent-days{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog)}
@media(max-width:768px){.tp-summary-grid{grid-template-columns:repeat(3,1fr)}.tp-product-grid{grid-template-columns:1fr}}
.tp-churn-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:4px}
.tp-churn-stat{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px;text-align:center}
.tp-stat-val{font-family:var(--font-display);font-weight:200;font-size:26px;color:var(--empire-white);line-height:1}
.tp-stat-val.teal{color:var(--signal-teal)}
.tp-stat-val.red{color:var(--status-red)}
.tp-stat-val.dim{color:var(--empire-mist)}
.tp-stat-lbl{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:6px}
.tp-reason-row{display:grid;grid-template-columns:20px 1fr auto 36px;gap:10px;align-items:center;padding:6px 0;font-family:var(--font-mono);font-size:10px;border-bottom:1px solid var(--empire-divider)}
.tp-reason-row:last-child{border-bottom:none}
.tp-reason-rank{color:var(--empire-fog);text-align:center;font-weight:500}
.tp-reason-bar-track{height:8px;background:var(--empire-elevated);border-radius:4px;overflow:hidden}
.tp-reason-bar-fill{height:100%;border-radius:4px;background:var(--status-red);transition:width .6s var(--ease-out-empire);min-width:2px}
.tp-reason-label{color:var(--empire-silver);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tp-reason-count{color:var(--empire-white);font-weight:500;text-align:right}


/* -- CPL PRICING ------------------------------------------------- */
.cpl-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:12px}
.cpl-tabs{display:flex;gap:4px;background:var(--empire-elevated);padding:3px;border-radius:8px}
.cpl-tab{padding:7px 18px;border:none;border-radius:6px;cursor:pointer;font-family:var(--font-mono);font-size:11px;color:var(--empire-mist);background:transparent;transition:all 0.15s var(--ease-snap)}
.cpl-tab:hover{color:var(--empire-white);background:var(--empire-raised)}
.cpl-tab.active{color:var(--empire-black);background:var(--signal-teal);font-weight:600}
.cpl-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.cpl-card{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:8px;padding:14px 16px}
.cpl-card-label{font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:var(--empire-fog);margin-bottom:4px}
.cpl-card-value{font-size:20px;font-weight:600;color:var(--empire-white);font-family:var(--font-mono)}
.cpl-card-value.positive{color:var(--signal-teal)}
.cpl-card-value.warning{color:var(--signal-gold)}
.cpl-health-card{grid-column:span 2}
.cpl-health-bar{display:flex;height:20px;border-radius:4px;overflow:hidden;gap:2px;margin:4px 0}
.cpl-health-seg{display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);font-size:9px;font-weight:600;color:#000;border-radius:3px;transition:flex 0.3s var(--ease-out-empire)}
.cpl-health-green{background:var(--signal-teal)}
.cpl-health-amber{background:#FFB800}
.cpl-health-red{background:#FF4444}
.cpl-health-meta{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:0.08em;text-align:center}
.cpl-health-active{opacity:1!important;filter:brightness(1.3);box-shadow:0 0 8px currentColor}
.cpl-health-dim{opacity:0.35;filter:saturate(0.3)}

.cpl-nav{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:14px}
.cpl-nav-btn{padding:5px 12px;border:1px solid var(--empire-border);border-radius:5px;cursor:pointer;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);background:transparent;transition:all 0.15s var(--ease-snap)}
.cpl-nav-btn:hover{border-color:var(--signal-teal);color:var(--signal-teal)}
.cpl-nav-btn.active{background:var(--signal-teal);color:var(--empire-black);border-color:var(--signal-teal);font-weight:600}
.cpl-service-summary{display:flex;align-items:center;gap:8px;padding:10px 14px;margin-bottom:14px;background:rgba(68,229,184,0.04);border:1px solid rgba(68,229,184,0.15);border-radius:6px;font-family:var(--font-mono);font-size:11px;animation:empire-fade-up 0.2s var(--ease-out-empire)}
.cpl-service-count{font-weight:700;font-size:16px;color:var(--signal-teal)}
.cpl-service-total{font-weight:600;font-size:14px;color:var(--empire-white)}
.cpl-service-label{color:var(--empire-mist);font-size:10px;letter-spacing:0.04em}
.cpl-service-badge{padding:3px 9px;border:1px solid var(--signal-teal-soft);border-radius:4px;color:var(--signal-teal);font-size:9px;letter-spacing:0.1em;text-transform:uppercase;margin-left:auto}
@keyframes cpl-shimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}
.cpl-skeleton{display:table-row-group}
.cpl-skeleton td{height:32px;padding:8px 10px}
.cpl-skel-bar{height:10px;border-radius:4px;background:linear-gradient(90deg,var(--empire-elevated) 25%,var(--empire-surface) 50%,var(--empire-elevated) 75%);background-size:800px 100%;animation:cpl-shimmer 1.5s ease-in-out infinite}
.cpl-last-refreshed-row{display:flex;align-items:center;justify-content:flex-end;margin-bottom:6px;gap:6px}
.cpl-last-refreshed{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.06em}
.cpl-reloading-bar{height:2px;background:var(--empire-divider);overflow:hidden;margin-bottom:8px;border-radius:2px}
.cpl-reloading-bar-inner{height:100%;width:40%;background:linear-gradient(90deg,transparent,var(--signal-teal),transparent);border-radius:2px;animation:cpl-reload-slide 1.2s ease-in-out infinite}
@keyframes cpl-reload-slide{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
.cpl-table{width:100%;border-collapse:collapse;font-size:11px}
.cpl-table th{text-align:left;padding:8px 10px;color:var(--empire-fog);font-weight:500;border-bottom:1px solid var(--empire-border);text-transform:uppercase;font-size:9px;letter-spacing:0.08em}
.hth-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin:0 auto;transition:transform 0.15s var(--ease-snap)}
.hth-dot:hover{transform:scale(1.8)}
.hth-dot.green{background:var(--signal-teal);box-shadow:0 0 6px rgba(68,229,184,0.6)}
.hth-dot.amber{background:#FFB800;box-shadow:0 0 6px rgba(255,184,0,0.5)}
.hth-dot.red{background:var(--status-red);box-shadow:0 0 6px rgba(255,68,68,0.5)}
.cpl-table td{padding:7px 10px;border-bottom:1px solid var(--empire-border);color:var(--empire-white);vertical-align:middle}
.cpl-table tr:hover td{background:var(--empire-elevated)}
.cpl-table tr.seo-row td{opacity:0.5}
.cpl-badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em}
.cpl-badge.ppl{background:rgba(0,200,200,0.15);color:var(--signal-teal)}
.cpl-badge.ppc{background:rgba(255,183,0,0.15);color:var(--signal-gold)}
.cpl-badge.service{background:rgba(130,100,255,0.15);color:#8264ff}
.cpl-badge.ppc-live{background:rgba(68,229,184,0.12);border-color:var(--signal-teal);color:var(--signal-teal);cursor:help}
.cpl-badge.ppc-live:hover{background:rgba(68,229,184,0.2)}
.cpl-margin-bar{display:inline-block;height:6px;border-radius:3px;min-width:2px;vertical-align:middle;margin-right:6px}
.cpl-margin-bar.high{background:var(--signal-teal)}
.cpl-margin-bar.mid{background:var(--signal-gold)}
.cpl-margin-bar.low{background:#e74c3c}
.cpl-pagination{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:16px;font-size:11px;color:var(--empire-mist)}
.cpl-pagination button{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:4px;padding:4px 10px;cursor:pointer;color:var(--empire-white);font-family:var(--font-mono);font-size:10px;transition:all 0.12s var(--ease-snap)}
.cpl-pagination button:hover{background:var(--signal-teal);color:var(--empire-black);border-color:var(--signal-teal)}
.cpl-pagination button:disabled{opacity:0.3;cursor:default}
.cpl-loading{text-align:center;padding:60px 0;color:var(--empire-fog);font-family:var(--font-mono);font-size:12px}
.cpl-error{background:rgba(231,76,60,0.1);border:1px solid #e74c3c;border-radius:8px;padding:16px 20px;color:#e74c3c;font-size:12px;margin-bottom:20px}

/* -- EXPORT BUTTONS --------------------------------------------- */
.cpl-export-bar{display:flex;gap:6px;align-items:center}
.cpl-export-btn{padding:6px 14px;border:1px solid var(--empire-border);border-radius:5px;cursor:pointer;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);background:transparent;transition:all 0.15s var(--ease-snap);display:flex;align-items:center;gap:5px}
.cpl-export-btn:hover{border-color:var(--signal-teal);color:var(--signal-teal);background:var(--signal-teal-soft)}
.cpl-export-btn svg{width:14px;height:14px;opacity:0.7}
.cpl-export-btn:hover svg{opacity:1}
/* -- COMPARE MODES TABLE ----------------------------------------- */
.cmp-intro{font-size:11px;color:var(--empire-mist);margin-bottom:16px;line-height:1.5}
.cmp-table{width:100%;border-collapse:collapse;font-size:11px;margin-bottom:20px}
.cmp-table th{text-align:left;padding:7px 9px;color:var(--empire-fog);font-weight:500;border-bottom:2px solid var(--empire-border);text-transform:uppercase;font-size:8px;letter-spacing:0.08em;background:var(--empire-elevated)}
.cmp-table td{padding:6px 9px;border-bottom:1px solid var(--empire-divider);color:var(--empire-white);vertical-align:middle}
.cmp-table tr:hover td{background:var(--empire-elevated)}
.cmp-table tr.seo-row td{opacity:0.4}
.cmp-model-cell{border-left:1px solid var(--empire-divider)}
.cmp-model-label{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;text-align:center;padding:3px 6px;border-radius:3px;display:inline-block}
.cmp-ppl{color:var(--signal-teal);border:1px solid rgba(0,200,200,0.2)}
.cmp-ppc{color:var(--signal-gold);border:1px solid rgba(255,183,0,0.2)}
.cmp-winner{background:rgba(68,229,184,0.04)}
.cmp-winner-tag{display:inline-block;font-size:8px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;padding:2px 6px;border-radius:3px;color:var(--signal-teal);border:1px solid rgba(68,229,184,0.2);background:rgba(68,229,184,0.06);margin-bottom:2px}
.cmp-value{font-family:var(--font-mono);font-size:10px}
.cmp-value.pos{color:var(--signal-teal)}
.cmp-value.neg{color:#e74c3c}
.cmp-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.cmp-card{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:8px;padding:14px 16px}
.cmp-card-label{font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:var(--empire-fog);margin-bottom:4px}
.cmp-card-value{font-size:18px;font-weight:600;color:var(--empire-white);font-family:var(--font-mono)}
.cmp-card-value.teal{color:var(--signal-teal)}
.cmp-card-value.gold{color:var(--signal-gold)}
.cmp-card-value.neutral{color:var(--empire-mist)}
.cmp-niche-filter{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.cmp-niche-btn{padding:4px 12px;border:1px solid var(--empire-border);border-radius:5px;cursor:pointer;font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);background:transparent;transition:all 0.12s var(--ease-snap)}
.cmp-niche-btn:hover{border-color:var(--signal-teal);color:var(--signal-teal)}
.cmp-niche-search{padding:5px 10px;border:1px solid var(--empire-border);border-radius:5px;background:var(--empire-raised);color:var(--empire-white);font-family:var(--font-mono);font-size:10px;outline:none;min-width:140px;transition:border-color 0.12s var(--ease-snap)}
.cmp-niche-search:focus{border-color:var(--signal-teal)}
.cmp-niche-search::placeholder{color:var(--empire-fog);opacity:0.5}
.cmp-niche-btn.active{background:var(--signal-teal);color:var(--empire-black);border-color:var(--signal-teal);font-weight:600}
/* -- AUTO-REFRESH TOGGLE ----------------------------------------- */
@keyframes cpl-refresh-pulse{0%,100%{opacity:1}50%{opacity:0.3}}
.cpl-refresh-btn{padding:6px 14px;border:1px solid var(--empire-border);border-radius:5px;cursor:pointer;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);background:transparent;transition:all 0.15s var(--ease-snap);display:flex;align-items:center;gap:6px}
.cpl-refresh-btn:hover{border-color:var(--signal-teal);color:var(--signal-teal);background:var(--signal-teal-soft)}
.cpl-refresh-btn.active{border-color:var(--signal-teal);color:var(--signal-teal);background:rgba(68,229,184,0.08)}
.cpl-refresh-dot{width:8px;height:8px;border-radius:50%;background:var(--empire-fog);flex-shrink:0;transition:all 0.3s var(--ease-snap)}
.cpl-refresh-btn.active .cpl-refresh-dot{background:var(--signal-teal);box-shadow:0 0 8px rgba(68,229,184,0.6);animation:cpl-refresh-pulse 2s ease-in-out infinite}
.cpl-refresh-label{font-size:9px;letter-spacing:0.06em}
/* -- PRINT STYLES ------------------------------------------------- */
@media print{
@page{size:landscape;margin:10mm 12mm}
body{background:#fff!important;color:#111!important;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif!important}
.app{grid-template-columns:1fr!important}
.nav,.nav *{display:none!important}

.cpl-header{margin-bottom:6px!important;padding:0!important}
.cpl-header h2{font-size:16px!important;color:#000!important;margin:0 0 2px!important}
.cpl-header .cpl-export-bar,.cpl-header .cpl-refresh-label{display:none!important}

.cpl-tabs,.cpl-nav,.cpl-pagination,.cpl-export-bar,.sidebar,.nav-panel,
.topbar,.cpl-reloading-bar,.cpl-loading,.cpl-error,
.roi-form,.roi-form-row,.roi-form-group,.roi-form-apply,
.chart-panel,.chart-empty,.chart-donut,.chart-bar{display:none!important}

.cpl-summary{display:grid!important;grid-template-columns:repeat(5,1fr)!important;
gap:6px!important;margin-bottom:8px!important;padding:0!important}
.cpl-card{background:#f8f8f8!important;border:1px solid #ccc!important;
padding:5px 8px!important;border-radius:3px!important;page-break-inside:avoid!important}
.cpl-card-label{font-size:7px!important;color:#666!important;
letter-spacing:.1em!important;text-transform:uppercase!important;margin-bottom:2px!important}
.cpl-card-value{font-size:13px!important;color:#000!important;font-weight:600!important}
.cpl-card-value.positive{color:#007700!important}
.cpl-card-value.warning{color:#cc8800!important}

.cpl-health-card{grid-column:1/-1!important;margin-top:2px!important}
.cpl-health-bar{display:flex!important;height:16px!important;border-radius:3px!important;
overflow:hidden!important;gap:2px!important;margin:3px 0!important}
.cpl-health-seg{display:flex!important;align-items:center!important;
justify-content:center!important;font-family:monospace!important;
font-size:8px!important;font-weight:700!important;color:#000!important;border-radius:2px!important}
.cpl-health-green{background:#4CAF50!important}
.cpl-health-amber{background:#FFC107!important}
.cpl-health-red{background:#F44336!important}
.cpl-health-meta{font-family:monospace!important;font-size:7px!important;
color:#666!important;text-align:center!important}

.cpl-table{width:100%!important;border-collapse:collapse!important;
font-size:7.5px!important;page-break-inside:auto!important}
.cpl-table thead{display:table-header-group!important}
.cpl-table th{background:#e8e8e8!important;color:#222!important;
padding:3px 4px!important;border:1px solid #bbb!important;
text-transform:uppercase!important;font-size:6.5px!important;
letter-spacing:.06em!important;font-weight:700!important}
.cpl-table td{padding:2px 4px!important;border:1px solid #ccc!important;
color:#333!important;font-size:7px!important;page-break-inside:avoid!important}
.cpl-table tbody tr{page-break-inside:avoid!important}
.cpl-table tbody tr:nth-child(even){background:#fafafa!important}
.cpl-table tbody tr:hover{background:#f0f0f0!important}
.cpl-table tr.seo-row td{opacity:0.35!important}

.cpl-badge{display:inline-block!important;border:1px solid #999!important;
padding:1px 4px!important;font-size:6.5px!important;border-radius:2px!important;
font-weight:600!important;line-height:1.3!important}
.cpl-badge.ppl{border-color:#009999!important;color:#009999!important}
.cpl-badge.ppc{border-color:#cc8800!important;color:#cc8800!important}
.cpl-badge.service{border-color:#6a4fcc!important;color:#6a4fcc!important}
.cpl-badge.model-ppc{background:#fff3e0!important;color:#e65100!important;
border-color:#e65100!important}

.cpl-margin-bar{border:1px solid #999!important;height:6px!important;
border-radius:2px!important;background:#eee!important}
.cpl-margin-fill{height:100%!important;border-radius:2px!important}

.cpl-health-dot{display:inline-block!important;width:8px!important;
height:8px!important;border-radius:50%!important;margin-right:2px!important}
.cpl-health-dot.green{background:#4CAF50!important}
.cpl-health-dot.amber{background:#FFC107!important}
.cpl-health-dot.red{background:#F44336!important}

.cpl-table td.tbl-num,.cpl-table th.tbl-num{text-align:right!important;font-family:monospace!important}
.cpl-table td.tbl-mono,.cpl-table th.tbl-mono{font-family:monospace!important;font-size:6.5px!important}

.cpl-service-summary{display:block!important;margin-bottom:8px!important;
padding:6px 8px!important;background:#f8f8f8!important;border:1px solid #ccc!important;
border-radius:3px!important;font-size:8px!important;color:#333!important}
.cpl-service-summary strong{color:#000!important}

.roi-results{display:block!important;padding:0!important;background:none!important;border:none!important}
.roi-card{background:#f8f8f8!important;border:1px solid #ccc!important;
padding:4px 8px!important;border-radius:3px!important;page-break-inside:avoid!important}
.roi-card-label{font-size:7px!important;color:#666!important;letter-spacing:.1em!important}
.roi-card-value{font-size:12px!important;color:#000!important}
.roi-card-value.profit{color:#007700!important}
.roi-card-value.loss{color:#cc0000!important}
.roi-table-wrap{display:block!important;margin-top:6px!important}
.roi-table{border-collapse:collapse!important;width:100%!important;font-size:7px!important}
.roi-table th{background:#e8e8e8!important;color:#222!important;padding:2px 4px!important;border:1px solid #ccc!important}
.roi-table td{padding:2px 4px!important;border:1px solid #ddd!important;color:#333!important}

.no-print,.cpl-skeleton{display:none!important}

tr{page-break-inside:avoid!important}
h2,h3,h4{page-break-after:avoid!important}

.cpl-header .print-date{display:block!important;font-family:monospace!important;
font-size:7px!important;color:#999!important;margin-top:2px!important
/* -- PULSE DASHBOARD PRINT STYLES --------------------------------- */
.pulse-grid{display:grid!important;grid-template-columns:repeat(4,1fr)!important;gap:8px!important;margin-bottom:12px!important}
.stat-card{background:#f8f8f8!important;border:1px solid #ccc!important;padding:10px 12px!important;page-break-inside:avoid!important}
.stat-label{font-size:8px!important;color:#666!important;letter-spacing:0.12em!important}
.stat-value{font-size:22px!important;color:#000!important}
.stat-value.teal{color:#008080!important}
.stat-value.cyan{color:#0088aa!important}
.stat-value.dim{color:#888!important}
.stat-meta{color:#666!important;font-size:8px!important}
.pulse-tabs{display:none!important}
.pulse-tab{display:none!important}
.section-sub{font-size:8px!important;color:#666!important}

/* -- REVENUE DASHBOARD PRINT STYLES ------------------------------- */
.pipeline-breakdown{background:#fff!important;border:1px solid #ccc!important;padding:12px!important;margin-bottom:12px!important;page-break-inside:avoid!important}
.pipeline-h{border-bottom:1px solid #ddd!important;margin-bottom:10px!important}
.pipeline-title{font-size:12px!important;color:#000!important}
.pipeline-total{color:#008080!important;font-size:10px!important}
.pipeline-grid{display:grid!important;grid-template-columns:repeat(auto-fill,minmax(200px,1fr))!important;gap:8px!important}
.rv-bar-row{display:grid!important;grid-template-columns:100px 1fr 60px 40px!important;gap:8px!important;padding:5px 0!important;border-bottom:1px solid #eee!important;font-size:9px!important}
.rv-bar-lane{color:#000!important;font-weight:600!important;font-size:9px!important}
.rv-bar-niche{color:#666!important;font-size:7px!important}
.rv-bar-track{height:8px!important;background:#eee!important;border-radius:3px!important}
.rv-bar-fill{background:#008080!important;border-radius:3px!important;min-width:2px!important}
.rv-bar-val{color:#008080!important;font-size:10px!important}
.rv-bar-meta{color:#888!important;font-size:7px!important}
.rv-accuracy-panel{background:#fff!important;border:1px solid #ccc!important;padding:12px!important;margin-top:12px!important;page-break-inside:avoid!important}
.rv-accuracy-head{border-bottom:1px solid #ddd!important;margin-bottom:12px!important;padding-bottom:8px!important}
.rv-accuracy-title{font-size:12px!important;color:#000!important}
.rv-accuracy-summary{font-size:9px!important;color:#666!important}
.rv-accuracy-chart{display:block!important;max-height:none!important}
.rv-acc-row{display:grid!important;grid-template-columns:50px 1fr 44px!important;gap:8px!important;padding:4px 0!important;border-bottom:1px solid #eee!important}
.rv-acc-date{color:#666!important;font-size:8px!important}
.rv-acc-bar-wrap{height:12px!important;background:#eee!important;border-radius:2px!important}
.rv-acc-bar.forecast{background:#0088aa!important;opacity:0.7!important}
.rv-acc-bar.actual{background:#008080!important;opacity:0.9!important}
.rv-acc-bar-label{font-size:7px!important;color:#fff!important}
.rv-acc-pct{font-size:10px!important;color:#000!important}
.rv-accuracy-legend{display:flex!important;gap:14px!important;margin-top:8px!important;padding-top:8px!important;border-top:1px solid #eee!important;font-size:8px!important}
.rv-acc-legend-swatch{width:8px!important;height:8px!important}
/* -- Section title / container support ------------------------------ */
.section-title{font-size:20px!important;color:#000!important}
.section-title em{color:#008080!important}
.rv-bar-label{display:flex!important;flex-direction:column!important;gap:2px!important}
.rv-acc-bars{display:flex!important;flex-direction:column!important;gap:4px!important}

/* -- Hide non-essential elements ---------------------------------- */
.topbar-actions,.rv-alerts,.rv-niche-card,.rv-narrative-panel,
.rv-accuracy-actions,.rv-export-btn,.rv-usdc-panel{display:none!important}
}
/* -- ROI CALCULATOR ---------------------------------------------- */
.roi-form{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:8px;padding:20px;margin-bottom:20px}
.roi-form-row{display:flex;gap:16px;flex-wrap:wrap;align-items:end}
.roi-form-group{display:flex;flex-direction:column;gap:4px;min-width:160px}
.roi-form-group label{font-size:9px;text-transform:uppercase;letter-spacing:0.1em;color:var(--empire-fog)}
.roi-form-group input,.roi-form-group select{background:var(--empire-raised);border:1px solid var(--empire-border);border-radius:5px;padding:8px 12px;color:var(--empire-white);font-family:var(--font-mono);font-size:12px;outline:none;transition:border-color 0.15s var(--ease-snap)}
.roi-form-group input:focus,.roi-form-group select:focus{border-color:var(--signal-teal)}
.roi-form-group input::placeholder{color:var(--empire-fog);opacity:0.5}
.roi-form-apply{padding:8px 24px;background:var(--signal-teal);border:none;border-radius:5px;color:var(--empire-black);font-family:var(--font-mono);font-size:11px;font-weight:600;cursor:pointer;transition:all 0.15s var(--ease-snap)}
.roi-form-apply:hover{box-shadow:var(--glow-signal);transform:translateY(-1px)}
.roi-form-apply:disabled{opacity:0.4;cursor:default;transform:none;box-shadow:none}
.roi-results{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.roi-card{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:8px;padding:14px 16px}
.roi-card-label{font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:var(--empire-fog);margin-bottom:4px}
.roi-card-value{font-size:18px;font-weight:600;color:var(--empire-white);font-family:var(--font-mono)}
.roi-card-value.profit{color:var(--signal-teal)}
.roi-card-value.loss{color:#e74c3c}
.roi-card-value.neutral{color:var(--signal-gold)}
.roi-table-wrap{overflow-x:auto;margin-top:8px}
.roi-table{width:100%;border-collapse:collapse;font-size:11px}
.roi-table th{text-align:left;padding:7px 10px;color:var(--empire-fog);font-weight:500;border-bottom:1px solid var(--empire-border);text-transform:uppercase;font-size:9px;letter-spacing:0.08em}
.roi-table td{padding:6px 10px;border-bottom:1px solid var(--empire-border);color:var(--empire-white);vertical-align:middle}
.roi-table tr:hover td{background:var(--empire-raised)}
.roi-table .pos{color:var(--signal-teal)}
.roi-table .neg{color:#e74c3c}

/* ── PSYCHOLOGY DASHBOARD ──────────────────────────────────────────── */
.psy-summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.psy-loading{padding:64px;text-align:center;font-family:var(--font-mono);font-size:11px;color:var(--empire-mist)}
.psy-error{padding:64px;text-align:center;font-family:var(--font-mono);font-size:11px;color:var(--status-red)}
.psy-flow-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px;max-height:360px;overflow-y:auto}
.psy-flow-card{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);background:var(--empire-elevated);padding:6px 10px;border:1px solid var(--empire-divider);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.psy-persona-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-bottom:20px}
.psy-persona-card{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:16px 18px}
.psy-persona-head{padding-left:12px;margin-bottom:10px}
.psy-persona-name{font-weight:500;font-size:14px;color:var(--empire-white);margin-bottom:2px}
.psy-persona-sub{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.08em}
.psy-persona-tone{font-family:var(--font-mono);font-size:9px;color:var(--strike-cyan);margin-bottom:6px;letter-spacing:.04em}
.psy-persona-dec{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.04em}
.psy-principle-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-bottom:20px}
.psy-principle-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:12px 14px}
.psy-principle-name{font-weight:500;font-size:13px;color:var(--empire-white);margin-bottom:4px}
.psy-principle-cat{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px}
.psy-principle-tactics{font-family:var(--font-mono);font-size:9px;color:var(--signal-teal);letter-spacing:.04em}
.psy-detect-input{font-family:var(--font-mono);font-size:11px;resize:vertical;min-height:80px}
.psy-detect-result{margin-top:16px;padding:16px;background:var(--empire-elevated);border:1px solid var(--empire-border);animation:empire-fade-up .2s var(--ease-out-empire)}
.psy-detect-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.psy-detect-label{font-size:14px;color:var(--empire-white);font-weight:500}
.psy-detect-label strong{color:var(--signal-teal)}
.psy-detect-conf{font-family:var(--font-mono);font-size:10px;color:var(--strike-cyan)}
.psy-detect-detail{padding-top:10px;border-top:1px solid var(--empire-divider)}
.psy-detect-detail-row{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);margin-bottom:6px;letter-spacing:.04em}
.psy-detect-pills{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.psy-detect-pill{display:inline-block;font-family:var(--font-mono);font-size:9px;letter-spacing:.08em;padding:4px 10px;border-radius:var(--radius-pill);border:1px solid var(--signal-teal-soft);color:var(--signal-teal);background:rgba(68,229,184,0.04)}
.psy-niche-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-bottom:20px}
.psy-niche-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px}
.psy-niche-name{font-weight:500;font-size:14px;color:var(--empire-white);margin-bottom:4px}
.psy-niche-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.08em;margin-bottom:8px}
.psy-niche-speed{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.04em;margin-bottom:2px}
.psy-niche-price{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.04em}
/* --- SELF-AWARENESS DASHBOARD --------------------------------------- */
.sa-empty{padding:48px;text-align:center;font-family:var(--font-mono);font-size:11px;color:var(--empire-fog);font-style:italic}
.sa-think-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-bottom:10px}
.sa-think-dots{display:flex;gap:6px;justify-content:center;margin-bottom:24px}
.sa-think-dot{width:6px;height:6px;border-radius:50%;background:var(--signal-teal);animation:psy-think 1.4s ease-in-out infinite}
.sa-think-dot:nth-child(2){animation-delay:.2s}
.sa-think-dot:nth-child(3){animation-delay:.4s}
@keyframes psy-think{0%,80%,100%{opacity:.2;transform:scale(.8)}40%{opacity:1;transform:scale(1.2)}}
.sa-live-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--signal-teal);box-shadow:var(--glow-signal);margin-right:6px;animation:empire-pulse var(--pulse-duration) infinite}
.sa-live-dot.paused{background:var(--status-amber);box-shadow:none;animation:none}
.sa-status{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.08em}
.sa-stat-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;position:relative;overflow:hidden;transition:border-color .15s var(--ease-snap)}
.sa-stat-card:hover{border-color:var(--empire-border-hi)}
.sa-stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--strike-cyan-soft),transparent)}
.sa-stat-row{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.sa-stat-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase}
.sa-stat-val{font-family:var(--font-display);font-weight:200;font-size:28px;color:var(--empire-white);line-height:1}
.sa-stat-val.ok{color:var(--signal-teal)}
.sa-stat-val.warn{color:var(--status-amber)}
.sa-stat-val.bad{color:var(--status-red)}
.sa-stat-val.dim{color:var(--empire-mist)}
.sa-stat-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:8px;letter-spacing:.04em}
.sa-graph-node{position:absolute;background:var(--empire-elevated);border:1px solid var(--empire-divider);border-radius:8px;padding:8px 12px;text-align:center;transition:all .2s var(--ease-snap);cursor:pointer;font-family:var(--font-mono);font-size:9px;color:var(--empire-white)}
.sa-graph-node:hover{border-color:var(--signal-teal-soft);z-index:10;box-shadow:0 0 16px rgba(68,229,184,.15)}
.sa-graph-node.active{border-color:var(--signal-teal);box-shadow:0 0 12px rgba(68,229,184,.2)}
.sa-graph-rect{fill:var(--empire-elevated);stroke:var(--empire-divider);stroke-width:1px}
.sa-graph-text{fill:var(--empire-mist);font-family:var(--font-mono);font-size:8px;text-anchor:middle}

/* ── EMAIL TRACKING DASHBOARD ───────────────────────────────── */
.et-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.et-card { background: var(--empire-surface); border: 1px solid var(--empire-border); padding: 18px 20px; position: relative; overflow: hidden; transition: border-color 0.2s var(--ease-snap); }
.et-card:hover { border-color: var(--empire-border-hi); }
.et-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, var(--signal-teal-soft), transparent); }
.et-card-label { font-family: var(--font-mono); font-size: 9px; color: var(--empire-mist); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 10px; }
.et-card-value { font-family: var(--font-mono); font-weight: 500; font-size: 28px; letter-spacing: -0.02em; color: var(--empire-white); line-height: 1; }
.et-card-value.teal { color: var(--signal-teal); }
.et-card-value.cyan { color: var(--strike-cyan); }
.et-card-value.dim { color: var(--empire-mist); }
.et-card-value.amber { color: var(--status-amber); }
.et-card-meta { font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog); margin-top: 6px; letter-spacing: 0.04em; }
.et-filters { display: flex; gap: 14px; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
.et-filter-tag { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.08em; }
.et-filter-btn { padding: 6px 14px; font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; border: 1px solid var(--empire-border); background: transparent; color: var(--empire-mist); cursor: pointer; border-radius: 4px; }
.et-filter-btn:hover { color: var(--empire-white); border-color: var(--empire-border-hi); }
.et-filter-btn.active { color: var(--signal-teal); border-color: var(--signal-teal-soft); background: rgba(68,229,184,0.04); }
.et-bar-row { display: grid; grid-template-columns: 140px 1fr 70px; gap: 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--empire-divider); font-family: var(--font-mono); }
.et-bar-row:last-child { border-bottom: none; }
.et-bar-label { font-size: 10px; color: var(--empire-white); font-weight: 500; }
.et-bar-track { height: 10px; background: var(--empire-elevated); border-radius: 4px; overflow: hidden; }
.et-bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s var(--ease-out-empire); min-width: 2px; }
.et-bar-fill.open { background: var(--signal-teal); }
.et-bar-fill.click { background: var(--strike-cyan); }
.et-bar-fill.bounce { background: var(--status-amber); }
.et-bar-val { font-size: 11px; color: var(--signal-teal); font-weight: 500; text-align: right; }
.et-chart-panel { background: var(--empire-surface); border: 1px solid var(--empire-border); padding: 18px; margin-bottom: 20px; }
.et-chart-panel-h { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--empire-divider); }
.et-chart-panel-title { font-weight: 500; font-size: 13px; letter-spacing: 0.02em; }
.et-chart-panel-tag { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.14em; }
.et-badge { display: inline-block; padding: 3px 8px; font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase; border-radius: 4px; border: 1px solid; }
.et-badge.open { color: var(--signal-teal); border-color: var(--signal-teal-soft); }
.et-badge.click { color: var(--strike-cyan); border-color: rgba(90,200,250,0.2); }
.et-badge.bounce { color: var(--status-amber); border-color: var(--status-amber); }
.et-badge.complaint { color: var(--status-red); border-color: var(--status-red); }
.et-badge.unsubscribe { color: var(--empire-mist); border-color: var(--empire-border); }
.et-email { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.et-seq-type { font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog); letter-spacing: 0.08em; }
.et-seq-type.b2b { color: var(--strike-cyan); }
.et-seq-type.storm { color: var(--signal-teal); }
.et-empty { font-family: var(--font-ui); font-size: 11px; color: var(--empire-fog); font-style: italic; padding: 32px 0; text-align: center; }

/* ── BILLING DASHBOARD ──────────────────────────────────────────── */
.bill-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.bill-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px 20px;position:relative;overflow:hidden;transition:border-color .2s var(--ease-snap)}
.bill-card:hover{border-color:var(--empire-border-hi)}
.bill-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.bill-card-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.18em;text-transform:uppercase;margin-bottom:10px}
.bill-card-val{font-family:var(--font-display);font-weight:200;font-size:32px;color:var(--empire-white);line-height:1}
.bill-card-val.teal{color:var(--signal-teal)}
.bill-card-val.cyan{color:var(--strike-cyan)}
.bill-card-val.gold{color:#FFD700}
.bill-card-val.dim{color:var(--empire-mist)}
.bill-card-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:6px}
.bill-split{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.bill-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px}
.bill-panel-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--empire-divider)}
.bill-panel-title{font-weight:500;font-size:13px;letter-spacing:.02em}
.bill-panel-count{font-family:var(--font-mono);font-size:10px;color:var(--signal-teal)}
.bill-bar-row{display:grid;grid-template-columns:1fr 80px 60px 60px;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--empire-divider);font-family:var(--font-mono);font-size:10px}
.bill-bar-row:last-child{border-bottom:none}
.bill-bar-name{color:var(--empire-white);font-weight:500;font-size:11px}
.bill-bar-num{color:var(--signal-teal);text-align:right}
.bill-bar-num.dim{color:var(--empire-mist)}
.bill-bar-num.gold{color:#FFD700}
.bill-buyer-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:12px 14px;margin-bottom:8px;transition:border-color .15s var(--ease-snap)}
.bill-buyer-card:hover{border-color:var(--empire-border-hi)}
.bill-buyer-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.bill-buyer-name{font-size:12px;color:var(--empire-white);font-weight:500}
.bill-buyer-meta{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.04em;margin-top:2px}
.bill-buyer-stats{display:flex;gap:10px;font-family:var(--font-mono);font-size:9px;color:var(--empire-mist)}
.bill-buyer-stats strong{color:var(--signal-teal);font-weight:600}
.bill-empty{font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic;padding:24px 0;text-align:center}

/* ├─ BILLING DASHBOARD ───────────────────────────────────────── */
.bill-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.bill-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:18px 20px;position:relative;overflow:hidden;transition:border-color .2s var(--ease-snap)}
.bill-card:hover{border-color:var(--empire-border-hi)}
.bill-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.bill-card-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.12em;text-transform:uppercase;margin-bottom:6px}
.bill-card-value{font-size:28px;font-weight:500;letter-spacing:-.02em}
.bill-card-value.dollar::before{content:'$';font-size:16px;opacity:.6;margin-right:2px}
.bill-card-value.teal{color:var(--signal-teal)}
.bill-card-value.gold{color:var(--signal-gold)}
.bill-card-value.green{color:var(--signal-green)}
.bill-card-value.red{color:var(--signal-red)}
.bill-card .delta{font-size:11px;margin-left:6px;font-family:var(--font-mono)}
.bill-card .delta.up{color:var(--signal-green)}
.bill-card .delta.down{color:var(--signal-red)}

/* ── BILLING CHART ────────────────────────────────────────────── */
.bill-chart-wrap{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin:20px 0;position:relative}
.bill-chart-wrap::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.bill-chart-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid var(--empire-divider)}
.bill-chart-title{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase}
.bill-chart-tag{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog)}
.bill-chart{display:flex;overflow-x:auto;height:140px;padding:8px 0 0;position:relative}
.bill-chart-bar-wrap{display:flex;flex-direction:column;align-items:center;flex-shrink:0;min-width:28px}
.bill-chart-bar{width:18px;border-radius:2px 2px 0 0;min-height:2px;transition:height .4s var(--ease-snap),background .2s;cursor:pointer;position:relative}
.bill-chart-bar:hover{opacity:.8}

.bill-chart-bar.settlement{background:var(--signal-teal);opacity:.85;border-radius:0 0 2px 2px}
.bill-chart-bar.premium{background:var(--status-amber);opacity:.7;border-radius:2px 2px 0 0;position:absolute;bottom:0;left:0;right:0}
.bill-chart-legend-dot.premium-dot{background:var(--status-amber);opacity:.7}
.bill-chart-bar.per-minute{background:var(--strike-cyan);opacity:.5;border-radius:2px 2px 0 0;margin-top:1px;position:relative}
.bill-chart-bar-stack{display:flex;flex-direction:column-reverse;align-items:center;width:18px;min-height:3px}
.bill-chart-bar.calls{background:var(--strike-cyan);opacity:.5}
.bill-chart-bar-label{font-family:var(--font-mono);font-size:7px;color:var(--empire-fog);margin-top:4px;white-space:nowrap}
.bill-chart-tooltip{position:absolute;bottom:100%;left:50%;transform:translateX(-50%);background:#000;color:var(--empire-white);padding:4px 8px;font-family:var(--font-mono);font-size:9px;border-radius:3px;white-space:nowrap;pointer-events:none;opacity:0;transition:opacity .15s;z-index:10;margin-bottom:4px}
.bill-chart-bar-wrap:hover .bill-chart-tooltip{opacity:1}
.bill-chart-line-svg{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2}
.bill-chart-line{fill:none;stroke:var(--strike-cyan);stroke-width:1.5px;stroke-linecap:round;stroke-linejoin:round;opacity:.7}
.bill-chart-line-dot{fill:var(--strike-cyan);opacity:.8;transition:r .15s var(--ease-snap)}
.bill-chart-line-cumul{fill:none;stroke:var(--status-amber);stroke-width:1.5px;opacity:.7;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:4 3}
.bill-chart-line-dot-cumul{fill:var(--status-amber);opacity:.6;transition:r .15s var(--ease-snap)}
.bill-chart-bars:hover ~ .bill-chart-line-svg .bill-chart-line-dot,.bill-chart-bars:hover ~ .bill-chart-line-svg .bill-chart-line-dot-cumul{r:3.5}
.bill-chart-inner{position:relative;flex:0 0 auto;height:130px}
.bill-chart-bars{display:flex;align-items:flex-end;gap:3px;position:relative;z-index:1}
.bill-chart-empty{text-align:center;padding:50px 20px;color:var(--empire-mist);font-family:var(--font-mono);font-size:11px}
.bill-chart-window{display:flex;gap:4px;margin-left:auto}
.bill-chart-window-btn{padding:4px 10px;font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;border:1px solid var(--empire-border);background:transparent;color:var(--empire-mist);cursor:pointer;border-radius:4px;transition:all .15s var(--ease-snap)}
.bill-chart-window-btn:hover{color:var(--empire-white);border-color:var(--empire-border-hi)}
.bill-chart-window-btn.active{color:var(--signal-teal);border-color:var(--signal-teal-soft);background:rgba(68,229,184,0.06)}
.bill-chart-mode-btn{margin-left:9px;padding:4px 10px;font-family:var(--font-mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;border:1px solid var(--empire-border);background:transparent;color:var(--empire-fog);cursor:pointer;border-radius:4px;transition:all .15s var(--ease-snap)}
.bill-chart-mode-btn:hover{color:var(--empire-white);border-color:var(--empire-border-hi)}
.bill-chart-bar-wrap.side{display:flex;gap:3px;align-items:flex-end}
.bill-chart-bar.settlement.side{background:var(--signal-teal);opacity:.85;border-radius:2px 2px 0 0;flex:1;min-width:6px}
.bill-chart-bar.per-minute.side{background:var(--strike-cyan);opacity:.5;border-radius:2px 2px 0 0;flex:1;min-width:6px}
.bill-chart-legend{display:flex;gap:16px;margin-top:10px;padding-top:10px;border-top:1px solid var(--empire-divider)}
.bill-chart-legend-item{display:flex;align-items:center;gap:6px;font-family:var(--font-mono);font-size:8px;color:var(--empire-mist);letter-spacing:.08em}
.bill-chart-legend-dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}
.bill-section-title{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;margin:28px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--empire-border)}
.bill-table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:20px}
.bill-table th{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.12em;text-transform:uppercase;text-align:left;padding:8px 10px;border-bottom:1px solid var(--empire-border)}
.bill-table td{padding:8px 10px;border-bottom:1px solid var(--empire-divider);color:var(--empire-white)}
.bill-table tr:hover td{background:rgba(255,255,255,.02)}
.bill-table .num{font-family:var(--font-mono);text-align:right}
.bill-loading{text-align:center;padding:60px 20px;color:var(--empire-mist);font-family:var(--font-mono);font-size:11px}
.bill-error{text-align:center;padding:40px 20px;color:var(--signal-red);font-family:var(--font-mono);font-size:11px}
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
const NAV_GROUPS = [
  {
    id: 'ops', label: 'COMMAND', icon: '📡', defaultOpen: true,
    items: [
      { id: 'command-center', label: 'Command Center', sub: 'All products · system health' },
      { id: 'pulse',         label: 'Pulse',         sub: 'Live overview' },
      { id: 'pipeline',      label: 'Pipeline',       sub: 'Email & SMS · state machine' },
      { id: 'dispatch',      label: 'Dispatch',       sub: 'Contractor matching' },
      { id: 'dispatch-health', label: 'Dispatch Health',  sub: 'Circuit breaker · errors · throughput' },
      { id: 'inbound',       label: 'Inbound',        sub: 'Calls · triage · recordings' },
      { id: 'leads',         label: 'Leads',          sub: 'Inbound leads · pipeline · intake' },
      { id: 'kanban',        label: 'Kanban',         sub: 'Agent task queue · pipeline stages' },
      { id: 'sms-performance', label: 'SMS Performance', sub: 'Niche breakdown · sequence stats' },
      { id: 'reply-rates',     label: 'Dispatch Monitor', sub: 'Reply rates · A/B · circuit breaker · dispatch health' },
      { id: 'fleet', label: 'Fleet', sub: 'Agent roles · hierarchy · findings' },
    ]
  },
  {
    id: 'revenue', label: 'REVENUE', icon: '💰', defaultOpen: true,
    items: [
      { id: 'payouts',       label: 'Payouts',        sub: 'Pending · approvals · history' },
      { id: 'dispatches',    label: 'Dispatches',     sub: 'Lead matches · mark settled' },
      { id: 'fees',          label: 'Fees',           sub: 'Settled claims · 3% per claim' },
      { id: 'predicted',     label: 'Predicted',      sub: 'Forecasted fees by segment' },
      { id: 'signal',        label: 'Signal',         sub: 'Organic replies + confidence gate' },
      { id: 'contractors',   label: 'Contractors',    sub: 'Applications & approvals' },
      { id: 'partners',      label: 'Partners',       sub: 'Buyers · pending · approvals' },
      { id: 'revenue',       label: 'Revenue',        sub: 'Predictive revenue · per-lane MRR · LLM forecast' },
      { id: 'closer',       label: 'Closer',         sub: 'AI pipeline · funnel · stats' },
      { id: 'products',     label: 'Products',       sub: 'Strike packs / SaaS tiers / subscriptions' },
      { id: 'pain-points',  label: 'Pain Points',    sub: 'Niche scripts · weights · conversion' },
      { id: 'swarm-gate',   label: 'Swarm Gate',     sub: 'Parallel video ads · scan → fire' },
      { id: 'trial-pipeline', label: 'Trial Pipeline', sub: 'Active · converting · churned' },
      { id: 'affiliates',   label: 'Affiliates',    sub: 'Manage · referral links · stats' },
      { id: 'cpl-pricing',  label: 'CPL Pricing',   sub: 'Per-lane margins . sell prices . benchmarks' },
      { id: 'profit-margin', label: 'Profit Margin',  sub: 'P&L · bottlenecks · maximiser' },
      { id: 'traffic-ads',  label: 'Traffic & Ads', sub: 'Campaigns · trends · budget' },
      { id: 'email-tracking', label: 'Email Tracking', sub: 'Opens · clicks · engagement' },
    ]
  },
  {
    id: 'intel', label: 'INTELLIGENCE', icon: '🧠', defaultOpen: false,
    items: [
      { id: 'neural-core',   label: 'Neural Core',    sub: 'Live brain · autonomous decisions · 5s refresh' },
      { id: 'holo-map',      label: 'Holo Map',       sub: 'Live storm grid · 3D target overlay' },
      { id: 'si-strategy',   label: 'SI Strategy',    sub: 'Evolution · genomes · win rates' },
      { id: 'si-adaptive',   label: 'SI Adaptive',    sub: 'Subsystem adoption · parameter propagation' },
      { id: 'panel_court',      label: 'Panel Court',    sub: '10-Agent ensemble · voting · learning' },
      { id: 'seo',           label: 'SEO',            sub: 'Audits · keywords · content · genome' },
      { id: 'personality',    label: 'Personality',    sub: 'Brain persona · per-niche config · thresholds' },
      { id: 'strategist',    label: 'Strategist',     sub: 'Strategic intel · analysis · narratives' },
      { id: 'business-planner',label: 'Planner',        sub: 'Quarterly plans · niche actions · roadmap' },
      { id: 'analytics',     label: 'Analytics',      sub: 'KPIs · funnel · trends · anomalies' },
      { id: 'psychology',    label: 'Psychology',    sub: 'Mind map · personas · persuasion' },
      { id: 'self-awareness',label: 'Self-Aware',    sub: 'System model · narrative · anomalies' },
    ]
  },
  {
    id: 'system', label: 'SYSTEM', icon: '⚙️', defaultOpen: false,
    items: [
      { id: 'console',       label: 'Console',        sub: 'Sovereign natural-language ops' },
      { id: 'operators',     label: 'Operators',      sub: 'Roster · roles · invites' },
      { id: 'audit',         label: 'Audit',          sub: 'Operator action history' },
      { id: 'governor',      label: 'Governor',       sub: 'AGI governor · weight control · guardrails' },
      { id: 'health-monitor',label: 'Health Monitor', sub: 'Agent mesh · system health · overseer' },
      { id: 'bridge',         label: 'Bridge',         sub: 'Voice-first interface · full-screen' },
      { id: 'network', label: 'Network',  sub: 'Members · referrals · growth' },
      { id: 'loop', label: 'Loop', sub: 'Lanes · pacing · strategies' },
      { id: 'support',       label: 'Support',        sub: 'FAQ · contact · live chat' },
      { id: 'stack', label: 'Stack', sub: 'Infra · services · incidents' },
      { id: 'agent-os',   label: 'Agent OS',     sub: 'Kernel · agents · IPC · boot' },
    ]
  },
];

// Flattened lookup (built from GROUPS) for hash → section resolution
const SECTIONS = NAV_GROUPS.reduce((flat, g) => flat.concat(g.items), []);

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


// ── CLOSER SECTION ────────────────────────────────────────────────────────────────────
function Closer() {
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);
  const [usdcData, setUsdcData] = useState(null);
  const [usdcErr, setUsdcErr] = useState(null);
  const [cryptoStats, setCryptoStats] = useState(null);

  useEffect(() => {
    let stop = false;
    const load = () => {
      apiFetch('/api/v1/closer/stats').then(r => r.json())
        .then(s => { if (!stop) { setStats(s); setErr(null); } })
        .catch(e => { if (!stop) setErr(String(e)); });
    };
    load();
    const iv = setInterval(load, 15000);
    return () => { stop = true; clearInterval(iv); };
  }, []);
  if (err) return html`<div class="stub"><div class="stub-title">Could not load Closer</div>

        <div class="cmp-summary"><div class="stub-body">${err}</div></div>`;
  if (!stats) return html`<div class="stub"><div class="stub-title">Loading <em>Closer</em></div><div class="stub-body">Fetching pipeline stats...</div></div>`;
  const total = (stats.leads_processed || 0);
  const goRate = total > 0 ? ((stats.brain_go || 0) / total * 100).toFixed(1) : '0.0';
  const noGoRate = total > 0 ? ((stats.brain_no_go || 0) / total * 100).toFixed(1) : '0.0';
  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">AI <em>Closer</em></div>
          <div class="section-sub">AGI voice pipeline · brain → strategy → call/nurture</div>
        </div>
        <div class="topbar-actions">
          <span style=${{fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-fog)'}}>
            Stream ≥${(stats.stream_confidence||0.7).toFixed(1)} · Static ≥${(stats.static_confidence||0.4).toFixed(1)}
          </span>
        </div>
      </div>
      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">LEADS PROCESSED</div>
          <div class="stat-value">${total}</div>
          <div class="stat-meta">total inbound through pipeline</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">BRAIN GO</div>
          <div class="stat-value teal">${stats.brain_go || 0}</div>
          <div class="stat-meta">${goRate}% · LLM-approved leads</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">BRAIN NO-GO</div>
          <div class="stat-value dim">${stats.brain_no_go || 0}</div>
          <div class="stat-meta">${noGoRate}% · skipped / nurtured</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">ERRORS</div>
          <div class=${'stat-value ' + ((stats.errors||0) > 0 ? 'bad' : 'teal')}>${stats.errors || 0}</div>
          <div class="stat-meta">pipeline health</div>
        </div>
      </div>
      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">AGI STREAM CALLS</div>
          <div class="stat-value cyan">${stats.agi_stream_calls || 0}</div>
          <div class="stat-meta">live Kokoro TTS · high confidence</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">STATIC CALLS</div>
          <div class="stat-value teal">${stats.static_calls || 0}</div>
          <div class="stat-meta">Vonage NCCO · medium confidence</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">NURTURE ROUTED</div>
          <div class="stat-value dim">${stats.nurture_routed || 0}</div>
          <div class="stat-meta">SMS/email drip · low confidence</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">CONVERSION</div>
          <div class="stat-value teal">${total > 0 ? (((stats.agi_stream_calls||0) + (stats.static_calls||0)) / total * 100).toFixed(1) + '%' : '0.0%'}</div>
          <div class="stat-meta">calls / total leads</div>
        </div>
      </div>
      <div class="compliance-panel" style=${{marginTop:'16px'}}>
        <div class="compliance-h">
          <div class="compliance-title">Wired Dependencies</div>
          <div class="compliance-tag">LIVE STATUS</div>
        </div>
        <div class="compliance-grid">
          <div class="compliance-card">
            <div class="compliance-card-label">BRAIN DECIDER</div>
            <div class=${'compliance-card-value ' + (stats.brain_decider_wired ? 'ok' : 'bad')}>
              ${stats.brain_decider_wired ? 'WIRED' : 'OFFLINE'}
            </div>
          </div>
          <div class="compliance-card">
            <div class="compliance-card-label">VOICE ROUTER</div>
            <div class=${'compliance-card-value ' + (stats.voice_router_wired ? 'ok' : 'bad')}>
              ${stats.voice_router_wired ? 'WIRED' : 'OFFLINE'}
            </div>
          </div>
          <div class="compliance-card">
            <div class="compliance-card-label">SMS ENGINE</div>
            <div class=${'compliance-card-value ' + (stats.sms_engine_wired ? 'ok' : 'bad')}>
              ${stats.sms_engine_wired ? 'WIRED' : 'OFFLINE'}
            </div>
          </div>
          <div class="compliance-card">
            <div class="compliance-card-label">EMAIL ENGINE</div>
            <div class=${'compliance-card-value ' + (stats.email_engine_wired ? 'ok' : 'bad')}>
              ${stats.email_engine_wired ? 'WIRED' : 'OFFLINE'}
            </div>
          </div>
        </div>
      </div>
    </div>
  ${profileCtr ? html`
    <div style="position:fixed;inset:0;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:9999" onClick=${() => setProfileCtr(null)}>
      <div style="background:var(--empire-surface);border:1px solid var(--empire-border);padding:28px 32px;max-width:420px;width:90%;position:relative;color:var(--empire-white)" onClick=${e => e.stopPropagation()}>
        <button style="position:absolute;top:12px;right:16px;background:none;border:none;color:var(--empire-mist);font-size:18px;cursor:pointer;font-family:var(--font-mono)" onClick=${() => setProfileCtr(null)}>✕</button>
        <div style="font-size:18px;font-weight:500;margin-bottom:4px">${profileCtr.name || 'Contractor'}</div>
        <div style="font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);margin-bottom:16px">${profileCtr.metro || '—'}</div>
        <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--empire-divider);font-family:var(--font-mono);font-size:10px">
          <span style="color:var(--empire-mist)">Trust Score</span>
          <span style="color:var(--signal-teal);font-weight:600">${profileCtr.trust_score != null ? profileCtr.trust_score.toFixed(1) + ' / 10' : '—'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--empire-divider);font-family:var(--font-mono);font-size:10px">
          <span style="color:var(--empire-mist)">Specialties</span>
          <span style="color:var(--signal-teal);font-weight:600">${profileCtr.specialties && profileCtr.specialties.length > 0 ? profileCtr.specialties.join(', ') : '—'}</span>
        </div>
      </div>
    </div>
  ` : ''}
  `;
}


// ── PAIN POINTS SECTION ────────────────────────────────────────────────────────────────────
function PainPoints() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [activeNiche, setActiveNiche] = useState(null);
  useEffect(() => {
    let stop = false;
    const load = () => {
      apiFetch('/api/v1/pain-points/snapshot').then(r => r.json())
        .then(d => { if (!stop) { setData(d); setErr(null); } })
        .catch(e => { if (!stop) setErr(String(e)); });
    };
    load();
    const iv = setInterval(load, 30000);
    return () => { stop = true; clearInterval(iv); };
  }, []);

  // ── Billing summary fetch ──
  useEffect(() => {
    let stop = false;
    const load = () => {
      apiFetch('/api/v1/billing/summary').then(r => r.json())
        .then(d => { if (!stop) { setBillingData(d); setBillingErr(null); } })
        .catch(e => { if (!stop) setBillingErr(String(e)); });
    };
    load();
    const iv = setInterval(load, 60000);
    return () => { stop = true; clearInterval(iv); };
  }, []);

  // ── Billing timeseries fetch (30-day chart) ──
  useEffect(() => {
    let stop = false;
    const load = () => {
      apiFetch('/api/v1/billing/timeseries?days=' + (billWindow === '90d' ? 90 : billWindow === '7d' ? 7 : 30)).then(r => r.json())
        .then(d => { if (!stop) { d.total_premium = d.series ? d.series.reduce((sum, s) => sum + Math.max(0, s.per_minute_revenue - s.settlement_revenue), 0) : 0; setBillTimeseries(d); } })
        .catch(e => { if (!stop) console.warn('timeseries fetch:', e); });
    };
    load();
    const iv = setInterval(load, 120000);
    return () => { stop = true; clearInterval(iv); };
  }, [billWindow]);


  if (err) return html`<div class="stub"><div class="stub-title">Could not load Pain Points</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-title">Loading <em>Pain Points</em></div><div class="stub-body">Fetching pain point profiles...</div></div>`;

  const niches = Object.entries(data.by_niche || {}).sort();
  const selectedNiche = activeNiche && data.by_niche[activeNiche] ? activeNiche : (niches[0] ? niches[0][0] : null);
  const nicheData = selectedNiche ? data.by_niche[selectedNiche] : null;
  const points = nicheData ? nicheData.pain_points : [];
  const totalAttempts = nicheData ? nicheData.total_attempts : 0;
  const totalSuccesses = nicheData ? nicheData.total_successes : 0;
  const overallCR = totalAttempts > 0 ? (totalSuccesses / totalAttempts * 100).toFixed(1) : '0.0';

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Pain <em>Points</em></div>
          <div class="section-sub">Niche scripts · conversion weights · AI closer integration</div>
        </div>
        <div class="topbar-actions">
          <span style=${{fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-fog)'}}>
            ${data.niches || 0} niches · ${data.total_pain_points || 0} profiles
          </span>
        </div>
      </div>
      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">NICHES TRACKED</div>
          <div class="stat-value teal">${data.niches || 0}</div>
          <div class="stat-meta">storm, hail, flood, legal, etc.</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">PAIN POINTS</div>
          <div class="stat-value teal">${data.total_pain_points || 0}</div>
          <div class="stat-meta">niche-specific profiles</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">TOTAL ATTEMPTS</div>
          <div class="stat-value cyan">${totalAttempts}</div>
          <div class="stat-meta">${selectedNiche || '—'} niche</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">OVERALL CONV RATE</div>
          <div class="stat-value ${overallCR > 30 ? 'teal' : 'dim'}">${overallCR}%</div>
          <div class="stat-meta">${totalSuccesses} successes</div>
        </div>
      </div>

      <div class="pp-niches-bar">
        ${niches.map(([niche, nd]) => {
          const nicr = nd.total_attempts > 0 ? (nd.total_successes / nd.total_attempts * 100).toFixed(0) : 0;
          return html`<button
            class=${"pp-niche-tab " + (selectedNiche === niche ? 'active' : '')}
            onClick=${() => setActiveNiche(niche)}
            key=${niche}
          >
            <span class="pp-niche-name">${niche}</span>
            <span class="pp-niche-count">${nd.pain_points.length}pp</span>
            <span class="pp-niche-cr">${nicr}%</span>
          </button>`;
        })}
      </div>

      ${points.length > 0 ? html`
      <div class="pipeline-breakdown">
        <div class="pipeline-h">
          <div class="pipeline-title">${selectedNiche} · Pain Points</div>
          <div class="pipeline-total">${totalAttempts} attempts · ${overallCR}% conv</div>
        </div>
        <div class="pipeline-grid">
          ${points.map(pp => {
            const cr = pp.attempts > 0 ? (pp.conversion_rate * 100).toFixed(1) : '0.0';
            const wColor = pp.weight >= 0.6 ? 'var(--signal-teal)' : pp.weight >= 0.5 ? 'var(--status-amber)' : 'var(--status-red)';
            const crColor = pp.conversion_rate >= 0.6 ? 'var(--signal-teal)' : pp.conversion_rate >= 0.3 ? 'var(--status-amber)' : 'var(--status-red)';
            return html`<div class="pp-card" key=${pp.id}>
              <div class="pp-card-top">
                <div class="pp-card-label">${pp.label}</div>
                <div class="pp-card-weight" style=${{color: wColor}}>${pp.weight.toFixed(2)} wt</div>
              </div>
              <div class="pp-card-hook">🗣 ${pp.hook}</div>
              <div class="pp-card-resolution">✓ ${pp.resolution.slice(0, 80)}</div>
              <div class="pp-card-proof">📊 ${pp.proof}</div>
              <div class="pp-card-stats">
                <span class="pp-card-stat">${pp.attempts} attempts</span>
                <span class="pp-card-stat">${pp.successes} won</span>
                <span class="pp-card-stat" style=${{color: crColor}}>${cr}% CR</span>
              </div>
              <div class="pp-w-bar-wrap">
                <div class="pp-w-bar" style=${{width: (pp.weight * 100) + '%', backgroundColor: wColor}}></div>
              </div>
            </div>`;
          })}
        </div>
      </div>
      ` : html`<div class="stub"><div class="stub-body">No pain points for ${selectedNiche} yet.</div></div>`}

      <div class="pp-export-bar">
        <button class="rv-export-btn csv" onClick=${() => {
          apiFetch('/api/v1/pain-points/export/csv').then(r => r.blob()).then(blob => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'empire_pain_points.csv';
            a.click(); URL.revokeObjectURL(url);
          });
        }}>Download CSV</button>
        <button class="rv-export-btn pdf" onClick=${() => {
          apiFetch('/api/v1/pain-points/export/report').then(r => r.text()).then(html => {
            const w = window.open('', '_blank');
            w.document.write(html); w.document.close();
          });
        }}>View Report</button>
      </div>
    </div>
  `;
}

// ── SWARM GATE SECTION ────────────────────────────────────────────────────────────────────
function SwarmGate() {
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [err, setErr] = useState(null);
  const [firing, setFiring] = useState(false);
  const [fireResult, setFireResult] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [s, j] = await Promise.all([
        apiFetch('/api/v1/swarm/stats').then(r => r.json()),
        apiFetch('/api/v1/swarm/jobs?limit=15').then(r => r.json()),
      ]);
      setStats(s);
      setJobs(j.jobs || []);
      setErr(null);
    // Fetch USDC ledger
    try {
      const u = await apiFetch('/api/revenue/usdc-ledger?limit=10');
      if (u.ok) {
        const j = await u.json();
        setUsdcData(j);
        setUsdcErr(null);
      } else {
        setUsdcErr('USDC ledger fetch failed: ' + u.status);
      }
    } catch (eu) {
      setUsdcErr(eu.message || 'USDC fetch error');
      setUsdcData(null);

    // Fetch crypto payment stats (for activation_failed panel)
    try {
      const cs = await apiFetch('/api/v1/crypto/stats');
      if (cs.ok) {
        setCryptoStats(await cs.json());
      }
    } catch (_) {
      /* non-critical */
    }
    }

    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(String(e));
    }
  }, []);

  useEffect(() => {
    let stop = false;
    const load = () => {
      apiFetch('/api/v1/swarm/stats').then(r => r.json())
        .then(s => { if (!stop) setStats(s); })
        .catch(e => { if (!stop && e.message !== 'Unauthorized') setErr(String(e)); });
      apiFetch('/api/v1/swarm/jobs?limit=15').then(r => r.json())
        .then(j => { if (!stop) setJobs(j.jobs || []); })
        .catch(() => {});
    };
    load();
    const iv = setInterval(load, 30000);
    return () => { stop = true; clearInterval(iv); };
  }, []);

  const fireSwarm = async () => {
    setFiring(true);
    setFireResult(null);
    try {
      const r = await apiFetch('/api/v1/swarm/scan', { method: 'POST' }).then(r => r.json());
      if (r.packages && r.packages.length > 0) {
        const fr = await apiFetch('/api/v1/swarm/fire', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ packages: r.packages }),
        }).then(r => r.json());
        setFireResult(fr);
        reload();
      } else {
        setFireResult({ ok: true, jobs: [billWindow], count: 0, message: 'No storm targets found' });
      }
    } catch (e) {
      setFireResult({ ok: false, error: String(e) });
    } finally {
      setFiring(false);
    }
  };

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Swarm Gate</div><div class="stub-body">${err}</div></div>`;
  if (!stats) return html`<div class="stub"><div class="stub-title">Loading <em>Swarm Gate</em></div><div class="stub-body">Fetching swarm stats...</div></div>`;

  const completed = stats.total_completed || 0;
  const failed = stats.total_failed || 0;
  const total = completed + failed;
  const successRate = total > 0 ? ((completed / total) * 100).toFixed(1) : '0.0';

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">God Mode <em>Swarm Gate</em></div>
          <div class="section-sub">Satellite scan → Parallel lanes → Script Engine → Kokoro TTS → FFmpeg 1080×1920</div>
        </div>
        <div class="topbar-actions">
          <span style=${{fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-fog)'}}>
            Lanes: ${stats.lane_count || 3} · Brain: ${stats.brain_decider_wired ? 'WIRED' : 'OFF'}
          </span>
          <button class="btn" onClick=${fireSwarm} disabled=${firing}
            style=${{padding:'8px 16px',fontSize:'10px'}}>
            ${firing ? 'FIRING...' : '⚡ FIRE SWARM'}
          </button>
        </div>
      </div>

      ${fireResult ? html`
      <div class="swarm-result" style=${{marginBottom:'16px',padding:'12px 18px',background:'var(--empire-surface)',border:'1px solid ' + (fireResult.ok ? 'var(--signal-teal-soft)' : 'var(--status-red)'),fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-silver)'}}>
        ${fireResult.ok
          ? 'Swarm fired: ' + (fireResult.count || 0) + ' jobs · ' + (fireResult.stats ? fireResult.stats.total_completed + ' completed' : '')
          : 'Error: ' + (fireResult.error || 'unknown')}
      </div>` : null}

      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">TOTAL FIRES</div>
          <div class="stat-value teal">${stats.total_fires || 0}</div>
          <div class="stat-meta">swarm fire operations</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">LANES PROCESSED</div>
          <div class="stat-value cyan">${stats.total_lanes_processed || 0}</div>
          <div class="stat-meta">total targets through pipeline</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">VIDEOS RENDERED</div>
          <div class="stat-value teal">${stats.total_videos_rendered || 0}</div>
          <div class="stat-meta">1080×1920 vertical ads</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">SUCCESS RATE</div>
          <div class=${'stat-value ' + (parseFloat(successRate) >= 70 ? 'teal' : 'dim')}>${successRate}%</div>
          <div class="stat-meta">${completed}/${total} completed</div>
        </div>
      </div>

      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">COMPLETED</div>
          <div class="stat-value teal">${completed}</div>
          <div class="stat-meta">script + audio + video</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">FAILED</div>
          <div class=${'stat-value ' + (failed > 0 ? 'bad' : 'teal')}>${failed}</div>
          <div class="stat-meta">timeouts & errors</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">SATELLITE STATUS</div>
          <div class="stat-value cyan">${((stats.satellite||{}).last_package_count || 0)}</div>
          <div class="stat-meta">last scan packages</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">SYNTH BRAIN</div>
          <div class=${'stat-value ' + (stats.synthetic_brain_wired ? 'teal' : 'dim')} style=${{fontSize:'18px'}}>
            ${stats.synthetic_brain_wired ? 'WIRED' : 'OFFLINE'}
          </div>
          <div class="stat-meta">Kokoro TTS + FFmpeg ready</div>
        </div>
      </div>

      ${jobs.length > 0 ? html`
      <div class="compliance-panel">
        <div class="compliance-h">
          <div class="compliance-title">Recent Swarm Jobs</div>
          <div class="compliance-tag">${jobs.length} jobs</div>
        </div>
        <div style=${{maxHeight:'400px',overflowY:'auto'}}>
          ${jobs.map(j => {
            const statusColor = j.status === 'complete' ? 'var(--signal-teal)' : j.status === 'failed' ? 'var(--status-red)' : 'var(--status-amber)';
            const decisionColor = j.brain_decision === 'GO' ? 'var(--signal-teal)' : 'var(--empire-mist)';
            return html`
            <div class="swarm-job-row" key=${j.id || j.target_id} style=${{display:'grid',gridTemplateColumns:'1fr 80px 60px 80px 60px 80px',gap:'10px',padding:'10px 0',borderBottom:'1px solid var(--empire-divider)',fontFamily:'var(--font-mono)',fontSize:'10px',alignItems:'center'}}>
              <span style=${{color:'var(--empire-white)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}} title=${j.warehouse_name}>${j.warehouse_name}</span>
              <span style=${{color:'var(--empire-mist)'}}>${j.metro}</span>
              <span style=${{color:decisionColor,fontWeight:500}}>${j.brain_decision || '—'}</span>
              <span style=${{color:'var(--strike-cyan)'}}>${j.strategy ? j.strategy.slice(0,10) : '—'}</span>
              <span style=${{color:statusColor,fontWeight:500}}>${j.status}</span>
              <span style=${{color:'var(--empire-fog)',fontSize:'8px'}}>${(j.created_at || '').slice(0,16)}</span>
            </div>`;
          })}
        </div>
      </div>` : html`<div class="stub" style=${{marginTop:'16px'}}><div class="stub-body">No swarm jobs yet. Click ⚡ FIRE SWARM to run a scan + render cycle.</div></div>`}
    </div>
  `;
}
// ── LIVE INBOX ─────────────────────────────────────────────────────────
function LiveInbox() {
  const [msgs, setMsgs] = useState([]);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    const reload = async () => {
      try {
        const r = await apiFetch('/api/v1/sms/inbound/recent?limit=15&minutes=1440').then(x => x.json());
        setMsgs(r.messages || []);
        setStats(r.by_intent || {});
      } catch (e) { setErr(e.message); }
    };
    reload();
    const t = setInterval(reload, 8000);
    return () => clearInterval(t);
  }, []);
  if (err) return html`<div class="stub-body">${err}</div>`;
  if (!stats) return html`<div class="stub-body">Loading inbox…</div>`;
  return html`
    <div class="live-inbox">
      <div class="inbox-bar">
        <span class="inbox-stat inbox-yes">✓ ${stats.yes || 0} YES</span>
        <span class="inbox-stat inbox-stop">⊘ ${stats.stop || 0} STOP</span>
        <span class="inbox-stat inbox-no">✗ ${stats.no || 0} NO</span>
        <span class="inbox-stat inbox-other">…${(stats.notnow || 0) + (stats.freeform || 0)} other</span>
      </div>
      ${msgs.length === 0
        ? html`<div class="inbox-empty">No inbound messages in the last 24h.</div>`
        : html`<table class="tbl"><thead><tr>
            <th>When</th><th>Phone</th><th>Body</th><th>Intent</th>
          </tr></thead><tbody>
          ${msgs.map(m => html`<tr key=${m.id}>
            <td class="tbl-mono">${String(m.created_at || '').slice(11,19)}</td>
            <td class="tbl-mono">${String(m.phone || '').slice(0,14)}</td>
            <td class="tbl-body">${m.body || ''}</td>
            <td><span class=${'inbox-intent inbox-' + m.intent}>${m.intent}</span></td>
          </tr>`)}
          </tbody></table>`}
    </div>
  `;
}


// ── PULSE SECTION ─────────────────────────────────────────────────────
function Pulse({ events, wsConnected }) {
  const [liveInboxKey, setLiveInboxKey] = useState(0);
  // Bump on inbound events to trigger LiveInbox refresh
  useEffect(() => {
    if (events && events.length > 0 && events[0].type === 'sms_inbound') setLiveInboxKey(k => k+1);
  }, [events]);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);
  const [tab, setTab] = useState('overview');
  const [pulseDim, setPulseDim] = useState('niche');
  const [pulseWindow, setPulseWindow] = useState('24h');
  const [pulseBreakdown, setPulseBreakdown] = useState(null);
  const prevHealthRef = useRef(null);

  const reload = useCallback(async () => {
    try {
      const [pb, em, sm, py, ib, pr, co, cl, rv, ac, ps, pbk, pl] = await Promise.all([
        apiFetch('/api/v1/playbook/summary').then(r => r.json()),
        apiFetch('/api/v1/email/stats').then(r => r.json()),
        apiFetch('/api/v1/sms/stats').then(r => r.json()),
        apiFetch('/api/v1/payouts/pending').then(r => r.json()),
        apiFetch('/api/v1/inbound/stats').then(r => r.json()),
        apiFetch('/api/v1/partner/all').then(r => r.json()),
        apiFetch('/api/v1/compliance/stats').then(r => r.json()),
        apiFetch('/api/v1/closer/stats').then(r => r.json()),
        apiFetch('/api/revenue/lanes').then(r => r.json()),
        apiFetch('/api/revenue/mrr').then(r => r.json()),
        apiFetch('/api/revenue/accuracy?days=14').then(r => r.json()),
        apiFetch('/api/pulse/summary?window=24h').then(r => r.json()),
        apiFetch('/api/pulse/breakdown?dimension=niche&window=7d').then(r => r.json()),
        apiFetch('/api/pulse/lanes').then(r => r.json()),
      ]);
      setStats(prev => ({ ...prev, pb, em, sm, py, ib, pr, co, cl, rv, ac, mr, ps, pbk, pl }));
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


  // ── Pulse API helper functions (defined inside Pulse for state access) ──
  const renderPulseBreakdown = () => {
    const bkd = pulseBreakdown || (stats.pbk || {});
    const groups = bkd.groups || [];
    const maxRev = groups.reduce((m, g) => Math.max(m, g.revenue || 0), 0);

    if (groups.length === 0) return html`<div class="stub" style=${{marginTop:'16px',padding:'32px 20px'}}><div class="stub-body">No breakdown data for this dimension</div></div>`;

    return html`
      <div class="pipeline-breakdown" style=${{marginTop:'16px'}}>
        <div class="pipeline-h">
          <div class="pipeline-title">Breakdown by <strong>${bkd.dimension || pulseDim}</strong></div>
          <div class="pipeline-total">${bkd.total_groups || groups.length} groups · ${(bkd.window || '7d')} window</div>
        </div>
        ${groups.map(g => {
          const barW = maxRev > 0 ? Math.max(2, Math.round((g.revenue || 0) / maxRev * 100)) : 0;
          return html`
            <div class="rv-bar-row" key=${g.key || g.label}>
              <div class="rv-bar-label">
                <span class="rv-bar-lane">${(g.label || g.key || '\u2014').slice(0, 22)}</span>
                <span class="rv-bar-niche">${(g.calls||0)} calls · ${(g.margin_pct||0).toFixed(1)}% margin</span>
              </div>
              <div class="rv-bar-track"><div class="rv-bar-fill" style=${{width: barW + '%', backgroundColor: 'var(--signal-teal)'}}></div></div>
              <div class="rv-bar-val">$${(g.revenue||0).toLocaleString()}</div>
              <div class="rv-bar-meta">${(g.spend||0) > 0 ? '$' + (g.spend||0).toLocaleString() + ' sp' : ''}</div>
            </div>
          `;
        })}
      </div>
    `;
  };

  const renderPulseHeatmap = () => {
    const lanes = stats.pl || {};
    const niches = (lanes.niches || []).slice(0, 8);
    const hours = (lanes.hours || []).slice(0, 24);

    if (niches.length === 0 || hours.length === 0) return html`<div class="stub" style=${{marginTop:'16px',padding:'32px 20px'}}><div class="stub-body">No heatmap data available</div></div>`;

    const lookup = {};
    (lanes.matrix || []).forEach(m => { lookup[m.niche + '|' + m.hour] = m; });
    const maxRev = (lanes.matrix || []).reduce((mx, m) => Math.max(mx, m.revenue || 0), 0);
    const hourLabels = hours.map(h => h.slice(11, 13));

    return html`
      <div class="pipeline-breakdown" style=${{marginTop:'16px',marginBottom:'24px'}}>
        <div class="pipeline-h">
          <div class="pipeline-title">Hourly <strong>Heatmap</strong> · 7d</div>
          <div class="pipeline-tag">${niches.length} niches × ${hours.length} hours · refresh 5min</div>
        </div>
        <div style=${{overflowX:'auto'}}>
          <table class="tbl" style=${{fontSize:'10px',whiteSpace:'nowrap'}}>
            <thead>
              <tr>
                <th style=${{minWidth:'90px'}}>Niche</th>
                ${hourLabels.map(hl => html`<th style=${{textAlign:'right',minWidth:'48px'}} key=${hl}>${hl}:00</th>`)}
              </tr>
            </thead>
            <tbody>
              ${niches.map(n => {
                const cells = hours.map(h => {
                  const m = lookup[n + '|' + h];
                  const rev = m ? (m.revenue || 0) : 0;
                  if (rev <= 0) return html`<td style=${{textAlign:'right',color:'var(--empire-fog)',opacity:0.3}} key=${h}>\u00B7</td>`;
                  const pct = rev / maxRev;
                  const bg = pct > 0.4 ? 'rgba(68,229,184,0.35)' : pct > 0.15 ? 'rgba(68,229,184,0.15)' : pct > 0.02 ? 'rgba(68,229,184,0.04)' : 'transparent';
                  const color = pct > 0.15 ? 'var(--empire-white)' : 'var(--empire-fog)';
                  const fv = rev > 0 ? '$' + rev.toLocaleString() : '\u00B7';
                  return html`<td style=${{textAlign:'right',background:bg,color:color,fontFamily:'var(--font-mono)',fontWeight:pct > 0.15 ? 500 : 400}} key=${h}>${fv}</td>`;
                });
                return html`<tr key=${n}><td style=${{fontWeight:500,color:'var(--empire-mist)',fontFamily:'var(--font-mono)',fontSize:'10px'}}>${n}</td>${cells}</tr>`;
              })}
            </tbody>
          </table>
        </div>
      </div>
    `;
  };

  const loadPulseSummary = async (w) => {
    try {
      const s = await apiFetch('/api/pulse/summary?window=' + w).then(r => r.json());
      setStats(prev => ({ ...prev, ps: s }));
    } catch(e) {}
  };

  const loadPulseBreakdown = async (window, dim) => {
    try {
      const b = await apiFetch('/api/pulse/breakdown?dimension=' + dim + '&window=' + window).then(r => r.json());
      setPulseBreakdown(b);
    } catch(e) {}
  };

  const strikes = stats.pb?.today?.strikes ?? 0;
  const brain_go = stats.pb?.today?.brain_go ?? 0;
  const seqActive = (stats.em?.sequences_active ?? 0) + (stats.sm?.sequences_active ?? 0);
  const emailsSent = stats.em?.emails_sent ?? 0;
  const smsSent = stats.sm?.sms_sent ?? 0;
  const pendingPayouts = (stats.py?.pending ?? []).length;
  const inboundCalls = stats.ib?.calls_received ?? 0;
  const inboundForwarded = stats.ib?.calls_forwarded ?? 0;

  // Partner stats from partner/all endpoint
  const allPartners = stats.pr?.partners || [];
  const activePartnersList = allPartners.filter(p => p.status === 'active' || p.status === 'ACTIVE');
  const activePartners = activePartnersList.length;
  const pendingPartners = allPartners.filter(p => p.status === 'pending_review').length;
  const totalPipelineValue = activePartnersList
    .reduce((sum, p) => sum + (parseFloat(p.base_payout) || 0), 0);
  const totalMonthlyRetainer = activePartnersList
    .reduce((sum, p) => sum + (parseFloat(p.monthly_retainer) || 0), 0);
  const totalPerCallFee = activePartnersList
    .reduce((sum, p) => sum + ((parseFloat(p.base_payout) || 0) * (parseFloat(p.fee_rate) || EMPIRE_FEE_RATE) + (parseFloat(p.per_call_fee) || 0)), 0);
  const projectedMRR = Math.round(totalMonthlyRetainer + (totalPerCallFee * 22));
  const projectedPerCallFees = Math.round(totalPerCallFee * 22);

  // ── Revenue bar chart: top 8 lanes by MRR ──
  const rvLanes = ((stats.rv||{}).lanes || []).slice(0, 8);
  const maxMRR = rvLanes.reduce((m, l) => Math.max(m, l.mrr_projected || 0), 0);

  // Pipeline breakdown content (extracted to reduce template nesting depth)
  const pipelineBreakdownHtml = activePartnersList.length > 0 ? html`
      <div class="pipeline-breakdown">
        <div class="pipeline-h">
          <div class="pipeline-title">Pipeline Breakdown</div>
          <div class="pipeline-total">${totalPipelineValue}/call · ${totalMonthlyRetainer}/mo retainers</div>
        </div>
        <div class="pipeline-grid">
          ${activePartnersList.map(p => {
            const payout = parseFloat(p.base_payout) || 0;
            const feeRate = parseFloat(p.fee_rate) || EMPIRE_FEE_RATE;
            const perCallFee = parseFloat(p.per_call_fee) || 0;
            const retainer = parseFloat(p.monthly_retainer) || 0;
            const empireFeePerCall = Math.round((payout * feeRate + perCallFee) * 100) / 100;
            const monthlyPotential = retainer + (empireFeePerCall * 22);
            const states = Array.isArray(p.state_coverage) ? p.state_coverage.join(', ') : (p.state_coverage || '—');
            return html`
              <div class="pipeline-card" onClick=${() => window.location.hash = '#/partners?focus=' + encodeURIComponent(p.id)} style=${{cursor: 'pointer'}}>
                <div class="pipeline-card-name">${p.buyer_name || '—'}</div>
                <div class="pipeline-card-detail">${p.niche || '—'} · ${states}</div>
                <div class="pipeline-card-payout">$${payout}<span class="pipeline-card-per">/call</span></div>
                <div class="pipeline-card-fees">
                  <span class="pipeline-fee-tag">$${empireFeePerCall}/call fee</span>
                  ${retainer > 0 ? html`<span class="pipeline-fee-tag retainer">$${retainer}/mo retainer</span>` : ''}
                </div>
                <div class="pipeline-card-monthly">~$${monthlyPotential}/mo projected</div>
              </div>
            `;
          })}
        </div>
      </div>
    ` : '';

  return html`
    <div>
      <div class="<${LiveInbox} />
        section-h">
        <div>
          <div class="section-title">Live <em>Pulse</em></div>
          <div class="section-sub">Real-time situational awareness</div>
        </div>
        <div class="section-sub">Auto-refresh · 30s</div>
      </div>
      <div class="pulse-tabs">
        <button class=${"pulse-tab " + (tab === 'overview' ? 'active' : '')} onClick=${() => setTab('overview')}>Overview</button>
        <button class=${"pulse-tab " + (tab === 'revenue' ? 'active' : '')} onClick=${() => setTab('revenue')}>Revenue</button>
        <button class=${"pulse-tab " + (tab === 'pipeline' ? 'active' : '')} onClick=${() => setTab('pipeline')}>Pipeline</button>
        <button class=${"pulse-tab " + (tab === 'pulse' ? 'active' : '')} onClick=${() => setTab('pulse')}>Pulse</button>
        <button class=${"pulse-tab " + (tab === 'products' ? 'active' : '')} onClick=${() => setTab('products')}>Products</button>
      </div>
      ${tab === 'overview' ? html`
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
          <div class="stat-label">Partners</div>
          <div class="stat-value teal">${activePartners}</div>
          <div class="stat-meta">${pendingPartners} pending · $${totalPipelineValue}/call · $${totalMonthlyRetainer}/mo retainers</div>
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
        <div class="stat-card">
          <div class="stat-label">Projected MRR</div>
          <div class="stat-value teal">$${projectedMRR}</div>
          <div class="stat-meta">$${totalMonthlyRetainer} retainers · $${projectedPerCallFees} per-call fees</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Actual MRR</div>
          <div class="stat-value ${(((stats.mr||{}).actual_mrr||0)) > 0 ? "teal" : "dim"}">$${((stats.mr||{}).actual_mrr||0).toLocaleString()}</div>
          <div class="stat-meta">${((stats.mr||{}).gap||0) > 0 ? ((stats.mr||{}).gap_pct||0)+"% below projected" : "meeting projection"} · ${((stats.mr||{}).buyer_subscriptions||0)} buyer subs</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Closer Pipeline</div>
          <div class="stat-value teal">${((stats.cl||{}).leads_processed || 0)}</div>
          <div class="stat-meta">leads processed</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Brain GO / NO-GO</div>
          <div class="stat-value ${((stats.cl||{}).brain_go||0) > 0 ? 'teal' : 'dim'}">${(stats.cl||{}).brain_go || 0} / ${(stats.cl||{}).brain_no_go || 0}</div>
          <div class="stat-meta">${(stats.cl||{}).brain_go + (stats.cl||{}).brain_no_go > 0 ? ((stats.cl||{}).brain_go / ((stats.cl||{}).brain_go + (stats.cl||{}).brain_no_go) * 100).toFixed(0) : 0}% GO rate</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Stream / Static Calls</div>
          <div class="stat-value cyan">${(stats.cl||{}).agi_stream_calls || 0} / ${(stats.cl||{}).static_calls || 0}</div>
          <div class="stat-meta">${(stats.cl||{}).nurture_routed || 0} nurtures · ${(stats.cl||{}).errors || 0} errors</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">24h Revenue</div>
          <div class="stat-value teal">$${((stats.rv||{}).totals||{}).revenue_24h != null ? Number(((stats.rv||{}).totals||{}).revenue_24h).toLocaleString() : '--'}</div>
          <div class="stat-meta">${((stats.rv||{}).totals||{}).active_buyers || 0} buyers · ${((stats.rv||{}).totals||{}).calls_24h || 0} calls</div>
        </div>
        <div class="stat-card" style="grid-column:span 2">
          <div class="stat-label">Revenue Health · Fleet Overview</div>
          <div style="display:flex;gap:24px;align-items:center">
            <div style="text-align:center;flex-shrink:0;min-width:70px">
              <div class="stat-value ${((stats.rv||{}).health||{}).status === 'healthy' || ((stats.rv||{}).health||{}).status === 'surging' ? 'teal' : ((stats.rv||{}).health||{}).status === 'warning' ? 'dim' : 'bad'}" style="font-size:24px;line-height:1.1">${((stats.rv||{}).health||{}).status || '--'}</div>
              <div class="stat-meta" style="font-size:9px;margin-top:2px">${((stats.rv||{}).health||{}).alerts ? ((stats.rv||{}).health||{}).alerts.length : 0} alerts</div>
            </div>
            <div style="flex:1;min-width:0">
              ${(() => {
                const h = (stats.rv||{}).health || {};
                const g = h.green || 0, a = h.amber || 0, r = h.red || 0;
                const t = g+a+r;
                var deltaStr = '';
                const prev = prevHealthRef.current;
                if (prev && t > 0) {
                  const dg = g - prev.green, da = a - prev.amber, dr = r - prev.red;
                  if (dg || da || dr) deltaStr = (dg>0?"+":"") + dg + "g " + (da>0?"+":"") + da + "a " + (dr>0?"+":"") + dr + "r";
                }
                if (t > 0) prevHealthRef.current = {green: g, amber: a, red: r};

                if (t > 0) return html`
                  <div class="cpl-health-bar" style="margin-bottom:5px">
                    ${g>0?html`<span class="cpl-health-seg cpl-health-green${healthFilter==='green'?' cpl-health-active':healthFilter?' cpl-health-dim':''}" style="flex:${g};cursor:pointer" title="${g} healthy - click to filter" onclick=${()=>setHealthFilter(healthFilter==='green'?null:'green')}>${g}</span>`:''}
                    ${a>0?html`<span class="cpl-health-seg cpl-health-amber${healthFilter==='amber'?' cpl-health-active':healthFilter?' cpl-health-dim':''}" style="flex:${a};cursor:pointer" title="${a} at-risk - click to filter" onclick=${()=>setHealthFilter(healthFilter==='amber'?null:'amber')}>${a}</span>`:''}
                    ${r>0?html`<span class="cpl-health-seg cpl-health-red${healthFilter==='red'?' cpl-health-active':healthFilter?' cpl-health-dim':''}" style="flex:${r};cursor:pointer" title="${r} critical - click to filter" onclick=${()=>setHealthFilter(healthFilter==='red'?null:'red')}>${r}</span>`:''}
                  </div>
                  <div style="display:flex;justify-content:space-between;font-family:var(--font-mono);font-size:9px;color:var(--empire-mist)">
                    <span>${g}g · ${a}a · ${r}r</span>
                    <span>${deltaStr?html`<span style="color:var(--empire-mist);margin-right:8px">${deltaStr}</span>`:''}${t} lanes</span>
                  </div>`;
                return html`<div style="font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);padding:4px 0">${h.pct_change != null ? h.pct_change + '% vs 7d avg' : ''} ${t} lanes tracked</div>`;
              })()}
            </div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Lanes Active</div>
          <div class="stat-value cyan">${((stats.rv||{}).totals||{}).lanes_active || 0}/32</div>
          <div class="stat-meta">$${((stats.rv||{}).totals||{}).mrr_projected != null ? Number(((stats.rv||{}).totals||{}).mrr_projected).toLocaleString() : '--'} MRR projected</div>
        </div>
      </div>

${(() => {
        const co = stats.co;
        if (!co) return '';
        const blockedToday = co.blocked_today || 0;
        const smsOptOuts = co.sms_opt_outs || 0;
        const outboundDnc = co.outbound_dnc || 0;
        const windowOpen = co.call_window && co.call_window.open;
        const windowLabel = co.call_window ? co.call_window.window : '—';
        const blocks = co.recent_blocks || [];
        return html`
      <div class="compliance-panel">
        <div class="compliance-h">
          <div class="compliance-title">Compliance</div>
          <div class="compliance-tag">
            <span class="compliance-window-open">
              <span class=${'compliance-window-dot ' + (windowOpen ? 'open' : 'closed')}></span>
              ${windowOpen ? 'Call window OPEN' : 'Call window CLOSED'} · ${windowLabel}
            </span>
          </div>
        </div>
        <div class="compliance-grid">
          <div class="compliance-card">
            <div class="compliance-card-label">Blocks Today</div>
            <div class=${'compliance-card-value ' + (blockedToday > 0 ? 'bad' : 'ok')}>${blockedToday}</div>
            <div class="compliance-card-meta">outbound calls stopped</div>
          </div>
          <div class="compliance-card">
            <div class="compliance-card-label">SMS Opt-Outs</div>
            <div class=${'compliance-card-value ' + (smsOptOuts > 0 ? 'warn' : 'ok')}>${smsOptOuts}</div>
            <div class="compliance-card-meta">STOP keyword entries</div>
          </div>
          <div class="compliance-card">
            <div class="compliance-card-label">DNC List</div>
            <div class="compliance-card-value dim">${outboundDnc}</div>
            <div class="compliance-card-meta">manual blocks</div>
          </div>
          <div class="compliance-card">
            <div class="compliance-card-label">Total DNC</div>
            <div class="compliance-card-value dim">${smsOptOuts + outboundDnc}</div>
            <div class="compliance-card-meta">combined protection</div>
          </div>
        </div>
        <div class="panel-head" style=${{fontSize: '10px', marginBottom: '8px'}}>Recent blocks</div>
        ${blocks.length === 0
          ? html`<div class="compliance-empty">No blocked calls today.</div>`
          : html`<div class="compliance-blocks">
            ${blocks.map(b => {
              let ruleCls = 'hours';
              if (b.rule === 'dnc_opt_out') ruleCls = 'dnc';
              else if (b.rule === 'invalid_phone') ruleCls = 'format';
              else if (b.rule === 'outside_call_hours') ruleCls = 'hours';
              return html`
              <div class="compliance-block-row">
                <span class="compliance-block-ts">${b.ts ? b.ts.slice(11, 19) : '—'}</span>
                <span class=${'compliance-block-rule ' + ruleCls}>${b.rule || '—'}</span>
                <span class="compliance-block-phone">${b.phone || '—'}</span>
              </div>
            `})}
          </div>`}
      </div>
      `; })()}

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
      ` : null}

      ${tab === 'revenue' ? html`
      ${rvLanes.length > 0 ? html`
      <div class="pipeline-breakdown">
        <div class="pipeline-h">
          <div class="pipeline-title">Revenue · Top Lanes</div>
          <div class="pipeline-total">$${maxMRR.toLocaleString()} peak MRR</div>
        </div>
        <div class="pipeline-grid" style="grid-template-columns:1fr">
          ${rvLanes.map(l => {
            const barW = maxMRR > 0 ? Math.max(2, Math.round((l.mrr_projected / maxMRR) * 100)) : 0;
            const barColor = (l.mrr_projected || 0) > 500 ? 'var(--signal-teal)' : (l.mrr_projected || 0) > 100 ? 'var(--strike-cyan)' : 'var(--empire-mist)';
            return html`<div class="rv-bar-row" key=${l.lane_id}>
              <div class="rv-bar-label">
                <span class="rv-bar-lane">L${l.lane_id}</span>
                <span class="rv-bar-niche">${(l.niche || '').slice(0, 18)}</span>
              </div>
              <div class="rv-bar-track">
                <div class="rv-bar-fill" style=${{width: barW + '%', backgroundColor: barColor}}></div>
              </div>
              <div class="rv-bar-val">$${(l.mrr_projected || 0).toLocaleString()}</div>
              <div class="rv-bar-meta">${l.calls_24h || 0}c · ${l.active_buyers || 0}b</div>
            </div>`;
          })}
        </div>
      </div>
      ` : null}

      ${(stats.ac||{}).series ? html`
      <div class="rv-accuracy-panel">
        <div class="rv-accuracy-head">
          <div class="rv-accuracy-title">Forecast · Actual</div>
          <div class="rv-accuracy-summary">
            ${(() => {
              const ser = (stats.ac||{}).series || [];
              const last14 = ser.slice(0, 14);
              const avgAcc = last14.length > 0 ? Math.round(last14.reduce((s, d) => s + (d.accuracy_pct || 0), 0) / last14.length) : 0;
              const accColor = avgAcc >= 80 ? 'var(--signal-teal)' : avgAcc >= 50 ? 'var(--status-amber)' : 'var(--status-red)';
              return html`<span style=${{color: accColor}}>${avgAcc}% avg accuracy</span> · ${last14.length}d`;
            })()}
          </div>
        </div>
        </div>
        <div class="rv-accuracy-chart">
          ${(() => {
            const ser = (stats.ac||{}).series || [];
            const last14 = ser.slice(0, 14).reverse();
            const maxVal = last14.reduce((m, d) => Math.max(m, d.forecasted_fee || 0, d.actual_revenue || 0), 0);
            return last14.map(d => {
              const forecastW = maxVal > 0 ? Math.max(2, Math.round((d.forecasted_fee / maxVal) * 100)) : 0;
              const actualW = maxVal > 0 ? Math.max(2, Math.round((d.actual_revenue / maxVal) * 100)) : 0;
              const accColor = d.accuracy_pct >= 80 ? 'var(--signal-teal)' : d.accuracy_pct >= 50 ? 'var(--status-amber)' : 'var(--status-red)';
              const dateLabel = (d.date || '').slice(5);
              return html`<div class="rv-acc-row" key=${d.date}>
                <div class="rv-acc-date">${dateLabel}</div>
                <div class="rv-acc-bars">
                  <div class="rv-acc-bar-wrap">
                    <div class="rv-acc-bar forecast" style=${{width: forecastW + '%'}}></div>
                    <span class="rv-acc-bar-label">$${(d.forecasted_fee || 0).toLocaleString()} fcst</span>
                  </div>
                  <div class="rv-acc-bar-wrap">
                    <div class="rv-acc-bar actual" style=${{width: actualW + '%'}}></div>
                    <span class="rv-acc-bar-label">$${(d.actual_revenue || 0).toLocaleString()} actual</span>
                  </div>
                </div>
                <div class="rv-acc-pct" style=${{color: accColor}}>
                  ${d.accuracy_pct != null ? d.accuracy_pct + '%' : '—'}
                </div>
              </div>`;
            });
          })()}
        </div>
        <div class="rv-accuracy-legend">
          <div class="rv-acc-legend-item"><span class="rv-acc-legend-swatch forecast"></span> Forecast</div>
          <div class="rv-acc-legend-item"><span class="rv-acc-legend-swatch actual"></span> Actual</div>
          <div class="rv-acc-legend-item"><span style="color:var(--signal-teal)">≥80%</span> <span style="color:var(--status-amber)">50–79%</span> <span style="color:var(--status-red)"><50%</span></div>
        </div>
      </div>
      ` : null}
      ` : null}

      ${tab === 'pulse' ? html`
      <div>
        <div class="section-h" style=${{marginTop:'8px'}}>
          <div>
            <div class="section-title">API <em>Pulse</em></div>
            <div class="section-sub">Materialized view · 5-min refresh · ${((stats.ps||{}).window || '24h')} window</div>
          </div>
          <div class="topbar-actions">
            ${['24h','7d','30d'].map(w => html`
              <button class=${"pulse-tab " + (pulseWindow === w ? 'active' : '')} style=${{fontSize:'9px',padding:'4px 10px'}} onClick=${() => { setPulseWindow(w); loadPulseSummary(w); loadPulseBreakdown(w, pulseDim); }}>${w}</button>
            `)}
          </div>
        </div>

        <div class="pulse-grid">
          <div class="stat-card">
            <div class="stat-label">REVENUE</div>
            <div class="stat-value teal">$${((stats.ps||{}).revenue||0).toLocaleString()}</div>
            <div class="stat-meta" style=${{color: ((stats.ps||{}).delta_revenue||0) >= 0 ? 'var(--signal-teal)' : 'var(--status-red)'}}>${((stats.ps||{}).delta_revenue||0) >= 0 ? '▲' : '▼'} $${Math.abs((stats.ps||{}).delta_revenue||0).toLocaleString()} vs prev</div>
          </div>

          <div class="stat-card">
            <div class="stat-label">SPEND</div>
            <div class="stat-value dim">$${((stats.ps||{}).spend||0).toLocaleString()}</div>
            <div class="stat-meta" style=${{color: ((stats.ps||{}).delta_spend||0) <= 0 ? 'var(--signal-teal)' : 'var(--status-red)'}}>${((stats.ps||{}).delta_spend||0) <= 0 ? '▼' : '▲'} $${Math.abs((stats.ps||{}).delta_spend||0).toLocaleString()} vs prev</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">MARGIN</div>
            <div class="stat-value teal">${((stats.ps||{}).margin_pct||0).toFixed(1)}%</div>
            <div class="stat-meta">$${((stats.ps||{}).margin||0).toLocaleString()} net</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">CALLS</div>
            <div class="stat-value cyan">${((stats.ps||{}).calls||0).toLocaleString()}</div>
            <div class="stat-meta" style=${{color: ((stats.ps||{}).delta_calls||0) >= 0 ? 'var(--signal-teal)' : 'var(--status-red)'}}>${((stats.ps||{}).delta_calls||0) >= 0 ? '▲' : '▼'} ${Math.abs((stats.ps||{}).delta_calls||0)} vs prev</div>
          </div>
        </div>

        <div class="pulse-tabs" style=${{marginTop:'8px'}}>
          ${['niche','channel','contractor','corridor','hour'].map(d => html`
            <button class=${"pulse-tab " + (pulseDim === d ? 'active' : '')} style=${{fontSize:'10px',padding:'6px 14px'}} onClick=${() => { setPulseDim(d); loadPulseBreakdown(pulseWindow, d); }}>${d}</button>
          `)}
        </div>

        ${renderPulseBreakdown()}

        ${renderPulseHeatmap()}
      </div>
      ` : null}

            ${tab === 'pipeline' ? html`
      ${pipelineBreakdownHtml}
      ` : null}

      ${tab === 'products' ? html`<${ProductsPanel} />` : null}

      
  `;
}


function ProductsPanel() {
  const [suite, setSuite] = useState(null);
  const [packs, setPacks] = useState(null);
  const [subTier, setSubTier] = useState(null); // {tier, name, price, slug} or null
  const [subAcct, setSubAcct] = useState('');
  const [subBusy, setSubBusy] = useState(false);
  const [subMsg, setSubMsg] = useState(null);
  // Crypto USDC payment state
  const [cryptoProduct, setCryptoProduct] = useState(null); // {tier, name, price}
  const [cryptoEmail, setCryptoEmail] = useState('');
  const [cryptoAcct, setCryptoAcct] = useState('');
  const [cryptoResult, setCryptoResult] = useState(null); // API response with memo, wallet, etc.
  const [cryptoBusy, setCryptoBusy] = useState(false);
  const [cryptoError, setCryptoError] = useState(null);
  const pollInterval = useRef(null);  // cleared when modal closes

  useEffect(() => {
    fetch('/api/v1/products/catalog').then(r=>r.json()).then(d => {
      setSuite(d.suite_products || []);
      setPacks(d.strike_packs || []);
    }).catch(() => {});
  }, []);

  async function doSubscribe(tierObj) {
    if (!subAcct.trim()) return setSubMsg('Please enter a customer account ID');
    setSubBusy(true);
    setSubMsg(null);
    try {
      const r = await fetch('/api/v1/products/subscribe', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ customer_account_id: subAcct.trim(), tier_level: tierObj.tier })
      });
      const j = await r.json();
      if (r.ok) { setSubMsg('✅ Subscribed!'); setSubTier(null); }
      else { setSubMsg('❌ ' + (j.detail || j.error || 'Error')); }
    } catch(e) { setSubMsg('❌ Network error'); }
    setSubBusy(false);
  }

  async function doCryptoPay(product) {
    const email = cryptoEmail.trim();
    const acct = cryptoAcct.trim() || email;
    if (!email || !email.includes('@')) return setCryptoError('Please enter a valid email address');
    setCryptoBusy(true);
    setCryptoError(null);
    setCryptoResult(null);
    try {
      const r = await fetch('/api/v1/crypto/pay', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ customer_email: email, customer_account_id: acct, tier_level: product.tier })
      });
      const j = await r.json();
      if (j.ok) {
        setCryptoResult(j);
        // Start polling (clear any previous interval first)
        const pid = j.payment_id;
        if (pollInterval.current) clearInterval(pollInterval.current);
        pollInterval.current = setInterval(async () => {
          try {
            const sr = await fetch('/api/v1/crypto/pay/' + pid);
            const sd = await sr.json();
            if (sd.status === 'completed' || sd.status === 'activation_pending') {
              setCryptoResult(prev => ({...prev, status: sd.status}));
              if (sd.status === 'completed') clearInterval(pollInterval.current);
            }
            if (sd.status === 'expired' || sd.status === 'activation_failed') {
              setCryptoResult(prev => ({...prev, status: sd.status}));
              clearInterval(pollInterval.current);
            }
          } catch(_) {}
        }, 10000);
      } else {
        setCryptoError(j.error || 'Failed to create payment request');
      }
    } catch(e) { setCryptoError('Network error: ' + (e?.message || String(e))); }
    setCryptoBusy(false);
  }

  return html`
    <div style=${{padding:'0 24px',color:'var(--foreground)'}}>
      <h3 style=${{fontFamily:'var(--font-mono)',fontWeight:300,fontSize:'24px',margin:'12 0 8 0',color:'var(--strike-cyan)'}}>Suite Products</h3>
      <p style=${{fontSize:'12px',color:'var(--foreground-muted)',margin:'0 0 16 0'}}>
        Subscribe to any tier directly from here. Prices are pulled from the product_metadata table.
      </p>
      ${suite ? suite.map(p => html`
        <div style=${{display:'flex',alignItems:'center',gap:'12px',padding:'8px 12px',margin:'4px 0',border:'1px solid var(--empire-border)',borderRadius:'6px',background:'var(--empire-surface)'}}>
          <div style=${{flex:1}}>
            <div style=${{fontWeight:600,fontSize:'13px'}}>${p.display_name||p.tier}</div>
            <div style=${{fontSize:'11px',color:'var(--foreground-muted)'}}>${p.description || ''}</div>
          </div>
          <div style=${{fontSize:'15px',fontWeight:700,color:'var(--signal-teal)'}}>\$${p.monthly_price_usd?.toFixed(0)}/mo</div>
          <button style=${{padding:'6px 16px',border:'1px solid var(--signal-teal)',background:'transparent',color:'var(--signal-teal)',borderRadius:'4px',cursor:'pointer',fontFamily:'var(--font-mono)',fontSize:'11px',textTransform:'uppercase',letterSpacing:'0.1em'}}
            onClick=${() => { setSubTier({tier:p.tier, name:p.display_name, price:p.monthly_price_usd}); setSubAcct(''); setSubMsg(null); }}
            onmouseover=${e => {e.target.style.background='var(--signal-teal)';e.target.style.color='var(--empire-black)'}}
            onmouseout=${e => {e.target.style.background='transparent';e.target.style.color='var(--signal-teal)'}}>Subscribe</button>
          <button style=${{marginLeft:'8px',padding:'6px 10px',border:'1px solid var(--strike-cyan)',background:'transparent',color:'var(--strike-cyan)',borderRadius:'4px',cursor:'pointer',fontFamily:'var(--font-mono)',fontSize:'10px',textTransform:'uppercase',letterSpacing:'0.1em'}}
            onClick=${() => { setCryptoProduct({tier:p.tier, name:p.display_name, price:p.monthly_price_usd}); setCryptoEmail(''); setCryptoAcct(''); setCryptoResult(null); setCryptoError(null); }}
            onmouseover=${e => {e.target.style.background='var(--strike-cyan)';e.target.style.color='var(--empire-black)'}}
            onmouseout=${e => {e.target.style.background='transparent';e.target.style.color='var(--strike-cyan)'}}>USDC</button>
      `) : html`<div style=${{fontSize:'11px',color:'var(--foreground-muted)',padding:'12px'}}>Loading products…</div>`}
      ${!packs ? null : html`
        <h3 style=${{fontFamily:'var(--font-mono)',fontWeight:300,fontSize:'24px',margin:'24 0 8 0',color:'var(--strike-cyan)'}}>Strike Packs</h3>
        <p style=${{fontSize:'12px',color:'var(--foreground-muted)',margin:'0 0 16 0'}}>
          Per-lead products by niche.
        </p>
        ${packs.map(s => html`
          <div style=${{display:'flex',alignItems:'center',gap:'12px',padding:'8px 12px',margin:'4px 0',border:'1px solid var(--empire-border)',borderRadius:'6px',background:'var(--empire-surface)'}}>
            <div style=${{flex:1,fontWeight:600,fontSize:'13px'}}>${s.slug}</div>
            <div style=${{fontSize:'11px',color:'var(--foreground-muted)'}}>tier ${s.tier}</div>
            <div style=${{fontSize:'15px',fontWeight:700,color:'var(--signal-teal)'}}>\$${s.monthly_price_usd?.toFixed(0)}/mo</div>
          </div>
        `)}
      `}
    </div>

    <!-- Subscribe modal overlay -->
    ${!subTier ? null : html`
      <div style=${{position:'fixed',inset:0,background:'rgba(0,0,0,0.6)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:9999}} onClick=${e => {if(e.target===e.currentTarget) setSubTier(null)}}>
        <div style=${{background:'var(--empire-surface)',border:'1px solid var(--empire-border)',borderRadius:'12px',padding:'24px',maxWidth:'420px',width:'90%',color:'var(--foreground)'}}>
          <div style=${{fontSize:'16px',fontWeight:600,margin:'0 0 4 0'}}>Subscribe to ${subTier.name || subTier.tier}</div>
          <div style=${{fontSize:'12px',color:'var(--foreground-muted)',margin:'0 0 16 0'}}>
            ${subTier.tier} · \$${subTier.price?.toFixed(2) ?? '—'}/mo
          </div>
          <input style=${{width:'100%',padding:'10px 12px',margin:'0 0 12 0',background:'var(--empire-black)',border:'1px solid var(--empire-border)',borderRadius:'6px',color:'var(--foreground)',fontSize:'13px',fontFamily:'var(--font-mono)',outline:'none',boxSizing:'border-box'}}
            placeholder="Customer account ID"
            value=${subAcct}
            onInput=${e => setSubAcct(e.target.value)}
            disabled=${subBusy} />
          ${!subMsg ? null : html`<div style=${{fontSize:'11px',margin:'0 0 12 0',color: subMsg.startsWith('✅') ? 'var(--strike-cyan)' : 'var(--signal-orange)'}}>${subMsg}</div>`}
          <div style=${{display:'flex',gap:'8px',justifyContent:'flex-end'}}>
            <button style=${{padding:'8px 20px',background:'transparent',border:'1px solid var(--empire-border)',color:'var(--foreground-muted)',borderRadius:'6px',cursor:'pointer',fontSize:'11px',fontFamily:'var(--font-mono)',textTransform:'uppercase'}}
              onClick=${() => setSubTier(null)} disabled=${subBusy}>Cancel</button>
            <button style=${{padding:'8px 20px',background:'var(--signal-teal)',border:'none',color:'var(--empire-black)',borderRadius:'6px',cursor:'pointer',fontSize:'11px',fontFamily:'var(--font-mono)',textTransform:'uppercase',fontWeight:600}}
              onClick=${() => doSubscribe(subTier)} disabled=${subBusy}>${subBusy ? 'Subscribing…' : 'Confirm'}</button>
          </div>
        </div>
      </div>
    `}

    // Crypto USDC Pay modal overlay
    ${!cryptoProduct ? null : html`
      <div style=${{position:'fixed',inset:0,background:'rgba(0,0,0,0.6)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:9999}} onClick=${e => {if(e.target===e.currentTarget) { if (pollInterval.current) { clearInterval(pollInterval.current); pollInterval.current = null; } setCryptoProduct(null); }}}}}>
        <div style=${{background:'var(--empire-surface)',border:'1px solid var(--empire-border)',borderRadius:'12px',padding:'24px',maxWidth:'480px',width:'90%',color:'var(--foreground)',maxHeight:'90vh',overflowY:'auto'}}>
          <div style=${{fontSize:'16px',fontWeight:600,margin:'0 0 4 0'}}>Pay with USDC for ${cryptoProduct.name || cryptoProduct.tier}</div>
          <div style=${{fontSize:'12px',color:'var(--foreground-muted)',margin:'0 0 16 0'}}>
            ${cryptoProduct.tier} &middot; $${cryptoProduct.price?.toFixed(2) ?? '—'}/mo
          </div>
          ${!cryptoResult ? html`
            <!-- Step 1: Email + Account form -->
            <input style=${{width:'100%',padding:'10px 12px',margin:'0 0 10 0',background:'var(--empire-black)',border:'1px solid var(--empire-border)',borderRadius:'6px',color:'var(--foreground)',fontSize:'13px',fontFamily:'var(--font-mono)',outline:'none',boxSizing:'border-box'}}
              placeholder="Your email address"
              value=${cryptoEmail}
              onInput=${e => setCryptoEmail(e.target.value)}
              disabled=${cryptoBusy} />
            <input style=${{width:'100%',padding:'10px 12px',margin:'0 0 10 0',background:'var(--empire-black)',border:'1px solid var(--empire-border)',borderRadius:'6px',color:'var(--foreground)',fontSize:'13px',fontFamily:'var(--font-mono)',outline:'none',boxSizing:'border-box'}}
              placeholder="Account ID (optional, defaults to email)"
              value=${cryptoAcct}
              onInput=${e => setCryptoAcct(e.target.value)}
              disabled=${cryptoBusy} />
            ${!cryptoError ? null : html`<div style=${{fontSize:'11px',color:'var(--signal-orange)',margin:'0 0 10 0'}}>${cryptoError}</div>`}
            <div style=${{display:'flex',gap:'8px',justifyContent:'flex-end'}}>
              <button style=${{padding:'8px 20px',background:'transparent',border:'1px solid var(--empire-border)',color:'var(--foreground-muted)',borderRadius:'6px',cursor:'pointer',fontSize:'11px',fontFamily:'var(--font-mono)',textTransform:'uppercase'}}
                onClick=${() => { if (pollInterval.current) { clearInterval(pollInterval.current); pollInterval.current = null; } setCryptoProduct(null); }} disabled=${cryptoBusy}>Cancel</button>
              <button style=${{padding:'8px 20px',background:'var(--strike-cyan)',border:'none',color:'var(--empire-black)',borderRadius:'6px',cursor:'pointer',fontSize:'11px',fontFamily:'var(--font-mono)',textTransform:'uppercase',fontWeight:600}}
                onClick=${() => doCryptoPay(cryptoProduct)} disabled=${cryptoBusy}>${cryptoBusy ? 'Creating…' : 'Create Payment'}</button>
            </div>
          ` : html`
            <!-- Step 2: Payment details with memo -->
            <div style=${{marginBottom:'14px'}}>
              <div style=${{fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-mist)',letterSpacing:'0.14em',textTransform:'uppercase',marginBottom:'4px'}}>Amount</div>
              <div style=${{fontFamily:'var(--font-mono)',fontSize:'22px',color:'var(--signal-teal)',fontWeight:600}}>$${cryptoResult.amount_usdc.toFixed(2)} USDC</div>
            </div>
            <div style=${{marginBottom:'14px'}}>
              <div style=${{fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-mist)',letterSpacing:'0.14em',textTransform:'uppercase',marginBottom:'4px'}}>Vault Wallet</div>
              <div style=${{fontFamily:'var(--font-mono)',fontSize:'11px',color:'var(--foreground)',wordBreak:'break-all',background:'var(--empire-black)',padding:'10px 12px',border:'1px solid var(--empire-border)',borderRadius:'6px'}}>${cryptoResult.vault_wallet}</div>
            </div>
            <div style=${{marginBottom:'14px'}}>
              <div style=${{fontFamily:'var(--font-mono)',fontSize:'10px',color:'#FFB800',letterSpacing:'0.18em',textTransform:'uppercase',marginBottom:'4px',fontWeight:600}}>Memo (include in transaction)</div>
              <div style=${{fontFamily:'var(--font-mono)',fontSize:'16px',color:'#FFB800',wordBreak:'break-all',background:'var(--empire-black)',padding:'12px 14px',border:'2px solid #FFB800',borderRadius:'6px',textAlign:'center',letterSpacing:'0.12em'}}>${cryptoResult.memo}</div>
            </div>
            <div style=${{fontSize:'11px',color:'var(--foreground-muted)',lineHeight:'1.6',marginBottom:'14px'}}>
              Send exactly <strong style=${{color:'var(--signal-teal)'}}>$${cryptoResult.amount_usdc.toFixed(2)} USDC</strong> on Solana to the wallet above.
              <strong style=${{color:'#FFB800'}}>Include the memo</strong> to identify your payment.
            </div>
            ${(cryptoResult.status === 'activation_pending' || cryptoResult.status === 'completed') ? html`
              <div style=${{fontSize:'13px',color: cryptoResult.status === 'completed' ? 'var(--signal-teal)' : 'var(--status-amber)',padding:'10px 12px',background:'var(--empire-black)',borderRadius:'6px',marginBottom:'14px',textAlign:'center'}}>
                ${cryptoResult.status === 'completed' ? 'Payment confirmed! Subscription active.' : 'Payment received! Activating subscription...'}
              </div>
            ` : cryptoResult.status === 'activation_failed' ? html`
              <div style=${{fontSize:'13px',color:'var(--status-red)',padding:'10px 12px',background:'var(--empire-black)',borderRadius:'6px',marginBottom:'14px',textAlign:'center'}}>
                Payment received but activation failed. Our team has been notified.
              </div>
            ` : null}
            <div style=${{display:'flex',gap:'8px',justifyContent:'flex-end'}}>
              <a href=${'/crypto/pay/' + cryptoResult.payment_id} target="_blank" style=${{padding:'8px 20px',background:'transparent',border:'1px solid var(--empire-border)',color:'var(--foreground-muted)',borderRadius:'6px',cursor:'pointer',fontSize:'11px',fontFamily:'var(--font-mono)',textTransform:'uppercase',textDecoration:'none'}}>Status Page</a>
              <button style=${{padding:'8px 20px',background:'transparent',border:'1px solid var(--empire-border)',color:'var(--foreground-muted)',borderRadius:'6px',cursor:'pointer',fontSize:'11px',fontFamily:'var(--font-mono)',textTransform:'uppercase'}}
                onClick=${() => { if (pollInterval.current) { clearInterval(pollInterval.current); pollInterval.current = null; } setCryptoProduct(null); }}>Close</button>
            </div>
          `}
        </div>
      </div>
    `}
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

  // ── Pipeline stage counts (email + SMS combined) ──
  const seqActive = (d.em?.sequences_active ?? 0) + (d.sm?.sequences_active ?? 0);
  const totalSent = (d.em?.emails_sent ?? 0) + (d.sm?.sms_sent ?? 0);
  const totalReplied = (d.em?.replies ?? 0) + (d.sm?.replies ?? 0);
  const totalUnsub = (d.em?.unsubscribes ?? 0) + (d.sm?.opt_outs ?? 0);
  const totalConverted = Math.round(totalReplied * 0.28); // rough: ~28% of replies convert
  const convRate = totalSent > 0 ? Math.round((totalReplied / totalSent) * 100) : 0;

  // Pipeline stages for the orbital ring (5 stages, clockwise from top)
  const stages = [
    { id: 'new',      icon: '●', label: 'Active',   count: seqActive,       cls: '' },
    { id: 'sent',     icon: '→', label: 'Sent',     count: totalSent,       cls: 'sent' },
    { id: 'replied',  icon: '↩', label: 'Replied',  count: totalReplied,    cls: 'replied' },
    { id: 'unsub',    icon: '✕', label: 'Unsub',    count: totalUnsub,      cls: '' },
    { id: 'converted',icon: '★', label: 'Converted',count: totalConverted,   cls: 'converted' },
  ];

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Pipeline <em>Orbital</em></div>
          <div class="section-sub">Email & SMS · 5-stage lifecycle</div>
        </div>
        <div class="section-sub">${seqActive} active · ${totalSent} sent · ${convRate}% reply rate</div>
      </div>

      <!-- ── 5-Stage Orbital Ring ── -->
      <div class="pipe-orbital-wrapper">
        ${(() => {
          const orbitR = 170;
          const outerR = 220;
          const innerR = 110;
          const svgW = outerR * 2 + 16;
          const svgH = outerR * 2 + 16;
          
          // SVG rings and lines
          const svgLines = stages.map((s, i) => {
            const angleDeg = i * (360 / stages.length) - 90;
            const angleRad = angleDeg * Math.PI / 180;
            const ax = Math.cos(angleRad) * orbitR;
            const ay = Math.sin(angleRad) * orbitR;
            const isActive = s.count > 0;
            return html`<line 
              x1="0" y1="0" 
              x2="${ax.toFixed(1)}" y2="${ay.toFixed(1)}" 
              class=${'pipe-orbit-line' + (isActive ? ' active' : '')}
              style=${{animationDelay: (i * 0.12) + 's'}}
            />`;
          });

          // Direction arrows between stages
          const arrows = stages.map((s, i) => {
            const nextI = (i + 1) % stages.length;
            const a1 = (i * (360 / stages.length) - 90) * Math.PI / 180;
            const a2 = (nextI * (360 / stages.length) - 90) * Math.PI / 180;
            const midR = orbitR;
            const x1 = Math.cos(a1) * midR * 0.82;
            const y1 = Math.sin(a1) * midR * 0.82;
            const x2 = Math.cos(a2) * midR * 0.82;
            const y2 = Math.sin(a2) * midR * 0.82;
            const mx = (x1 + x2) / 2;
            const my = (y1 + y2) / 2;
            const dx = x2 - x1;
            const dy = y2 - y1;
            const len = Math.sqrt(dx*dx + dy*dy);
            const ux = dx / len;
            const uy = dy / len;
            // Arrowhead triangle
            const tipX = x2;
            const tipY = y2;
            const baseX = tipX - ux * 10;
            const baseY = tipY - uy * 10;
            const wing = 5;
            const px = -uy * wing;
            const py = ux * wing;
            const points = `${tipX.toFixed(1)},${tipY.toFixed(1)} ${(baseX+px).toFixed(1)},${(baseY+py).toFixed(1)} ${(baseX-px).toFixed(1)},${(baseY-py).toFixed(1)}`;
            return html`<polygon class="pipe-orbit-arrow" points="${points}" style=${{animationDelay: (i * 0.2) + 's'}} />`;
          });
          
          return html`
            <svg class="pipe-orbital-svg" width="${svgW}" height="${svgH}" viewBox="${-svgW/2} ${-svgH/2} ${svgW} ${svgH}">
              <circle cx="0" cy="0" r="${outerR}" class="pipe-orbit-ring outer"/>
              <circle cx="0" cy="0" r="${orbitR}" class="pipe-orbit-ring pulse"/>
              <circle cx="0" cy="0" r="${innerR}" class="pipe-orbit-ring"/>
              ${svgLines}
              ${arrows}
            </svg>
            
            <!-- Boss card: conversion rate -->
            <div class="pipe-boss-card">
              <span class="pipe-boss-label">Reply Rate</span>
              <span class="pipe-boss-rate">${convRate}%</span>
              <span class="pipe-boss-sub">${totalReplied}/${totalSent}</span>
            </div>
            
            <!-- 5 stage nodes -->
            ${stages.map((s, i) => {
              const angleDeg = i * (360 / stages.length) - 90;
              const angleRad = angleDeg * Math.PI / 180;
              const ax = Math.cos(angleRad) * orbitR;
              const ay = Math.sin(angleRad) * orbitR;
              return html`
                <div class=${'pipe-stage-node' + (s.cls ? ' ' + s.cls : '')}
                     style=${{transform: 'translate(-50%,-50%) translate(' + ax.toFixed(1) + 'px,' + ay.toFixed(1) + 'px)', animationDelay: (i * 0.08) + 's'}}>
                  <span class="pipe-stage-icon">${s.icon}</span>
                  <span class="pipe-stage-count">${s.count}</span>
                  <span class="pipe-stage-label">${s.label}</span>
                </div>
              `;
            })}
          `;
        })()}
      </div>

      <!-- ── Engine panels below orbital ── -->
      <div class="split" style=${{marginTop: '8px'}}>
        <div class="panel">
          <div class="panel-head">Email Engine</div>
          <div class="sec-meta">Active: <strong>${d.em?.sequences_active ?? 0}</strong> · Sent: <strong>${d.em?.emails_sent ?? 0}</strong> · Replies: <strong>${d.em?.replies ?? 0}</strong> · Unsubs: <strong>${d.em?.unsubscribes ?? 0}</strong></div>
        </div>
        <div class="panel">
          <div class="panel-head">SMS Engine</div>
          <div class="sec-meta">Active: <strong>${d.sm?.sequences_active ?? 0}</strong> · Sent: <strong>${d.sm?.sms_sent ?? 0}</strong> · Replies: <strong>${d.sm?.replies ?? 0}</strong> · Opt-outs: <strong>${d.sm?.opt_outs ?? 0}</strong></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head">Engine status</div>
        <div class="sec-meta">Email dispatcher: <strong>every 5s</strong> · limit 12/min · SMS dispatcher: <strong>every 5s</strong> · limit 6/min</div>
      </div>
    </div>
  `;
}

// ── DISPATCH ──────────────────────────────────────────────────────────
function Dispatch() {
  const [board, setBoard] = useState(null);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);
  const [genomeHistory, setGenomeHistory] = useState(null);
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

// ── DISPATCHES (mark-settled) ──────────────────────────────────────────
function Dispatches() {
  const [list, setList] = useState(null);
  const [err, setErr] = useState(null);
  const [settling, setSettling] = useState(null);
  const [busy, setBusy] = useState(null);

  // SettleForm state
  const [showForm, setShowForm] = useState(null);
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');

  const reload = async () => {
    try {
      const r = await apiFetch('/api/v1/matching/dispatches?limit=50').then(x => x.json());
      setList(r.dispatches || []);
    } catch (e) { setErr(e.message); }
  };
  useEffect(() => { reload(); }, []);

  const submitSettle = async (dispatch_id) => {
    if (!amount || parseFloat(amount) <= 0) {
      alert('Enter a positive claim amount');
      return;
    }
    setBusy(dispatch_id);
    try {
      const r = await apiFetch('/api/v1/claims/mark-settled', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dispatch_id, claim_amount: parseFloat(amount), meta: { notes } }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        alert('Failed: ' + (e.detail || e.error || r.status));
      } else {
        setShowForm(null);
        setAmount('');
        setNotes('');
        await reload();
      }
    } catch (e) { alert('Network error: ' + e.message); }
    setBusy(null);
  };

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!list) return html`<div class="stub"><div class="stub-body">Loading dispatches…</div></div>`;

  const fmtUsd = (n) => '$' + Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Dispatches</div><div class="section-sub">Lead → contractor match log · mark claims settled</div></div><div class="sec-actions"><button class="tbl-action go" onClick=${reload}>↻ Refresh</button></div></div>
      <div class="panel">
        <div class="panel-head">Recent dispatches</div>
        ${list.length === 0
          ? html`<div class="tbl-empty">No dispatches yet. When a lead replies YES to a storm_strike SMS, the dispatch agent routes it to contractors in the metro. See the Fees section for settled claims.</div>`
          : html`<table class="tbl"><thead><tr>
                <th>When</th><th>Lead</th><th>Contractor</th><th class="tbl-num">Match</th><th>Status</th><th class="tbl-num">Payout</th><th>Actions</th>
              </tr></thead><tbody>
              ${list.map(d => html`<tr key=${d.id}>
                <td class="tbl-mono">${String(d.created_at || '').slice(0,16).replace('T',' ')}</td>
                <td class="tbl-mono">${String(d.lead_id || '').slice(0,8)}</td>
                <td class="tbl-mono">${String(d.contractor_id || '').slice(0,8)}</td>
                <td class="tbl-num">${d.match_score ?? '—'}</td>
                <td><span class=${'dispatch-status ' + (d.status || 'sent')}>${d.status || 'sent'}</span></td>
                <td class="tbl-num">${d.payout_amount ? fmtUsd(d.payout_amount) : '—'}</td>
                <td>
                  ${d.meta && d.meta.settled
                    ? html`<span class="settled-badge">Settled $${d.meta.claim_amount ? fmtUsd(d.meta.claim_amount) : ''}</span>`
                    : html`<button class="tbl-action go" disabled=${busy === d.id} onClick=${() => setShowForm(d.id)}>${busy === d.id ? 'Settling…' : 'Mark Settled'}</button>`}
                </td>
              </tr>`)}
              </tbody></table>`}
      </div>
      ${showForm ? html`
        <div class="settle-form panel" style=${{marginTop: '12px'}}>
          <div class="panel-head">Mark claim settled — dispatch ${String(showForm).slice(0,8)}</div>
          <div class="settle-row">
            <label>Claim amount (USD)</label>
            <input type="number" step="0.01" min="0" value=${amount} onInput=${(e) => setAmount(e.target.value)} placeholder="50000" autofocus />
          </div>
          <div class="settle-row">
            <label>Notes (optional)</label>
            <input type="text" value=${notes} onInput=${(e) => setNotes(e.target.value)} placeholder="adjuster notes, claim ref, etc." />
          </div>
          <div class="settle-actions">
            <button class="tbl-action go" disabled=${busy === showForm} onClick=${() => submitSettle(showForm)}>${busy === showForm ? 'Settling…' : 'Confirm'}</button>
            <button class="tbl-action" onClick=${() => { setShowForm(null); setAmount(''); setNotes(''); }}>Cancel</button>
          </div>
          <div class="settle-hint">Fee will be 3% of claim amount. Fee_events row will be created and the dispatch will be marked settled.</div>
        </div>
      ` : null}
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
  // Bounty payout state
  const [bountyPending, setBountyPending] = useState(null);
  const [bountyHistory, setBountyHistory] = useState(null);
  const [bountyStats, setBountyStats] = useState(null);
  const [bountyErr, setBountyErr] = useState(null);
  const [bountyTab, setBountyTab] = useState('pending');

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
    // Load bounty data
    try {
      const [bp, bh, bs] = await Promise.all([
        apiFetch('/api/v1/bounty-payouts/pending').then(r => r.json()),
        apiFetch('/api/v1/bounty-payouts/history?limit=20').then(r => r.json()),
        apiFetch('/api/v1/bounty-payouts/stats').then(r => r.json()),
      ]);
      setBountyPending(bp.pending || []);
      setBountyHistory(bh.history || []);
      setBountyStats(bs || {});
    } catch (e) { setBountyErr(e.message); }
  };
  useEffect(() => { reload(); }, []);

  const act = async (id, action) => {
    if (!confirm('Confirm ' + action + ' for payout ' + id.slice(0,8) + '?')) return;
    setBusy(id);
    try {
      await apiFetch('/api/v1/payouts/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ payout_id: id }) });
      await reload();
      loadActivity(0, false);
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  // Bounty payout actions
  const bountyAct = async (id, action) => {
    const label = action === 'approve' ? 'Pay' : 'Reject';
    if (!confirm(label + ' bounty payout ' + id.slice(0,8) + '?')) return;
    setBusy('bounty-' + id);
    try {
      await apiFetch('/api/v1/bounty-payouts/' + action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payout_id: id, reason: 'Approved by operator' }),
      });
      await reload();
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  const fmtUsd = (n) => '$' + Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!pending) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;
  const mode = (stats && stats.mode) || 'DRY-RUN';

  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Payouts</div><div class="section-sub">Settlements · bounty referrals</div></div><div class="sec-actions"><button class="tbl-action go" onClick=${reload}>↻ Refresh</button></div></div>

      <div class="pulse-tabs">
        <button class="pulse-tab ${bountyTab === 'settlement' ? 'active' : ''}" onClick=${() => setBountyTab('settlement')}>Settlement</button>
        <button class="pulse-tab ${bountyTab !== 'settlement' ? 'active' : ''}" onClick=${() => setBountyTab('pending')}>Bounty Payouts</button>
      </div>

      ${bountyTab === 'settlement' ? html`
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
      ` : html`
        ${bountyErr ? html`<div class="sec-meta" style=${{color:'var(--status-red)'}}>Error: ${bountyErr}</div>` : ''}
        ${bountyStats ? html`
        <div class="fee-stats">
          <div class="fee-stat"><div class="fee-stat-label">Pending requests</div><div class="fee-stat-value" style=${{color:'var(--status-amber)'}}>${bountyStats.pending_requested || 0}</div></div>
          <div class="fee-stat"><div class="fee-stat-label">Pending amount</div><div class="fee-stat-value" style=${{color:'var(--status-amber)'}}>${fmtUsd(bountyStats.pending_amount_usd)}</div></div>
          <div class="fee-stat"><div class="fee-stat-label">Paid bounties</div><div class="fee-stat-value teal">${bountyStats.paid_count || 0}</div></div>
          <div class="fee-stat"><div class="fee-stat-label">Total paid</div><div class="fee-stat-value teal">${fmtUsd(bountyStats.paid_amount_usd)}</div></div>
        </div>
        ` : ''}

        <div class="panel" style=${{marginBottom: '16px'}}>
          <div class="panel-head">Pending Bounty Payout Requests</div>
          ${!bountyPending ? html`<div class="tbl-empty">Loading…</div>` : bountyPending.length === 0
            ? html`<div class="tbl-empty">No pending bounty payout requests.</div>`
            : html`<table class="tbl"><thead><tr>
                <th>Referrer</th><th>Wallet / Email</th><th class="tbl-num">Bounty</th><th>Requested</th><th>Actions</th>
              </tr></thead><tbody>
              ${bountyPending.map(p => html`<tr key=${p.id}>
                <td><strong>${p.referrer_name || 'Unknown'}</strong></td>
                <td class="tbl-mono" style=${{fontSize:'10px'}}>${p.payout_address ? String(p.payout_address).slice(0,24) + '…' : (p.referrer_email || '')}</td>
                <td class="tbl-num"><strong style=${{color:'var(--signal-teal)'}}>${fmtUsd(p.bounty_amount)}</strong></td>
                <td class="tbl-mono">${String(p.created_at || '').slice(0,16).replace('T',' ')}</td>
                <td>
                  <button class="tbl-action go" disabled=${busy === 'bounty-' + p.id} onClick=${() => bountyAct(p.id, 'approve')}>Pay</button>
                  <button class="tbl-action danger" disabled=${busy === 'bounty-' + p.id} onClick=${() => bountyAct(p.id, 'reject')}>Reject</button>
                </td>
              </tr>`)}
            </tbody></table>`}
        </div>

        <div class="panel">
          <div class="panel-head">Bounty Payout History</div>
          ${!bountyHistory ? html`<div class="tbl-empty">Loading…</div>` : bountyHistory.length === 0
            ? html`<div class="tbl-empty">No bounty history yet.</div>`
            : html`<table class="tbl"><thead><tr>
                <th>When</th><th>Referrer</th><th class="tbl-num">Amount</th><th>Status</th>
              </tr></thead><tbody>
              ${bountyHistory.map(p => html`<tr key=${p.id}>
                <td class="tbl-mono">${String(p.paid_at || p.created_at || '').slice(0,16).replace('T',' ')}</td>
                <td><strong>${p.referrer_name || 'Unknown'}</strong></td>
                <td class="tbl-num">${fmtUsd(p.bounty_amount)}</td>
                <td><span class="status-pill status-${p.status === 'paid' ? 'sent' : 'cancelled'}">${p.status}</span></td>
              </tr>`)}
            </tbody></table>`}
        </div>
      `}
    </div>
  `;
}

// ── CONTRACTORS ───────────────────────────────────────────────────────
// ── FEES ──────────────────────────────────────────────────────────────
function Fees() {
  const [list, setList] = useState(null);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);

  const reload = async () => {
    try {
      const [l, s] = await Promise.all([
        apiFetch('/api/v1/fee/list?limit=50').then(r => r.json()),
        apiFetch('/api/v1/fee/stats').then(r => r.json()),
      ]);
      setList(l.fees || []);
      setStats(s || {});
    } catch (e) { setErr(e.message); }
  };
  useEffect(() => { reload(); }, []);

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!list) return html`<div class="stub"><div class="stub-body">Loading fees…</div></div>`;

  const fmtUsd = (n) => '$' + Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const totalClaim = stats.total_claim_usd || 0;
  const totalFee = stats.total_fee_usd || 0;
  const byStatus = stats.by_status || {};
  const count = stats.count || 0;

  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Fees</div><div class="section-sub">Settled-claim events · 3% per settled claim · ${count} total</div></div><div class="sec-actions"><button class="tbl-action go" onClick=${reload}>↻ Refresh</button></div></div>
      <div class="fee-stats">
        <div class="fee-stat"><div class="fee-stat-label">Total claim amount</div><div class="fee-stat-value teal">${fmtUsd(totalClaim)}</div></div>
        <div class="fee-stat"><div class="fee-stat-label">Total fees (3%)</div><div class="fee-stat-value">${fmtUsd(totalFee)}</div></div>
        <div class="fee-stat"><div class="fee-stat-label">Pending</div><div class="fee-stat-value">${byStatus.pending || 0}</div></div>
        <div class="fee-stat"><div class="fee-stat-label">Paid</div><div class="fee-stat-value dim">${byStatus.paid || 0}</div></div>
      </div>
      <div class="panel">
        <div class="panel-head">Recent fee events</div>
        ${list.length === 0
          ? html`<div class="tbl-empty">No fee events yet. When a real claim settles, the webhook at <code>POST /api/v1/fee/claim-settled</code> writes rows here. Operator mark-settled also writes to this table.</div>`
          : html`<table class="tbl"><thead><tr>
                <th>When</th><th>Claim</th><th>Contractor</th><th class="tbl-num">Claim $</th><th class="tbl-num">Fee $</th><th>Status</th><th>Source</th>
              </tr></thead><tbody>
              ${list.map(f => html`<tr key=${f.id}>
                <td class="tbl-mono">${String(f.settled_at || f.created_at || '').slice(0,16).replace('T',' ')}</td>
                <td class="tbl-mono">${String(f.claim_id || '').slice(0,28)}</td>
                <td class="tbl-mono">${String(f.contractor_id || '').slice(0,8)}</td>
                <td class="tbl-num">${fmtUsd(f.claim_amount)}</td>
                <td class="tbl-num"><strong>${fmtUsd(f.fee_amount)}</strong></td>
                <td><span class=${'fee-status ' + (f.status || 'pending')}>${f.status || 'pending'}</span></td>
                <td class="tbl-mono">${f.source || '—'}</td>
              </tr>`)}
              </tbody></table>`}
      </div>
      <div class="panel" style=${{marginTop: '16px'}}>
        <div class="panel-head">How fees get created</div>
        <div class="panel-body" style=${{fontSize: '12px', color: 'var(--empire-mist)', lineHeight: '1.6'}}>
          <p style=${{marginBottom: '8px'}}><strong>1. Carrier webhook (when integrated):</strong> <code>POST /api/v1/fee/claim-settled</code> with <code>{claim_id, claim_amount, contractor_id, lead_id, settled_at}</code></p>
          <p style=${{marginBottom: '8px'}}><strong>2. Operator mark-settled:</strong> <code>POST /api/v1/claims/mark-settled</code> with <code>{dispatch_id, claim_amount, meta}</code>. Looks up the dispatch, resolves the lead + contractor, writes the fee event.</p>
          <p style=${{marginBottom: '8px'}}><strong>3. Manual trigger:</strong> <code>python3 -m agents.fee_watcher.trigger --claim-amount 50000 --contractor-id &lt;uuid&gt;</code></p>
          <p style=${{marginBottom: '0'}}>All three paths converge on the same <code>fee_events</code> table with <code>fee_amount = claim_amount × 0.03</code>.</p>
        </div>
      </div>
    </div>
  `;
}


// ── PREDICTED REVENUE ──────────────────────────────────────────────────
function Predicted() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const reload = async () => {
    try {
      const r = await apiFetch('/api/v1/predictive/revenue?days=30').then(x => x.json());
      setData(r);
    } catch (e) { setErr(e.message); }
  };
  useEffect(() => { reload(); }, []);

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading projection…</div></div>`;

  const fmtUsd = (n) => '$' + Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  const seq = data.by_sequence_type || [];
  const metros = (data.by_metro || []).slice(0, 10);
  const niches = data.by_niche || [];
  const lowConf = data.low_confidence === true;

  return html`
    <div>
      <div class="section-h"><div><div class="section-title">Predicted Revenue</div><div class="section-sub">Projected fees by segment · ${data.window_days}-day window</div></div><div class="sec-actions"><button class="tbl-action go" onClick=${reload}>↻ Refresh</button></div></div>
      ${lowConf ? html`
        <div style=${{background: 'rgba(255,180,0,.08)', border: '1px solid rgba(255,180,0,.35)', borderRadius: '4px', padding: '14px 18px', marginBottom: '20px'}}>
          <div style=${{fontFamily: 'var(--font-mono, ui-monospace)', fontSize: '10px', color: 'rgba(255,180,0,.9)', letterSpacing: '.22em', textTransform: 'uppercase', marginBottom: '6px'}}>Pending signal</div>
          <div style=${{fontSize: '13px', color: 'var(--empire-mist)', lineHeight: '1.6'}}>
            ${data.low_confidence_reason || "Insufficient organic reply data to project fees."}
            <br /><br />
            <strong>Sent in window:</strong> ${data.total_sent_in_window || 0} ·
            <strong>Replied:</strong> ${data.total_replied_in_window || 0} ·
            <strong>Active sequences:</strong> ${data.total_active_sequences || 0}
            <br />
            Projections will populate as organic replies arrive (24-72h reply window).
          </div>
        </div>
      ` : ''}
      ${health && health.ok ? html`
        <div class="fee-stats" style="margin-bottom:20px">
          <div class="fee-stat" style="${health.circuit_breaker && health.circuit_breaker.consecutive_failures > 0 ? 'border-color:rgba(255,68,68,0.3)' : ''}">
            <div class="fee-stat-label">Circuit Breaker</div>
            <div class="fee-stat-value ${health.circuit_breaker && health.circuit_breaker.consecutive_failures > 0 ? '' : 'teal'}" style="font-size:18px;${health.circuit_breaker && health.circuit_breaker.consecutive_failures > 0 ? 'color:var(--status-red)' : ''}">
              ${health.circuit_breaker && health.circuit_breaker.is_open ? '⚠ OPEN' : '✓ CLOSED'}
            </div>
            <div style="font-size:10px;color:var(--empire-fog);margin-top:4px">
              ${health.circuit_breaker ? health.circuit_breaker.consecutive_failures + ' consecutive failures' : ''}
            </div>
          </div>
          <div class="fee-stat">
            <div class="fee-stat-label">Dispatched (24h)</div>
            <div class="fee-stat-value teal">${health.dispatched_24h || 0}</div>
          </div>
          <div class="fee-stat" style="${health.failed_24h > 0 ? 'border-color:rgba(255,184,0,0.2)' : ''}">
            <div class="fee-stat-label">Failed (24h)</div>
            <div class="fee-stat-value ${health.failed_24h > 0 ? '' : 'dim'}" style="${health.failed_24h > 0 ? 'color:var(--status-amber)' : ''}">${health.failed_24h || 0}</div>
          </div>
          <div class="fee-stat">
            <div class="fee-stat-label">Matcher Runs</div>
            <div class="fee-stat-value dim">${health.matcher_stats ? (health.matcher_stats.matches_computed || 0) : 0}</div>
          </div>
        </div>
        ${health.recent_errors && health.recent_errors.length > 0 ? html`
          <div class="panel" style="margin-bottom:20px;border-color:rgba(255,184,0,0.15)">
            <div class="panel-head" style="display:flex;justify-content:space-between">
              <span style="color:var(--status-amber)">⚠ Recent Dispatch Errors</span>
              <span class="sec-meta" style="margin:0">${health.recent_errors.length} errors</span>
            </div>
            ${health.recent_errors.slice(0, 5).map(e => html`
              <div style="font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);padding:6px 0;border-bottom:1px solid var(--empire-divider);word-break:break-word">
                <span style="color:var(--empire-fog);font-size:9px">${(e.at || '').slice(0,19)}</span>
                <span style="margin-left:8px">${(e.body || '').slice(0,100)}</span>
              </div>
            `)}
          </div>
        ` : null}
      ` : null}
      <div class="fee-stats">
        <div class="fee-stat"><div class="fee-stat-label">Projected total</div><div class="fee-stat-value teal">${lowConf ? '—' : fmtUsd(data.total_projected_fees_usd)}</div></div>
        <div class="fee-stat"><div class="fee-stat-label">Active sequences</div><div class="fee-stat-value">${data.total_active_sequences.toLocaleString()}</div></div>
        <div class="fee-stat"><div class="fee-stat-label">Blended reply rate</div><div class="fee-stat-value">${data.blended_reply_rate_pct}%</div></div>
        <div class="fee-stat"><div class="fee-stat-label">Avg claim (real)</div><div class="fee-stat-value dim">${fmtUsd(data.avg_claim_usd)}</div></div>
      </div>
      <div class="panel">
        <div class="panel-head">By sequence type</div>
        ${seq.length === 0 ? html`<div class="tbl-empty">No active sequences.</div>` : html`
          <table class="tbl"><thead><tr>
            <th>Sequence</th><th class="tbl-num">Active</th><th class="tbl-num">Sent (window)</th><th class="tbl-num">Replied</th><th class="tbl-num">Reply rate</th><th class="tbl-num">Projected fees</th>
          </tr></thead><tbody>
            ${seq.map(s => html`<tr key=${s.sequence_type}>
              <td><strong>${s.sequence_type}</strong></td>
              <td class="tbl-num">${s.active_sequences}</td>
              <td class="tbl-num">${s.sent_in_window || 0}</td>
              <td class="tbl-num">${s.replied_in_window || 0}</td>
              <td class="tbl-num">${s.reply_rate_pct}%</td>
              <td class="tbl-num"><strong>${lowConf ? '—' : fmtUsd(s.projected_fees_usd)}</strong></td>
            </tr>`)}
          </tbody></table>`}
      </div>
      <div class="panel" style=${{marginTop: '16px'}}>
        <div class="panel-head">By metro (top 10)</div>
        ${metros.length === 0 ? html`<div class="tbl-empty">No metro data.</div>` : html`
          <table class="tbl"><thead><tr>
            <th>Metro</th><th class="tbl-num">Active</th><th class="tbl-num">Reply rate</th><th class="tbl-num">Projected fees</th>
          </tr></thead><tbody>
            ${metros.map(m => html`<tr key=${m.metro}>
              <td><strong>${m.metro}</strong></td>
              <td class="tbl-num">${m.active_sequences}</td>
              <td class="tbl-num">${m.reply_rate_pct}%</td>
              <td class="tbl-num"><strong>${fmtUsd(m.projected_fees_usd)}</strong></td>
            </tr>`)}
          </tbody></table>`}
      </div>
      <div class="panel" style=${{marginTop: '16px'}}>
        <div class="panel-head">How this is computed</div>
        <div class="panel-body" style=${{fontSize: '12px', color: 'var(--empire-mist)', lineHeight: '1.6'}}>
          <p>Projected fees = active sequences × reply rate × avg claim size × 3%</p>
          <p>Reply rate is computed from <code style=${{fontFamily: 'var(--font-mono, ui-monospace)', fontSize: '11px', background: 'rgba(255,255,255,.04)', padding: '1px 5px', borderRadius: '2px'}}>outreach_log.response_received_at</code> over the last ${data.window_days} days — organic ground truth, not seed data.</p>
          <p>Avg claim (${fmtUsd(data.avg_claim_usd)}) is the all-time average from <code style=${{fontFamily: 'var(--font-mono, ui-monospace)', fontSize: '11px', background: 'rgba(255,255,255,.04)', padding: '1px 5px', borderRadius: '2px'}}>fee_events</code>. As more fee_events arrive, this narrows.</p>
          <p style=${{marginTop: '8px'}}><strong>Confidence:</strong> ${lowConf ? 'low — projections zeroed until ≥10 organic replies accumulate. The raw reply rate is shown for transparency.' : 'sufficient signal for projection.'}</p>
          ${data._data_source_note ? html`<p style=${{marginTop: '6px', fontStyle: 'italic', opacity: '0.8'}}>${data._data_source_note}</p>` : ''}
        </div>
      </div>
    </div>
  `;
}



function OrganicSignal() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const reload = async () => {
    try {
      const r = await apiFetch('/api/v1/signal/organic?windows_days=1,7,30,90');
      setData(await r.json());
    } catch (e) { setErr(e.message); }
  };
  useEffect(() => { reload(); }, []);

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading signal…</div></div>`;

  const gate = data.confidence_gate || {};
  const gateMet = gate.gate_met === true;
  const gatePct = gate.threshold ? Math.min(100, Math.round(100 * (gate.best_window_replies || 0) / gate.threshold)) : 0;

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Organic Signal</div>
          <div class="section-sub">Ground-truth replies across windows · confidence gate for projections</div>
        </div>
        <div class="sec-actions"><button class="tbl-action go" onClick=${reload}>↻ Refresh</button></div>
      </div>

      <div class="fee-stats">
        <div class="fee-stat"><div class="fee-stat-label">1d replies</div><div class="fee-stat-value">${(data.windows.find(w => w.days === 1) || {}).replied || 0}</div></div>
        <div class="fee-stat"><div class="fee-stat-label">7d replies</div><div class="fee-stat-value">${(data.windows.find(w => w.days === 7) || {}).replied || 0}</div></div>
        <div class="fee-stat"><div class="fee-stat-label">30d replies</div><div class="fee-stat-value">${(data.windows.find(w => w.days === 30) || {}).replied || 0}</div></div>
        <div class="fee-stat"><div class="fee-stat-label">All-time</div><div class="fee-stat-value dim">${data.total_replies_all_time || 0}</div></div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <span>Confidence gate for projection</span>
          <span style=${{color: gateMet ? 'var(--signal-teal)' : 'rgba(255,180,0,.85)'}}>${gateMet ? '✓ MET' : gate.replies_to_gate + ' to go'}</span>
        </div>
        <div style=${{padding: '14px 0'}}>
          <div style=${{height: '14px', background: 'rgba(255,255,255,.06)', borderRadius: '7px', overflow: 'hidden', position: 'relative'}}>
            <div style=${{height: '100%', width: gatePct + '%', background: gateMet ? 'linear-gradient(90deg, var(--signal-teal), #4FB89E)' : 'linear-gradient(90deg, rgba(255,180,0,.6), rgba(255,180,0,.85))', borderRadius: '7px', transition: 'width .6s var(--ease-out-empire)'}}></div>
          </div>
          <div style=${{marginTop: '10px', fontFamily: 'var(--font-mono, ui-monospace)', fontSize: '11px', color: 'var(--empire-mist)'}}>${(gate.best_window_replies || 0)} / ${gate.threshold || 10} organic replies (best window)</div>
        </div>
        <div class="panel-body" style=${{fontSize: '12px', color: 'var(--empire-mist)', lineHeight: '1.6'}}>
          Once ${gate.threshold || 10} organic replies accumulate, the Predicted Revenue section stops showing "Pending signal" and starts surfacing real dollar projections.
        </div>
      </div>

      <div class="panel" style=${{marginTop: '16px'}}>
        <div class="panel-head">By window</div>
        <table class="tbl"><thead><tr><th>Window</th><th class="tbl-num">Sent</th><th class="tbl-num">Replied</th><th class="tbl-num">Reply rate</th></tr></thead><tbody>
          ${(data.windows || []).map(w => html`<tr key=${w.days}><td><strong>${w.days}d</strong></td><td class="tbl-num">${w.sent}</td><td class="tbl-num">${w.replied}</td><td class="tbl-num">${w.rate_pct}%</td></tr>`)}
        </tbody></table>
      </div>

      <div class="panel" style=${{marginTop: '16px'}}>
        <div class="panel-head">Most recent replies</div>
        ${(data.most_recent_replies || []).length === 0 ? html`<div class="tbl-empty">No organic replies yet.</div>` : html`
          <table class="tbl"><thead><tr><th>When</th><th>Sequence</th><th>Reply text</th></tr></thead><tbody>
            ${(data.most_recent_replies || []).map(r => html`<tr key=${r.at}><td class="tbl-mono">${(r.at || '').slice(0, 19)}</td><td>${r.sequence || '?'}</td><td>${(r.response_text || '').slice(0, 100)}</td></tr>`)}
          </tbody></table>
        `}
      </div>

      <div class="panel" style=${{marginTop: '16px'}}>
        <div class="panel-head">How this is computed</div>
        <div class="panel-body" style=${{fontSize: '12px', color: 'var(--empire-mist)', lineHeight: '1.6'}}>
          <p>Reply counts come from <code style=${{fontFamily: 'var(--font-mono, ui-monospace)', fontSize: '11px', background: 'rgba(255,255,255,.04)', padding: '1px 5px', borderRadius: '2px'}}>outreach_log.response_received_at</code> — set by the inbound handler (SMS via Vonage, email via Resend) every time a contact replies.</p>
          <p>Best window = the window with the most replies. The 10-reply threshold is a confidence gate: below 10, the Predicted Revenue projection is too noisy to be useful (low_confidence=true).</p>
        </div>
      </div>
    </div>
  `;
}

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

function AgiDashboard(){
  const [data,setData]=useState(null);
  const [err,setErr]=useState(null);
  const [tick,setTick]=useState(0);
  const [approved,setApproved]=useState([]);
  const [replayIdx,setReplayIdx]=useState(null);const [dreamData,setDreamData]=useState(null);
  useEffect(()=>{
    let alive=true;
    async function poll(){
      try{
        const r=await apiFetch("/api/telemetry?lines=20");
        const j=await r.json();
        if(alive){setData(j);setErr(null);}
        apiFetch('/api/dream/recent?limit=1').then(r2=>r2.json()).then(dr=>{if(dr.dreams&&dr.dreams.length>0)setDreamData(dr.dreams[0]);}).catch(()=>{});
      }catch(e){if(alive)setErr(e.message);}
    }
    poll();
    const id=setInterval(()=>{poll();setTick(t=>t+1);},5000);
    return()=>{alive=false;clearInterval(id);};
  },[]);
  const hist=data?.snapshots??[]; const live=replayIdx===null; const snap=live?hist[0]:hist[replayIdx];
  const doApprove=(idx,w)=>{if(approved.includes(idx))return;setApproved(p=>[...p,idx]);apiFetch("/api/v1/storm/tick",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({auto_weight:parseFloat(w),source:"neural-core"})}).catch(e=>console.warn(e));};
  const decisions=(data?.actions??[]).map(a=>({weight:a.new_weight?.toFixed(2),reason:a.reasoning}));
  // Parse genome trait drift for visualization
  const drift = genomeHistory && genomeHistory.trait_drift ? genomeHistory.trait_drift : null;
  const driftEntries = drift ? Object.entries(drift).map(([k,v]) => ({trait:k, drift:v})) : [];
  const driftMax = driftEntries.length > 0 ? Math.max(...driftEntries.map(d => Math.abs(d.drift)), 0.01) : 0.01;

  return html`<div class="section-header"><div><div class="section-title">Neural Core</div><div class="section-sub">Live brain · autonomous decisions · 5s refresh</div></div><div class="agi-meta">TICK ${tick} · LIVE<button class=${live?"agi-replay-btn active":"agi-replay-btn"} onClick=${()=>setReplayIdx(null)}>LIVE</button><button class="agi-replay-btn" onClick=${()=>setReplayIdx(r=>r===null?1:Math.min(r+1,hist.length-1))}>PREV</button><button class="agi-replay-btn" onClick=${()=>setReplayIdx(r=>r===null?null:r<=1?null:r-1)}>NEXT</button></div></div><div class="agi-grid"><div class="agi-tile"><div class="agi-tile-label">LEAD VELOCITY</div><div class="agi-tile-val"><em>${snap?.lead_velocity??"--"}</em></div><div class="agi-tile-sub">leads/hr</div></div><div class="agi-tile"><div class="agi-tile-label">REVENUE PULSE</div><div class="agi-tile-val"><em>${snap?.revenue_pulse!=null?(snap.revenue_pulse*100).toFixed(1)+"%":"--"}</em></div><div class="agi-tile-sub">AI confidence</div></div><div class="agi-tile"><div class="agi-tile-label">PROXY HEALTH</div><div class="agi-tile-val"><em>${snap?.proxy_health!=null?(snap.proxy_health*100).toFixed(1)+"%":"--"}</em></div><div class="agi-tile-sub">network health</div></div><div class="agi-tile"><div class="agi-tile-label">AI CALLS</div><div class="agi-tile-val"><em>${snap?.ai_calls_today??"--"}</em></div><div class="agi-tile-sub">brain activations</div></div></div><div class="agi-decisions">
      ${dreamData ? html`
        <div class="agi-decisions-head">
          <div class="agi-decisions-title">Dream Memory <span style=${{fontSize:'0.7em',opacity:0.6}}>(cycle #${dreamData.dream_cycle})</span></div>
          <div class="agi-decisions-count">${(dreamData.insights||[]).length} insights · ${(dreamData.rule_suggestions||[]).length} rules${(dreamData.risk_flags||[]).length > 0 ? ` · ⚠ ${(dreamData.risk_flags||[]).length} risks` : ''}</div>
        </div>
        ${(dreamData.insights||[]).slice(0,3).map(i => html`
          <div class="agi-row">
            <div class="agi-row-weight">${i.confidence}/10</div>
            <div class="agi-row-reason">${i.text} <span style=${{fontSize:'0.8em',opacity:0.6}}>[${(i.systems||[]).join(", ")}]</span></div>
          </div>
        `)}
        ${dreamData.wisdom_context ? html`
          <div class="agi-row" style=${{borderTop:'1px solid var(--empire-divider)',marginTop:'8px',paddingTop:'12px'}}>
            <div class="agi-row-weight" style=${{color:'var(--strike-cyan)'}}>Wisdom</div>
            <div class="agi-row-reason" style=${{fontStyle:'italic'}}>${dreamData.wisdom_context}</div>
          </div>
        ` : null}
      ` : null}
      <div class="agi-decisions-head"><div class="agi-decisions-title">Decision Log</div><div class="agi-decisions-count">${decisions.length} entries</div></div>${decisions.map((d,i)=>html`<div class="agi-row"><div class=${"agi-row-weight "+(parseFloat(d.weight)>=1.5?"agi-w-hi":parseFloat(d.weight)>=1.0?"agi-w-mid":"agi-w-lo")}>${d.weight??"·"}<div class="agi-w-bar"></div></div><div class="agi-row-reason">${d.reason??"·"}<button class=${approved.includes(i)?"agi-approve-btn done":"agi-approve-btn"} onClick=${()=>doApprove(i,d.weight)}>${approved.includes(i)?"✓ APPROVED":"AUTO-APPROVE"}</button></div></div>`)}</div>`;
}

function Partners() {
  const [partners, setPartners] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);
  const [filter, setFilter] = useState('all');
  const [focusId, setFocusId] = useState(null);

  function getFocusParam() {
    const hash = window.location.hash;
    const idx = hash.indexOf('?');
    if (idx === -1) return null;
    try { return new URLSearchParams(hash.slice(idx + 1)).get('focus') || null; } catch { return null; }
  }

  const reload = async () => {
    try {
      const endpoint = f === 'pending'
        ? '/api/v1/partner/pending'
        : '/api/v1/partner/all';
      const r = await apiFetch(endpoint).then(x => x.json());
      setPartners(r.partners || (Array.isArray(r) ? r : []));
    } catch (e) { setErr(e.message); }
  };

  useEffect(() => { reload(); }, [filter]);

  // Read focus param from hash on mount and on hash change
  useEffect(() => {
    const onHash = () => setFocusId(getFocusParam());
    onHash();
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const displayedPartners = partners && focusId
    ? partners.filter(p => p.id === focusId)
    : partners;

  const clearFocus = () => {
    window.location.hash = '#/partners';
    setFocusId(null);
  };

  const act = async (id, action) => {
    const label = action === 'approve' ? 'Approve' : 'Reject';
    if (!confirm(`${label} partner ${id.slice(0,8)}?`)) return;
    setBusy(id);
    try {
      const body = action === 'reject'
        ? JSON.stringify({ reason: prompt('Rejection reason (optional):') || '' })
        : '{}';
      await apiFetch(`/api/v1/partner/${id}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      await reload();
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!partners) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Partners</div>
          <div class="section-sub">Buyer pipeline · approvals</div>
        </div>
        <div style=${{display: 'flex', gap: '10px', alignItems: 'center'}}>
          <button class=${'tbl-action ' + (filter === 'pending' ? 'go' : '')} onClick=${() => setFilter('pending')}>Pending only</button>
          <button class=${'tbl-action ' + (filter === 'all' ? 'go' : '')} onClick=${() => setFilter('all')}>All</button>
          <span class="section-sub">${displayedPartners.length} partner${displayedPartners.length === 1 ? '' : 's'}${focusId ? ' · filtered' : ''}</span>
          ${focusId ? html`<button class="tbl-action go" onClick=${clearFocus}>Back to all</button>` : ''}
        </div>
      </div>
      ${displayedPartners.length === 0
        ? html`<div class="tbl-empty">No partners found.</div>`
        : html`<table class="tbl"><thead><tr>
            <th>Business</th><th>Contact</th><th>Niche</th><th>State</th><th>Applied</th><th>Status</th><th>Actions</th>
          </tr></thead><tbody>
          ${displayedPartners.map(p => html`<tr key=${p.id}>
            <td>
              <strong>${p.buyer_name || '—'}</strong>
              ${p.email ? html`<br/><span class="tbl-mono">${p.email}</span>` : ''}
            </td>
            <td>
              ${p.contact_name || '—'}
              ${p.destination_phone ? html`<br/><span class="tbl-mono">${p.destination_phone}</span>` : ''}
            </td>
            <td class="tbl-mono">${p.niche || '—'}</td>
            <td class="tbl-mono">${Array.isArray(p.state_coverage) ? p.state_coverage.join(', ') : (p.state_coverage || '—')}</td>
            <td class="tbl-mono">${(p.created_at || '').slice(0,10)}</td>
            <td><span class=${'bdg ' + (p.status || 'unknown')}>${p.status || '—'}</span></td>
            <td>
              ${p.status === 'pending_review' ? html`
                <button class="tbl-action go" disabled=${busy === p.id} onClick=${() => act(p.id, 'approve')}>Approve</button>
                <button class="tbl-action danger" disabled=${busy === p.id} onClick=${() => act(p.id, 'reject')}>Reject</button>
              ` : html`
                ${p.status === 'active' ? html`<span class="tbl-mono" style=${{color: 'var(--signal-teal)'}}>✓ Active</span>` : ''}
                ${p.status === 'rejected' ? html`<span class="tbl-mono" style=${{color: 'var(--status-red)'}}>✗ Rejected</span>` : ''}
              `}
            </td>
          </tr>`)}
        </tbody></table>`}
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

// ── GOVERNOR ───────────────────────────────────────────────────────────
function Governor() {
  const [status, setStatus] = useState(null);
  const [log, setLog] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([
        apiFetch('/api/governor/status').then(r => r.json()),
        apiFetch('/api/governor/log?lines=20').then(r => r.json()),
      ]);
      setStatus(s);
      setLog(l.entries || []);
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 10000);
    return () => clearInterval(t);
  }, [reload]);

  const doHeal = async () => {
    if (!confirm('⚠️ Force-restart ALL PM2 services? The hub will self-restart last (this page will reload).')) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await apiFetch('/api/governor/heal', { method: 'POST' });
      const j = await r.json();
      setResult(j);
    } catch (e) {
      setResult({ ok: false, message: e.message });
    }
    setBusy(false);
  };

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Governor</div><div class="stub-body">${err}</div></div>`;

  const svcs = status?.services || [];
  const wd = status?.watchdog;

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Governor</div>
          <div class="section-sub">PM2 watchdog · self-heal · service health</div>
        </div>
        <div class="section-sub" style=${{display: 'flex', alignItems: 'center', gap: '16px'}}>
          ${wd ? html`
            <span class="gov-watch-tag">Check: <strong>every ${wd.interval_s}s</strong></span>
            <span class="gov-watch-tag">Healthy: <strong>${wd.healthy}/${wd.total}</strong></span>
          ` : ''}
          <button class="gov-heal-btn" disabled=${busy} onClick=${doHeal}>${busy ? 'Healing…' : 'Heal All'}</button>
        </div>
      </div>

      ${wd ? html`
      <div class="gov-watchdog" style=${{marginBottom: '16px'}}>
        <span class="gov-watch-tag">Last check: <strong>${(wd.last_check || '').slice(11,19)}</strong></span>
        <span class="gov-watch-tag">Watching: <strong>${wd.watching.join(', ')}</strong></span>
      </div>
      ` : ''}

      ${mrrData ? html`<div class="rv-narrative-panel" style="margin-bottom:20px">
        <div class="rv-narrative-head">
          <div class="rv-narrative-title">MRR: Actual vs Projected</div>
          <div class="rv-narrative-badge">${mrrData.subscriptions.length} active subscriptions</div>
        </div>
        <div style="display:flex;gap:24px;align-items:center;padding:8px 0">
          <div style="flex:1;display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist)">
              <span>Projected MRR</span>
              <span style="color:var(--strike-cyan);font-weight:500">$${((mrrData.projected_mrr||0)).toLocaleString()}</span>
            </div>
            <div style="height:28px;background:var(--empire-elevated);border-radius:6px;overflow:hidden;position:relative">
              <div style="height:100%;width:${Math.min(100,((mrrData.projected_mrr||0) / Math.max((mrrData.projected_mrr||0), 1) * 100))}%;background:var(--strike-cyan);border-radius:6px;opacity:0.7;transition:width .6s var(--ease-out-empire)"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist)">
              <span>Actual MRR</span>
              <span style="color:var(--signal-teal);font-weight:500">$${((mrrData.actual_mrr||0)).toLocaleString()}</span>
            </div>
            <div style="height:28px;background:var(--empire-elevated);border-radius:6px;overflow:hidden;position:relative">
              <div style="height:100%;width:${Math.min(100,((mrrData.actual_mrr||0) / Math.max((mrrData.projected_mrr||0), 1) * 100))}%;background:var(--signal-teal);border-radius:6px;opacity:0.85;transition:width .6s var(--ease-out-empire)"></div>
            </div>
          </div>
          <div style="text-align:center;flex-shrink:0">
            <div style="font-family:var(--font-display);font-weight:200;font-size:36px;color:${((mrrData.gap||0) > 0) ? 'var(--status-amber)' : 'var(--signal-teal)'};line-height:1">${((mrrData.gap_pct||0))}%</div>
            <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:4px">${((mrrData.gap||0) > 0) ? 'Below Projection' : 'On Track'}</div>
            <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:6px">Gap: $${((mrrData.gap||0)).toLocaleString()}</div>
          </div>
        </div>
        ${(mrrData.subscriptions||[]).length > 0 ? html`<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--empire-divider)">
          <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;margin-bottom:8px">Subscription Breakdown</div>
          ${mrrData.subscriptions.map(s => html`<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;font-family:var(--font-mono);font-size:10px;border-bottom:1px solid var(--empire-divider)">
            <span style="color:var(--empire-silver)">${s.account}</span>
            <span style="color:var(--empire-mist);font-size:9px;letter-spacing:.08em">${s.tier}</span>
            <span style="color:var(--signal-teal);font-weight:500">$${s.mrr.toLocaleString()}</span>
          </div>`)}
        </div>` : null}
      </div>` : null}

${!status
        ? html`<div class="gov-panel"><div class="gov-empty">Loading service status…</div></div>`
        : html`
      <div class="gov-grid">
        ${svcs.length === 0
          ? html`<div class="gov-empty" style=${{gridColumn: '1 / -1'}}>No PM2 services found.</div>`
          : svcs.map(s => {
            const statusCls = s.status === 'online' ? 'online' : s.status === 'errored' ? 'errored' : s.status === 'stopped' ? 'stopped' : 'unknown';
            const uptime = s.uptime_s != null
              ? (s.uptime_s >= 86400 ? Math.round(s.uptime_s / 86400) + 'd'
                : s.uptime_s >= 3600 ? Math.round(s.uptime_s / 3600) + 'h'
                : s.uptime_s >= 60 ? Math.round(s.uptime_s / 60) + 'm'
                : s.uptime_s + 's')
              : '—';
            return html`
            <div class="gov-card" key=${s.name}>
              <div class="gov-card-row">
                <div class="gov-card-name">${s.name}</div>
                <span class=${'gov-bdg ' + statusCls}>
                  <span class="gov-bdg-dot"></span>${s.status}
                </span>
              </div>
              <div class="gov-card-stats">
                <div class="gov-stat">
                  <div class="gov-stat-val">${uptime}</div>
                  <div class="gov-stat-lbl">uptime</div>
                </div>
                <div class="gov-stat">
                  <div class="gov-stat-val">${s.restarts}</div>
                  <div class="gov-stat-lbl">restarts</div>
                </div>
                <div class="gov-stat">
                  <div class="gov-stat-val">${s.mem_mb ?? '—'}</div>
                  <div class="gov-stat-lbl">mem (mb)</div>
                </div>
                <div class="gov-stat">
                  <div class="gov-stat-val">${s.cpu_pct ?? '—'}%</div>
                  <div class="gov-stat-lbl">cpu</div>
                </div>
              </div>
            </div>
          `})}
      </div>
      `}

      ${result ? html`<div class="gov-result">${result.message || (result.ok ? 'Heal complete' : 'Heal failed')}${result.errors && result.errors.length ? ' · ' + result.errors.length + ' error(s)' : ''}</div>` : ''}

      <div class="gov-panel">
        <div class="gov-panel-h">
          <div class="gov-panel-title">Heal Log</div>
          <div class="gov-panel-tag">${log.length} entries</div>
        </div>
        ${log.length === 0
          ? html`<div class="gov-empty">No heal log entries yet.</div>`
          : html`<div class="gov-log">
            ${log.map(e => html`
              <div class="gov-log-row" key=${e.ts + e.service + e.action}>
                <span class="gov-log-ts">${(e.ts || '').slice(11,19)}</span>
                <span class=${'gov-log-lvl ' + (e.level || 'info')}>${e.level || '—'}</span>
                <span class="gov-log-svc">${e.service || '—'}</span>
                <span class="gov-log-detail">${e.detail || e.action || '—'}</span>
              </div>
            `)}
          </div>`}
      </div>

      <${GovernorHealthPanel} />

      <${AgentFleetPanel} />
    </div>
  `;
}

// ── DONUT CHART ──────────────────────────────────────────────────────
function DonutChart({data, size = 108, strokeWidth = 22, colors = ["var(--signal-teal)", "var(--strike-cyan)", "var(--empire-mist)", "var(--status-red)"]}) {
  const total = data.reduce((s, d) => s + (d.value || 0), 0);
  if (total === 0) return html`<div class="chart-empty" style=${{height: size + 'px', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>No data</div>`;
  const cx = size / 2, cy = size / 2;
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const gap = 2;
  let startAngle = 0;
  const topPct = Math.round((Math.max(...data.map(d => d.value || 0)) / total) * 100);
  const topLabel = data.reduce((a, b) => (a.value || 0) > (b.value || 0) ? a : b, data[0]);
  return html`<div class="chart-donut">
    <svg class="chart-donut-svg" width=${size} height=${size} viewBox="0 0 ${size} ${size}">
      ${data.map((d, i) => {
        const segLen = Math.max(0, ((d.value || 0) / total) * circ - (i < data.length - 1 ? gap : 0));
        const color = d.color || colors[i % colors.length];
        const pct = Math.round(((d.value || 0) / total) * 100);
        const seg = startAngle;
        startAngle += ((d.value || 0) / total) * circ;
        return html`<circle cx=${cx} cy=${cy} r=${r} fill="none" stroke=${color} stroke-width=${strokeWidth}
          stroke-dasharray=${segLen} ${circ - segLen}
          stroke-dashoffset=${-seg}
          transform="rotate(-90 ${cx} ${cy})"
          style=${{cursor:'pointer',transition:'stroke-dasharray 0.3s var(--ease-snap)'}}
        ><title>${d.label}: ${d.value} (${pct}%)</title></circle>`;
      })}
      <circle cx=${cx} cy=${cy} r=${r - strokeWidth / 2 + 1} fill="var(--empire-surface)" />
      <text x=${cx} y=${cy - 4} text-anchor="middle" fill="var(--empire-white)" font-family="var(--font-display)" font-weight="200" font-size=${Math.round(size * 0.22)}>${topPct}%</text>
      ${data.length > 1 ? html`<text x=${cx} y=${cy + 14} text-anchor="middle" fill="var(--empire-fog)" font-family="var(--font-mono)" font-size=${Math.round(size * 0.08)}>${topLabel.label}</text>` : ''}
    </svg>
    <div class="chart-legend">
      ${data.map((d, i) => {
        const pct = Math.round(((d.value || 0) / total) * 100);
        return html`<div class="chart-legend-item" key=${i}>
        <span class="chart-legend-dot" style=${{backgroundColor: d.color || colors[i % colors.length]}}></span>
        ${d.label}
        <span class="chart-legend-val">${d.value} · ${pct}%</span>
      </div>`;
      })}
    </div>
  </div>`;
}

// ── HOLO MAP ─────────────────────────────────────────────────────────
function HoloMap() {
  const [storms, setStorms] = useState({type:'FeatureCollection',features:[]});
  const [targets, setTargets] = useState({type:'FeatureCollection',features:[]});
  const [config, setConfig] = useState(null);
  const [err, setErr] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [s, t, c] = await Promise.all([
        apiFetch('/api/v1/map/storms').then(r => r.json()),
        apiFetch('/api/v1/map/targets?limit=200').then(r => r.json()),
        apiFetch('/api/v1/map/config').then(r => r.json()),
      ]);
      if (s && s.features) setStorms(s);
      if (t && t.features) setTargets(t);
      if (c && c.center) setConfig(c);
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

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Holo Map</div><div class="stub-body">${err}</div></div>`;

  const stormFeatures = storms.features || [];
  const targetFeatures = targets.features || [];

  const sevCounts = {Extreme: 0, Severe: 0, Moderate: 0, Minor: 0};
  for (const f of stormFeatures) {
    const sev = f.properties?.severity || 'Minor';
    if (sevCounts[sev] != null) sevCounts[sev]++;
  }

  function hashToAngle(s) {
    let h = 0;
    for (let i = 0; i < (s||'').length; i++) { h = ((h << 5) - h) + s.charCodeAt(i); h |= 0; }
    return (Math.abs(h) % 360);
  }
  function hashToRadius(s) {
    let h = 0;
    for (let i = 0; i < (s||'').length; i++) { h = ((h << 3) - h) + s.charCodeAt(i); h |= 0; }
    return 15 + (Math.abs(h) % 70);
  }

  const targetBlips = targetFeatures.slice(0, 40).map(f => ({
    id: f.properties?.id || 't',
    angle: hashToAngle(JSON.stringify(f.geometry?.coordinates)),
    radius: hashToRadius(f.properties?.name || 't'),
    type: 'target',
    name: f.properties?.name || (f.properties?.address || '').slice(0,20) || 'Target',
  }));

  const stormBlips = stormFeatures.slice(0, 10).map(f => ({
    id: f.properties?.id || 's',
    angle: hashToAngle(f.properties?.headline || 's'),
    radius: hashToRadius(f.properties?.event || 's'),
    type: 'storm',
    name: f.properties?.event || 'Storm',
  }));

  const blips = [...targetBlips, ...stormBlips];

  function blipStyle(b) {
    const rad = (b.angle - 90) * Math.PI / 180;
    const r = 45 + (b.radius / 100) * 130;
    const x = 180 + r * Math.cos(rad);
    const y = 180 + r * Math.sin(rad);
    return {position: 'absolute', left: x + 'px', top: y + 'px', zIndex: b.type === 'storm' ? 2 : 1};
  }

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Holo <em>Map</em></div>
          <div class="section-sub">Live storm grid · 3D target overlay</div>
        </div>
        <div class="section-sub" style=${{display: 'flex', gap: '16px', alignItems: 'center'}}>
          <span class="holo-badge storm"><span class="holo-bdg-dot" style=${{width:6,height:6,borderRadius:'50%',background:'var(--strike-cyan)',boxShadow:'0 0 6px var(--strike-cyan)'}}></span>${stormFeatures.length} storms</span>
          <span class="holo-badge target"><span class="holo-bdg-dot" style=${{width:6,height:6,borderRadius:'50%',background:'var(--signal-teal)',boxShadow:'0 0 6px var(--signal-teal)'}}></span>${targetFeatures.length} targets</span>
        </div>
      </div>
      <div class="holo-radar-wrap">
        <div class="holo-radar">
          <div class="holo-radar-ring r1"></div>
          <div class="holo-radar-ring r2"></div>
          <div class="holo-radar-ring r3"></div>
          <div class="holo-radar-cross"></div>
          <div class="holo-radar-sweep"></div>
          <div class="holo-radar-center">
            <div class="holo-radar-count">${stormFeatures.length + targetFeatures.length}</div>
            <div class="holo-radar-lbl">features tracked</div>
          </div>
          ${blips.map(b => html`
            <div class="holo-blip" key=${b.id + b.type} style=${blipStyle(b)} title=${b.name}>
              <div class=${'holo-blip-dot ' + b.type}></div>
              <div class=${'holo-blip-ping ' + b.type}></div>
            </div>
          `)}
        </div>
        <div class="holo-badges">
          ${Object.entries(sevCounts).filter(([k,v]) => v > 0).map(([k,v]) => html`
            <span class="holo-storm-sev ${k}">${k}: ${v}</span>
          `)}
        </div>
      </div>
      <div class="holo-split">
        <div class="holo-panel">
          <div class="holo-panel-h">
            <div class="holo-panel-title">Active Storms</div>
            <div class="holo-panel-tag">${stormFeatures.length} alerts</div>
          </div>
          ${stormFeatures.length === 0
            ? html`<div class="holo-empty">No active storm alerts in coverage area.${config ? ` Center: ${config.center.join(', ')}` : ''}</div>`
            : html`<div style=${{maxHeight: '360px', overflowY: 'auto'}}>
              ${stormFeatures.map(f => html`
                <div class="holo-storm-card" key=${f.properties?.id || Math.random()}>
                  <div class="holo-storm-row">
                    <span class="holo-storm-name">${f.properties?.event || 'Weather Alert'}</span>
                    <span class=${'holo-storm-sev ' + (f.properties?.severity || 'Minor')}>${f.properties?.severity || 'Minor'}</span>
                  </div>
                  <div class="holo-storm-area">${f.properties?.area || '—'}</div>
                  <div class="holo-storm-meta">${f.properties?.headline || ''} ${f.properties?.urgency ? '· ' + f.properties.urgency : ''}</div>
                </div>
              `)}
            </div>`}
        </div>
        <div class="holo-panel">
          <div class="holo-panel-h">
            <div class="holo-panel-title">Target Overlay</div>
            <div class="holo-panel-tag">${targetFeatures.length} markers</div>
          </div>
          ${targetFeatures.length === 0
            ? html`<div class="holo-empty">No targets loaded yet. Radar targets appear as leads are captured.</div>`
            : html`<div class="holo-target-scroll">
              ${targetFeatures.map(f => {
                const p = f.properties || {};
                const label = p.name || p.address || '—';
                const status = (p.status || 'new').toLowerCase();
                return html`
                <div class="holo-target-row" key=${p.id || label}>
                  <span class="holo-target-name">${label}</span>
                  <span class=${'holo-target-status ' + status}>${status}</span>
                </div>
              `})}
            </div>`}
        </div>
      </div>
    </div>
  `;
}

// ── HEALTH MONITOR ───────────────────────────────────────────────────

function AgentDetailModal({ agent, govHealth, onClose }) {
  if (!agent) return null;
  // Match this agent against the governor's stale/healthy lists
  const all = [...(govHealth && govHealth.stale || []), ...(govHealth && govHealth.healthy || [])];
  const govEntry = all.find(g => g.agent_name === agent.agent_name) || null;
  const lastPingStr = agent.last_ping ? new Date(agent.last_ping).toLocaleString() : '—';
  const ageStr = agent.seconds_since_ping == null ? '—'
    : agent.seconds_since_ping < 60 ? `${agent.seconds_since_ping}s ago`
    : agent.seconds_since_ping < 3600 ? `${Math.floor(agent.seconds_since_ping / 60)}m ago`
    : `${Math.floor(agent.seconds_since_ping / 3600)}h ago`;
  const metrics = agent.metrics || {};
  const metricKeys = Object.keys(metrics);
  return html`
    <div class="af-modal-overlay" onClick=${onClose}>
      <div class="af-modal" onClick=${e => e.stopPropagation()}>
        <div class="af-modal-head">
          <div>
            <div class="af-modal-eyebrow">Agent Detail</div>
            <div class="af-modal-title">
              <span class=${'af-dot ' + (agent.is_stale ? 'red' : 'green')}></span>
              ${agent.agent_name || 'unknown'}
            </div>
          </div>
          <button class="af-modal-close" onClick=${onClose}>×</button>
        </div>
        <div class="af-modal-body">
          <div class="af-modal-grid">
            <div class="af-modal-section">
              <div class="af-modal-section-h">Status</div>
              <div class="af-modal-kv"><span>Status</span><strong>${agent.status || '?'}</strong></div>
              <div class="af-modal-kv"><span>Enabled</span><strong>${agent.enabled ? 'YES' : 'NO'}</strong></div>
              <div class="af-modal-kv"><span>Last ping</span><strong>${lastPingStr}</strong></div>
              <div class="af-modal-kv"><span>Age</span><strong>${ageStr}</strong></div>
            </div>
            <div class="af-modal-section">
              <div class="af-modal-section-h">Throughput</div>
              <div class="af-modal-kv"><span>Leads today</span><strong class="teal">${agent.leads_today != null ? agent.leads_today : '—'}</strong></div>
              <div class="af-modal-kv"><span>Total registered</span><strong>${data && data.total_count ? data.total_count : '—'}</strong></div>
            </div>
            <div class="af-modal-section af-modal-section-wide">
              <div class="af-modal-section-h">Governor Health Snapshot</div>
              ${govEntry
                ? html`
                  <div class="af-modal-kv"><span>Bucket</span><strong class=${govEntry.is_stale ? 'red' : 'teal'}>${govEntry.is_stale ? 'STALE' : 'HEALTHY'}</strong></div>
                  <div class="af-modal-kv"><span>Interval</span><strong>${govEntry.interval_hours != null ? govEntry.interval_hours.toFixed(1) + 'h' : '—'}</strong></div>
                  <div class="af-modal-kv"><span>Max age (3×)</span><strong>${govEntry.max_age_seconds != null ? Math.floor(govEntry.max_age_seconds / 60) + 'm' : '—'}</strong></div>
                  <div class="af-modal-kv"><span>Actual age</span><strong>${govEntry.seconds_since_ping != null ? Math.floor(govEntry.seconds_since_ping / 60) + 'm' : '—'}</strong></div>
                `
                : html`<div class="af-modal-empty">Not in governor snapshot (disabled or unknown agent)</div>`
              }
            </div>
            ${metricKeys.length > 0
              ? html`
                <div class="af-modal-section af-modal-section-wide">
                  <div class="af-modal-section-h">Metrics</div>
                  <div class="af-modal-metrics">
                    ${metricKeys.map(k => html`
                      <div class="af-modal-metric" key=${k}>
                        <div class="af-modal-metric-k">${k}</div>
                        <div class="af-modal-metric-v">${typeof metrics[k] === 'object' ? JSON.stringify(metrics[k]) : String(metrics[k])}</div>
                      </div>
                    `)}
                  </div>
                </div>
              `
              : html`
                <div class="af-modal-section af-modal-section-wide">
                  <div class="af-modal-section-h">Metrics</div>
                  <div class="af-modal-empty">No metrics reported</div>
                </div>
              `
            }
            ${agent.capabilities && agent.capabilities.length > 0
              ? html`
                <div class="af-modal-section af-modal-section-wide">
                  <div class="af-modal-section-h">Capabilities</div>
                  <div class="af-card-caps">
                    ${agent.capabilities.map(c => html`<span class="af-cap" key=${c}>${c}</span>`)}
                  </div>
                </div>
              ` : null
            }
          </div>
        </div>
      </div>
    </div>
  `;
}

function GovernorHealthPanel() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/governor/health');
      const d = await r.json();
      setData(d);
      setErr(null);
    } catch (e) { if (e.message !== 'Unauthorized') setErr(e.message); }
  }, []);
  const forceRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await apiFetch('/api/governor/refresh', { method: 'POST' });
      const d = await r.json();
      setData(d);
      setErr(null);
    } catch (e) { if (e.message !== 'Unauthorized') setErr(e.message); }
    setRefreshing(false);
  }, []);
  useEffect(() => {
    reload();
    const t = setInterval(reload, 15000);
    return () => clearInterval(t);
  }, [reload]);
  if (err) return html`
    <div class="af-panel">
      <div class="af-h">
        <div class="af-title">Governor Health</div>
        <div class="af-tag">error</div>
      </div>
      <div class="af-empty">${err}</div>
    </div>
  `;
  if (!data) return html`
    <div class="af-panel">
      <div class="af-h">
        <div class="af-title">Governor Health</div>
        <div class="af-tag">loading…</div>
      </div>
      <div class="af-empty">Loading governor health…</div>
    </div>
  `;
  return html`
    <div class="af-panel">
      <div class="af-h">
        <div class="af-title">Governor Health</div>
        <div class="af-tag">${data.checked_at ? new Date(data.checked_at).toLocaleTimeString() : ''}</div>
      </div>
      <div class="af-summary">
        <div class="af-stat healthy">
          <span class=${'af-dot ' + (data.healthy_count > 0 ? 'green' : 'red')}></span>
          Healthy <strong>${data.healthy_count}</strong>
        </div>
        <div class="af-stat stale">
          <span class=${'af-dot ' + (data.stale_count > 0 ? 'red' : 'green')}></span>
          Stale <strong>${data.stale_count}</strong>
        </div>
        <div class="af-stat">Total <strong>${data.total_count}</strong></div>
        <div class="gh-refresh">
          <button class="gh-refresh-btn" disabled=${refreshing} onClick=${forceRefresh}>
            ${refreshing ? 'Refreshing…' : 'Refresh now'}
          </button>
        </div>
      </div>
    </div>
  `;
}

function AgentFleetPanel() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [selected, setSelected] = useState(null);
  const [govHealth, setGovHealth] = useState(null);
  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/agent-registry/heartbeats?stale_seconds=600');
      const d = await r.json();
      setData(d);
      setErr(null);
    } catch (e) { if (e.message !== 'Unauthorized') setErr(e.message); }
  }, []);
  const reloadGov = useCallback(async () => {
    try {
      const r = await apiFetch('/api/governor/health');
      const d = await r.json();
      setGovHealth(d);
    } catch (e) { /* silent */ }
  }, []);
  useEffect(() => {
    reload();
    reloadGov();
    const t1 = setInterval(reload, 20000);
    const t2 = setInterval(reloadGov, 30000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [reload, reloadGov]);
  // Esc closes modal
  useEffect(() => {
    if (!selected) return;
    const handler = e => { if (e.key === 'Escape') setSelected(null); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [selected]);
  if (err) return html`<div class="af-panel"><div class="af-h"><div class="af-title">Agent Fleet</div><div class="af-tag">error</div></div><div class="af-empty">${err}</div></div>`;
  if (!data) return html`<div class="af-panel"><div class="af-h"><div class="af-title">Agent Fleet</div><div class="af-tag">loading…</div></div><div class="af-empty">Loading heartbeats…</div></div>`;
  const agents = data.agents || [];
  return html`
    <div class="af-panel">
      <div class="af-h">
        <div class="af-title">Agent Fleet</div>
        <div class="af-tag">${data.checked_at ? new Date(data.checked_at).toLocaleTimeString() : ''} · ${data.total_count} agents</div>
      </div>
      <div class="af-summary">
        <div class="af-stat healthy">Active <strong>${data.active_count}</strong></div>
        <div class="af-stat stale">Stale <strong>${data.stale_count}</strong></div>
        <div class="af-stat">Total <strong>${data.total_count}</strong></div>
        <div class="af-stat">Threshold <strong>${data.stale_threshold_seconds}s</strong></div>
      </div>
      ${agents.length === 0
        ? html`<div class="af-empty">No agents registered yet</div>`
        : html`
          <div class="af-grid">
            ${agents.map(a => {
              const age = a.seconds_since_ping;
              const ageStr = age == null ? '—' : age < 60 ? `${age}s ago` : age < 3600 ? `${Math.floor(age/60)}m ago` : `${Math.floor(age/3600)}h ago`;
              return html`
                <div class=${'af-card' + (a.is_stale ? ' stale' : '')} onClick=${() => setSelected(a)}>
                  <div class=${'af-dot ' + (a.is_stale ? 'red' : 'green')}></div>
                  <div class="af-card-body">
                    <div class="af-card-name">${a.agent_name || 'unknown'}</div>
                    <div class=${'af-card-meta' + (a.is_stale ? ' stale' : '')}>
                      ${a.status || '?'} · ${ageStr}${a.is_stale ? ' · STALE' : ''}
                    </div>
                    ${a.capabilities && a.capabilities.length > 0 ? html`
                      <div class="af-card-caps">
                        ${a.capabilities.slice(0, 4).map(c => html`<span class="af-cap" key=${c}>${c}</span>`)}
                      </div>
                    ` : null}
                  </div>
                </div>
              `;
            })}
          </div>
        `}
      ${selected ? html`<${AgentDetailModal} agent=${selected} govHealth=${govHealth} onClose=${() => setSelected(null)} />` : null}
    </div>
  `;
}



// ── STRATEGIST ── Strategic intelligence agent

// ── BRAIN PERSONALITY ── Operator-configurable persona per niche������
function Personality() {
  const [data, setData] = useState(null);
  const [niche, setNiche] = useState('__global__');
  const [persona, setPersona] = useState('balanced');
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [history, setHistory] = useState([]);
  const [tab, setTab] = useState('config');
  const [confThresh, setConfThresh] = useState(0.6);
  const [tempVal, setTempVal] = useState(0.1);
  const [urgFloor, setUrgFloor] = useState(5);
  const [promptSuffix, setPromptSuffix] = useState('');
  const [operatorId, setOperatorId] = useState('');
  const [opOverrides, setOpOverrides] = useState({});
  const [opTab, setOpTab] = useState('global');

  const reload = useCallback(async () => {
    try {
      const [snap, hist] = await Promise.all([
        apiFetch('/api/brain/personality/snapshot').then(r => r.json()),
        apiFetch('/api/brain/personality/history').then(r => r.json()),
      ]);
      setData(snap);
      setHistory(hist.entries || []);
      const c = (snap.configs || {})[niche] || snap.configs['__global__'] || {};
      setConfThresh(c.confidence_threshold || 0.6);
      setTempVal(c.temperature || 0.1);
      setUrgFloor(c.urgency_floor || 5);
      setPersona(c.persona || 'balanced');
    } catch (e) {
      if (e.message !== 'Unauthorized') console.error(e);
    }
  }, [niche]);

  const loadOperatorOverrides = async (opId) => {
    if (!opId) { setOpOverrides({}); return; }
    try {
      const r = await apiFetch('/api/brain/personality/operator/' + encodeURIComponent(opId)).then(r => r.json());
      setOpOverrides(r.overrides || {});
    } catch (e) { console.error(e); }
  };

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (!data) return;
    const c = (tab === 'operator' ? (opOverrides[niche] || opOverrides['__global__'] || {}) : (data.configs || {})[niche] || data.configs['__global__'] || {});
    setConfThresh(c.confidence_threshold != null ? c.confidence_threshold : 0.6);
    setTempVal(c.temperature != null ? c.temperature : 0.1);
    setUrgFloor(c.urgency_floor != null ? c.urgency_floor : 5);
    setPersona(c.persona || 'balanced');
    setPromptSuffix(c.custom_prompt_suffix || '');
  }, [niche, data, opOverrides, tab]);

  const save = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      let url = '/api/brain/personality/set';
      let body = { niche, persona, confidence_threshold: confThresh, urgency_floor: urgFloor, temperature: tempVal, custom_prompt_suffix: promptSuffix };
      if (tab === 'operator' && operatorId) {
        url = '/api/brain/personality/operator/set';
        body.operator_id = operatorId;
      }
      const r = await apiFetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      }).then(r => r.json());
      setSaveMsg(r.ok ? 'Saved' : 'Error: ' + (r.error || 'unknown'));
      if (r.ok && tab === 'operator') loadOperatorOverrides(operatorId);
      else if (r.ok) reload();
    } catch (e) {
      setSaveMsg('Error: ' + e.message);
    }
    setSaving(false);
  };

  const removeOpOverride = async (n) => {
    if (!operatorId) return;
    try {
      await apiFetch('/api/brain/personality/operator/remove', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ operator_id: operatorId, niche: n }),
      });
      loadOperatorOverrides(operatorId);
    } catch (e) { console.error(e); }
  };

  if (!data) return html`<div class="stub"><div class="stub-body">Loading personality...</div></div>`;

  const configs = data.configs || {};
  const profiles = data.profiles_available || [];
  const details = data.profile_details || {};
  const nicheKeys = Object.keys(configs).filter(k => k !== '__global__').sort();
  const globCfg = configs['__global__'] || {};

  const slider = (label, val, setter, min, max, step, color) => html`
    <div class="fld">
      <div style=${{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <div class="fld-lbl">${label}</div>
        <span style=${{fontFamily:'var(--font-mono)',fontSize:'12px',color: color || 'var(--signal-teal)',fontWeight:500}}>${typeof val === 'number' ? (step < 1 ? val.toFixed(3) : val) : val}</span>
      </div>
      <input type="range" min=${min} max=${max} step=${step} value=${val}
        onInput=${e => { const v = parseFloat(e.target.value); setter(v); }}
        style=${{width:'100%',height:'4px',appearance:'none',background:'var(--empire-elevated)',borderRadius:'2px',outline:'none',cursor:'pointer'}} />
    </div>
  `;

  return html`
    <div class="section-h">
      <div>
        <div class="section-title">Brain <em>Personality</em></div>
        <div class="section-sub">Configure brain persona per niche \u00b7 thresholds \u00b7 tone</div>
      </div>
      <div class="topbar-actions">
        <button class="pulse-tab" style=${{opacity: saveMsg ? 1 : 0.5,fontSize:'10px'}}>${saveMsg || 'Idle'}</button>
      </div>
    </div>

    <div class="pulse-tabs" style=${{marginTop:'8px'}}>
      <button class=${"pulse-tab " + (tab === 'config' ? 'active' : '')} onClick=${() => { setTab('config'); setOpTab('global'); }}>Configuration</button>
      <button class=${"pulse-tab " + (tab === 'profiles' ? 'active' : '')} onClick=${() => setTab('profiles')}>Profiles</button>
      <button class=${"pulse-tab " + (tab === 'operator' ? 'active' : '')} onClick=${() => setTab('operator')}>Per-Operator</button>
      <button class=${"pulse-tab " + (tab === 'history' ? 'active' : '')} onClick=${() => setTab('history')}>History</button>
    </div>

    ${tab === 'config' ? html`
    <div class="pipeline-breakdown" style=${{marginTop:'16px'}}>
      <div class="pipeline-h">
        <div class="pipeline-title">Per-Niche <strong>Configuration</strong></div>
        <div class="pipeline-total">${nicheKeys.length + 1} configs \u00b7 ${profiles.length} profiles</div>
      </div>

      <div style=${{display:'flex',gap:'12px',alignItems:'center',marginBottom:'16px',padding:'14px 16px',background:'var(--empire-surface)',border:'1px solid var(--empire-border)'}}>
        <select value=${niche} onChange=${e => { setNiche(e.target.value); }} style=${{flex:1,padding:'8px 10px',background:'var(--empire-elevated)',border:'1px solid var(--empire-border)',color:'var(--empire-mist)',fontFamily:'var(--font-mono)',fontSize:'11px',outline:'none'}}>
          <option value="__global__">__global__ (default)</option>
          ${nicheKeys.map(k => html`<option value=${k} key=${k}>${k}</option>`)}
        </select>
        <div style=${{display:'flex',gap:'4px'}}>
          ${profiles.map(p => html`
            <button class=${"pulse-tab " + (persona === p ? 'active' : '')} style=${{fontSize:'9px',padding:'5px 10px'}} onClick=${() => setPersona(p)} key=${p}>${p}</button>
          `)}
        </div>
      </div>

      <div class="split" style=${{marginBottom:'12px'}}>
        <div class="panel">
          <div class="panel-head">Thresholds</div>
          ${slider('Confidence Threshold', confThresh, setConfThresh, 0.0, 1.0, 0.01, 'var(--signal-teal)')}
          ${slider('Temperature', tempVal, setTempVal, 0.0, 1.0, 0.01, 'var(--strike-cyan)')}
          ${slider('Urgency Floor', urgFloor, setUrgFloor, 1, 10, 1, 'var(--status-amber)')}
        </div>
        <div class="panel">
          <div class="panel-head">Custom Prompt Suffix</div>
          <textarea value=${promptSuffix} onInput=${e => setPromptSuffix(e.target.value)}
            style=${{width:'100%',minHeight:'80px',background:'var(--empire-elevated)',border:'1px solid var(--empire-border)',padding:'8px 10px',color:'var(--empire-silver)',fontFamily:'var(--font-mono)',fontSize:'10px',outline:'none',resize:'vertical'}}
            placeholder="Extra instructions appended to brain prompt for this niche..." />
          <div style=${{marginTop:'8px'}}>
            <button class="btn" style=${{fontSize:'10px',padding:'8px 16px'}} onClick=${save} disabled=${saving}>${saving ? 'Saving...' : 'Apply Configuration'}</button>
          </div>
        </div>
      </div>

      <div class="panel" style=${{marginTop:'8px'}}>
        <div class="panel-head">System Prompt Preview <span style=${{color:'var(--empire-fog)',fontWeight:400}}>(simulated for ${niche})</span></div>
        <pre style=${{background:'var(--empire-elevated)',border:'1px solid var(--empire-divider)',padding:'12px 14px',color:'var(--empire-silver)',fontFamily:'var(--font-mono)',fontSize:'9px',lineHeight:'1.6',overflowX:'auto',whiteSpace:'pre-wrap',maxHeight:'200px',overflowY:'auto'}}>${data.prompt_preview || 'No preview available'}</pre>
      </div>

      <table class="tbl" style=${{width:'100%',fontSize:'10px',marginTop:'16px'}}>
        <thead>
          <tr>
            <th>Niche</th>
            <th>Persona</th>
            <th style=${{textAlign:'right'}}>Conf Threshold</th>
            <th style=${{textAlign:'right'}}>Urgency</th>
            <th style=${{textAlign:'right'}}>Temp</th>
            <th>Notes</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          <tr style=${{background:'rgba(68,229,184,0.04)',fontWeight:500}}>
            <td>__global__</td>
            <td><span class="rv-bar-lane">${globCfg.persona || 'balanced'}</span></td>
            <td class="tbl-num">${(globCfg.confidence_threshold || 0.6).toFixed(3)}</td>
            <td class="tbl-num">${globCfg.urgency_floor || 5}</td>
            <td class="tbl-num">${(globCfg.temperature || 0.1).toFixed(3)}</td>
            <td style=${{color:'var(--empire-fog)',fontSize:'9px'}}>${(globCfg.operator_notes || '') || '-'}</td>
            <td><span class="bdg active" style=${{fontSize:'8px'}}>global</span></td>
          </tr>
          ${nicheKeys.map(n => {
            const c = configs[n] || {};
            return html`<tr key=${n}>
              <td>${n}</td>
              <td><span class="rv-bar-lane">${c.persona || 'balanced'}</span></td>
              <td class="tbl-num">${(c.confidence_threshold || 0.6).toFixed(3)}</td>
              <td class="tbl-num">${c.urgency_floor || 5}</td>
              <td class="tbl-num">${(c.temperature || 0.1).toFixed(3)}</td>
              <td style=${{color:'var(--empire-fog)',fontSize:'9px'}}>${(c.operator_notes || '') || '-'}</td>
              <td><span class="bdg active" style=${{fontSize:'8px'}}>global</span></td>
            </tr>`;
          })}
        </tbody>
      </table>
    </div>
    ` : null}

    ${tab === 'profiles' ? html`
    <div class="pipeline-breakdown" style=${{marginTop:'16px'}}>
      <div class="pipeline-h">
        <div class="pipeline-title">Available <strong>Personalities</strong></div>
        <div class="pipeline-total">${profiles.length} profiles</div>
      </div>
      <div style=${{display:'flex',gap:'16px',flexWrap:'wrap'}}>
        ${profiles.map(p => {
          const pd = details[p] || {};
          const isActive = persona === p;
          return html`
          <div class="stat-card" style=${{flex:'1',minWidth:'180px',cursor:'pointer',borderColor: isActive ? 'var(--signal-teal)' : 'var(--empire-border)', opacity: isActive ? 1 : 0.7}} onClick=${() => setPersona(p)} key=${p}>
            <div class="stat-label">${pd.label || p}</div>
            <div class="stat-meta" style=${{color:'var(--empire-mist)',fontSize:'11px',marginBottom:'12px'}}>${pd.description || ''}</div>
            ${pd.confidence_threshold != null ? html`
            <div style=${{display:'flex',flexDirection:'column',gap:'8px'}}>
              <div style=${{display:'flex',justifyContent:'space-between',fontFamily:'var(--font-mono)',fontSize:'10px'}}>
                <span style=${{color:'var(--empire-fog)'}}>Confidence</span>
                <span style=${{color: isActive ? 'var(--signal-teal)' : 'var(--empire-mist)'}}>${pd.confidence_threshold.toFixed(2)}</span>
              </div>
              <div style=${{height:'3px',background:'var(--empire-elevated)',borderRadius:'2px',overflow:'hidden'}}>
                <div style=${{height:'100%',width: (pd.confidence_threshold * 100) + '%',background: isActive ? 'var(--signal-teal)' : 'var(--empire-fog)',borderRadius:'2px',transition:'width 0.4s var(--ease-out-empire)'}}></div>
              </div>
              <div style=${{display:'flex',justifyContent:'space-between',fontFamily:'var(--font-mono)',fontSize:'10px'}}>
                <span style=${{color:'var(--empire-fog)'}}>Temperature</span>
                <span style=${{color: isActive ? 'var(--signal-teal)' : 'var(--empire-mist)'}}>${pd.temperature != null ? pd.temperature.toFixed(2) : '0.10'}</span>
              </div>
              <div style=${{display:'flex',justifyContent:'space-between',fontFamily:'var(--font-mono)',fontSize:'10px'}}>
                <span style=${{color:'var(--empire-fog)'}}>Fallback</span>
                <span style=${{color: pd.go_fallback === 'GO' ? 'var(--status-amber)' : 'var(--empire-mist)'}}>${pd.go_fallback || 'NO_GO'}</span>
              </div>
            </div>
            ` : null}
            ${isActive ? html`<div style=${{marginTop:'10px',fontSize:'9px',color:'var(--signal-teal)',fontFamily:'var(--font-mono)',letterSpacing:'0.08em'}}>ACTIVE</div>` : null}
          </div>
          `;
        })}
      </div>
      <div style=${{marginTop:'20px'}}>
        <div class="panel-head" style=${{marginBottom:'12px'}}>Tone Instructions <span style=${{color:'var(--empire-fog)',fontWeight:400}}>(what the LLM sees)</span></div>
        ${profiles.map(p => {
          const pd = details[p] || {};
          const isActive = persona === p;
          return html`
            <div style=${{marginBottom:'10px',padding:'10px 14px',background: isActive ? 'var(--empire-surface)' : 'var(--empire-elevated)',border:'1px solid ' + (isActive ? 'var(--signal-teal-soft)' : 'var(--empire-divider)'),borderRadius:'6px'}} key=${p}>
              <div style=${{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'6px'}}>
                <strong style=${{color:'var(--empire-white)',fontSize:'12px'}}>${pd.label || p}</strong>
                <span style=${{fontFamily:'var(--font-mono)',fontSize:'9px',color: isActive ? 'var(--signal-teal)' : 'var(--empire-fog)'}}>${p}</span>
              </div>
              <div style=${{fontFamily:'var(--font-mono)',fontSize:'9px',color:'var(--empire-silver)',lineHeight:'1.6',whiteSpace:'pre-wrap'}}>
                ${pd.tone_instruction || ""}
              </div>
            </div>`;
        })}
      </div>
    </div>
    ` : null}

    ${tab === 'operator' ? html`
    <div class="pipeline-breakdown" style=${{marginTop:'16px'}}>
      <div class="pipeline-h">
        <div class="pipeline-title">Per-Operator <strong>Overrides</strong></div>
        <div class="pipeline-total">Override global personality per operator</div>
      </div>

      <div style=${{display:'flex',gap:'12px',alignItems:'center',marginBottom:'16px',padding:'14px 16px',background:'var(--empire-surface)',border:'1px solid var(--empire-border)'}}>
        <div class="fld" style=${{flex:1,margin:0}}>
          <div class="fld-lbl" style=${{marginBottom:'4px'}}>Operator ID</div>
          <input class="fld-in mono" value=${operatorId} onInput=${e => { setOperatorId(e.target.value); loadOperatorOverrides(e.target.value); }} placeholder="Paste operator UUID..." style=${{width:'100%'}} />
        </div>
      </div>

      ${operatorId ? html`
      <div style=${{marginBottom:'16px'}}>
        <div class="pulse-tabs" style=${{borderBottom:'1px solid var(--empire-divider)',marginBottom:'12px'}}>
          <button class=${"pulse-tab " + (opTab === 'global' ? 'active' : '')} onClick=${() => setOpTab('global')}>Global Override</button>
          <button class=${"pulse-tab " + (opTab === 'niche' ? 'active' : '')} onClick=${() => setOpTab('niche')}>Per-Niche Override</button>
          <button class=${"pulse-tab " + (opTab === 'active' ? 'active' : '')} onClick=${() => setOpTab('active')}>Active Overrides</button>
        </div>

        ${opTab === 'global' ? html`
        <div class="panel">
          <div class="panel-head">Operator Global Default</div>
          <div style=${{display:'flex',gap:'12px',alignItems:'center',marginBottom:'12px'}}>
            ${profiles.map(p => html`
              <button class=${"pulse-tab " + (persona === p ? 'active' : '')} style=${{fontSize:'9px',padding:'5px 10px'}} onClick=${() => setPersona(p)} key=${p}>${p}</button>
            `)}
          </div>
          ${slider('Confidence Threshold', confThresh, setConfThresh, 0.0, 1.0, 0.01)}
          ${slider('Temperature', tempVal, setTempVal, 0.0, 1.0, 0.01)}
          <div style=${{marginTop:'10px'}}>
            <button class="btn" style=${{fontSize:'10px',padding:'8px 16px'}} onClick=${save} disabled=${saving}>${saving ? 'Saving...' : 'Set Global Override'}</button>
          </div>
        </div>
        ` : null}

        ${opTab === 'niche' ? html`
        <div class="panel">
          <div class="panel-head">Per-Niche Override</div>
          <div style=${{display:'flex',gap:'12px',alignItems:'center',marginBottom:'12px'}}>
            <select value=${niche} onChange=${e => setNiche(e.target.value)} style=${{padding:'8px 10px',background:'var(--empire-elevated)',border:'1px solid var(--empire-border)',color:'var(--empire-mist)',fontFamily:'var(--font-mono)',fontSize:'11px',outline:'none',flex:1}}>
              <option value="__global__">__global__</option>
              ${nicheKeys.map(k => html`<option value=${k} key=${k}>${k}</option>`)}
            </select>
          </div>
          <div style=${{display:'flex',gap:'4px',marginBottom:'12px'}}>
            ${profiles.map(p => html`
              <button class=${"pulse-tab " + (persona === p ? 'active' : '')} style=${{fontSize:'9px',padding:'5px 10px'}} onClick=${() => setPersona(p)} key=${p}>${p}</button>
            `)}
          </div>
          ${slider('Confidence Threshold', confThresh, setConfThresh, 0.0, 1.0, 0.01)}
          ${slider('Temperature', tempVal, setTempVal, 0.0, 1.0, 0.01)}
          <div style=${{marginTop:'10px'}}>
            <button class="btn" style=${{fontSize:'10px',padding:'8px 16px'}} onClick=${save} disabled=${saving}>${saving ? 'Saving...' : 'Set Niche Override'}</button>
          </div>
        </div>
        ` : null}

        ${opTab === 'active' ? html`
        <div class="panel">
          <div class="panel-head">Active Operator Overrides</div>
          ${Object.keys(opOverrides).length === 0 ? html`
            <div class="stub" style=${{padding:'24px 14px'}}><div class="stub-body">No operator overrides for this operator</div></div>
          ` : html`
          <table class="tbl" style=${{width:'100%',fontSize:'10px'}}>
            <thead><tr><th>Niche</th><th>Persona</th><th style=${{textAlign:'right'}}>Conf</th><th style=${{textAlign:'right'}}>Temp</th><th></th></tr></thead>
            <tbody>
              ${Object.entries(opOverrides).map(([n, c]) => html`<tr key=${n}>
                <td>${n}</td>
                <td><span class="rv-bar-lane">${c.persona || 'balanced'}</span></td>
                <td class="tbl-num">${(c.confidence_threshold || 0.6).toFixed(3)}</td>
                <td class="tbl-num">${(c.temperature || 0.1).toFixed(3)}</td>
                <td><button class="tbl-action danger" onClick=${() => removeOpOverride(n)}>Remove</button></td>
              </tr>`)}
            </tbody>
          </table>
          `}
        </div>
        ` : null}
      </div>
      ` : html`
      <div class="stub" style=${{padding:'32px 20px'}}><div class="stub-body">Enter an Operator ID above to configure per-operator personality overrides</div></div>
      `}
    </div>
    ` : null}

    ${tab === 'history' ? html`
    <div class="pipeline-breakdown" style=${{marginTop:'16px'}}>
      <div class="pipeline-h">
        <div class="pipeline-title">Operator Preference <strong>Log</strong></div>
        <div class="pipeline-total">${history.length} changes</div>
      </div>
      ${history.length === 0 ? html`
        <div class="stub" style=${{padding:'24px 14px'}}><div class="stub-body">No preference changes logged yet</div></div>
      ` : html`
      <div style=${{maxHeight:'500px',overflowY:'auto'}}>
      <table class="tbl" style=${{width:'100%',fontSize:'10px'}}>
        <thead><tr><th>Time</th><th>Operator</th><th>Niche</th><th>Field</th><th>From</th><th>To</th></tr></thead>
        <tbody>
          ${history.map((h, i) => html`<tr key=${i}>
            <td style=${{fontFamily:'var(--font-mono)',fontSize:'9px',whiteSpace:'nowrap'}}>${(h.created_at || '').slice(11,19)}</td>
            <td style=${{fontSize:'9px'}}>${(h.operator_id || '').slice(0,8)}</td>
            <td style=${{fontSize:'10px'}}>${h.niche}</td>
            <td><span class="rv-bar-lane">${h.field}</span></td>
            <td style=${{color:'var(--empire-fog)',fontFamily:'var(--font-mono)',fontSize:'9px',wordBreak:'break-all',maxWidth:'120px'}}>${h.old_value || '-'}</td>
            <td style=${{color:'var(--signal-teal)',fontFamily:'var(--font-mono)',fontSize:'9px',wordBreak:'break-all',maxWidth:'120px'}}>${h.new_value || '-'}</td>
          </tr>`)}
        </tbody>
      </table>
      </div>
      `}
    </div>
    ` : null}
  `;
}
function Strategist() {
  const [data, setData] = useState(null);
  const [niche, setNiche] = useState(null);
  const [nicheDetail, setNicheDetail] = useState(null);
  const [narrative, setNarrative] = useState(null);
  const [tab, setTab] = useState('overview');
  const [err, setErr] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [ov, rc, tr, na] = await Promise.all([
        apiFetch('/api/strategist/overview').then(r => r.json()),
        apiFetch('/api/strategist/recommendations').then(r => r.json()),
        apiFetch('/api/strategist/trends').then(r => r.json()),
        apiFetch('/api/strategist/narrative').then(r => r.json()),
      ]);
      setData({overview: ov, recommendations: rc, trends: tr});
      setNarrative(na);
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);

  useEffect(() => { reload(); const iv = setInterval(reload, 30000); return () => clearInterval(iv); }, [reload]);
  useEffect(() => {
    if (niche) {
      apiFetch('/api/strategist/niche/' + encodeURIComponent(niche)).then(r => r.json()).then(setNicheDetail).catch(() => {});
    } else {
      setNicheDetail(null);
    }
  }, [niche]);

  if (err) return html`<div class="stub"><div class="stub-title">Strategist Error</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading strategist...</div></div>`;

  const niches = (data.overview?.by_niche || []);
  const maxScore = niches.reduce((m, n) => Math.max(m, n.strategy_score || 0), 0);

  return html`
    <div class="section-header"><div><div class="section-title"><em>Strategist</em></div><div class="section-sub">Strategic intelligence · niche analysis · narratives</div></div></div>
    <div class="pulse-tabs" style={{marginTop:'8px'}}>
      <button class=${'pulse-tab' + (tab==='overview' ? ' active' : '')} onClick=${()=>setTab('overview')}>Overview</button>
      <button class=${'pulse-tab' + (tab==='niches' ? ' active' : '')} onClick=${()=>setTab('niches')}>Niches</button>
      <button class=${'pulse-tab' + (tab==='recommendations' ? ' active' : '')} onClick=${()=>setTab('recommendations')}>Recommendations</button>
      <button class=${'pulse-tab' + (tab==='narrative' ? ' active' : '')} onClick=${()=>setTab('narrative')}>Narrative</button>
    </div>

    ${tab === 'overview' ? html`
    <div class="pulse-grid" style={{marginTop:'12px'}}>
      <div class="stat-card"><div class="stat-label">NICHES TRACKED</div><div class="stat-value teal">${data.overview?.niche_count || 0}</div></div>
      <div class="stat-card"><div class="stat-label">AVG STRATEGY SCORE</div><div class="stat-value" style="color:var(--strike-cyan)">${((data.overview?.avg_score||0)*100).toFixed(0)}%</div></div>
      <div class="stat-card"><div class="stat-label">TRENDS ACTIVE</div><div class="stat-value">${(data.trends?.trends||[]).length}</div></div>
      <div class="stat-card"><div class="stat-label">RECOMMENDATIONS</div><div class="stat-value teal">${(data.recommendations?.recommendations||[]).length}</div></div>
    </div>
    ` : null}

    ${tab === 'niches' ? html`
    <div class="pipeline-breakdown" style={{marginTop:'12px'}}>
      <div class="pipeline-h"><div class="pipeline-title">Niche <strong>Strategy Scores</strong></div></div>
      ${niches.length > 0 ? niches.map(n => html`
        <div class="rv-bar-row" key=${n.name} style={{cursor:'pointer'}} onClick=${()=>{ setNiche(n.name); setTab('recommendations'); }}>
          <div class="rv-bar-label"><span class="rv-bar-lane">${(n.name||'').slice(0,22)}</span><span class="rv-bar-niche">${n.strategy||'no strategy'}</span></div>
          <div class="rv-bar-track"><div class="rv-bar-fill" style=${{width:maxScore>0?Math.round((n.strategy_score||0)/maxScore*100)+'%':'0%', backgroundColor:'var(--signal-teal)'}}></div></div>
          <div class="rv-bar-val">${((n.strategy_score||0)*100).toFixed(0)}%</div>
          <div class="rv-bar-meta">${n.win_rate||0}% win</div>
        </div>
      `) : html`<div class="stub-body">No niche data available</div>`}
    </div>
    ` : null}

    ${tab === 'recommendations' ? html`
      ${niche ? html`
      <div class="pipeline-breakdown" style={{marginTop:'12px'}}>
        <div class="pipeline-h"><div class="pipeline-title">Deep Analysis: <strong>${niche}</strong></div><button class="agi-replay-btn" onClick=${()=>{setNiche(null);}}>All niches</button></div>
        ${nicheDetail ? html`
          <div class="pulse-grid">
            <div class="stat-card"><div class="stat-label">STRATEGY SCORE</div><div class="stat-value teal">${((nicheDetail.strategy_score||0)*100).toFixed(0)}%</div></div>
            <div class="stat-card"><div class="stat-label">WIN RATE</div><div class="stat-value" style="color:var(--strike-cyan)">${(nicheDetail.win_rate||0).toFixed(0)}%</div></div>
            <div class="stat-card"><div class="stat-label">TRIALS</div><div class="stat-value">${nicheDetail.trials||0}</div></div>
            <div class="stat-card"><div class="stat-label">GENOME</div><div class="stat-value teal" style="font-size:12px">${nicheDetail.genome||'--'}</div></div>
          </div>
          ${nicheDetail.genome_traits ? html`
          <div class="pipeline-breakdown" style={{marginTop:'16px'}}>
            <div class="pipeline-h"><div class="pipeline-title">Genome <strong>Traits</strong></div></div>
            ${Object.entries(nicheDetail.genome_traits).map(([trait, val]) => html`
              <div class="rv-bar-row" key=${trait}>
                <div class="rv-bar-label"><span class="rv-bar-lane">${(trait||'').slice(0,22)}</span></div>
                <div class="rv-bar-track"><div class="rv-bar-fill" style=${{width:Math.round(Math.min(1,Math.max(0,val||0))*100)+'%', backgroundColor:'var(--strike-cyan)'}}></div></div>
                <div class="rv-bar-val">${(val||0).toFixed(2)}</div>
              </div>
            `)}
          </div>
          ` : null}
        ` : html`<div class="stub-body" style={{padding:'24px'}}>Click a niche card in the Niches tab to see deep strategy analysis.</div>`}
      </div>
      ` : html`
      <div class="pipeline-breakdown" style={{marginTop:'12px'}}>
        <div class="pipeline-h"><div class="pipeline-title">Strategic <strong>Recommendations</strong></div></div>
        ${(data.recommendations?.recommendations||[]).map((r,i) => html`
          <div key=${i} style={{padding:'12px 14px', borderBottom:'1px solid var(--empire-border)', fontSize:'12px', lineHeight:1.6}}>
            <span style={{color:'var(--signal-teal)', fontFamily:'var(--font-mono)', fontSize:'10px', fontWeight:600, textTransform:'uppercase', marginRight:8}}>${r.priority||'INFO'}</span>
            ${r.text || r.recommendation || ''}
            <div style={{marginTop:4, fontSize:'10px', color:'var(--empire-fog)'}}>${r.niche ? 'Niche: ' + r.niche : ''} ${r.expected_impact ? '· Impact: ' + r.expected_impact : ''}</div>
          </div>
        `)}
        ${!(data.recommendations?.recommendations||[]).length ? html`<div class="stub-body">No recommendations yet.</div>` : null}
      </div>
      `}
    ` : null}

    ${tab === 'narrative' ? html`
    <div style={{marginTop:'12px', padding:'20px 24px', background:'rgba(15,23,42,0.5)', border:'1px solid var(--empire-border)', borderRadius:12, lineHeight:1.8, fontSize:'13px'}}>
      ${narrative?.narrative ? narrative.narrative.split('\n').map((p,i) => html`<p key=${i} style={{marginBottom:12}}>${p}</p>`) : html`<div class="stub-body">No narrative generated yet.</div>`}
      ${narrative?.key_insights ? html`<div style={{marginTop:16}}><strong style={{color:'var(--signal-teal)'}}>Key Insights:</strong><ul>${narrative.key_insights.map((ins,i) => html`<li key=${i} style={{marginTop:6}}>${ins}</li>`)}</ul></div>` : null}
      ${narrative?.timestamp ? html`<div style={{marginTop:16, fontSize:'9px', color:'var(--empire-fog)', fontFamily:'var(--font-mono)'}}>Generated: ${narrative.timestamp}</div>` : null}
    </div>
    ` : null}
  `;
}

// ── ANALYTICS ── Analytics intelligence agent
function Analytics() {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('overview');
  const [metric, setMetric] = useState('revenue');
  const [err, setErr] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [kp, fn, ts, an, ex] = await Promise.all([
        apiFetch('/api/analytics/kpi').then(r => r.json()),
        apiFetch('/api/analytics/funnel').then(r => r.json()),
        apiFetch('/api/analytics/timeseries?metric=' + metric + '&days=14').then(r => r.json()),
        apiFetch('/api/analytics/anomalies').then(r => r.json()),
        apiFetch('/api/analytics/export').then(r => r.json()),
      ]);
      setData({kpi: kp, funnel: fn, timeseries: ts, anomalies: an, export: ex});
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, [metric]);

  useEffect(() => { reload(); const iv = setInterval(reload, 30000); return () => clearInterval(iv); }, [reload]);

  if (err) return html`<div class="stub"><div class="stub-title">Analytics Error</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading analytics...</div></div>`;

  const kpi = data.kpi || {};
  const funnel = data.funnel || {};
  const ts = data.timeseries || {};
  const anomalies = data.anomalies || {};
  const series = ts.series || [];
  const maxVal = series.reduce((m, p) => Math.max(m, p.value||0), 0);
  const anomalyList = anomalies.anomalies || [];

  return html`
    <div class="section-header"><div><div class="section-title"><em>Analytics</em></div><div class="section-sub">KPIs · funnel · trends · anomalies</div></div></div>
    <div class="pulse-tabs" style={{marginTop:'8px'}}>
      <button class=${'pulse-tab' + (tab==='overview' ? ' active' : '')} onClick=${()=>setTab('overview')}>Overview</button>
      <button class=${'pulse-tab' + (tab==='funnel' ? ' active' : '')} onClick=${()=>setTab('funnel')}>Funnel</button>
      <button class=${'pulse-tab' + (tab==='trends' ? ' active' : '')} onClick=${()=>setTab('trends')}>Trends</button>
      <button class=${'pulse-tab' + (tab==='anomalies' ? ' active' : '')} onClick=${()=>setTab('anomalies')}>Anomalies</button>
    </div>

    ${tab === 'overview' ? html`
    <div class="pulse-grid" style={{marginTop:'12px'}}>
      <div class="stat-card"><div class="stat-label">TOTAL REVENUE</div><div class="stat-value teal">${(kpi.total_revenue||0).toLocaleString()}</div></div>
      <div class="stat-card"><div class="stat-label">TOTAL CALLS</div><div class="stat-value" style="color:var(--strike-cyan)">${kpi.total_calls||0}</div></div>
      <div class="stat-card"><div class="stat-label">CONVERSION RATE</div><div class="stat-value teal">${((kpi.conversion_rate||0)*100).toFixed(1)}%</div></div>
      <div class="stat-card"><div class="stat-label">ACTIVE LEADS</div><div class="stat-value">${kpi.active_leads||0}</div></div>
    </div>
    ${kpi.health_score != null ? html`
    <div class="stat-card" style={{marginTop:'8px'}}>
      <div class="stat-label">SYSTEM HEALTH</div>
      <div class="stat-value" style="color:${(kpi.health_score||0) > 0.7 ? 'var(--signal-teal)' : (kpi.health_score||0) > 0.4 ? '#FFB800' : '#FF4444'}">${((kpi.health_score||0)*100).toFixed(0)}%</div>
    </div>
    ` : null}
    ` : null}

    ${tab === 'funnel' ? html`
    <div class="pipeline-breakdown" style={{marginTop:'12px'}}>
      <div class="pipeline-h"><div class="pipeline-title">Conversion <strong>Funnel</strong></div></div>
      ${['impressions','qualifications','outreaches','responses','deals'].map((stage, i) => {
        const val = funnel[stage] || 0;
        const prev = funnel[['impressions','qualifications','outreaches','responses','deals'][i-1]];
        const drop = prev ? ((prev - val) / prev * 100).toFixed(0) : null;
        return html`
          <div class="rv-bar-row" key=${stage}>
            <div class="rv-bar-label"><span class="rv-bar-lane">${stage.charAt(0).toUpperCase() + stage.slice(1)}</span></div>
            <div class="rv-bar-track"><div class="rv-bar-fill" style=${{width:Math.round((val/(funnel.impressions||1))*100)+'%', backgroundColor:i===4?'var(--signal-teal)':i===3?'var(--strike-cyan)':'rgba(68,229,184,0.2)'}}></div></div>
            <div class="rv-bar-val">${val}</div>
            <div class="rv-bar-meta">${drop ? '-' + drop + '% drop' : ''}</div>
          </div>
        `;
      })}
    </div>
    ` : null}

    ${tab === 'trends' ? html`
    <div class="pipeline-breakdown" style={{marginTop:'12px'}}>
      <div class="pipeline-h">
        <div class="pipeline-title">Time Series: <strong>${metric}</strong></div>
        <div class="topbar-actions">
          ${['revenue','calls','conversions'].map(m => html`
            <button class=${'pulse-tab ' + (metric===m?'active':'')} style={{fontSize:'9px',padding:'4px 10px'}} onClick=${()=>setMetric(m)}>${m}</button>
          `)}
        </div>
      </div>
      <div style={{padding:'16px 0'}}>
        ${series.map((p, i) => html`
          <div class="rv-bar-row" key=${i}>
            <div class="rv-bar-label"><span class="rv-bar-lane" style={{fontSize:'9px',minWidth:'70px'}}>${(p.date||'').slice(5,10)}</span></div>
            <div class="rv-bar-track"><div class="rv-bar-fill" style=${{width:maxVal>0?Math.round((p.value||0)/maxVal*100)+'%':'0%', backgroundColor:'var(--signal-teal)', opacity:0.7}}></div></div>
            <div class="rv-bar-val" style={{fontSize:'10px'}}>${(p.value||0).toLocaleString()}</div>
          </div>
        `)}
        ${series.length === 0 ? html`<div class="stub-body">No time series data yet.</div>` : null}
      </div>
    </div>
    ` : null}

    ${tab === 'anomalies' ? html`
    <div class="pipeline-breakdown" style={{marginTop:'12px'}}>
      <div class="pipeline-h"><div class="pipeline-title">Detected <strong>Anomalies</strong></div></div>
      ${anomalyList.map((a, i) => html`
        <div key=${i} style={{padding:'12px 14px', borderBottom:'1px solid var(--empire-border)'}}>
          <div style={{display:'flex', justifyContent:'space-between', marginBottom:4}}>
            <span style={{color:'var(--signal-teal)', fontWeight:600, fontSize:'12px'}}>${a.metric||a.type||'Anomaly'}</span>
            <span style={{fontFamily:'var(--font-mono)', fontSize:'10px', color:a.severity==='high'?'#FF4444':a.severity==='medium'?'#FFB800':'var(--empire-fog)'}}>${(a.severity||'info').toUpperCase()}</span>
          </div>
          <div style={{fontSize:'11px', color:'var(--empire-fog)', lineHeight:1.5}}>${a.message || a.description || ''}</div>
          ${a.date ? html`<div style={{marginTop:4, fontSize:'9px', fontFamily:'var(--font-mono)', color:'var(--empire-fog)', opacity:0.5}}>${a.date}</div>` : null}
        </div>
      `)}
      ${anomalyList.length === 0 ? html`<div class="stub-body">No anomalies detected.</div>` : null}
    </div>
    ` : null}
  `;
}

function HealthMonitor() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [dhealth, setDhealth] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [r, dh] = await Promise.all([
        apiFetch('/api/v1/health/mesh').then(x => x.json()),
        apiFetch('/api/v1/dispatch/health').then(x => x.json()).catch(() => null),
      ]);
      setData(r);
      if (dh && dh.ok) setDhealth(dh);
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 15000);
    return () => clearInterval(t);
  }, [reload]);

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Health Monitor</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading mesh health…</div></div>`;

  const agents = data.agents || [];
  const funnel = data.funnel || {};
  const pm2 = data.pm2 || {};
  const brainCls = data.brain_up ? 'ok' : 'bad';
  const pm2Cls = pm2.healthy === pm2.total ? 'ok' : pm2.healthy > 0 ? 'warn' : 'bad';
  const forecastCls = data.storm_forecasts_count > 0 ? 'ok' : 'warn';
  const overseerRaw = data.overseer ? JSON.stringify(data.overseer, null, 2) : null;

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Health Monitor</div>
          <div class="section-sub">Agent mesh · system health · overseer</div>
        </div>
        <div class="section-sub">Auto-refresh · 15s</div>
      </div>
      ${agents.length > 0 ? html`<div class="chart-panel">
        <div class="chart-panel-h">
          <div class="chart-panel-title">Agent Status</div>
          <div class="chart-panel-tag">${agents.length} agents monitored</div>
        </div>
        ${(() => {
          let active = 0, error = 0, idle = 0, offline = 0, other = 0;
          for (const a of agents) {
            const s = a.status || 'unknown';
            if (s === 'ACTIVE') active++;
            else if (s === 'ERROR') error++;
            else if (s === 'IDLE') idle++;
            else if (s === 'OFFLINE') offline++;
            else other++;
          }
          const sd = [];
          if (active > 0) sd.push({label: 'Active', value: active, color: 'var(--signal-teal)'});
          if (error > 0) sd.push({label: 'Error', value: error, color: 'var(--status-red)'});
          if (idle > 0) sd.push({label: 'Idle', value: idle, color: 'var(--status-amber)'});
          if (offline > 0) sd.push({label: 'Offline', value: offline, color: 'var(--empire-mist)'});
          if (other > 0) sd.push({label: 'Other', value: other, color: 'var(--empire-fog)'});
          return html`<${DonutChart} data=${sd} size=${108} strokeWidth=${22} />`;
        })()}
      </div>` : ''}
      <div class="hm-split">
        <div class="hm-panel">
          <div class="hm-panel-h">
            <div class="hm-panel-title">Agent Mesh</div>
            <div class="hm-panel-tag">${agents.length} registered</div>
          </div>
          ${agents.length === 0
            ? html`<div class="hm-empty">No registered agents found.</div>`
            : html`<div class="hm-agent-grid">
              ${agents.filter(a => !a.error).map(a => {
                const statusCls = a.status || 'OFFLINE';
                const ping = a.ping_age_min != null
                  ? (a.ping_age_min < 1 ? '<1m' : a.ping_age_min + 'm')
                  : '—';
                return html`
                <div class="hm-agent-card" key=${a.agent_name}>
                  <div class="hm-agent-row">
                    <span class="hm-agent-name">${a.agent_name}</span>
                    <span class=${'hm-bdg ' + statusCls}>
                      <span class="hm-bdg-dot"></span>${statusCls}
                    </span>
                  </div>
                  <div class="hm-agent-meta">Last ping: ${ping} ago</div>
                </div>
              `})}
              ${agents.filter(a => a.error).map(a => html`
                <div class="hm-agent-card" key=${'err'}>
                  <div class="hm-agent-row">
                    <span class="hm-agent-name">⚠ Error</span>
                  </div>
                  <div class="hm-agent-meta">${a.error}</div>
                </div>
              `)}
            </div>`}
        </div>
        <div class="hm-panel">
          <div class="hm-panel-h">
            <div class="hm-panel-title">System Health</div>
            <div class="hm-panel-tag">${data.ts ? data.ts.slice(11,19) : ''}</div>
          </div>
          <div class="hm-health-grid">
            <div class="hm-health-card">
              <div class=${'hm-health-val ' + brainCls}>${data.brain_up ? 'UP' : 'DOWN'}</div>
              <div class="hm-health-lbl">Brain (Ollama)</div>
            </div>
            <div class="hm-health-card">
              <div class=${'hm-health-val ' + pm2Cls}>${pm2.healthy}/${pm2.total}</div>
              <div class="hm-health-lbl">PM2 Services</div>
            <div class="hm-health-card" style="${dhealth && dhealth.ok && dhealth.circuit_breaker && dhealth.circuit_breaker.is_open ? 'border-color:rgba(255,68,68,0.3)' : ''}">
              <div class="hm-health-val ${dhealth && dhealth.ok && dhealth.circuit_breaker && dhealth.circuit_breaker.is_open ? '' : 'ok'}" style="${dhealth && dhealth.ok && dhealth.circuit_breaker && dhealth.circuit_breaker.is_open ? 'color:var(--status-red)' : ''}">
                ${dhealth && dhealth.ok ? (dhealth.circuit_breaker && dhealth.circuit_breaker.is_open ? '\u26a0 OPEN' : '\u2713 CLOSED') : '\u2014'}
              </div>
              <div class="hm-health-lbl">Circuit Breaker</div>
              <div style="font-size:8px;color:var(--empire-fog);margin-top:2px;font-family:var(--font-mono)">${dhealth && dhealth.ok && dhealth.circuit_breaker && dhealth.circuit_breaker.reset_at ? 'reset ' + dhealth.circuit_breaker.reset_at.slice(0,16) : ''}</div>
            </div>
            <div class="hm-health-card">
              <div class="hm-health-val ok">${dhealth && dhealth.ok ? dhealth.dispatched_24h || 0 : '\u2014'}</div>
              <div class="hm-health-lbl">Disp. (24h)</div>
            </div>
            <div class="hm-health-card" style="${dhealth && dhealth.ok && dhealth.failed_24h > 0 ? 'border-color:rgba(255,184,0,0.2)' : ''}">
              <div class="hm-health-val ${dhealth && dhealth.ok && dhealth.failed_24h > 0 ? '' : 'ok'}" style="${dhealth && dhealth.ok && dhealth.failed_24h > 0 ? 'color:var(--status-amber)' : ''}">
                ${dhealth && dhealth.ok ? dhealth.failed_24h || 0 : '\u2014'}
              </div>
              <div class="hm-health-lbl">Disp. Failed</div>
            </div>
            </div>
            <div class="hm-health-card">
              <div class="hm-health-val ok">${funnel.calls_today ?? 0}</div>
              <div class="hm-health-lbl">Calls Today</div>
            </div>
            <div class="hm-health-card">
              <div class=${'hm-health-val ' + forecastCls}>${data.storm_forecasts_count ?? 0}</div>
              <div class="hm-health-lbl">Storm Forecasts</div>
            </div>
          </div>
          <div style=${{marginTop: '12px', fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--empire-fog)'}}>
            Qualified: <strong style=${{color: 'var(--empire-white)'}}>${funnel.qualified_today ?? 0}</strong> / ${funnel.calls_today ?? 0} calls
          </div>
        </div>
      </div>
      ${overseerRaw ? html`
      <div class="hm-overseer">
        <div class="hm-panel-h">
          <div class="hm-panel-title">Overseer Report</div>
          <div class="hm-panel-tag">latest snapshot</div>
        </div>
        <div class="hm-overseer-body">${overseerRaw}</div>
      </div>
      ` : html`
      <div class="hm-overseer">
        <div class="hm-panel-h">
          <div class="hm-panel-title">Overseer Report</div>
          <div class="hm-panel-tag">not available</div>
        </div>
        <div class="hm-empty">No overseer report yet. The overseer agent writes to system_health every 10 minutes.</div>
      </div>
      `}
    </div>
  `;
}

// ── SNIPER FLEET ─────────────────────────────────────────────────────


// ── STUB SECTION (other tabs) ────────────────────────────────────────


/* ── EMAIL TRACKING SECTION ───────────────────────────────────── */



// ── DISPATCH HEALTH — circuit breaker, errors, throughput ──
function DispatchHealth() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/v1/dispatch/health').then(x => x.json());
      setData(r);
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

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Dispatch Health</div><div class="stub-body">\${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading dispatch health…</div></div>`;

  const cb = data.circuit_breaker || {};
  const isOpen = cb.is_open || cb.consecutive_failures > 0;
  const failRate = data.dispatched_24h > 0 ? ((data.failed_24h || 0) / data.dispatched_24h * 100).toFixed(1) : '0.0';

  return html`
    <div>
      <div class="section-h">
        <div class="section-title">Dispatch <em>Health</em></div>
        <div class="section-sub">Refreshes every 30s</div>
      </div>

      <div class="fee-stats" style="margin-bottom:24px">
        <div class="fee-stat" style="\${isOpen ? 'border-color:rgba(255,68,68,0.35);background:rgba(255,68,68,0.04)' : 'border-color:rgba(68,229,184,0.2)'}">
          <div class="fee-stat-label">Circuit Breaker</div>
          <div class="fee-stat-value \${isOpen ? '' : 'teal'}" style="font-size:20px;\${isOpen ? 'color:var(--status-red)' : ''}">
            \${isOpen ? '⚠ OPEN' : '✓ CLOSED'}
          </div>
          <div style="font-size:10px;color:var(--empire-fog);margin-top:6px">
            \${cb.consecutive_failures ? cb.consecutive_failures + ' consecutive failures' : 'No recent failures'}
          </div>
          \${cb.import_error ? html`
            <div style="margin-top:8px;padding:8px 10px;background:rgba(255,184,0,0.08);border:1px solid rgba(255,184,0,0.2);border-radius:4px;font-family:var(--font-mono);font-size:9px;color:var(--status-amber);line-height:1.4">
              ⚠ Circuit state unavailable: \${cb.import_error}
            </div>
          ` : null}
          \${cb.backoff_until ? html`
            <div style="font-size:9px;color:var(--status-amber);margin-top:4px;font-family:var(--font-mono)">
              Backoff until \${(cb.backoff_until || '').slice(0,19)}
            </div>
          ` : null}
          \${cb.last_failure_at ? html`
            <div style="font-size:9px;color:var(--empire-fog);margin-top:2px;font-family:var(--font-mono)">
              Last failure: \${(cb.last_failure_at || '').slice(0,19)}
            </div>
          ` : null}
        </div>
        <div class="fee-stat">
          <div class="fee-stat-label">Dispatched (24h)</div>
          <div class="fee-stat-value teal">\${data.dispatched_24h || 0}</div>
          <div class="fee-stat-label" style="margin-top:8px">Throughput</div>
          <div style="font-size:11px;color:var(--empire-mist);font-family:var(--font-mono)">
            \${data.dispatched_24h > 0 ? (data.dispatched_24h / 24).toFixed(1) + '/hr' : '—'}
          </div>
        </div>
        <div class="fee-stat" style="\${(data.failed_24h || 0) > 0 ? 'border-color:rgba(255,184,0,0.2)' : ''}">
          <div class="fee-stat-label">Failed (24h)</div>
          <div class="fee-stat-value \${(data.failed_24h || 0) > 0 ? '' : 'dim'}" style="\${(data.failed_24h || 0) > 0 ? 'color:var(--status-amber)' : ''}">
            \${data.failed_24h || 0}
          </div>
          <div class="fee-stat-label" style="margin-top:8px">Failure Rate</div>
          <div style="font-size:11px;color:\${parseFloat(failRate) > 10 ? 'var(--status-red)' : parseFloat(failRate) > 0 ? 'var(--status-amber)' : 'var(--signal-teal)'};font-family:var(--font-mono)">
            \${failRate}%
          </div>
        </div>
        <div class="fee-stat">
          <div class="fee-stat-label">Matcher</div>
          \${data.matcher_stats ? html`
            <div class="fee-stat-value dim" style="font-size:20px">\${data.matcher_stats.matches_computed || 0} runs</div>
            <div style="font-size:9px;color:var(--empire-fog);margin-top:4px;font-family:var(--font-mono)">
              \${data.matcher_stats.dispatches_sent || 0} sent · \${data.matcher_stats.dispatches_accepted || 0} accepted
            </div>
            <div style="font-size:9px;color:var(--empire-fog);font-family:var(--font-mono)">
              Trust updates: \${data.matcher_stats.trust_updates || 0}
            </div>
          ` : html`<div class="fee-stat-value dim">—</div>`}
        </div>
      </div>

      \${(data.recent_errors || []).length > 0 ? html`
        <div class="panel" style="margin-bottom:24px;border-color:rgba(255,184,0,0.2)">
          <div class="panel-head" style="display:flex;justify-content:space-between;align-items:center">
            <span style="color:var(--status-amber)">⚠ Recent Dispatch Errors</span>
            <span class="sec-meta" style="margin:0">\${data.recent_errors.length} errors in 24h</span>
          </div>
          \${data.recent_errors.map((e, i) => html`
            <div style="padding:10px 0;border-bottom:1px solid var(--empire-divider);\${i === data.recent_errors.length - 1 ? 'border-bottom:none' : ''}">
              <div style="display:flex;gap:12px;align-items:baseline;margin-bottom:4px">
                <span style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);flex-shrink:0">\${(e.at || '').slice(0,19)}</span>
                <span style="font-family:var(--font-mono);font-size:10px;color:var(--status-amber);letter-spacing:.04em">FAILED</span>
              </div>
              <div style="font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);word-break:break-word;line-height:1.5;padding-left:90px">
                \${(e.body || '').slice(0,200)}
              </div>
            </div>
          `)}
        </div>
      ` : html`
        <div class="panel" style="margin-bottom:24px;border-color:rgba(68,229,184,0.1)">
          <div class="panel-head">
            <span style="color:var(--signal-teal)">✓ No recent dispatch errors</span>
          </div>
          <div style="padding:8px 0;font-family:var(--font-ui);font-size:11px;color:var(--empire-fog);font-style:italic">
            All dispatches in the last 24 hours completed without errors.
          </div>
        </div>
      `}

      <div class="split">
        <div class="panel">
          <div class="panel-head">Matcher Score Breakdown</div>
          \${data.matcher_stats ? html`
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div style="text-align:center;padding:12px;background:var(--empire-elevated);border-radius:4px">
                <div style="font-family:var(--font-mono);font-size:22px;color:var(--signal-teal)">\${data.matcher_stats.matches_computed || 0}</div>
                <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:4px;letter-spacing:.08em;text-transform:uppercase">Matches Computed</div>
              </div>
              <div style="text-align:center;padding:12px;background:var(--empire-elevated);border-radius:4px">
                <div style="font-family:var(--font-mono);font-size:22px;color:var(--strike-cyan)">\${data.matcher_stats.dispatches_sent || 0}</div>
                <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:4px;letter-spacing:.08em;text-transform:uppercase">Dispatches Sent</div>
              </div>
              <div style="text-align:center;padding:12px;background:var(--empire-elevated);border-radius:4px">
                <div style="font-family:var(--font-mono);font-size:22px;color:\${(data.matcher_stats.dispatches_accepted || 0) > 0 ? 'var(--signal-teal)' : 'var(--empire-mist)'}">\${data.matcher_stats.dispatches_accepted || 0}</div>
                <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:4px;letter-spacing:.08em;text-transform:uppercase">Accepted</div>
              </div>
              <div style="text-align:center;padding:12px;background:var(--empire-elevated);border-radius:4px">
                <div style="font-family:var(--font-mono);font-size:22px;color:var(--empire-mist)">\${data.matcher_stats.trust_updates || 0}</div>
                <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:4px;letter-spacing:.08em;text-transform:uppercase">Trust Updates</div>
              </div>
            </div>
          ` : html`<div class="chart-empty">No matcher data yet</div>`}
        </div>
        <div class="panel">
          <div class="panel-head">Circuit Breaker Status</div>
          <div style="padding:8px 0">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
              <div style="width:14px;height:14px;border-radius:50%;background:\${isOpen ? 'var(--status-red)' : 'var(--signal-teal)'};box-shadow:0 0 10px \${isOpen ? 'rgba(255,68,68,0.5)' : 'rgba(68,229,184,0.5)'}"></div>
              <div>
                <div style="font-weight:500;font-size:14px;color:\${isOpen ? 'var(--status-red)' : 'var(--signal-teal)'}">
                  \${isOpen ? 'Circuit Open' : 'Circuit Closed'}
                </div>
                <div style="font-size:10px;color:var(--empire-fog);font-family:var(--font-mono);margin-top:2px">
                  \${isOpen ? 'Dispatch cron is paused' : 'Dispatch cron is running normally'}
                </div>
              </div>
            </div>
            <div style="font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);line-height:1.7">
              <div>Consecutive failures: <strong style="color:\${cb.consecutive_failures > 0 ? 'var(--status-red)' : 'var(--signal-teal)'}">\${cb.consecutive_failures || 0}</strong></div>
              <div>Backoff level: <span style="color:var(--empire-silver)">\${cb.consecutive_failures > 0 ? Math.min(5 * Math.pow(2, cb.consecutive_failures - 1), 60) + ' min' : 'none'}</span></div>
              <div>Last failure: <span style="color:var(--empire-fog)">\${cb.last_failure_at ? cb.last_failure_at.slice(0,19) : '—'}</span></div>
              <div>Last reset: <span style="color:var(--empire-fog)">${cb.reset_at ? cb.reset_at.slice(0,19) : '—'}</span></div>
              <div>Backoff until: <span style="color:var(--empire-fog)">\${cb.backoff_until ? cb.backoff_until.slice(0,19) : '—'}</span></div>
            </div>
          
            </div>
            <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--empire-divider)">
              <button class="tbl-action danger" onclick="\${async () => { try { const r = await apiFetch('/api/v1/dispatch/reset-circuit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: 'Operator reset from SPA' }) }).then(x => x.json()); if (r.ok) { alert('Circuit breaker reset successfully.'); location.reload(); } else { alert('Reset failed: ' + (r.error || 'unknown')); } } catch(e) { alert('Reset request failed: ' + e.message); } }}" style="width:100%;padding:8px 14px;font-size:10px;cursor:pointer">
                ↻ Reset Circuit Breaker
              </button>
              <div style="font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);margin-top:6px;text-align:center">
                Zeroes the failure counter and resumes dispatch cron
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

// ── REPLY RATES DASHBOARD — YES reply % by niche, A/B, daily dispatch ──
function ReplyRates() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [days, setDays] = useState(30);

  const [health, setHealth] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [r, h] = await Promise.all([
        apiFetch('/api/v1/reply/rates?days=' + days).then(x => x.json()),
        apiFetch('/api/v1/dispatch/health').then(x => x.json()).catch(() => ({ok: false})),
      ]);
      setData(r);
      if (h.ok) setHealth(h);
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, [days]);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 60000);
    return () => clearInterval(t);
  }, [reload]);

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Reply Rates</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading reply rates…</div></div>`;

  const niches = data.by_niche || [];
  const cohorts = data.by_sequence || [];
  const daily = data.daily_dispatches || [];

  const rateColor = (pct) => pct >= 8 ? '#44E5B8' : pct >= 4 ? '#FFB800' : '#FF4444';
  const barWidth = (pct) => Math.min(100, Math.max(2, pct * 4)) + '%';

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Reply Rates</div>
          <div class="section-sub">YES reply % by niche · A/B comparison · daily dispatch</div>
        </div>
        <div class="sec-actions">
          <select class="tbl-action" value=${days} onChange=${e => setDays(Number(e.target.value))}>
            <option value="7">7 days</option>
            <option value="14">14 days</option>
            <option value="30" selected>30 days</option>
            <option value="60">60 days</option>
            <option value="90">90 days</option>
          </select>
          <button class="btn ghost" onClick=${reload}>Refresh</button>
        </div>
      </div>

      <div class="fee-stats" style="margin-bottom:20px">
        <div class="fee-stat">
          <div class="fee-stat-label">Blended reply rate</div>
          <div class="fee-stat-value teal">${data.blended_reply_rate_pct}%</div>
        </div>
        <div class="fee-stat">
          <div class="fee-stat-label">Total sent (${data.window_days}d)</div>
          <div class="fee-stat-value">${data.total_sent}</div>
        </div>
        <div class="fee-stat">
          <div class="fee-stat-label">Total YES replies</div>
          <div class="fee-stat-value teal">${data.total_yes_replies}</div>
        </div>
        <div class="fee-stat">
          <div class="fee-stat-label">Daily avg dispatched</div>
          <div class="fee-stat-value dim">${daily.length > 0 ? Math.round(daily.reduce((s,d) => s + d.count, 0) / daily.length) : 0}</div>
        </div>
      </div>

      <div class="split" style="margin-bottom:20px">
        <div class="panel" style="max-height:480px;overflow-y:auto">
          <div class="panel-head">YES reply rate by niche</div>
          ${niches.length > 0 ? niches.map(n => html`
            <div style=${{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'10px 0',borderBottom:'1px solid var(--empire-divider)'}}>
              <div style=${{flex:1,minWidth:0}}>
                <div style=${{fontSize:'12px',color:'var(--empire-white)',fontWeight:500,marginBottom:'2px'}}>${n.label}</div>
                <div style=${{fontFamily:'var(--font-mono)',fontSize:'9px',color:'var(--empire-fog)'}}>${n.sent} sent · ${n.yes_replies} YES</div>
              </div>
              <div style=${{fontFamily:'var(--font-mono)',fontSize:'16px',fontWeight:600,color:rateColor(n.reply_rate_pct)}}>${n.reply_rate_pct}%</div>
            </div>
          `) : html`<div class="hm-empty">No sequence data in this window.</div>`}
        </div>

        <div class="panel">
          <div class="panel-head">storm_strike vs storm_strike_v2</div>
          ${cohorts.length > 0 ? cohorts.map(c => html`
            <div style=${{marginBottom:'16px'}}>
              <div style=${{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:'6px'}}>
                <span style=${{fontSize:'13px',color:'var(--empire-white)',fontWeight:500}}>${c.label}</span>
                <span style=${{fontFamily:'var(--font-mono)',fontSize:'12px',color:rateColor(c.reply_rate_pct)}}>${c.reply_rate_pct}%</span>
              </div>
              <div style=${{display:'flex',justifyContent:'space-between',marginBottom:'8px',fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-fog)'}}>
                <span>${c.sent} sent</span>
                <span>${c.yes_replies} YES replies</span>
              </div>
              <div style=${{height:'6px',background:'var(--empire-elevated)',borderRadius:'3px',overflow:'hidden'}}>
                <div style=${{width:barWidth(c.reply_rate_pct),height:'100%',borderRadius:'3px',background:rateColor(c.reply_rate_pct),transition:'width .6s var(--ease-out-empire)'}}></div>
              </div>
            </div>
          `) : html`<div class="hm-empty">No storm_strike data in this window.</div>`}
          ${cohorts.length >= 2 && html`
            <div style=${{marginTop:'14px',paddingTop:'12px',borderTop:'1px solid var(--empire-divider)',fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-mist)'}}>
              ${(() => {
                const a = cohorts.find(c => c.cohort === 'storm_strike');
                const b = cohorts.find(c => c.cohort === 'storm_strike_v2');
                if (!a || !b || a.reply_rate_pct === b.reply_rate_pct) return 'No significant difference';
                const winner = a.reply_rate_pct > b.reply_rate_pct ? a : b;
                const loser = winner === a ? b : a;
                const lift = Math.abs(winner.reply_rate_pct - loser.reply_rate_pct);
                return html`<strong>${winner.label}</strong> leads by <span style="color:#44E5B8">+${lift.toFixed(1)}pp</span> reply rate`;
              })()}
            </div>
          `}
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">Daily dispatch counts (${data.window_days}d)</div>
        ${daily.length > 0 ? html`
          <div style=${{display:'flex',alignItems:'flex-end',gap:'3px',height:'120px',paddingTop:'8px'}}>
            ${daily.map(d => {
              const maxCount = Math.max(...daily.map(x => x.count), 1);
              const h = Math.max(2, Math.round(d.count / maxCount * 100));
              return html`
                <div style=${{flex:1,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'flex-end',height:'100%'}} title="${d.date}: ${d.count} dispatched, ${d.yes_replies} YES, ${d.sent} sent">
                  <div style=${{fontFamily:'var(--font-mono)',fontSize:'7px',color:'var(--empire-fog)',marginBottom:'3px'}}>${d.count || ''}</div>
                  <div style=${{width:'100%',maxWidth:'28px',height:h+'%',background:'linear-gradient(180deg, #44E5B8, rgba(68,229,184,0.2))',borderRadius:'2px 2px 0 0',minHeight:'2px',transition:'height .4s var(--ease-out-empire)'}}></div>
                  <div style=${{fontFamily:'var(--font-mono)',fontSize:'6px',color:'var(--empire-fog)',marginTop:'4px',transform:'rotate(-45deg)',transformOrigin:'top left',whiteSpace:'nowrap'}}>${d.date.slice(5)}</div>
                </div>`;
            })}
          </div>
          <div style=${{marginTop:'8px',fontFamily:'var(--font-mono)',fontSize:'9px',color:'var(--empire-fog)',textAlign:'center'}}>
            Hover bars for detail · ${daily.filter(d => d.count > 0).length} days with dispatches
          </div>
        ` : html`<div class="hm-empty">No dispatch data in this window.</div>`}
      </div>
    </div>
  `;
}

// ── SMS PERFORMANCE — niche-specific sequence breakdown ──────────────
function SmsPerformance() {
  const [data, setData] = React.useState(null);
  const [busy, setBusy] = React.useState(true);
  const [err, setErr] = React.useState(null);

  const reload = React.useCallback(async () => {
    setBusy(true);
    try {
      const r = await apiFetch('/api/v1/sms/niche-stats').then(x => x.json());
      setData(r);
      setErr(null);
    } catch (e) {
      setErr(e.message || 'Failed to load SMS niche stats');
    } finally {
      setBusy(false);
    }
  }, []);

  React.useEffect(() => { reload(); }, [reload]);

  if (err) return html`<div class="stub"><div class="stub-title"><em>SMS</em> Performance</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const niches = data.niches || [];
  const total = data.total || 0;
  const totalActive = niches.reduce((s, n) => s + (n.active || 0), 0);
  const totalReplied = niches.reduce((s, n) => s + (n.replied || 0), 0);
  const totalCompleted = niches.reduce((s, n) => s + (n.completed || 0), 0);
  const totalOptedOut = niches.reduce((s, n) => s + (n.opted_out || 0), 0);

  return html`
    <div class="section-h">
      <div>
        <div class="section-title">SMS <em>Performance</em></div>
        <div class="section-sub">Niches · sequence stats · enrollment breakdown by type</div>
      </div>
      <button class="tbl-action go" onClick=${reload}>↻ Refresh</button>
    </div>

    <div class="sms-niche-grid">
      <div class="sms-niche-card">
        <div class="sms-niche-val teal">${total}</div>
        <div class="sms-niche-lbl">Total Sequences</div>
      </div>
      <div class="sms-niche-card">
        <div class="sms-niche-val">${totalActive}</div>
        <div class="sms-niche-lbl">Active</div>
      </div>
      <div class="sms-niche-card">
        <div class="sms-niche-val cyan">${totalReplied}</div>
        <div class="sms-niche-lbl">Replied</div>
      </div>
      <div class="sms-niche-card">
        <div class="sms-niche-val">${totalCompleted}</div>
        <div class="sms-niche-lbl">Completed</div>
      </div>
      <div class="sms-niche-card">
        <div class="sms-niche-val warn">${totalOptedOut}</div>
        <div class="sms-niche-lbl">Opted Out</div>
      </div>
    </div>

    <div class="sms-niche-table-wrap">
      <table class="tbl">
        <thead>
          <tr>
            <th>Sequence Type</th>
            <th style="text-align:right">Total</th>
            <th style="text-align:right">Active</th>
            <th style="text-align:right">Replied</th>
            <th style="text-align:right">Completed</th>
            <th style="text-align:right">Opted Out</th>
            <th style="text-align:right">Avg Step</th>
            <th style="text-align:right">With Phone</th>
            <th>Active / Total</th>
          </tr>
        </thead>
        <tbody>
          ${niches.map(n => html`
            <tr>
              <td><strong>${n.label}</strong></td>
              <td class="tbl-num">${n.total}</td>
              <td class="tbl-num">${n.active}</td>
              <td class="tbl-num" style="color:var(--strike-cyan)">${n.replied}</td>
              <td class="tbl-num" style="color:var(--signal-teal)">${n.completed}</td>
              <td class="tbl-num" style="color:var(--status-amber)">${n.opted_out}</td>
              <td class="tbl-num">${n.avg_step}</td>
              <td class="tbl-num">${n.with_phone}</td>
              <td>
                <div style="display:flex;align-items:center;gap:8px">
                  <div style="flex:1;height:6px;background:var(--empire-elevated);border-radius:3px;overflow:hidden">
                    <div class="sms-niche-bar active" style="width:${(n.active / Math.max(n.total, 1) * 100).toFixed(0)}%"></div>
                  </div>
                  <span class="tbl-mono" style="color:var(--empire-mist);font-size:10px">${(n.active / Math.max(n.total, 1) * 100).toFixed(0)}%</span>
                </div>
              </td>
            </tr>
          `)}
        </tbody>
      </table>
      ${niches.length === 0 ? html`<div class="tbl-empty">No SMS sequences found.</div>` : ''}
    </div>
  `;
}

function EmailTracking() {
  const [events, setEvents] = React.useState([]);
  const [days, setDays] = React.useState(30);
  const [eventFilter, setEventFilter] = React.useState('all');
  const [busy, setBusy] = React.useState(true);
  const [err, setErr] = React.useState(null);

  async function reload() {
    setBusy(true);
    setErr(null);
    try {
      let url = '/api/v1/email/tracking?days=' + days + '&limit=500';
      if (eventFilter !== 'all') url += '&event=' + eventFilter;
      const r = await apiFetch(url);
      const data = await r.json();
      setEvents(data.tracking || []);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  React.useEffect(() => { reload(); }, [days, eventFilter]);

  // Compute stats
  const total = events.length;
  const opens = events.filter(e => e.event === 'open').length;
  const clicks = events.filter(e => e.event === 'click').length;
  const bounces = events.filter(e => e.event === 'bounce').length;
  const complaints = events.filter(e => e.event === 'complaint').length;
  const unsubs = events.filter(e => e.event === 'unsubscribe').length;
  const uniqueEmails = new Set(events.map(e => e.email)).size;
  const uniqueOpens = new Set(events.filter(e => e.event === 'open').map(e => e.email)).size;
  const uniqueClicks = new Set(events.filter(e => e.event === 'click').map(e => e.email)).size;
  const delivered = total - bounces - complaints;
  const openRate = delivered > 0 ? ((uniqueOpens / delivered) * 100).toFixed(1) : '0.0';
  const clickRate = uniqueOpens > 0 ? ((uniqueClicks / uniqueOpens) * 100).toFixed(1) : '0.0';

  // Breakdown by sequence type
  const bySeqType = {};
  events.forEach(e => {
    const st = e.sequence_type || 'unknown';
    if (!bySeqType[st]) bySeqType[st] = { total: 0, opens: 0, clicks: 0, bounces: 0 };
    bySeqType[st].total++;
    if (e.event === 'open') bySeqType[st].opens++;
    if (e.event === 'click') bySeqType[st].clicks++;
    if (e.event === 'bounce') bySeqType[st].bounces++;
  });
  const seqTypes = Object.keys(bySeqType).sort();


  // Latest 50 events for the table
  const recentEvents = events.slice(0, 50);

  const eventOpts = ['all', 'open', 'click', 'bounce', 'complaint', 'unsubscribe'];
  const dayOpts = [7, 14, 30, 90];

  if (err) return html`<div class="stub"><div class="stub-title">Error</div><div class="stub-body">${err}</div></div>`;

  return html`
    <div class="section-h">
      <div class="section-title">Email <em>Tracking</em></div>
      <div class="section-sub">${total} events tracked</div>
    </div>

    <div class="et-filters">
      <span class="et-filter-tag">Event:</span>
      ${eventOpts.map(e => html`<button class=${'et-filter-btn' + (eventFilter === e ? ' active' : '')} onClick=${() => setEventFilter(e)}>${e === 'all' ? 'All' : e}</button>`)}
      <span class="et-filter-tag" style="margin-left:12px">Period:</span>
      ${dayOpts.map(d => html`<button class=${'et-filter-btn' + (days === d ? ' active' : '')} onClick=${() => setDays(d)}>${d}d</button>`)}
      ${busy ? html`<span style="margin-left:8px; font-family:var(--font-mono); font-size:10px; color:var(--empire-mist)">loading…</span>` : ''}
    </div>

    <div class="et-grid">
      <div class="et-card">
        <div class="et-card-label">Total Events</div>
        <div class="et-card-value teal">${total}</div>
        <div class="et-card-meta">In last ${days} days</div>
      </div>
      <div class="et-card">
        <div class="et-card-label">Unique Opens</div>
        <div class="et-card-value cyan">${uniqueOpens}</div>
        <div class="et-card-meta">${openRate}% open rate of ${delivered} delivered</div>
      </div>
      <div class="et-card">
        <div class="et-card-label">Unique Clicks</div>
        <div class="et-card-value teal">${uniqueClicks}</div>
        <div class="et-card-meta">${clickRate}% click rate of ${uniqueOpens} openers</div>
      </div>
      <div class="et-card">
        <div class="et-card-label">Bounces / Complaints</div>
        <div class="et-card-value ${bounces > 5 ? 'amber' : 'dim'}">${bounces} / ${complaints}</div>
        <div class="et-card-meta">${unsubs} unsubscribes</div>
      </div>
    </div>

    <div class="et-chart-panel">
      <div class="et-chart-panel-h">
        <div class="et-chart-panel-title">Event Breakdown by Sequence Type</div>
        <div class="et-chart-panel-tag">${seqTypes.length} campaigns</div>
      </div>
      ${seqTypes.length === 0 ? html`<div class="et-empty">No tracking data for this period</div>` :
        seqTypes.map(st => {
          const s = bySeqType[st];
          const maxVal = Math.max(s.opens, s.clicks, 1);
          const label = st === 'b2b_outreach' ? 'B2B Outreach' : st === 'storm_strike' ? 'Storm Strike' : st;
          return html`
            <div class="et-bar-row">
              <div class="et-bar-label">${label}</div>
              <div>
                <div class="et-bar-track"><div class="et-bar-fill open" style="width:${(s.opens/maxVal*100).toFixed(0)}%"></div></div>
                <div class="et-bar-track" style="margin-top:3px"><div class="et-bar-fill click" style="width:${(s.clicks/maxVal*100).toFixed(0)}%"></div></div>
              </div>
              <div class="et-bar-val">${s.opens} opens / ${s.clicks} clicks</div>
            </div>
          `;
        })
      }
    </div>

    <div class="et-chart-panel">
      <div class="et-chart-panel-h">
        <div class="et-chart-panel-title">Recent Events</div>
        <div class="et-chart-panel-tag">${recentEvents.length} of ${total} shown</div>
      </div>
      ${recentEvents.length === 0 ? html`<div class="et-empty">No events to display</div>` :
        html`
          <table class="tbl">
            <thead>
              <tr>
                <th>Time</th>
                <th>Email</th>
                <th>Event</th>
                <th>Campaign</th>
                <th>Step</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              ${recentEvents.map(e => html`
                <tr>
                  <td class="tbl-mono" style="font-size:10px;color:var(--empire-fog)">${e.created_at ? e.created_at.slice(11, 19) : '--'}</td>
                  <td><span class="et-email" title=${e.email}>${e.email}</span></td>
                  <td><span class="et-badge ${e.event}">${e.event}</span></td>
                  <td><span class="et-seq-type ${e.sequence_type === 'b2b_outreach' ? 'b2b' : 'storm'}">${(e.sequence_type || '').replace('_', ' ')}</span></td>
                  <td class="tbl-num" style="color:var(--empire-mist)">${e.step != null ? e.step : '--'}</td>
                  <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                    ${e.link_url ? html`<a href=${e.link_url} target="_blank" style="color:var(--strike-cyan);font-size:10px;font-family:var(--font-mono)">link</a>` : html`<span style="color:var(--empire-fog);font-size:10px">--</span>`}
                  </td>
                </tr>
              `)}
            </tbody>
          </table>
        `
      }
    </div>
  `;
}
function Stub({ section }) {
  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">${section.label}</div>
          <div class="section-sub">${section.sub}</div>
        </div>
      </div>
      <div class="stub">
        <div class="stub-title">Coming in <em>Phase 2</em></div>
        <div class="stub-body">
          The ${section.label.toLowerCase()} section is wired to existing /api/v1 endpoints and ready to render. Phase 2 brings the full UI for this section.
        </div>
        <div class="stub-tag">Phase 2 · Next PR</div>
      </div>
    </div>
  `;

// ── LEADS ────────────────────────────────────────────────────────────
function Leads() {
  const [leads, setLeads] = useState(null);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);
  const [filter, setFilter] = useState('all');
  const [busy, setBusy] = useState(null);
  const [noteText, setNoteText] = useState({});
  const [activity, setActivity] = useState([]);
  const [activityErr, setActivityErr] = useState(null);
  const [activityOffset, setActivityOffset] = useState(0);
  const [hasMoreActivity, setHasMoreActivity] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadActivity = useCallback(async (offset = 0, append = false) => {
    try {
      const r = await apiFetch(`/api/v1/leads/activity?limit=50&offset=${offset}`).then(r => r.json());
      if (append) {
        setActivity(a => [...a, ...(r.entries || [])]);
      } else {
        setActivity(r.entries || []);
      }
      setHasMoreActivity(r.has_more || false);
      setActivityOffset(offset + (r.entries || []).length);
      setActivityErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setActivityErr(e.message);
    }
  }, []);

  useEffect(() => { loadActivity(0, false); }, [loadActivity]);

  const reload = useCallback(async () => {
    try {
      const [l, s] = await Promise.all([
        apiFetch('/api/v1/inbound/leads?limit=100').then(r => r.json()),
        apiFetch('/api/v1/inbound/stats').then(r => r.json()),
      ]);
      setLeads(l.leads || (Array.isArray(l) ? l : []));
      setStats(s || {});
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);

  useEffect(() => { reload(); fetchFunnel(); fetchTopLinks(); }, [reload, fetchFunnel, fetchTopLinks]);

  const addNote = async (leadId) => {
    const text = (noteText[leadId] || '').trim();
    if (!text || busy) return;
    setBusy(leadId);
    try {
      await apiFetch('/api/v1/inbound/leads/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_id: leadId, notes: text }),
      });
      setNoteText(n => { const c = {...n}; delete c[leadId]; return c; });
      await reload();
      loadActivity(0, false);
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  const deleteNote = async (leadId, noteTs) => {
    if (!confirm('Delete this note?')) return;
    setBusy(leadId);
    try {
      await apiFetch('/api/v1/inbound/leads/delete-note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_id: leadId, timestamp: noteTs }),
      });
      await reload();
      loadActivity(0, false);
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  const updateStatus = async (leadId, status) => {
    if (!confirm('Set status to ' + status + '?')) return;
    setBusy(leadId);
    try {
      await apiFetch('/api/v1/inbound/leads/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_id: leadId, status }),
      });
      await reload();
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Leads</div><div class="stub-body">${err}</div></div>`;
  if (!leads) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const filterMap = {
    all: () => true,
    new: l => !l.status || l.status === 'new',
    contacted: l => l.status === 'contacted',
    qualified: l => l.status === 'qualified',
    closed: l => l.status === 'closed',
    rejected: l => l.status === 'rejected',
  };
  const filtered = leads.filter(filterMap[filter] || filterMap.all);

  const totalLeads = stats?.total ?? leads.length;
  const newLeads = stats?.new ?? 0;
  const contactedLeads = stats?.contacted ?? 0;
  const qualifiedLeads = stats?.qualified ?? 0;

  const statusActions = (l) => {
    const actions = [];
    if (l.status === 'new' || !l.status) {
      actions.push(html`<button class="ld-action-btn go" disabled=${busy === l.id} onClick=${() => updateStatus(l.id, 'contacted')}>Contacted</button>`);
      actions.push(html`<button class="ld-action-btn ghost" disabled=${busy === l.id} onClick=${() => updateStatus(l.id, 'qualified')}>Qualify</button>`);
    }
    if (l.status === 'contacted') {
      actions.push(html`<button class="ld-action-btn go" disabled=${busy === l.id} onClick=${() => updateStatus(l.id, 'qualified')}>Qualify</button>`);
    }
    if (l.status !== 'closed' && l.status !== 'rejected') {
      actions.push(html`<button class="ld-action-btn ghost" disabled=${busy === l.id} onClick=${() => updateStatus(l.id, 'closed')}>Close</button>`);
      actions.push(html`<button class="ld-action-btn danger" disabled=${busy === l.id} onClick=${() => updateStatus(l.id, 'rejected')}>Reject</button>`);
    }
    return actions;
  };

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Inbound <em>Leads</em></div>
          <div class="section-sub">Pipeline · intake · notes</div>
        </div>
        <div class="section-sub">${filtered.length} of ${totalLeads} leads</div>
      </div>

      <div class="ld-stats">
        <div class="ld-stat">
          <div class="ld-stat-val teal">${totalLeads}</div>
          <div class="ld-stat-lbl">Total leads</div>
        </div>
        <div class="ld-stat">
          <div class="ld-stat-val teal">${newLeads}</div>
          <div class="ld-stat-lbl">New</div>
        </div>
        <div class="ld-stat">
          <div class="ld-stat-val">${contactedLeads}</div>
          <div class="ld-stat-lbl">Contacted</div>
        </div>
        <div class="ld-stat">
          <div class="ld-stat-val">${qualifiedLeads}</div>
          <div class="ld-stat-lbl">Qualified</div>
        </div>
      </div>

      <div class="ld-filter">
        <span class="ld-filter-tag">Filter:</span>
        ${['all','new','contacted','qualified','closed','rejected'].map(f => html`
          <button class=${'ld-filter-btn ' + (filter === f ? 'active' : '')} onClick=${() => setFilter(f)}>${f.charAt(0).toUpperCase() + f.slice(1)}</button>
        `)}
      </div>

      ${filtered.length === 0
        ? html`<div class="ld-empty">No leads match this filter.</div>`
        : filtered.map(l => {
          const notes = (() => {
            try { return typeof l.notes === 'string' ? JSON.parse(l.notes) : (Array.isArray(l.notes) ? l.notes : []); }
            catch { return []; }
          })();
          const ts = l.created_at || l._t || '';
          const phone = l.from_number || l.phone || l.caller_id || '';
          const name = l.name || l.caller_name || l.contact_name || phone || '—';
          const source = l.source || (l.from_number || l.phone ? 'inbound' : 'unknown');
          const status = l.status || 'new';
          const statusCls = status === 'closed' || status === 'rejected' ? status : (status === 'new' ? 'new' : status === 'contacted' ? 'contacted' : status === 'qualified' ? 'qualified' : status);
          return html`
          <div class="ld-lead" key=${l.id} data-lead-id=${l.id}>
            <div class="ld-lead-row">
              <div>
                <div class="ld-lead-name">${name}</div>
                ${phone ? html`<div class="ld-lead-contact">${phone}</div>` : ''}
              </div>
              <span class=${'ld-bdg ' + statusCls}>${status}</span>
            </div>
            <div class="ld-lead-meta">
              ${ts ? html`<span>${ts.slice(0,19).replace('T',' ')}</span>` : ''}
              <span class=${'ld-bdg source'}>${source}</span>
            </div>

            ${notes.length > 0 ? html`
            <div class="ld-notes-history">
              ${notes.map(n => {
                const noteTs = n.ts || n.timestamp || '';
                const noteText = n.text || n.note || '';
                const noteOp = n.operator || n.op || '';
                if (!noteText) return '';
                return html`
                <div class="ld-note-entry" key=${noteTs}>
                  <div class="ld-note-meta">
                    ${noteOp ? html`<span class="ld-note-op">${noteOp}</span>` : ''}
                    ${noteTs ? html`<span>${noteTs.slice(0,19).replace('T',' ')}</span>` : ''}
                    <button class="ld-note-del" disabled=${busy === l.id} onClick=${() => deleteNote(l.id, noteTs)} title="Delete note">✕</button>
                  </div>
                  <div class="ld-note-text">${noteText}</div>
                </div>
              `;
              })}
            </div>
            ` : ''}

            <div class="ld-notes">
              <input class="ld-notes-in"
                value=${noteText[l.id] || ''}
                onChange=${e => setNoteText(n => ({...n, [l.id]: e.target.value}))}
                onKeyDown=${e => { if (e.key === 'Enter') addNote(l.id); }}
                placeholder="Add a note…"
              />
              <button class="ld-note-save"
                disabled=${busy === l.id || !(noteText[l.id] || '').trim()}
                onClick=${() => addNote(l.id)}
              >Save</button>
            </div>

            <div class="ld-actions">
              ${statusActions(l)}
            </div>
          </div>
        `;
      })}

      <div class="live-panel" style=${{marginTop: '24px'}}>
        <div class="panel-h">
          <div class="panel-title">Activity Log</div>
          <div class="panel-tag">${activity.length} entries${hasMoreActivity ? html` · <button class="act-clear" style=${{marginLeft: "4px"}} onClick=${async () => { setLoadingMore(true); await loadActivity(activityOffset, true); setLoadingMore(false); }} disabled=${loadingMore}>${loadingMore ? "Loading…" : "Load More"}</button>` : ""} · <button class="act-clear" onClick=${() => { setActivity([]); setActivityOffset(0); setHasMoreActivity(false); }}>Clear</button></div>
        </div>
        ${activityErr
          ? html`<div class="act-empty">Could not load activity: ${activityErr}</div>`
          : activity.length === 0
            ? html`<div class="act-empty">No activity yet — operator actions will appear here.</div>`
            : html`<div class="act-feed">
              ${activity.map((a, i) => {
                const aTs = a.timestamp || '';
                const aOp = a.operator || '—';
                const aText = a.text || '';
                const aLead = a.lead_name || '—';
                const aLeadId = a.lead_id || '';
                return html`
                <div class="act-entry" key=${aTs + i}>
                  <span class="act-entry-ts">${aTs.slice(0,19).replace('T',' ')}</span>
                  <span class="act-entry-body">
                    <span class="act-entry-lead" onClick=${() => {
                      const el = document.querySelector('[data-lead-id="' + aLeadId + '"]');
                      if (el) el.scrollIntoView({ behavior: 'smooth' });
                    }}>${aLead}</span>
                    <span class="act-entry-text"> · ${aText}</span>
                  </span>
                  <span class="act-entry-operator">${aOp}</span>
                </div>
              `;
              })}
            </div>`}
      </div>

    </div>
  `;
}

}

// ── KANBAN ────────────────────────────────────────────────────────────
function Kanban() {
  const [tasks, setTasks] = useState(null);
  const [err, setErr] = useState(null);
  const [tick, setTick] = useState(0);
  const [typeFilter, setTypeFilter] = useState('');

  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/hermes/queue?limit=200').then(x => x.json());
      setTasks(r.tasks || []);
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);

  useEffect(() => {
    reload();
    const t = setInterval(() => { reload(); setTick(x => x + 1); }, 15000);
    return () => clearInterval(t);
  }, [reload]);

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Kanban</div><div class="stub-body">${err}</div></div>`;
  if (!tasks) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const TASK_TYPES = [
    'scout.find_roofs',
    'outreach.draft_email',
    'studio.write_script',
    'studio.render_reel',
    'revenue.connect_buyer',
    'revenue.score_call',
    'swarm.fire',
    'swarm.strike_video',
  ];

  const filtered = typeFilter ? tasks.filter(t => t.task_type === typeFilter) : tasks;

  const STATUSES = ['To-Do', 'In Progress', 'Done', 'Failed', 'Blocked', 'Retried', 'Promoted'];
  const byStatus = {};
  for (const s of STATUSES) byStatus[s] = [];
  for (const t of filtered) {
    const st = t.status || 'unknown';
    if (byStatus[st]) byStatus[st].push(t);
  }

  const summary = STATUSES.map(s => `${byStatus[s].length} ${s}`).join(' · ');
  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title"><em>Kanban</em> Board</div>
          <div class="section-sub">Agent task queue · pipeline stages</div>
        </div>
        <div class="section-sub">Auto-refresh · 15s · TICK ${tick}</div>
      </div>

      <div class="kb-summary">
        <span class="kb-summary-tag">Total: <strong>${filtered.length} tasks</strong></span>
        <span class="kb-summary-tag">${summary}</span>
      </div>

      <div class="ld-filter">
        <span class="ld-filter-tag">Filter by type:</span>
        <button class=${'ld-filter-btn ' + (typeFilter === '' ? 'active' : '')} onClick=${() => setTypeFilter('')}>All</button>
        ${TASK_TYPES.map(tt => html`
          <button class=${'ld-filter-btn ' + (typeFilter === tt ? 'active' : '')} onClick=${() => setTypeFilter(tt)}>${tt}</button>
        `)}
      </div>

      <div class="kb-board">
        ${STATUSES.map(status => {
          const cards = byStatus[status] || [];
          return html`
            <div class="kb-col" key=${status}>
              <div class=${'kb-col-h ' + status.replace(' ','-')}>
                <span class="kb-col-title">${status}</span>
                <span class="kb-col-count">${cards.length}</span>
              </div>
              <div class="kb-col-body">
                ${cards.length === 0
                  ? html`<div class="kb-empty">No tasks</div>`
                  : cards.map(t => {
                    const payload = (() => {
                      try { return typeof t.payload === 'string' ? JSON.parse(t.payload) : (t.payload || {}); }
                      catch { return {}; }
                    })();
                    const label = payload.lead_id || payload.source_id || payload.campaign_id || payload.phone || '';
                    const ts = (t.created_at || t.completed_at || '').slice(0,16).replace('T',' ');
                    return html`
                      <div class="kb-card" key=${t.ticket_id} title=${'Payload: ' + JSON.stringify(payload).slice(0,200)}>
                        <div class="kb-card-id">#${(t.ticket_id || '').slice(0,8)}</div>
                        <div class="kb-card-type">${t.task_type || '—'}</div>
                        <div class="kb-card-agent">${t.assigned_agent || 'unassigned'}</div>
                        ${label ? html`<div class="kb-card-type" style=${{fontSize: '9px', color: 'var(--signal-teal)'}}>${label.slice(0, 30)}</div>` : ''}
                        <div class="kb-card-meta">
                          <span class="kb-card-pri">pri <strong>${t.priority ?? 0}</strong></span>
                          <span class="kb-card-ts">${ts || '—'}</span>
                        </div>
                      </div>
                    `;
                  })}
              </div>
            </div>
          `;
        })}
      </div>
    </div>
  `;
}

// ── REVENUE ──────────────────────────────────────────────────────────────
function Revenue({ events, wsConnected }) {
  const [data, setData] = useState(null);
  const [narrative, setNarrative] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [accuracy, setAccuracy] = useState(null);
  const [mrrData, setMrrData] = useState(null);
  const [refLeaderboard, setRefLeaderboard] = useState(null);
  const [profileCtr, setProfileCtr] = useState(null);
  const [err, setErr] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [r, nr] = await Promise.all([
        apiFetch('/api/revenue/lanes').then(x => x.json()),
        apiFetch('/api/revenue/forecast').then(x => x.json()),
      ]);
      setData(r);
      setNarrative(nr.narrative || nr);
      setForecast(nr);
      const ar = await apiFetch('/api/revenue/accuracy?days=14').then(x => x.json());
      setAccuracy(ar);
      // Fetch MRR comparison
      try {
        const mr = await (await apiFetch("/api/revenue/mrr")).json();
        setMrrData(mr);
      } catch(e) { /* MRR timeout okay */ }
      // Fetch referral leaderboard
      try {
        const lb = await apiFetch('/api/v1/referral-leaderboard?limit=10').then(x => x.json());
        setRefLeaderboard(lb);
      } catch(e) { /* non-critical */ }
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 60000);
    return () => clearInterval(t);
  }, [reload]);

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Revenue</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading\u2026</div></div>`;

  const lanes = data.lanes || [];
  const totals = data.totals || {};
  const nicheSummary = data.niche_summary || {};
  const health = data.health || {};
  const adaptation = (forecast && forecast.adaptation) || {};
  const topLanes = lanes.slice(0, 8);
  const maxMRR = topLanes.length > 0 ? Math.max(...topLanes.map(l => l.mrr_projected || 0)) : 1;

  // Narrative fields (from adaptive_forecast)
  const execSummary = (narrative && narrative.executive_summary) || '';
  const highlights = (narrative && narrative.lane_highlights) || [];
  const trendAnalysis = (narrative && narrative.trend_analysis) || '';
  const advice = (narrative && narrative.actionable_advice) || '';
  const risks = (narrative && narrative.risks) || [];

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Predictive <em>Revenue</em></div>
          <div class="section-sub">Per-lane MRR \u00b7 pipeline value \u00b7 LLM forecast</div>
        </div>
        <div class="section-sub">Auto-refresh \u00b7 60s</div>
      </div>

      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">24h Revenue</div>
          <div class="stat-value teal">$${totals.revenue_24h || 0}</div>
          <div class="stat-meta">${totals.calls_24h || 0} calls \u00b7 ${totals.active_buyers || 0} buyers</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Projected MRR</div>
          <div class="stat-value teal">$${totals.mrr_projected || 0}</div>
          <div class="stat-meta">${totals.lanes_active || 0} active lanes</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Revenue Health</div>
          <div class=${'stat-value ' + (health.status === 'critical' ? 'dim' : health.status === 'warning' ? 'dim' : 'teal')} style=${{color: health.status === 'critical' ? 'var(--status-red)' : health.status === 'warning' ? 'var(--status-amber)' : 'var(--signal-teal)'}}>${health.status || '\u2014'}</div>
          <div class="stat-meta">${health.pct_change || 0}% vs 7d avg</div>
        
        </div>
        <div class="stat-card">
          <div class="stat-label">Actual MRR</div>
          <div class=${'stat-value ' + ((mrrData||{}).actual_mrr > 0 ? "teal" : "dim")}>$${((mrrData||{}).actual_mrr||0).toLocaleString()}</div>
          <div class="stat-meta">${((mrrData||{}).subscriptions||[]).length} subs · ${((mrrData||{}).gap_pct||0)}% ${((mrrData||{}).gap||0) > 0 ? 'below projected' : 'of target'}</div>
        </div></div>
        <div class="stat-card">
          <div class="stat-label">Pipeline Value</div>
          <div class="stat-value cyan">$${totals.active_buyers || 0}</div>
          <div class="stat-meta">active buyer pipeline</div>
        </div>
      </div>

      ${health.alerts && health.alerts.length > 0 ? html`
      <div class="rv-alerts">
        ${health.alerts.map(a => html`
          <div class=${'rv-alert ' + (a.level || 'info')} key=${a.message}>
            <span class="rv-alert-lvl">${a.level || 'info'}</span>
            <span class="rv-alert-msg">${a.message}</span>
            ${a.niche ? html`<span class="rv-alert-niche">${a.niche}</span>` : ''}
          </div>
        `)}
      </div>
      ` : ''}

      <div class="rv-split">
        <div class="rv-panel">
          <div class="panel-head">Top Lanes by MRR</div>
          ${topLanes.map(l => {
            const barW = maxMRR > 0 ? Math.max(2, Math.round((l.mrr_projected / maxMRR) * 100)) : 0;
            const barColor = l.mrr_projected > 500 ? 'var(--signal-teal)' : l.mrr_projected > 100 ? 'var(--strike-cyan)' : 'var(--empire-mist)';
            return html`
            <div class="rv-bar-row" key=${l.lane_id}>
              <div class="rv-bar-label">
                <span class="rv-bar-lane">L${l.lane_id}</span>
                <span class="rv-bar-niche">${(l.niche || '').slice(0, 18)}</span>
              </div>
              <div class="rv-bar-track">
                <div class="rv-bar-fill" style=${{width: barW + '%', backgroundColor: barColor}}></div>
              </div>
              <div class="rv-bar-val">$${l.mrr_projected || 0}</div>
              <div class="rv-bar-meta">${l.calls_24h}c \u00b7 ${l.active_buyers}b</div>
            </div>
          `})}
          ${topLanes.length === 0 ? html`<div class="kb-empty">No lane data yet.</div>` : ''}
        </div>

        <div class="rv-panel">
          <div class="panel-head">Niche Summary</div>
          ${Object.values(nicheSummary).map(ns => {
            return html`
            <div class="rv-niche-card" key=${ns.niche}>
              <div class="rv-niche-name">${ns.niche}</div>
              <div class="rv-niche-stats">
                <span class="rv-niche-stat"><strong>$${ns.mrr_projected || 0}</strong> MRR</span>
                <span class="rv-niche-stat">$${ns.revenue_24h || 0}/24h</span>
                <span class="rv-niche-stat">${ns.calls_24h} calls</span>
                <span class="rv-niche-stat">${ns.active_buyers} buyers</span>
              </div>
              <div class="rv-niche-lanes">${ns.lane_count} lanes</div>
            </div>
          `})}
          ${Object.keys(nicheSummary).length === 0 ? html`<div class="kb-empty">No niche data yet.</div>` : ''}
        </div>
      </div>

      
      <!-- ── USDC Revenue Ledger ── -->
      <div class="rv-usdc-panel">
        <div class="chart-panel-h" style="margin-bottom:0;padding-bottom:0;border-bottom:none">
          <span class="chart-panel-title">On-Chain USDC Revenue</span>
          <span class="chart-panel-tag">Solana · verified payments</span>
        </div>
        ${(() => {
          if (usdcErr) return html`<div class="stub" style="margin-top:14px;padding:32px 16px"><div class="stub-body">Could not load USDC ledger: ${usdcErr}</div></div>`;
          if (!usdcData) return html`<div class="chart-empty" style="padding:32px 0">Loading USDC ledger…</div>`;
          const usdc = usdcData;
          const pms = usdc.payments || [];
          return html`
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0">
              <div class="stat-card" style="padding:14px">
                <div class="stat-label">USDC Received</div>
                <div class="stat-value teal" style="font-size:22px">$${usdc.total_usdc_all_time != null ? Number(usdc.total_usdc_all_time).toLocaleString(undefined, {minimumFractionDigits:2,maximumFractionDigits:6}) : '—'}</div>
                <div class="stat-meta">all time</div>
              </div>
              <div class="stat-card" style="padding:14px">
                <div class="stat-label">Transactions</div>
                <div class="stat-value" style="font-size:22px">${usdc.count || 0}</div>
                <div class="stat-meta">recent ${limit} payments</div>
              </div>
              <div class="stat-card" style="padding:14px">
                <div class="stat-label">This Window</div>
                <div class="stat-value cyan" style="font-size:22px">$${usdc.total_usdc_displayed != null ? Number(usdc.total_usdc_displayed).toLocaleString(undefined, {minimumFractionDigits:2,maximumFractionDigits:6}) : '—'}</div>
                <div class="stat-meta">displayed below</div>
              </div>
            </div>
            <table class="tbl">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Sender</th>
                  <th class="tbl-num">Amount (USDC)</th>
                  <th>Campaign</th>
                  <th class="tbl-mono">Sig (abbr.)</th>
                </tr>
              </thead>
              <tbody>
                ${pms.length === 0 ? html`<tr><td colspan="5" class="tbl-empty">No verified USDC payments yet.</td></tr>` :
                  pms.map(p => html`
                    <tr key=${p.transaction_signature}>
                      <td class="tbl-mono" style="color:var(--empire-fog)">${p.block_time_stamp ? new Date(p.block_time_stamp).toLocaleString() : new Date(p.logged_at).toLocaleString()}</td>
                      <td class="tbl-mono" style="max-width:120px;overflow:hidden;text-overflow:ellipsis" title=${p.sender_address}>${p.sender_address.slice(0,4)}…${p.sender_address.slice(-4)}</td>
                      <td class="tbl-num tbl-mono" style="color:var(--signal-teal);font-weight:600">${Number(p.usdc_amount).toLocaleString(undefined, {minimumFractionDigits:2,maximumFractionDigits:6})}</td>
                      <td class="tbl-mono" style="color:var(--empire-mist);max-width:100px;overflow:hidden;text-overflow:ellipsis">${p.tracking_memo || '—'}</td>
                      <td class="tbl-mono" style="color:var(--empire-fog);font-size:9px" title=${p.transaction_signature}>${p.transaction_signature.slice(0,8)}…</td>
                    </tr>
                  `)}
              </tbody>
            </table>
            <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:10px;text-align:right;letter-spacing:.04em">Source: Solana (empire_revenue_ledger) · 60s refresh</div>

      <!-- Activation Failed Payments (Crypto) -->
      ${cryptoStats && cryptoStats.activation_failed && cryptoStats.activation_failed.length > 0 ? html`
      <div class="rv-usdc-panel" style="margin-top:0">
        <div class="chart-panel-h" style="margin-bottom:0;padding-bottom:0;border-bottom:none">
          <span class="chart-panel-title">Activation Failed Payments</span>
          <span class="chart-panel-tag" style="color:var(--status-red)">needs operator review</span>
        </div>
        <table class="tbl" style="margin-top:12px">
          <thead>
            <tr>
              <th>Date</th>
              <th>Customer</th>
              <th>Tier</th>
              <th class="tbl-num">Amount</th>
              <th>Error</th>
              <th class="tbl-mono">TX</th>
            </tr>
          </thead>
          <tbody>
            ${cryptoStats.activation_failed.map(f => html`
              <tr key=${f.id}>
                <td class="tbl-mono" style="color:var(--empire-fog)">${f.failed_at ? new Date(f.failed_at).toLocaleString() : ''}</td>
                <td>${f.email}</td>
                <td class="tbl-mono" style="color:var(--status-red)">${f.tier}</td>
                <td class="tbl-num tbl-mono" style="color:var(--status-red)">$${f.amount.toFixed(2)}</td>
                <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title=${f.notes}>${f.notes || ''}</td>
                <td class="tbl-mono" style="color:var(--empire-fog);font-size:9px" title=${f.tx}>${f.tx || ''}</td>
              </tr>
            `)}
          </tbody>
        </table>
        <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:10px;text-align:right;letter-spacing:.04em">Source: crypto_payment_requests &middot; refresh on page load</div>
      </div>
      ` : ''}

      <!-- ── Referral Leaderboard ── -->
      ${refLeaderboard && refLeaderboard.leaderboard && refLeaderboard.leaderboard.length > 0 ? html`
      <div class="rv-referral-panel" style="margin-top:0">
        <div class="chart-panel-h" style="margin-bottom:0;padding-bottom:0;border-bottom:none">
          <span class="chart-panel-title">Referral Leaderboard</span>
          <span class="chart-panel-tag">${refLeaderboard.total_referrers || 0} referrers · top earners</span>
        </div>
        <table class="tbl" style="margin-top:12px">
          <thead>
            <tr>
              <th class="tbl-num">#</th>
              <th>Referrer</th>
              <th class="tbl-num">Referred</th>
              <th class="tbl-num">Total Earned</th>
              <th class="tbl-num">Paid</th>
            </tr>
          </thead>
          <tbody>
            ${refLeaderboard.leaderboard.map(e => html`
              <tr key=${e.rank}>
                <td class="tbl-num" style="font-weight:${e.rank <= 3 ? '700' : '400'};color:${e.rank === 1 ? 'var(--status-amber)' : e.rank <= 3 ? 'var(--signal-teal)' : 'var(--empire-fog)'}">
                  ${e.rank === 1 ? '\uD83E\uDD47 ' : e.rank === 2 ? '\uD83E\uDD48 ' : e.rank === 3 ? '\uD83E\uDD49 ' : ''}${e.rank}
                </td>
                <td style="font-weight:600">${e.is_you ? html`<span style="color:var(--signal-teal)">${e.name} ← You</span>` : html`<span style="cursor:pointer;border-bottom:1px dotted var(--empire-fog);color:var(--empire-silver)" onclick="(() => { fetch('/api/v1/contractor-public/' + encodeURIComponent(e.id)).then(r => r.json()).then(d => { if (d.ok) setProfileCtr(d); else setProfileCtr({ name: 'Not found' }); }).catch(() => setProfileCtr({ name: 'Error' })); })()">${e.name}</span>`}</td>
                <td class="tbl-num">${e.total_referrals}</td>
                <td class="tbl-num" style="color:var(--status-amber);font-weight:600">$${Number(e.total_earned).toLocaleString(undefined, {minimumFractionDigits:2})}</td>
                <td class="tbl-num" style="color:var(--signal-teal)">$${Number(e.total_paid).toLocaleString(undefined, {minimumFractionDigits:2})}</td>
              </tr>
            `)}
          </tbody>
        </table>
        <div style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-top:10px;text-align:right;letter-spacing:.04em">Source: referral_payouts · $500 bounty per contractor referral · 60s refresh</div>
      </div>
      ` : html`
      <div class="rv-referral-panel" style="margin-top:0">
        <div class="chart-panel-h" style="margin-bottom:0;padding-bottom:0;border-bottom:none">
          <span class="chart-panel-title">Referral Leaderboard</span>
          <span class="chart-panel-tag">no bounties earned yet</span>
        </div>
        <div class="tbl-empty" style="padding:32px 0">No referrals with earned bounties yet. Share contractor referral links to start earning $500 per closed deal.</div>
      </div>
      `}

          `;
        })()}
      </div>

      ${(execSummary || highlights.length > 0) ? html`${(execSummary || highlights.length > 0) ? html`
      <div class="rv-narrative-panel">
        <div class="rv-narrative-head">
          <span class="rv-narrative-title">AGI Revenue Narrative</span>
          <span class="rv-narrative-badge">few-shot · learning</span>
        </div>
        ${execSummary ? html`
        <div class="rv-narrative-summary">${execSummary}</div>
        ` : ''}
        ${highlights.length > 0 ? html`
        <div class="rv-narrative-section">
          <div class="rv-narrative-section-h">Lane Highlights</div>
          ${highlights.map(h => html`
            <div class="rv-narrative-item" key=${h}>${h}</div>
          `)}
        </div>
        ` : ''}
        ${trendAnalysis ? html`
        <div class="rv-narrative-section">
          <div class="rv-narrative-section-h">Trend Analysis</div>
          <div class="rv-narrative-item">${trendAnalysis}</div>
        </div>
        ` : ''}
        ${advice ? html`
        <div class="rv-narrative-section">
          <div class="rv-narrative-section-h">Actionable Advice</div>
          <div class="rv-narrative-item advice">${advice}</div>
        </div>
        ` : ''}
        ${risks.length > 0 ? html`
        <div class="rv-narrative-section">
          <div class="rv-narrative-section-h">Risks</div>
          ${risks.map((r, i) => html`
            <div class="rv-narrative-item risk" key=${i}>⚠ ${r}</div>
          `)}
        </div>
        ` : ''}
      </div>
      ` : ''}

      ${accuracy && accuracy.series && accuracy.series.length > 0 ? html`
      <div class="rv-accuracy-panel">
        <div class="rv-accuracy-head">
          <span class="rv-accuracy-title">Forecast vs Actual</span>
          <div class="rv-accuracy-actions">
            <button class="rv-export-btn csv" onClick=${() => window.open('/api/revenue/accuracy/csv?days=14', '_blank')}>Download CSV</button>
            <button class="rv-export-btn pdf" onClick=${() => window.open('/api/revenue/accuracy/report?days=14', '_blank')}>Print PDF</button>
          </div>
          <span class="rv-accuracy-summary">
            ${accuracy.summary ? Math.round(accuracy.summary.avg_accuracy_pct) + '% avg accuracy · ' + accuracy.summary.trend : ''}
          </span>
        </div>
        <div class="rv-accuracy-chart">
          ${accuracy.series.slice(0, 14).reverse().map(d => {
            const maxVal = Math.max(d.forecasted_fee || 1, d.actual_revenue || 1);
            const forecastW = maxVal > 0 ? Math.max(2, Math.round((d.forecasted_fee / maxVal) * 100)) : 0;
            const actualW = maxVal > 0 ? Math.max(2, Math.round((d.actual_revenue / maxVal) * 100)) : 0;
            const accColor = d.accuracy_pct != null ? (d.accuracy_pct >= 80 ? 'var(--signal-teal)' : d.accuracy_pct >= 50 ? 'var(--status-amber)' : 'var(--status-red)') : 'var(--empire-mist)';
            return html`
            <div class="rv-acc-row" key=${d.date}>
              <div class="rv-acc-date">${(d.date || '').slice(5)}</div>
              <div class="rv-acc-bars">
                <div class="rv-acc-bar-wrap">
                  <div class="rv-acc-bar forecast" style=${{width: forecastW + '%'}}></div>
                  <span class="rv-acc-bar-label">$${d.forecasted_fee || 0} fcst</span>
                </div>
                <div class="rv-acc-bar-wrap">
                  <div class="rv-acc-bar actual" style=${{width: actualW + '%'}}></div>
                  <span class="rv-acc-bar-label">$${d.actual_revenue || 0} actual</span>
                </div>
              </div>
              <div class="rv-acc-pct" style=${{color: accColor}}>
                ${d.accuracy_pct != null ? d.accuracy_pct + '%' : '—'}
              </div>
            </div>
          `})}
        </div>
        <div class="rv-accuracy-legend">
          <span class="rv-acc-legend-item"><span class="rv-acc-legend-swatch forecast"></span> Forecast</span>
          <span class="rv-acc-legend-item"><span class="rv-acc-legend-swatch actual"></span> Actual MRR</span>
          <span class="rv-acc-legend-item">Accuracy: <span style=${{color:'var(--signal-teal)'}}>≥80%</span> <span style=${{color:'var(--status-amber)'}}>50-79%</span> <span style=${{color:'var(--status-red)'}}><50%</span></span>
        </div>
      </div>
      ` : ''}

    </div>
  `;
}
// ── APP SHELL ────────────────────────────────────────────────────────
// ── SI STRATEGY EVOLUTION ─────────────────────────────────────────────
// ── SI ADAPTIVE ENGINE ──────────────────────────────────────────────────
function SiAdaptive() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    apiFetch('/api/si/adaptive').then(r => r.json())
      .then(d => { setData(d); setErr(null); })
      .catch(e => setErr(e.message));
  }, []);

  const apiError = data && data.error || null;
  if (err || apiError) return html`<div class="stub"><div class="stub-title">Could not load SI Adaptive data</div><div class="stub-body">${err || apiError}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading adaptive engine…</div></div>`;

  const subsystems = data.subsystems_registered || [];
  const recent = data.recent_changes || [];
  const totalAdopted = data.adaptations_applied || 0;
  const lastTs = data.last_apply_ts;

  const fmtVal = (v) => {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') {
      if (Number.isInteger(v)) return v.toString();
      if (Math.abs(v) < 0.01) return v.toFixed(4);
      return v.toFixed(3);
    }
    if (typeof v === 'boolean') return v ? 'true' : 'false';
    if (typeof v === 'string') return v;
    if (typeof v === 'object') return 'X';
    return String(v);
  };

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">SI <em>Adaptive Engine</em></div>
          <div class="section-sub">Subsystem adoption · parameter propagation</div>
        </div>
        ${lastTs ? html`<div class="rv-narrative-badge">last apply: ${lastTs.slice(0, 19).replace('T', ' ')}</div>` : ''}
      </div>

      <div class="sia-grid">
        <div class="sia-tile">
          <div class="sia-tile-label">Subsystems Registered</div>
          <div class="sia-tile-val">${subsystems.length}</div>
          <div class="sia-tile-sub">receiving parameter updates</div>
        </div>
        <div class="sia-tile">
          <div class="sia-tile-label">Adaptations Applied</div>
          <div class="sia-tile-val">${totalAdopted}</div>
          <div class="sia-tile-sub">total propagated changes</div>
        </div>
        <div class="sia-tile">
          <div class="sia-tile-label">Recent Batches</div>
          <div class="sia-tile-val">${recent.length}</div>
          <div class="sia-tile-sub">last 10 propagation events</div>
        </div>
        <div class="sia-tile">
          <div class="sia-tile-label">Status</div>
          <div class=${'sia-tile-val ' + (subsystems.length > 0 ? '' : 'dim')}>${subsystems.length > 0 ? 'LIVE' : 'IDLE'}</div>
          <div class="sia-tile-sub">${subsystems.length > 0 ? 'adaptive engine online' : 'no subsystems registered'}</div>
        </div>
      </div>

      <div class="sia-subsystem-panel">
        <div class="sia-subsystem-head">
          <span class="sia-subsystem-title">Registered Subsystems</span>
          <span class="sia-subsystem-count">${subsystems.length} consumers</span>
        </div>
        ${subsystems.length === 0 ? html`
          <div class="sia-adoption-empty">No subsystems registered yet — AdaptiveEngine.register_subsystem() has not been called.</div>
        ` : html`
          <div class="sia-subsystem-grid">
            ${subsystems.map(name => html`
              <div class="sia-sub-card" key=${name}>
                <div class="sia-sub-dot"></div>
                <div class="sia-sub-body">
                  <div class="sia-sub-name">${name}</div>
                  <div class="sia-sub-meta">listening for parameter updates</div>
                </div>
              </div>
            `)}
          </div>
        `}
      </div>

      <div class="sia-adoption-panel">
        <div class="sia-adoption-head">
          <span class="sia-adoption-title">Recent Adoption Log</span>
          <span class="sia-adoption-count">${recent.length} batches · last 10 events</span>
        </div>
        ${recent.length === 0 ? html`
          <div class="sia-adoption-empty">No adoption events yet — SI core has not propagated any parameters to subsystems.</div>
        ` : html`
          <div class="sia-adoption-feed">
            ${recent.map((batch, i) => {
              const ts = (batch.ts || '').slice(0, 19).replace('T', ' ');
              const changes = batch.changes || [];
              const count = batch.count != null ? batch.count : changes.length;
              return html`
                <div class="sia-adoption-batch" key=${`batch-${i}`}>
                  <div class="sia-adoption-head-row">
                    <span class="sia-adoption-ts">${ts}</span>
                    <span class="sia-adoption-bdg">${count} change${count === 1 ? '' : 's'}</span>
                  </div>
                  <div class="sia-adoption-changes">
                    ${changes.map((c, j) => html`
                      <div class="sia-adoption-change" key=${j}>
                        <span class="sia-change-key">${c.key}</span>
                        <span class="sia-change-sub">${c.subsystem || 'unknown'}</span>
                        <span style=${{color:'var(--empire-fog)'}}>→</span>
                        <span class="sia-change-val">${fmtVal(c.value)}</span>
                      </div>
                    `)}
                  </div>
                </div>
              `;
            })}
          </div>
        `}
      </div>
    </div>
  `;
}

function SiEvolution() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    apiFetch('/api/si/snapshot').then(r => r.json())
      .then(d => { setData(d); setErr(null); })
      .catch(e => setErr(e.message));
  }, []);

  const apiError = data.error || null;
  if (err || apiError) return html`<div class="stub"><div class="stub-title">Could not load SI data</div><div class="stub-body">${err || apiError}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const byNiche = data.by_niche || {};
  const best = data.best_per_niche || {};
  const niches = Object.keys(byNiche).filter(n => n !== '__base__' && (byNiche[n] || []).length > 0);

  // Color map for genome traits
  const traitColors = {
    aggressiveness:     '#FF4444',
    risk_tolerance:     '#FFB800',
    outreach_intensity: '#5AC8FA',
    price_premium:      '#44E5B8',
    narrow_focus:       '#C8A2C8',
  };
  const traitLabels = {
    aggressiveness:     'Aggression',
    risk_tolerance:     'Risk Tol.',
    outreach_intensity: 'Outreach',
    price_premium:      'Premium',
    narrow_focus:       'Focus',
  };

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">SI <em>Strategy Evolution</em></div>
          <div class="section-sub">Genomes · win rates · generation tracking</div>
        </div>
        <div class="rv-narrative-badge">${data.evolution_runs || 0} evolutions · ${data.active_strategies || 0} active</div>
      </div>

      ${niches.length === 0 ? html`
        <div class="tbl-empty">No evolved strategies yet — outcomes need to flow through the SI core first.</div>
      ` : niches.map(niche => {
        const strategies = byNiche[niche] || [];
        const bestInfo = best[niche] || {};
        strategies.sort((a, b) => b.score - a.score);
        return html`
      <div class="si-niche-panel" key=${niche}>
        <div class="si-niche-head">
          <div class="si-niche-name">${niche}</div>
          <div class="si-niche-meta">
            <span>Best: <strong>${bestInfo.name || '—'}</strong></span>
            <span class="si-niche-score">${(bestInfo.score || 0).toFixed(3)}</span>
          </div>
        </div>

        <div class="si-strategy-grid">
          ${strategies.map(s => {
            const winRate = s.runs > 0 ? (s.wins / s.runs * 100).toFixed(0) : 0;
            const isBest = s.name === bestInfo.name;
            return html`
          <div class=${'si-strat-card ' + (isBest ? 'best' : '')} key=${s.id}>
            <div class="si-strat-top">
              <div class="si-strat-name">${s.name}</div>
              <div>
                ${s.generation > 0 ? html`<span class="si-gen-bdg">Gen ${s.generation}</span>` : ''}
                <span class="si-parent-bdg">${s.parent || s.name}</span>
              </div>
            </div>

            <div class="si-strat-stats">
              <div class="si-stat"><span class="si-stat-val teal">${s.score.toFixed(3)}</span><span class="si-stat-lbl">score</span></div>
              <div class="si-stat"><span class="si-stat-val">${winRate}%</span><span class="si-stat-lbl">win rate</span></div>
              <div class="si-stat"><span class="si-stat-val dim">${s.runs}</span><span class="si-stat-lbl">runs</span></div>
              <div class="si-stat"><span class="si-stat-val${s.generation > 1 ? ' cyan' : ' dim'}">${s.generation}</span><span class="si-stat-lbl">gen</span></div>
            </div>

            <div class="si-genome">
              <div class="si-genome-label">Genome</div>
              ${Object.entries(s.genome || {}).map(([trait, val]) => {
                const pct = Math.round(val * 100);
                const color = traitColors[trait] || '#64748B';
                const label = traitLabels[trait] || trait;
                return html`
              <div class="si-trait" key=${trait}>
                <div class="si-trait-head">
                  <span class="si-trait-name">${label}</span>
                  <span class="si-trait-pct" style=${{color}}>${pct}%</span>
                </div>
                <div class="si-trait-track">
                  <div class="si-trait-fill" style=${{width: pct + '%', background: color}}></div>
                </div>
              </div>
              `;
              })}
            </div>
          </div>
          `;
          })}
        </div>
      </div>
      `;
      })}

      ${data.last_evolution_ts ? html`
      <div class="si-evo-footer">
        <span>Last evolution: ${data.last_evolution_ts.slice(0, 19).replace('T', ' ')}</span>
        <span>${data.inactive_strategies || 0} inactive strategies pruned</span>
      </div>
      ` : ''}

      ${(data.evolution_events || []).length > 0 ? html`
      <div class="si-evo-history">
        <div class="si-evo-history-head">
          <span class="si-evo-history-title">Evolution Event History</span>
          <span class="si-evo-history-count">${data.evolution_events.length} events</span>
        </div>
        <div class="si-evo-events">
          ${data.evolution_events.map(ev => {
            const ts = (ev.ts || '').slice(0, 19).replace('T', ' ');
            if (ev.type === 'evolve') {
              return html`
            <div class="si-evo-event" key=${ev.new_strategy + ev.generation}>
              <span class="si-evo-event-ts">${ts}</span>
              <span class="si-evo-event-type evolve">EVOLVED</span>
              <span class="si-evo-event-niche">${ev.niche || ''}</span>
              <span class="si-evo-event-detail">${ev.new_strategy} ← ${ev.parent} (gen ${ev.generation})</span>
            </div>
            `;
            } else if (ev.type === 'deactivate') {
              return html`
            <div class="si-evo-event" key=${(ev.deactivated || []).join(',')}>
              <span class="si-evo-event-ts">${ts}</span>
              <span class="si-evo-event-type deactivate">PRUNED</span>
              <span class="si-evo-event-niche">${ev.niche || ''}</span>
              <span class="si-evo-event-detail">${(ev.deactivated || []).join(', ')}</span>
            </div>
            `;
            }
            return '';
          })}
        </div>
      </div>
      ` : ''}
    </div>
  `;
}

// ── PANEL_COURT 5-PANEL CONSENSUS ──────────────────────────────────────────
function PanelCourtPanel() {
  const [data, setData] = useState(null);
  const [pool, setPool] = useState(null);
  const [err, setErr] = useState(null);
  const [selectedAgentId, setSelectedAgentId] = useState(null);
  const [hoveredAgentId, setHoveredAgentId] = useState(null);
  const [hoverPos, setHoverPos] = useState({x:0,y:0});
  const [expanded, setExpanded] = useState(null);
  const [highlighted, setHighlighted] = useState(null);
  const chartDrawn = useRef(false);

  useEffect(() => {
    Promise.all([
      apiFetch('/api/panel_court/decisions?limit=30').then(r => r.json()),
      apiFetch('/api/panel_court/pool').then(r => r.json()),
    ]).then(([decisions, poolData]) => {
      setData(decisions.decisions || []);
      setPool(poolData);
    }).catch(e => setErr(e.message));
  }, []);

  // Real-time pool updates via WebSocket (with reconnection + SSE fallback)
  const poolOnEvent = useCallback((data) => {
    if (data.type === 'panel_court_pool' && data.agents) setPool(data);
  }, []);
  useLiveSocket(poolOnEvent);

  const poolErr = pool && pool.error;
  if (err) return html`<div class="stub"><div class="stub-title">Could not load Panel Court</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const dispatched = data.filter(d => d.verdict === 'DISPATCH').length;
  const rejected = data.filter(d => d.verdict === 'REJECT').length;
  const avgScore = data.length > 0 ? Math.round(data.reduce((s, d) => s + (d.score || 0), 0) / data.length) : 0;
  const totalRuns = pool && pool.agents ? pool.agents.reduce((s, a) => s + (a.total_runs || 0), 0) : 0;

  // Agent pool sorted by win rate
  useEffect(() => { if (pool && pool.temperature_history && pool.temperature_history.length >= 2) { chartDrawn.current = true; } }, [pool]);

  const agents = (pool && pool.agents ? [...pool.agents] : []).sort((a, b) => (a.id || 0) - (b.id || 0));

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Panel Court <em>10-Agent Ensemble</em></div>
          <div class="section-sub">Parallel scoring · 5-role voting · learning loop</div>
        </div>
        <div class="section-sub">${data.length} decisions · ${totalRuns} agent runs</div>
      </div>

      <!-- ── Summary Cards ── -->
      <div class="pc-summary-grid">
        <div class="pc-summary-card">
          <div class="pc-summary-val teal">${dispatched}</div>
          <div class="pc-summary-lbl">Dispatched</div>
        </div>
        <div class="pc-summary-card">
          <div class="pc-summary-val amber">${rejected}</div>
          <div class="pc-summary-lbl">Rejected</div>
        </div>
        <div class="pc-summary-card">
          <div class=${'pc-summary-val ' + (avgScore >= 80 ? 'teal' : avgScore >= 60 ? 'amber' : 'red')}>${avgScore}</div>
          <div class="pc-summary-lbl">Avg Score</div>
        </div>
        <div class="pc-summary-card">
          <div class="pc-summary-val dim">${totalRuns}</div>
          <div class="pc-summary-lbl">Agent Runs</div>
        </div>
      </div>

      <!-- ── 10-Agent Orbital Ring ── -->
      ${agents.length > 0 ? html`
      <div class="pc-pool-panel">
        <div class="pc-pool-head">
          <span class="pc-pool-title">Agent Pool</span>
          <span class="pc-pool-tag">${agents.filter(a => a.total_runs > 0).length}/10 active · orbital mesh</span>
        </div>
        <div class="pc-orbital-wrapper">
          ${(() => {
            const cx = 0, cy = 0;
            const orbitR = 180;  // radius for the 10-agent ring
            const innerR = 110;  // inner decorative ring
            const outerR = 240;  // outer decorative ring
            const svgW = outerR * 2 + 20;
            const svgH = outerR * 2 + 20;
            
            // SVG for rings and connection lines
            const winnerId = data.length > 0 ? data[0].winner_agent_id : null;
            const svgLines = agents.map((a, i) => {
              const angleDeg = (i * 360 / agents.length) - 90; // start from top
              const angleRad = angleDeg * Math.PI / 180;
              const ax = Math.cos(angleRad) * orbitR;
              const ay = Math.sin(angleRad) * orbitR;
              const isWinner = a.id === winnerId;
              return html`<line 
                x1="0" y1="0" 
                x2="${ax}" y2="${ay}" 
                class=${'pc-orbit-line' + (isWinner ? ' winner' : '')} 
                style=${{animationDelay: (i * 0.1) + 's'}}
              />`;
            });
            
            return html`
              <svg class="pc-orbital-svg" width="${svgW}" height="${svgH}" viewBox="${-svgW/2} ${-svgH/2} ${svgW} ${svgH}">
                <!-- Outer ring -->
                <circle cx="0" cy="0" r="${outerR}" class="pc-orbit-ring outer"/>
                <!-- Main orbit ring -->
                <circle cx="0" cy="0" r="${orbitR}" class="pc-orbit-ring pulse"/>
                <!-- Inner ring -->
                <circle cx="0" cy="0" r="${innerR}" class="pc-orbit-ring inner"/>
                <!-- Connection lines from center -->
                ${svgLines}
                <!-- Critique arrows between agents -->
                ${(() => {
                  const d0 = data;
                  const crits = (d0 && d0.length > 0 && d0[0].agent_critiques) 
                    ? (typeof d0[0].agent_critiques === 'string' 
                        ? JSON.parse(d0[0].agent_critiques) 
                        : d0[0].agent_critiques) 
                    : [];
                  return crits.map((cr, ci) => {
                    const cidx = (cr.critic_id || 1) - 1;
                    const tidx = (cr.target_id || 1) - 1;
                    const cAngle = (cidx * 360 / 10 - 90) * Math.PI / 180;
                    const tAngle = (tidx * 360 / 10 - 90) * Math.PI / 180;
                    
                    // critique ring, inside orbit to avoid card overlap
                    const cx = Math.cos(cAngle) * 148;
                    const cy = Math.sin(cAngle) * 148;
                    const tx = Math.cos(tAngle) * 148;
                    const ty = Math.sin(tAngle) * 148;
                    // Arrowhead
                    const dx = tx - cx, dy = ty - cy;
                    const len = Math.sqrt(dx*dx+dy*dy) || 1;
                    const ux = dx/len, uy = dy/len;
                    const sevCls = (cr.severity || 0) >= 7 ? 'severe' : (cr.severity || 0) <= 3 ? 'mild' : '';
                    const tipX = tx - ux * 8;
                    const tipY = ty - uy * 8;
                    const wing = 4;
                    const px = -uy * wing, py = ux * wing;
                    const pts = `${tx.toFixed(1)},${ty.toFixed(1)} ${(tipX+px).toFixed(1)},${(tipY+py).toFixed(1)} ${(tipX-px).toFixed(1)},${(tipY-py).toFixed(1)}`;
                    return html`
                      <line key=${'crline'+ci} x1="${cx.toFixed(1)}" y1="${cy.toFixed(1)}" x2="${tx.toFixed(1)}" y2="${ty.toFixed(1)}" class=${'pc-critique-arrow' + (sevCls ? ' ' + sevCls : '')}/>
                      <polygon key=${'crhead'+ci} points="${pts}" class=${'pc-critique-arrowhead' + (sevCls ? ' ' + sevCls : '')}/>
                    `;
                  });
                })()}
              </svg>
              
              <!-- Boss agent (center) -->
              <div class="pc-boss-card">
                <span class="pc-boss-label">Panel Court</span>
                <span class="pc-boss-title">The Judge</span>
                <span class="pc-boss-sub">5-Role Panel</span>
                <div class="pc-boss-roles">
                  <span class="pc-boss-role">CFO</span>
                  <span class="pc-boss-role">Growth</span>
                  <span class="pc-boss-role">Strategy</span>
                  <span class="pc-boss-role">Purist</span>
                  <span class="pc-boss-role">Judge</span>
                </div>
              </div>
              
              <!-- Hover tooltip -->
              ${hoveredAgentId ? html`
                <div class="pc-hover-tooltip" style=${{position:'fixed',left:hoverPos.x+14+'px',top:hoverPos.y-10+'px',zIndex:9999}}>
                  ${(() => { const ha = agents.find(a=>a.id===hoveredAgentId); if(!ha) return ''; return html`
                    <div class="pc-tooltip-framing">${ha.framing||'No framing available'}</div>
                    <div class="pc-tooltip-stats">
                      <span>Temp: ${(ha.temperature||0).toFixed(2)}°</span>
                      <span>Wins: ${ha.wins||0}</span>
                      <span>Losses: ${ha.losses||0}</span>
                      <span>Win rate: ${Math.round((ha.win_rate||0)*100)}%</span>
                    </div>
                    <div class="pc-tooltip-stats">
                      <span>Avg score: ${(ha.avg_score||0).toFixed(1)}</span>
                      <span>Accuracy: ${(ha.accuracy_weight||1.0).toFixed(2)}x</span>
                      <span>Conv rate: ${Math.round((ha.real_conversion_rate||0)*100)}%</span>
                    </div>
                  `; })()}
                </div>
              ` : ''}
              <!-- 10 orbiting agents -->
              ${agents.map((a, i) => {
                const angleDeg = (i * 360 / agents.length) - 90;
                const angleRad = angleDeg * Math.PI / 180;
                const ax = Math.cos(angleRad) * orbitR;
                const ay = Math.sin(angleRad) * orbitR;
                const wr = a.win_rate || 0;
                const wrPct = Math.round(wr * 100);
                const tempCls = a.temperature <= 0.08 ? 'cold' : a.temperature >= 0.12 ? 'hot' : 'warm';
                const wonLast = data.length > 0 && data[0].winner_agent_id === a.id;
                
                const isSelected = selectedAgentId === a.id;
                const selCls = isSelected ? ' selected' : '';
                return html`
                  <div class=${'pc-orbital-agent' + (wonLast ? ' winner' : '') + selCls}
                       style=${{transform: 'translate(-50%,-50%) translate(' + ax + 'px,' + ay + 'px)', animationDelay: (i * 0.05) + 's'}}
                       onClick=${() => setSelectedAgentId(isSelected ? null : a.id)}
                       onMouseEnter=${(e) => { setHoveredAgentId(a.id); setHoverPos({x: e.clientX, y: e.clientY}); }}
                       onMouseLeave=${() => setHoveredAgentId(null)}>
                    <span class="pc-orbital-agent-id">#${a.id}</span>
                    <span class=${'pc-orbital-agent-temp ' + tempCls}>${a.temperature.toFixed(2)}°</span>
                    <span class="pc-orbital-agent-wr">${wrPct}%</span>
                    <span class="pc-orbital-agent-wl">${a.wins}W ${a.losses}L</span>
                    ${wonLast ? html`<span class="pc-orbital-agent-won">★ Winner</span>` : ''}
                    ${isSelected ? html`<span class="pc-orbital-agent-won" style=${{top:'auto',bottom:'-8px',color:'var(--strike-cyan)',borderColor:'rgba(90,200,250,0.3)'}}>▼ Selected</span>` : ''}
                  </div>
                `;
              })}
            `;
          })()}
        </div>
      </div>
      ` : ''}

      <!-- ── Temperature Convergence Chart ── -->
      ${(() => {
        const history = pool && pool.temperature_history ? pool.temperature_history : [];
        const agents = pool && pool.agents ? pool.agents : [];
        if (history.length < 2) return '';
        
        const chartW = 640;
        const chartH = 200;
        const padL = 32, padR = 16, padT = 10, padB = 28;
        const plotW = chartW - padL - padR;
        const plotH = chartH - padT - padB;
        const maxCycles = history.length;
        const allTemps = history.flat();
        const dataMin = allTemps.length > 0 ? Math.min(...allTemps) : 0.05;
        const dataMax = allTemps.length > 0 ? Math.max(...allTemps) : 0.14;
        const tempMin = Math.max(0.03, dataMin - 0.015);
        const tempMax = Math.min(0.85, dataMax + 0.015);
        const tempSpan = tempMax - tempMin || 0.01;
        
        // Y-axis labels
        const tickCount = 4;
        const yTicks = Array.from({length: tickCount}, (_, i) => Math.round((tempMin + (tempSpan * i / (tickCount - 1))) * 100) / 100);
        const yLines = yTicks.map(t => {
          const y = padT + plotH * (1 - (t - tempMin) / tempSpan);
          return html`<line key=${'yg'+t} x1="${padL}" y1="${y.toFixed(1)}" x2="${padL+plotW}" y2="${y.toFixed(1)}" class="pc-converge-grid"/>`;
        });
        
        // X-axis labels (cycle numbers)
        const xLabelStep = Math.max(1, Math.floor(maxCycles / 8));
        const xLabels = [];
        for (let c = 0; c < maxCycles; c += xLabelStep) {
          const x = padL + (c / (maxCycles - 1 || 1)) * plotW;
          xLabels.push(html`<text key=${'xl'+c} x="${x.toFixed(1)}" y="${chartH - 6}" class="pc-converge-label" text-anchor="middle">${c}</text>`);
        }
        
        // Y-axis labels
        const yLabelEls = yTicks.map(t => {
          const y = padT + plotH * (1 - (t - tempMin) / tempSpan);
          return html`<text key=${'yl'+t} x="${padL - 4}" y="${y.toFixed(1)+3}" class="pc-converge-y-label" text-anchor="end">${t.toFixed(2)}</text>`;
        });
        
        // Agent color palette
        const agentColors = ['#44E5B8','#FFB800','#FF6444','#5AC8FA','#C8A2C8','#FF8C42',
                              '#7B68EE','#FF69B4','#20B2AA','#F0E68C'];
        
        // Line paths for each agent
        const agentLines = agents.map((a, ai) => {
          const color = agentColors[ai % agentColors.length];
          const pts = [];
          for (let c = 0; c < maxCycles; c++) {
            if (history[c] && history[c][ai] != null) {
              const x = padL + (c / (maxCycles - 1 || 1)) * plotW;
              const y = padT + plotH * (1 - (history[c][ai] - tempMin) / tempSpan);
              pts.push(x.toFixed(1) + ',' + y.toFixed(1));
            }
          }
          if (pts.length < 2) return '';
          const d = 'M' + pts.join(' L');
          const lineOpacity = highlighted != null ? (highlighted === ai ? 1 : 0.15) : 1;
          const drawStyle = !chartDrawn.current ? {strokeDasharray:'1000',strokeDashoffset:'1000',animation:'pc-chart-draw 1.2s var(--ease-out-empire) '+(ai * 0.08)+'s forwards'} : {};
          return html`<path key=${'line'+a.id} d="${d}" class="pc-converge-line" stroke="${color}" opacity="${lineOpacity}" style=${drawStyle}/>`;
        });
        
        // Legend
        const legendItems = agents.map((a, ai) => {
          const color = agentColors[ai % agentColors.length];
          const id = 'conv_legend_' + a.id;
          return html`<span key=${id} class=${"pc-converge-legend-item" + (highlighted != null && highlighted !== ai ? " dimmed" : "")} onClick=${() => setHighlighted(highlighted === ai ? null : ai)}>
            <span class="pc-converge-legend-swatch" style=${{background: color}}></span>
            #${a.id}
          </span>`;
        });
        
        return html`
                      <!-- Selected agent detail -->
              ${selectedAgentId ? html`
                <div class="pc-agent-detail">
                  ${(() => {
                    const sa = agents.find(a => a.id === selectedAgentId);
                    if (!sa) return '';
                    return html`
                      <div class="pc-agent-detail-head">
                        <div class="pc-agent-detail-title">Agent #${sa.id} — Full Stats</div>
                        <button class="pc-agent-detail-close" onClick=${() => setSelectedAgentId(null)}>✕</button>
                      </div>
                      <div class="pc-agent-detail-body">
                        <div class="pc-agent-detail-framing">${sa.framing || 'No framing data'}</div>
                        <div class="pc-agent-detail-grid">
                          <div class="pc-agent-stat"><span class="pc-agent-stat-val">${(sa.temperature||0).toFixed(3)}°</span><span class="pc-agent-stat-lbl">Temperature</span></div>
                          <div class="pc-agent-stat"><span class="pc-agent-stat-val">${sa.wins||0}</span><span class="pc-agent-stat-lbl">Wins</span></div>
                          <div class="pc-agent-stat"><span class="pc-agent-stat-val">${sa.losses||0}</span><span class="pc-agent-stat-lbl">Losses</span></div>
                          <div class="pc-agent-stat"><span class="pc-agent-stat-val">${Math.round((sa.win_rate||0)*100)}%</span><span class="pc-agent-stat-lbl">Win Rate</span></div>
                          <div class="pc-agent-stat"><span class="pc-agent-stat-val">${(sa.avg_score||0).toFixed(1)}</span><span class="pc-agent-stat-lbl">Avg Score</span></div>
                          <div class="pc-agent-stat"><span class="pc-agent-stat-val">${(sa.accuracy_weight||1.0).toFixed(2)}x</span><span class="pc-agent-stat-lbl">Accuracy Weight</span></div>
                          <div class="pc-agent-stat"><span class="pc-agent-stat-val">${sa.total_runs||0}</span><span class="pc-agent-stat-lbl">Total Runs</span></div>
                          <div class="pc-agent-stat"><span class="pc-agent-stat-val">${Math.round((sa.real_conversion_rate||0)*100)}%</span><span class="pc-agent-stat-lbl">Real Conv Rate</span></div>
                        </div>
                        <div class="pc-agent-detail-meta">
                          <span>Real dispatches: ${sa.real_dispatches||0}</span>
                        </div>
                      </div>
                    `;
                  })()}
                </div>
              ` : ''}
<div class="pc-converge-panel">
          <div class="pc-converge-head">
            <span class="pc-converge-title">Temperature Convergence</span>
            <span class="pc-converge-count">${maxCycles} cycles · ${agents.length} agents</span>
          </div>
          <div class="pc-converge-chart">
            <svg class="pc-converge-svg" viewBox="0 0 ${chartW} ${chartH}" preserveAspectRatio="xMidYMid meet">
              ${yLines}
              ${yLabelEls}
              ${xLabels}
              ${agentLines}
            </svg>
          </div>
          <div class="pc-converge-legend">
            ${legendItems}
          </div>
        </div>
        `;
      })()}

      <!-- ── Decision List ── -->
      <div class="pc-decision-panel">
        <div class="pc-decision-head">
          <span class="pc-decision-title">Ensemble History</span>
          <span class="pc-decision-count">${data.length} decisions</span>
        </div>
        ${data.length === 0 ? html`
          <div class="tbl-empty">No ensemble decisions yet — run the dispatcher to see Panel Court in action.</div>
        ` : html`
        <div class="pc-decision-list">
          ${data.map(d => {
            const isExpanded = expanded === d.lead_id;
            const scores = typeof d.per_agent_scores === 'string' ? JSON.parse(d.per_agent_scores || '{}') : (d.per_agent_scores || {});
            const winner = d.winner_agent_id;
            return html`
              <div class=${'pc-decision-card' + (isExpanded ? ' expanded' : '')} onClick=${() => setExpanded(isExpanded ? null : d.lead_id)}>
                <div class="pc-decision-row">
                  <div class="pc-decision-lead">
                    <span class="pc-decision-lead-name">${d.lead_summary || '—'}</span>
                    <span class="pc-decision-lead-id">${(d.lead_id || '').slice(0, 12)}</span>
                  </div>
                  <div class="pc-decision-winner">
                    <span class="pc-winner-badge">Agent #${winner}</span>
                  </div>
                  <div class=${'pc-score-circle ' + (d.score >= 80 ? 'pc-score-ok' : d.score >= 50 ? 'pc-score-warn' : 'pc-score-bad')}>
                    ${d.score || '—'}
                  </div>
                  <div class="pc-decision-verdict">
                    <span class=${'pc-verdict-badge ' + (d.verdict === 'DISPATCH' ? 'dispatch' : 'reject')}>${d.verdict || '?'}</span>
                  </div>
                </div>
                ${isExpanded ? html`
                <div class="pc-decision-detail">
                  <div class="pc-detail-title">Per-Agent Scores</div>
                  <div class="pc-detail-scores">
                    ${Object.entries(scores).map(([aid, score]) => {
                      const isWinner = parseInt(aid) === winner;
                      return html`
                        <div class=${'pc-detail-score' + (isWinner ? ' winner' : '')}>
                          <span class="pc-detail-aid">Agent #${aid}</span>
                          <span class="pc-detail-pts">${score}</span>
                        </div>
                      `;
                    })}
                  </div>
                  ${(() => {
                    const crits = d.agent_critiques 
                      ? (typeof d.agent_critiques === 'string' ? JSON.parse(d.agent_critiques) : d.agent_critiques) 
                      : [];
                    if (!crits || crits.length === 0) return '';
                    return html`
                    <div class="pc-critique-detail">
                      <div class="pc-critique-title">Agent Critique Rounds</div>
                      ${crits.map((cr, ci) => {
                        const sev = cr.severity || 0;
                        const sevCls = sev >= 7 ? 'severe' : sev <= 3 ? 'mild' : '';
                        const sevLabel = sev >= 7 ? 'high' : sev <= 3 ? 'low' : '';
                        return html`
                        <div key=${'crit'+ci} class=${'pc-critique-card' + (sevCls ? ' ' + sevCls : '')}>
                          <div class="pc-critique-head">
                            <span class="pc-critique-flow">Agent #${cr.critic_id} → #${cr.target_id}</span>
                            <span class=${'pc-critique-sev' + (sevLabel ? ' ' + sevLabel : '')}>sev ${sev}/10</span>
                            ${cr.suggested_adjustment != null ? html`<span class="pc-critique-adj">${cr.suggested_adjustment > 0 ? '+' : ''}${cr.suggested_adjustment.toFixed(1)}</span>` : ''}
                          </div>
                          <div class="pc-critique-text">${cr.critique_text || '—'}</div>
                        </div>
                        `;
                      })}
                    </div>
                    `;
                  })()}
                  ${d.judge_reasoning ? html`
                    <div class="pc-judge-block">
                      <div class="pc-judge-head">AGI Judge</div>
                      <div class="pc-judge-reasoning">${d.judge_reasoning}</div>
                    </div>
                  ` : ''}
                  ${d.hybrid_reasoning ? html`
                    <div class="pc-judge-block hybrid">
                      <div class="pc-judge-head">⚡ Hybrid Synthesizer <span style=${{fontWeight:'400',opacity:'0.7',fontSize:'0.8em'}}>(weighted blend of all 5 perspectives)</span></div>
                      <div class="pc-judge-reasoning">${d.hybrid_reasoning}</div>
                    </div>
                  ` : ''}
                </div>
                ` : ''}
              </div>
            `;
          })}
        </div>
        `}
      </div>
    </div>
  `;
}
function SEOPanel() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    apiFetch('/api/seo/performance').then(r => r.json())
      .then(d => { setData(d); setErr(null); })
      .catch(e => setErr(e.message));
    apiFetch('/api/seo/genome-history?limit=10').then(r => r.json()).then(gh => setGenomeHistory(gh)).catch(() => {})
  }, []);

  if (err) return html`<div class="stub"><div class="stub-title">Could not load SEO data</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const s = data.stats || {};
  const genome = data.genome || {};
  const audits = data.audits || [];
  const keywords = data.keywords || [];
  const content = data.content || [];
  const topKeywords = keywords.filter(k => (k.conversion_rate || 0) > 0).slice(0, 10);

  const traitColors = {
    keyword_competitiveness: '#FF4444',
    local_intent:            '#5AC8FA',
    content_depth:           '#44E5B8',
    technical_rigor:         '#FFB800',
    link_authority:          '#C8A2C8',
  };
  const traitLabels = {
    keyword_competitiveness: 'Competition',
    local_intent:            'Local Intent',
    content_depth:           'Depth',
    technical_rigor:         'Technical',
    link_authority:          'Authority',
  };

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">SEO <em>Optimization</em></div>
          <div class="section-sub">Audits · keyword tracking · content generation · genome evolution</div>
        </div>
        <div class="rv-narrative-badge">Gen ${data.evolution_runs || 0} · ${s.leads_attributed || 0} leads attributed</div>
      </div>

      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">Audits Run</div>
          <div class="stat-value dim">${s.audits_run || 0}</div>
          <div class="stat-meta">website health checks</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Keywords Tracked</div>
          <div class="stat-value cyan">${s.keywords_tracked || 0}</div>
          <div class="stat-meta">with intent & competition data</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Content Generated</div>
          <div class="stat-value teal">${s.content_generated || 0}</div>
          <div class="stat-meta">LLM-optimized pages</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Revenue</div>
          <div class="stat-value teal">$${(s.total_revenue || 0).toLocaleString()}</div>
          <div class="stat-meta">${s.total_conversions || 0} conversions · ${(s.avg_conversion_rate || 0).toFixed(1)}% avg rate</div>
        </div>
      </div>

      
      ${data.churn_stats && data.churn_stats.total_churned > 0 ? html`
        <div class="panel" style="margin-bottom:20px">
          <div class="panel-head">Churn Breakdown</div>
          <div class="tp-churn-strip">
            <div class="tp-churn-stat">
              <div class="tp-stat-val red">${data.churn_stats.total_churned}</div>
              <div class="tp-stat-lbl">Churned</div>
            </div>
            <div class="tp-churn-stat">
              <div class="tp-stat-val teal">$${Number(data.churn_stats.total_mrr_lost).toLocaleString()}</div>
              <div class="tp-stat-lbl">MRR Lost</div>
            </div>
            <div class="tp-churn-stat">
              <div class="tp-stat-val ${(data.churn_stats.churn_rate || 0) > 0.5 ? 'red' : 'dim'}">${Math.round((data.churn_stats.churn_rate || 0) * 100)}%</div>
              <div class="tp-stat-lbl">Churn Rate</div>
            </div>
            <div class="tp-churn-stat">
              <div class="tp-stat-val dim">$${Number(data.churn_stats.mrr_per_churn || 0).toFixed(0)}</div>
              <div class="tp-stat-lbl">Avg / Churn</div>
            </div>
          </div>
          ${data.churn_stats.top_reasons.length > 0 ? html`
            <div style="margin-top:16px;border-top:1px solid var(--empire-divider);padding-top:14px">
              <div class="panel-head" style="margin-bottom:10px">Top Churn Reasons</div>
              ${data.churn_stats.top_reasons.map((r, i) => html`
                <div class="tp-reason-row">
                  <span class="tp-reason-rank">${i + 1}</span>
                  <div class="tp-reason-bar-track">
                    <div class="tp-reason-bar-fill" style="width:${Math.round(r.count / data.churn_stats.top_reasons[0].count * 100)}%"></div>
                  </div>
                  <span class="tp-reason-label">${r.reason}</span>
                  <span class="tp-reason-count">${r.count}</span>
                </div>
              `)}
            </div>
          ` : ''}
        </div>
      ` : ''}
      ${data.win_back_stats && data.win_back_stats.win_backs_sent > 0 ? html`
        <div class="panel" style="margin-bottom:20px">
          <div class="panel-head">Win-Back Sequence</div>
          <div class="tp-churn-strip">
            <div class="tp-churn-stat">
              <div class="tp-stat-val teal">${data.win_back_stats.win_backs_sent}</div>
              <div class="tp-stat-lbl">Win-Backs Sent</div>
            </div>
            <div class="tp-churn-stat">
              <div class="tp-stat-val dim">${data.win_back_stats.followups_sent}</div>
              <div class="tp-stat-lbl">Followups Sent</div>
            </div>
            <div class="tp-churn-stat">
              <div class="tp-stat-val teal">${data.win_back_stats.reactivations}</div>
              <div class="tp-stat-lbl">Reactivated</div>
            </div>
            <div class="tp-churn-stat">
              <div class="tp-stat-val teal">${(data.win_back_stats.reactivation_rate * 100).toFixed(1)}%</div>
              <div class="tp-stat-lbl">Reactivation Rate</div>
            
            <div class="tp-churn-stat">
              <div class="tp-stat-val dim">${data.win_back_stats.opted_out || 0}</div>
              <div class="tp-stat-lbl">Opted Out</div>
            </div></div>
          </div>
        </div>
            ` : ''}
      ${data.win_back_stats && data.win_back_stats.variants && data.win_back_stats.variants.length > 0 ? html`
        <div class="panel" style="margin-bottom:20px">
          <div class="panel-head">A/B Test Results</div>
          <div style="overflow-x:auto">
            <table class="tbl" style="margin-top:4px">
              <thead>
                <tr>
                  <th>Variant</th>
                  <th>Tone</th>
                  <th>Split</th>
                  <th>Sent</th>
                  <th>Followups</th>
                  <th>Reactivated</th>
                  <th>Rate</th>
                </tr>
              </thead>
              <tbody>
                ${data.win_back_stats.variants.map(v => html`
                  <tr>
                    <td><strong>${v.name}</strong></td>
                    <td class="tbl-mono">${v.tone}</td>
                    <td class="tbl-num">${v.weight}%</td>
                    <td class="tbl-num">${v.sent}</td>
                    <td class="tbl-num">${v.followups_sent}</td>
                    <td class="tbl-num">${v.reactivations}</td>
                    <td class="tbl-num" style="color:var(--signal-teal);font-weight:600">${(v.reactivation_rate * 100).toFixed(1)}%</td>
                  </tr>
                `)}
                <tr style="border-top:2px solid var(--empire-divider);font-weight:600">
                  <td><em style="color:var(--empire-fog)">Total</em></td>
                  <td></td>
                  <td></td>
                  <td class="tbl-num" style="color:var(--empire-white)">${data.win_back_stats.variants.reduce((s,v) => s + v.sent, 0)}</td>
                  <td class="tbl-num" style="color:var(--empire-white)">${data.win_back_stats.variants.reduce((s,v) => s + v.followups_sent, 0)}</td>
                  <td class="tbl-num" style="color:var(--empire-white)">${data.win_back_stats.variants.reduce((s,v) => s + v.reactivations, 0)}</td>
                  <td class="tbl-num" style="color:var(--signal-teal)">${(data.win_back_stats.reactivation_rate * 100).toFixed(1)}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ` : ''}

      ${data.sla_stats ? html`
        <div class="panel" style="margin-bottom:20px">
          <div class="panel-head">SLA Compliance</div>
          <div class="tp-churn-strip">
            <div class="tp-churn-stat">
              <div class="tp-stat-val ${data.sla_stats.breached > 0 ? 'red' : 'teal'}">${data.sla_stats.breached}</div>
              <div class="tp-stat-lbl">SLA Breaches</div>
            </div>
            <div class="tp-churn-stat">
              <div class="tp-stat-val dim">${data.sla_stats.total_past_sla}</div>
              <div class="tp-stat-lbl">Past Grace Window</div>
            </div>
            <div class="tp-churn-stat">
              <div class="tp-stat-val teal">${data.sla_stats.completed_on_time}</div>
              <div class="tp-stat-lbl">On Time</div>
            </div>
            <div class="tp-churn-stat">
              <div class="tp-stat-val teal">${(data.sla_stats.sla_rate * 100).toFixed(1)}%</div>
              <div class="tp-stat-lbl">SLA Rate</div>
            </div>
          </div>
        </div>
      ` : ''}
<div class="split">
        <div class="panel">
          <div class="panel-head">SEO Genome (Gen ${data.evolution_runs || 0})</div>
          ${Object.entries(genome).length === 0 ? html`<div class="kb-empty">No genome data yet.</div>` :
            Object.entries(genome).map(([trait, val]) => {
              const pct = Math.round((val || 0) * 100);
              const color = traitColors[trait] || '#64748B';
              const label = traitLabels[trait] || trait;
              return html`
            <div class="si-trait" key=${trait}>
              <div class="si-trait-head">
                <span class="si-trait-name">${label}</span>
                <span class="si-trait-pct" style=${{color}}>${pct}%</span>
              </div>
              <div class="si-trait-track">
                <div class="si-trait-fill" style=${{width: pct + '%', background: color}}></div>
              </div>
            </div>
            `;
            })}
          ${data.last_evolution ? html`
          <div class="si-evo-footer" style=${{marginTop: '12px', paddingTop: '10px'}}>
            <span>Last evolution: ${data.last_evolution.slice(0,19).replace('T',' ')}</span>
          </div>` : ''}
        </div>

        <div class="panel">
          <div class="panel-head">Top Converting Keywords</div>
          ${topKeywords.length === 0 ? html`<div class="kb-empty">No conversion data yet.</div>` :
            html`<div style=${{maxHeight:'280px',overflowY:'auto'}}>
            ${topKeywords.map(k => html`
            <div class="seo-kw-row" key=${k.keyword}>
              <div class="seo-kw-name">${k.keyword}</div>
              <div class="seo-kw-meta">
                <span class="seo-kw-stat">${(k.conversion_rate || 0).toFixed(1)}%</span>
                <span class="seo-kw-stat dim">${k.conversions || 0} conv</span>
                <span class="seo-kw-stat dim">$${(k.total_revenue || 0).toFixed(0)}</span>
                <span class=${'seo-kw-comp ' + (k.competition || 'low')}>${k.competition || '?'}</span>
              </div>
            </div>
            `)}
          </div>`}
        </div>
      </div>

      ${content.length > 0 ? html`
      <div class="chart-panel">
        <div class="chart-panel-h">
          <span class="chart-panel-title">Recent Content</span>
          <span class="chart-panel-tag">${content.length} pieces</span>
        </div>
        ${content.slice(0, 8).map(c => html`
        <div class="seo-content-card" key=${c.id || c.keyword}>
          <div class="seo-content-head">
            <span class="seo-content-kw">${c.keyword || '—'}</span>
            <span class="seo-content-niche">${c.niche || ''} · ${c.metro || ''}</span>
          </div>
          <div class="seo-content-title">${c.title_tag || c.h1 || '—'}</div>
          <div class="seo-content-meta">${c.meta_description || ''}</div>
          ${c.attributed_lead_id ? html`<div class="seo-content-attrib">✓ Attributed to lead ${(c.attributed_lead_id || '').slice(0,8)} ${c.converted ? '· Converted' : ''}</div>` : ''}
        </div>
        `)}
      </div>
      ` : ''}

      ${audits.length > 0 ? html`
      <div class="chart-panel" style=${{marginTop: '16px'}}>
        <div class="chart-panel-h">
          <span class="chart-panel-title">Recent Audits</span>
          <span class="chart-panel-tag">${audits.length} sites</span>
        </div>
        ${audits.slice(0, 5).map(a => html`
        <div class="seo-audit-row" key=${a.id}>
          <div class="seo-audit-url">${(a.url || '').slice(0, 50)}</div>
          <div class="seo-audit-scores">
            <span class="seo-audit-score ${a.overall_score >= 70 ? 'ok' : a.overall_score >= 40 ? 'warn' : 'bad'}">${a.overall_score || 0}</span>
            <span class="seo-audit-score dim">M:${a.meta_score || 0}</span>
            <span class="seo-audit-score dim">C:${a.content_score || 0}</span>
            <span class="seo-audit-score dim">T:${a.technical_score || 0}</span>
          </div>
        </div>
        `)}
      </div>
      ` : ''}
    </div>
  `;
}

// ── AFFILIATES MANAGEMENT ───────────────────────────────────────────
function Affiliates() {
  const [affiliates, setAffiliates] = useState(null);
  const [err, setErr] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [linkLabel, setLinkLabel] = useState({});
  const [busy, setBusy] = useState({});
  const [saving, setSaving] = useState({});
  const [affLinks, setAffLinks] = useState({});
  const [funnelData, setFunnelData] = useState(null);
  const [funnelErr, setFunnelErr] = useState(null);
  const [topLinks, setTopLinks] = useState(null);
  const [topLinksErr, setTopLinksErr] = useState(null);

  const fetchTopLinks = useCallback(async () => {
    try {
      const r = await apiFetch('/api/v1/affiliates/top-links').then(x => x.json());
      setTopLinks(r);
      setTopLinksErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setTopLinksErr(e.message);
    }
  }, []);

  const fetchFunnel = useCallback(async () => {
    try {
      const r = await apiFetch('/api/v1/affiliates/funnel').then(x => x.json());
      setFunnelData(r);
      setFunnelErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setFunnelErr(e.message);
    }
  }, []);

  const fetchAffLinks = useCallback(async (id) => {
    try {
      const r = await apiFetch('/api/v1/affiliate/' + id + '/links').then(x => x.json());
      setAffLinks(l => ({ ...l, [id]: r.links || [] }));
    } catch (e) {}
  }, []);

  const toggleExpanded = (id) => {
    const next = expandedId === id ? null : id;
    setExpandedId(next);
    if (next && !affLinks[next]) {
      fetchAffLinks(next);
    }
  };

  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/v1/affiliates/list').then(x => x.json());
      setAffiliates(r.affiliates || []);
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);
  useEffect(() => { reload(); fetchFunnel(); }, [reload, fetchFunnel]);

  const toggleActive = async (id, current) => {
    setSaving(s => ({ ...s, [id]: true }));
    try {
      await apiFetch('/api/v1/affiliates/' + id + '/toggle-active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !current }),
      });
      await reload();
    } catch (e) {
      alert('Failed: ' + e.message);
    }
    setSaving(s => ({ ...s, [id]: false }));
  };

  const createLink = async (id) => {
    const label = linkLabel[id] || '';
    if (!label.trim()) return;
    setBusy(b => ({ ...b, [id]: true }));
    try {
      await apiFetch('/api/v1/affiliates/' + id + '/create-link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: label.trim() }),
      });
      setLinkLabel(l => ({ ...l, [id]: '' }));
      await reload();
    } catch (e) {
      alert('Failed: ' + e.message);
    }
    setBusy(b => ({ ...b, [id]: false }));
  };

  if (err) return html`<div class="stub"><div class="stub-body">${err}</div></div>`;
  if (!affiliates) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const active = affiliates.filter(a => a.is_active);
  const totalRevenue = affiliates.reduce((s, a) => s + (a.total_revenue || 0), 0);
  const totalCommission = affiliates.reduce((s, a) => s + (a.commission_earned || 0), 0);
  const totalCalls = affiliates.reduce((s, a) => s + (a.total_calls || 0), 0);

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Affiliates</div>
          <div class="section-sub">Manage partners · referral links · performance</div>
        </div>
        <button class="btn ghost" onClick=${() => { reload(); fetchFunnel(); fetchTopLinks(); }}>Refresh</button>
      </div>

      ${/* Funnel analytics section */ ''}
      ${funnelData ? html`
        <div class="pipeline-breakdown" style=${{marginBottom: '20px'}}>
          <div class="pipeline-h">
            <div class="pipeline-title">Conversion <strong>Funnel</strong></div>
            <div class="pipeline-total">${funnelData.affiliate_count || 0} affiliates</div>
          </div>
          <div style=${{display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '12px', marginBottom: '16px'}}>
            <div class="stat-card" style=${{padding: '14px 16px'}}>
              <div class="stat-label" style=${{fontSize: '9px'}}>CLICKS</div>
              <div class="stat-value" style=${{fontSize: '22px'}}>${funnelData.totals.clicks.toLocaleString()}</div>
              <div class="stat-meta">100%</div>
            </div>
            <div class="stat-card" style=${{padding: '14px 16px'}}>
              <div class="stat-label" style=${{fontSize: '9px'}}>LEADS</div>
              <div class="stat-value cyan" style=${{fontSize: '22px'}}>${funnelData.totals.leads.toLocaleString()}</div>
              <div class="stat-meta">${funnelData.totals.click_to_lead || 0}% of clicks</div>
            </div>
            <div class="stat-card" style=${{padding: '14px 16px'}}>
              <div class="stat-label" style=${{fontSize: '9px'}}>CALLS</div>
              <div class="stat-value" style=${{fontSize: '22px'}}>${funnelData.totals.calls.toLocaleString()}</div>
              <div class="stat-meta">${funnelData.totals.lead_to_call || 0}% of leads</div>
            </div>
            <div class="stat-card" style=${{padding: '14px 16px'}}>
              <div class="stat-label" style=${{fontSize: '9px'}}>QUALIFIED</div>
              <div style=${{fontSize: '22px', color: 'var(--status-amber)', fontFamily: 'var(--font-mono)', fontWeight: 500}} style=${{fontSize: '22px'}}>${funnelData.totals.qualified.toLocaleString()}</div>
              <div class="stat-meta">${funnelData.totals.call_to_qualified || 0}% of calls</div>
            </div>
            <div class="stat-card" style=${{padding: '14px 16px'}}>
              <div class="stat-label" style=${{fontSize: '9px'}}>REVENUE</div>
              <div class="stat-value teal" style=${{fontSize: '22px'}}>$${funnelData.totals.revenue.toLocaleString()}</div>
              <div class="stat-meta">${funnelData.totals.overall_ctr || 0}% overall CTR</div>
            </div>
          </div>
          ${/* Funnel bar chart per affiliate */ ''}
          <div class="section-sub" style=${{marginBottom: '8px', fontSize: '9px'}}>Per-affiliate funnel</div>
          ${funnelData.funnel.slice(0, 20).map(a => {
            const fs = a.funnel;
            const maxVal = Math.max(fs.clicks, 1);
            return html`
            <div style=${{marginBottom: '12px'}}>
              <div style=${{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px'}}>
                <span style=${{fontSize: '11px', color: 'var(--empire-white)', fontWeight: 500}}>${a.buyer_name}</span>
                <span style=${{fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--empire-fog)'}}>
                  ${a.niche || '—'} · ${a.link_count} links · ${a.rates.overall_ctr}% CTR
                </span>
              </div>
              <div style=${{display: 'flex', gap: '4px', height: '18px', alignItems: 'center'}}>
                <div style=${{flex: '1', height: '100%', display: 'flex', borderRadius: '3px', overflow: 'hidden', background: 'var(--empire-elevated)'}}>
                  <div style=${{width: Math.max(2, (fs.clicks / maxVal) * 60) + '%', height: '100%', background: 'var(--empire-surface)', borderRight: '1px solid var(--empire-divider)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px', color: 'var(--empire-mist)', fontFamily: 'var(--font-mono)', minWidth: '20px'}}>${fs.clicks}</div>
                  <div style=${{width: Math.max(2, (fs.leads / maxVal) * 50) + '%', height: '100%', background: 'rgba(90,200,250,0.2)', borderRight: '1px solid var(--empire-divider)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px', color: 'var(--strike-cyan)', fontFamily: 'var(--font-mono)', minWidth: '20px'}}>${fs.leads}</div>
                  <div style=${{width: Math.max(2, (fs.calls / maxVal) * 40) + '%', height: '100%', background: 'rgba(255,184,0,0.2)', borderRight: '1px solid var(--empire-divider)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px', color: 'var(--status-amber)', fontFamily: 'var(--font-mono)', minWidth: '20px'}}>${fs.calls}</div>
                  <div style=${{width: Math.max(2, (fs.qualified / maxVal) * 30) + '%', height: '100%', background: 'rgba(68,229,184,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px', color: 'var(--signal-teal)', fontFamily: 'var(--font-mono)', minWidth: '20px'}}>${fs.qualified}</div>
                </div>
                <span style=${{fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--signal-teal)', fontWeight: 500, minWidth: '65px', textAlign: 'right'}}>$${fs.revenue.toLocaleString()}</span>
              </div>
            </div>
          `})}
          ${funnelData.funnel.length > 20 ? html`<div class="stub" style=${{padding: '12px', marginTop: '8px', fontSize: '9px'}}><div class="stub-body">Showing top 20 of ${funnelData.funnel.length} affiliates</div></div>` : ''}
        </div>
      ` : funnelErr ? html`
        <div class="stub" style=${{marginBottom: '20px'}}><div class="stub-body">Funnel data unavailable: ${funnelErr}</div></div>
      ` : null}

      ${/* Top Performing Links widget */ ''}
      ${topLinks ? html`
        <div class="pipeline-breakdown" style=${{marginBottom: '20px'}}>
          <div class="pipeline-h">
            <div class="pipeline-title">Top <strong>Performing Links</strong></div>
            <div class="pipeline-total">
              ${topLinks.links_with_clicks || 0} with clicks · 
              ${topLinks.links_with_leads || 0} with leads · 
              ${topLinks.total || 0} total links
            </div>
          </div>
          ${topLinks.links && topLinks.links.length > 0 ? html`
            <div style=${{marginTop: '12px'}}>
              ${topLinks.links.slice(0, 10).map(l => {
                const barPct = Math.min(100, Math.round(l.click_to_lead * 2.5));
                const barColor = l.click_to_lead >= 20 ? 'var(--signal-teal)' : l.click_to_lead >= 5 ? 'var(--status-amber)' : 'var(--empire-fog)';
                return html`
                  <div style=${{marginBottom: '10px'}}>
                    <div style=${{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px'}}>
                      <div style=${{display: 'flex', alignItems: 'center', gap: '8px'}}>
                        <span style=${{fontSize: '10px', color: 'var(--empire-white)', fontWeight: 500, maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>${l.label}</span>
                        <span style=${{fontFamily: 'var(--font-mono)', fontSize: '8px', color: 'var(--empire-fog)'}}>${l.code}</span>
                        <span style=${{fontSize: '9px', color: 'var(--empire-mist)'}}>${l.buyer_name}</span>
                      </div>
                      <div style=${{display: 'flex', gap: '12px', fontFamily: 'var(--font-mono)', fontSize: '9px', alignItems: 'center'}}>
                        <span style=${{color: 'var(--empire-white)'}}>${l.click_count} <span style=${{color: 'var(--empire-fog)'}}>clicks</span></span>
                        <span style=${{color: l.lead_count > 0 ? 'var(--strike-cyan)' : 'var(--empire-fog)'}}>${l.lead_count} <span style=${{color: 'var(--empire-fog)'}}>leads</span></span>
                        <span style=${{color: barColor, fontWeight: 700}}>${l.click_to_lead}%</span>
                      </div>
                    </div>
                    <div style=${{height: '4px', background: 'var(--empire-elevated)', borderRadius: '2px', overflow: 'hidden'}}>
                      <div style=${{width: barPct + '%', height: '100%', background: barColor, borderRadius: '2px', transition: 'width 0.3s ease'}}></div>
                    </div>
                    <div style=${{display: 'flex', gap: '16px', fontFamily: 'var(--font-mono)', fontSize: '8px', color: 'var(--empire-fog)', marginTop: '2px'}}>
                      <span>${l.lead_to_call}% lead→call</span>
                      <span>${l.qualified_count} qualified</span>
                      ${l.revenue > 0 ? html`<span style=${{color: 'var(--signal-teal)'}}>\$${l.revenue.toLocaleString()}</span>` : ''}
                    </div>
                  </div>
                `;
              })}
            </div>
            ${topLinks.links.length > 10 ? html`<div class="stub" style=${{padding: '12px', marginTop: '4px', fontSize: '9px'}}><div class="stub-body">Showing top 10 of ${topLinks.links.length} links with clicks</div></div>` : ''}
          ` : html`
            <div class="stub" style=${{marginTop: '16px', padding: '24px 20px'}}>
              <div class="stub-title">No link activity yet</div>
              <div class="stub-body">Share affiliate landing URLs or embed tracking pixels to start collecting click data</div>
            </div>
          `}
        </div>
      ` : topLinksErr ? html`
        <div class="stub" style=${{marginBottom: '20px'}}><div class="stub-body">Top links unavailable: ${topLinksErr}</div></div>
      ` : null}

      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">Total Affiliates</div>
          <div class="stat-value teal">${affiliates.length}</div>
          <div class="stat-meta">${active.length} active</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Revenue</div>
          <div class="stat-value teal">$${totalRevenue.toLocaleString()}</div>
          <div class="stat-meta">attributed to affiliates</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Commission</div>
          <div class="stat-value cyan">$${totalCommission.toLocaleString()}</div>
          <div class="stat-meta">earned by affiliates</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Calls</div>
          <div class="stat-value">${totalCalls.toLocaleString()}</div>
          <div class="stat-meta">across all affiliates</div>
        </div>
      </div>

      <table class="tbl">
        <thead><tr>
          <th>Name</th>
          <th>Email</th>
          <th>Niche</th>
          <th>Fee Rate</th>
          <th>Links</th>
          <th>Revenue</th>
          <th>Commission</th>
          <th>Status</th>
          <th></th>
        </tr></thead>
        <tbody>
          ${affiliates.map(a => html`
            <tr key=${a.id} style=${{cursor: 'pointer'}} onClick=${() => toggleExpanded(a.id)}>
              <td><strong>${a.buyer_name}</strong></td>
              <td class="tbl-mono">${a.email}</td>
              <td>${a.niche || '—'}</td>
              <td class="tbl-num">${(a.fee_rate * 100).toFixed(1)}%</td>
              <td class="tbl-num">${a.active_links || 0}/${a.link_count || 0}</td>
              <td class="tbl-num teal">$${(a.total_revenue || 0).toLocaleString()}</td>
              <td class="tbl-num cyan">$${(a.commission_earned || 0).toLocaleString()}</td>
              <td>
                <span class="bdg ${a.is_active ? 'active' : 'paused'}">
                  ${a.is_active ? 'Active' : (a.status || 'Inactive')}
                </span>
              </td>
              <td>
                <button class="tbl-action ${a.is_active ? 'danger' : 'go'}"
                        disabled=${saving[a.id]}
                        onClick=${(e) => { e.stopPropagation(); toggleActive(a.id, a.is_active); }}>
                  ${saving[a.id] ? '…' : (a.is_active ? 'Deactivate' : 'Activate')}
                </button>
              </td>
            </tr>
            ${expandedId === a.id ? html`
            <tr key=${a.id + '-detail'}>
              <td colspan="9" style=${{padding: '0', borderBottom: '1px solid var(--empire-divider)'}}>
                <div style=${{padding: '16px 24px', background: 'var(--empire-elevated)'}}>
                  <div style=${{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '14px'}}>
                    <div class="stat-card" style=${{padding: '14px 16px'}}>
                      <div class="stat-label">Leads</div>
                      <div class="stat-value" style=${{fontSize: '22px'}}>${a.total_leads || 0}</div>
                    </div>
                    <div class="stat-card" style=${{padding: '14px 16px'}}>
                      <div class="stat-label">Qualified Calls</div>
                      <div class="stat-value cyan" style=${{fontSize: '22px'}}>${a.qualified_calls || 0}</div>
                    </div>
                  </div>
                  <div style=${{display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '16px'}}>
                    <input class="fld-in mono" style=${{flex: 1}}
                           value=${linkLabel[a.id] || ''}
                           onChange=${e => setLinkLabel(l => ({ ...l, [a.id]: e.target.value }))}
                           placeholder="New referral link label…" />
                    <button class="btn"
                            disabled=${busy[a.id] || !(linkLabel[a.id] || '').trim()}
                            onClick=${() => createLink(a.id)}>
                      ${busy[a.id] ? 'Creating…' : 'Create Link'}
                    </button>
                  </div>

                  ${/* Show existing links with pixel + landing URLs */ ''}
                  ${(affLinks[a.id] && affLinks[a.id].length > 0) ? html`
                    <div class="section-sub" style=${{marginBottom: '10px', fontSize: '9px'}}>Referral Links</div>
                    ${affLinks[a.id].map(l => html`
                      <div style=${{background: 'var(--empire-surface)', border: '1px solid var(--empire-divider)', padding: '12px 14px', marginBottom: '8px'}}>
                        <div style=${{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px'}}>
                          <div>
                            <span class="bdg ${l.active ? 'active' : 'paused'}" style=${{fontSize: '8px'}}>${l.code}</span>
                            <span style=${{marginLeft: '8px', fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--empire-silver)'}}>${l.label || ''}</span>
                          </div>
                          <div style=${{fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--empire-mist)'}}>
                            ${l.click_count || 0} clicks · ${l.conversion_count || 0} conversions
                          </div>
                        </div>
                        <div style=${{fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--empire-fog)', lineHeight: '1.8'}}>
                          <div><span style=${{color: 'var(--signal-teal)'}}>Landing:</span> <a href=${l.landing_url || l.url} target="_blank" style=${{color: 'var(--strike-cyan)'}}>${l.landing_url || l.url}</a></div>
                          <div><span style=${{color: 'var(--signal-teal)'}}>Pixel:</span> <code style=${{color: 'var(--empire-mist)', background: 'var(--empire-elevated)', padding: '2px 6px'}}>${l.pixel_url || (l.url ? l.url.replace('/verify?ref=', '/track/aff/') + '/pixel.gif' : '')}</code></div>
                          <div style=${{marginTop: '4px'}}>
                            <span style=${{color: 'var(--empire-mist)'}}>Embed:</span>
                            <code style=${{color: 'var(--empire-fog)', background: 'var(--empire-elevated)', padding: '2px 6px', fontSize: '8px', wordBreak: 'break-all'}}>
                              &lt;img src="${l.pixel_url || (l.url ? l.url.replace('/verify?ref=', '/track/aff/') + '/pixel.gif' : '')}" width="1" height="1" /&gt;
                            </code>
                          </div>
                        </div>
                      </div>
                    `)}
                  ` : html`<div class="section-sub" style=${{marginBottom: '10px', color: 'var(--empire-fog)', fontStyle: 'italic', fontSize: '9px'}}>No referral links yet. Create one above.</div>`}
                </div>
              </td>
            </tr>` : ''}
          `.join('')}
          ${affiliates.length === 0 ? html`<tr><td class="tbl-empty" colspan="9">No affiliates found. Add buyers to get started.</td></tr>` : ''}
        </tbody>
      </table>
    </div>
  `;
}



// -- CPL PRICING + ROI CALCULATOR --------------------------------------------
const CplPricing = () => {
  const [lanes, setLanes] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState(null);
  const [modelFilter, setModelFilter] = useState('all');
  const [serviceOnly, setServiceOnly] = useState(false);
  const [laneSearch, setLaneSearch] = useState('');
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState('lanes');
  const perPage = 12;
  // ROI calculator state
  const [roiNiche, setRoiNiche] = useState('Roofing Restoration');
  const [roiVolume, setRoiVolume] = useState(100);
  const [roiSellPrice, setRoiSellPrice] = useState('');
  const [roiResult, setRoiResult] = useState(null);
  const [roiLoading, setRoiLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [cmpNicheFilter, setCmpNicheFilter] = useState(null);
  const [nicheSearch, setNicheSearch] = useState('');

  // Initial data fetch
  const prepareLaneData = (lanes) => lanes.map(l => {
    if (!l.cpl_available) {
      const ppc_ready = l.ppc_ready === true;
  return { ...l, ppc_ready, cpl_low: null, cpl_high: null, cpl_ppc_low: null, cpl_ppc_high: null,
        sell_price_low: null, sell_price_high: null, margin_pct: null, annual_revenue: null,
        roi_pct: null, monthly_revenue: null, monthly_acq_cost: null, breakeven: null };
    }
    const cpl = l.cpl || {};
    const ppl = cpl.ppl || {}; const ppc = cpl.ppc || {};
    const roi = l.roi || {};
    const suggested = l.suggested_pricing || {};
    const sellPrice = roi.sell_price_per_lead || suggested.suggested_sell_price || null;
    const monthRev = roi.monthly_revenue ? Math.round(roi.monthly_revenue) : null;
    const monthAcq = roi.monthly_acquisition_cost ? Math.round(roi.monthly_acquisition_cost) : null;
    const annualRev = roi.monthly_revenue ? Math.round(roi.monthly_revenue * 12) : null;
    const marginPct = suggested.actual_margin_pct != null ? suggested.actual_margin_pct :
      (roi.gross_margin != null && monthRev ? Math.round((roi.gross_margin / monthRev) * 100 * 10) / 10 : null);
    return { ...l,
      cpl_low: ppl.low, cpl_high: ppl.high,
      cpl_ppc_low: ppc.low, cpl_ppc_high: ppc.high,
      sell_price_low: sellPrice, sell_price_high: sellPrice ? Math.round(sellPrice * 1.3) : null,
      annual_revenue: annualRev, roi_pct: roi.roi_percentage,
      monthly_revenue: monthRev, monthly_acq_cost: monthAcq,
      breakeven: roi.breakeven_volume, margin_pct: marginPct
    };
  });

  const modelToParam = (mf) => mf === 'all' || mf === 'service' ? 'both' : mf;

  const fetchLanes = (model) => {
    const m = model || modelToParam(modelFilter);
    setReloading(true);
    apiFetch('/api/v1/cpl/lanes?model=' + m + '&monthly_volume=100')
      .then(data => { setLanes(prepareLaneData(data.lanes || data)); setLoading(false); setReloading(false); setLastRefreshed(new Date()); })
      .catch(e => { setError(e.message || 'Failed to load CPL data'); setLoading(false); setReloading(false); });
  };

  useEffect(() => {
    fetchLanes(modelToParam(modelFilter));
    setPage(1);
  }, [modelFilter]);


  // Auto-refresh: poll every 30 seconds when toggled on
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      setReloading(true);
      apiFetch('/api/v1/cpl/lanes?model=' + modelToParam(modelFilter) + '&monthly_volume=100')
        .then(data => { setLanes(prepareLaneData(data.lanes || data)); setReloading(false); setLastRefreshed(new Date()); })
        .catch(e => { setReloading(false); /* silent refresh failure */ });
    }, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh, modelFilter]);
    setReloading(true);
    apiFetch('/api/v1/cpl/lanes?model=both&monthly_volume=100')
      .then(data => { setLanes(prepareLaneData(data.lanes || data)); setLoading(false); setReloading(false); setLastRefreshed(new Date()); })
      .catch(e => { setError(e.message || 'Failed to load CPL data'); setLoading(false); setReloading(false); });
  }, []);

  if (loading) return html`<div class="cpl-loading">Loading CPL pricing...</div>`;
  const reloadingIndicator = reloading ? html`<div class="cpl-reloading-bar"><div class="cpl-reloading-bar-inner"></div></div>` : html``;
  if (error) return html`<div class="cpl-error">${error}</div>`;
  if (!lanes) return html`<div class="cpl-loading">No data</div>`;

  const filtered = lanes.filter(l => {
    const matchesModel = serviceOnly ? !l.cpl_available : modelFilter === 'all' ? true : modelFilter === 'service' ? !l.cpl_available : l.best_model === modelFilter;
    const matchesSearch = !laneSearch || l.niche.toLowerCase().includes(laneSearch.toLowerCase());
    return matchesModel && matchesSearch;
  });
  const totalPages = Math.ceil(filtered.length / perPage);
  const pg = Math.min(page, Math.max(1, totalPages));
  const pageLanes = filtered.slice((pg - 1) * perPage, pg * perPage);

  const summary = (() => {
    const priced = lanes.filter(l => l.cpl_available);
    if (!priced.length) return { total: lanes.length, priced: 0, avgLow: 0, avgHigh: 0, avgMargin: 0 };
    return {
      total: lanes.length,
      priced: priced.length,
      avgLow: Math.round(priced.reduce((s, l) => s + l.cpl_low, 0) / priced.length),
      avgHigh: Math.round(priced.reduce((s, l) => s + l.cpl_high, 0) / priced.length),
      avgMargin: Math.round(priced.reduce((s, l) => s + (l.margin_pct || 0), 0) / priced.length * 10) / 10,
      totalMRR: priced.reduce((s, l) => s + (l.monthly_revenue || 0), 0),
      avgROI: Math.round(priced.reduce((s, l) => s + (l.roi_pct || 0), 0) / priced.length * 10) / 10,
      totalAcqCost: priced.reduce((s, l) => s + (l.monthly_acq_cost || 0), 0),
      healthGreen: priced.filter(l => l.roi_pct != null && l.roi_pct > 0 && (l.margin_pct != null && l.margin_pct > 50) && (l.breakeven != null && l.breakeven <= 200)).length,
      healthAmber: priced.filter(l => l.roi_pct != null && l.roi_pct > 0 && !((l.margin_pct != null && l.margin_pct > 50) && (l.breakeven != null && l.breakeven <= 200))).length,
      healthRed: priced.filter(l => l.roi_pct != null && l.roi_pct <= 0).length,
      healthNone: priced.filter(l => l.roi_pct == null).length,
      ppcReady: lanes.filter(l => l.ppc_ready === true).length,
    };
  })();

  const marginClass = (pct) => pct >= 50 ? 'high' : pct >= 25 ? 'mid' : 'low';
  const modelClass = (m) => m === 'ppl' ? 'ppl' : m === 'ppc' ? 'ppc' : 'service';

  const runRoi = () => {
    setRoiLoading(true);
    setRoiResult(null);
    const sp = roiSellPrice ? parseFloat(roiSellPrice) : null;
    const params = new URLSearchParams({ niche: roiNiche, monthly_volume: String(roiVolume) });
    if (sp) params.set('sell_price', String(sp));
    apiFetch('/api/v1/cpl/roi/' + encodeURIComponent(roiNiche) + '?' + params.toString())
      .then(data => { setRoiResult(data); setRoiLoading(false); })
      .catch(e => { setError(e.message); setRoiLoading(false); });
  };

  const roiClass = (v) => v > 0 ? 'profit' : v < 0 ? 'loss' : 'neutral';

  // -- CSV export ---------------------------------------------------------
    // Compute health label for a lane (matches Health indicator logic)
  const healthLabel = (l) => {
    if (!l.cpl_available || l.roi_pct == null) return 'N/A';
    if (l.roi_pct > 0 && (l.margin_pct != null && l.margin_pct > 50) && (l.breakeven != null && l.breakeven <= 200)) return 'Healthy';
    if (l.roi_pct > 0) return 'At Risk';
    return 'Unprofitable';
  };

    const exportCSV = () => {
    // Formula reference for predictive revenue columns:
    //   ROI %  = ((Monthly Revenue - Monthly Acq Cost) / Monthly Acq Cost) x 100
    //   Mo. Rev = projected monthly revenue at estimated conversion rate & sell price
    //   Acq Cost = CPL x monthly volume (what it costs to acquire leads per month)
    //   BE Vol   = Breakeven volume = Monthly Acq Cost / (Sell Price - CPL)
    //   Health  = Green (ROI>0% & margin>50% & BE<=200) | Amber (ROI>0%, thin) | Red (ROI<=0%)
    //
    const rows = [
      ['# Formula Reference:'],
      ['# ROI %  = ((Monthly Revenue - Monthly Acq Cost) / Monthly Acq Cost) * 100'],
      ['# Mo. Rev = Monthly revenue at estimated conversion rate & sell price'],
      ['# Acq Cost = CPL * monthly volume — cost to acquire leads per month'],
      ['# BE Vol   = Breakeven volume = Acq Cost / (Sell Price - CPL)'],
      ['# Health  = Green (ROI > 0% & margin > 50% & BE <= 200) | Amber (ROI > 0%, thin margins or high BE) | Red (ROI <= 0%)'],
      ['','','','','','','','','','','','','','','',''],
      ['Lane','Niche','Sub-Niche','CPL Low','CPL High','Model','Sell Price Low','Sell Price High','Margin %','Annual Revenue','ROI %','Mo. Rev','Acq Cost','BE Vol','Health','CPL Available','PPC Ready']];
    lanes.forEach(l => {
      rows.push([
        'L'+String(l.lane_id).padStart(2,'0'),
        l.niche,
        l.sub_niche,
        l.cpl_available ? (modelFilter === 'ppc' && l.cpl_ppc_low != null ? String(l.cpl_ppc_low) : String(l.cpl_low)) : 'N/A',
        l.cpl_available ? (modelFilter === 'ppc' && l.cpl_ppc_high != null ? String(l.cpl_ppc_high) : String(l.cpl_high)) : 'N/A',
        l.best_model || 'n/a',
        l.cpl_available ? String(l.sell_price_low) : 'N/A',
        l.cpl_available ? String(l.sell_price_high) : 'N/A',
        l.cpl_available ? String(l.margin_pct) : 'N/A',
        l.cpl_available ? String(l.annual_revenue || 0) : 'N/A',
        l.cpl_available ? (l.roi_pct != null ? l.roi_pct + '%' : 'N/A') : 'N/A',
        l.cpl_available ? String(l.monthly_revenue || 0) : 'N/A',
        l.cpl_available ? String(l.monthly_acq_cost || 0) : 'N/A',
        l.cpl_available ? (l.breakeven != null ? String(l.breakeven) : 'N/A') : 'N/A',
        l.cpl_available ? healthLabel(l) : 'N/A',
        l.cpl_available ? 'Yes' : 'No',
        l.ppc_ready ? 'Yes' : 'No'
      ]);
    });
    // Aggregate summary row
    const pricedLanes = lanes.filter(l => l.cpl_available);
    const n = pricedLanes.length;
    const totalMRR = pricedLanes.reduce(function(s, l) { return s + (l.monthly_revenue || 0); }, 0);
    const avgAcq = n > 0 ? Math.round(pricedLanes.reduce(function(s, l) { return s + (l.monthly_acq_cost || 0); }, 0) / n) : 0;
    var g = 0, a = 0, r = 0;
    pricedLanes.forEach(function(l) {
      if (l.roi_pct == null) return;
      if (l.roi_pct > 0 && l.margin_pct > 50 && l.breakeven <= 200) g++;
      else if (l.roi_pct > 0) a++;
      else r++;
    });
    rows.push(['','','','','','','','','','','','','','','','','']);
    rows.push(['TOTALS','','','','','','','','','','','$'+totalMRR,'$'+avgAcq,'','G:'+g+' A:'+a+' R:'+r,'','']);

    const csv = rows.map(r => r.map(c => '"' + String(c).replace(/"/g,'""') + '"').join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'empire_cpl_pricing_' + new Date().toISOString().split('T')[0] + '.csv';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  };

  // -- PDF / Print --------------------------------------------------------
  const exportPDF = () => { window.print(); };

  return html`
    <div class="section-h">
      <div class="cpl-header">
        <h2 style="margin:0;font-size:16px;font-weight:600">CPL Pricing</h2>
        <div class="cpl-export-bar">
          <button class="cpl-export-btn" onClick=${exportCSV} title="Download CSV">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            CSV
          </button>
          <button class="cpl-export-btn" onClick=${exportPDF} title="Print / Save as PDF">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            PDF
          </button>
          <button class="cpl-refresh-btn ${autoRefresh ? 'active' : ''}" onClick=${() => setAutoRefresh(!autoRefresh)} title="Toggle auto-refresh (30s)">
            <span class="cpl-refresh-dot"></span>
            <span class="cpl-refresh-label">${autoRefresh ? 'LIVE' : 'AUTO'}</span>
          </button>
        </div>
        <div class="cpl-tabs">
          <button class="cpl-tab ${tab === 'lanes' ? 'active' : ''}" onClick=${() => setTab('lanes')}>Lane Pricing</button>
          <button class="cpl-tab ${tab === 'roi' ? 'active' : ''}" onClick=${() => setTab('roi')}>ROI Calculator</button>
          <button class="cpl-tab ${tab === 'compare' ? 'active' : ''}" onClick=${() => setTab('compare')}>PPL vs PPC</button>
        </div>
      </div>

      ${tab === 'lanes' ? html`
        <div class="cpl-summary">
          <div class="cpl-card"><div class="cpl-card-label">Total Lanes</div><div class="cpl-card-value">${summary.total}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">PPC Ready</div><div class="cpl-card-value positive" style="font-size:14px">${summary.ppcReady} lane${summary.ppcReady !== 1 ? 's' : ''} <span style="font-size:9px;color:var(--signal-teal);font-weight:400">live</span></div></div>
          <div class="cpl-card"><div class="cpl-card-label">Priced Lanes</div><div class="cpl-card-value">${summary.priced} / ${summary.total}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Avg CPL Range</div><div class="cpl-card-value">$${summary.avgLow} - $${summary.avgHigh}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Avg Margin</div><div class="cpl-card-value ${summary.avgMargin >= 50 ? 'positive' : 'warning'}">${summary.avgMargin}%</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Proj. MRR</div><div class="cpl-card-value positive">$${summary.totalMRR.toLocaleString()}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Avg ROI</div><div class="cpl-card-value ${summary.avgROI >= 0 ? 'positive' : 'warning'}">${summary.avgROI}%</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Acq Cost</div><div class="cpl-card-value warning">$${summary.totalAcqCost.toLocaleString()}</div></div>
          <div class="cpl-card cpl-health-card"><div class="cpl-card-label">Revenue Health</div><div class="cpl-health-bar">${summary.healthGreen > 0 ? html`<span class="cpl-health-seg cpl-health-green" style="flex:${summary.healthGreen}" title="${summary.healthGreen} healthy lanes">${summary.healthGreen}</span>` : ''}${summary.healthAmber > 0 ? html`<span class="cpl-health-seg cpl-health-amber" style="flex:${summary.healthAmber}" title="${summary.healthAmber} at-risk lanes">${summary.healthAmber}</span>` : ''}${summary.healthRed > 0 ? html`<span class="cpl-health-seg cpl-health-red" style="flex:${summary.healthRed}" title="${summary.healthRed} unprofitable lanes">${summary.healthRed}</span>` : ''}</div><div class="cpl-health-meta">${summary.healthGreen + summary.healthAmber + summary.healthRed > 0 ? html`<span>${summary.healthGreen}g ${summary.healthAmber}a ${summary.healthRed}r · ${summary.healthGreen + summary.healthAmber + summary.healthRed} total</span>` : html`<span style="color:var(--empire-fog)">No health data</span>`}${summary.healthNone > 0 ? html`<span style="color:var(--empire-fog);margin-left:6px">${summary.healthNone} unpriced</span>` : ''}</div></div>
        </div>

        ${reloadingIndicator}
        ${!reloading && lastRefreshed ? html`<div class="cpl-last-refreshed-row"><span class="cpl-last-refreshed">Last refreshed: ${(() => { const d = lastRefreshed; const pad = n => String(n).padStart(2,'0'); return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); })()}</span></div>` : ''}
        <div class="cpl-nav">
          <button class="cpl-nav-btn ${modelFilter === 'all' ? 'active' : ''}" onClick=${() => { setModelFilter('all'); setPage(1); }}>All</button>
          <button class="cpl-nav-btn ${modelFilter === 'ppl' ? 'active' : ''}" onClick=${() => { setModelFilter('ppl'); setPage(1); }}>PPL</button>
          <button class="cpl-nav-btn ${modelFilter === 'ppc' ? 'active' : ''}" onClick=${() => { setModelFilter('ppc'); setPage(1); }}>PPC</button>
          <button class="cpl-nav-btn ${modelFilter === 'service' ? 'active' : ''}" onClick=${() => { setModelFilter('service'); setPage(1); }}>Service</button>
          <button class="cpl-nav-btn ${serviceOnly ? 'active' : ''}" onClick=${() => { setServiceOnly(!serviceOnly); setPage(1); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>Service Only</button>
          <input class="cmp-niche-search" type="search" placeholder="Filter by niche..." value=${laneSearch} onChange=${e => { setLaneSearch(e.target.value); setPage(1); }} style="flex:0 1 160px;margin:0 4px" />
          <span style="flex:1;text-align:right;font-size:10px;color:var(--empire-fog);padding:5px 0">${filtered.length} lanes</span>
        </div>
        ${serviceOnly ? html\ : ''}

        <table class="cpl-table">
          <thead><tr>
            <th>Lane</th><th>Niche</th><th>Sub-Niche</th><th>CPL Lo</th><th>CPL Hi</th>
            <th>Model</th><th>Sell Price</th><th>Margin</th><th>Annual Rev</th><th title="ROI = (Monthly Revenue − Monthly Acq Cost) ÷ Monthly Acq Cost × 100. Measures return on lead acquisition spend.">ROI</th><th title="Mo. Rev = Projected monthly revenue from this lane at the estimated conversion rate and sell price.">Mo. Rev</th><th title="Acq Cost = CPL × monthly volume. What it costs per month to acquire leads for this lane.">Acq Cost</th><th title="BE Vol = Breakeven volume = Monthly Acq Cost ÷ (Sell Price − CPL). Leads per month needed to break even.">BE Vol</th><th title="Health = composite: Green (ROI > 0% & margin > 50% & BE ≤ 200), Amber (ROI > 0% but margin ≤ 50% or BE > 200), Red (ROI ≤ 0%)">Health</th>
          </tr></thead>
          ${reloading ? html`<tbody class="cpl-skeleton">${[1,2,3,4,5,6,7,8].map(i => html`<tr><td colspan="15"><div class="cpl-skel-bar"></div></td></tr>`)}</tbody>` : html`<tbody>
            ${pageLanes.map(l => html`
              <tr class="${l.cpl_available ? '' : 'seo-row'}">
                <td style="color:var(--empire-fog);font-family:var(--font-mono);font-size:10px">L${String(l.lane_id).padStart(2,'0')}</td>
                <td>${l.niche}</td>
                <td>${l.sub_niche}</td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available ? (modelFilter === 'ppc' && l.cpl_ppc_low != null ? '$' + l.cpl_ppc_low : '$' + l.cpl_low) : '-'}</td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available ? (modelFilter === 'ppc' && l.cpl_ppc_high != null ? '$' + l.cpl_ppc_high : '$' + l.cpl_high) : '-'}</td>
                <td><span class="cpl-badge ${modelClass(l.best_model)}">${l.best_model || 'n/a'}</span>${l.ppc_ready ? html`<span class="cpl-badge ppc-live" title="Live Pay-Per-Call enabled · Storm-triggered voice dispatch active">☎ LIVE</span>` : ''}</td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available ? '$' + l.sell_price_low + ' - $' + l.sell_price_high : '-'}</td>
                <td>
                  ${l.cpl_available ? html`
                    <span class="cpl-margin-bar ${marginClass(l.margin_pct)}" style="width:${Math.min(l.margin_pct, 100)}%"></span>
                    ${l.margin_pct}%
                  ` : '-'}
                </td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available ? '$' + (l.annual_revenue || 0).toLocaleString() : '-'}</td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available ? (l.roi_pct != null ? l.roi_pct + '%' : '-') : '-'}</td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available && l.monthly_revenue ? '$' + l.monthly_revenue.toLocaleString() : '-'}</td>
                <td style="font-family:var(--font-mono);font-size:10px;color:var(--status-amber)">${l.cpl_available && l.monthly_acq_cost ? '$' + l.monthly_acq_cost.toLocaleString() : '-'}</td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available && l.breakeven ? l.breakeven : '-'}</td>
                <td style="text-align:center">${l.cpl_available ? 
                  (l.roi_pct != null && l.roi_pct > 0 && (l.margin_pct != null && l.margin_pct > 50) && (l.breakeven != null && l.breakeven <= 200) ? html`<span class="hth-dot green" title="ROI ${l.roi_pct}% · Margin ${l.margin_pct}% · BE ${l.breakeven}"></span>` : 
                  (l.roi_pct != null && l.roi_pct > 0 ? html`<span class="hth-dot amber" title="ROI ${l.roi_pct}% · Margin ${l.margin_pct != null ? l.margin_pct + '%' : 'N/A'} · BE ${l.breakeven != null ? l.breakeven : 'N/A'}"></span>` : 
                  html`<span class="hth-dot red" title="ROI ${l.roi_pct != null ? l.roi_pct + '%' : 'N/A'} · Margin ${l.margin_pct != null ? l.margin_pct + '%' : 'N/A'} · BE ${l.breakeven != null ? l.breakeven : 'N/A'}"></span>`)) : '—'}</td>
              </tr>
            `)}
          </tbody>`}
        </table>

        ${totalPages > 1 ? html`
          <div class="cpl-pagination">
            <button disabled=${pg <= 1} onClick=${() => setPage(pg - 1)}>Prev</button>
            <span>Page ${pg} of ${totalPages}</span>
            <button disabled=${pg >= totalPages} onClick=${() => setPage(pg + 1)}>Next</button>
          </div>
        ` : ''}
      ` : html`
        <div class="roi-form">
          <div class="roi-form-row">
            <div class="roi-form-group">
              <label>Niche</label>
              <select value=${roiNiche} onChange=${e => setRoiNiche(e.target.value)}>
                ${[...new Set(lanes.map(l => l.niche))].sort().map(n => html`<option value="${n}">${n}</option>`)}
              </select>
            </div>
            <div class="roi-form-group">
              <label>Monthly Volume (leads)</label>
              <input type="number" min="1" max="10000" value=${roiVolume} onChange=${e => setRoiVolume(parseInt(e.target.value) || 100)} />
            </div>
            <div class="roi-form-group">
              <label>Sell Price / Lead (optional - blank uses default 2.5x CPL)</label>
              <input type="number" min="1" step="10" placeholder="Auto (2.5x CPL)" value=${roiSellPrice} onChange=${e => setRoiSellPrice(e.target.value)} />
            </div>
            <button class="roi-form-apply" disabled=${roiLoading} onClick=${runRoi}>
              ${roiLoading ? 'Calculating...' : 'Calculate ROI'}
            </button>
          </div>
        </div>

        ${roiResult ? html`
          <div class="roi-results">
            <div class="roi-card">
              <div class="roi-card-label">Monthly Revenue</div>
              <div class="roi-card-value ${roiClass(roiResult.monthly_revenue - roiResult.monthly_acquisition_cost)}">
                $${(roiResult.monthly_revenue || 0).toLocaleString()}
              </div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">Acquisition Cost</div>
              <div class="roi-card-value">$${(roiResult.monthly_acquisition_cost || 0).toLocaleString()}</div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">Gross Profit</div>
              <div class="roi-card-value ${roiClass(roiResult.monthly_revenue - roiResult.monthly_acquisition_cost)}">
                $${((roiResult.monthly_revenue || 0) - (roiResult.monthly_acquisition_cost || 0)).toLocaleString()}
              </div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">Margin</div>
              <div class="roi-card-value ${roiClass(roiResult.margin_pct)}">${roiResult.margin_pct}%</div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">ROI</div>
              <div class="roi-card-value ${roiClass(roiResult.roi_percentage)}">${roiResult.roi_percentage}%</div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">Breakeven Volume</div>
              <div class="roi-card-value">${roiResult.breakeven_volume || 'N/A'}</div>
            </div>
          </div>
        ` : ''}

        ${roiResult ? html`
          <h3 style="font-size:12px;font-weight:600;margin:20px 0 12px;color:var(--empire-white)">Per-Lane Projection (at ${roiVolume} leads/mo)</h3>
          <div class="roi-table-wrap">
            <table class="roi-table">
              <thead><tr>
                <th>Lane</th><th>Niche</th><th>Model</th><th>CPL</th><th>Acquisition</th><th>Revenue</th><th>Profit</th><th>Margin</th>
              </tr></thead>
              <tbody>
                ${lanes.filter(l => l.cpl_available && l.niche === roiNiche).map(l => {
                  const midCpl = (l.cpl_low + l.cpl_high) / 2;
                  const acq = Math.round(midCpl * roiVolume);
                  const nicheLanes = lanes.filter(x => x.cpl_available && x.niche === roiNiche);
                  const rev = nicheLanes.length ? Math.round((roiResult.monthly_revenue || 0) / nicheLanes.length) : 0;
                  const profit = rev - acq;
                  const margin = rev > 0 ? Math.round((profit / rev) * 100) : 0;
                  return html`
                    <tr>
                      <td style="font-family:var(--font-mono);font-size:10px;color:var(--empire-fog)">L${String(l.lane_id).padStart(2,'0')}</td>
                      <td>${l.sub_niche}</td>
                      <td><span class="cpl-badge ${modelClass(l.best_model)}">${l.best_model || 'n/a'}</span>${l.ppc_ready ? html`<span class="cpl-badge ppc-live" title="Live Pay-Per-Call enabled">☎ LIVE</span>` : ''}</td>
                      <td style="font-family:var(--font-mono)">$${l.cpl_low}-$${l.cpl_high}</td>
                      <td style="font-family:var(--font-mono)">$${acq.toLocaleString()}</td>
                      <td style="font-family:var(--font-mono)" class="pos">$${rev.toLocaleString()}</td>
                      <td style="font-family:var(--font-mono)" class="${profit >= 0 ? 'pos' : 'neg'}">$${profit.toLocaleString()}</td>
                      <td class="${margin >= 30 ? 'pos' : 'neg'}">${margin}%</td>
                    </tr>
                  `;
                })}
              </tbody>
            </table>
          </div>

      ${tab === 'compare' ? html`
        <div class="cmp-intro">Comparing <strong>PPL</strong> (Pay Per Lead) vs <strong>PPC</strong> (Pay Per Click) pricing models side-by-side per lane.</div>

        <div class="cmp-niche-filter">
          <input class="cmp-niche-search" type="text" placeholder="Search niche..." value=${nicheSearch} onChange=${e => setNicheSearch(e.target.value)} />
          <button class="cmp-niche-btn ${cmpNicheFilter === null && nicheSearch === '' ? 'active' : ''}" onClick=${() => { setCmpNicheFilter(null); setNicheSearch(''); }}>All</button>
          ${[...new Set(lanes.filter(l => l.cpl_available).map(l => l.niche))].sort().filter(n => n.toLowerCase().includes(nicheSearch.toLowerCase())).map(n => html`
            <button class="cmp-niche-btn ${cmpNicheFilter === n ? 'active' : ''}" onClick=${() => setCmpNicheFilter(n)}>${n}</button>
          `)}
        </div>

        <div class="cmp-summary">
          <div class="cmp-card"><div class="cmp-card-label">Total Lanes</div><div class="cmp-card-value">${cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter).length : lanes.length}</div></div>
          <div class="cmp-card"><div class="cmp-card-label">Best PPL</div><div class="cmp-card-value teal">${(() => { const pplLanes = cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter) : lanes; const pplLowest = pplLanes.filter(l => l.cpl_available && l.cpl && l.cpl.ppl && l.cpl.ppl.low != null).map(l => l.cpl.ppl.low); return pplLowest.length ? '$' + Math.min(...pplLowest) : '-' })()}</div></div>
          <div class="cmp-card"><div class="cmp-card-label">Best PPC</div><div class="cmp-card-value gold">${(() => { const ppcLanes = cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter) : lanes; const ppcLowest = ppcLanes.filter(l => l.cpl_available && l.cpl && l.cpl.ppc && l.cpl.ppc.low != null).map(l => l.cpl.ppc.low); return ppcLowest.length ? '$' + Math.min(...ppcLowest) : '-' })()}</div></div>
          <div class="cmp-card"><div class="cmp-card-label">Lanes with Both</div><div class="cmp-card-value neutral">${(cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter) : lanes).filter(l => l.cpl_available && l.cpl && l.cpl.ppl && l.cpl.ppc).length}</div></div>
        </div>

        <table class="cmp-table">
          <thead><tr>
            <th rowspan="2">Lane</th>
            <th rowspan="2">Niche</th>
            <th colspan="3" style="text-align:center;border-bottom:1px solid var(--signal-teal);color:var(--signal-teal)">PPL</th>
            <th colspan="3" style="text-align:center;border-bottom:1px solid var(--signal-gold);color:var(--signal-gold)">PPC</th>
            <th rowspan="2">Best</th>
          </tr><tr>
            <th style="color:var(--empire-fog)">CPL Range</th>
            <th style="color:var(--empire-fog)">Sell Price</th>
            <th style="color:var(--empire-fog)">Margin</th>
            <th style="color:var(--empire-fog)">CPL Range</th>
            <th style="color:var(--empire-fog)">Sell Price</th>
            <th style="color:var(--empire-fog)">Margin</th>
          </tr></thead>
          <tbody>
            ${(cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter) : lanes).map(l => {
              if (!l.cpl_available || !l.cpl) return html`
                <tr class="seo-row">
                  <td style="font-family:var(--font-mono);font-size:10px;color:var(--empire-fog)">L${String(l.lane_id).padStart(2,'0')}</td>
                  <td>${l.niche}</td>
                  <td class="cmp-model-cell" colspan="3" style="text-align:center;color:var(--empire-fog);font-size:10px">Service lane — no CPL data</td>
                  <td class="cmp-model-cell" colspan="3" style="text-align:center;color:var(--empire-fog);font-size:10px">Service lane — no CPL data</td>
                  <td style="text-align:center"><span class="cpl-badge service">service</span></td>
                </tr>
              `;
              const ppl = l.cpl.ppl; const ppc = l.cpl.ppc;
              const hasPpl = ppl && ppl.low != null; const hasPpc = ppc && ppc.low != null;
              const pplMid = hasPpl ? (ppl.low + ppl.high) / 2 : 0;
              const ppcMid = hasPpc ? (ppc.low + ppc.high) / 2 : 0;
              const pplPrice = hasPpl ? Math.round(pplMid * 2.5) : 0;
              const ppcPrice = hasPpc ? Math.round(ppcMid * 2.5) : 0;
              const pplMargin = hasPpl ? Math.round((pplPrice - pplMid) / pplPrice * 100) : 0;
              const ppcMargin = hasPpc ? Math.round((ppcPrice - ppcMid) / ppcPrice * 100) : 0;
              const best = hasPpl && hasPpc ? (pplMargin > ppcMargin ? 'ppl' : 'ppc') : hasPpl ? 'ppl' : hasPpc ? 'ppc' : 'none';
              return html`
                <tr class="${best === 'ppl' ? 'cmp-winner' : ''}">
                  <td style="font-family:var(--font-mono);font-size:10px;color:var(--empire-fog)">L${String(l.lane_id).padStart(2,'0')}</td>
                  <td>${l.niche}${l.sub_niche !== l.niche ? html` <span style="color:var(--empire-fog);font-size:9px">· ${l.sub_niche}</span>` : ''}</td>
                  <td class="cmp-model-cell cmp-value">${hasPpl ? '$${ppl.low} — $${ppl.high}' : '-'}</td>
                  <td class="cmp-model-cell cmp-value">${hasPpl ? '$${pplPrice}' : '-'}</td>
                  <td class="cmp-model-cell cmp-value ${pplMargin >= 30 ? 'pos' : pplMargin > 0 ? '' : 'neg'}">${hasPpl ? pplMargin + '%' : '-'}</td>
                  <td class="cmp-model-cell cmp-value">${hasPpc ? '$${ppc.low} — $${ppc.high}' : '-'}</td>
                  <td class="cmp-model-cell cmp-value">${hasPpc ? '$${ppcPrice}' : '-'}</td>
                  <td class="cmp-model-cell cmp-value ${ppcMargin >= 30 ? 'pos' : ppcMargin > 0 ? '' : 'neg'}">${hasPpc ? ppcMargin + '%' : '-'}</td>
                  <td style="text-align:center">${best !== 'none' ? html`<span class="cmp-model-label cmp-${best}">${best.toUpperCase()}</span>` : '-'}</td>
                </tr>
              `;
            })}
          </tbody>
        </table>
      ` : ''}

        ` : ''}
      `}
    </div>
  `;
};

// ── TRAFFIC & ADS ──────────────────────────────────────────────────
function TrafficAds() {
  const [platforms, setPlatforms] = useState(null);
  const [campaigns, setCampaigns] = useState(null);
  const [trends, setTrends] = useState(null);
  const [summary, setSummary] = useState(null);
  const [narrative, setNarrative] = useState(null);
  const [tab, setTab] = useState('platforms');
  const [err, setErr] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [pl, ca, tr, su, na] = await Promise.all([
        apiFetch('/api/traffic-ads/platforms').then(r => r.json()),
        apiFetch('/api/traffic-ads/campaigns').then(r => r.json()),
        apiFetch('/api/traffic-ads/trends').then(r => r.json()),
        apiFetch('/api/traffic-ads/summary').then(r => r.json()),
        apiFetch('/api/traffic-ads/narrative').then(r => r.json()),
      ]);
      setPlatforms(pl);
      setCampaigns(ca);
      setTrends(tr);
      setSummary(su);
      setNarrative(na);
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);
  useEffect(() => { reload(); const iv = setInterval(reload, 30000); return () => clearInterval(iv); }, [reload]);
  if (err) return html`<div class="stub"><div class="stub-title">Traffic & Ads Error</div><div class="stub-body">${err}</div></div>`;
  if (!platforms) return html`<div class="stub"><div class="stub-body">Loading traffic & ads...</div></div>`;
  const total = summary?.consolidated || {};
  const totalConversions = total.total_conversions || 0;
  const totalImpressions = total.total_impressions || 0;
  const totalClicks = total.total_clicks || 0;
  const totalSpend = total.total_spend || 0;
  return html`
    <div class="section-header"><div><div class="section-title"><em>Traffic & Ads</em></div><div class="section-sub">Cross-platform campaigns · trends · budget optimization</div></div></div>
    <div class="pulse-tabs" style={{marginTop:"8px"}}>
      <button class=${'pulse-tab' + (tab==='platforms' ? ' active' : '')} onClick=${()=>setTab('platforms')}>Platforms</button>
      <button class=${'pulse-tab' + (tab==='campaigns' ? ' active' : '')} onClick=${()=>setTab('campaigns')}>Campaigns</button>
      <button class=${'pulse-tab' + (tab==='trends' ? ' active' : '')} onClick=${()=>setTab('trends')}>Trends</button>
      <button class=${'pulse-tab' + (tab==='narrative' ? ' active' : '')} onClick=${()=>setTab('narrative')}>Narrative</button>
    </div>
    ${tab === 'platforms' ? html`
    <div class="pulse-grid" style={{marginTop:"12px"}}>
      <div class="stat-card"><div class="stat-label">TOTAL CONVERSIONS</div><div class="stat-value teal">${totalConversions.toLocaleString()}</div><div class="stat-meta">${totalClicks.toLocaleString()} clicks · ${(totalImpressions/1000).toFixed(0)}K impressions</div></div>
      <div class="stat-card"><div class="stat-label">TOTAL SPEND</div><div class="stat-value">$${totalSpend.toLocaleString()}</div><div class="stat-meta">CPA: $${totalSpend > 0 && totalConversions > 0 ? (totalSpend/totalConversions).toFixed(2) : '\u2014'}</div></div>
      <div class="stat-card"><div class="stat-label">PLATFORMS ACTIVE</div><div class="stat-value teal">${(platforms.platforms||[]).length}</div><div class="stat-meta">${(platforms.total?.total_conversions||0)} total conversions</div></div>
      <div class="stat-card"><div class="stat-label">TRENDING NICHES</div><div class="stat-value">${(trends?.trends||[]).length}</div><div class="stat-meta">${(trends?.seasonal_spikes||[]).length} seasonal spikes</div></div>
    </div>
    <div class="pipeline-breakdown">
      <div class="pipeline-h"><div class="pipeline-title">Platform <strong>Performance</strong></div></div>
      ${(platforms.platforms||[]).length > 0 ? html`<table class="tbl">
        <thead><tr><th>Platform</th><th>Impressions</th><th>Clicks</th><th>Conversions</th><th>Spend</th><th>CTR</th><th>CPA</th></tr></thead>
        <tbody>${(platforms.platforms||[]).map((p, i) => html`
          <tr key=${i}>
            <td style="font-weight:500;color:var(--empire-white);text-transform:capitalize">${p.name || 'unknown'}</td>
            <td class="tbl-num">${(p.impressions||0).toLocaleString()}</td>
            <td class="tbl-num">${(p.clicks||0).toLocaleString()}</td>
            <td class="tbl-num">${(p.conversions||0).toLocaleString()}</td>
            <td class="tbl-num">$${(p.spend||0).toLocaleString()}</td>
            <td class="tbl-num">${p.impressions > 0 ? ((p.clicks||0)/p.impressions*100).toFixed(1) + '%' : '\u2014'}</td>
            <td class="tbl-num">$${p.conversions > 0 ? ((p.spend||0)/p.conversions).toFixed(2) : '\u2014'}</td>
          </tr>
        `)}</tbody>
      </table>` : html`<div class="stub-body">No platform data available.</div>`}
    </div>
    ` : null}
    ${tab === 'campaigns' ? html`
    <div class="pipeline-breakdown" style={{marginTop:"12px"}}>
      <div class="pipeline-h"><div class="pipeline-title">Active <strong>Campaigns</strong></div><div class="pipeline-total">${(campaigns?.campaigns||[]).length} campaigns</div></div>
      ${(campaigns?.campaigns||[]).length > 0 ? html`<table class="tbl">
        <thead><tr><th>Campaign</th><th>Platform</th><th>Budget</th><th>Spend</th><th>Impressions</th><th>Clicks</th><th>Conversions</th><th>ROAS</th></tr></thead>
        <tbody>${(campaigns.campaigns||[]).map((c, i) => html`
          <tr key=${i}>
            <td style="font-weight:500;color:var(--empire-white)">${c.name||'unknown'}</td>
            <td style="text-transform:capitalize">${c.platform||'\u2014'}</td>
            <td class="tbl-num">$${(c.budget||0).toLocaleString()}</td>
            <td class="tbl-num">$${(c.spend||0).toLocaleString()}</td>
            <td class="tbl-num">${(c.impressions||0).toLocaleString()}</td>
            <td class="tbl-num">${(c.clicks||0).toLocaleString()}</td>
            <td class="tbl-num">${(c.conversions||0).toLocaleString()}</td>
            <td class="tbl-num" style="color:var(--signal-teal)">${c.spend > 0 && c.revenue ? (c.revenue/c.spend).toFixed(2)+'x' : '\u2014'}</td>
          </tr>
        `)}</tbody>
      </table>` : html`<div class="stub-body">No active campaigns.</div>`}
    </div>
    ` : null}
    ${tab === 'trends' ? html`
    <div style={{marginTop:"12px"}}>
      ${(trends?.trends||[]).length > 0 ? html`<div class="pipeline-breakdown">
        <div class="pipeline-h"><div class="pipeline-title">Trending <strong>Niches</strong></div></div>
        ${(trends.trends||[]).map((t, i) => html`
          <div key=${i} class="rv-bar-row">
            <div class="rv-bar-label"><span class="rv-bar-lane">${t.niche||t.name||'unknown'}</span><span class="rv-bar-niche">${t.volume||'\u2014'} searches</span></div>
            <div class="rv-bar-track"><div class="rv-bar-fill" style=${{width:Math.min(100,((t.growth||0)*100).toFixed(0))+"%", backgroundColor:"var(--strike-cyan)"}}></div></div>
            <div class="rv-bar-val">${t.growth != null ? (t.growth*100).toFixed(1)+"%" : '\u2014'}</div>
            <div class="rv-bar-meta">${t.momentum||''}</div>
          </div>
        `)}
      </div>` : null}
      ${(trends?.seasonal_spikes||[]).length > 0 ? html`<div class="pipeline-breakdown" style={{marginTop:"12px"}}>
        <div class="pipeline-h"><div class="pipeline-title">Seasonal <strong>Spikes</strong></div></div>
        ${trends.seasonal_spikes.map((s, i) => html`
          <div key=${i} style={{padding:"10px 14px",borderBottom:"1px solid var(--empire-border)",fontSize:"11px",fontFamily:"var(--font-mono)"}}>
            <span style="color:var(--empire-white);font-weight:500">${s.niche||s.name||'\u2014'}</span>
            <span style={{color:"var(--empire-fog)",marginLeft:8}}>${s.month||'\u2014'} · ${s.expected_impact||''}</span>
          </div>
        `)}
      </div>` : null}
    </div>
    ` : null}
    ${tab === 'narrative' ? html`
    <div style={{marginTop:"12px", padding:"20px 24px", background:"rgba(15,23,42,0.5)", border:"1px solid var(--empire-border)", borderRadius:12, lineHeight:1.8, fontSize:"13px"}}>
      ${narrative?.narrative ? narrative.narrative.split('\n').map((p,i) => html`<p key=${i} style={{marginBottom:12}}>${p}</p>`) : html`<div class="stub-body">No narrative generated yet.</div>`}
      ${narrative?.recommendations ? html`<div style={{marginTop:16}}><strong style={{color:"var(--signal-teal)"}}>Recommendations:</strong><ul>${narrative.recommendations.map((r,i) => html`<li key=${i} style={{marginTop:6}}>${r}</li>`)}</ul></div>` : null}
      ${narrative?.timestamp ? html`<div style={{marginTop:16, fontSize:"9px", color:"var(--empire-fog)", fontFamily:"var(--font-mono)"}}>Generated: ${narrative.timestamp}</div>` : null}
    </div>
    ` : null}
  `;
}



// ── STACK ENGINEERING ──────────────────────────────────────────────
function Stack() {
  const [status, setStatus] = useState(null);
  const [services, setServices] = useState(null);
  const [incidents, setIncidents] = useState(null);
  const [report, setReport] = useState(null);
  const [tab, setTab] = useState('overview');
  const [err, setErr] = useState(null);
  const reload = useCallback(async () => {
    try {
      const [st, sv, ic, rp] = await Promise.all([
        apiFetch('/api/stack/status').then(r => r.json()),
        apiFetch('/api/stack/services').then(r => r.json()),
        apiFetch('/api/stack/incidents').then(r => r.json()),
        apiFetch('/api/stack/report').then(r => r.json()),
      ]);
      setStatus(st); setServices(sv); setIncidents(ic); setReport(rp); setErr(null);
    } catch (e) { if (e.message !== 'Unauthorized') setErr(e.message); }
  }, []);
  useEffect(() => { reload(); const iv = setInterval(reload, 30000); return () => clearInterval(iv); }, [reload]);
  if (err) return html`<div class="stub"><div class="stub-title">Stack Error</div><div class="stub-body">${err}</div></div>`;
  if (!status) return html`<div class="stub"><div class="stub-body">Loading stack status...</div></div>`;
  const resource = status?.resources || {};
  const health = status?.health || 'unknown';
  const healthColor = health === 'healthy' ? 'var(--signal-teal)' : health === 'degraded' ? 'var(--status-amber)' : 'var(--status-red)';
  return html`
    <div class="section-header"><div><div class="section-title"><em>Stack</em></div><div class="section-sub">Infrastructure · services · incidents · monitoring</div></div></div>
    <div class="pulse-tabs" style={{marginTop:"8px"}}>
      <button class=${'pulse-tab' + (tab==='overview' ? ' active' : '')} onClick=${()=>setTab('overview')}>Overview</button>
      <button class=${'pulse-tab' + (tab==='services' ? ' active' : '')} onClick=${()=>setTab('services')}>Services</button>
      <button class=${'pulse-tab' + (tab==='incidents' ? ' active' : '')} onClick=${()=>setTab('incidents')}>Incidents</button>
      <button class=${'pulse-tab' + (tab==='report' ? ' active' : '')} onClick=${()=>setTab('report')}>Report</button>
    </div>
    ${tab === 'overview' ? html`
    <div class="pulse-grid" style={{marginTop:"12px"}}>
      <div class="stat-card"><div class="stat-label">SYSTEM HEALTH</div><div class="stat-value" style="color:${healthColor}">${health.toUpperCase()}</div><div class="stat-meta">${status?.uptime || '\u2014'} uptime</div></div>
      <div class="stat-card"><div class="stat-label">SERVICES</div><div class="stat-value teal">${status?.service_count || 0}</div><div class="stat-meta">${status?.online||0} online · ${status?.stopped||0} offline</div></div>
      <div class="stat-card"><div class="stat-label">CPU</div><div class="stat-value">${resource.cpu_usage_pct != null ? resource.cpu_usage_pct.toFixed(1)+"%" : '\u2014'}</div><div class="stat-meta">${resource.cpu_cores||'\u2014'} cores</div></div>
      <div class="stat-card"><div class="stat-label">MEMORY</div><div class="stat-value">${resource.memory_used_mb != null ? (resource.memory_used_mb/1024).toFixed(1)+"GB" : '\u2014'}</div><div class="stat-meta">${resource.memory_total_mb != null ? (resource.memory_total_mb/1024).toFixed(1)+'GB' : '\u2014'} total</div></div>
    </div>
    <div class="pipeline-breakdown">
      <div class="pipeline-h"><div class="pipeline-title">Resource <strong>Usage</strong></div></div>
      <div class="split">
        <div class="panel">
          <div class="panel-head">Disk</div>
          <div style="font-family:var(--font-mono);font-size:28px;color:var(--empire-white)">${resource.disk_used || "\u2014" : '\u2014'}GB</div>
          <div style="font-family:var(--font-mono);font-size:11px;color:var(--empire-fog);margin-top:4px">of ${resource.disk_total||'\u2014'}</div>
          ${resource.disk_usage_pct != null ? html`<div style={{marginTop:8,height:6,background:"var(--empire-elevated)",borderRadius:3,overflow:"hidden"}}><div style=${{height:"100%",width:Math.min(100,parseInt(resource.disk_usage_pct))+"%",background:parseInt(resource.disk_usage_pct) > 85 ? "var(--status-red)" : "var(--signal-teal)",borderRadius:3,transition:"width 0.6s var(--ease-out-empire)"}}></div></div>` : null}
        </div>
        <div class="panel">
          <div class="panel-head">Network</div>
          <div style="font-family:var(--font-mono);font-size:28px;color:var(--empire-white)">${resource.load_avg || "\u2014" : '\u2014'}</div>
          <div style="font-family:var(--font-mono);font-size:11px;color:var(--empire-fog);margin-top:4px">GB received · ${"\u2014" : '\u2014'} GB sent</div>
        </div>
      </div>
    </div>
    ` : null}
    ${tab === 'services' ? html`
    <div class="pipeline-breakdown" style={{marginTop:"12px"}}>
      <div class="pipeline-h"><div class="pipeline-title">Service <strong>Health</strong></div><div class="pipeline-total">${(services?.services||[]).length} services</div></div>
      ${(services?.services||[]).length > 0 ? html`<table class="tbl">
        <thead><tr><th>Service</th><th>PID</th><th>Uptime</th><th>Memory</th><th>CPU</th><th>Restarts</th><th>Status</th></tr></thead>
        <tbody>${(services.services||[]).map((s, i) => html`
          <tr key=${i}>
            <td style="font-weight:500;color:var(--empire-white);font-family:var(--font-mono);font-size:10px">${s.name||'unknown'}</td>
            <td class="tbl-mono">${s.pid||'\u2014'}</td>
            <td class="tbl-mono">${s.uptime||'\u2014'}</td>
            <td class="tbl-num">${s.memory_mb != null ? s.memory_mb.toFixed(0)+"MB" : '\u2014'}</td>
            <td class="tbl-num">${s.cpu_pct != null ? s.cpu_pct.toFixed(1)+"%" : '\u2014'}</td>
            <td class="tbl-num">${s.restarts||0}</td>
            <td><span class=${'bdg ' + (s.status === 'online' ? 'active' : s.status === 'degraded' ? 'paused' : s.status === 'offline' ? 'failed' : 'pending')}>${s.status||'unknown'}</span></td>
          </tr>
        `)}</tbody>
      </table>` : html`<div class="stub-body">No service data.</div>`}
    </div>
    ` : null}
    ${tab === 'incidents' ? html`
    <div class="pipeline-breakdown" style={{marginTop:"12px"}}>
      <div class="pipeline-h"><div class="pipeline-title">Recent <strong>Incidents</strong></div><div class="pipeline-total">${(incidents?.incidents||[]).length} incidents</div></div>
      ${(incidents?.incidents||[]).length > 0 ? html`<div class="gov-log">
        ${incidents.incidents.map((inc, i) => html`
          <div key=${i} class="gov-log-row">
            <span class="gov-log-ts">${inc.timestamp||'\u2014'}</span>
            <span class=${'gov-log-lvl ' + (inc.severity||'info').toLowerCase()}>${inc.severity||'INFO'}</span>
            <span class="gov-log-svc">${inc.service||'\u2014'}</span>
            <span class="gov-log-detail">${inc.message||inc.description||''}</span>
          </div>
        `)}
      </div>` : html`<div class="stub-body">No recent incidents.</div>`}
    </div>
    ` : null}
    ${tab === 'report' ? html`
    <div style={{marginTop:"12px", padding:"20px 24px", background:"rgba(15,23,42,0.5)", border:"1px solid var(--empire-border)", borderRadius:12, lineHeight:1.8, fontSize:"13px"}}>
      ${report?.report ? report.report.split('\n').map((p,i) => html`<p key=${i} style={{marginBottom:12}}>${p}</p>`) : html`<div class="stub-body">No report generated yet.</div>`}
      ${report?.recommendations ? html`<div style={{marginTop:16}}><strong style={{color:"var(--signal-teal)"}}>Recommendations:</strong><ul>${report.recommendations.map((r,i) => html`<li key=${i} style={{marginTop:6}}>${r}</li>`)}</ul></div>` : null}
      ${report?.timestamp ? html`<div style={{marginTop:16, fontSize:"9px", color:"var(--empire-fog)", fontFamily:"var(--font-mono)"}}>Generated: ${report.timestamp}</div>` : null}
    </div>
    ` : null}
  `;
}



// ── NETWORK ────────────────────────────────────────────────────────
function Network() {
  const [overview, setOverview] = useState(null);
  const [members, setMembers] = useState(null);
  const [referrals, setReferrals] = useState(null);
  const [report, setReport] = useState(null);
  const [tab, setTab] = useState('overview');
  const [err, setErr] = useState(null);
  const reload = useCallback(async () => {
    try {
      const [ov, mb, rf, rp] = await Promise.all([
        apiFetch('/api/network/overview').then(r => r.json()),
        apiFetch('/api/network/members').then(r => r.json()),
        apiFetch('/api/network/referrals').then(r => r.json()),
        apiFetch('/api/network/report').then(r => r.json()),
      ]);
      setOverview(ov); setMembers(mb); setReferrals(rf); setReport(rp); setErr(null);
    } catch (e) { if (e.message !== 'Unauthorized') setErr(e.message); }
  }, []);
  useEffect(() => { reload(); const iv = setInterval(reload, 30000); return () => clearInterval(iv); }, [reload]);
  if (err) return html`<div class="stub"><div class="stub-title">Network Error</div><div class="stub-body">${err}</div></div>`;
  if (!overview) return html`<div class="stub"><div class="stub-body">Loading network...</div></div>`;
  const totalMembers = overview?.total_members || 0;
  const activeMembers = overview?.active || 0;
  const totalAffiliates = (overview?.by_type && overview.by_type.affiliate) || 0;
  const totalReferrals = (referrals?.referrals||[]).length;
  return html`
    <div class="section-header"><div><div class="section-title"><em>Network</em></div><div class="section-sub">Contractors · affiliates · referrals · growth</div></div></div>
    <div class="pulse-tabs" style={{marginTop:"8px"}}>
      <button class=${'pulse-tab' + (tab==='overview' ? ' active' : '')} onClick=${()=>setTab('overview')}>Overview</button>
      <button class=${'pulse-tab' + (tab==='members' ? ' active' : '')} onClick=${()=>setTab('members')}>Members</button>
      <button class=${'pulse-tab' + (tab==='referrals' ? ' active' : '')} onClick=${()=>setTab('referrals')}>Referrals</button>
      <button class=${'pulse-tab' + (tab==='report' ? ' active' : '')} onClick=${()=>setTab('report')}>Report</button>
    </div>
    ${tab === 'overview' ? html`
    <div class="pulse-grid" style={{marginTop:"12px"}}>
      <div class="stat-card"><div class="stat-label">TOTAL MEMBERS</div><div class="stat-value teal">${totalMembers}</div><div class="stat-meta">${activeMembers} active</div></div>
      <div class="stat-card"><div class="stat-label">AFFILIATES</div><div class="stat-value">${totalAffiliates}</div><div class="stat-meta">${"\u2014"} active</div></div>
      <div class="stat-card"><div class="stat-label">REFERRALS</div><div class="stat-value teal">${totalReferrals}</div><div class="stat-meta">${(referrals?.referrals||[]).filter(r=>r.status==='pending').length} pending</div></div>
      <div class="stat-card"><div class="stat-label">GROWTH</div><div class="stat-value" style="color:var(--strike-cyan)">${overview?.conversion_rate_pct != null ? overview.conversion_rate_pct.toFixed(1)+"%" : '\u2014'}</div><div class="stat-meta">${overview?.total_leads||0} this month</div></div>
    </div>
    <div class="pipeline-breakdown">
      <div class="pipeline-h"><div class="pipeline-title">Network <strong>Composition</strong></div></div>
      <div class="split">
        <div class="panel">
          <div class="panel-head">By Type</div>
          ${overview?.by_type && Object.keys(overview.by_type).length > 0 ? Object.entries(overview.by_type).map(([k,v]) => html`
            <div class="rv-bar-row" key=${k}>
              <div class="rv-bar-label"><span class="rv-bar-lane" style="text-transform:capitalize">${k}</span></div>
              <div class="rv-bar-track"><div class="rv-bar-fill" style=${{width:Math.min(100,(v/Math.max(1,totalMembers)*100).toFixed(0))+"%",backgroundColor:"var(--signal-teal)"}}></div></div>
              <div class="rv-bar-val">${v}</div>
            </div>
          `) : html`<div class="stub-body">No type data.</div>`}
        </div>
        <div class="panel">
          <div class="panel-head">Metrics</div>
          <div style="font-family:var(--font-mono);font-size:24px;color:var(--signal-teal)">$${(overview?.total_revenue||0).toLocaleString()}</div>
          <div style="font-family:var(--font-mono);font-size:11px;color:var(--empire-fog);margin-top:4px">Revenue · ${overview?.total_leads||0} leads · ${overview?.total_conversions||0} conversions</div>
          <div style="font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);margin-top:12px">Conversion rate: ${overview?.conversion_rate_pct != null ? overview.conversion_rate_pct+'%' : '—'}</div>
              <div class="rv-bar-label"><span class="rv-bar-lane" style="text-transform:capitalize">${s.status||'unknown'}</span></div>
              <div class="rv-bar-track"><div class="rv-bar-fill" style=${{width:Math.min(100,((s.count||0)/Math.max(1,totalMembers)*100).toFixed(0))+"%",backgroundColor:s.status==='active'?"var(--signal-teal)":s.status==='pending'?"var(--status-amber)":"var(--empire-mist)"}}></div></div>
              <div class="rv-bar-val">${s.count||0}</div>
            </div>
          `) : html`<div class="stub-body">No status data.</div>`}
        </div>
      </div>
    </div>
    ` : null}
    ${tab === 'members' ? html`
    <div class="pipeline-breakdown" style={{marginTop:"12px"}}>
      <div class="pipeline-h"><div class="pipeline-title">Network <strong>Members</strong></div><div class="pipeline-total">${(members?.members||[]).length} members</div></div>
      ${(members?.members||[]).length > 0 ? html`<table class="tbl">
        <thead><tr><th>Name</th><th>Type</th><th>Status</th><th>Leads</th><th>Conversion</th><th>Revenue</th><th>Score</th></tr></thead>
        <tbody>${(members.members||[]).map((m, i) => html`
          <tr key=${i}>
            <td style="font-weight:500;color:var(--empire-white)">${m.name||m.email||'unknown'}</td>
            <td style="text-transform:capitalize">${m.type||'\u2014'}</td>
            <td><span class=${'bdg ' + (m.status==='active'?'active':m.status==='pending'?'pending':m.status==='approved'?'approved':'rejected')}>${m.status||'unknown'}</span></td>
            <td class="tbl-num">${m.leads||0}</td>
            <td class="tbl-num">${m.conversion_rate_pct != null ? m.conversion_rate_pct.toFixed(1)+"%" : '\u2014'}</td>
            <td class="tbl-num teal">$${(m.revenue||0).toLocaleString()}</td>
            <td class="tbl-num" style="color:var(--strike-cyan)">${m.quality_score != null ? (m.quality_score*100).toFixed(0) : '\u2014'}</td>
          </tr>
        `)}</tbody>
      </table>` : html`<div class="stub-body">No member data.</div>`}
    </div>
    ` : null}
    ${tab === 'referrals' ? html`
    <div class="pipeline-breakdown" style={{marginTop:"12px"}}>
      <div class="pipeline-h"><div class="pipeline-title">Referral <strong>Tracking</strong></div><div class="pipeline-total">${(referrals?.referrals||[]).length} referrals</div></div>
      ${(referrals?.referrals||[]).length > 0 ? html`<table class="tbl">
        <thead><tr><th>Referrer</th><th>Referred</th><th>Status</th><th>Tier</th><th>Commission</th><th>Date</th></tr></thead>
        <tbody>${(referrals.referrals||[]).map((r, i) => html`
          <tr key=${i}>
            <td style="font-weight:500;color:var(--empire-white)">${r.referrer||'\u2014'}</td>
            <td>${r.referred||'\u2014'}</td>
            <td><span class=${'bdg ' + (r.status==='converted'?'active':r.status==='pending'?'pending':r.status==='approved'?'approved':'rejected')}>${r.status||'pending'}</span></td>
            <td class="tbl-mono">${r.tier||'\u2014'}</td>
            <td class="tbl-num">$${(r.value||0).toLocaleString()}</td>
            <td class="tbl-mono">${r.date||'\u2014'}</td>
          </tr>
        `)}</tbody>
      </table>` : html`<div class="stub-body">No referral data.</div>`}
    </div>
    ` : null}
    ${tab === 'report' ? html`
    <div style={{marginTop:"12px", padding:"20px 24px", background:"rgba(15,23,42,0.5)", border:"1px solid var(--empire-border)", borderRadius:12, lineHeight:1.8, fontSize:"13px"}}>
      ${report?.report ? report.report.split('\n').map((p,i) => html`<p key=${i} style={{marginBottom:12}}>${p}</p>`) : html`<div class="stub-body">No report generated yet.</div>`}
      ${report?.growth?.niche_gaps ? html`<div style={{marginTop:16}}><strong style={{color:"var(--signal-teal)"}}>Growth Opportunities:</strong><ul>${report.opportunities.map((o,i) => html`<li key=${i} style={{marginTop:6}}>${o}</li>`)}</ul></div>` : null}
      ${report?.timestamp ? html`<div style={{marginTop:16, fontSize:"9px", color:"var(--empire-fog)", fontFamily:"var(--font-mono)"}}>Generated: ${report.timestamp}</div>` : null}
    </div>
    ` : null}
  `;
}



// ── LOOP ENGINEERING ───────────────────────────────────────────────
function Loop() {
  const [overview, setOverview] = useState(null);
  const [lanes, setLanes] = useState(null);
  const [pacing, setPacing] = useState(null);
  const [report, setReport] = useState(null);
  const [tab, setTab] = useState('overview');
  const [laneFocus, setLaneFocus] = useState(null);
  const [laneDetail, setLaneDetail] = useState(null);
  const [err, setErr] = useState(null);
  const reload = useCallback(async () => {
    try {
      const [ov, ln, pc, rp] = await Promise.all([
        apiFetch('/api/loop/overview').then(r => r.json()),
        apiFetch('/api/loop/lanes').then(r => r.json()),
        apiFetch('/api/loop/pacing').then(r => r.json()),
        apiFetch('/api/loop/report').then(r => r.json()),
      ]);
      setOverview(ov); setLanes(ln); setPacing(pc); setReport(rp); setErr(null);
    } catch (e) { if (e.message !== 'Unauthorized') setErr(e.message); }
  }, []);
  useEffect(() => { reload(); const iv = setInterval(reload, 30000); return () => clearInterval(iv); }, [reload]);
  useEffect(() => {
    if (laneFocus) {
      apiFetch('/api/loop/lane/' + encodeURIComponent(laneFocus)).then(r => r.json()).then(setLaneDetail).catch(() => {});
    } else { setLaneDetail(null); }
  }, [laneFocus]);
  if (err) return html`<div class="stub"><div class="stub-title">Loop Error</div><div class="stub-body">${err}</div></div>`;
  if (!overview) return html`<div class="stub"><div class="stub-body">Loading loop data...</div></div>`;
  const laneList = (lanes?.lanes || overview?.lanes || []);
  const totalLanes = overview?.total || 0;
  const activeLanes = overview?.active || 0;
  const niches = overview?.by_niche || {};
  const nicheCount = Object.keys(niches).length;
  return html`
    <div class="section-header"><div><div class="section-title"><em>Loop Engineering</em></div><div class="section-sub">Lane execution · pacing · strategy optimization</div></div></div>
    <div class="pulse-tabs" style={{marginTop:"8px"}}>
      <button class=${'pulse-tab' + (tab==='overview' ? ' active' : '')} onClick=${()=>setTab('overview')}>Overview</button>
      <button class=${'pulse-tab' + (tab==='lanes' ? ' active' : '')} onClick=${()=>setTab('lanes')}>Lanes</button>
      <button class=${'pulse-tab' + (tab==='pacing' ? ' active' : '')} onClick=${()=>setTab('pacing')}>Pacing</button>
      <button class=${'pulse-tab' + (tab==='report' ? ' active' : '')} onClick=${()=>setTab('report')}>Report</button>
    </div>
    ${tab === 'overview' ? html`
    <div class="pulse-grid" style={{marginTop:"12px"}}>
      <div class="stat-card"><div class="stat-label">TOTAL LANES</div><div class="stat-value teal">${totalLanes}</div><div class="stat-meta">${activeLanes} active</div></div>
      <div class="stat-card"><div class="stat-label">NICHES COVERED</div><div class="stat-value">${nicheCount}</div><div class="stat-meta">${Object.values(niches).reduce((a,b)=>a+(b||0),0)} strategies deployed</div></div>
      <div class="stat-card"><div class="stat-label">THROUGHPUT</div><div class="stat-value teal">${overview?.total != null ? overview.total.toLocaleString() : '\u2014'}</div><div class="stat-meta">per cycle</div></div>
      <div class="stat-card"><div class="stat-label">EFFICIENCY</div><div class="stat-value" style="color:var(--strike-cyan)">${overview?.active != null ? (overview.active/Math.max(1,overview.total||1)*100).toFixed(1)+"%" : '\u2014'}</div><div class="stat-meta">lane utilization</div></div>
    </div>
    <div class="pipeline-breakdown">
      <div class="pipeline-h"><div class="pipeline-title">Niche <strong>Distribution</strong></div></div>
      ${Object.entries(niches).length > 0 ? Object.entries(niches).map(([niche, count]) => html`
        <div class="rv-bar-row" key=${niche}>
          <div class="rv-bar-label"><span class="rv-bar-lane">${niche}</span></div>
          <div class="rv-bar-track"><div class="rv-bar-fill" style=${{width:Math.min(100,(count/Math.max(1,Object.values(niches).reduce((a,b)=>a+(b||0),0))*100).toFixed(0))+"%",backgroundColor:"var(--signal-teal)"}}></div></div>
          <div class="rv-bar-val">${count}</div>
        </div>
      `) : html`<div class="stub-body">No niche data.</div>`}
    </div>
    ` : null}
    ${tab === 'lanes' ? html`
    <div class="pipeline-breakdown" style={{marginTop:"12px"}}>
      <div class="pipeline-h"><div class="pipeline-title">Lane <strong>Execution</strong></div><div class="pipeline-total">${laneList.length} lanes</div></div>
      ${laneFocus ? html`
        <div class="rv-bar-row" style={{marginBottom:16,borderBottom:"1px solid var(--empire-divider)"}}>
          <div class="rv-bar-label"><span class="rv-bar-lane" style="color:var(--strike-cyan)">Selected: ${laneFocus}</span></div>
          <div class="rv-bar-track" style={{flex:0}}></div>
          <button style={{fontFamily:"var(--font-mono)",fontSize:"9px",cursor:"pointer",border:"1px solid var(--empire-border)",background:"transparent",color:"var(--empire-mist)",padding:"4px 10px",borderRadius:"3px"}} onClick=${()=>setLaneFocus(null)}>All lanes</button>
        </div>
        ${laneDetail ? html`
          <div class="pulse-grid">
            <div class="stat-card"><div class="stat-label">WINS</div><div class="stat-value teal">${laneDetail.wins||0}</div></div>
            <div class="stat-card"><div class="stat-label">LOSSES</div><div class="stat-value">${laneDetail.losses||0}</div></div>
            <div class="stat-card"><div class="stat-label">WIN RATE</div><div class="stat-value" style="color:var(--strike-cyan)">${(laneDetail.win_rate||0)*100 > 0 ? ((laneDetail.win_rate||0)*100).toFixed(1)+"%" : '\u2014'}</div></div>
            <div class="stat-card"><div class="stat-label">REVENUE</div><div class="stat-value teal">$${(laneDetail.revenue||0).toLocaleString()}</div></div>
          </div>
          ${laneDetail.strategies ? html`
          <div class="pipeline-h" style={{marginTop:16}}><div class="pipeline-title">Active <strong>Strategies</strong></div></div>
          <div class="si-strategy-grid">
            ${(laneDetail.strategies||[]).map((st, j) => html`
              <div key=${j} class="si-strat-card ${st.best ? 'best' : ''}">
                <div class="si-strat-top"><div class="si-strat-name">${st.name||'unnamed'}</div></div>
                <div class="si-strat-stats">
                  <div class="si-stat"><span class="si-stat-val teal">${st.wins||0}</span><span class="si-stat-lbl">Wins</span></div>
                  <div class="si-stat"><span class="si-stat-val dim">${st.losses||0}</span><span class="si-stat-lbl">Losses</span></div>
                  <div class="si-stat"><span class="si-stat-val cyan">${st.win_rate != null ? (st.win_rate*100).toFixed(0) + '%' : '\u2014'}</span><span class="si-stat-lbl">Win Rate</span></div>
                  <div class="si-stat"><span class="si-stat-val teal">$${(st.revenue||0).toLocaleString()}</span><span class="si-stat-lbl">Revenue</span></div>
                </div>
              </div>
            `)}
          </div>
          ` : null}
        ` : html`<div class="stub-body">Click a lane to see detail.</div>`}
      ` : null}
      ${!laneFocus && laneList.length > 0 ? html`<table class="tbl">
        <thead><tr><th>Lane</th><th>Niche</th><th>Strategy</th><th>Wins</th><th>Losses</th><th>Win Rate</th><th>Revenue</th></tr></thead>
        <tbody>${laneList.map((l, i) => html`
          <tr key=${i} style={{cursor:"pointer"}} onClick=${()=>setLaneFocus(l.lane_name||l.name||l.lane||'unknown')}>
            <td style="font-weight:500;color:var(--empire-white);font-family:var(--font-mono);font-size:10px">${l.lane_name||l.name||l.lane||'\u2014'}</td>
            <td>${l.niche||'\u2014'}</td>
            <td class="tbl-mono">${l.strategy||l.strategies||'\u2014'}</td>
            <td class="tbl-num">${l.wins||0}</td>
            <td class="tbl-num">${l.losses||0}</td>
            <td class="tbl-num" style="color:var(--strike-cyan)">${l.win_rate != null ? (l.win_rate*100).toFixed(1)+"%" : (l.wins > 0 || l.losses > 0) ? ((l.wins/Math.max(1,l.wins+l.losses))*100).toFixed(1)+"%" : '\u2014'}</td>
            <td class="tbl-num" style="color:var(--signal-teal)">$${(l.revenue||0).toLocaleString()}</td>
          </tr>
        `)}</tbody>
      </table>` : null}
      ${!laneFocus && laneList.length === 0 ? html`<div class="stub-body">No lane data available.</div>` : null}
    </div>
    ` : null}
    ${tab === 'pacing' ? html`
    <div style={{marginTop:"12px"}}>
      <div class="pipeline-breakdown">
        <div class="pipeline-h"><div class="pipeline-title">Throughput <strong>Forecast</strong></div></div>
        <div class="pulse-grid">
          <div class="stat-card"><div class="stat-label">CURRENT PACE</div><div class="stat-value teal">${(pacing?.forecasts||[]).length > 0 ? pacing.forecasts[0].current_pct+'%' : '\u2014'}</div><div class="stat-meta">per cycle</div></div>
          <div class="stat-card"><div class="stat-label">TARGET PACE</div><div class="stat-value">${'N/A'}</div><div class="stat-meta">${(pacing?.bottlenecks||[]).length > 0 ? (pacing.bottlenecks.length+' bottlenecks') : 'On track' : ''}</div></div>
          <div class="stat-card"><div class="stat-label">BOTTLENECKS</div><div class="stat-value teal">${(pacing?.bottlenecks||[]).length}</div><div class="stat-meta">detected</div></div>
          <div class="stat-card"><div class="stat-label">FORECAST</div><div class="stat-value" style="color:var(--strike-cyan)">${(pacing?.forecasts||[]).length > 0 ? pacing.forecasts.map(f=>f.resource).join(', ') : 'No alerts'}</div><div class="stat-meta">next cycle</div></div>
        </div>
      </div>
      ${(pacing?.bottlenecks||[]).length > 0 ? html`<div class="pipeline-breakdown" style={{marginTop:"12px"}}>
        <div class="pipeline-h"><div class="pipeline-title">Pacing <strong>Bottlenecks</strong></div></div>
        ${pacing.bottlenecks.map((b, i) => html`
          <div key=${i} style={{padding:"10px 14px",borderBottom:"1px solid var(--empire-border)",fontSize:"11px",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <span style="color:var(--empire-white);font-weight:500">${b.lane||b.name||'\u2014'}</span>
            <span style={{fontFamily:"var(--font-mono)",color:"var(--status-amber)"}}>${b.impact||b.description||''}</span>
          </div>
        `)}
      </div>` : null}
    </div>
    ` : null}
    ${tab === 'report' ? html`
    <div style={{marginTop:"12px", padding:"20px 24px", background:"rgba(15,23,42,0.5)", border:"1px solid var(--empire-border)", borderRadius:12, lineHeight:1.8, fontSize:"13px"}}>
      ${report?.report ? report.report.split('\n').map((p,i) => html`<p key=${i} style={{marginBottom:12}}>${p}</p>`) : html`<div class="stub-body">No report generated yet.</div>`}
      ${report?.optimizations ? html`<div style={{marginTop:16}}><strong style={{color:"var(--signal-teal)"}}>Optimizations:</strong><ul>${report.optimizations.map((o,i) => html`<li key=${i} style={{marginTop:6}}>${o}</li>`)}</ul></div>` : null}
      ${report?.timestamp ? html`<div style={{marginTop:16, fontSize:"9px", color:"var(--empire-fog)", fontFamily:"var(--font-mono)"}}>Generated: ${report.timestamp}</div>` : null}
    </div>
    ` : null}
  `;
}



// ── PSYCHOLOGY DASHBOARD ──────────────────────────────────────────────────────
function PsychologyDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('mindmap');
  const [billData, setBillData] = useState(null);
  const [detectText, setDetectText] = useState('');
  
  const [billingData, setBillingData] = useState(null);
  const [billingErr, setBillingErr] = useState(null);
  const [billTimeseries, setBillTimeseries] = useState(null);const [billWindow, setBillWindow] = useState("30d");
      const [chartMode, setChartMode] = useState("stacked");const [detectResult, setDetectResult] = useState(null);

  useEffect(() => {
    apiFetch('/api/psychology/snapshot')
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  // Fetch billing summary
  useEffect(() => {
    let stop = false;
    const load = () => {
      apiFetch('/api/v1/billing/summary').then(r => r.json())
        .then(d => { if (!stop) setBillData(d); })
        .catch(e => { if (!stop) console.error('billing:', e); });
    };
    load();
    const t = setInterval(load, 30000);
    return () => { stop = true; clearInterval(t); };
  }, []);

  if (loading) return html`<div class="body"><div class="psy-loading">Loading psychology data...</div></div>`;
  if (error) return html`<div class="body"><div class="psy-error">Error: ${error}</div></div>`;
  if (!data) return html`<div class="body"><div class="psy-error">No data</div></div>`;

  const mm = data.mind_map || { nodes: [], edges: [], summary: {} };
  const eff = data.effectiveness || {};
  const nodes = mm.nodes || [];
  const summary = mm.summary || {};
  const nicheNodes = nodes.filter(n => n.type === 'niche');
  const personaNodes = nodes.filter(n => n.type === 'persona');
  const principleNodes = nodes.filter(n => n.type === 'principle');

  const detectPersona = async () => {
    if (!detectText.trim()) return;
    try {
      const res = await apiFetch('/api/psychology/detect-persona?text=' + encodeURIComponent(detectText.trim()));
      setDetectResult(res);
    } catch(e) {
      setDetectResult({ persona: 'error', confidence: 0, error: e.message });
    }
  };

  return html`
    <div class="body">
      <div class="section-h">
        <div>
          <div class="section-title">Sales <em>Psychology</em> Mind Map</div>
          <div class="section-sub">Persuasion principles &middot; Buyer personas &middot; Niche psychology</div>
        </div>
      </div>

      <div class="pulse-tabs">
        <button class="pulse-tab ${activeTab === 'mindmap' ? 'active' : ''}" onClick=${() => setActiveTab('mindmap')}>Mind Map</button>
        <button class="pulse-tab ${activeTab === 'personas' ? 'active' : ''}" onClick=${() => setActiveTab('personas')}>Personas</button>
        <button class="pulse-tab ${activeTab === 'principles' ? 'active' : ''}" onClick=${() => setActiveTab('principles')}>Principles</button>
        <button class="pulse-tab ${activeTab === 'detect' ? 'active' : ''}" onClick=${() => setActiveTab('detect')}>Detect</button>
        <button class="pulse-tab ${activeTab === 'niches' ? 'active' : ''}" onClick=${() => setActiveTab('niches')}>Niche Profiles</button>
        <button class="pulse-tab ${activeTab === 'billing' ? 'active' : ''}" onClick=${() => setActiveTab('billing')}>Billing</button>
        <button class="pulse-tab ${activeTab === 'billing' ? 'active' : ''}" onClick=${() => setActiveTab('billing')}>Billing</button>
      </div>

      ${activeTab === 'mindmap' && html`
        <div class="psy-summary-grid">
          <div class="stat-card"><div class="stat-label">Niches</div><div class="stat-value teal">${summary.niches || 0}</div></div>
          <div class="stat-card"><div class="stat-label">Personas</div><div class="stat-value cyan">${summary.personas || 0}</div></div>
          <div class="stat-card"><div class="stat-label">Principles</div><div class="stat-value">${summary.principles || 0}</div></div>
          <div class="stat-card"><div class="stat-label">Techniques</div><div class="stat-value teal">${summary.techniques || 0}</div></div>
          <div class="stat-card"><div class="stat-label">Nodes</div><div class="stat-value dim">${summary.total_nodes || 0}</div></div>
          <div class="stat-card"><div class="stat-label">Connections</div><div class="stat-value dim">${summary.total_edges || 0}</div></div>
          <div class="stat-card"><div class="stat-label">Combos Tracked</div><div class="stat-value cyan">${eff.total_combinations_tracked || 0}</div></div>
          <div class="stat-card"><div class="stat-label">Conv Rate</div><div class="stat-value teal">${eff.overall_conversion_rate ? (eff.overall_conversion_rate * 100).toFixed(1) + '%' : 0}</div></div>
        </div>

        <div class="chart-panel">
          <div class="chart-panel-h"><span class="chart-panel-title">Psychology Flow Map</span><span class="chart-panel-tag">Niche &rarr; Persona &rarr; Principle &rarr; Technique</span></div>
          <div class="psy-flow-grid">
            ${edges.slice(0, 60).map(e => html`<div class="psy-flow-card" key=${e.source}>${e.source}&rarr;${e.target}</div>`)}
          </div>
        </div>
      `}

      ${activeTab === 'personas' && html`
        <div class="psy-persona-grid">
          ${personaNodes.map(p => html`
            <div class="psy-persona-card" key=${p.id}>
              <div class="psy-persona-head"><div class="psy-persona-name">${p.label}</div><div class="psy-persona-sub">${p.subtitle}</div></div>
              <div class="psy-persona-tone">Tone: ${p.metrics?.voice_tone || '—'}</div>
              <div class="psy-persona-dec">Style: ${p.metrics?.decision_style || '—'}</div>
            </div>
          `)}
        </div>
        ${personaNodes.length === 0 && html`<div class="stub-body">No persona data.</div>`}
      `}

      ${activeTab === 'principles' && html`
        <div class="psy-principle-list">
          ${principleNodes.map(p => html`
            <div class="psy-principle-card" key=${p.id}>
              <div class="psy-principle-name">${p.label}</div>
              <div class="psy-principle-cat">${p.subtitle}</div>
              <div class="psy-principle-tactics">${p.metrics?.tactic_count || 0} tactics</div>
            </div>
          `)}
        </div>
      `}

      ${activeTab === 'detect' && html`
        <div class="chart-panel">
          <div class="chart-panel-h"><span class="chart-panel-title">Persona Detection</span><span class="chart-panel-tag">Detect buyer persona from lead text</span></div>
          <div class="fld">
            <label class="fld-lbl">Lead text or objection</label>
            <textarea class="fld-in psy-detect-input" rows="3" placeholder="Paste lead text, objection, or transcript..." value=${detectText} onInput=${(e) => setDetectText(e.target.value)}></textarea>
          </div>
          <button class="btn" onClick=${detectPersona} disabled=${!detectText.trim()}>Detect Persona</button>
          ${detectResult && html`
            <div class="psy-detect-result">
              <div class="psy-detect-top">
                <span class="psy-detect-label">Detected: <strong>${detectResult.label || detectResult.persona}</strong></span>
                <span class="psy-detect-conf">Confidence: ${(detectResult.confidence * 100).toFixed(0)}%</span>
              </div>
              ${detectResult.recommended_approach && html`
                <div class="psy-detect-detail">
                  <div class="psy-detect-detail-row">Closer: ${detectResult.recommended_approach.best_closer_persona.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</div>
                  <div class="psy-detect-detail-row">Tone: ${detectResult.recommended_approach.script_tone}</div>
                  <div class="psy-detect-detail-row">Style: ${detectResult.recommended_approach.decision_style}</div>
                  <div class="psy-detect-pills">
                    ${(detectResult.recommended_approach.top_principles || []).slice(0, 3).map(p => html`<span class="psy-detect-pill">${p.principle_name}</span>`)}
                  </div>
                </div>
              `}
            </div>
          `}
        </div>
      `}

      ${activeTab === 'niches' && html`
        <div class="psy-niche-grid">
          ${nicheNodes.map(n => html`
            <div class="psy-niche-card" key=${n.id}>
              <div class="psy-niche-name">${n.label}</div>
              <div class="psy-niche-meta">${n.subtitle}</div>
              <div class="psy-niche-speed">Speed: ${n.metrics?.decision_speed || '—'}</div>
              <div class="psy-niche-price">Price sensitivity: ${n.metrics?.price_sensitivity || '—'}</div>
            </div>
          `)}
        </div>
        ${nicheNodes.length === 0 && html`<div class="stub-body">No niche profiles.</div>

      ${activeTab === 'billing' && html`
                ${billingErr ? html`<div class="bill-error">⚠ ${billingErr}</div>` : ''}
        ${!billingErr && !billingData ? html`<div class="bill-loading">Loading billing data…</div>` : ''}
        ${billingData ? html`
        <div class="psy-summary-grid">
          <div class="stat-card"><div class="stat-label">Today's Calls</div><div class="stat-value teal">${billingData?.calls_today ?? 0}</div></div>
          <div class="stat-card"><div class="stat-label">Today's Revenue</div><div class="stat-value dollar teal">${(billingData?.revenue_today ?? 0).toFixed(2)}</div></div>
          <div class="stat-card"><div class="stat-label">Week Revenue</div><div class="stat-value dollar gold">${(billingData?.revenue_week ?? 0).toFixed(2)}</div></div>
          <div class="stat-card"><div class="stat-label">Month Revenue</div><div class="stat-value dollar green">${(billingData?.revenue_month ?? 0).toFixed(2)}</div></div>
        </div>

        <div class="bill-section-title">Call Breakdown by Source</div>
        <table class="bill-table">
          <thead><tr><th>Source</th><th>Calls</th><th class="num">Net Payout</th><th class="num">Fees</th><th class="num">Qualified</th></tr></thead>
          <tbody>
            ${billingData?.by_source?.length > 0 ? billingData.by_source.map(s => html`
              <tr><td>${s.source}</td><td>${s.calls}</td><td class="num">$${s.net_payout.toFixed(2)}</td><td class="num">$${s.fees.toFixed(2)}</td><td class="num">${s.qualified}</td></tr>
            `).join('') : '<tr><td colspan="8" style="color:var(--empire-mist);text-align:center;padding:20px">No calls today</td></tr>'}
          </tbody>
        </table>

        <div class="bill-section-title">Top Calls by Payout</div>
        <table class="bill-table">
          <thead><tr><th>Buyer</th><th>Niche</th><th class="num">Duration</th><th class="num">Net Payout</th><th class="num">Settlement</th><th class="num">Per-Min</th><th class="num">Fee</th><th>Model</th></tr></thead>
          <tbody>
            ${billingData?.top_calls?.length > 0 ? billingData.top_calls.map(c => html`
              <tr><td>${c.buyer_name || c.source}</td><td>${c.niche || '-'}</td><td class="num">${c.duration || 0}s</td><td class="num">$${(c.net_payout || 0).toFixed(2)}</td><td class="num">$${(c.settlement_fee || 0).toFixed(2)}</td><td class="num">$${(c.per_minute_fee || 0).toFixed(2)}</td><td class="num">$${(c.fee || 0).toFixed(2)}</td><td class="num">${c.fee_model === 'per_minute' ? '⏱ Per-Min' : '📋 Settlement'}</td></tr>
            `).join('') : '<tr><td colspan="8" style="color:var(--empire-mist);text-align:center;padding:20px">No calls today</td></tr>'}
          </tbody>
        </table>
      `}
` : ''}
      `}
      `}
    </div>
  `;
}

function SelfAwarenessDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [narrative, setNarrative] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [view, setView] = useState('graph');
  const [liveConnected, setLiveConnected] = useState(false);
  const narrativeRef = useRef(null);
  const decisionsRef = useRef(null);

  // Initial fetch
  useEffect(() => {
    apiFetch('/api/self-awareness/snapshot')
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  // WebSocket subscription for live events
  useEffect(() => {
    const onConnect = () => setLiveConnected(true);
    const onDisconnect = () => setLiveConnected(false);
    const onStats = e => { addThought(e, 'stats'); };
    const onAny = e => {
      if (e.type && e.type !== 'stats' && e.type !== 'hello' && e.type !== 'pong') {
        addDecision(e);
      }
    };
    function addThought(e, type) {
      const ts = (e && e.ts && e.ts.slice) ? e.ts.slice(11, 19) : new Date().toLocaleTimeString();
      setNarrative(prev => {
        const next = [...prev, { ts, type: type || e.type || 'event', data: e }];
        return next.slice(-100);
      });
    }
    function addDecision(e) {
      const ts = (e && e.ts && e.ts.slice) ? e.ts.slice(11, 19) : new Date().toLocaleTimeString();
      setDecisions(prev => {
        const next = [...prev, { ts, event: e }];
        return next.slice(-50);
      });
    }
    function subscribeLive() {
      setLiveConnected(true);
      window.EMPIRE_LIVE.on('stats', onStats);
      window.EMPIRE_LIVE.on('*', onAny);
      window.EMPIRE_LIVE.on('connect', onConnect);
      window.EMPIRE_LIVE.on('disconnect', onDisconnect);
    }
    function unsubscribeLive() {
      window.EMPIRE_LIVE.off('stats', onStats);
      window.EMPIRE_LIVE.off('*', onAny);
      window.EMPIRE_LIVE.off('connect', onConnect);
      window.EMPIRE_LIVE.off('disconnect', onDisconnect);
    }
    if (typeof window !== 'undefined' && window.EMPIRE_LIVE) {
      subscribeLive();
      return unsubscribeLive;
    }
    const check = setInterval(() => {
      if (window.EMPIRE_LIVE) {
        clearInterval(check);
        subscribeLive();
      }
    }, 500);
    setTimeout(() => clearInterval(check), 10000);
    return () => { clearInterval(check); if (window.EMPIRE_LIVE) unsubscribeLive(); };
  }, []);

  // Auto-scroll (only if user is near bottom)
  function isNearBottom(ref) {
    if (!ref.current) return true;
    const el = ref.current;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }
  useEffect(() => {
    if (narrativeRef.current && isNearBottom(narrativeRef)) {
      narrativeRef.current.scrollTop = narrativeRef.current.scrollHeight;
    }
  }, [narrative]);
  useEffect(() => {
    if (decisionsRef.current && isNearBottom(decisionsRef)) {
      decisionsRef.current.scrollTop = decisionsRef.current.scrollHeight;
    }
  }, [decisions]);

  if (loading) return html`<div class="body"><div class="sa-think-label"><span class="sa-live-dot"></span> System is thinking<div class="sa-think-dots"><span class="sa-think-dot"></span><span class="sa-think-dot"></span><span class="sa-think-dot"></span></div></div></div>`;
  if (error) return html`<div class="body"><div class="sa-empty">Error: ${error}</div></div>`;
  if (!data) return html`<div class="body"><div class="sa-empty">No data</div></div>`;

  const model = data.system_model || {};
  const health = model.health || {};
  const agents = model.agents || [];
  const deps = model.dependencies || {};
  const caps = model.capabilities || {};
  const lanes = model.lanes || {};
  const revenue = model.revenue || {};
  const anomalies = data.anomalies || [];
  const narr = data.narrative || {};
  const ts = data.ts || '';

  const agentTotal = health.agent_total || agents.length;
  const agentHealthy = health.agent_healthy || 0;
  const healthPct = agentTotal > 0 ? Math.round((agentHealthy / agentTotal) * 100) : 0;
  const healthColor = healthPct >= 80 ? 'teal' : healthPct >= 50 ? 'amber' : 'red';
  const staleCount = (health.stale_agents || []).length;
  const criticalCount = (health.critical_agents || []).length;
  const winRate = lanes.overall_win_rate;
  const rev24h = revenue.total_revenue_24h || 0;
  const anomalyCount = data.anomaly_count || 0;
  const critAnomalies = data.critical_count || 0;
  const improveCount = data.improvement_count || 0;

  // Build graph nodes (position agents in concentric rings)
  const agentNames = Object.keys(deps).length > 0 ? Object.keys(deps) : agents.map(a => a.name);
  const centerIdx = agentNames.indexOf('hub');
  const center = centerIdx >= 0 ? agentNames[centerIdx] : (agentNames[0] || '');
  const ring1 = center ? (deps[center] || []) : [];
  const ring2 = agentNames.filter(n => n !== center && !ring1.includes(n));

  function graphX(i, total, radius, cx) { return cx + radius * Math.cos((2 * Math.PI * i) / total - Math.PI / 2); }
  function graphY(i, total, radius, cy) { return cy + radius * Math.sin((2 * Math.PI * i) / total - Math.PI / 2); }

  const CX = 300, CY = 170;
  const RADII = [0, 120, 220];

  function getAgent(name) { return agents.find(a => a.name === name) || { name, status: 'UNKNOWN', capabilities: '' }; }

  function agentStatusColor(status) {
    if (status === 'ACTIVE' || status === 'online') return '#44E5B8';
    if (status === 'STALE' || status === 'IDLE') return '#FFB800';
    if (status === 'CRITICAL' || status === 'UNREGISTERED') return '#FF4444';
    return '#64748b';
  }

  function agentNode(name, cx, cy, r) {
    const a = getAgent(name);
    const status = a.status;
    const color = agentStatusColor(status);
    const isSelected = selectedAgent === name;
    return html`<g class="sa-graph-node ${isSelected ? 'active' : ''}" onClick=${() => setSelectedAgent(name === selectedAgent ? null : name)} transform="translate(${cx - r}, ${cy - 8})">
      <rect class="sa-graph-rect" width="${r * 2}" height="16" rx="4" style="stroke:${color};${isSelected ? 'fill:rgba(' + (color === '#44E5B8' ? '68,229,184' : color === '#FFB800' ? '255,184,0' : '255,68,68') + ',0.08)' : ''}"/>
      <text class="sa-graph-text" x="${r}" y="11">${name.length > 10 ? name.slice(0, 10) + '..' : name}</text>
      <circle cx="4" cy="4" r="2" fill="${color}" style="${status === 'ACTIVE' ? 'animation:sa-node-pulse 2s ease-in-out infinite;filter:drop-shadow(0 0 4px ' + color + ')' : ''}"/>
    </g>`;
  }

  // Build edges from dependency graph
  const edges = [];
  for (const [agent, depList] of Object.entries(deps)) {
    for (const dep of depList) {
      edges.push({ from: dep, to: agent });
    }
  }

  // Build narrative from data
  const initialThoughts = [
    { ts: ts ? ts.slice(11, 19) : '--', type: 'info', icon: '●', body: `System <em>${health.overall || 'unknown'}</em> · ${agentHealthy}/${agentTotal} agents healthy · ${staleCount} stale, ${criticalCount} critical` },
  ];
  if (anomalies.length > 0) {
    initialThoughts.push({ ts: '--', type: anomalies[0].severity === 'critical' ? 'critical' : 'warn', icon: anomalies[0].severity === 'critical' ? '⚠' : '▲', body: anomalies[0].message });
  }
  if (improveCount > 0) {
    initialThoughts.push({ ts: '--', type: 'info', icon: '●', body: `<strong>${improveCount}</strong> improvement suggestions available` });
  }

  const allThoughts = [...initialThoughts, ...narrative];

  return html`
    <div class="body">
      <div class="section-h">
        <div>
          <div class="section-title"><em>Claude OS</em> · Self-Awareness</div>
          <div class="section-sub">Live system model · Narrative · Dependency graph · Decisions</div>
        </div>
        <div style="display:flex;align-items:center;gap:14px">
          <span class="${liveConnected ? 'sa-live-dot' : 'sa-live-dot paused'}"></span>
          <span style="font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.08em">${liveConnected ? 'LIVE' : 'OFFLINE'}</span>
          <button class="pulse-tab ${view === 'graph' ? 'active' : ''}" onClick=${() => setView('graph')} style="font-size:10px;padding:6px 14px">Graph</button>
          <button class="pulse-tab ${view === 'feed' ? 'active' : ''}" onClick=${() => setView('feed')} style="font-size:10px;padding:6px 14px">Narrative</button>
        </div>
      </div>

      <!-- Status bar -->
      <div class="sa-status">
        <div class="sa-stat-card">
          <div class="sa-stat-row">
            <span class="sa-stat-label">Health</span>
          </div>
          <div class="sa-stat-val ${healthColor}">${healthPct}%</div>
          <div class="sa-stat-meta">${health.overall || 'unknown'} · ${agentHealthy}/${agentTotal} agents</div>
        </div>
        <div class="sa-stat-card">
          <div class="sa-stat-row">
            <span class="sa-stat-label">Win Rate</span>
            <span style="font-size:9px;color:var(--empire-fog)">${lanes.active || 0} lanes</span>
          </div>
          <div class="sa-stat-val ${winRate >= 0.6 ? 'teal' : winRate >= 0.3 ? 'amber' : 'red'}">${winRate != null ? (winRate * 100).toFixed(0) + '%' : '--'}</div>
          <div class="sa-stat-meta">${lanes.total_runs || 0} runs · ${lanes.evolutions_run || 0} evolutions</div>
        </div>
        <div class="sa-stat-card">
          <div class="sa-stat-row">
            <span class="sa-stat-label">Revenue</span>
          </div>
          <div class="sa-stat-val teal">${rev24h > 0 ? '$' + rev24h.toLocaleString() : '--'}</div>
          <div class="sa-stat-meta">24h · ${revenue.total_revenue_7d > 0 ? '$' + revenue.total_revenue_7d.toLocaleString() + ' 7d' : 'no data'}</div>
        </div>
        <div class="sa-stat-card">
          <div class="sa-stat-row">
            <span class="sa-stat-label">Anomalies</span>
            <span style="font-size:9px;color:var(--empire-fog)">${improveCount} improvements</span>
          </div>
          <div class="sa-stat-val ${critAnomalies > 0 ? 'red' : anomalyCount > 0 ? 'amber' : 'teal'}">${anomalyCount}</div>
          <div class="sa-stat-meta">${critAnomalies > 0 ? critAnomalies + ' critical' : 'no critical issues'}</div>
        </div>
      </div>

      ${view === 'graph' ? html`
        <!-- Main content: graph + narrative + decisions -->
        <div class="sa-wrapper">
          <!-- LEFT: Agent dependency graph -->
          <div class="sa-panel">
            <div class="sa-panel-h">
              <strong>Agent Dependency Graph</strong>
              <span>${agentNames.length} nodes · ${edges.length} edges</span>
            </div>
            <div class="sa-panel-body" style="padding:0">
              <div class="sa-graph-wrap">
                <svg class="sa-graph-svg" viewBox="0 0 600 340">
                  <!-- Center glow -->
                  <circle cx="${CX}" cy="${CY}" r="180" class="sa-graph-ring"/>
                  <circle cx="${CX}" cy="${CY}" r="120" class="sa-graph-ring"/>
                  <circle cx="${CX}" cy="${CY}" r="60" class="sa-graph-ring"/>
                  <circle cx="${CX}" cy="${CY}" r="30" class="sa-graph-center-dot"/>
                  
                  <!-- Edges -->
                  ${edges.map((e, i) => {
                    const fromIdx = agentNames.indexOf(e.from);
                    const toIdx = agentNames.indexOf(e.to);
                    if (fromIdx < 0 || toIdx < 0) return '';
                    const fromRing = e.from === center ? 0 : ring1.includes(e.from) ? 1 : 2;
                    const toRing = e.to === center ? 0 : ring1.includes(e.to) ? 1 : 2;
                    let fromCx, fromCy, toCx, toCy;
                    if (fromRing === 0) { fromCx = CX; fromCy = CY; }
                    else {
                      const group = fromRing === 1 ? ring1 : ring2;
                      const idx = group.indexOf(e.from);
                      if (idx < 0) return '';
                      fromCx = graphX(idx, group.length, RADII[fromRing], CX);
                      fromCy = graphY(idx, group.length, RADII[fromRing], CY);
                    }
                    if (toRing === 0) { toCx = CX; toCy = CY; }
                    else {
                      const group = toRing === 1 ? ring1 : ring2;
                      const idx = group.indexOf(e.to);
                      if (idx < 0) return '';
                      toCx = graphX(idx, group.length, RADII[toRing], CX);
                      toCy = graphY(idx, group.length, RADII[toRing], CY);
                    }
                    return html`<line x1="${fromCx}" y1="${fromCy}" x2="${toCx}" y2="${toCy}" class="sa-graph-edge ${e.from === center || e.to === center ? 'active' : ''}"/>`;
                  })}
                  
                  <!-- Nodes -->
                  ${agentNames.map((name, i) => {
                    if (name === center) {
                      return agentNode(name, CX - 50, CY - 8, 50);
                    } else if (ring1.includes(name)) {
                      const idx = ring1.indexOf(name);
                      const x = graphX(idx, ring1.length, RADII[1], CX);
                      const y = graphY(idx, ring1.length, RADII[1], CY);
                      return agentNode(name, x - 36, y - 8, 36);
                    } else {
                      const idx = ring2.indexOf(name);
                      if (idx < 0) return '';
                      const x = graphX(idx, ring2.length, RADII[2], CX);
                      const y = graphY(idx, ring2.length, RADII[2], CY);
                      return agentNode(name, x - 32, y - 8, 32);
                    }
                  })}
                </svg>
              </div>
              
              <!-- Agent detail panel -->
              ${selectedAgent ? (() => {
                const a = getAgent(selectedAgent);
                const depsList = deps[selectedAgent] || [];
                const dependedBy = agentNames.filter(n => (deps[n] || []).includes(selectedAgent));
                return html`<div class="sa-agent-detail">
                  <div class="sa-agent-detail-h">
                    <div class="sa-agent-detail-name"><span style="color:${agentStatusColor(a.status)}">●</span> ${selectedAgent}</div>
                    <button class="sa-agent-detail-close" onClick=${() => setSelectedAgent(null)}>✕</button>
                  </div>
                  <div class="sa-agent-detail-body">
                    <div class="sa-agent-detail-grid">
                      <div class="sa-agent-detail-field"><span class="lbl">Status</span><span class="val" style="color:${agentStatusColor(a.status)}">${a.status}</span></div>
                      <div class="sa-agent-detail-field"><span class="lbl">Ping</span><span class="val">${a.last_ping ? new Date(a.last_ping).toLocaleString() : 'never'}</span></div>
                      <div class="sa-agent-detail-field" style="grid-column:1/-1"><span class="lbl">Capabilities</span><span class="val">${a.capabilities || caps[selectedAgent] || 'none'}</span></div>
                      <div class="sa-agent-detail-field"><span class="lbl">Depends On</span><span class="val">${depsList.length ? depsList.join(', ') : 'none'}</span></div>
                      <div class="sa-agent-detail-field"><span class="lbl">Depended By</span><span class="val">${dependedBy.length ? dependedBy.join(', ') : 'none'}</span></div>
                    </div>
                  </div>
                </div>`;
              })() : ''}
            </div>
          </div>

          <!-- RIGHT: Live narrative + decisions -->
          <div style="display:flex;flex-direction:column;gap:12px">
            <!-- Narrative feed -->
            <div class="sa-panel" style="flex:1">
              <div class="sa-panel-h">
                <strong>Live Narrative</strong>
                <span>${allThoughts.length} events</span>
              </div>
              <div class="sa-narrative-feed" ref=${narrativeRef}>
                ${allThoughts.length === 0 ? html`<div class="sa-empty">Awaiting system signals...</div>` : ''}
                ${allThoughts.map(t => html`
                  <div class="sa-thought">
                    <span class="sa-thought-ts">${t.ts}</span>
                    <span class="sa-thought-type ${t.type}">${t.icon || t.type}</span>
                    <span class="sa-thought-body">${t.body}</span>
                  </div>
                `)}
                <span class="sa-cursor"></span>
              </div>
            </div>

            <!-- Decision trace feed -->
            <div class="sa-panel" style="flex:0 0 auto;max-height:200px">
              <div class="sa-panel-h">
                <strong>Decision Trace</strong>
                <span>${decisions.length} live events</span>
              </div>
              <div class="sa-decision-feed" ref=${decisionsRef}>
                ${decisions.length === 0 ? html`<div class="sa-empty">No live events yet. Connect to WebSocket to see real-time decisions.</div>` : ''}
                ${decisions.map(d => html`
                  <div class="sa-decision">
                    <span class="sa-decision-ts">${d.ts}</span>
                    <span class="sa-decision-body">
                      <span class="key">${d.event.type}</span>
                      ${Object.entries(d.event).filter(([k]) => k !== 'type' && k !== 'ts').slice(0, 3).map(([k, v]) => html` <span class="key">${k}:</span> <span class="val">${typeof v === 'object' ? JSON.stringify(v).slice(0, 40) : String(v).slice(0, 40)}</span>`).join('')}
                    </span>
                  </div>
                `)}
              </div>
            </div>
          </div>
        </div>
      ` : html`
        <!-- Narrative-only view -->
        <div class="sa-panel" style="min-height:400px">
          <div class="sa-panel-h">
            <strong>System Narrative Stream</strong>
            <span>${allThoughts.length} events · ${narrative.length} live</span>
          </div>
          <div class="sa-narrative-feed" ref=${narrativeRef} style="max-height:70vh">
            ${allThoughts.map(t => html`
              <div class="sa-thought">
                <span class="sa-thought-ts">${t.ts}</span>
                <span class="sa-thought-type ${t.type}">${t.icon || t.type}</span>
                <span class="sa-thought-body">${t.body}</span>
              </div>
            `)}
            <span class="sa-cursor"></span>
          </div>
        </div>
      `}
    </div>
  `;
}

function AgentOSDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('overview');
  const [actioning, setActioning] = useState({});
  const [actionError, setActionError] = useState(null);

  async function fetchStatus() {
    try {
      const res = await apiFetch('/api/agent-os/status');
      if (!res.ok) { setError('Failed to load'); setLoading(false); return; }
      const d = await res.json();
      setData(d);
    } catch (e) { setError(e.message); }
    setLoading(false);
  }

  async function actionAgent(name, action) {
    setActionError(null);
    setActioning(prev => ({ ...prev, [name]: action }));
    try {
      const r = await apiFetch(`/api/agent-os/agents/${name}/${action}`, { method: 'POST' });
      if (!r.ok) { throw new Error(await r.text()); }
      // Re-fetch to reflect new status
      const res = await apiFetch('/api/agent-os/status');
      if (res.ok) setData(await res.json());
    } catch (e) {
      setActionError(action + ' ' + name + ': ' + (e.message || e).slice(0, 60));
    }
    setActioning(prev => ({ ...prev, [name]: null }));
  }

  useEffect(() => { fetchStatus(); }, []);

  if (loading) return html`<div class="body"><div class="psy-loading">Loading Agent OS data...</div></div>`;
  if (error) return html`<div class="body"><div class="psy-error">Error: ${error}</div></div>`;
  if (!data) return html`<div class="body"><div class="psy-error">No data</div></div>`;

  const proc = data.processes || {};
  const ipc = data.ipc || {};
  const caps = data.capabilities || {};
  const k = data.kernel || {};
  const agents = proc.agents || {};
  const agentList = Object.entries(agents);

  const healthPct = proc.total_agents > 0 ? Math.round((proc.running / proc.total_agents) * 100) : 0;

  return html`
    <div class="body">
      ${actionError ? html`<div style="margin-bottom:14px;padding:10px 16px;background:rgba(255,68,68,0.06);border:1px solid rgba(255,68,68,0.25);border-radius:6px;font-family:var(--font-mono);font-size:10px;color:var(--status-red);display:flex;align-items:center;gap:8px">
        <span>⚠</span><span>${actionError}</span>
        <button style="margin-left:auto;background:none;border:none;color:var(--status-red);cursor:pointer;font-size:14px" onClick=${() => setActionError(null)}>×</button>
      </div>` : ''}
      <div class="section-h">
        <div class="section-title"><em>Agent OS</em></div>
        <div class="section-sub">Kernel · Process manager · IPC bus · Capability registry · Boot protocol</div>
      </div>

      <div class="pulse-tabs">
        <button class="pulse-tab ${tab === 'overview' ? 'active' : ''}" onClick=${() => setTab('overview')}>Overview</button>
        <button class="pulse-tab ${tab === 'agents' ? 'active' : ''}" onClick=${() => setTab('agents')}>Agents</button>
        <button class="pulse-tab ${tab === 'ipc' ? 'active' : ''}" onClick=${() => setTab('ipc')}>IPC Bus</button>
        <button class="pulse-tab ${tab === 'capabilities' ? 'active' : ''}" onClick=${() => setTab('capabilities')}>Capabilities</button>
        <button class="pulse-tab ${tab === 'boot' ? 'active' : ''}" onClick=${() => setTab('boot')}>Boot</button>
      </div>

      ${tab === 'overview' ? html`
        <div class="psy-summary-grid">
          <div class="cpl-card">
            <div class="cpl-card-label">Booted</div>
            <div class="cpl-card-value ${k.booted ? 'positive' : 'warning'}">${k.booted ? 'YES' : 'NO'}</div>
          </div>
          <div class="cpl-card">
            <div class="cpl-card-label">Agents</div>
            <div class="cpl-card-value">${proc.total_agents || 0}</div>
          </div>
          <div class="cpl-card">
            <div class="cpl-card-label">Running</div>
            <div class="cpl-card-value positive">${proc.running || 0}</div>
          </div>
          <div class="cpl-card">
            <div class="cpl-card-label">Health</div>
            <div class="cpl-card-value ${healthPct >= 80 ? 'positive' : healthPct >= 50 ? 'warning' : ''}">${healthPct}%</div>
          </div>
          <div class="cpl-card">
            <div class="cpl-card-label">Error</div>
            <div class="cpl-card-value ${proc.error > 0 ? 'warning' : ''}">${proc.error || 0}</div>
          </div>
          <div class="cpl-card">
            <div class="cpl-card-label">IPC Events</div>
            <div class="cpl-card-value">${ipc.total_events_tracked || 0}</div>
          </div>
          <div class="cpl-card">
            <div class="cpl-card-label">Capabilities</div>
            <div class="cpl-card-value">${(caps.total_capabilities) || 0}</div>
          </div>
          <div class="cpl-card">
            <div class="cpl-card-label">Uptime</div>
            <div class="cpl-card-value positive">${k.uptime_seconds ? Math.round(k.uptime_seconds / 60) + 'm' : '0m'}</div>
          </div>
        </div>
        <div class="cpl-health-meta" style="margin-top: 8px; text-align: center;">
          Boot order: ${(proc.boot_order || []).slice(0, 10).join(' → ')}${(proc.boot_order || []).length > 10 ? ' …' : ''}
        </div>
      ` : ''}

      ${tab === 'agents' ? html`
        <div class="cpl-service-summary" style="margin-bottom: 14px;">
          <span class="cpl-service-count">${agentList.length}</span>
          <span class="cpl-service-label">agents registered</span>
        </div>
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
          <span class="cpl-service-count">${agentList.length}</span>
          <span class="cpl-service-label">agents registered</span>
          <button class="gh-refresh-btn" style="margin-left:auto" onClick=${() => fetchStatus()}>Refresh</button>
        </div>
        <table class="cpl-table">
          <thead><tr><th>Agent</th><th>Status</th><th>Interval</th><th>Priority</th><th>Capabilities</th><th>Dependencies</th><th>Retries</th><th>Actions</th></tr></thead>
          <tbody>
            ${agentList.map(([name, a]) => {
              const busy = actioning[name];
              const running = a.status === 'RUNNING';
              const isErr = a.status === 'ERROR';
              return html`<tr key=${name} class="${busy ? 'af-card stale' : ''}">
              <td style="font-weight: 500;">${name}</td>
              <td><span class="hth-dot ${running ? 'green' : isErr ? 'red' : 'amber'}"></span> ${a.status}</td>
              <td style="font-family: var(--font-mono);">${a.interval || '-'}s</td>
              <td>${a.priority || '-'}</td>
              <td style="color: var(--empire-mist); font-size: 10px;">${(a.capabilities || []).join(', ')}</td>
              <td style="color: var(--empire-mist); font-size: 10px;">${(a.dependencies || []).join(', ') || '-'}</td>
              <td>${a.retry_count || 0}/${a.max_retries || 3}</td>
              <td style="white-space:nowrap">
                ${!running ? html`<button class="tbl-action go" disabled=${!!busy} onClick=${() => actionAgent(name, 'start')}>${busy === 'start' ? '...' : 'Start'}</button>` : ''}
                ${running ? html`<button class="tbl-action" disabled=${!!busy} onClick=${() => actionAgent(name, 'stop')}>${busy === 'stop' ? '...' : 'Stop'}</button>` : ''}
                <button class="tbl-action" disabled=${!!busy} onClick=${() => actionAgent(name, 'restart')}>${busy === 'restart' ? '...' : 'Restart'}</button>
              </td>
            </tr>`;
            })}
          </tbody>
        </table>
      ` : ''}

      ${tab === 'ipc' ? html`
        <div class="cpl-service-summary" style="margin-bottom: 14px;">
          <span class="cpl-service-count">${ipc.total_events_tracked || 0}</span>
          <span class="cpl-service-label">events tracked</span>
          <span style="margin-left: 16px; color: var(--empire-mist);">${Object.keys(ipc.subscriptions || {}).length} subscriptions</span>
        </div>
        <table class="cpl-table">
          <thead><tr><th>Event</th><th>Source</th><th>Priority</th><th>Time</th></tr></thead>
          <tbody>
            ${(ipc.recent_events || []).map(ev => html`<tr key=${ev.event_id}>
              <td style="font-weight: 500;">${ev.event_type}</td>
              <td style="color: var(--empire-mist);">${ev.source}</td>
              <td><span class="cpl-badge ${ev.priority === 'critical' ? 'ppc' : 'ppl'}">${ev.priority}</span></td>
              <td style="font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog);">${new Date(ev.ts).toLocaleTimeString()}</td>
            </tr>`)}
            ${(ipc.recent_events || []).length === 0 ? html`<tr><td colspan="4" style="color: var(--empire-mist); text-align: center; padding: 20px;">No events yet</td></tr>` : ''}
          </tbody>
        </table>
      ` : ''}

      ${tab === 'capabilities' ? html`
        <div class="cpl-service-summary" style="margin-bottom: 14px;">
          <span class="cpl-service-count">${caps.total_capabilities || 0}</span>
          <span class="cpl-service-label">capabilities across</span>
          <span class="cpl-service-total">${caps.total_agents || 0}</span>
          <span class="cpl-service-label">agents</span>
        </div>
        <table class="cpl-table">
          <thead><tr><th>Capability</th><th>Agents</th></tr></thead>
          <tbody>
            ${Object.entries(caps.by_capability || {}).sort().map(([cap, agentList]) => html`<tr key=${cap}>
              <td style="font-weight: 500;">${cap}</td>
              <td style="color: var(--empire-mist); font-size: 10px;">${agentList.join(', ')}</td>
            </tr>`)}
            ${Object.keys(caps.by_capability || {}).length === 0 ? html`<tr><td colspan="2" style="color: var(--empire-mist); text-align: center; padding: 20px;">No capabilities registered</td></tr>` : ''}
          </tbody>
        </table>
      ` : ''}

      ${tab === 'boot' ? html`
        <div class="cpl-service-summary" style="margin-bottom: 14px;">
          <span class="cpl-service-count">${(proc.boot_order || []).length}</span>
          <span class="cpl-service-label">agents in boot order</span>
        </div>
        <table class="cpl-table">
          <thead><tr><th>#</th><th>Agent</th><th>Status</th><th>Priority</th><th>Dependencies</th></tr></thead>
          <tbody>
            ${(proc.boot_order || []).map((name, i) => {
              const a = agents[name] || {};
              return html`<tr key=${name}>
                <td style="color: var(--empire-fog);">${i + 1}</td>
                <td style="font-weight: 500;">${name}</td>
                <td><span class="hth-dot ${a.status === 'RUNNING' ? 'green' : a.status === 'ERROR' ? 'red' : 'amber'}"></span> ${a.status || 'unknown'}</td>
                <td>${a.priority || '-'}</td>
                <td style="color: var(--empire-mist); font-size: 10px;">${(a.dependencies || []).join(', ') || '-'}</td>
              </tr>`;
            })}
          </tbody>
        </table>
      ` : ''}
    </div>
  `;
}

function BusinessPlannerDashboard() {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('overview');
  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch('/api/business-planner/plan');
        if (!res.ok) { setError('Failed to load'); setLoading(false); return; }
        const d = await res.json();
        setPlan(d);
      } catch (e) { setError(e.message); }
      setLoading(false);
    })();
  }, []);
  if (loading) return html`<div class="body"><div class="psy-loading">Generating business plan...</div></div>`;
  if (error) return html`<div class="body"><div class="psy-error">Error: ${error}</div></div>`;
  if (!plan) return html`<div class="body"><div class="psy-error">No plan data</div></div>`;
  const exec = plan.executive_summary || {};
  const niches = plan.niche_plans || [];
  const actions = plan.action_roadmap || [];
  const risks = plan.risk_assessment || {};
  const psych = plan.psychology_insights || {};
  const curr = exec.current_state || {};
  const targets = exec.targets || {};
  const criticalNiches = niches.filter(n => n.priority === 'critical');
  const highNiches = niches.filter(n => n.priority === 'high');
  const healthLabel = curr.health_label || 'unknown';
  return html`
    <div class="body">
      <div class="section-h">
        <div class="section-title"><em>Business Planner</em></div>
        <div class="section-sub">Quarterly plan · Niche actions · Resource allocation · Risk assessment · Roadmap</div>
      </div>
      <div class="pulse-tabs">
        <button class="pulse-tab ${tab === 'overview' ? 'active' : ''}" onClick=${() => setTab('overview')}>Overview</button>
        <button class="pulse-tab ${tab === 'niches' ? 'active' : ''}" onClick=${() => setTab('niches')}>Niches</button>
        <button class="pulse-tab ${tab === 'actions' ? 'active' : ''}" onClick=${() => setTab('actions')}>Actions</button>
        <button class="pulse-tab ${tab === 'risks' ? 'active' : ''}" onClick=${() => setTab('risks')}>Risks</button>
        <button class="pulse-tab ${tab === 'psychology' ? 'active' : ''}" onClick=${() => setTab('psychology')}>Psychology</button>
      </div>
      ${tab === 'overview' ? html`
        <div class="psy-summary-grid">
          <div class="cpl-card"><div class="cpl-card-label">Quarter</div><div class="cpl-card-value">${plan.quarter}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Health</div><div class="cpl-card-value ${healthLabel === 'excellent' ? 'positive' : healthLabel === 'critical' ? 'warning' : ''}">${curr.health_score || 0}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Current MRR</div><div class="cpl-card-value">$${curr.current_mrr || 0}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Target MRR</div><div class="cpl-card-value positive">$${targets.target_mrr || 0}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Win Rate</div><div class="cpl-card-value">${curr.overall_win_rate || 0}%</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Confidence</div><div class="cpl-card-value ${(exec.confidence_score || 0) >= 50 ? 'positive' : 'warning'}">${exec.confidence_score || 0}%</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Niches</div><div class="cpl-card-value">${niches.length}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Actions</div><div class="cpl-card-value">${actions.length}</div></div>
        </div>
        <div class="cpl-health-meta" style="margin-top: 8px;">
          ${plan.strategist_narrative ? html`<div style="font-size: 10px; color: var(--empire-mist); line-height: 1.6; padding: 8px 12px; background: var(--empire-elevated); border: 1px solid var(--empire-border); border-radius: 6px;">${plan.strategist_narrative}</div>` : ''}
        </div>
        <div style="margin-top: 16px;"><div class="cpl-card-label">Target Niches</div><div style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px;">
          ${targets.target_niches ? html`<span class="cpl-badge ppl">${targets.target_niches} niches</span>` : ''}
          ${targets.target_win_rate_pct ? html`<span class="cpl-badge ppc">${targets.target_win_rate_pct}% win rate</span>` : ''}
          ${targets.target_mrr ? html`<span class="cpl-badge service">$${targets.target_mrr} MRR</span>` : ''}
        </div></div>
      ` : ''}
      ${tab === 'niches' ? html`
        <div class="cpl-service-summary" style="margin-bottom: 14px;">
          <span class="cpl-service-count">${niches.length}</span><span class="cpl-service-label">niches planned</span>
          ${criticalNiches.length > 0 ? html`<span class="cpl-badge ppc">${criticalNiches.length} critical</span>` : ''}
          ${highNiches.length > 0 ? html`<span class="cpl-badge ppl">${highNiches.length} high</span>` : ''}
        </div>
        <table class="cpl-table"><thead><tr><th>Niche</th><th>Priority</th><th>Score</th><th>Verdict</th><th>Est. Monthly</th><th>Actions</th></tr></thead><tbody>
          ${niches.map(n => html`<tr key=${n.niche}>
            <td style="font-weight: 500;">${n.niche}</td>
            <td><span class="cpl-badge ${n.priority === 'critical' ? 'ppc' : n.priority === 'high' ? 'ppl' : ''}">${n.priority}</span></td>
            <td style="font-family: var(--font-mono);">${n.rank_rent_score}</td>
            <td style="color: var(--empire-mist); font-size: 10px;">${n.verdict}</td>
            <td style="font-family: var(--font-mono);">$${(n.current_monthly_revenue_est || 0).toLocaleString()}</td>
            <td>${(n.actions || []).length} actions</td>
          </tr>`)
          ${niches.length === 0 ? html`<tr><td colspan="6" style="text-align: center; color: var(--empire-mist); padding: 20px;">No niche plans generated</td></tr>` : ''}
        </tbody></table>
      ` : ''}
      ${tab === 'actions' ? html`
        <div class="cpl-service-summary" style="margin-bottom: 14px;">
          <span class="cpl-service-count">${actions.length}</span><span class="cpl-service-label">action items</span>
        </div>
        <table class="cpl-table"><thead><tr><th>ID</th><th>Action</th><th>Category</th><th>Priority</th><th>Timeline</th></tr></thead><tbody>
          ${actions.map(a => html`<tr key=${a.id}>
            <td style="font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog);">${a.id}</td>
            <td style="font-size: 10px;">${a.action.slice(0, 80)}${a.action.length > 80 ? '…' : ''}</td>
            <td style="color: var(--empire-mist); font-size: 10px;">${a.category}</td>
            <td><span class="cpl-badge ${a.priority === 'critical' ? 'ppc' : a.priority === 'high' ? 'ppl' : ''}">${a.priority}</span></td>
            <td style="font-family: var(--font-mono); font-size: 9px;">${a.timeline || '-'}</td>
          </tr>`)
          ${actions.length === 0 ? html`<tr><td colspan="5" style="text-align: center; color: var(--empire-mist); padding: 20px;">No action items generated</td></tr>` : ''}
        </tbody></table>
      ` : ''}
      ${tab === 'risks' ? html`
        <div class="cpl-service-summary" style="margin-bottom: 14px;">
          <span class="cpl-service-count">${risks.total_risks || 0}</span><span class="cpl-service-label">risks identified</span>
          ${risks.critical_risks > 0 ? html`<span class="cpl-badge ppc">${risks.critical_risks} critical</span>` : ''}
        </div>
        <table class="cpl-table"><thead><tr><th>Risk</th><th>Severity</th><th>Recommendation</th></tr></thead><tbody>
          ${(risks.risks || []).map(r => html`<tr key=${r.risk}>
            <td style="font-weight: 500; font-size: 10px;">${r.risk}</td>
            <td><span class="cpl-badge ${r.severity === 'critical' ? 'ppc' : 'ppl'}">${r.severity}</span></td>
            <td style="color: var(--empire-mist); font-size: 10px;">${r.recommended_action || '-'}</td>
          </tr>`)
          ${(risks.risks || []).length === 0 ? html`<tr><td colspan="3" style="text-align: center; color: var(--empire-mist); padding: 20px;">No risks</td></tr>` : ''}
        </tbody></table>
      ` : ''}
      ${tab === 'psychology' ? html`
        <div class="psy-summary-grid">
          <div class="cpl-card"><div class="cpl-card-label">Overall Conv.</div><div class="cpl-card-value ${psych.overall_conversion_rate >= 0.3 ? 'positive' : 'warning'}">${(psych.overall_conversion_rate * 100 || 0).toFixed(1)}%</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Attempts</div><div class="cpl-card-value">${psych.total_attempts || 0}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Successes</div><div class="cpl-card-value positive">${psych.total_successes || 0}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Combinations</div><div class="cpl-card-value">${psych.combinations_tracked || 0}</div></div>
        </div>
        <div style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap;">
          ${psych.best_persona ? html`<span class="cpl-badge service">Best persona: ${psych.best_persona}</span>` : ''}
          ${psych.best_principle ? html`<span class="cpl-badge ppl">Best principle: ${psych.best_principle}</span>` : ''}
          ${psych.best_niche ? html`<span class="cpl-badge ppc">Best niche: ${psych.best_niche}</span>` : ''}
        </div>
      ` : ''}
    </div>
  `;
}
function App() {



  const [operator, setOperator] = useState(null);
  const [bootError, setBootError] = useState(null);
  const [section, setSection] = useState(currentSection());
  const [collapsed, setCollapsed] = useState({});
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
        ${NAV_GROUPS.map(g => html`
      <div class="nav-group" key=${g.id}>
        <button type="button" class=${"nav-group-header " + (collapsed[g.id] === undefined ? (g.defaultOpen ? '' : 'collapsed') : (collapsed[g.id] ? 'collapsed' : ''))}
                onClick=${() => setCollapsed({...collapsed, [g.id]: collapsed[g.id] === undefined ? !g.defaultOpen : !collapsed[g.id]})}>
          <span class="nav-group-icon">${g.icon}</span>
          <span class="nav-group-label">${g.label}</span>
          <span class="nav-group-count">${g.items.length}</span>
          <span class="nav-group-chevron">▼</span>
        </button>
        <div class=${"nav-group-items " + ((collapsed[g.id] === undefined ? g.defaultOpen : !collapsed[g.id]) ? '' : 'collapsed')}>
          ${g.items.map(s => html`
            <a key=${s.id} class=${'nav-item ' + (s.id === section ? 'active' : '')} href=${'#/' + s.id}>
              <span class="nav-item-dot"></span>${s.label}
            </a>
          `)}
        </div>
      </div>
    `)}
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
            active.id === 'dispatch-health' ? html`<${DispatchHealth} />` :
            active.id === 'inbound'     ? html`<${Inbound} />` :
            active.id === 'payouts'     ? html`<${Payouts} />` :
            active.id === 'dispatches'  ? html`<${Dispatches} />` :
            active.id === 'fees'        ? html`<${Fees} />` :
            active.id === 'predicted'   ? html`<${Predicted} />` :
            active.id === 'signal'      ? html`<${OrganicSignal} />` :
            active.id === 'contractors' ? html`<${Contractors} />` :
            active.id === 'console'     ? html`<${Console} />` :
            active.id === 'audit'       ? html`<${Audit} />` :
            active.id === 'kanban'      ? html`<${Kanban} />` :
            active.id === 'revenue'     ? html`<${Revenue} events=${events} wsConnected=${liveConnected} />` :
            active.id === 'si-strategy'  ? html`<${SiEvolution} />` :
            active.id === 'si-adaptive'    ? html`<${SiAdaptive} />` :
            active.id === 'panel_court'     ? html`<${PanelCourtPanel} />` :
            active.id === 'seo'          ? html`<${SEOPanel} />` :
            active.id === 'leads'       ? html`<${Leads} />` :
            active.id === 'neural-core'   ? html`<${AgiDashboard} />` :
            active.id === 'holo-map'      ? html`<${HoloMap} />` :
            active.id === 'partners'      ? html`<${Partners} />` :
            active.id === 'closer'        ? html`<${Closer} />` :
            active.id === "'products'"      ? html`<${ProductsPanel} />` :
            active.id === 'pain-points'   ? html`<${PainPoints} />` :
            active.id === 'swarm-gate'    ? html`<${SwarmGate} />` :
            active.id === 'operators'     ? html`<${Operators} />` :
            active.id === 'governor'      ? html`<${Governor} />` :
            active.id === 'fleet'  ? html`<${SniperFleet} />` :
            active.id === 'command-center' ? html`<${CommandCenter} />` :
            active.id === 'trial-pipeline' ? html`<${TrialPipeline} />` :
            active.id === 'health-monitor' ? html`<${HealthMonitor} />` :
            active.id === 'personality'   ? html`<${Personality} />` :
            active.id === 'strategist'    ? html`<${Strategist} />` :
            active.id === 'business-planner' ? html`<${BusinessPlannerDashboard} />` :
            active.id === 'analytics'     ? html`<${Analytics} />` :
            active.id === 'psychology'    ? html`<${PsychologyDashboard} />` :
            active.id === 'self-awareness' ? html`<${SelfAwarenessDashboard} />` :
            active.id === 'agent-os'       ? html`<${AgentOSDashboard} />` :
            active.id === 'bridge'        ? html`<${Bridge} />` :
            active.id === 'affiliates'    ? html`<${Affiliates} />` :
            active.id === 'cpl-pricing'   ? html`<${CplPricing} />` :

            active.id === 'traffic-ads'  ? html`<${TrafficAds} />` :
            active.id === 'email-tracking' ? html`<${EmailTracking} />` :
            active.id === 'stack'        ? html`<${Stack} />` :
            active.id === 'network'      ? html`<${Network} />` :
            active.id === 'loop'         ? html`<${Loop} />` :
            active.id === 'sms-performance' ? html`<${SmsPerformance} />` : active.id === 'reply-rates' ? html`<${ReplyRates} />` :
            html`<${Stub} section=${active} />`
          }
        </section>
      </main>
    </div>
  `;
}



// ── SNIPER FLEET — Watcher Findings Dashboard ──────────────────────
function SniperFleet() {
  const [findings, setFindings] = useState(null);
  const [stats, setStats] = useState(null);
  const [acknowledging, setAcknowledging] = useState({});
  const [fixing, setFixing] = useState({});
  const [loading, setLoading] = useState(true);
  const [showAllFindings, setShowAllFindings] = useState(true);
  // ── Operator override state ──────────────────────────────────
  const [overrideInfo, setOverrideInfo] = useState(null);
  const [ovLoading, setOvLoading] = useState(false);
  const [overrideError, setOverrideError] = useState(false);
  const [overrideForm, setOverrideForm] = useState({buy_amount_sol:'',min_risk_score:'',market_mode:'balanced',ttl_seconds:'300'});
  const [settingOverride, setSettingOverride] = useState(false);

  const fetchOverrideStatus = useCallback(async () => {
    setOverrideError(false);
    try {
      const res = await apiFetch('/api/v1/sniper/brain/health');
      if (res.ok) {
        const data = await res.json();
        setOverrideInfo(data);
      } else {
        setOverrideError(true);
      }
    } catch (e) {
      console.error('Override status fetch error:', e);
      setOverrideError(true);
    } finally {
      setOvLoading(false);
    }
  }, []);

  async function setOverride() {
    const ba = overrideForm.buy_amount_sol.trim();
    const rs = overrideForm.min_risk_score.trim();
    const mm = overrideForm.market_mode.trim();
    if (!ba && !rs && mm === 'balanced') return;
    setSettingOverride(true);
    try {
      const body = {};
      if (ba) body.buy_amount_sol = parseFloat(ba);
      if (rs) body.min_risk_score = parseInt(rs);
      if (mm) body.market_mode = mm;
      body.ttl_seconds = parseInt(overrideForm.ttl_seconds) || 300;
      const res = await apiFetch('/api/v1/sniper/brain/override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setOverrideForm({buy_amount_sol:'',min_risk_score:'',market_mode:'balanced',ttl_seconds:'300'});
        await fetchOverrideStatus();
      }
    } catch (e) {
      console.error('Set override error:', e);
    } finally {
      setSettingOverride(false);
    }
  }

  async function clearOverride() {
    setSettingOverride(true);
    try {
      await apiFetch('/api/v1/sniper/brain/override', { method: 'DELETE' });
      await fetchOverrideStatus();
    } catch (e) {
      console.error('Clear override error:', e);
    } finally {
      setSettingOverride(false);
    }
  }

  const fetchData = useCallback(async () => {
    try {
      const [findingsRes, statsRes] = await Promise.all([
        apiFetch('/api/v1/fleet/watcher-findings?limit=30'),
        apiFetch('/api/v1/fleet/watcher-stats?days=7'),
      ]);
      const fd = await findingsRes.json();
      const st = await statsRes.json();
      setFindings(fd);
      setStats(st);
    } catch (e) {
      console.error('Fleet fetch error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); fetchOverrideStatus(); const iv = setInterval(fetchData, 15000); return () => clearInterval(iv); }, [fetchData, fetchOverrideStatus]);

  async function acknowledgeFinding(id) {
    setAcknowledging(prev => ({ ...prev, [id]: true }));
    try { await apiFetch(`/api/v1/fleet/watcher-findings/${id}/acknowledge`, { method: 'PATCH' }); await fetchData(); }
    catch (e) { console.error(e); } finally { setAcknowledging(prev => ({ ...prev, [id]: false })); }
  }

  async function fixFinding(id) {
    setFixing(prev => ({ ...prev, [id]: true }));
    try { await apiFetch(`/api/v1/fleet/watcher-findings/${id}/fix`, { method: 'PATCH' }); await fetchData(); }
    catch (e) { console.error(e); } finally { setFixing(prev => ({ ...prev, [id]: false })); }
  }

  function ago(iso) {
    if (!iso) return '\u2014';
    const diff = Date.now() - new Date(iso).getTime();
    const s = Math.floor(diff / 1000);
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  if (loading) return html`<div class="stub"><div class="stub-body">Loading fleet findings\u2026</div></div>`;

  const findingList = findings?.findings || [];
  const s = stats || {};
  const filteredFindings = showAllFindings ? findingList : findingList.filter(f => !f.auto_healed);

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Agent <em>Fleet</em></div>
          <div class="section-sub">Watcher findings \u00b7 acknowledge \u00b7 fix tracking</div>
        </div>
        <div class="sec-actions">
          <button class="btn" onClick=${() => fetchData()} disabled=${loading}>${loading ? 'REFRESHING\u2026' : 'REFRESH'}</button>
        </div>
      </div>

      ${/* Filter Toggle */ ''}
      <div class="ld-filter" style={{marginBottom:'16px'}}>
        <span class="ld-filter-tag">Filter:</span>
        <button class="ld-filter-btn ${showAllFindings ? 'active' : ''}" onClick=${() => setShowAllFindings(true)}>All findings</button>
        <button class="ld-filter-btn ${!showAllFindings ? 'active' : ''}" onClick=${() => setShowAllFindings(false)}>Unresolved only</button>
      </div>

      ${/* Watcher Findings Stats */ ''}
      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">Total Findings</div>
          <div class="stat-value ${s.total > 0 ? 'teal' : 'dim'}">${s.total || 0}</div>
          <div class="stat-meta">${s.lookback_days || 7}d lookback</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Critical</div>
          <div class="stat-value" style=${{color: s.critical > 0 ? 'var(--status-red)' : 'var(--empire-mist)'}}>${s.critical || 0}</div>
          <div class="stat-meta">\u25cf ${s.warning || 0} warnings</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Acknowledged</div>
          <div class="stat-value" style=${{color: s.acknowledged > 0 ? 'var(--strike-cyan)' : 'var(--empire-mist)'}}>${s.acknowledged || 0}</div>
          <div class="stat-meta">${s.unacknowledged || 0} unacknowledged</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Fixed</div>
          <div class="stat-value" style=${{color: s.fixed > 0 ? 'var(--signal-teal)' : 'var(--empire-mist)'}}>${s.fixed || 0}</div>
          <div class="stat-meta">${s.unfixed || 0} unfixed</div>
        </div>
      </div>

      ${/* Operator Override Panel */ ''}
      <div class="af-panel" style={{marginTop:'0'}}>
        <div class="af-h">
          <div class="af-title">Sniper <em>Override</em></div>
          <div class="af-tag">operator override for dynamic sniper config</div>
        </div>
        <div style={{display:'flex',flexDirection:'column',gap:'12px'}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
            <div>
                            ${ovLoading ? html`<span class="af-tag">Loading…</span>` : overrideError ? html`
                <span style={{fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--status-red)'}}>
                  \xe2\x9a\xa0 Brain Unreachable — using static fallback config
                </span>
              ` : overrideInfo ? html`
                <span style={{fontFamily:'var(--font-mono)',fontSize:'10px',color:overrideInfo.brain_healthy && !overrideInfo.operator_override_active?'var(--empire-fog)':'var(--signal-teal)'}}>
                  \xe2\x97\x8f ${overrideInfo.brain_healthy ? html`Brain ${overrideInfo.operator_override_active ? 'OVERRIDE ACTIVE' : 'ONLINE'}` : html`Brain Unreachable`}
                </span>
                <span style={{fontFamily:'var(--font-mono)',fontSize:'9px',color:'var(--empire-mist)',marginLeft:'12px'}}>
                  Router: ${overrideInfo.router_available ? '\xe2\x9c\x93' : '\xe2\x9c\x97'} \xc2\xb7 DB: ${overrideInfo.db_available ? '\xe2\x9c\x93' : '\xe2\x9c\x97'}
                </span>
              ` : html`<span class="af-tag">Fetching status…</span>`}
            </div>
            <div style={{display:'flex',gap:'8px'}}>
              <button class="btn ghost" style={{fontSize:'9px',padding:'6px 12px'}} onClick={() => { setOvLoading(true); fetchOverrideStatus(); }} disabled={ovLoading}>REFRESH</button>
            </div>
          </div>
          ${/* Override form */ ''}
          <div style={{display:'flex',gap:'10px',flexWrap:'wrap',alignItems:'end'}}>
            <div class="fld" style={{flex:'0 1 120px',marginBottom:'0'}}>
              <label class="fld-lbl" style={{fontSize:'9px'}}>Buy (SOL)</label>
              <input class="fld-in mono" style={{fontSize:'11px',padding:'7px 10px'}} type="number" step="0.01" min="0" placeholder="0.1" value={overrideForm.buy_amount_sol} onChange={e => setOverrideForm(p => ({...p, buy_amount_sol: e.target.value}))} />
            </div>
            <div class="fld" style={{flex:'0 1 100px',marginBottom:'0'}}>
              <label class="fld-lbl" style={{fontSize:'9px'}}>Risk (1-100)</label>
              <input class="fld-in mono" style={{fontSize:'11px',padding:'7px 10px'}} type="number" min="1" max="100" placeholder="50" value={overrideForm.min_risk_score} onChange={e => setOverrideForm(p => ({...p, min_risk_score: e.target.value}))} />
            </div>
            <div class="fld" style={{flex:'0 1 110px',marginBottom:'0'}}>
              <label class="fld-lbl" style={{fontSize:'9px'}}>Market Mode</label>
              <select class="fld-in mono" style={{fontSize:'11px',padding:'7px 10px',cursor:'pointer'}} value={overrideForm.market_mode} onChange={e => setOverrideForm(p => ({...p, market_mode: e.target.value}))}>
                <option value="balanced">balanced</option>
                <option value="aggressive">aggressive</option>
                <option value="conservative">conservative</option>
              </select>
            </div>
            <div class="fld" style={{flex:'0 1 80px',marginBottom:'0'}}>
              <label class="fld-lbl" style={{fontSize:'9px'}}>TTL (s)</label>
              <input class="fld-in mono" style={{fontSize:'11px',padding:'7px 10px'}} type="number" min="10" max="3600" value={overrideForm.ttl_seconds} onChange={e => setOverrideForm(p => ({...p, ttl_seconds: e.target.value}))} />
            </div>
            <button class="btn" style={{fontSize:'9px',padding:'7px 14px'}} onClick={setOverride} disabled={settingOverride}>{settingOverride ? 'SETTING…' : 'SET OVERRIDE'}</button>
            <button class="btn ghost" style={{fontSize:'9px',padding:'7px 14px',color:'var(--status-red)',borderColor:'var(--status-red)'}} onClick={clearOverride} disabled={settingOverride}>{settingOverride ? '…' : 'CLEAR'}</button>
          </div>
        </div>
      </div>

      ${/* Error Rate Trend */ ''}
      ${s.daily_counts && s.daily_counts.length > 0 ? html`
        <div class="af-panel" style=${{marginTop:'0'}}>
          <div class="af-h">
            <div class="af-title">Error Rate <em>Trend</em></div>
            <div class="af-tag">daily findings \u00b7 ${s.daily_counts.length} days</div>
          </div>
          <div style=${{display:'flex',flexDirection:'column',gap:'6px'}}>
            ${s.daily_counts.map(d => {
              const maxVal = Math.max(...s.daily_counts.map(x => x.total), 1);
              const pct = (d.total / maxVal) * 100;
              return html`
                <div class="rv-bar-row" key=${d.date}>
                  <span class="rv-bar-label" style=${{minWidth:'80px'}}><span class="rv-bar-lane" style=${{fontSize:'11px'}}>${d.date}</span></span>
                  <div class="rv-bar-track">
                    <div class="rv-bar-fill" style=${{width:pct+'%',background:d.critical>0?'var(--status-red)':'var(--status-amber)'}}></div>
                  </div>
                  <span class="rv-bar-val">${d.total}</span>
                  <span class="rv-bar-meta" style=${{color:d.critical>0?'var(--status-red)':'var(--empire-fog)'}}>${d.critical>0?d.critical+' crit':d.warning+' warn'}</span>
                </div>`;
            })}
          </div>
        </div>` : null}

      ${/* Findings Table with Ack/Fix Toggles */ ''}
      <div class="af-panel" style=${{marginTop:'20px'}}>
        <div class="af-h">
          <div class="af-title">Watcher <em>Findings</em></div>
          <div class="af-tag">${filteredFindings.length} shown \u00b7 ${s.unacknowledged||0} unacknowledged \u00b7 ${s.unfixed||0} unfixed</div>
        </div>
        ${filteredFindings.length === 0 ? html`
          <div class="af-empty">${findings?.error ? 'Watcher findings table not available: '+findings.error : 'No watcher findings. The fleet is healthy.'}</div>
        ` : html`
          <table class="tbl">
            <thead><tr>
              <th>Time</th><th>Severity</th><th>Type</th><th>Agent</th><th>Title</th><th>Status</th><th>Actions</th>
            </tr></thead>
            <tbody>
              ${filteredFindings.map(f => {
                const isCritical = f.severity === 'critical';
                const isAcked = f.acknowledged;
                const isFixed = f.fixed;
                return html`
                  <tr key=${f.id} style=${{background:isCritical&&!isFixed?'rgba(255,68,68,0.03)':'transparent'}}>
                    <td class="tbl-mono" style=${{fontSize:'10px',color:'var(--empire-fog)'}}>${f.created_at?new Date(f.created_at).toLocaleString():''}</td>
                    <td><span class="bdg ${isCritical?'active':'pending'}" style=${{color:isCritical?'var(--status-red)':'var(--status-amber)',borderColor:isCritical?'rgba(255,68,68,0.3)':'rgba(255,184,0,0.3)'}}>${f.severity||'warning'}</span></td>
                    <td class="tbl-mono" style=${{fontSize:'10px'}}>${f.finding_type||'\u2014'}</td>
                    <td class="tbl-mono" style=${{fontSize:'10px',color:'var(--strike-cyan)'}}>${f.agent_name||'\u2014'}</td>
                    <td style=${{maxWidth:'280px',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}} title=${f.title||''}>${(f.title||f.message||'').substring(0,80)}</td>
                    <td>${isFixed?html`<span class="bdg complete" style=${{color:'var(--signal-teal)',borderColor:'rgba(68,229,184,0.2)'}}>FIXED</span>`:isAcked?html`<span class="bdg replied" style=${{color:'var(--strike-cyan)'}}>ACKED</span>`:html`<span class="bdg pending">OPEN</span>`}</td>
                    <td><div style=${{display:'flex',gap:'4px'}}>
                      ${!isAcked?html`<button class="tbl-action" disabled=${acknowledging[f.id]} onClick=${()=>acknowledgeFinding(f.id)}>${acknowledging[f.id]?'\u2026':'Ack'}</button>`:null}
                      ${!isFixed?html`<button class="tbl-action go" disabled=${fixing[f.id]} onClick=${()=>fixFinding(f.id)}>${fixing[f.id]?'\u2026':'Fix'}</button>`:null}
                    </div></td>
                  </tr>`;})}
            </tbody>
          </table>`}
      </div>

      ${/* Findings by Type */ ''}
      ${s.by_type&&Object.keys(s.by_type).length>0?html`
      <div class="af-panel" style=${{marginTop:'20px'}}>
        <div class="af-h"><div class="af-title">Findings by <em>Type</em></div><div class="af-tag">${Object.keys(s.by_type).length} types</div></div>
        <div style=${{display:'flex',gap:'8px',flexWrap:'wrap'}}>
          ${Object.entries(s.by_type).map(([type,count])=>html`
            <div class="sf-bdg ACTIVE" style=${{fontSize:'10px',padding:'5px 12px'}} key=${type}>
              <span class="sf-bdg-dot"></span> ${type.replace(/_/g,' ')}: <strong>${count}</strong>
            </div>`)}
        </div>
      </div>`:null}
    </div>`;
}

function CommandCenter() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    apiFetch('/api/v6/suite/ccp/health')
      .then(r => r.json())
      .then(d => { setHealth(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  if (loading) return html`<div style=${{padding:'24px',color:'var(--empire-fog)',fontFamily:'var(--font-mono)',fontSize:'11px'}}>Loading Command Center…</div>`;
  if (!health) return html`<div style=${{padding:'24px',color:'var(--status-amber)',fontFamily:'var(--font-mono)',fontSize:'11px'}}>No health data available</div>`;
  const products = health.products || [];
  const summary = health.summary || {};
  const totalProducts = products.length;
  const healthy = products.filter(p => p.status === 'ok').length;
  const warnCount = products.filter(p => p.status === 'warn').length;
  const downCount = products.filter(p => p.status === 'error').length;
  const totalMRR = health.total_mrr || 0;
  const activeSubs = health.active_subscriptions || 0;
  return html`
    <div class="ccp-dash">
      <div class="section-h">
        <div class="section-title">Command Center <em>Pro</em></div>
        <div class="section-sub">All products · unified health</div>
      </div>
      <div class="ccp-summary-grid">
        <div class="ccp-summary-card">
          <div class="ccp-summary-val teal">${totalProducts}</div>
          <div class="ccp-summary-lbl">Products</div>
        </div>
        <div class="ccp-summary-card">
          <div class="ccp-summary-val ${healthy === totalProducts ? 'teal' : warnCount > 0 ? 'amber' : 'red'}">${healthy}</div>
          <div class="ccp-summary-lbl">Healthy</div>
        </div>
        <div class="ccp-summary-card">
          <div class="ccp-summary-val ${warnCount > 0 ? 'amber' : 'dim'}">${warnCount}</div>
          <div class="ccp-summary-lbl">Warnings</div>
        </div>
        <div class="ccp-summary-card">
          <div class="ccp-summary-val ${downCount > 0 ? 'red' : 'dim'}">${downCount}</div>
          <div class="ccp-summary-lbl">Errors</div>
        </div>
        <div class="ccp-summary-card">
          <div class="ccp-summary-val teal">$${totalMRR.toLocaleString()}</div>
          <div class="ccp-summary-lbl">Total MRR</div>
        </div>
        <div class="ccp-summary-card">
          <div class="ccp-summary-val teal">${activeSubs}</div>
          <div class="ccp-summary-lbl">Active Subs</div>
        </div>
      </div>
      <div class="ccp-product-grid">
        ${products.map(p => html`
          <div class="ccp-product-card ${p.status === 'error' ? 'error' : p.status === 'warn' ? 'warn' : ''}">
            <div class="ccp-product-top">
              <div class="ccp-product-name">${p.name || p.product || '?'}</div>
              <span class="ccp-bdg ${p.status}">
                <span class="ccp-bdg-dot"></span>
                ${p.status}
              </span>
            </div>
            ${p.tier ? html`<div class="ccp-product-tier">${p.tier}</div>` : ''}
            ${p.description ? html`<div class="ccp-product-desc">${p.description}</div>` : ''}
            <div class="ccp-product-meta">
              ${p.monthly_price_usd ? html`<span class="ccp-product-price">$${Number(p.monthly_price_usd).toLocaleString()}/mo</span>` : ''}
              ${p.message ? html`<span class="ccp-product-msg">${p.message}</span>` : ''}
            </div>
          </div>
        `)}
      </div>
    </div>
  `;
}


function TrialPipeline() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    apiFetch('/api/v6/suite/sales/trial-pipeline')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  if (loading) return html`<div style=${{padding:'24px',color:'var(--empire-fog)',fontFamily:'var(--font-mono)',fontSize:'11px'}}>Loading Trial Pipeline…</div>`;
  if (!data) return html`<div style=${{padding:'24px',color:'var(--status-amber)',fontFamily:'var(--font-mono)',fontSize:'11px'}}>No trial data available</div>`;
  const s = data.summary || {};
  const products = data.by_product || [];
  const daily = data.daily_starts || [];
  const recent = data.recent || [];
  const totalTrials = s.total_trial_starts || 0;
  const active = s.active || 0;
  const expiring = s.expiring_soon || 0;
  const converted = s.converted || 0;
  const churned = s.churned || 0;
  const expired = s.expired_unconverted || 0;
  const winRate = s.win_rate || 0;
  const potentialMRR = s.potential_monthly_mrr || 0;
  return html`
    <div>
      <div class="section-h">
        <div class="section-title">Trial <em>Pipeline</em></div>
        <div class="section-sub">Active · expiring · converted · churned · ${daily.length > 0 ? daily[0].date + ' daily' : ''}</div>
      </div>
      <div class="tp-summary-grid">
        <div class="tp-summary-card">
          <div class="tp-summary-val teal">${active}</div>
          <div class="tp-summary-lbl">Active Trials</div>
          <div class="tp-summary-sub">${expiring} expiring soon</div>
        </div>
        <div class="tp-summary-card">
          <div class="tp-summary-val amber">${expiring}</div>
          <div class="tp-summary-lbl">Expiring Soon</div>
          <div class="tp-summary-sub">${active > 0 ? Math.round(expiring/active*100) + '% of active' : '—'}</div>
        </div>
        <div class="tp-summary-card">
          <div class="tp-summary-val teal">${converted}</div>
          <div class="tp-summary-lbl">Converted</div>
          <div class="tp-summary-sub">${winRate > 0 ? Math.round(winRate*100) + '% win rate' : ''}</div>
        </div>
        <div class="tp-summary-card">
          <div class="tp-summary-val ${churned > 0 ? 'red' : 'dim'}">${churned}</div>
          <div class="tp-summary-lbl">Churned</div>
          <div class="tp-summary-sub">${converted > 0 && churned > 0 ? Math.round(churned/converted*100) + '% of converted' : ''}</div>
        </div>
        <div class="tp-summary-card">
          <div class="tp-summary-val ${expired > 5 ? 'amber' : 'dim'}">${expired}</div>
          <div class="tp-summary-lbl">Expired (Unconv.)</div>
          <div class="tp-summary-sub">${totalTrials > 0 ? Math.round(expired/totalTrials*100) + '% of all' : ''}</div>
        </div>
        <div class="tp-summary-card">
          <div class="tp-summary-val teal">\$${potentialMRR.toLocaleString()}</div>
          <div class="tp-summary-lbl">Potential MRR</div>
          <div class="tp-summary-sub">From active trials</div>
        </div>
      </div>
      ${products.length > 0 ? html`
        <div class="tp-product-grid">
          ${products.map(p => html`
            <div class="tp-product-card">
              <div class="tp-product-name">${p.name || p.product || '?'}</div>
              <div class="tp-product-meta">
                <span>${p.trials} trials · ${p.active} active</span>
                <span class="${p.converted > 0 ? 'tp-stat-teal' : 'tp-stat-dim'}">${p.converted} conv</span>
              </div>
              <div class="tp-product-bar">
                <div class="tp-bar-track">
                  ${p.trials > 0 ? html`
                    <div class="tp-bar-fill active" style=${{width: Math.round(p.active/p.trials*100)+'%'}}></div>
                    <div class="tp-bar-fill converted" style=${{width: Math.round(p.converted/p.trials*100)+'%'}}></div>
                    <div class="tp-bar-fill expired" style=${{width: Math.round(p.expired/p.trials*100)+'%'}}></div>
                  ` : ''}
                </div>
              </div>
              <div class="tp-bar-legend">
                <span class="tp-legend-dot active">Active ${Math.round(p.active/p.trials*100) + '%'}</span>
                <span class="tp-legend-dot converted">Conv ${Math.round(p.converted/p.trials*100) + '%'}</span>
                <span class="tp-legend-dot expired">Exp ${Math.round(p.expired/p.trials*100) + '%'}</span>
              </div>
            </div>
          `)}
        </div>
      ` : ''}
      <div class="split">
        ${daily.length > 0 ? html`
          <div class="panel">
            <div class="panel-head">Daily Trial Starts (last 14d)</div>
            <div style=${{display:'flex',flexDirection:'column',gap:'4px'}}>
              ${daily.slice(0,14).reverse().map(d => {
                const maxCount = Math.max(...daily.slice(0,14).map(x=>x.count), 1);
                return html`
                  <div class="tp-bar-row">
                    <span class="tp-bar-date">${d.date.slice(5)}</span>
                    <div class="tp-small-bar-track">
                      <div class="tp-small-bar-fill" style=${{width: Math.round(d.count/maxCount*80)+'%'}}></div>
                    </div>
                    <span class="tp-bar-val">${d.count}</span>
                  </div>
                `;
              })}
            </div>
          </div>
        ` : ''}
        ${recent.length > 0 ? html`
          <div class="panel">
            <div class="panel-head">Recent Trials</div>
            <div style=${{maxHeight:'320px',overflowY:'auto'}}>
              ${recent.map(t => html`
                <div class="tp-recent-row">
                  <div class="tp-recent-left">
                    <div class="tp-recent-email">${t.email}</div>
                    <div class="tp-recent-prod">${t.product} · ${t.tier}</div>
                  </div>
                  <div class="tp-recent-right">
                    <span class="tp-status-bdg ${t.status}">
                      <span class="tp-bdg-dot"></span>
                      ${t.status}
                    </span>
                    <div class="tp-recent-days">
                      ${t.status === 'active' ? t.days_left + 'd left' : t.status === 'expired' ? 'ended' : t.status === 'converted' ? 'paid' : ''}
                    </div>
                  </div>
                </div>
              `)}
            </div>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

// ── QC DASHBOARD ──────────────────────────────────────────────────────
function QC() {
  const [events, setEvents] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [resolving, setResolving] = useState({});
  const [severity, setSeverity] = useState('');
  const [showResolved, setShowResolved] = useState(false);
  const [timeRange, setTimeRange] = useState('24h');

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      let url = '/api/v1/qc/events?limit=100';
      if (severity) url += '&severity=' + encodeURIComponent(severity);
      if (!showResolved) url += '&resolved=false';
      const since = timeRange === '7d' ? new Date(Date.now() - 7*86400000).toISOString() : timeRange === '30d' ? new Date(Date.now() - 30*86400000).toISOString() : '';
      if (since) url += '&since=' + encodeURIComponent(since);
      const r = await apiFetch(url).then(x => x.json());
      if (r.ok === false) { setErr(r.error || 'API error'); setEvents([]); }
      else { setEvents(r.events || []); }
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
      setEvents([]);
    }
    setLoading(false);
  }, [severity, showResolved, timeRange]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const resolveEvent = async (id) => {
    setResolving(r => ({ ...r, [id]: true }));
    try {
      const r = await apiFetch('/api/v1/qc/events/' + id + '/resolve', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved_by: 'operator' }),
      }).then(x => x.json());
      if (r.ok) {
        setEvents(evts => (evts || []).map(e => e.id === id ? { ...e, resolved: true, resolved_at: r.resolved_at, resolved_by: r.resolved_by } : e));
      }
    } catch (e) {}
    setResolving(r => ({ ...r, [id]: false }));
  };

  const toggleExpand = (id) => {
    setExpandedId(prev => prev === id ? null : id);
  };

  if (err) return html`<div class="qc-error">${err}</div>`;

  const totalEvents = events ? events.length : 0;
  const unresolvedTier2 = events ? events.filter(e => e.severity === 'tier_2' && !e.resolved).length : 0;
  const autoRemediated24h = events ? events.filter(e => e.auto_remediated).length : 0;
  const lastSummary = events ? events.filter(e => e.category === 'daily_summary').sort((a,b) => new Date(b.created_at) - new Date(a.created_at))[0] : null;

  return html`
    <div>
      <div class="section-h">
        <div class="section-title">Quality <em>Control</em></div>
        <div class="section-sub">Events · severity · resolve</div>
      </div>
      <div class="qc-summary-grid">
        <div class="qc-card">
          <div class="qc-card-label">Total Events (24h)</div>
          <div class="qc-card-val ${totalEvents > 0 ? 'teal' : 'dim'}">${totalEvents}</div>
          <div class="qc-card-sub">In current view</div>
        </div>
        <div class="qc-card">
          <div class="qc-card-label">Unresolved Tier-2</div>
          <div class="qc-card-val ${unresolvedTier2 > 0 ? 'amber' : 'teal'}">${unresolvedTier2}</div>
          <div class="qc-card-sub">${unresolvedTier2 > 0 ? 'Needs your attention' : 'All clear'}</div>
        </div>
        <div class="qc-card">
          <div class="qc-card-label">Auto-Remediations</div>
          <div class="qc-card-val teal">${autoRemediated24h}</div>
          <div class="qc-card-sub">Tier-1 auto-fixes in view</div>
        </div>
        <div class="qc-card">
          <div class="qc-card-label">Last Daily Summary</div>
          <div class="qc-card-val ${lastSummary ? 'teal' : 'dim'}">${lastSummary ? new Date(lastSummary.created_at).toLocaleDateString() : '—'}</div>
          <div class="qc-card-sub">${lastSummary ? new Date(lastSummary.created_at).toLocaleTimeString() : 'No summary yet'}</div>
        </div>
      </div>
      <div class="qc-filter-bar">
        <div class="qc-filter-group">
          <span class="qc-filter-label">Severity</span>
          <select class="qc-filter-select" value=${severity} onChange=${e => setSeverity(e.target.value)}>
            <option value="">All</option>
            <option value="tier_1">Tier 1</option>
            <option value="tier_2">Tier 2</option>
            <option value="tier_3">Tier 3</option>
          </select>
        </div>
        <div class="qc-filter-group">
          <span class="qc-filter-label">Time</span>
          <select class="qc-filter-select" value=${timeRange} onChange=${e => setTimeRange(e.target.value)}>
            <option value="24h">Last 24h</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
        </div>
        <button class=${'qc-filter-toggle ' + (showResolved ? 'active' : '')} onClick=${() => setShowResolved(r => !r)}>
          ${showResolved ? '✓' : '○'} Show Resolved
        </button>
        <button class="qc-refresh-btn" onClick=${fetchEvents} disabled=${loading}>
          ${loading ? '⟳' : '↻'} Refresh
        </button>
      </div>
      ${loading ? html`<div class="qc-loading">Loading QC events…</div>` : !events || events.length === 0 ? html`<div class="qc-empty">No QC events found</div>` : html`
        <div class="qc-table-wrap">
          <table class="qc-table">
            <thead>
              <tr>
                <th>Created</th>
                <th>Severity</th>
                <th>Category</th>
                <th>Subject</th>
                <th>Summary</th>
                <th class="qc-check">Auto</th>
                <th class="qc-check">TG</th>
                <th>Resolved</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${events.map(e => {
                const isExpanded = expandedId === e.id;
                return html`
                  <tr key=${e.id} class=${isExpanded ? 'qc-expanded' : ''} onClick=${() => toggleExpand(e.id)} style=${{cursor:'pointer'}}>
                    <td style=${{whiteSpace:'nowrap',fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-fog)'}}>${new Date(e.created_at).toLocaleString()}</td>
                    <td><span class=${'qc-severity ' + e.severity}>${e.severity.replace('_', ' ')}</span></td>
                    <td><span class="qc-category">${e.category || '—'}</span></td>
                    <td><span class="qc-subject-id" title=${e.subject_id || ''}>${(e.subject_id || '—').slice(0,24)}</span></td>
                    <td><span class="qc-summary" title=${e.summary || ''}>${e.summary || '—'}</span></td>
                    <td class=${'qc-check ' + (e.auto_remediated ? 'yes' : 'no')}>${e.auto_remediated ? '✓' : '—'}</td>
                    <td class=${'qc-check ' + (e.telegram_pinged ? 'yes' : 'no')}>${e.telegram_pinged ? '✓' : '—'}</td>
                    <td>${e.resolved ? html`<span style=${{color:'var(--empire-mist)',fontSize:'10px',fontFamily:'var(--font-mono)'}}>✓ ${(e.resolved_at || '').slice(0,10)}</span>` : html`<span style=${{color:'var(--status-amber)',fontSize:'10px',fontFamily:'var(--font-mono)'}}>Pending</span>`}</td>
                    <td>
                      ${!e.resolved ? html`
                        <button class="qc-resolve-btn"
                                onClick=${(ev) => { ev.stopPropagation(); resolveEvent(e.id); }}
                                disabled=${resolving[e.id]}>
                          ${resolving[e.id] ? '…' : 'Resolve'}
                        </button>
                      ` : html`
                        <button class="qc-resolve-btn done" disabled>Done</button>
                      `}
                    </td>
                  </tr>
                  ${isExpanded ? html`
                    <tr key=${e.id + '-detail'}>
                      <td colspan="9" style=${{padding:'0'}}>
                        <div class="qc-detail-panel">
                          <div class="qc-detail-meta">
                            <span>Source: <strong>${e.source_agent || '—'}</strong></span>
                            <span>Kind: <strong>${e.subject_kind || '—'}</strong></span>
                            <span>ID: <strong>${e.subject_id || '—'}</strong></span>
                            ${e.auto_remediated ? html`<span>Remediation: <strong>${e.remediation || 'auto'}</strong></span>` : ''}
                            ${e.resolved ? html`<span>Resolved by: <strong>${e.resolved_by || '—'}</strong></span>` : ''}
                          </div>
                          <div class="qc-detail-head">Detail Context</div>
                          <div class="qc-detail-json">${JSON.stringify(e.detail || {}, null, 2)}</div>
                        </div>
                      </td>
                    </tr>
                  ` : ''}
                `;
              })}
            </tbody>
          </table>
        </div>

        <div class="bill-chart-wrap">
          <div class="bill-chart-h">
            <span class="bill-chart-title">Daily Fee Breakdown &middot; ${billWindow === '90d' ? '90' : billWindow === '7d' ? '7' : '30'}-Day</span>
            <div class="bill-chart-window">
              <button class="bill-chart-window-btn ${billWindow === '7d' ? 'active' : ''}" onClick=${() => setBillWindow('7d')}>7d</button>
              <button class="bill-chart-window-btn ${billWindow === '30d' ? 'active' : ''}" onClick=${() => setBillWindow('30d')}>30d</button>
              <button class="bill-chart-window-btn ${billWindow === '90d' ? 'active' : ''}" onClick=${() => setBillWindow('90d')}>90d</button>
            </div>
            <button class="bill-chart-mode-btn" onClick=${() => setChartMode(chartMode === "stacked" ? "side" : "stacked")}>${chartMode === "stacked" ? "Side-by-Side" : "Stacked"}</button>
            <span class="bill-chart-tag">${billTimeseries ? billTimeseries.total_revenue.toLocaleString('en-US', {style:'currency',currency:'USD',minimumFractionDigits:0}) + ' total' + (billTimeseries.total_premium > 0 ? ' · +$' + billTimeseries.total_premium.toFixed(0) + ' PM' : '') : ''}</span>
          </div>
          ${!billTimeseries ? html`<div class="bill-chart-empty">Loading chart data&hellip;</div>` : billTimeseries.series.length === 0 ? html`<div class="bill-chart-empty">${`No billing data in the last ${billWindow === '90d' ? 90 : billWindow === '7d' ? 7 : 30} days`}</div>` : html`
          <div class="bill-chart">
          <div class="bill-chart-inner">
            ${(() => {
              const maxRev = Math.max(...billTimeseries.series.map(d => d.revenue), 1);
              const maxCalls = Math.max(...billTimeseries.series.map(d => d.calls), 1);
              const barStep = 28;
              const chartH = 130;
              const series = billTimeseries.series;
              return html`
                ${series.map(d => html`
                  <div class="bill-chart-bars" style="display:flex;align-items:flex-end;gap:3px;grid-area:chart"><div class="bill-chart-bar-wrap">
                    <div class="bill-chart-tooltip">${d.date}: $${d.revenue.toFixed(0)} total · S:$${d.settlement_revenue.toFixed(0)} PM:$${d.per_minute_revenue.toFixed(0)}${d.per_minute_revenue > d.settlement_revenue ? ' Δ+$' + (d.per_minute_revenue - d.settlement_revenue).toFixed(0) : ''} · ${d.calls} calls · ${d.billable} billable</div>
                    ${chartMode === "stacked" ? html`<div class="bill-chart-bar-stack" style="height:${Math.max(3, (d.revenue / maxRev) * chartH)}px"><div class="bill-chart-bar per-minute" style="height:${Math.max(0, (d.per_minute_revenue / maxRev) * chartH)}px">${d.per_minute_revenue > d.settlement_revenue ? html`<div class="bill-chart-bar premium" style="height:${Math.max(2, ((d.per_minute_revenue - d.settlement_revenue) / maxRev) * chartH)}px"></div>` : }</div><div class="bill-chart-bar settlement" style="height:${Math.max(3, (d.settlement_revenue / maxRev) * chartH)}px"></div></div>` : html`<div class="bill-chart-bars-side" style="display:flex;gap:3px;align-items:flex-end;height:${Math.max(3, (Math.max(d.settlement_revenue, d.per_minute_revenue) / maxRev) * chartH)}px;width:100%"><div class="bill-chart-bar settlement side" style="height:${Math.max(3, (d.settlement_revenue / maxRev) * chartH)}px;flex:1;min-width:6px;border-radius:2px 2px 0 0"></div><div class="bill-chart-bar per-minute side" style="height:${Math.max(0, (d.per_minute_revenue / maxRev) * chartH)}px;flex:1;min-width:6px;border-radius:2px 2px 0 0;position:relative">${d.per_minute_revenue > d.settlement_revenue ? html`<div class="bill-chart-bar premium" style="height:${Math.max(2, ((d.per_minute_revenue - d.settlement_revenue) / maxRev) * chartH)}px;position:absolute;bottom:0;left:0;right:0;background:var(--status-amber);opacity:.7;border-radius:2px 2px 0 0"></div>` : }</div></div>`}
                    <div class="bill-chart-bar-label">${d.date.slice(5)}</div>
                  </div>
                `).join('')}
                </div>
                <svg class="bill-chart-line-svg" width="${Math.max(series.length * (barStep + 3), 50)}" height="130" viewBox="0 0 ${Math.max(series.length * (barStep + 3), 50)} 130"
                  <polyline class="bill-chart-line" points="${series.map((d, i) => {
                    const x = (barStep / 2) + i * (barStep + 3);
                    const y = chartH - (d.calls / maxCalls) * chartH;
                    return x.toFixed(1) + ',' + y.toFixed(1);
                  }).join(' ')}" vector-effect="non-scaling-stroke"/>
                  ${series.map((d, i) => {
                    const x = (barStep / 2) + i * (barStep + 3);
                    const y = chartH - (d.calls / maxCalls) * chartH;
                    return '<circle class="bill-chart-line-dot" cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="2.5"/>';
                  }).join('')}
                </svg>
              `;
            })()}
          </div>
          <div class="bill-chart-legend">
            <div class="bill-chart-legend-item"><div class="bill-chart-legend-dot" style="background:var(--signal-teal);opacity:.85"></div>Settlement</div>
            <div class="bill-chart-legend-item"><div class="bill-chart-legend-dot" style="background:var(--strike-cyan);opacity:.5"></div>Per-Min</div>
            <div class="bill-chart-legend-item"><div class="bill-chart-legend-dot premium-dot"></div>Premium</div>
            <div class="bill-chart-legend-item"><div class="bill-chart-legend-dot" style="background:var(--status-amber);opacity:.7;height:2px;border-radius:1px;border:1px dashed var(--status-amber)"></div>Cumulative Fees</div>
            <div class="bill-chart-legend-item"><div class="bill-chart-legend-dot" style="background:var(--strike-cyan);opacity:.7;height:2px;border-radius:1px"></div>Call Volume</div>
            <div class="bill-chart-legend-item"><span style="color:var(--empire-mist)">${billTimeseries.total_calls} calls · ${billTimeseries.days} days with data</span></div>
          </div>
          `}
        </div>

      `}
    </div>
  `;
}

createRoot(document.getElementById('root')).render(html`<${App} />`);
"""
