"""
EMPIRE V49 · PAY-PER-CALL PRODUCT PAGE
=======================================
Dedicated landing page at /ppc explaining the live call routing model
and letting buyers sign up for call allocation.

Wire-up in hub.py:
    from empire_ppc import ppc_page

    @app.get("/ppc", response_class=HTMLResponse)
    async def ppc():
        return HTMLResponse(ppc_page())
"""

from empire_tokens import empire_head

# ── PPC NICHE DATA ────────────────────────────────────────────────────
# Sourced from CPL_BENCHMARKS in empire_pricing.py
# Only niches with viable PPC model are listed

_PPC_NICHES = [
    {
        "niche": "Plumbing",
        "category": "Home Services",
        "icon": "🔧",
        "cpl_range": "$14 – $150",
        "cpl_mid": 82,
        "trigger": "Emergency, burst pipe",
        "pacing": "24/7 — always-on",
        "volume": "High",
        "description": "Live call routing for emergency plumbing leads. Burst pipes, water heater failures, drain emergencies — speed wins every time.",
        "best_for": "Emergency service contractors, home warranty companies, property managers",
    },
    {
        "niche": "Roofing Restoration",
        "category": "Home Services",
        "icon": "🏠",
        "cpl_range": "$11 – $258",
        "cpl_mid": 134,
        "trigger": "Storm/hail, emergency",
        "pacing": "Storm-triggered — seasonal peaks",
        "volume": "Highest",
        "description": "Storm-damaged roofing leads in high-risk corridors. Hail damage, wind uplift, leak detection — 78% of homeowners hire the first responder.",
        "best_for": "Roofing contractors, restoration companies, insurance adjusters",
    },
    {
        "niche": "HVAC",
        "category": "Home Services",
        "icon": "❄️",
        "cpl_range": "$10 – $150",
        "cpl_mid": 80,
        "trigger": "Weather extremes, seasonal",
        "pacing": "Seasonal — summer/winter peaks",
        "volume": "High",
        "description": "Heating and cooling emergency calls. AC failures in July, furnace outages in January — predictable seasonal surges with high close rates.",
        "best_for": "HVAC contractors, home service franchises, property maintenance firms",
    },
    {
        "niche": "Electrical",
        "category": "Home Services",
        "icon": "⚡",
        "cpl_range": "$20 – $80",
        "cpl_mid": 50,
        "trigger": "Emergency/renovation",
        "pacing": "Steady — year-round",
        "volume": "Medium",
        "description": "Live electrical service calls. Outages, short circuits, code violations, and renovation wiring. Steady demand with consistent close rates.",
        "best_for": "Licensed electricians, electrical contractors, renovation firms",
    },
    {
        "niche": "Water Damage Restoration",
        "category": "Home Services",
        "icon": "💧",
        "cpl_range": "$40 – $200",
        "cpl_mid": 120,
        "trigger": "Flood/burst → immediate",
        "pacing": "24/7 — weather-dependent surges",
        "volume": "Medium-High",
        "description": "Immediate-response water damage leads. Burst pipes, flooding, sewage backups — every hour of delay compounds the damage.",
        "best_for": "Restoration companies, carpet cleaners, mold remediation specialists",
    },
    {
        "niche": "Addiction Treatment",
        "category": "Healthcare",
        "icon": "🏥",
        "cpl_range": "$150 – $500",
        "cpl_mid": 325,
        "trigger": "Avg patient LTV: $78k+",
        "pacing": "Steady — year-round",
        "volume": "Medium",
        "description": "High-value addiction treatment intake calls. Callers actively seeking help — LTV justifies premium CPL. Phone converts 3-5x better than web forms.",
        "best_for": "Treatment centers, detox facilities, behavioral health networks",
    },
    {
        "niche": "Assisted Living",
        "category": "Senior Care",
        "icon": "👴",
        "cpl_range": "$100 – $300",
        "cpl_mid": 200,
        "trigger": "Sales cycle: 3-6 months",
        "pacing": "Steady — year-round",
        "volume": "Growing",
        "description": "Senior care placement calls. Families researching assisted living options — high intent, long consideration cycle, high LTV.",
        "best_for": "Assisted living facilities, senior placement agencies, home health providers",
    },
    {
        "niche": "Personal Injury",
        "category": "Legal",
        "icon": "⚖️",
        "cpl_range": "$150 – $400",
        "cpl_mid": 275,
        "trigger": "Highest competition",
        "pacing": "Steady — year-round",
        "volume": "High value",
        "description": "Personal injury intake calls. Auto accidents, slip-and-fall, medical malpractice — callers actively seeking representation. 88% of legal search ends in a phone call.",
        "best_for": "PI law firms, mass tort practices, legal lead aggregators",
    },
]

# ── HOW IT WORKS STEPS ────────────────────────────────────────────────

_HOW_IT_WORKS = [
    {
        "step": "01",
        "title": "Choose Your Niches",
        "desc": "Select the verticals and sub-niches you want to buy calls for. Each niche has transparent CPL ranges — no hidden markups, no bidding wars.",
    },
    {
        "step": "02",
        "title": "Set Your Allocation",
        "desc": "Define your monthly call volume per niche. Our predictive engine routes only high-intent calls that match your capacity and service area.",
    },
    {
        "step": "03",
        "title": "Live Call Routing",
        "desc": "When a qualified caller matches your profile, we route the call live through our AI closer pipeline. You receive warm, pre-qualified leads — not cold data.",
    },
    {
        "step": "04",
        "title": "Pay Per Completed Call",
        "desc": "You pay only for calls that meet agreed duration and quality thresholds. Each call is audited for compliance, duration, and conversion intent.",
    },
]

# ── FAQ ──────────────────────────────────────────────────────────────

_FAQ = [
    {
        "q": "What's the difference between PPL and PPC?",
        "a": "PPL (Pay-Per-Lead) charges for form-fill data — names, emails, and phone numbers submitted through web forms. PPC (Pay-Per-Call) charges for live, connected phone calls with verified duration. PPC converts 2-5x higher because the caller is actively engaged.",
    },
    {
        "q": "How are calls qualified before routing?",
        "a": "Our AI triage pipeline scores each inbound call for intent, urgency, and service-area match before routing. Only calls above confidence threshold are dispatched — you never pay for spam, wrong numbers, or low-intent inquiries.",
    },
    {
        "q": "What happens if a call drops before 60 seconds?",
        "a": "You're not charged. Our post-call audit verifies minimum duration thresholds before marking a call as billable. Standard contracts use a 60-90 second minimum.",
    },
    {
        "q": "Can I cap my monthly spend?",
        "a": "Absolutely. Every allocation comes with hard monthly caps on both volume and spend. Our system auto-pauses routing when either cap is reached — no surprises.",
    },
    {
        "q": "How fast can I start receiving calls?",
        "a": "Once your allocation is configured and your forwarding number is verified, calls can start routing within 24 hours. Plumbing and emergency niches can go live in as little as 2 hours.",
    },
    {
        "q": "Is there a minimum commitment?",
        "a": "No long-term contracts. All allocations are month-to-month with 7-day cancellation. Enterprise customers can negotiate volume-based discounts at 500+ calls/month per niche.",
    },
]


def ppc_page() -> str:
    """Return the full /ppc landing page HTML."""

    ppc_css = """
    /* ── PPC PAGE SPECIFIC ─────────────────────────────────────────── */
    .ppc-wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 32px 80px;
      position: relative;
      z-index: 1;
    }

    /* ── HERO ──────────────────────────────────────────────────────── */
    .ppc-hero {
      text-align: center;
      margin-bottom: 64px;
      animation: empire-fade-up 0.7s var(--ease-out-empire) both;
    }
    .ppc-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 14px;
    }
    .ppc-eyebrow .e-sonar {
      display: inline-flex; vertical-align: middle;
      margin-right: 8px;
    }
    .ppc-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 48px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.08;
      margin-bottom: 18px;
    }
    .ppc-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .ppc-title .pipe {
      color: var(--empire-shadow);
      font-weight: 200;
    }
    .ppc-sub {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--empire-mist);
      letter-spacing: 0.14em;
      max-width: 640px;
      margin: 0 auto;
      line-height: 1.8;
    }
    .ppc-stats {
      display: flex;
      justify-content: center;
      gap: 32px;
      margin-top: 36px;
      flex-wrap: wrap;
    }
    .ppc-stat {
      text-align: center;
    }
    .ppc-stat-num {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 36px;
      color: var(--signal-teal);
      line-height: 1;
    }
    .ppc-stat-label {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-top: 6px;
    }

    /* ── SECTION ───────────────────────────────────────────────────── */
    .ppc-section {
      margin-bottom: 72px;
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .ppc-section:last-child { margin-bottom: 0; }
    .ppc-section-h {
      display: flex;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 28px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .ppc-section-num {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--signal-teal);
      letter-spacing: 0.12em;
    }
    .ppc-section-title {
      font-weight: 500;
      font-size: 22px;
      letter-spacing: -0.02em;
      color: var(--empire-white);
    }
    .ppc-section-sub {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.14em;
      text-transform: uppercase;
      margin-left: auto;
    }

    /* ── HOW IT WORKS ──────────────────────────────────────────────── */
    .ppc-steps {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }
    .ppc-step {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 28px 22px;
      position: relative;
      transition: all 0.25s var(--ease-snap);
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .ppc-step:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .ppc-step-num {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--signal-teal);
      letter-spacing: 0.12em;
      margin-bottom: 12px;
    }
    .ppc-step-title {
      font-weight: 600;
      font-size: 15px;
      color: var(--empire-white);
      margin-bottom: 10px;
    }
    .ppc-step-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.7;
    }

    /* ── PRICING TABLE ─────────────────────────────────────────────── */
    .ppc-table-wrap {
      overflow-x: auto;
      border: 1px solid var(--empire-divider);
      background: var(--empire-surface);
    }
    .ppc-table {
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
    }
    .ppc-table thead th {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      text-align: left;
      padding: 14px 16px;
      border-bottom: 1px solid var(--empire-divider);
      background: var(--empire-elevated);
      font-weight: 600;
    }
    .ppc-table tbody td {
      padding: 14px 16px;
      border-bottom: 1px solid rgba(122, 140, 163, 0.06);
      font-size: 12px;
      color: var(--empire-silver);
      vertical-align: middle;
    }
    .ppc-table tbody tr:last-child td { border-bottom: none; }
    .ppc-table tbody tr:hover { background: var(--empire-elevated); }
    .ppc-table tbody tr:hover td { color: var(--empire-white); }
    .ppc-niche-name {
      font-weight: 600;
      color: var(--empire-white);
    }
    .ppc-niche-icon {
      font-size: 16px;
      margin-right: 8px;
    }
    .ppc-price {
      font-family: var(--font-mono);
      color: var(--signal-teal);
      font-weight: 600;
      font-size: 13px;
    }
    .ppc-pacing {
      font-family: var(--font-mono);
      font-size: 10px;
    }
    .ppc-trigger {
      font-size: 11px;
      color: var(--empire-fog);
    }
    .ppc-volume {
      font-family: var(--font-mono);
      font-size: 10px;
    }
    .ppc-volume.high { color: var(--signal-teal); }
    .ppc-volume.medium { color: var(--strike-cyan); }
    .ppc-volume.growing { color: var(--status-amber); }

    /* ── NICHE CARDS (mobile fallback) ─────────────────────────────── */
    .ppc-cards {
      display: none;
      grid-template-columns: 1fr;
      gap: 12px;
    }
    .ppc-card {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 20px;
      transition: all 0.2s var(--ease-snap);
    }
    .ppc-card:hover {
      border-color: var(--signal-teal-soft);
    }
    .ppc-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .ppc-card-niche {
      font-weight: 600;
      font-size: 14px;
      color: var(--empire-white);
    }
    .ppc-card-price {
      font-family: var(--font-mono);
      color: var(--signal-teal);
      font-weight: 600;
      font-size: 14px;
    }
    .ppc-card-meta {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      margin-bottom: 8px;
    }
    .ppc-card-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.6;
    }

    /* ── SIGNUP FORM ───────────────────────────────────────────────── */
    .ppc-form-wrap {
      max-width: 640px;
    }
    .ppc-form {
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .ppc-form-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
    .ppc-form .e-field {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .ppc-form .e-field-label {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }
    .ppc-form .e-input,
    .ppc-form .e-textarea,
    .ppc-form .e-select {
      background: rgba(0, 0, 0, 0.4);
      color: var(--empire-white);
      border: 1px solid var(--empire-border);
      border-radius: var(--radius-sm);
      font-family: var(--font-mono);
      font-size: 13px;
      padding: 12px 14px;
      outline: none;
      width: 100%;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .ppc-form .e-input:focus,
    .ppc-form .e-textarea:focus,
    .ppc-form .e-select:focus {
      border-color: var(--signal-teal);
      box-shadow: 0 0 0 1px var(--signal-teal-glow);
    }
    .ppc-form .e-input::placeholder,
    .ppc-form .e-textarea::placeholder {
      color: var(--empire-fog);
    }
    .ppc-form .e-textarea {
      resize: vertical;
      min-height: 100px;
      line-height: 1.7;
    }
    .ppc-form .e-select option {
      background: var(--empire-surface);
      color: var(--empire-white);
    }
    .ppc-form .e-btn {
      align-self: flex-start;
    }
    .ppc-form-note {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      line-height: 1.6;
      margin-top: 12px;
    }
    .ppc-form-note a {
      color: var(--signal-teal);
      text-decoration: none;
    }
    .ppc-form-note a:hover {
      text-decoration: underline;
    }

    /* ── FAQ ────────────────────────────────────────────────────────── */
    .ppc-faq-list {
      max-width: 720px;
    }
    .ppc-faq-item {
      border-bottom: 1px solid var(--empire-divider);
      padding: 18px 0;
    }
    .ppc-faq-item:first-child { padding-top: 0; }
    .ppc-faq-q {
      display: flex;
      justify-content: space-between;
      align-items: center;
      width: 100%;
      padding: 0;
      cursor: pointer;
      border: none;
      background: none;
      font: inherit;
      text-align: left;
      color: var(--empire-white);
      font-weight: 500;
      font-size: 14px;
      margin-bottom: 8px;
      user-select: none;
      -webkit-appearance: none;
      appearance: none;
    }
    .ppc-faq-q:hover { color: var(--signal-teal); }
    .ppc-faq-q[aria-expanded="true"] { color: var(--signal-teal); }
    .ppc-faq-chevron {
      flex-shrink: 0;
      margin-left: 12px;
      width: 18px;
      height: 18px;
      transition: transform 0.25s ease;
      color: var(--empire-fog);
      pointer-events: none;
    }
    .ppc-faq-q[aria-expanded="true"] .ppc-faq-chevron {
      transform: rotate(180deg);
      color: var(--signal-teal);
    }
    .ppc-faq-a {
      font-size: 13px;
      color: var(--empire-mist);
      line-height: 1.7;
      overflow: hidden;
      max-height: 0;
      opacity: 0;
      transition: max-height 0.3s ease, opacity 0.25s ease, padding 0.15s ease;
    }
    .ppc-faq-a[aria-hidden="false"] {
      max-height: 300px;
      opacity: 1;
    }
    .ppc-faq-a.open {
      max-height: 300px;
      opacity: 1;
    }

    /* ── CTA BAR ────────────────────────────────────────────────────── */
    .ppc-cta-bar {
      margin-top: 48px;
      padding: 32px;
      background: var(--empire-surface);
      border: 1px solid var(--signal-teal-soft);
      text-align: center;
      position: relative;
      overflow: hidden;
    }
    .ppc-cta-bar::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 2px;
      background: linear-gradient(90deg, var(--signal-teal), var(--strike-cyan));
    }
    .ppc-cta-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 28px;
      color: var(--empire-white);
      margin-bottom: 10px;
    }
    .ppc-cta-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .ppc-cta-desc {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      margin-bottom: 20px;
    }

    /* ── RESPONSIVE ────────────────────────────────────────────────── */
    @media (max-width: 900px) {
      .ppc-steps { grid-template-columns: repeat(2, 1fr); }
      .ppc-title { font-size: 32px; }
      .ppc-wrap { padding: 32px 20px 60px; }
      .ppc-table-wrap { display: none; }
      .ppc-cards { display: grid; }
      .ppc-form-row { grid-template-columns: 1fr; }
    }
    @media (max-width: 540px) {
      .ppc-steps { grid-template-columns: 1fr; }
      .ppc-stats { gap: 20px; }
      .ppc-stat-num { font-size: 28px; }
    }

    /* ── FOOTER ─────────────────────────────────────────────────────── */
    .ppc-foot {
      margin-top: 64px;
      padding-top: 24px;
      border-top: 1px solid var(--empire-divider);
      text-align: center;
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.24em;
      text-transform: uppercase;
    }
    .ppc-foot a {
      color: var(--empire-mist);
      text-decoration: none;
      transition: color 0.2s;
    }
    .ppc-foot a:hover { color: var(--signal-teal); }
    .ppc-foot .sep {
      padding: 0 8px;
      color: var(--empire-shadow);
    }
    """

    # ── Build pricing table rows ─────────────────────────────────────
    table_rows = ""
    card_rows = ""
    for i, n in enumerate(_PPC_NICHES):
        vol_class = {"High": "high", "Highest": "high", "Medium-High": "high",
                     "Medium": "medium", "High value": "high", "Growing": "growing"}.get(n["volume"], "")
        table_rows += f"""<tr style="animation-delay: {0.05 + i * 0.03}s">
          <td><span class="ppc-niche-icon">{n["icon"]}</span><span class="ppc-niche-name">{n["niche"]}</span><br><span class="ppc-trigger">{n["category"]}</span></td>
          <td class="ppc-price">{n["cpl_range"]}</td>
          <td><span class="ppc-pacing">{n["pacing"]}</span></td>
          <td><span class="ppc-trigger">{n["trigger"]}</span></td>
          <td><span class="ppc-volume {vol_class}">{n["volume"]}</span></td>
        </tr>"""
        card_rows += f"""<div class="ppc-card" style="animation-delay: {0.05 + i * 0.03}s">
          <div class="ppc-card-header">
            <span class="ppc-card-niche">{n["icon"]} {n["niche"]}</span>
            <span class="ppc-card-price">{n["cpl_range"]}</span>
          </div>
          <div class="ppc-card-meta">{n["category"]} · {n["pacing"]} · {n["trigger"]}</div>
          <div class="ppc-card-desc">{n["description"]}</div>
        </div>"""

    # ── Build FAQ rows ───────────────────────────────────────────────
    faq_rows = ""
    for i, faq in enumerate(_FAQ):
        faq_rows += f"""<div class="ppc-faq-item">
          <button class="ppc-faq-q" onclick="togglePpcFaq(this)" type="button" id="ppc-faq-trigger-{i}" aria-controls="ppc-faq-answer-{i}" aria-expanded="false">
            <span>{faq["q"]}</span>
            <svg class="ppc-faq-chevron" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7l5 5 5-5"/></svg>
          </button>
          <div class="ppc-faq-a" id="ppc-faq-answer-{i}" role="region" aria-labelledby="ppc-faq-trigger-{i}" aria-hidden="true">
            {faq["a"]}
          </div>
        </div>"""

    # ── Niche options for the form select ────────────────────────────
    niche_options = "".join(
        f'<option value="{n["niche"]}">{n["icon"]} {n["niche"]} ({n["cpl_range"]})</option>'
        for n in _PPC_NICHES
    )

    head = empire_head(
        title="Empire AI · Pay-Per-Call Routing",
        extra=ppc_css,
        page="ppc",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="ppc-wrap">

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- HERO                                                          -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <div class="ppc-hero">
    <div class="ppc-eyebrow">
      <span class="e-sonar live"><span class="e-sonar-dot"></span></span>
      Live · Pay-Per-Call
    </div>
    <h1 class="ppc-title">
      Buy <em>Live Calls</em><br>
      <span class="pipe">/</span> Not Lead Lists
    </h1>
    <p class="ppc-sub">
      Real-time call routing from high-intent inbounders to vetted buyers.
      You pay only for connected, verified calls — each one pre-scored
      for urgency, niche match, and conversion probability.
    </p>
    <div class="ppc-stats">
      <div class="ppc-stat">
        <div class="ppc-stat-num">2-5x</div>
        <div class="ppc-stat-label">Higher conversion vs PPL</div>
      </div>
      <div class="ppc-stat">
        <div class="ppc-stat-num">24h</div>
        <div class="ppc-stat-label">Time to first call</div>
      </div>
      <div class="ppc-stat">
        <div class="ppc-stat-num">8</div>
        <div class="ppc-stat-label">PPC-ready niches</div>
      </div>
      <div class="ppc-stat">
        <div class="ppc-stat-num">0</div>
        <div class="ppc-stat-label">Long-term contracts</div>
      </div>
    </div>
  </div>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- HOW IT WORKS                                                  -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <div class="ppc-section">
    <div class="ppc-section-h">
      <span class="ppc-section-num">01</span>
      <span class="ppc-section-title">How It Works</span>
      <span class="ppc-section-sub">Four steps to live</span>
    </div>
    <div class="ppc-steps">
      {''.join(f'''<div class="ppc-step" style="animation-delay: {0.05 + i * 0.08}s">
        <div class="ppc-step-num">{s["step"]}</div>
        <div class="ppc-step-title">{s["title"]}</div>
        <div class="ppc-step-desc">{s["desc"]}</div>
      </div>''' for i, s in enumerate(_HOW_IT_WORKS))}
    </div>
  </div>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- PRICING TABLE                                                 -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <div class="ppc-section">
    <div class="ppc-section-h">
      <span class="ppc-section-num">02</span>
      <span class="ppc-section-title">PPC Rates by Niche</span>
      <span class="ppc-section-sub">Transparent · No bidding</span>
    </div>
    <p style="font-size:12px; color:var(--empire-mist); line-height:1.7; margin-bottom:20px; max-width:720px;">
      All prices are per connected call at the agreed minimum duration.
      Volume discounts available at 100+ calls/month per niche.
      Enterprise pricing at 500+ calls/month.
    </p>
    <div class="ppc-table-wrap">
      <table class="ppc-table">
        <thead>
          <tr>
            <th>Niche</th>
            <th>CPL Range</th>
            <th>Pacing</th>
            <th>Trigger</th>
            <th>Volume</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </div>
    <div class="ppc-cards">
      {card_rows}
    </div>
  </div>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- SIGNUP                                                        -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <div class="ppc-section" id="signup">
    <div class="ppc-section-h">
      <span class="ppc-section-num">03</span>
      <span class="ppc-section-title">Allocate Calls</span>
      <span class="ppc-section-sub">Start routing in 24h</span>
    </div>
    <div class="ppc-form-wrap">
      <p style="font-size:12px; color:var(--empire-mist); line-height:1.7; margin-bottom:24px;">
        Tell us which niches and volumes you're targeting. Our team will
        configure your allocation and have calls routing within 24 hours.
      </p>
      <form class="ppc-form" id="ppc-signup-form" onsubmit="return submitPPCForm(event)">
        <div class="ppc-form-row">
          <div class="e-field">
            <label class="e-field-label" for="ppc-name">Full Name</label>
            <input class="e-input" id="ppc-name" name="name" type="text" placeholder="e.g., Alex Rivera" required>
          </div>
          <div class="e-field">
            <label class="e-field-label" for="ppc-email">Email Address</label>
            <input class="e-input" id="ppc-email" name="email" type="email" placeholder="e.g., alex@example.com" required>
          </div>
        </div>
        <div class="ppc-form-row">
          <div class="e-field">
            <label class="e-field-label" for="ppc-phone">Phone Number</label>
            <input class="e-input" id="ppc-phone" name="phone" type="tel" placeholder="e.g., +1 214 555 0100" required>
          </div>
          <div class="e-field">
            <label class="e-field-label" for="ppc-company">Company</label>
            <input class="e-input" id="ppc-company" name="company" type="text" placeholder="e.g., Rivera Contracting">
          </div>
        </div>
        <div class="ppc-form-row">
          <div class="e-field">
            <label class="e-field-label" for="ppc-niche">Primary Niche</label>
            <select class="e-select" id="ppc-niche" name="niche" required>
              <option value="">Select a niche…</option>
              {niche_options}
            </select>
          </div>
          <div class="e-field">
            <label class="e-field-label" for="ppc-volume">Monthly Call Target</label>
            <select class="e-select" id="ppc-volume" name="volume" required>
              <option value="">Select volume…</option>
              <option value="10-50">10–50 calls/month</option>
              <option value="50-100">50–100 calls/month</option>
              <option value="100-500">100–500 calls/month</option>
              <option value="500+">500+ calls/month (enterprise)</option>
            </select>
          </div>
        </div>
        <div class="e-field">
          <label class="e-field-label" for="ppc-notes">Additional Notes</label>
          <textarea class="e-textarea" id="ppc-notes" name="notes" placeholder="Target markets, preferred pricing, timing, or anything else we should know…" rows="3"></textarea>
        </div>
        <button class="e-btn" type="submit">Submit Allocation Request</button>
        <div class="ppc-form-note" id="ppc-form-status" style="display:none;"></div>
        <div class="ppc-form-note">
          By submitting, you agree to our <a href="/terms">Terms of Service</a>.
          We'll follow up within 2 business hours to confirm your allocation.
        </div>
      </form>
    </div>
  </div>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- FAQ                                                           -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <div class="ppc-section">
    <div class="ppc-section-h">
      <span class="ppc-section-num">04</span>
      <span class="ppc-section-title">Frequently Asked</span>
      <span class="ppc-section-sub">Questions</span>
    </div>
    <div class="ppc-faq-list">
      {faq_rows}
    </div>
  </div>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- CTA BAR                                                       -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <div class="ppc-cta-bar">
    <div class="ppc-cta-title">Ready to start receiving <em>live calls</em>?</div>
    <div class="ppc-cta-desc">Set up your allocation in minutes — calls can route within 24 hours</div>
    <a href="#signup" class="e-btn">Request Allocation</a>
  </div>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- FOOTER                                                        -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  <div class="ppc-foot">
    <a href="/">Empire AI</a>
    <span class="sep">·</span>
    <a href="/pricing">Pricing</a>
    <span class="sep">·</span>
    <a href="/command">Dashboard</a>
    <span class="sep">·</span>
    <a href="mailto:ops@empire-ai.co.uk">Contact</a>
    <br>
    <span style="letter-spacing:0.12em; color:var(--empire-shadow); margin-top:8px; display:block;">
      Pay-Per-Call · Transparent pricing · No long-term commitments
    </span>
  </div>

</div>

<script>
(function() {{
  // ── FAQ toggle with ARIA support ──
  window.togglePpcFaq = function(btn) {{
    var isExpanded = btn.getAttribute('aria-expanded') === 'true';
    var answer = document.getElementById(btn.getAttribute('aria-controls'));
    if (!answer) return;
    
    btn.setAttribute('aria-expanded', !isExpanded);
    answer.setAttribute('aria-hidden', isExpanded);
    if (!isExpanded) {{
      answer.classList.add('open');
    }} else {{
      answer.classList.remove('open');
    }}
  }};
}})();

// ── Form submission handler ──
function submitPPCForm(event) {{
  event.preventDefault();
  var form = document.getElementById('ppc-signup-form');
  var status = document.getElementById('ppc-form-status');
  var btn = form.querySelector('.e-btn');

  var data = {{
    name: form.querySelector('#ppc-name').value,
    email: form.querySelector('#ppc-email').value,
    phone: form.querySelector('#ppc-phone').value,
    company: form.querySelector('#ppc-company').value || '',
    niche: form.querySelector('#ppc-niche').value,
    volume: form.querySelector('#ppc-volume').value,
    notes: form.querySelector('#ppc-notes').value || '',
  }};

  btn.disabled = true;
  btn.textContent = 'Submitting…';
  status.style.display = 'none';

  // If the API submission fails, fall back to mailto
  var mailtoLink = 'mailto:ops@empire-ai.co.uk'
    + '?subject=' + encodeURIComponent('PPC Allocation Request: ' + data.niche)
    + '&body=' + encodeURIComponent(
        'Name: ' + data.name + '\\n' +
        'Email: ' + data.email + '\\n' +
        'Phone: ' + data.phone + '\\n' +
        'Company: ' + data.company + '\\n' +
        'Niche: ' + data.niche + '\\n' +
        'Volume: ' + data.volume + '\\n' +
        'Notes: ' + data.notes + '\\n'
      );

  fetch('/api/v1/ppc/signup', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(data),
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(result) {{
    if (result.ok) {{
      status.style.display = 'block';
      status.innerHTML = '✓ Allocation request received! We\\'ll follow up within 2 business hours.';
      status.style.color = 'var(--signal-teal)';
      form.reset();
    }} else {{
      // Fall back to mailto
      window.location.href = mailtoLink;
      status.style.display = 'block';
      status.innerHTML = '→ Redirecting to email…';
    }}
  }})
  .catch(function() {{
    // Fall back to mailto
    window.location.href = mailtoLink;
    status.style.display = 'block';
    status.innerHTML = '→ Redirecting to email…';
  }})
  .finally(function() {{
    btn.disabled = false;
    btn.textContent = 'Submit Allocation Request';
  }});

  return false;
}}
</script>

</body>
</html>"""
