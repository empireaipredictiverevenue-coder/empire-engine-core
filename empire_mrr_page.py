"""
EMPIRE V49 · UNIFIED MRR PRICING PAGE
=======================================
Comprehensive landing page at /mrr showing all 16 Empire AI Suite products
with pricing tiers, features, and links to individual product pages.

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

# Sort: products with active subs first, then alphabetically
SORT_ORDER = {
    "All Access": 0, "LeadScore AI": 1, "Compliant": 2, "Strike Campaigns": 3,
    "HexStrike AI": 4, "SEO Optimizer": 5, "Analyzer Agent": 6, "Inbound Router": 7,
    "Data Vault": 8, "Buyer Spy AI": 9, "Forecast": 10, "Market Eye": 11,
    "Content Pulse": 12, "Contractor Exchange": 13, "Meetily AI": 14, "Elite Scraper v2": 15,
}
MRR_PRODUCTS.sort(key=lambda p: SORT_ORDER.get(p["name"], 99))

# ── Tier → Crypto Checkout Key Mapping ──────────────────────────
# Maps (product_name, tier_name) to the tier key used in
# /crypto/checkout/{tier} and TIER_PRICES_USDC.
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
    """Return the /crypto/checkout/{tier} URL for a product+tier, or mailto fallback."""
    key = _TIER_KEY_MAP.get((prod_name, tier_name))
    if key:
        return f"/crypto/checkout/{key}"
    return f"mailto:ops@empire-ai.co.uk?subject={prod_name.replace(' ', '%20')}%20{tier_name.replace(' ', '%20')}%20Inquiry"


def _tier_cta(prod_name: str, tier_name: str, original_cta: str) -> str:
    """Return the appropriate CTA text for a tier button.
    
    Products wired to crypto checkout get "Pay with USDC";
    unmatched products keep their original CTA (mailto fallback).
    """
    key = _TIER_KEY_MAP.get((prod_name, tier_name))
    if key:
        return "Pay with USDC"
    return original_cta


def mrr_page() -> str:
    """Return the full /mrr landing page HTML."""

    extra_css = """
    .mr-wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 32px 80px;
    }
    .mr-hero {
      text-align: center;
      margin-bottom: 56px;
    }
    .mr-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 14px;
    }
    .mr-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 48px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.08;
      margin-bottom: 18px;
    }
    .mr-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .mr-sub {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--empire-mist);
      letter-spacing: 0.14em;
      max-width: 640px;
      margin: 0 auto;
      line-height: 1.8;
    }
    .mr-stats {
      display: flex;
      justify-content: center;
      gap: 32px;
      margin-top: 36px;
      flex-wrap: wrap;
    }
    .mr-stat { text-align: center; }
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

    /* Product cards */
    .mr-product {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      margin-bottom: 16px;
      overflow: hidden;
      transition: all 0.25s var(--ease-snap);
    }
    .mr-product:hover {
      border-color: var(--signal-teal-soft);
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
    }
    .mr-product-chevron {
      flex-shrink: 0;
      width: 18px;
      height: 18px;
      color: var(--empire-fog);
      transition: transform 0.25s ease;
    }
    .mr-product.expanded .mr-product-chevron {
      transform: rotate(180deg);
      color: var(--signal-teal);
    }

    /* Tier cards inside the expandable section */
    .mr-tiers {
      max-height: 0;
      overflow: hidden;
      transition: max-height 0.35s ease;
    }
    .mr-tiers.open {
      max-height: 600px;
    }
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
    }
    .mr-tier:hover {
      border-color: var(--empire-border);
    }
    .mr-tier.highlight {
      border-color: var(--signal-teal);
      position: relative;
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
    }
    .mr-tier-price span {
      font-size: 13px;
      color: var(--empire-fog);
      font-weight: 400;
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
      transition: opacity 0.2s;
    }
    .mr-tier-btn:hover { opacity: 0.85; }
    .mr-tier-btn.outline {
      background: transparent;
      color: var(--signal-teal);
      border: 1px solid var(--signal-teal);
    }
    .mr-tier-btn.outline:hover {
      background: var(--signal-teal);
      color: #0A1A2F;
    }

    /* Section label */
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

    /* Footer */
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
      .mr-title { font-size: 32px; }
      .mr-tiers-inner { grid-template-columns: 1fr; }
    }
    """

    # Build product cards
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
            tiers_html += f"""
            <div class="mr-tier{hl}">
              <div class="mr-tier-name">{tier['name']}</div>
              <div class="mr-tier-price">${tier['price']}<span>/mo</span></div>
              <ul class="mr-tier-features">{features_list}</ul>
              <a class="mr-tier-btn{btn_class}" href="{_tier_checkout_url(prod['name'], tier['name'])}">{_tier_cta(prod['name'], tier['name'], prod['cta'])}</a>
            </div>"""

        products_html += f"""
    <div class="mr-product" id="mr-prod-{pi}">
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

    head = empire_head(title="Empire AI Suite · Products & Pricing · MRR", extra=extra_css)

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="mr-wrap">

  <div class="mr-hero">
    <div class="mr-eyebrow">Empire AI Suite</div>
    <h1 class="mr-title"><em>16 Products</em> · One Platform<br>Unified MRR Pricing</h1>
    <p class="mr-sub">
      From lead generation to revenue intelligence — every product in the Empire AI Suite,
      with transparent pricing and no hidden fees.
    </p>
    <div class="mr-stats">
      <div class="mr-stat">
        <div class="mr-stat-num">16</div>
        <div class="mr-stat-label">Products</div>
      </div>
      <div class="mr-stat">
        <div class="mr-stat-num">42</div>
        <div class="mr-stat-label">Tiers / SKUs</div>
      </div>
      <div class="mr-stat">
        <div class="mr-stat-num">$49</div>
        <div class="mr-stat-label">Starting Price</div>
      </div>
      <div class="mr-stat">
        <div class="mr-stat-num">$2,499</div>
        <div class="mr-stat-label">All Access</div>
      </div>
    </div>
    <div class="mr-cta-row">
      <a class="e-btn" href="mailto:ops@empire-ai.co.uk?subject=Empire%20AI%20Suite%20Inquiry">Contact Sales</a>
      <a class="e-btn" href="/products/meetily" style="background:transparent;color:var(--signal-teal);border:1px solid var(--signal-teal);">View Meetily</a>
      <a class="e-btn" href="/products/elite-scraper" style="background:transparent;color:var(--signal-teal);border:1px solid var(--signal-teal);">View Scraper</a>
    </div>
  </div>

  <div class="mr-section-label">All Products · Click to expand tiers and pricing</div>

  {products_html}

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
  window.toggleMrTiers = function(idx) {{
    var prod = document.getElementById('mr-prod-' + idx);
    var tiers = document.getElementById('mr-tiers-' + idx);
    var header = prod.querySelector('.mr-product-header');
    if (!prod || !tiers) return;
    var expanded = prod.classList.toggle('expanded');
    tiers.classList.toggle('open');
    header.setAttribute('aria-expanded', expanded);
  }};
}})();
</script>

</body>
</html>"""
