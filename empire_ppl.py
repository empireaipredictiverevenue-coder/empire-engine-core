"""
EMPIRE V49 · PAY-PER-LEAD STOREFRONT
======================================
Dedicated landing page at /ppl explaining the per-lead buying model
and letting buyers purchase leads by niche.

Wire-up in hub.py:
    from empire_ppl import ppl_page

    @app.get("/ppl", response_class=HTMLResponse)
    async def ppl():
        return HTMLResponse(ppl_page())
"""

from empire_tokens import empire_head

# PPL niche data from CPL_BENCHMARKS
_PPL_NICHES = [
    {
        "niche": "Roofing Restoration",
        "icon": "🏠",
        "cpl_range": "$162 – $228",
        "cpl_mid": 195,
        "margin": "High",
        "volume": "Highest",
        "lead_type": "Storm-damaged property owners",
        "description": "Verified property owners with active storm damage. Each lead includes name, phone, address, damage severity, and insurance status.",
        "best_for": "Roofing contractors, restoration companies, insurance adjusters",
    },
    {
        "niche": "Personal Injury",
        "icon": "⚖️",
        "cpl_range": "$250 – $600",
        "cpl_mid": 425,
        "margin": "Highest",
        "volume": "High",
        "lead_type": "Legal intake prospects",
        "description": "High-intent personal injury prospects. Auto accidents, slip-and-fall, medical malpractice. Pre-qualified via SMS and call triage.",
        "best_for": "PI law firms, mass tort practices, legal lead aggregators",
    },
    {
        "niche": "HVAC",
        "icon": "❄️",
        "cpl_range": "$51 – $149",
        "cpl_mid": 100,
        "margin": "Medium",
        "volume": "High",
        "lead_type": "Homeowners with HVAC needs",
        "description": "Homeowners actively seeking HVAC services. AC failures, furnace issues, seasonal maintenance. High close rates in peak seasons.",
        "best_for": "HVAC contractors, home service franchises, property maintenance",
    },
    {
        "niche": "Debt Consolidation",
        "icon": "💰",
        "cpl_range": "$150 – $400",
        "cpl_mid": 275,
        "margin": "High",
        "volume": "Growing",
        "lead_type": "Consumers seeking debt relief",
        "description": "Financially distressed consumers actively researching debt consolidation. Pre-screened for debt load, income, and intent.",
        "best_for": "Debt settlement companies, credit counseling, financial services",
    },
    {
        "niche": "Medicare Advantage",
        "icon": "🏥",
        "cpl_range": "$35 – $85",
        "cpl_mid": 60,
        "margin": "Medium",
        "volume": "Seasonal (AEP)",
        "lead_type": "Seniors researching Medicare plans",
        "description": "Medicare-eligible seniors actively comparing plans. High-value demographic with recurring commission potential.",
        "best_for": "Insurance agents, Medicare brokers, health plans",
    },
    {
        "niche": "Addiction Treatment",
        "icon": "🏥",
        "cpl_range": "$200 – $500",
        "cpl_mid": 350,
        "margin": "Highest",
        "volume": "Medium",
        "lead_type": "High-intent treatment seekers",
        "description": "Individuals and families actively seeking addiction treatment. Phone-verified. Avg patient LTV exceeds $78k.",
        "best_for": "Treatment centers, detox facilities, behavioral health",
    },
    {
        "niche": "Assisted Living",
        "icon": "👴",
        "cpl_range": "$75 – $250",
        "cpl_mid": 162,
        "margin": "High",
        "volume": "Growing",
        "lead_type": "Families researching senior care",
        "description": "Families actively researching assisted living options. High-intent, long consideration cycle, high LTV per placement.",
        "best_for": "Assisted living facilities, senior placement agencies",
    },
    {
        "niche": "Commercial Solar",
        "icon": "☀️",
        "cpl_range": "$100 – $300",
        "cpl_mid": 200,
        "margin": "High",
        "volume": "Growing",
        "lead_type": "Commercial property owners",
        "description": "Commercial property owners in high-solar-yield regions. Includes warehouse owners, retail chains, and industrial facilities.",
        "best_for": "Solar installers, energy consultants, commercial contractors",
    },
    {
        "niche": "Commercial Roofing",
        "icon": "🏢",
        "cpl_range": "$162 – $228",
        "cpl_mid": 195,
        "margin": "High",
        "volume": "Medium",
        "lead_type": "Commercial property managers",
        "description": "Commercial and industrial property owners with verified roof damage. Includes asset value, building size, and insurance info.",
        "best_for": "Commercial roofing contractors, restoration companies",
    },
    {
        "niche": "Debt Relief",
        "icon": "💳",
        "cpl_range": "$100 – $300",
        "cpl_mid": 200,
        "margin": "High",
        "volume": "Growing",
        "lead_type": "Consumers seeking debt relief",
        "description": "Consumers actively researching debt relief options. Pre-qualified for debt amount, income verification, and intent to enroll.",
        "best_for": "Debt relief companies, bankruptcy attorneys, credit repair",
    },
]


_PPL_HOW_IT_WORKS = [
    {
        "step": "01",
        "title": "Browse Niches",
        "desc": "Select the verticals and lead types you want to buy. Each niche has transparent CPL ranges and lead profiles.",
    },
    {
        "step": "02",
        "title": "Purchase Leads",
        "desc": "Buy leads in bulk or subscribe for weekly batches. Volume discounts available at 100+ leads/month per niche.",
    },
    {
        "step": "03",
        "title": "Receive Contact Data",
        "desc": "Each lead includes name, phone, email, address, and qualification data. Delivered via API or CSV export.",
    },
    {
        "step": "04",
        "title": "Close & Convert",
        "desc": "Contact pre-qualified leads within your service area. Our 3% fee only triggers on settled insurance claims.",
    },
]


_PPL_FAQ = [
    {
        "q": "What's included in a lead purchase?",
        "a": "Each lead includes the property owner's name, phone number, email, property address, damage/need assessment, insurance status, and urgency score. Storm-related leads include NWS event data and estimated damage severity.",
    },
    {
        "q": "Are leads exclusive to one buyer?",
        "a": "Leads can be purchased as exclusive (single buyer in a metro) or non-exclusive (multiple buyers compete on first-contact). Exclusive pricing is typically 2-3x standard CPL.",
    },
    {
        "q": "What's the difference from PPC?",
        "a": "PPL delivers contact data that you call or email. PPC routes live, connected calls directly to you. PPC converts 2-5x higher but costs more per event. Many buyers use both — PPL for nurturing, PPC for immediate closers.",
    },
    {
        "q": "Can I target specific metros?",
        "a": "Yes. Every lead is geo-tagged with city, state, and metro area. You can filter purchases by metro, niche, urgency score, and damage severity.",
    },
    {
        "q": "What happens if a lead is bad?",
        "a": "We guarantee lead quality. If a phone number is disconnected or the lead explicitly opts out, we replace it at no cost within 7 days of purchase.",
    },
    {
        "q": "How fast can I start receiving leads?",
        "a": "Immediately for available inventory. For ongoing subscriptions, we deliver leads within 24-48 hours of purchase, with weekly batch options for higher volumes.",
    },
]


def ppl_page() -> str:
    """Return the full /ppl landing page HTML."""

    ppl_css = """
    .ppl-wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 32px 80px;
    }
    .ppl-hero {
      text-align: center;
      margin-bottom: 64px;
    }
    .ppl-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 14px;
    }
    .ppl-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 48px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.08;
      margin-bottom: 18px;
    }
    .ppl-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .ppl-sub {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--empire-mist);
      letter-spacing: 0.14em;
      max-width: 640px;
      margin: 0 auto;
      line-height: 1.8;
    }
    .ppl-stats {
      display: flex;
      justify-content: center;
      gap: 32px;
      margin-top: 36px;
      flex-wrap: wrap;
    }
    .ppl-stat {
      text-align: center;
    }
    .ppl-stat-num {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 36px;
      color: var(--signal-teal);
      line-height: 1;
    }
    .ppl-stat-label {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-top: 6px;
    }
    .ppl-section {
      margin-bottom: 72px;
    }
    .ppl-section-h {
      display: flex;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 28px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .ppl-section-num {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--signal-teal);
      letter-spacing: 0.12em;
    }
    .ppl-section-title {
      font-weight: 500;
      font-size: 22px;
      letter-spacing: -0.02em;
      color: var(--empire-white);
    }
    .ppl-steps {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }
    .ppl-step {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 28px 22px;
      transition: all 0.25s var(--ease-snap);
    }
    .ppl-step:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
    }
    .ppl-step-num {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--signal-teal);
      margin-bottom: 12px;
    }
    .ppl-step-title {
      font-weight: 600;
      font-size: 15px;
      color: var(--empire-white);
      margin-bottom: 10px;
    }
    .ppl-step-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.7;
    }
    .ppl-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 16px;
    }
    .ppl-card {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 24px;
      transition: all 0.25s var(--ease-snap);
    }
    .ppl-card:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-1px);
    }
    .ppl-card-icon {
      font-size: 24px;
      margin-bottom: 12px;
    }
    .ppl-card-title {
      font-weight: 600;
      font-size: 16px;
      color: var(--empire-white);
      margin-bottom: 6px;
    }
    .ppl-card-price {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--signal-teal);
      margin-bottom: 10px;
    }
    .ppl-card-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.6;
      margin-bottom: 14px;
    }
    .ppl-card-meta {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      margin-bottom: 14px;
    }
    .ppl-card-btn {
      display: inline-block;
      padding: 10px 18px;
      font-size: 12px;
      font-weight: 600;
      color: #0A1A2F;
      background: var(--signal-teal);
      border: 0;
      border-radius: var(--radius-sm);
      cursor: pointer;
      text-decoration: none;
      transition: opacity 0.2s;
    }
    .ppl-card-btn:hover {
      opacity: 0.85;
    }
    .ppl-cta-bar {
      margin-top: 48px;
      padding: 32px;
      background: var(--empire-surface);
      border: 1px solid var(--signal-teal-soft);
      text-align: center;
    }
    .ppl-cta-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 28px;
      color: var(--empire-white);
      margin-bottom: 10px;
    }
    .ppl-cta-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .ppl-cta-desc {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      margin-bottom: 20px;
    }
    .ppl-faq-list {
      max-width: 720px;
    }
    .ppl-faq-item {
      border-bottom: 1px solid var(--empire-divider);
      padding: 18px 0;
    }
    .ppl-faq-item:first-child { padding-top: 0; }
    .ppl-faq-q {
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
    .ppl-faq-q:hover { color: var(--signal-teal); }
    .ppl-faq-q[aria-expanded="true"] { color: var(--signal-teal); }
    .ppl-faq-chevron {
      flex-shrink: 0;
      margin-left: 12px;
      width: 18px;
      height: 18px;
      transition: transform 0.25s ease;
      color: var(--empire-fog);
      pointer-events: none;
    }
    .ppl-faq-q[aria-expanded="true"] .ppl-faq-chevron {
      transform: rotate(180deg);
      color: var(--signal-teal);
    }
    .ppl-faq-a {
      font-size: 13px;
      color: var(--empire-mist);
      line-height: 1.7;
      overflow: hidden;
      max-height: 0;
      opacity: 0;
      transition: max-height 0.3s ease, opacity 0.25s ease, padding 0.15s ease;
    }
    .ppl-faq-a.open {
      max-height: 300px;
      opacity: 1;
    }
    .ppl-foot {
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
    .ppl-foot a {
      color: var(--empire-mist);
      text-decoration: none;
    }
    .ppl-foot a:hover { color: var(--signal-teal); }
    @media (max-width: 900px) {
      .ppl-steps { grid-template-columns: repeat(2, 1fr); }
      .ppl-title { font-size: 32px; }
      .ppl-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 540px) {
      .ppl-steps { grid-template-columns: 1fr; }
    }
    """

    niche_cards = ""
    for i, n in enumerate(_PPL_NICHES):
        niche_cards += f"""
    <div class="ppl-card" style="animation-delay: {0.03 * i}s">
      <div class="ppl-card-icon">{n['icon']}</div>
      <div class="ppl-card-title">{n['niche']}</div>
      <div class="ppl-card-price">CPL: {n['cpl_range']} · per lead</div>
      <div class="ppl-card-desc">{n['description']}</div>
      <div class="ppl-card-meta">{n['lead_type']} · {n['volume']} volume · {n['margin']} margin</div>
      <a class="ppl-card-btn" href="mailto:ops@empire-ai.co.uk?subject={n['niche'].replace(' ','%20')}%20Lead%20Purchase">Inquire →</a>
    </div>"""

    faq_rows = ""
    for i, faq in enumerate(_PPL_FAQ):
        faq_rows += f"""
    <div class="ppl-faq-item">
      <button class="ppl-faq-q" onclick="togglePplFaq(this)" type="button" id="ppl-faq-trigger-{i}" aria-controls="ppl-faq-answer-{i}" aria-expanded="false">
        <span>{faq['q']}</span>
        <svg class="ppl-faq-chevron" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7l5 5 5-5"/></svg>
      </button>
      <div class="ppl-faq-a" id="ppl-faq-answer-{i}" role="region" aria-labelledby="ppl-faq-trigger-{i}" aria-hidden="true">
        {faq['a']}
      </div>
    </div>"""

    steps_html = ""
    for i, s in enumerate(_PPL_HOW_IT_WORKS):
        steps_html += f"""
    <div class="ppl-step" style="animation-delay: {0.08 * i}s">
      <div class="ppl-step-num">{s['step']}</div>
      <div class="ppl-step-title">{s['title']}</div>
      <div class="ppl-step-desc">{s['desc']}</div>
    </div>"""

    head = empire_head(title="Empire AI · Pay-Per-Lead Marketplace", extra=ppl_css)

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="ppl-wrap">

  <div class="ppl-hero">
    <div class="ppl-eyebrow">Buy Pre-Qualified Leads</div>
    <h1 class="ppl-title">Buy <em>Verified</em> Leads<br><span style="color:var(--empire-shadow);font-weight:200;">/</span> Not Just Data</h1>
    <p class="ppl-sub">
      Every lead is pre-screened, verified, and ready for contact.
      From storm-damaged property owners to high-intent legal prospects —
      buy by the lead or subscribe for weekly delivery.
    </p>
    <div class="ppl-stats">
      <div class="ppl-stat">
        <div class="ppl-stat-num">10</div>
        <div class="ppl-stat-label">Active Niches</div>
      </div>
      <div class="ppl-stat">
        <div class="ppl-stat-num">8,900+</div>
        <div class="ppl-stat-label">Available Leads</div>
      </div>
      <div class="ppl-stat">
        <div class="ppl-stat-num">2.5x</div>
        <div class="ppl-stat-label">Typical Markup</div>
      </div>
      <div class="ppl-stat">
        <div class="ppl-stat-num">7d</div>
        <div class="ppl-stat-label">Quality Guarantee</div>
      </div>
    </div>
  </div>

  <div class="ppl-section">
    <div class="ppl-section-h">
      <span class="ppl-section-num">01</span>
      <span class="ppl-section-title">How It Works</span>
    </div>
    <div class="ppl-steps">{steps_html}</div>
  </div>

  <div class="ppl-section">
    <div class="ppl-section-h">
      <span class="ppl-section-num">02</span>
      <span class="ppl-section-title">Available Leads by Niche</span>
    </div>
    <p style="font-size:12px; color:var(--empire-mist); line-height:1.7; margin-bottom:20px; max-width:720px;">
      All leads include phone, email, address, and qualification data.
      Volume discounts at 100+ leads/month.
    </p>
    <div class="ppl-grid">{niche_cards}</div>
  </div>

  <div class="ppl-section">
    <div class="ppl-section-h">
      <span class="ppl-section-num">03</span>
      <span class="ppl-section-title">FAQ</span>
    </div>
    <div class="ppl-faq-list">{faq_rows}</div>
  </div>

  <div class="ppl-cta-bar">
    <div class="ppl-cta-title">Ready to buy <em>verified leads</em>?</div>
    <div class="ppl-cta-desc">Contact us for a lead inventory report and volume pricing</div>
    <a class="e-btn" href="mailto:ops@empire-ai.co.uk?subject=Lead%20Purchase%20Inquiry">Contact Sales</a>
  </div>

  <div class="ppl-foot">
    <a href="/">Empire AI</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/pricing">Pricing</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/ppc">Pay-Per-Call</a>
    <br>
    <span style="letter-spacing:0.12em;color:var(--empire-shadow);margin-top:8px;display:block;">
      Pay-Per-Lead · Verified contacts · Volume discounts
    </span>
  </div>

</div>

<script>
(function() {{
  // ── FAQ toggle with ARIA support ──
  window.togglePplFaq = function(btn) {{
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
</script>

</body>
</html>"""
