"""
Empire V49 · Base Layout
========================
The Cinematic Command Deck shell. Every operator-facing view inherits this
chrome: topbar (brand + pulse + clock), sidebar (module nav + AGI status),
content slot, and NWS ticker at the bottom.

Usage:
    from empire_tokens import empire_head
    from empire_layout import base_layout

    @app.get("/view/scout")
    async def view_scout(token: str = ""):
        content = '<div class="e-page">...</div>'
        return HTMLResponse(base_layout(
            title="Scout",
            subtitle="Live NWS Radar",
            content=content,
            active_module="scout",
            token=token,
        ))

This replaces the duplicated header/sidebar/ticker HTML that was previously
inlined in all 8 view routes.
"""

from empire_tokens import empire_head
from empire_live import LIVE_CLIENT_JS

# ─────────────────────────────────────────────────────────────────────────────
# MODULE NAV — defines the sidebar items. Single source of truth.
# Add new views here; the sidebar updates automatically.
# ─────────────────────────────────────────────────────────────────────────────
MODULES = [
    # (slug, num, name, icon, section)
    # section: "ops" → Operations group · "sov" → Sovereign group
    ("pulse",       "01", "Pulse",       "ti-activity-heartbeat", "ops"),
    ("pipeline",    "02", "Pipeline",    "ti-line-dotted",        "ops"),
    ("dispatch",    "03", "Dispatch",    "ti-route",              "ops"),
    ("inbound",     "04", "Inbound",     "ti-phone-incoming",     "ops"),
    ("leads", "04.5", "Leads", "ti-target", "ops"),
    ("payouts",     "05", "Payouts",     "ti-coin",               "ops"),
    ("contractors", "06", "Contractors", "ti-users-group",        "ops"),
    ("console",     "07", "Console",     "ti-terminal-2",         "sov"),
    ("audit",       "08", "Audit Log",   "ti-shield-check",       "sov"),
    ("operators",   "09", "Operators",   "ti-id-badge-2",         "sov"),
]

# Each module slug maps to its URL. `pulse` is the canonical /command page;
# the rest are /command/<slug>. This keeps the original URL working.
def _module_href(slug: str) -> str:
    return "/command" if slug == "pulse" else f"/command/{slug}"


def _layout_css() -> str:
    """Layout-specific CSS — sits on top of empire_tokens components."""
    return """
    /* ── APP SHELL ────────────────────────────────────────────────── */
    html, body { overflow: hidden; }
    body { display: flex; flex-direction: column; }

    /* TOPBAR */
    .e-topbar {
      height: 56px; flex-shrink: 0; z-index: 10;
      background: var(--empire-overlay);
      backdrop-filter: blur(40px);
      border-bottom: 1px solid var(--empire-divider);
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 28px;
      position: relative;
    }
    .e-brand {
      display: flex; align-items: center; gap: 16px;
    }
    .e-brand-mark {
      display: flex; align-items: baseline;
    }
    .e-brand-empire {
      font-family: var(--font-display);
      font-weight: 700;
      font-size: 18px;
      letter-spacing: 0.18em;
      color: var(--empire-white);
    }
    .e-brand-ai {
      font-family: var(--font-display);
      font-weight: 700;
      font-size: 18px;
      letter-spacing: 0.18em;
      color: var(--strike-cyan);
      margin-left: 6px;
    }
    .e-brand-sub {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.25em;
      text-transform: uppercase;
      margin-left: 16px;
      padding-left: 16px;
      border-left: 1px solid var(--empire-divider);
    }
    .e-topbar-right {
      display: flex; align-items: center; gap: 20px;
    }
    .e-clock {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      letter-spacing: 0.15em;
    }
    .e-clock .e-clock-time {
      color: var(--signal-teal);
      font-weight: 600;
    }

    /* LAYOUT */
    .e-layout {
      display: flex;
      flex: 1;
      overflow: hidden;
      position: relative;
      z-index: 1;
    }

    /* SIDEBAR */
    .e-sidebar {
      width: 220px; flex-shrink: 0;
      background: var(--empire-overlay);
      backdrop-filter: blur(40px);
      border-right: 1px solid var(--empire-divider);
      display: flex; flex-direction: column;
      overflow: hidden;
    }
    .e-nav-section {
      padding: 18px 0 10px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .e-nav-label {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.28em;
      padding: 0 18px 10px;
      text-transform: uppercase;
    }
    .e-nav-item {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 18px;
      cursor: pointer;
      user-select: none;
      transition: background 0.2s, color 0.2s;
      position: relative;
      text-decoration: none;
    }
    .e-nav-item::before {
      content: '';
      position: absolute; left: 0; top: 0; bottom: 0;
      width: 1px;
      background: transparent;
      transition: background 0.2s;
    }
    .e-nav-item:hover { background: rgba(255, 255, 255, 0.02); }
    .e-nav-item:hover::before { background: var(--empire-shadow); }
    .e-nav-item.active { background: var(--signal-teal-soft); }
    .e-nav-item.active::before {
      background: var(--signal-teal);
      box-shadow: var(--glow-signal);
    }
    .e-nav-icon {
      font-size: 16px;
      color: var(--empire-mist);
      transition: color 0.2s;
    }
    .e-nav-item.active .e-nav-icon { color: var(--signal-teal); }
    .e-nav-item.special .e-nav-icon { color: var(--strike-cyan); }
    .e-nav-num {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-shadow);
      letter-spacing: 0.1em;
      flex-shrink: 0;
      width: 16px;
    }
    .e-nav-name {
      font-family: var(--font-ui);
      font-weight: 400;
      font-size: 13px;
      letter-spacing: -0.01em;
      color: var(--empire-silver);
      flex: 1;
    }
    .e-nav-item.active .e-nav-name {
      color: var(--empire-white);
      font-weight: 500;
    }
    .e-nav-item.special .e-nav-name { color: var(--strike-cyan); }

    /* AGI BLOCK at sidebar bottom */
    .e-agi {
      margin-top: auto;
      padding: 16px 18px;
      border-top: 1px solid var(--empire-divider);
    }
    .e-agi-label {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--signal-teal);
      letter-spacing: 0.22em;
      margin-bottom: 8px;
      opacity: 0.7;
      text-transform: uppercase;
    }
    .e-agi-row {
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-mist);
      display: flex; align-items: center; gap: 6px;
      margin-bottom: 4px;
    }
    .e-agi-dot {
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--empire-shadow);
      transition: background 0.3s, box-shadow 0.3s;
    }
    .e-agi-dot.online {
      background: var(--signal-teal);
      box-shadow: var(--glow-signal);
      animation: empire-pulse var(--pulse-duration) ease-in-out infinite;
    }
    .e-agi-dot.scanning {
      background: var(--strike-cyan);
      box-shadow: var(--glow-strike);
    }
    .e-agi-dot.error {
      background: var(--status-red);
      box-shadow: 0 0 8px var(--status-red);
    }
    .e-agi-stats {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-shadow);
      letter-spacing: 0.08em;
      margin-top: 6px;
    }
    .e-agi-stats .v { color: var(--empire-silver); }

    /* MAIN CONTENT */
    .e-main {
      flex: 1;
      background: linear-gradient(180deg, var(--empire-canvas) 0%, var(--empire-canvas-2) 100%);
      overflow: hidden;
      position: relative;
    }
    .e-frame {
      width: 100%; height: 100%; border: none;
      display: block;
    }
    .e-main-scroll {
      width: 100%; height: 100%;
      overflow-y: auto;
    }

    /* TICKER */
    .e-ticker {
      height: 32px; flex-shrink: 0; z-index: 10;
      background: var(--empire-overlay);
      backdrop-filter: blur(40px);
      border-top: 1px solid var(--empire-divider);
      display: flex; align-items: center;
      overflow: hidden;
    }
    .e-ticker-label {
      flex-shrink: 0;
      padding: 0 16px;
      height: 100%;
      display: flex; align-items: center; gap: 6px;
      font-family: var(--font-mono);
      font-size: 9px;
      font-weight: 600;
      color: var(--signal-teal);
      letter-spacing: 0.22em;
      text-transform: uppercase;
      border-right: 1px solid var(--empire-divider);
    }
    .e-ticker-track {
      flex: 1; overflow: hidden;
    }
    .e-ticker-inner {
      display: flex; white-space: nowrap;
      animation: empire-ticker-scroll 36s linear infinite;
    }
    @keyframes empire-ticker-scroll {
      0%   { transform: translateX(0); }
      100% { transform: translateX(-50%); }
    }
    .e-tick {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 0 24px; height: 32px;
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.04em;
    }
    .e-tick .dot {
      width: 4px; height: 4px; border-radius: 50%;
      flex-shrink: 0;
    }
    .e-tick.extreme .dot {
      background: var(--status-red);
      box-shadow: 0 0 5px var(--status-red);
      animation: empire-pulse 1.2s ease-in-out infinite;
    }
    .e-tick.severe .dot {
      background: var(--status-amber);
      box-shadow: 0 0 5px var(--status-amber);
    }
    .e-tick.default .dot {
      background: var(--empire-shadow);
    }
    .e-tick-event { color: var(--empire-silver); }
    .e-tick-area  { color: var(--signal-teal); opacity: 0.8; }
    .e-tick-sep   { color: var(--empire-shadow); padding: 0 4px; }
    """


def _sidebar_html(active_module: str) -> str:
    """Render the sidebar with active state set for `active_module`."""
    sections = {"ops": [], "sov": []}
    for slug, num, name, icon, section in MODULES:
        active_cls = " active" if slug == active_module else ""
        special_cls = " special" if section == "sov" else ""
        sections[section].append(f"""
        <a href="{_module_href(slug)}" class="e-nav-item{active_cls}{special_cls}" data-module="{slug}">
          <i class="ti {icon} e-nav-icon" aria-hidden="true"></i>
          <span class="e-nav-num">{num}</span>
          <span class="e-nav-name">{name}</span>
        </a>""")

    return f"""
    <aside class="e-sidebar" aria-label="Empire navigation">
      <div class="e-nav-section">
        <div class="e-nav-label">/ / Operations</div>
        {''.join(sections["ops"])}
      </div>
      <div class="e-nav-section" style="border-bottom:none;">
        <div class="e-nav-label">/ / Sovereign</div>
        {''.join(sections["sov"])}
      </div>
      <div class="e-agi">
        <div class="e-agi-label">/ / Subconscious Mind</div>
        <div class="e-agi-row">
          <span class="e-agi-dot" id="agi-dot"></span>
          <span id="agi-status">Idle</span>
        </div>
        <div class="e-agi-stats">
          cycles <span class="v" id="agi-cycles">0</span>
          · strikes <span class="v" id="agi-strikes">0</span>
        </div>
      </div>
    </aside>
    """


def _topbar_html(vault_total: str) -> str:
    """Render the topbar. No domain in header per V49 brand standard."""
    return f"""
    <header class="e-topbar" role="banner">
      <div class="e-brand">
        <div class="e-pulse-pill">
          <span class="e-pulse-dot"></span>
          <span>Strike Ready</span>
        </div>
        <div class="e-brand-mark">
          <span class="e-brand-empire">EMPIRE</span><span class="e-brand-ai">AI</span>
        </div>
        <span class="e-brand-sub">Predictive Revenue</span>
      </div>
      <div class="e-topbar-right">
        <div class="e-clock">
          <span class="e-clock-time" id="empire-clock">--:--:--</span>
        </div>
      </div>
    </header>
    """


def _ticker_html() -> str:
    """NWS ticker scrolling along the bottom. Refreshed by client JS."""
    return """
    <div class="e-ticker" role="region" aria-label="NWS alert ticker">
      <div class="e-ticker-label">
        <i class="ti ti-broadcast" aria-hidden="true"></i>
        <span>NWS</span>
      </div>
      <div class="e-ticker-track">
        <div class="e-ticker-inner" id="ticker-inner">
          <div class="e-tick default"><span class="dot"></span><span class="e-tick-event">Loading alerts</span></div>
        </div>
      </div>
    </div>
    """


def _shell_js() -> str:
    """JavaScript for live clock + AGI status (driven by /ws/live stats events)."""
    return """
    <script>
    (function() {
      // Session token lives in localStorage (set by /auth/verify) — used for
      // WS auth (?token=) and any explicit Authorization header fetches.
      // HTTP requests authenticate via the HttpOnly empire_session cookie.
      const TOKEN = new URLSearchParams(location.search).get('token')
        || localStorage.getItem('hub_token') || '';
      if (TOKEN && new URLSearchParams(location.search).get('token')) {
        localStorage.setItem('hub_token', TOKEN);
      }
      window.EMPIRE_TOKEN = TOKEN;

      // ── LIVE CLOCK ──
      function tickClock() {
        const now = new Date();
        const h = String(now.getHours()).padStart(2, '0');
        const m = String(now.getMinutes()).padStart(2, '0');
        const s = String(now.getSeconds()).padStart(2, '0');
        const el = document.getElementById('empire-clock');
        if (el) el.textContent = `${h}:${m}:${s}`;
      }
      tickClock();
      setInterval(tickClock, 1000);

      // ── AGI STATUS — driven by /ws/live `stats` events ──
      function applyAgi(agi) {
        const dot = document.getElementById('agi-dot');
        const txt = document.getElementById('agi-status');
        if (!dot || !txt) return;
        const stat = String(agi.status || 'idle').toLowerCase();
        dot.className = 'e-agi-dot';
        if (agi.running && stat === 'ok') {
          dot.classList.add('online');
          txt.textContent = 'Online';
          txt.style.color = 'var(--signal-teal)';
        } else if (stat === 'scanning') {
          dot.classList.add('scanning');
          txt.textContent = 'Scanning';
          txt.style.color = 'var(--strike-cyan)';
        } else if (stat.startsWith('error')) {
          dot.classList.add('error');
          txt.textContent = 'Error';
          txt.style.color = 'var(--status-red)';
        } else {
          txt.textContent = stat.charAt(0).toUpperCase() + stat.slice(1);
          txt.style.color = 'var(--empire-mist)';
        }
        const cyc = document.getElementById('agi-cycles');
        const stk = document.getElementById('agi-strikes');
        if (cyc) cyc.textContent = agi.cycles || 0;
        if (stk) stk.textContent = agi.strikes_total || 0;
      }

      // Subscribe once EMPIRE_LIVE is wired by LIVE_CLIENT_JS (loaded by views
      // that opt-in to live updates). Falls back silently on pages without WS.
      function bindLive() {
        if (window.EMPIRE_LIVE && window.EMPIRE_LIVE.on) {
          window.EMPIRE_LIVE.on('stats', payload => {
            if (payload && payload.agi) applyAgi(payload.agi);
          });
        } else {
          setTimeout(bindLive, 500);
        }
      }
      bindLive();
    })();
    </script>
    """


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API — Two layout helpers.
# ─────────────────────────────────────────────────────────────────────────────
def base_layout(
    title: str,
    content: str,
    active_module: str = "",
    subtitle: str = "",
    extra_css: str = "",
    extra_js: str = "",
    vault_total: str = "$0.00 USDC",
) -> str:
    """
    Full Cinematic Command Deck shell with sidebar + topbar + ticker.
    Use for every operator-facing /view/* page.

    Args:
        title:         Browser tab title and primary heading
        content:       HTML for the page body (typically wrapped in .e-page)
        active_module: Slug of the currently-active nav item (e.g. "scout")
        subtitle:      Optional subtitle shown under page title
        extra_css:     Additional CSS specific to this view
        extra_js:      Additional JS specific to this view
        vault_total:   USDC vault display string

    Returns:
        Complete HTML document as string.
    """
    head = empire_head(
        title=f"Empire AI · {title}",
        extra=_layout_css() + (extra_css or ""),
    )
    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>
{_topbar_html(vault_total)}
<div class="e-layout">
  {_sidebar_html(active_module)}
  <main class="e-main" role="main">
    <div class="e-main-scroll">
      {content}
    </div>
  </main>
</div>
{LIVE_CLIENT_JS}
{_shell_js()}
{extra_js or ''}
</body>
</html>"""


def section_stub(slug: str, title: str, blurb: str = "") -> str:
    """
    Placeholder section page — full chrome, empty content slot.
    Lets the sidebar work end-to-end before sections are built out.
    """
    content = f"""
    <div class="e-page">
      <div class="e-page-header">
        <div>
          <div class="e-page-title">{title}</div>
          <div class="e-page-sub">{blurb or 'Awaiting build · Phase 3'}</div>
        </div>
      </div>
      <div class="e-panel" style="text-align:center; padding:80px 32px;">
        <div style="font-family:var(--font-mono); font-size:10px; color:var(--empire-fog);
                    letter-spacing:0.22em; text-transform:uppercase; margin-bottom:14px;">
          Under construction
        </div>
        <div style="color:var(--empire-mist); font-size:13px; max-width:520px; margin:0 auto;">
          This section is wired in the nav but the view hasn't been built yet.
          Backing APIs are live · UI lands in Phase 3.
        </div>
      </div>
    </div>
    """
    return base_layout(
        title=title,
        content=content,
        active_module=slug,
        subtitle="Operator Console",
    )


def standalone_layout(
    title: str,
    content: str,
    extra_css: str = "",
    extra_js: str = "",
) -> str:
    """
    Empire-styled HTML without the sidebar/topbar chrome.
    Use for public pages like /sovereign, /alert/{slug}, /contractor/*.
    """
    head = empire_head(
        title=title,
        extra=extra_css,
    )
    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>
{content}
{extra_js or ''}
</body>
</html>"""
