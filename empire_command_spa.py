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
n/* ── ACTIVITY LOG ────────────────────────────────────────────────── */
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
.chart-bar:hover{opacity:1 !important;filter:brightness(1.2)}
.chart-donut{display:flex;align-items:center;gap:16px}
.chart-donut-svg{flex-shrink:0}
.chart-legend{display:flex;flex-direction:column;gap:4px}
.chart-legend-item{display:flex;align-items:center;gap:6px;font-family:var(--font-mono);font-size:9px;color:var(--empire-mist)}
.chart-legend-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.chart-legend-val{color:var(--empire-white);margin-left:auto;font-weight:500}

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
  { id: 'pulse',         label: 'Pulse',         sub: 'Live overview' },
  { id: 'pipeline',      label: 'Pipeline',       sub: 'Email & SMS · state machine' },
  { id: 'dispatch',      label: 'Dispatch',       sub: 'Contractor matching' },
  { id: 'inbound',       label: 'Inbound',        sub: 'Calls · triage · recordings' },
  { id: 'payouts',       label: 'Payouts',        sub: 'Pending · approvals · history' },
  { id: 'contractors',   label: 'Contractors',    sub: 'Applications & approvals' },
  { id: 'console',       label: 'Console',        sub: 'Sovereign natural-language ops' },
  { id: 'audit',         label: 'Audit',          sub: 'Operator action history' },
  { id: 'operators',     label: 'Operators',      sub: 'Roster · roles · invites' },
  { id: 'neural-core',   label: 'Neural Core',    sub: 'Live brain · autonomous decisions · 5s refresh' },
  { id: 'holo-map',      label: 'Holo Map',       sub: 'Live storm grid · 3D target overlay' },
  { id: 'governor',      label: 'Governor',       sub: 'AGI governor · weight control · guardrails' },
  { id: 'sniper-fleet',  label: 'Sniper Fleet',   sub: 'Active agents · lane status · targeting' },
  { id: 'health-monitor',label: 'Health Monitor', sub: 'Agent mesh · system health · overseer' },
  { id: 'partners',      label: 'Partners',       sub: 'Buyers · pending · approvals' },
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
      const [pb, em, sm, py, ib, pr, co] = await Promise.all([
        apiFetch('/api/v1/playbook/summary').then(r => r.json()),
        apiFetch('/api/v1/email/stats').then(r => r.json()),
        apiFetch('/api/v1/sms/stats').then(r => r.json()),
        apiFetch('/api/v1/payouts/pending').then(r => r.json()),
        apiFetch('/api/v1/inbound/stats').then(r => r.json()),
        apiFetch('/api/v1/partner/all').then(r => r.json()),
        apiFetch('/api/v1/compliance/stats').then(r => r.json()),
      ]);
      setStats({ pb, em, sm, py, ib, pr, co });
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
    .reduce((sum, p) => sum + ((parseFloat(p.base_payout) || 0) * (parseFloat(p.fee_rate) || 0.01) + (parseFloat(p.per_call_fee) || 0)), 0);
  const projectedMRR = Math.round(totalMonthlyRetainer + (totalPerCallFee * 22));

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
          <div class="stat-meta">$${totalMonthlyRetainer} retainers · $${Math.round(totalPerCallFee * 22)} per-call fees</div>
        </div>
      </div>

      ${activePartnersList.length > 0 ? html`
      <div class="pipeline-breakdown">
        <div class="pipeline-h">
          <div class="pipeline-title">Pipeline Breakdown</div>
          <div class="pipeline-total">$${totalPipelineValue}/call · $${totalMonthlyRetainer}/mo retainers</div>
        </div>
        <div class="pipeline-grid">
          ${activePartnersList.map(p => {
            const payout = parseFloat(p.base_payout) || 0;
            const feeRate = parseFloat(p.fee_rate) || 0.01;
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
      ` : ''}

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
          style="cursor:pointer;transition: stroke-dasharray 0.3s var(--ease-snap)"
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
function HealthMonitor() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/v1/health/mesh').then(x => x.json());
      setData(r);
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
      ` : ''}
    </div>
  `;
}

// ── SNIPER FLEET ─────────────────────────────────────────────────────
function SniperFleet() {
  const [agents, setAgents] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);

  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/agents/status').then(x => x.json());
      setAgents(r.agents || []);
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

  const doToggle = async (id) => {
    const a = agents.find(x => x.id === id);
    const label = a?.enabled ? 'disable' : 'enable';
    if (!confirm(`${label.charAt(0).toUpperCase() + label.slice(1)} ${a?.name || id} agent?`)) return;
    setBusy(id);
    try {
      await apiFetch(`/api/agents/${id}/toggle`, { method: 'POST' });
      await reload();
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Sniper Fleet</div><div class="stub-body">${err}</div></div>`;

  const activeCount = (agents || []).filter(a => a.status === 'ACTIVE').length;
  const idleCount = (agents || []).filter(a => a.status === 'IDLE').length;
  const offlineCount = (agents || []).filter(a => a.status === 'OFFLINE').length;

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Sniper Fleet</div>
          <div class="section-sub">Active agents · lane status · targeting</div>
        </div>
        <div class="section-sub">Auto-refresh · 10s</div>
      </div>
      <div class="sf-summary">
        <span class="sf-summary-tag">Active: <strong style=${{color: 'var(--signal-teal)'}}>${activeCount}</strong></span>
        <span class="sf-summary-tag">Idle: <strong style=${{color: 'var(--status-amber)'}}>${idleCount}</strong></span>
        <span class="sf-summary-tag">Offline: <strong style=${{color: 'var(--empire-mist)'}}>${offlineCount}</strong></span>
      </div>
      ${activeCount + idleCount + offlineCount > 0 ? html`<div class="chart-panel">
        <div class="chart-panel-h">
          <div class="chart-panel-title">Agent Status</div>
          <div class="chart-panel-tag">${activeCount + idleCount + offlineCount} total agents</div>
        </div>
        ${(() => {
          const sd = [];
          if (activeCount > 0) sd.push({label: 'Active', value: activeCount, color: 'var(--signal-teal)'});
          if (idleCount > 0) sd.push({label: 'Idle', value: idleCount, color: 'var(--status-amber)'});
          if (offlineCount > 0) sd.push({label: 'Offline', value: offlineCount, color: 'var(--empire-mist)'});
          return html`<${DonutChart} data=${sd} size=${108} strokeWidth=${22} />`;
        })()}
      </div>` : ''}
      ${!agents
        ? html`<div class="stub"><div class="stub-body">Loading agent status…</div></div>`
        : html`
      <div class="sf-grid">
        ${agents.length === 0
          ? html`<div class="stub" style=${{gridColumn: '1 / -1'}}><div class="stub-body">No agents found.</div></div>`
          : agents.map(a => {
            const statusCls = a.status || 'OFFLINE';
            const ping = a.last_ping
              ? ((new Date() - new Date(a.last_ping)) / 1000 < 120 ? 'now' : (a.last_ping || '').slice(11,19))
              : '—';
            return html`
            <div class="sf-card" key=${a.id}>
              <div class="sf-card-top">
                <div class="sf-card-info">
                  <div class="sf-card-name">${a.name || a.id}</div>
                  <div class="sf-card-type">${a.type || '—'}</div>
                </div>
                <span class=${'sf-bdg ' + statusCls}>
                  <span class="sf-bdg-dot"></span>${statusCls}
                </span>
              </div>
              <div class="sf-leads">${a.leads_today ?? 0}<div class="sf-leads-lbl">leads today</div></div>
              <div class="sf-card-meta">
                <span>Last ping: ${ping}</span>
                <button class=${'sf-toggle ' + (a.enabled ? 'on' : 'off')} disabled=${busy === a.id} onClick=${() => doToggle(a.id)}>
                  ${busy === a.id ? '…' : (a.enabled ? 'ON' : 'OFF')}
                </button>
              </div>
            </div>
          `})}
      </div>
      `}
    </div>
  `;
}

// ── STUB SECTION (other tabs) ────────────────────────────────────────
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
            active.id === 'audit'       ? html`<${Audit} />` :            active.id === 'neural-core'   ? html`<${AgiLoop} />` :
            active.id === 'holo-map'      ? html`<${HoloMap} />` :
            active.id === 'partners'      ? html`<${Partners} />` :
            active.id === 'operators'     ? html`<${Operators} />` :
            active.id === 'governor'      ? html`<${Governor} />` :
            active.id === 'sniper-fleet'  ? html`<${SniperFleet} />` :
            active.id === 'health-monitor' ? html`<${HealthMonitor} />` :
            html`<${Stub} section=${active} />`
          }
        </section>
      </main>
    </div>
  `;
}

createRoot(document.getElementById('root')).render(html`<${App} />`);
"""
