"""
EMPIRE V49 · ELITE SCRAPER V2 PRODUCT PAGE
=============================================
Dedicated landing page at /products/elite-scraper for the Predictive Revenue
Fleet — AI-powered scraper agents using camofox-browser.

Wire-up in hub.py:
    from empire_scraper_page import scraper_page

    @app.get("/products/elite-scraper", response_class=HTMLResponse)
    async def elite_scraper_product_page():
        return HTMLResponse(scraper_page())
"""

from empire_tokens import empire_head

SCRAPER_FEATURES = [
    {
        "icon": "🦊",
        "title": "Camofox Stealth Scraper",
        "desc": "B2B lead scraping via camofox-browser with search macros (@yelp_search, @google_search). Scrapes 6 niches across 4+ metros without getting blocked.",
    },
    {
        "icon": "🎯",
        "title": "Predictive Prospector",
        "desc": "Autonomous lead discovery agent. Supports 36+ lanes with AGI self-improvement — adapts scraping weights based on performance data.",
    },
    {
        "icon": "🎬",
        "title": "YouTube Intelligence",
        "desc": "Scrapes YouTube transcripts and feeds them to Synthetic Brain for idea extraction, competitive strategy analysis, and niche discovery.",
    },
    {
        "icon": "🧠",
        "title": "Synthetic Brain Scoring",
        "desc": "Every lead is scored by the Synthetic Brain — LLM-powered deep reasoning for opportunity analysis and strategic value assessment.",
    },
    {
        "icon": "🔄",
        "title": "AGI Self-Improvement",
        "desc": "Adaptive weight optimization across relevance, volume, and difficulty. The scraper fleet learns and improves without human tuning.",
    },
    {
        "icon": "🔗",
        "title": "Fleet Pipeline Integration",
        "desc": "Scraped opportunities feed directly into the Predictive Revenue Fleet — Deep Research Agent → Outreach Agent → Dispatch pipeline.",
    },
]

SCRAPER_TIERS_DISPLAY = [
    {
        "tier": "Starter",
        "price": 149,
        "period": "/month",
        "desc": "Single-niche B2B scraping for small operations.",
        "features": [
            "1 niche (roofing, HVAC, solar, restoration, PA, or commercial)",
            "100 leads/month",
            "Camofox-browser stealth scraping",
            "Basic enrichment (name, phone, address)",
            "Weekly delivery via CSV or API",
            "Email support",
        ],
        "cta": "Get Started",
        "highlight": False,
    },
    {
        "tier": "Pro",
        "price": 499,
        "period": "/month",
        "desc": "Multi-niche scraping with YouTube intel and predictive scoring.",
        "features": [
            "Up to 3 niches across 4 metros",
            "500 leads/month",
            "Camofox-browser + search macros",
            "YouTube transcript scraping + SB analysis",
            "Predictive lead scoring (LLM + rules)",
            "Smart deduplication across sources",
            "Real-time delivery via API/webhook",
            "Priority email support",
        ],
        "cta": "Get Started",
        "highlight": True,
    },
    {
        "tier": "Enterprise",
        "price": 1999,
        "period": "/month",
        "desc": "Full scraper fleet with Prospector, YouTube, and managed infrastructure.",
        "features": [
            "All 6+ niches across 4+ metros (36+ lanes)",
            "5,000+ leads/month",
            "Camofox-browser + proxy rotation + sessions",
            "Predictive Prospector Agent (autonomous)",
            "YouTube scraper for competitive intel",
            "Synthetic Brain deep reasoning",
            "AGI self-improving scrape strategy",
            "API-first integration + webhooks",
            "99.9% SLA",
            "Dedicated support engineer",
        ],
        "cta": "Contact Sales",
        "highlight": False,
    },
]

SCRAPER_HOW_IT_WORKS = [
    {
        "step": "01",
        "title": "Configure Targets",
        "desc": "Select niches (roofing, HVAC, solar, etc.) and metros. Enterprise tier gets all 36+ lanes with custom configuration.",
    },
    {
        "step": "02",
        "title": "Camofox Scraping",
        "desc": "Camofox-browser runs stealth scrapes using search macros. Prospector Agent discovers new leads autonomously.",
    },
    {
        "step": "03",
        "title": "Enrich & Score",
        "desc": "Synthetic Brain scores every lead. YouTube scraper provides competitive content intelligence for each niche.",
    },
    {
        "step": "04",
        "title": "Deliver & Act",
        "desc": "Scored, enriched leads delivered via API/webhook or CSV. Feeds directly into the Predictive Revenue Fleet pipeline.",
    },
]

SCRAPER_VERTICALS = [
    {"name": "Roofing", "desc": "Residential & commercial roofers", "agents": "Camofox + Prospector"},
    {"name": "HVAC", "desc": "Heating & cooling contractors", "agents": "Camofox + Prospector"},
    {"name": "Solar", "desc": "Commercial & residential solar", "agents": "Camofox + Prospector"},
    {"name": "Restoration", "desc": "Water/fire/mold restoration", "agents": "Camofox + YouTube"},
    {"name": "Public Adjuster", "desc": "Licensed insurance adjusters", "agents": "Camofox + Prospector"},
    {"name": "Commercial", "desc": "General commercial contractors", "agents": "Camofox + YouTube"},
]

SCRAPER_FAQ = [
    {
        "q": "What scraper agents are included?",
        "a": "Three agents work together: (1) Predictive Camofox Scraper — B2B lead scraping via camofox-browser stealth browser, (2) Predictive YouTube Scraper — transcript extraction and competitive content intelligence, (3) Predictive Prospector Agent — autonomous lead discovery across 36+ lanes.",
    },
    {
        "q": "How does the camofox-browser avoid getting blocked?",
        "a": "Camofox-browser uses advanced anti-detection techniques — custom user agents, browser fingerprint randomization, stealth macros, and configurable rate limiting. Enterprise tier adds proxy rotation and session persistence.",
    },
    {
        "q": "What data does each lead include?",
        "a": "Every lead includes company name, phone, address, niche classification, and source attribution. Pro+ tiers add email, website, social profiles, and a Synthetic Brain quality score.",
    },
    {
        "q": "Can I target specific metros?",
        "a": "Yes. Standard metros are Texas, Florida, California, and Arizona. Enterprise tier supports custom metro configuration and geo-fenced searches.",
    },
    {
        "q": "What does the Synthetic Brain do with scraped data?",
        "a": "The Synthetic Brain scores each lead for strategic value (0-100), extracts deep reasoning about opportunity quality, and identifies competitive positioning. YouTube transcripts are analyzed for niche-relevant ideas and strategies.",
    },
    {
        "q": "How does AGI self-improvement work?",
        "a": "The scraper agents continuously adjust their internal weights (relevance, volume, difficulty) based on scraping performance. Over time, the fleet learns which niches and sources yield the highest-quality leads and prioritizes them automatically.",
    },
]


def scraper_page() -> str:
    """Return the full /products/elite-scraper landing page HTML."""

    extra_css = """
    .sc-wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 32px 80px;
    }
    .sc-hero {
      text-align: center;
      margin-bottom: 64px;
    }
    .sc-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 14px;
    }
    .sc-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 52px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.08;
      margin-bottom: 18px;
    }
    .sc-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .sc-sub {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--empire-mist);
      letter-spacing: 0.14em;
      max-width: 640px;
      margin: 0 auto;
      line-height: 1.8;
    }
    .sc-cta-row {
      display: flex;
      justify-content: center;
      gap: 16px;
      margin-top: 32px;
      flex-wrap: wrap;
    }
    .sc-section {
      margin-bottom: 72px;
    }
    .sc-section-h {
      display: flex;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 28px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .sc-section-num {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--signal-teal);
      letter-spacing: 0.12em;
    }
    .sc-section-title {
      font-weight: 500;
      font-size: 22px;
      letter-spacing: -0.02em;
      color: var(--empire-white);
    }
    .sc-features {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }
    .sc-feature {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 28px 22px;
      transition: all 0.25s var(--ease-snap);
    }
    .sc-feature:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
    }
    .sc-feature-icon { font-size: 28px; margin-bottom: 14px; }
    .sc-feature-title {
      font-weight: 600; font-size: 15px;
      color: var(--empire-white); margin-bottom: 10px;
    }
    .sc-feature-desc {
      font-size: 12px; color: var(--empire-mist);
      line-height: 1.7;
    }
    .sc-steps {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }
    .sc-step {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 28px 22px;
      transition: all 0.25s var(--ease-snap);
    }
    .sc-step:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
    }
    .sc-step-num {
      font-family: var(--font-mono); font-size: 12px;
      color: var(--signal-teal); margin-bottom: 12px;
    }
    .sc-step-title {
      font-weight: 600; font-size: 15px;
      color: var(--empire-white); margin-bottom: 10px;
    }
    .sc-step-desc {
      font-size: 12px; color: var(--empire-mist); line-height: 1.7;
    }
    .sc-pricing {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }
    .sc-card {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 32px 24px;
      display: flex;
      flex-direction: column;
      transition: all 0.3s var(--ease-snap);
    }
    .sc-card:hover { transform: translateY(-3px); }
    .sc-card.highlight {
      border-color: var(--signal-teal);
      position: relative;
    }
    .sc-card.highlight::before {
      content: "Most Popular";
      position: absolute;
      top: -12px; left: 50%;
      transform: translateX(-50%);
      background: var(--signal-teal);
      color: #0A1A2F;
      font-family: var(--font-mono);
      font-size: 9px; letter-spacing: 0.2em;
      text-transform: uppercase;
      padding: 4px 14px;
      font-weight: 600;
    }
    .sc-card-tier {
      font-family: var(--font-mono); font-size: 10px;
      color: var(--signal-teal); letter-spacing: 0.24em;
      text-transform: uppercase; margin-bottom: 8px;
    }
    .sc-card-price {
      font-family: var(--font-display);
      font-weight: 200; font-size: 40px;
      color: var(--empire-white); line-height: 1;
      margin-bottom: 4px;
    }
    .sc-card-price span {
      font-size: 14px; color: var(--empire-fog); font-weight: 400;
    }
    .sc-card-desc {
      font-size: 12px; color: var(--empire-mist);
      line-height: 1.6; margin-bottom: 20px;
      margin-top: 8px; min-height: 40px;
    }
    .sc-card-features {
      list-style: none; padding: 0; margin: 0 0 24px; flex: 1;
    }
    .sc-card-features li {
      font-family: var(--font-mono); font-size: 11px;
      color: var(--empire-mist);
      padding: 8px 0; border-bottom: 1px solid var(--empire-divider);
      display: flex; align-items: center; gap: 8px;
    }
    .sc-card-features li:last-child { border-bottom: none; }
    .sc-card-features li::before {
      content: "\\2713"; color: var(--signal-teal); font-weight: 700;
    }
    .sc-card-btn {
      display: inline-block; padding: 12px 24px;
      font-size: 13px; font-weight: 600;
      color: #0A1A2F; background: var(--signal-teal);
      border: 0; border-radius: var(--radius-sm);
      cursor: pointer; text-decoration: none; text-align: center;
      transition: opacity 0.2s;
    }
    .sc-card-btn:hover { opacity: 0.85; }
    .sc-card-btn.outline {
      background: transparent; color: var(--signal-teal);
      border: 1px solid var(--signal-teal);
    }
    .sc-card-btn.outline:hover {
      background: var(--signal-teal); color: #0A1A2F;
    }
    .sc-verticals {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 12px;
    }
    .sc-vertical {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 20px 16px;
      text-align: center;
      transition: all 0.2s var(--ease-snap);
    }
    .sc-vertical:hover {
      border-color: var(--signal-teal-soft);
    }
    .sc-vertical-name {
      font-weight: 600; font-size: 14px;
      color: var(--empire-white); margin-bottom: 6px;
    }
    .sc-vertical-desc {
      font-size: 11px; color: var(--empire-mist); margin-bottom: 8px;
    }
    .sc-vertical-meta {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-fog); letter-spacing: 0.12em;
    }
    .sc-faq-list { max-width: 720px; }
    .sc-faq-item {
      border-bottom: 1px solid var(--empire-divider); padding: 18px 0;
    }
    .sc-faq-item:first-child { padding-top: 0; }
    .sc-faq-q {
      display: flex; justify-content: space-between; align-items: center;
      width: 100%; padding: 0; cursor: pointer; border: none;
      background: none; font: inherit; text-align: left;
      color: var(--empire-white); font-weight: 500; font-size: 14px;
      margin-bottom: 8px; user-select: none; appearance: none;
    }
    .sc-faq-q:hover { color: var(--signal-teal); }
    .sc-faq-q[aria-expanded="true"] { color: var(--signal-teal); }
    .sc-faq-chevron {
      flex-shrink: 0; margin-left: 12px; width: 18px; height: 18px;
      transition: transform 0.25s ease; color: var(--empire-fog);
      pointer-events: none;
    }
    .sc-faq-q[aria-expanded="true"] .sc-faq-chevron {
      transform: rotate(180deg); color: var(--signal-teal);
    }
    .sc-faq-a {
      font-size: 13px; color: var(--empire-mist); line-height: 1.7;
      overflow: hidden; max-height: 0; opacity: 0;
      transition: max-height 0.3s ease, opacity 0.25s ease, padding 0.15s ease;
    }
    .sc-faq-a.open { max-height: 300px; opacity: 1; }
    .sc-stats {
      display: flex; justify-content: center;
      gap: 32px; margin-top: 36px; flex-wrap: wrap;
    }
    .sc-stat { text-align: center; }
    .sc-stat-num {
      font-family: var(--font-display);
      font-weight: 200; font-size: 36px;
      color: var(--signal-teal); line-height: 1;
    }
    .sc-stat-label {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-fog); letter-spacing: 0.18em;
      text-transform: uppercase; margin-top: 6px;
    }
    .sc-agents {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }
    .sc-agent {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 24px 20px;
      text-align: center;
      transition: all 0.25s var(--ease-snap);
    }
    .sc-agent:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
    }
    .sc-agent-icon { font-size: 36px; margin-bottom: 12px; }
    .sc-agent-name {
      font-weight: 600; font-size: 14px;
      color: var(--empire-white); margin-bottom: 6px;
    }
    .sc-agent-file {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--signal-teal); letter-spacing: 0.1em;
      margin-bottom: 10px;
    }
    .sc-agent-desc {
      font-size: 11px; color: var(--empire-mist); line-height: 1.6;
    }
    .sc-foot {
      margin-top: 64px; padding-top: 24px;
      border-top: 1px solid var(--empire-divider);
      text-align: center; font-family: var(--font-mono);
      font-size: 9px; color: var(--empire-fog);
      letter-spacing: 0.24em; text-transform: uppercase;
    }
    .sc-foot a { color: var(--empire-mist); text-decoration: none; }
    .sc-foot a:hover { color: var(--signal-teal); }
    @media (max-width: 900px) {
      .sc-title { font-size: 36px; }
      .sc-features { grid-template-columns: repeat(2, 1fr); }
      .sc-agents { grid-template-columns: repeat(2, 1fr); }
      .sc-steps { grid-template-columns: repeat(2, 1fr); }
      .sc-pricing { grid-template-columns: 1fr; max-width: 400px; margin: 0 auto; }
    }
    @media (max-width: 540px) {
      .sc-features, .sc-agents { grid-template-columns: 1fr; }
      .sc-steps { grid-template-columns: 1fr; }
    }
    """

    features_html = ""
    for i, f in enumerate(SCRAPER_FEATURES):
        features_html += f"""
    <div class="sc-feature" style="animation-delay: {0.04 * i}s">
      <div class="sc-feature-icon">{f['icon']}</div>
      <div class="sc-feature-title">{f['title']}</div>
      <div class="sc-feature-desc">{f['desc']}</div>
    </div>"""

    agents_html = ""
    agents_data = [
        {"icon": "🦊", "name": "Camofox Scraper", "file": "bots/predictive_camofox_scraper.py", "desc": "Stealth B2B lead scraper using camofox-browser. 6 niches, 4 metros, search macros, proxy rotation."},
        {"icon": "🎬", "name": "YouTube Scraper", "file": "bots/predictive_youtube_scraper.py", "desc": "Video transcript scraper. Extracts content intelligence and feeds Synthetic Brain for niche analysis."},
        {"icon": "🔍", "name": "Prospector Agent", "file": "bots/predictive_prospector_agent.py", "desc": "Autonomous lead discovery across 36+ lanes. AGI self-improving scrape strategy."},
    ]
    for a in agents_data:
        agents_html += f"""
    <div class="sc-agent">
      <div class="sc-agent-icon">{a['icon']}</div>
      <div class="sc-agent-name">{a['name']}</div>
      <div class="sc-agent-file">{a['file']}</div>
      <div class="sc-agent-desc">{a['desc']}</div>
    </div>"""

    steps_html = ""
    for i, s in enumerate(SCRAPER_HOW_IT_WORKS):
        steps_html += f"""
    <div class="sc-step" style="animation-delay: {0.08 * i}s">
      <div class="sc-step-num">{s['step']}</div>
      <div class="sc-step-title">{s['title']}</div>
      <div class="sc-step-desc">{s['desc']}</div>
    </div>"""

    pricing_html = ""
    for t in SCRAPER_TIERS_DISPLAY:
        highlight_class = " highlight" if t["highlight"] else ""
        btn_class = "" if t["highlight"] else " outline"
        features_list = "".join(f"<li>{f}</li>" for f in t["features"])
        pricing_html += f"""
    <div class="sc-card{highlight_class}">
      <div class="sc-card-tier">{t['tier']}</div>
      <div class="sc-card-price">${t['price']}<span>{t['period']}</span></div>
      <div class="sc-card-desc">{t['desc']}</div>
      <ul class="sc-card-features">{features_list}</ul>
      <a class="sc-card-btn{btn_class}" href="mailto:ops@empire-ai.co.uk?subject=Elite%20Scraper%20{t['tier']}%20Inquiry">{t['cta']}</a>
    </div>"""

    verticals_html = ""
    for v in SCRAPER_VERTICALS:
        verticals_html += f"""
    <div class="sc-vertical">
      <div class="sc-vertical-name">{v['name']}</div>
      <div class="sc-vertical-desc">{v['desc']}</div>
      <div class="sc-vertical-meta">Agents: {v['agents']}</div>
    </div>"""

    faq_rows = ""
    for i, faq in enumerate(SCRAPER_FAQ):
        faq_rows += f"""
    <div class="sc-faq-item">
      <button class="sc-faq-q" onclick="toggleScFaq(this)" type="button" id="sc-faq-trigger-{i}" aria-controls="sc-faq-answer-{i}" aria-expanded="false">
        <span>{faq['q']}</span>
        <svg class="sc-faq-chevron" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7l5 5 5-5"/></svg>
      </button>
      <div class="sc-faq-a" id="sc-faq-answer-{i}" role="region" aria-labelledby="sc-faq-trigger-{i}" aria-hidden="true">
        {faq['a']}
      </div>
    </div>"""

    head = empire_head(title="Elite Scraper v2 · Predictive Revenue Fleet · Empire AI", extra=extra_css)

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="sc-wrap">

  <div class="sc-hero">
    <div class="sc-eyebrow">Empire AI Product</div>
    <h1 class="sc-title">Elite Scraper <em>v2</em><br>Predictive Revenue Fleet</h1>
    <p class="sc-sub">
      Three AI-powered scraper agents working together — Camofox stealth browser,
      YouTube intelligence, and autonomous Prospector. 36+ lanes across 6 niches.
    </p>
    <div class="sc-cta-row">
      <a class="e-btn" href="mailto:ops@empire-ai.co.uk?subject=Elite%20Scraper%20Inquiry">Get Started</a>
      <a class="e-btn" href="/pricing" style="background:transparent;color:var(--signal-teal);border:1px solid var(--signal-teal);">View Pricing</a>
    </div>
    <div class="sc-stats">
      <div class="sc-stat">
        <div class="sc-stat-num">6</div>
        <div class="sc-stat-label">Niches</div>
      </div>
      <div class="sc-stat">
        <div class="sc-stat-num">36+</div>
        <div class="sc-stat-label">Scrape Lanes</div>
      </div>
      <div class="sc-stat">
        <div class="sc-stat-num">3</div>
        <div class="sc-stat-label">Scraper Agents</div>
      </div>
      <div class="sc-stat">
        <div class="sc-stat-num">24/7</div>
        <div class="sc-stat-label">Fleet Pipeline</div>
      </div>
    </div>
  </div>

  <div class="sc-section">
    <div class="sc-section-h">
      <span class="sc-section-num">01</span>
      <span class="sc-section-title">The Scraper Fleet</span>
    </div>
    <div class="sc-agents">{agents_html}</div>
  </div>

  <div class="sc-section">
    <div class="sc-section-h">
      <span class="sc-section-num">02</span>
      <span class="sc-section-title">Key Features</span>
    </div>
    <div class="sc-features">{features_html}</div>
  </div>

  <div class="sc-section">
    <div class="sc-section-h">
      <span class="sc-section-num">03</span>
      <span class="sc-section-title">How It Works</span>
    </div>
    <div class="sc-steps">{steps_html}</div>
  </div>

  <div class="sc-section">
    <div class="sc-section-h">
      <span class="sc-section-num">04</span>
      <span class="sc-section-title">Available Niches</span>
    </div>
    <div class="sc-verticals">{verticals_html}</div>
  </div>

  <div class="sc-section">
    <div class="sc-section-h">
      <span class="sc-section-num">05</span>
      <span class="sc-section-title">Pricing</span>
    </div>
    <div class="sc-pricing">{pricing_html}</div>
  </div>

  <div class="sc-section">
    <div class="sc-section-h">
      <span class="sc-section-num">06</span>
      <span class="sc-section-title">FAQ</span>
    </div>
    <div class="sc-faq-list">{faq_rows}</div>
  </div>

  <div class="sc-foot">
    <a href="/">Empire AI</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/pricing">Pricing</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/products/elite-scraper">Elite Scraper v2</a>
    <br>
    <span style="letter-spacing:0.12em;color:var(--empire-shadow);margin-top:8px;display:block;">
      Predictive Revenue Fleet · Camofox · YouTube · Prospector
    </span>
  </div>

</div>

<script>
(function() {{
  window.toggleScFaq = function(btn) {{
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
