"""
EMPIRE V49 · UNIFIED MRR PRICING PAGE
=======================================
Comprehensive landing page at /mrr showing all 16 Empire AI Suite products
with pricing tiers, features, and links to individual product pages.

Features:
  - Hero product slider cycling through featured products
  - Animated stat counters that count up on scroll
  - Monthly/annual pricing toggle with smooth transition
  - Scroll-triggered entrance animations for product cards
  - Testimonial slider section
  - Expanding tier cards with Best Value highlights

Wire-up in hub.py:
    from empire_mrr_page import mrr_page

    @app.get("/mrr", response_class=HTMLResponse)
    async def mrr_pricing():
        return HTMLResponse(mrr_page())
"""

from empire_tokens import empire_head

MRR_PRODUCTS = [
    {
        "icon": "🔀", "name": "Inbound Router", "slug": "/products/inbound-router",
        "desc": "Call triage, multi-channel dispatch, and urgency scoring for incoming leads.",
        "tiers": [{"name": "SaaS", "price": 499, "features": ["Call triage", "Multi-channel dispatch", "Urgency scoring"]}],
        "cta": "Contact Sales",
    },
    {
        "icon": "🗄️", "name": "Data Vault", "slug": None,
        "desc": "Enterprise data retention, encryption, and audit trail for compliance.",
        "tiers": [{"name": "Enterprise", "price": 799, "features": ["Retention policies", "Encryption at rest", "Audit trail", "API access"]}],
        "cta": "Contact Sales",
    },
    {
        "icon": "🕵️", "name": "Buyer Spy AI", "slug": None,
        "desc": "Transcript analysis, network mapping, and buying signal detection.",
        "tiers": [{"name": "Enterprise", "price": 1499, "features": ["Transcript analysis", "Network mapping", "Buying signals", "Custom alerts"]}],
        "cta": "Contact Sales",
    },
    {
        "icon": "📊", "name": "LeadScore AI", "slug": None,
        "desc": "AI-powered lead scoring with Bayesian models and batch processing.",
        "tiers": [
            {"name": "Starter", "price": 299, "features": ["Bayesian scoring", "Basic reports"]},
            {"name": "Growth", "price": 599, "features": ["Advanced models", "Batch scoring", "CSV export"], "highlight": True},
            {"name": "Enterprise", "price": 999, "features": ["Custom models", "API access", "99.9% SLA"]},
        ],
        "cta": "Get Started",
    },
    {
        "icon": "🛡️", "name": "Compliant", "slug": None,
        "desc": "TCPA/DNC compliance checking, quiet hours enforcement, and opt-out management.",
        "tiers": [
            {"name": "Starter", "price": 199, "features": ["TCPA check", "DNC scan"]},
            {"name": "Growth", "price": 499, "features": ["Quiet hours", "Opt-out mgmt", "Audit log"], "highlight": True},
            {"name": "Enterprise", "price": 999, "features": ["Custom rules", "Bulk check", "Compliance reports"]},
        ],
        "cta": "Get Started",
    },
    {
        "icon": "⚡", "name": "Strike Campaigns", "slug": None,
        "desc": "Multi-channel outreach campaigns with A/B testing and SI optimization.",
        "tiers": [
            {"name": "Starter", "price": 99, "features": ["5 campaigns", "SMS only"]},
            {"name": "Growth", "price": 249, "features": ["SMS + email", "Analytics", "A/B testing"], "highlight": True},
            {"name": "Enterprise", "price": 499, "features": ["Unlimited campaigns", "All channels", "SI optimization"]},
        ],
        "cta": "Get Started",
    },
    {
        "icon": "🔮", "name": "Forecast", "slug": None,
        "desc": "Revenue forecasting with per-lane pipeline, LLM narrative, and SI evolution.",
        "tiers": [
            {"name": "Lite", "price": 199, "features": ["Per-lane pipeline", "Health alerts"]},
            {"name": "Pro", "price": 499, "features": ["LLM narrative", "Accuracy tracking", "SI evolution"], "highlight": True},
            {"name": "Enterprise", "price": 999, "features": ["What-if scenarios", "Multi-account", "API export"]},
        ],
        "cta": "Get Started",
    },
    {
        "icon": "👁️", "name": "Market Eye", "slug": None,
        "desc": "Competitive intelligence — website monitoring, price detection, and weekly briefs.",
        "tiers": [
            {"name": "Starter", "price": 199, "features": ["500 checks/mo", "Competitor tracking"]},
            {"name": "Growth", "price": 499, "features": ["2,000 checks", "Weekly briefs", "Alerts"], "highlight": True},
            {"name": "Enterprise", "price": 999, "features": ["10,000 checks", "Custom sources", "Full API"]},
        ],
        "cta": "Get Started",
    },
    {
        "icon": "📝", "name": "Content Pulse", "slug": None,
        "desc": "AI content generation — landing pages, blogs, email campaigns, and SEO audits.",
        "tiers": [
            {"name": "Starter", "price": 99, "features": ["Landing pages", "Basic SEO"]},
            {"name": "Growth", "price": 249, "features": ["Bulk generation", "Email content", "SEO audits"], "highlight": True},
            {"name": "Enterprise", "price": 499, "features": ["Unlimited", "Custom templates", "API access"]},
        ],
        "cta": "Get Started",
    },
    {
        "icon": "🤝", "name": "Contractor Exchange", "slug": None,
        "desc": "Verified contractor marketplace with trust scoring, vetting, and smart matching.",
        "tiers": [
            {"name": "Starter", "price": 299, "features": ["Contractor directory", "Search"]},
            {"name": "Growth", "price": 599, "features": ["Trust scoring", "Vetting", "Matching"], "highlight": True},
            {"name": "Enterprise", "price": 999, "features": ["Unlimited", "API", "Custom workflow"]},
        ],
        "cta": "Get Started",
    },
    {
        "icon": "🔐", "name": "HexStrike AI", "slug": None,
        "desc": "Security scanning — containers, APIs, secrets, and pipeline vulnerability detection.",
        "tiers": [
            {"name": "Starter", "price": 99, "features": ["100 scans/mo", "Container + API"]},
            {"name": "Growth", "price": 249, "features": ["500 scans", "All scan types", "Weekly schedule"], "highlight": True},
            {"name": "Enterprise", "price": 499, "features": ["Unlimited scans", "Custom targets", "Priority alerts"]},
        ],
        "cta": "Get Started",
    },
    {
        "icon": "🔍", "name": "Analyzer Agent", "slug": None,
        "desc": "OSINT investigation — email, phone, username search, social presence, and Shodan.",
        "tiers": [
            {"name": "Lite", "price": 49, "features": ["Email check", "Phone validation"]},
            {"name": "Growth", "price": 149, "features": ["Username search", "Google intel", "Social presence"], "highlight": True},
            {"name": "Enterprise", "price": 399, "features": ["Unlimited ops", "Shodan scanning", "Deep OSINT"]},
        ],
        "cta": "Get Started",
    },
    {
        "icon": "🤖", "name": "Meetily AI", "slug": "/products/meetily",
        "desc": "Privacy-first AI meeting assistant with local transcription and multi-LLM summaries.",
        "tiers": [
            {"name": "Starter", "price": 99, "features": ["Local transcription", "AI summaries", "Single user"]},
            {"name": "Pro", "price": 299, "features": ["5 users", "Speaker diarization", "Custom workflows"], "highlight": True},
            {"name": "Enterprise", "price": 999, "features": ["Unlimited users", "Dedicated server", "White-label"]},
        ],
        "cta": "Learn More",
    },
    {
        "icon": "🦊", "name": "Elite Scraper v2", "slug": "/products/elite-scraper",
        "desc": "Predictive scraper fleet — Camofox, YouTube, and autonomous Prospector agent.",
        "tiers": [
            {"name": "Starter", "price": 149, "features": ["1 niche", "100 leads/mo", "Basic enrichment"]},
            {"name": "Pro", "price": 499, "features": ["3 niches", "500 leads", "YouTube intel", "Real-time"], "highlight": True},
            {"name": "Enterprise", "price": 1999, "features": ["36+ lanes", "5,000+ leads", "AGI self-improvement"]},
        ],
        "cta": "Learn More",
    },
    {
        "icon": "👑", "name": "All Access", "slug": None,
        "desc": "Every Empire AI product in a single subscription. Full access to the entire Suite.",
        "tiers": [{"name": "Enterprise", "price": 2499, "features": ["All products included", "Full feature access", "Priority support", "Everything unlimited"]}],
        "cta": "Contact Sales",
    },
    {
        "icon": "📈", "name": "SEO Optimizer", "slug": None,
        "desc": "SEO audits, keyword tracking, content generation, and landing page optimization.",
        "tiers": [
            {"name": "Starter", "price": 99, "features": ["5 audits/mo", "50 keywords"]},
            {"name": "Growth", "price": 199, "features": ["15 audits", "200 keywords", "Research pipeline"], "highlight": True},
            {"name": "Pro", "price": 499, "features": ["Unlimited audits", "Unlimited keywords", "Landing pages"]},
        ],
        "cta": "Get Started",
    },
]

SORT_ORDER = {
    "All Access": 0, "LeadScore AI": 1, "Compliant": 2, "Strike Campaigns": 3,
    "HexStrike AI": 4, "SEO Optimizer": 5, "Analyzer Agent": 6, "Inbound Router": 7,
    "Data Vault": 8, "Buyer Spy AI": 9, "Forecast": 10, "Market Eye": 11,
    "Content Pulse": 12, "Contractor Exchange": 13, "Meetily AI": 14, "Elite Scraper v2": 15,
}
MRR_PRODUCTS.sort(key=lambda p: SORT_ORDER.get(p["name"], 99))

_TIER_KEY_MAP = {
    ("Inbound Router", "SaaS"): "ROUTER_SaaS",
    ("Data Vault", "Enterprise"): "DATA_ENTERPRISE",
    ("Buyer Spy AI", "Enterprise"): "SPY_DATA",
    ("LeadScore AI", "Starter"): "LEADSCORE_STARTER",
    ("LeadScore AI", "Growth"): "LEADSCORE_GROWTH",
    ("LeadScore AI", "Enterprise"): "LEADSCORE_ENTERPRISE",
    ("Compliant", "Starter"): "COMPLIANT_STARTER",
    ("Compliant", "Growth"): "COMPLIANT_GROWTH",
    ("Compliant", "Enterprise"): "COMPLIANT_ENTERPRISE",
    ("Strike Campaigns", "Starter"): "STRIKE_STARTER",
    ("Strike Campaigns", "Growth"): "STRIKE_GROWTH",
    ("Strike Campaigns", "Enterprise"): "STRIKE_ENTERPRISE",
    ("Forecast", "Lite"): "FORECAST_LITE",
    ("Forecast", "Pro"): "FORECAST_PRO",
    ("Forecast", "Enterprise"): "FORECAST_ENTERPRISE",
    ("Market Eye", "Starter"): "MARKET_EYE_STARTER",
    ("Market Eye", "Growth"): "MARKET_EYE_GROWTH",
    ("Market Eye", "Enterprise"): "MARKET_EYE_ENTERPRISE",
    ("Content Pulse", "Starter"): "CONTENT_PULSE_STARTER",
    ("Content Pulse", "Growth"): "CONTENT_PULSE_GROWTH",
    ("Content Pulse", "Enterprise"): "CONTENT_PULSE_ENTERPRISE",
    ("Contractor Exchange", "Starter"): "CONTRACTOR_EXCHANGE_STARTER",
    ("Contractor Exchange", "Growth"): "CONTRACTOR_EXCHANGE_GROWTH",
    ("Contractor Exchange", "Enterprise"): "CONTRACTOR_EXCHANGE_ENTERPRISE",
    ("HexStrike AI", "Starter"): "HEXSTRIKE_STARTER",
    ("HexStrike AI", "Growth"): "HEXSTRIKE_GROWTH",
    ("HexStrike AI", "Enterprise"): "HEXSTRIKE_ENTERPRISE",
    ("Analyzer Agent", "Lite"): "ANALYZER_LITE",
    ("Analyzer Agent", "Growth"): "ANALYZER_GROWTH",
    ("Analyzer Agent", "Enterprise"): "ANALYZER_ENTERPRISE",
    ("Meetily AI", "Starter"): "MEETILY_STARTER",
    ("Meetily AI", "Pro"): "MEETILY_PRO",
    ("Meetily AI", "Enterprise"): "MEETILY_ENTERPRISE",
    ("Elite Scraper v2", "Starter"): "SCRAPER_STARTER",
    ("Elite Scraper v2", "Pro"): "SCRAPER_PRO",
    ("Elite Scraper v2", "Enterprise"): "SCRAPER_ENTERPRISE",
    ("All Access", "Enterprise"): "ALL_ACCESS",
    ("SEO Optimizer", "Starter"): "SEO_STARTER",
    ("SEO Optimizer", "Growth"): "SEO_GROWTH",
    ("SEO Optimizer", "Pro"): "SEO_PRO",
}


def _tier_checkout_url(prod_name: str, tier_name: str) -> str:
    key = _TIER_KEY_MAP.get((prod_name, tier_name))
    if key:
        return f"/crypto/checkout/{key}"
    return f"mailto:ops@empire-ai.co.uk?subject={prod_name.replace(' ', '%20')}%20{tier_name.replace(' ', '%20')}%20Inquiry"


def _tier_cta(prod_name: str, tier_name: str, original_cta: str) -> str:
    key = _TIER_KEY_MAP.get((prod_name, tier_name))
    if key:
        return "Pay with USDC"
    return original_cta


def mrr_page() -> str:
    """Return the full /mrr landing page HTML with animations, slider, and pricing toggle."""

    extra_css = """
    .mr-wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 32px 80px;
    }

    /* ── HERO SLIDER ────────────────────────────────────────────── */
    .mr-hero-slider {
      position: relative;
      margin-bottom: 56px;
      overflow: hidden;
    }
    .mr-slide-track {
      display: flex;
      transition: transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .mr-slide {
      min-width: 100%;
      text-align: center;
      padding: 0 20px;
    }
    .mr-slide-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 14px;
      animation: empire-fade-up 0.5s 0.1s both;
    }
    .mr-slide-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 48px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.08;
      margin-bottom: 18px;
      animation: empire-fade-up 0.5s 0.15s both;
    }
    .mr-slide-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .mr-slide-sub {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--empire-mist);
      letter-spacing: 0.14em;
      max-width: 640px;
      margin: 0 auto;
      line-height: 1.8;
      animation: empire-fade-up 0.5s 0.2s both;
    }
    .mr-slide-dots {
      display: flex;
      justify-content: center;
      gap: 10px;
      margin-top: 24px;
    }
    .mr-slide-dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--empire-shadow);
      border: 0;
      cursor: pointer;
      transition: all 0.3s var(--ease-snap);
      padding: 0;
    }
    .mr-slide-dot.active {
      background: var(--signal-teal);
      box-shadow: 0 0 8px var(--signal-teal);
      width: 28px;
      border-radius: 5px;
    }
    .mr-slide-dot:hover {
      background: var(--empire-mist);
    }
    .mr-slide-arrows {
      position: absolute;
      top: 50%;
      left: 0;
      right: 0;
      transform: translateY(-50%);
      display: flex;
      justify-content: space-between;
      pointer-events: none;
      padding: 0 16px;
    }
    .mr-slide-arrow {
      pointer-events: auto;
      width: 40px; height: 40px;
      border-radius: 50%;
      background: var(--empire-overlay);
      border: 1px solid var(--empire-divider);
      color: var(--empire-mist);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.2s var(--ease-snap);
      font-size: 18px;
      backdrop-filter: blur(8px);
    }
    .mr-slide-arrow:hover {
      color: var(--signal-teal);
      border-color: var(--signal-teal-soft);
      background: var(--signal-teal-soft);
    }

    /* ── STATS WITH COUNTER ─────────────────────────────────────── */
    .mr-stats {
      display: flex;
      justify-content: center;
      gap: 32px;
      margin-top: 36px;
      flex-wrap: wrap;
    }
    .mr-stat {
      text-align: center;
      opacity: 0;
      transform: translateY(20px);
      transition: all 0.6s var(--ease-out-empire);
    }
    .mr-stat.visible {
      opacity: 1;
      transform: translateY(0);
    }
    .mr-stat-num {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 36px;
      color: var(--signal-teal);
      line-height: 1;
    }
    .mr-stat-label {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-top: 6px;
    }
    .mr-cta-row {
      display: flex;
      justify-content: center;
      gap: 16px;
      margin-top: 32px;
      flex-wrap: wrap;
    }

    /* ── PRICING TOGGLE ─────────────────────────────────────────── */
    .mr-toggle-wrap {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 14px;
      margin-bottom: 24px;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      letter-spacing: 0.1em;
    }
    .mr-toggle-wrap .active-label {
      color: var(--empire-white);
      font-weight: 600;
    }
    .mr-toggle {
      position: relative;
      width: 52px; height: 28px;
      background: var(--empire-divider);
      border-radius: 14px;
      cursor: pointer;
      transition: background 0.3s;
      border: 0;
      padding: 0;
    }
    .mr-toggle.active {
      background: var(--signal-teal-soft);
    }
    .mr-toggle::after {
      content: '';
      position: absolute;
      top: 3px; left: 3px;
      width: 22px; height: 22px;
      border-radius: 50%;
      background: var(--empire-mist);
      transition: all 0.3s var(--ease-snap);
    }
    .mr-toggle.active::after {
      left: 27px;
      background: var(--signal-teal);
    }
    .mr-toggle-save {
      font-size: 9px;
      color: var(--status-green);
      background: rgba(16,185,129,0.1);
      padding: 2px 8px;
      border-radius: 4px;
      margin-left: 4px;
    }

    /* ── SCROLL ANIMATIONS ──────────────────────────────────────── */
    .mr-reveal {
      opacity: 0;
      transform: translateY(30px);
      transition: all 0.6s var(--ease-out-empire);
    }
    .mr-reveal.visible {
      opacity: 1;
      transform: translateY(0);
    }
    .mr-reveal-delay-1 { transition-delay: 0.1s; }
    .mr-reveal-delay-2 { transition-delay: 0.2s; }
    .mr-reveal-delay-3 { transition-delay: 0.3s; }
    .mr-reveal-delay-4 { transition-delay: 0.4s; }

    /* ── PRODUCT CARDS ──────────────────────────────────────────── */
    .mr-product {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      margin-bottom: 16px;
      overflow: hidden;
      transition: all 0.25s var(--ease-snap);
      position: relative;
    }
    .mr-product::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--signal-teal), transparent);
      opacity: 0;
      transition: opacity 0.3s;
    }
    .mr-product:hover::before { opacity: 1; }
    .mr-product:hover {
      border-color: var(--signal-teal-soft);
      transform: translateX(4px);
    }
    .mr-product-header {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 20px 24px;
      cursor: pointer;
      user-select: none;
      transition: background 0.2s;
    }
    .mr-product-header:hover {
      background: rgba(255,255,255,0.02);
    }
    .mr-product-icon {
      font-size: 28px;
      flex-shrink: 0;
      width: 44px;
      text-align: center;
    }
    .mr-product-info {
      flex: 1;
      min-width: 0;
    }
    .mr-product-name {
      font-weight: 600;
      font-size: 16px;
      color: var(--empire-white);
      margin-bottom: 3px;
    }
    .mr-product-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.5;
    }
    .mr-product-price-range {
      font-family: var(--font-mono);
      font-size: 13px;
      color: var(--signal-teal);
      font-weight: 600;
      flex-shrink: 0;
      margin-right: 12px;
      transition: opacity 0.3s;
    }
    .mr-product-chevron {
      flex-shrink: 0;
      width: 18px;
      height: 18px;
      color: var(--empire-fog);
      transition: transform 0.25s ease, color 0.25s;
    }
    .mr-product.expanded .mr-product-chevron {
      transform: rotate(180deg);
      color: var(--signal-teal);
    }

    /* ── TIER CARDS ─────────────────────────────────────────────── */
    .mr-tiers {
      max-height: 0;
      overflow: hidden;
      transition: max-height 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .mr-tiers.open { max-height: 600px; }
    .mr-tiers-inner {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 12px;
      padding: 0 24px 20px;
    }
    .mr-tier {
      background: rgba(0,0,0,0.2);
      border: 1px solid var(--empire-divider);
      padding: 20px;
      display: flex;
      flex-direction: column;
      transition: all 0.2s var(--ease-snap);
      position: relative;
    }
    .mr-tier:hover {
      border-color: var(--empire-border);
      transform: translateY(-2px);
    }
    .mr-tier.highlight {
      border-color: var(--signal-teal);
    }
    .mr-tier.highlight::before {
      content: "Best Value";
      position: absolute;
      top: -10px;
      right: 12px;
      background: var(--signal-teal);
      color: #0A1A2F;
      font-family: var(--font-mono);
      font-size: 8px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      padding: 3px 10px;
      font-weight: 600;
    }
    .mr-tier-name {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.2em;
      text-transform: uppercase;
      margin-bottom: 6px;
    }
    .mr-tier-price {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 34px;
      color: var(--empire-white);
      line-height: 1;
      margin-bottom: 4px;
      transition: opacity 0.3s;
    }
    .mr-tier-price span {
      font-size: 13px;
      color: var(--empire-fog);
      font-weight: 400;
    }
    .mr-tier-price.annual {
      font-size: 28px;
    }
    .mr-tier-price.annual span {
      font-size: 12px;
    }
    .mr-tier-features {
      list-style: none;
      padding: 0;
      margin: 12px 0 16px;
      flex: 1;
    }
    .mr-tier-features li {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      padding: 6px 0;
      border-bottom: 1px solid rgba(122,140,163,0.06);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .mr-tier-features li:last-child { border-bottom: none; }
    .mr-tier-features li::before {
      content: "\\2713";
      color: var(--signal-teal);
      font-weight: 700;
    }
    .mr-tier-btn {
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
      text-align: center;
      transition: opacity 0.2s, transform 0.2s;
    }
    .mr-tier-btn:hover { opacity: 0.85; transform: scale(1.02); }
    .mr-tier-btn.outline {
      background: transparent;
      color: var(--signal-teal);
      border: 1px solid var(--signal-teal);
    }
    .mr-tier-btn.outline:hover {
      background: var(--signal-teal);
      color: #0A1A2F;
    }

    /* ── SECTION LABEL ──────────────────────────────────────────── */
    .mr-section-label {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.22em;
      text-transform: uppercase;
      font-weight: 600;
      margin: 40px 0 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--empire-divider);
    }

    /* ── TESTIMONIAL SLIDER ─────────────────────────────────────── */
    .mr-testimonials {
      margin-top: 80px;
      padding: 48px 0;
      border-top: 1px solid var(--empire-divider);
      border-bottom: 1px solid var(--empire-divider);
    }
    .mr-test-header {
      text-align: center;
      margin-bottom: 36px;
    }
    .mr-test-eyebrow {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--signal-teal);
      letter-spacing: 0.28em;
      text-transform: uppercase;
    }
    .mr-test-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 28px;
      color: var(--empire-white);
      margin-top: 8px;
    }
    .mr-test-track {
      position: relative;
      overflow: hidden;
    }
    .mr-test-inner {
      display: flex;
      transition: transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .mr-test-card {
      min-width: 100%;
      padding: 0 60px;
      text-align: center;
      box-sizing: border-box;
    }
    .mr-test-quote {
      font-size: 18px;
      color: var(--empire-silver);
      line-height: 1.7;
      max-width: 640px;
      margin: 0 auto 20px;
      font-style: italic;
      letter-spacing: -0.01em;
    }
    .mr-test-quote::before { content: "\\201C"; color: var(--signal-teal); font-size: 32px; }
    .mr-test-quote::after { content: "\\201D"; color: var(--signal-teal); font-size: 32px; }
    .mr-test-author {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
    }
    .mr-test-author strong {
      color: var(--empire-white);
      font-weight: 600;
    }
    .mr-test-dots {
      display: flex;
      justify-content: center;
      gap: 8px;
      margin-top: 24px;
    }
    .mr-test-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: var(--empire-shadow);
      border: 0;
      cursor: pointer;
      transition: all 0.3s var(--ease-snap);
      padding: 0;
    }
    .mr-test-dot.active {
      background: var(--signal-teal);
      box-shadow: 0 0 6px var(--signal-teal);
    }
    .mr-test-dot:hover { background: var(--empire-mist); }

    /* ── FOOTER ─────────────────────────────────────────────────── */
    .mr-foot {
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
    .mr-foot a { color: var(--empire-mist); text-decoration: none; }
    .mr-foot a:hover { color: var(--signal-teal); }

    @media (max-width: 900px) {
      .mr-slide-title { font-size: 32px; }
      .mr-tiers-inner { grid-template-columns: 1fr; }
      .mr-test-card { padding: 0 24px; }
      .mr-test-quote { font-size: 15px; }
    }
    """

    # ── HERO SLIDES DATA ────────────────────────────────────────────────
    hero_slides = [
        {
            "title": '<em>16 Products</em> · One Platform<br>Unified MRR Pricing',
            "sub": "From lead generation to revenue intelligence — every product in the Empire AI Suite, with transparent pricing and no hidden fees.",
        },
        {
            "title": '<em>AI-Powered</em> Lead Scoring<br>Start at <em>$49/mo</em>',
            "sub": "Bayesian models, batch processing, and CSV export. The most advanced lead intelligence platform on the market.",
        },
        {
            "title": '<em>Full Suite</em> Access<br><em>$2,499/mo</em> — Everything Included',
            "sub": "All 16 products. Unlimited usage. Priority support. The complete predictive revenue engine in one subscription.",
        },
    ]

    slides_html = ""
    for si, slide in enumerate(hero_slides):
        active_cls = ' style="display:block"' if si == 0 else ' style="display:none"'
        slides_html += f"""
        <div class="mr-slide" data-slide="{si}"{active_cls}>
          <div class="mr-slide-eyebrow">Empire AI Suite</div>
          <h2 class="mr-slide-title">{slide['title']}</h2>
          <p class="mr-slide-sub">{slide['sub']}</p>
        </div>"""

    dots_html = "".join(
        f'<button class="mr-slide-dot{" active" if si == 0 else ""}" onclick="goToSlide({si})" aria-label="Slide {si+1}"></button>'
        for si in range(len(hero_slides))
    )

    stats_data = [
        ("16", "Products"),
        ("42", "Tiers / SKUs"),
        ("$49", "Starting Price"),
        ("$2,499", "All Access"),
    ]

    stats_html = "".join(
        f"""
        <div class="mr-stat" data-count="{s[0]}">
          <div class="mr-stat-num">{s[0]}</div>
          <div class="mr-stat-label">{s[1]}</div>
        </div>"""
        for si, s in enumerate(stats_data)
    )

    # ── PRODUCT CARDS ──────────────────────────────────────────────────
    products_html = ""
    for pi, prod in enumerate(MRR_PRODUCTS):
        min_price = min(t["price"] for t in prod["tiers"])
        max_price = max(t["price"] for t in prod["tiers"])
        if min_price == max_price:
            price_range = f"${min_price}/mo"
        else:
            price_range = f"${min_price} – ${max_price}/mo"

        tiers_html = ""
        for ti, tier in enumerate(prod["tiers"]):
            hl = " highlight" if tier.get("highlight") else ""
            features_list = "".join(f"<li>{f}</li>" for f in tier["features"])
            btn_class = "" if tier.get("highlight") else " outline"
            annual_price = round(tier["price"] * 10)  # ~2 months free
            tiers_html += f"""
            <div class="mr-tier{hl}">
              <div class="mr-tier-name">{tier['name']}</div>
              <div class="mr-tier-price" data-monthly="${tier['price']}" data-annual="${annual_price}">
                ${tier['price']}<span>/mo</span>
              </div>
              <ul class="mr-tier-features">{features_list}</ul>
              <a class="mr-tier-btn{btn_class}" href="{_tier_checkout_url(prod['name'], tier['name'])}">{_tier_cta(prod['name'], tier['name'], prod['cta'])}</a>
            </div>"""

        delay = pi % 4
        products_html += f"""
    <div class="mr-product mr-reveal mr-reveal-delay-{delay}" id="mr-prod-{pi}">
      <div class="mr-product-header" onclick="toggleMrTiers({pi})" role="button" tabindex="0" aria-expanded="false" aria-controls="mr-tiers-{pi}">
        <div class="mr-product-icon">{prod['icon']}</div>
        <div class="mr-product-info">
          <div class="mr-product-name">{prod['name']}</div>
          <div class="mr-product-desc">{prod['desc']}</div>
        </div>
        <div class="mr-product-price-range">{price_range}</div>
        <svg class="mr-product-chevron" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7l5 5 5-5"/></svg>
      </div>
      <div class="mr-tiers" id="mr-tiers-{pi}">
        <div class="mr-tiers-inner">{tiers_html}</div>
      </div>
    </div>"""

    # ── TESTIMONIALS ──────────────────────────────────────────────────
    testimonials = [
        {"quote": "Empire AI's lead scoring cut our prospecting time by 60%. We now focus only on high-intent leads and close 3x more deals.", "author": "Operations Director", "company": "National Roofing Corp"},
        {"quote": "The Strike Campaigns platform automated our entire outreach pipeline. From lead discovery to SMS follow-up — it runs itself.", "author": "VP of Sales", "company": "Premier Home Services"},
        {"quote": "We evaluated 12 lead gen platforms. Empire AI's predictive engine was the only one that consistently delivered qualified, verified leads.", "author": "CEO", "company": "Summit Restoration"},
        {"quote": "The compliance layer alone saves us thousands in legal fees. TCPA, DNC, quiet hours — all automated and audited.", "author": "General Counsel", "company": "Liberty Contractors"},
    ]

    test_cards_html = ""
    for ti, t in enumerate(testimonials):
        test_cards_html += f"""
        <div class="mr-test-card" data-test="{ti}">
          <div class="mr-test-quote">{t['quote']}</div>
          <div class="mr-test-author"><strong>{t['author']}</strong> · {t['company']}</div>
        </div>"""

    test_dots_html = "".join(
        f'<button class="mr-test-dot{" active" if ti == 0 else ""}" onclick="goToTestimonial({ti})" aria-label="Testimonial {ti+1}"></button>'
        for ti in range(len(testimonials))
    )

    head = empire_head(title="Empire AI Suite · Products & Pricing · MRR", extra=extra_css, page="mrr")

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>
<h1 class="sr-only">Empire AI Suite · Products &amp; Pricing</h1>

<div class="mr-wrap">

  <!-- ── HERO SLIDER ──────────────────────────────────────────────── -->
  <div class="mr-hero-slider">
    <div class="mr-slide-track" id="mr-slide-track">
      {slides_html}
    </div>
    <div class="mr-slide-arrows">
      <button class="mr-slide-arrow" onclick="prevSlide()" aria-label="Previous slide">\\u2039</button>
      <button class="mr-slide-arrow" onclick="nextSlide()" aria-label="Next slide">\\u203a</button>
    </div>
    <div class="mr-slide-dots" id="mr-slide-dots">
      {dots_html}
    </div>
  </div>

  <!-- ── STATS ────────────────────────────────────────────────────── -->
  <div class="mr-stats" id="mr-stats">
    {stats_html}
  </div>

  <div class="mr-cta-row">
    <a class="e-btn" href="mailto:ops@empire-ai.co.uk?subject=Empire%20AI%20Suite%20Inquiry">Contact Sales</a>
    <a class="e-btn" href="/products/meetily" style="background:transparent;color:var(--signal-teal);border:1px solid var(--signal-teal);">View Meetily</a>
    <a class="e-btn" href="/products/elite-scraper" style="background:transparent;color:var(--signal-teal);border:1px solid var(--signal-teal);">View Scraper</a>
  </div>

  <!-- ── PRICING TOGGLE ───────────────────────────────────────────── -->
  <div class="mr-section-label" style="margin-top:64px;">All Products · Click to expand tiers</div>

  <div class="mr-toggle-wrap">
    <span class="active-label" id="toggle-label-monthly">Monthly</span>
    <button class="mr-toggle" id="pricing-toggle" onclick="togglePricing()" role="switch" aria-checked="false" aria-label="Toggle annual pricing">
    </button>
    <span id="toggle-label-annual">Annual <span class="mr-toggle-save">Save ~17%</span></span>
  </div>

  <!-- ── PRODUCTS LIST ────────────────────────────────────────────── -->
  <div id="mr-products-list">
    {products_html}
  </div>

  <!-- ── TESTIMONIAL SLIDER ───────────────────────────────────────── -->
  <div class="mr-testimonials mr-reveal" id="mr-testimonials">
    <div class="mr-test-header">
      <div class="mr-test-eyebrow">What Our Customers Say</div>
      <div class="mr-test-title">Trusted by leading contractors nationwide</div>
    </div>
    <div class="mr-test-track">
      <div class="mr-test-inner" id="mr-test-inner">
        {test_cards_html}
      </div>
    </div>
    <div class="mr-test-dots" id="mr-test-dots">
      {test_dots_html}
    </div>
  </div>

  <!-- ── FOOTER ───────────────────────────────────────────────────── -->
  <div class="mr-foot">
    <a href="/">Empire AI</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/pricing">Legacy Pricing</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/ppl">Pay-Per-Lead</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/products/meetily">Meetily</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/products/elite-scraper">Elite Scraper</a>
    <br>
    <span style="letter-spacing:0.12em;color:var(--empire-shadow);margin-top:8px;display:block;">
      MRR Suite · 16 Products · Transparent Pricing
    </span>
  </div>

</div>

<script>
(function() {{
  // ── PRODUCT EXPAND/COLLAPSE ────────────────────────────────────────
  window.toggleMrTiers = function(idx) {{
    var prod = document.getElementById('mr-prod-' + idx);
    var tiers = document.getElementById('mr-tiers-' + idx);
    var header = prod.querySelector('.mr-product-header');
    if (!prod || !tiers) return;
    var expanded = prod.classList.toggle('expanded');
    tiers.classList.toggle('open');
    header.setAttribute('aria-expanded', expanded);
  }};

  // ── HERO SLIDER ──────────────────────────────────────────────────
  var currentSlide = 0;
  var totalSlides = {len(hero_slides)};

  function updateSlide() {{
    var track = document.getElementById('mr-slide-track');
    var slides = track.querySelectorAll('.mr-slide');
    var dots = document.querySelectorAll('.mr-slide-dot');
    slides.forEach(function(s, i) {{
      s.style.display = i === currentSlide ? 'block' : 'none';
    }});
    dots.forEach(function(d, i) {{
      d.classList.toggle('active', i === currentSlide);
    }});
  }}

  window.goToSlide = function(idx) {{
    currentSlide = idx;
    updateSlide();
  }};

  window.nextSlide = function() {{
    currentSlide = (currentSlide + 1) % totalSlides;
    updateSlide();
  }};

  window.prevSlide = function() {{
    currentSlide = (currentSlide - 1 + totalSlides) % totalSlides;
    updateSlide();
  }};

  // Auto-rotate hero slider every 5s
  setInterval(window.nextSlide, 5000);

  // ── TESTIMONIAL SLIDER ──────────────────────────────────────────
  var currentTest = 0;
  var totalTests = {len(testimonials)};

  window.goToTestimonial = function(idx) {{
    currentTest = idx;
    var inner = document.getElementById('mr-test-inner');
    var dots = document.querySelectorAll('.mr-test-dot');
    inner.style.transform = 'translateX(-' + (idx * 100) + '%)';
    dots.forEach(function(d, i) {{
      d.classList.toggle('active', i === idx);
    }});
  }};

  // Auto-rotate testimonials every 6s
  setInterval(function() {{
    window.goToTestimonial((currentTest + 1) % totalTests);
  }}, 6000);

  // ── PRICING TOGGLE (Monthly / Annual) ───────────────────────────
  var isAnnual = false;

  window.togglePricing = function() {{
    isAnnual = !isAnnual;
    var toggle = document.getElementById('pricing-toggle');
    var monthlyLabel = document.getElementById('toggle-label-monthly');
    var annualLabel = document.getElementById('toggle-label-annual');
    toggle.classList.toggle('active', isAnnual);
    monthlyLabel.classList.toggle('active-label', !isAnnual);
    annualLabel.classList.toggle('active-label', isAnnual);

    // Update all tier prices
    document.querySelectorAll('.mr-tier').forEach(function(tier) {{
      var priceEl = tier.querySelector('.mr-tier-price');
      if (!priceEl) return;
      if (isAnnual) {{
        var annualPrice = priceEl.getAttribute('data-annual');
        if (annualPrice) {{
          priceEl.innerHTML = '$' + annualPrice + '<span>/mo billed annually</span>';
        }}
      }} else {{
        var monthlyPrice = priceEl.getAttribute('data-monthly');
        if (monthlyPrice) {{
          priceEl.innerHTML = '$' + monthlyPrice + '<span>/mo</span>';
        }}
      }}
    }});

    // Update price ranges in product headers
    document.querySelectorAll('.mr-product-price-range').forEach(function(el) {{
      var monthly = el.getAttribute('data-monthly-range');
      var annual = el.getAttribute('data-annual-range');
      if (isAnnual && annual) {{
        el.textContent = annual;
      }} else if (monthly) {{
        el.textContent = monthly;
      }}
    }});
  }};

  // Store both monthly and annual price ranges on product headers
  document.querySelectorAll('.mr-product').forEach(function(prod) {{
    var priceEl = prod.querySelector('.mr-product-price-range');
    if (!priceEl) return;
    var monthlyText = priceEl.textContent;
    priceEl.setAttribute('data-monthly-range', monthlyText);
    // Calculate annual: take the numbers and multiply by 10 (~2 months free)
    var annualText = monthlyText.replace(/\\$[\\d,]+/g, function(m) {{
      var num = parseInt(m.replace(/[$,]/g, ''));
      return '$' + (num * 10);
    }});
    priceEl.setAttribute('data-annual-range', annualText + ' billed annually');
  }});

  // ── SCROLL REVEAL ANIMATIONS ────────────────────────────────────
  function checkReveals() {{
    var reveals = document.querySelectorAll('.mr-reveal');
    var stats = document.querySelectorAll('.mr-stat');
    var winH = window.innerHeight;

    reveals.forEach(function(el) {{
      var rect = el.getBoundingClientRect();
      if (rect.top < winH - 60) {{
        el.classList.add('visible');
      }}
    }});

    stats.forEach(function(el) {{
      var rect = el.getBoundingClientRect();
      if (rect.top < winH - 40) {{
        el.classList.add('visible');
      }}
    }});
  }}

  window.addEventListener('scroll', checkReveals);
  checkReveals();  // initial check

}})();
</script>

</body>
</html>"""
