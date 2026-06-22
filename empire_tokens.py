"""
Empire V49 · Design Tokens
==========================
Single source of truth for the Empire AI design system.
Colors extracted directly from the brand logo (teal wave + cyan pulse).

Usage in views:
    from empire_tokens import EMPIRE_TOKENS_CSS, EMPIRE_FONTS

    @app.get("/view/scout")
    async def view_scout():
        return HTMLResponse(f'<html><head>{EMPIRE_FONTS}<style>{EMPIRE_TOKENS_CSS}</style>...')

Or, recommended, use the base_layout() helper in views.py which wires
fonts + tokens + chrome automatically.
"""

# ─────────────────────────────────────────────────────────────────────────────
# FONTS — loaded from Google Fonts. Geist for UI, Geist Mono for numbers.
# Inter and JetBrains Mono kept as fallbacks for clients that block Geist.
# ─────────────────────────────────────────────────────────────────────────────
EMPIRE_FONTS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@100;200;300;400;500;600;700;800;900&family=Geist+Mono:wght@300;400;500;600;700&family=Inter:wght@100;200;300;400;500;600;700;900&family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/dist/tabler-icons.min.css">
""".strip()

# ─────────────────────────────────────────────────────────────────────────────
# CSS VARIABLES — every color, font, motion timing, and shadow.
# Pulled straight from the Empire AI brand logo. Do not edit ad-hoc — change
# here, propagates everywhere.
# ─────────────────────────────────────────────────────────────────────────────
EMPIRE_TOKENS_CSS = """
:root {
  /* ── CANVAS (logo backdrop tones) ─────────────────────────────── */
  --empire-black:      #030810;   /* deepest — page edge */
  --empire-canvas:     #0A1A2F;   /* primary background */
  --empire-canvas-2:   #0E1F36;   /* gradient lower stop */
  --empire-surface:    #15263F;   /* panel face */
  --empire-elevated:   #1A2D4A;   /* hover / nested panel */
  --empire-glass:      rgba(21, 38, 63, 0.6);
  --empire-overlay:    rgba(10, 26, 47, 0.85);

  /* ── BRAND (extracted from logo gradient) ─────────────────────── */
  --signal-teal:       #44E5B8;   /* logo wave side · "predictive / live" */
  --signal-teal-dim:   #1FB890;
  --signal-teal-glow:  rgba(68, 229, 184, 0.6);
  --signal-teal-soft:  rgba(68, 229, 184, 0.08);

  --strike-cyan:       #5AC8FA;   /* logo pulse side · "strike / connected" */
  --strike-cyan-dim:   #2BA8E0;
  --strike-cyan-glow:  rgba(90, 200, 250, 0.6);
  --strike-cyan-soft:  rgba(90, 200, 250, 0.08);

  --empire-blue:       #1E88E5;   /* deep accent for big actions */

  /* ── TEXT ─────────────────────────────────────────────────────── */
  --empire-white:      #F8FAFD;
  --empire-silver:     #C8D4E4;
  --empire-mist:       #7A8CA3;
  --empire-fog:        #4A5A72;
  --empire-shadow:     #2A3A52;

  /* ── STATUS ───────────────────────────────────────────────────── */
  --status-amber:      #F5A623;   /* warning · use only when real */
  --status-amber-soft: rgba(245, 166, 35, 0.08);
  --status-red:        #FF4757;   /* critical · use only when broken */
  --status-red-soft:   rgba(255, 71, 87, 0.08);
  --status-success:    var(--signal-teal);

  /* ── STRUCTURE ────────────────────────────────────────────────── */
  --empire-divider:    rgba(122, 140, 163, 0.12);
  --empire-border:     rgba(122, 140, 163, 0.18);
  --empire-border-hi:  rgba(122, 140, 163, 0.32);

  /* ── TYPOGRAPHY ───────────────────────────────────────────────── */
  --font-ui:           'Geist', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono:         'Geist Mono', 'JetBrains Mono', 'SF Mono', Menlo, monospace;
  --font-display:      'Geist', 'Inter', sans-serif;

  /* ── MOTION ───────────────────────────────────────────────────── */
  --pulse-duration:    1.8s;
  --sonar-duration:    2s;
  --ease-out-empire:   cubic-bezier(0.16, 1, 0.3, 1);
  --ease-snap:         cubic-bezier(0.4, 0, 0.2, 1);

  /* ── EFFECTS ──────────────────────────────────────────────────── */
  --glow-signal:       0 0 16px var(--signal-teal-glow);
  --glow-strike:       0 0 16px var(--strike-cyan-glow);
  --glow-soft:         0 0 24px rgba(68, 229, 184, 0.15);
  --shadow-elevated:   0 20px 60px rgba(0, 0, 0, 0.4);
  --shadow-panel:      0 8px 24px rgba(0, 0, 0, 0.3);

  /* ── RADII ────────────────────────────────────────────────────── */
  --radius-xs:         2px;
  --radius-sm:         4px;
  --radius-md:         8px;
  --radius-lg:         12px;
  --radius-xl:         18px;
  --radius-pill:       999px;

  /* ── SPACING SCALE ────────────────────────────────────────────── */
  --space-1:           4px;
  --space-2:           8px;
  --space-3:           12px;
  --space-4:           16px;
  --space-5:           20px;
  --space-6:           24px;
  --space-8:           32px;
  --space-10:          40px;
  --space-12:          48px;
}
""".strip()

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL BASE STYLES — applied to every Empire view.
# Includes: reset, body atmosphere, scrollbars, keyframes, base utilities.
# ─────────────────────────────────────────────────────────────────────────────
EMPIRE_BASE_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body { height: 100%; }

body {
  background: var(--empire-canvas);
  color: var(--empire-white);
  font-family: var(--font-ui);
  letter-spacing: -0.02em;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  font-feature-settings: 'ss01' 1, 'cv11' 1;
}

/* Ambient atmosphere — radial glow at corridor edges + subtle grid */
body::before {
  content: '';
  position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background:
    radial-gradient(ellipse 60% 40% at 15% 15%, rgba(68, 229, 184, 0.06) 0%, transparent 50%),
    radial-gradient(ellipse 60% 40% at 85% 85%, rgba(90, 200, 250, 0.05) 0%, transparent 50%);
}

/* Grid texture — barely visible mission-control vibe */
body::after {
  content: '';
  position: fixed; inset: 0; pointer-events: none; z-index: 0; display: none;
  background-image:
    linear-gradient(rgba(68, 229, 184, 0.015) 1px, transparent 1px),
    linear-gradient(90deg, rgba(68, 229, 184, 0.015) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 90%);
}

/* Custom scrollbars — thin and tasteful */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--empire-shadow);
  border-radius: var(--radius-sm);
}
::-webkit-scrollbar-thumb:hover { background: var(--empire-mist); }

/* Selection */
::selection { background: var(--signal-teal-soft); color: var(--signal-teal); }

/* Focus rings — accessible without being ugly */
:focus-visible {
  outline: 1px solid var(--signal-teal);
  outline-offset: 2px;
}

/* Reusable keyframes */
@keyframes empire-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(0.88); }
}
@keyframes empire-sonar {
  0%   { transform: scale(0.8); opacity: 1; }
  100% { transform: scale(2.5); opacity: 0; }
}
@keyframes empire-shimmer {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}
@keyframes empire-fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: none; }
}
@keyframes empire-fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@keyframes empire-scan {
  0%   { top: -10%; opacity: 0; }
  20%  { opacity: 1; }
  80%  { opacity: 1; }
  100% { top: 110%; opacity: 0; }
}

/* Accessibility helper */
.sr-only {
  position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
""".strip()

# ─────────────────────────────────────────────────────────────────────────────
# COMPONENT LIBRARY CSS — Reusable Empire primitives.
# Cards, stat-chips, badges, buttons, inputs, tables, sonar pulses.
# These are the same primitives used in the Cinematic Command Deck mockup.
# ─────────────────────────────────────────────────────────────────────────────
EMPIRE_COMPONENTS_CSS = """
/* ── PULSE INDICATOR ─────────────────────────────────────────────── */
.e-pulse-pill {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: 6px 14px;
  background: var(--signal-teal-soft);
  border: 1px solid rgba(68, 229, 184, 0.2);
  border-radius: var(--radius-pill);
  font-family: var(--font-mono); font-size: 10px;
  color: var(--signal-teal);
  letter-spacing: 0.25em; font-weight: 600;
  text-transform: uppercase;
}
.e-pulse-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--signal-teal);
  box-shadow: var(--glow-signal);
  animation: empire-pulse var(--pulse-duration) ease-in-out infinite;
}
.e-pulse-dot.cyan {
  background: var(--strike-cyan);
  box-shadow: var(--glow-strike);
}
.e-pulse-dot.amber {
  background: var(--status-amber);
  box-shadow: 0 0 12px rgba(245, 166, 35, 0.6);
  animation-duration: 1.2s;
}
.e-pulse-dot.red {
  background: var(--status-red);
  box-shadow: 0 0 12px rgba(255, 71, 87, 0.7);
  animation-duration: 1s;
}

/* ── PANEL / CARD ────────────────────────────────────────────────── */
.e-panel {
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: var(--space-5);
  transition: border-color 0.25s, transform 0.25s;
  animation: empire-fade-up 0.5s var(--ease-out-empire) both;
}
.e-panel:hover {
  border-color: var(--empire-border);
}
.e-panel-glass {
  background: var(--empire-glass);
  backdrop-filter: blur(40px);
}

/* ── STAT CHIP ───────────────────────────────────────────────────── */
.e-stat {
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: 18px 20px;
  position: relative;
  overflow: hidden;
  transition: all 0.25s var(--ease-out-empire);
  animation: empire-fade-up 0.4s var(--ease-out-empire) both;
}
.e-stat:hover {
  border-color: var(--empire-border);
  transform: translateY(-2px);
}
.e-stat::before {
  content: '';
  position: absolute; top: 0; left: 0;
  width: 2px; height: 100%;
  background: var(--accent, var(--signal-teal));
}
.e-stat.teal  { --accent: var(--signal-teal); }
.e-stat.cyan  { --accent: var(--strike-cyan); }
.e-stat.amber { --accent: var(--status-amber); }
.e-stat.red   { --accent: var(--status-red); }
.e-stat.muted { --accent: var(--empire-shadow); }

.e-stat-label {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--empire-mist);
  letter-spacing: 0.2em; text-transform: uppercase;
  font-weight: 600;
}
.e-stat-value {
  font-family: var(--font-mono); font-weight: 600;
  font-size: 32px; line-height: 1;
  margin-top: 8px;
  letter-spacing: -0.04em;
  color: var(--empire-white);
  font-feature-settings: 'tnum' 1;
}
.e-stat-value.teal  { color: var(--signal-teal); }
.e-stat-value.cyan  { color: var(--strike-cyan); }
.e-stat-value.amber { color: var(--status-amber); }
.e-stat-value.red   { color: var(--status-red); }

.e-stat-delta {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--empire-mist);
  margin-top: 6px;
}
.e-stat-delta.up   { color: var(--signal-teal); }
.e-stat-delta.warn { color: var(--status-amber); }
.e-stat-delta.down { color: var(--status-red); }

.e-stat-spark {
  position: absolute; bottom: 6px; right: 6px;
  width: 60px; height: 22px; opacity: 0.5;
  pointer-events: none;
}

/* ── BUTTON ──────────────────────────────────────────────────────── */
.e-btn {
  background: var(--signal-teal);
  color: var(--empire-black);
  border: 1px solid var(--signal-teal);
  font-family: var(--font-ui);
  font-weight: 700; font-size: 13px;
  letter-spacing: -0.01em;
  padding: 12px 24px;
  cursor: pointer;
  transition: all 0.2s var(--ease-snap);
  border-radius: var(--radius-sm);
}
.e-btn:hover {
  background: transparent;
  color: var(--signal-teal);
  box-shadow: var(--glow-soft);
}
.e-btn:active { transform: scale(0.98); }
.e-btn:disabled { opacity: 0.4; cursor: wait; }

.e-btn-cyan {
  background: var(--strike-cyan);
  color: var(--empire-black);
  border-color: var(--strike-cyan);
}
.e-btn-cyan:hover {
  background: transparent;
  color: var(--strike-cyan);
}

.e-btn-ghost {
  background: transparent;
  color: var(--empire-mist);
  border: 1px solid var(--empire-border);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  padding: 8px 14px;
  cursor: pointer;
  transition: all 0.2s;
  border-radius: var(--radius-sm);
}
.e-btn-ghost:hover {
  color: var(--empire-white);
  border-color: var(--empire-border-hi);
}

/* ── INPUT / TEXTAREA ────────────────────────────────────────────── */
.e-field {
  display: flex; flex-direction: column;
  gap: var(--space-2);
}
.e-field-label {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--empire-mist);
  letter-spacing: 0.14em; text-transform: uppercase;
}
.e-input, .e-textarea, .e-select {
  background: rgba(0, 0, 0, 0.4);
  color: var(--empire-white);
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono); font-size: 13px;
  padding: 12px 14px;
  outline: none;
  width: 100%;
  transition: border-color 0.2s, box-shadow 0.2s;
  letter-spacing: -0.01em;
}
.e-input:focus, .e-textarea:focus, .e-select:focus {
  border-color: var(--signal-teal);
  box-shadow: 0 0 0 1px var(--signal-teal-glow);
}
.e-input::placeholder, .e-textarea::placeholder {
  color: var(--empire-fog);
}
.e-textarea {
  resize: vertical;
  line-height: 1.7;
  min-height: 100px;
}

/* ── BADGE ───────────────────────────────────────────────────────── */
.e-badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px;
  font-family: var(--font-mono); font-size: 9px;
  letter-spacing: 0.12em; text-transform: uppercase;
  border: 1px solid;
  border-radius: var(--radius-xs);
  font-weight: 600;
}
.e-badge-teal  { color: var(--signal-teal); border-color: rgba(68, 229, 184, 0.3); background: var(--signal-teal-soft); }
.e-badge-cyan  { color: var(--strike-cyan); border-color: rgba(90, 200, 250, 0.3); background: var(--strike-cyan-soft); }
.e-badge-amber { color: var(--status-amber); border-color: rgba(245, 166, 35, 0.3); background: var(--status-amber-soft); }
.e-badge-red   { color: var(--status-red); border-color: rgba(255, 71, 87, 0.3); background: var(--status-red-soft); }
.e-badge-muted { color: var(--empire-mist); border-color: var(--empire-border); }

/* ── SONAR PULSE (for live calls / strikes) ──────────────────────── */
.e-sonar {
  position: relative;
  width: 12px; height: 12px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.e-sonar-dot {
  width: 8px; height: 8px; border-radius: 50%;
  z-index: 2;
}
.e-sonar.live .e-sonar-dot {
  background: var(--signal-teal);
  box-shadow: var(--glow-signal);
}
.e-sonar.connected .e-sonar-dot {
  background: var(--strike-cyan);
  box-shadow: var(--glow-strike);
}
.e-sonar.live::before,
.e-sonar.connected::before {
  content: '';
  position: absolute;
  width: 100%; height: 100%;
  border-radius: 50%;
  border: 1px solid currentColor;
  animation: empire-sonar var(--sonar-duration) ease-out infinite;
}
.e-sonar.live::before      { color: var(--signal-teal); }
.e-sonar.connected::before { color: var(--strike-cyan); }

/* ── TABLE ───────────────────────────────────────────────────────── */
.e-table { width: 100%; border-collapse: collapse; }
.e-table th {
  font-family: var(--font-mono); font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.18em; text-transform: uppercase;
  font-weight: 600;
  padding: 12px 16px;
  border-bottom: 1px solid var(--empire-divider);
  text-align: left;
}
.e-table td {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(122, 140, 163, 0.04);
  font-family: var(--font-ui); font-size: 13px;
  color: var(--empire-silver);
  letter-spacing: -0.01em;
}
.e-table tr { animation: empire-fade-up 0.3s var(--ease-out-empire) both; }
.e-table tr:hover td { background: rgba(255, 255, 255, 0.015); }

/* ── CORRIDOR BAR (gradient-fill with shimmer) ───────────────────── */
.e-corridor {
  margin-bottom: 14px;
}
.e-corridor-row {
  display: flex; justify-content: space-between;
  font-size: 12px; margin-bottom: 6px;
  font-family: var(--font-ui);
}
.e-corridor-name {
  color: var(--empire-silver);
  font-weight: 500;
}
.e-corridor-value {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--empire-white);
}
.e-corridor-track {
  height: 4px;
  background: rgba(10, 26, 47, 0.8);
  border-radius: 2px;
  overflow: hidden;
}
.e-corridor-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--signal-teal) 0%, var(--strike-cyan) 100%);
  border-radius: 2px;
  box-shadow: 0 0 8px rgba(68, 229, 184, 0.4);
  position: relative;
  overflow: hidden;
  transition: width 0.9s var(--ease-out-empire);
}
.e-corridor-fill::after {
  content: '';
  position: absolute;
  top: 0; left: -100%;
  width: 100%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.25), transparent);
  animation: empire-shimmer 3s ease-in-out infinite;
}

/* ── LIVE CALL ROW ───────────────────────────────────────────────── */
.e-call {
  display: flex; align-items: center;
  gap: var(--space-3);
  padding: 12px 14px;
  background: var(--empire-elevated);
  border-radius: var(--radius-sm);
  border-left: 2px solid;
  transition: all 0.2s var(--ease-snap);
  margin-bottom: 8px;
}
.e-call:hover {
  background: rgba(26, 45, 74, 0.9);
  transform: translateX(2px);
}
.e-call.live      { border-left-color: var(--signal-teal); }
.e-call.connected { border-left-color: var(--strike-cyan); }
.e-call.waterfall { border-left-color: var(--status-amber); }
.e-call.settled   { border-left-color: var(--signal-teal); opacity: 0.7; }

.e-call-body {
  flex: 1; min-width: 0;
}
.e-call-title {
  font-size: 13px; font-weight: 500;
  color: var(--empire-white);
  margin-bottom: 3px;
  letter-spacing: 0.2px;
}
.e-call-status {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--empire-mist);
  letter-spacing: 0.3px;
}
.e-call-value {
  font-family: var(--font-mono);
  font-size: 15px; font-weight: 600;
  letter-spacing: -0.3px;
}
.e-call-value.teal { color: var(--signal-teal); }

/* ── PAGE LAYOUT HELPERS ─────────────────────────────────────────── */
.e-page {
  padding: 32px 36px;
  height: 100%;
  overflow-y: auto;
  position: relative;
  z-index: 1;
}

.e-page-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding-bottom: 20px; margin-bottom: 28px;
  border-bottom: 1px solid var(--empire-divider);
  animation: empire-fade-up 0.5s var(--ease-out-empire) both;
  gap: var(--space-4);
  flex-wrap: wrap;
}
.e-page-title {
  font-family: var(--font-display);
  font-weight: 200;
  font-size: 32px;
  letter-spacing: -0.04em;
  color: var(--empire-white);
  line-height: 1;
}
.e-page-title em {
  font-style: italic;
  font-weight: 700;
  color: var(--signal-teal);
}
.e-page-sub {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--empire-fog);
  letter-spacing: 0.22em;
  text-transform: uppercase;
  margin-top: 8px;
}

.e-grid {
  display: grid; gap: var(--space-3);
}
.e-grid-2 { grid-template-columns: repeat(2, 1fr); }
.e-grid-3 { grid-template-columns: repeat(3, 1fr); }
.e-grid-4 { grid-template-columns: repeat(4, 1fr); }
.e-grid-main { grid-template-columns: 1.4fr 1fr; }

@media (max-width: 880px) {
  .e-grid-3, .e-grid-4 { grid-template-columns: repeat(2, 1fr); }
  .e-grid-main { grid-template-columns: 1fr; }
  .e-page { padding: 20px 16px; }
}

.e-section-label {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--empire-mist);
  letter-spacing: 0.22em; text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 14px;
}
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helper: full <head> contents for any view.
# ─────────────────────────────────────────────────────────────────────────────
def empire_head(
    title: str = "Empire AI · Command Deck",
    extra: str = "",
    meta_html: str = "",
    description: str = "",
    keywords: str = "",
    canonical: str = "",
    page: str = "",
) -> str:
    """Returns the complete <head> block (fonts + tokens + base + components).

    Args:
        title: Page title (used for og:title, twitter:title).
        extra: Additional CSS to inject into <style>.
        meta_html: Raw HTML to inject before </head> (e.g. structured data).
        description: Meta description (155 chars). Auto-generated from title if empty.
        keywords: Comma-separated meta keywords.
        canonical: Canonical URL.
        page: One of the SEO_TAGS keys (e.g. 'splash', 'pricing'). Overrides
               description/keywords/canonical with centralized SEO metadata.
    """
    import html as _html

    # Resolve from SEO metadata module if page key provided
    if page:
        try:
            from empire_seo_meta import SEO_TAGS as _seo
            tags = _seo.get(page, {})
            if tags:
                if tags.get("description"):
                    description = tags["description"]
                if tags.get("keywords"):
                    keywords = tags["keywords"]
                if tags.get("canonical"):
                    canonical = tags["canonical"]
        except ImportError:
            pass

    # Fallback description from title if none provided
    if not description:
        base = "AI-powered lead generation, contractor dispatch, and revenue automation."
        description = f"Empire AI — {base}"

    # Build SEO meta tags
    desc_esc = _html.escape(description[:300])
    title_esc = _html.escape(title)
    kw_esc = _html.escape(keywords[:500]) if keywords else ""
    canonical_url = canonical or "https://empire-ai.co.uk/"

    seo_meta = f"""
<meta name="description" content="{desc_esc}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title_esc}">
<meta property="og:description" content="{desc_esc}">
<meta property="og:url" content="{canonical_url}">
<meta property="og:site_name" content="Empire AI">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_esc}">
<meta name="twitter:description" content="{desc_esc}">
<link rel="canonical" href="{canonical_url}">"""

    if kw_esc:
        seo_meta += f'\n<meta name="keywords" content="{kw_esc}">'

    seo_meta += '\n<meta name="robots" content="index, follow">'

    # ── Headroom.js auto-hide header ─────────────────────────────────────
    try:
        from empire_headroom_js import EMPIRE_HEADROOM_CSS, EMPIRE_HEADROOM_JS
        _headroom_css = EMPIRE_HEADROOM_CSS
        _headroom_js = EMPIRE_HEADROOM_JS
    except ImportError:
        _headroom_css = ""
        _headroom_js = ""

    return f"""<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0A1A2F">
<title>{title_esc}</title>
{seo_meta}
{EMPIRE_FONTS}
{_headroom_js}
<style>
{EMPIRE_TOKENS_CSS}
{EMPIRE_BASE_CSS}
{EMPIRE_COMPONENTS_CSS}
{_headroom_css}
{extra}
</style>
{meta_html}
</head>"""


# ─────────────────────────────────────────────────────────────────────────────
# JWT helpers for unsubscribe links + session tokens.
# Used by empire_email.py for one-click unsubscribe URLs.
# ─────────────────────────────────────────────────────────────────────────────
import os as _os
import datetime as _dt

try:
    import jwt as _jwt
except ImportError:
    _jwt = None

_SECRET_KEY = _os.environ.get("SECRET_KEY", "empire-rotate-me-to-a-real-secret")
_ALGORITHM = "HS256"


def _sign_token(data: dict) -> str:
    """Sign a payload dict and return a JWT string."""
    if _jwt is None:
        raise RuntimeError("PyJWT not installed — pip install pyjwt")
    payload = dict(data)
    if "exp" not in payload:
        payload["exp"] = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=365)
    return _jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def _verify_token(token: str):
    """Verify a JWT string. Returns the decoded payload dict, or None on failure."""
    if _jwt is None or not token:
        return None
    try:
        return _jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except Exception:
        return None
