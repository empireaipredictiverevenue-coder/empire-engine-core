"""
EMPIRE V49 · MEETILY PRODUCT PAGE
===================================
Dedicated landing page at /products/meetily explaining the privacy-first
AI meeting assistant and letting clients choose a tier.

Wire-up in hub.py:
    from empire_meetily_page import meetily_page

    @app.get("/products/meetily", response_class=HTMLResponse)
    async def meetily_product_page():
        return HTMLResponse(meetily_page())
"""

from empire_tokens import empire_head

MEETILY_FEATURES = [
    {
        "icon": "🔒",
        "title": "100% Private & Local",
        "desc": "All transcription runs locally on your machine using Whisper. No audio, transcripts, or metadata ever leave your network.",
    },
    {
        "icon": "🤖",
        "title": "Multi-LLM Support",
        "desc": "Choose your AI engine — Ollama for fully local, or Claude, Groq, and OpenRouter for cloud-powered summaries.",
    },
    {
        "icon": "📝",
        "title": "Smart Summaries",
        "desc": "Get AI-generated meeting summaries, action items, decisions, and key takeaways — customized to your workflow.",
    },
    {
        "icon": "🎤",
        "title": "Speaker Diarization",
        "desc": "Know who said what. Pro+ tiers identify and label speakers across the entire meeting transcript.",
    },
    {
        "icon": "📤",
        "title": "Advanced Export",
        "desc": "Export transcripts and summaries as PDF, DOCX, SRT, or plain text. Integrate with your existing document pipeline.",
    },
    {
        "icon": "🖥️",
        "title": "Cross-Platform",
        "desc": "Runs on macOS, Windows, and Linux. Enterprise tier includes dedicated server deployment with white-label branding.",
    },
]

MEETILY_TIERS_DISPLAY = [
    {
        "tier": "Starter",
        "price": 99,
        "period": "/month",
        "desc": "Single-user AI meeting assistant for personal use.",
        "features": [
            "Local transcription (Whisper)",
            "AI-powered summaries",
            "Single user license",
            "Ollama support",
            "Basic meeting search",
            "Email support",
        ],
        "cta": "Get Started",
        "highlight": False,
    },
    {
        "tier": "Pro",
        "price": 299,
        "period": "/month",
        "desc": "Multi-user with advanced features for teams.",
        "features": [
            "Everything in Starter",
            "Up to 5 users",
            "Speaker diarization",
            "Custom summary workflows",
            "Advanced export (PDF, DOCX, SRT)",
            "Claude/Groq/OpenRouter support",
            "Priority email support",
        ],
        "cta": "Get Started",
        "highlight": True,
    },
    {
        "tier": "Enterprise",
        "price": 999,
        "period": "/month",
        "desc": "Full enterprise deployment with dedicated infrastructure.",
        "features": [
            "Everything in Pro",
            "Unlimited users",
            "Dedicated Linux server",
            "White-label branding",
            "Custom integrations (Slack, Teams)",
            "On-premise or VPC hosting",
            "99.9% SLA",
            "Dedicated support engineer",
            "Backup & disaster recovery",
        ],
        "cta": "Contact Sales",
        "highlight": False,
    },
]

MEETILY_HOW_IT_WORKS = [
    {
        "step": "01",
        "title": "Install",
        "desc": "Download and install Meetily on your device or server. Enterprise clients get a fully managed deployment.",
    },
    {
        "step": "02",
        "title": "Configure",
        "desc": "Connect your preferred LLM (Ollama, Claude, Groq) and customize summary templates to your workflow.",
    },
    {
        "step": "03",
        "title": "Record",
        "desc": "Start or join meetings — Meetily captures audio, transcribes in real-time, and processes everything locally.",
    },
    {
        "step": "04",
        "title": "Review & Share",
        "desc": "Get AI-generated summaries, action items, and searchable transcripts. Export, share, or archive with one click.",
    },
]

MEETILY_FAQ = [
    {
        "q": "Is my meeting data stored on external servers?",
        "a": "No. All transcription runs locally via Whisper. No audio, transcripts, or any meeting data ever leaves your machine. For cloud LLM integrations (Claude, Groq), only anonymized text summaries are sent — no raw audio or identifying metadata.",
    },
    {
        "q": "Which LLMs can I use with Meetily?",
        "a": "Meetily supports Ollama (fully local, free), Claude (Anthropic), Groq, and OpenRouter. You can switch between them at any time. For maximum privacy, use Ollama — everything stays on your machine.",
    },
    {
        "q": "Can I try Meetily before purchasing?",
        "a": "Yes! Meetily is open-source (MIT license) on GitHub. You can download, install, and evaluate it for free. A paid subscription unlocks multi-user features, priority support, and enterprise deployment options.",
    },
    {
        "q": "What platforms does Meetily support?",
        "a": "Meetily runs on macOS, Windows, and Linux. The desktop app is built with Tauri 2.x for native performance. Enterprise deployments are on dedicated Linux servers managed by Empire AI.",
    },
    {
        "q": "How does Enterprise licensing work?",
        "a": "Enterprise tier includes a dedicated Linux server, white-label branding, custom integrations (Slack, Teams, etc.), 99.9% SLA, a dedicated support engineer, and backup/disaster recovery. We handle deployment, updates, and monitoring.",
    },
    {
        "q": "Can I customize summary formats?",
        "a": "Yes. Pro and Enterprise tiers support custom summary workflows. Define your own templates, output formats, and action-item extraction rules to match your team's specific needs.",
    },
]


def meetily_page() -> str:
    """Return the full /products/meetily landing page HTML."""

    extra_css = """
    .mt-wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 32px 80px;
    }
    .mt-hero {
      text-align: center;
      margin-bottom: 64px;
    }
    .mt-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 14px;
    }
    .mt-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 52px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.08;
      margin-bottom: 18px;
    }
    .mt-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .mt-sub {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--empire-mist);
      letter-spacing: 0.14em;
      max-width: 640px;
      margin: 0 auto;
      line-height: 1.8;
    }
    .mt-cta-row {
      display: flex;
      justify-content: center;
      gap: 16px;
      margin-top: 32px;
      flex-wrap: wrap;
    }
    .mt-section {
      margin-bottom: 72px;
    }
    .mt-section-h {
      display: flex;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 28px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .mt-section-num {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--signal-teal);
      letter-spacing: 0.12em;
    }
    .mt-section-title {
      font-weight: 500;
      font-size: 22px;
      letter-spacing: -0.02em;
      color: var(--empire-white);
    }

    /* Features grid */
    .mt-features {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }
    .mt-feature {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 28px 22px;
      transition: all 0.25s var(--ease-snap);
    }
    .mt-feature:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
    }
    .mt-feature-icon {
      font-size: 28px;
      margin-bottom: 14px;
    }
    .mt-feature-title {
      font-weight: 600;
      font-size: 15px;
      color: var(--empire-white);
      margin-bottom: 10px;
    }
    .mt-feature-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.7;
    }

    /* Steps */
    .mt-steps {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }
    .mt-step {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 28px 22px;
      transition: all 0.25s var(--ease-snap);
    }
    .mt-step:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
    }
    .mt-step-num {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--signal-teal);
      margin-bottom: 12px;
    }
    .mt-step-title {
      font-weight: 600;
      font-size: 15px;
      color: var(--empire-white);
      margin-bottom: 10px;
    }
    .mt-step-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.7;
    }

    /* Pricing */
    .mt-pricing {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }
    .mt-card {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 32px 24px;
      display: flex;
      flex-direction: column;
      transition: all 0.3s var(--ease-snap);
    }
    .mt-card:hover {
      transform: translateY(-3px);
    }
    .mt-card.highlight {
      border-color: var(--signal-teal);
      position: relative;
    }
    .mt-card.highlight::before {
      content: "Most Popular";
      position: absolute;
      top: -12px;
      left: 50%;
      transform: translateX(-50%);
      background: var(--signal-teal);
      color: #0A1A2F;
      font-family: var(--font-mono);
      font-size: 9px;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      padding: 4px 14px;
      font-weight: 600;
    }
    .mt-card-tier {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.24em;
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .mt-card-price {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 40px;
      color: var(--empire-white);
      line-height: 1;
      margin-bottom: 4px;
    }
    .mt-card-price span {
      font-size: 14px;
      color: var(--empire-fog);
      font-weight: 400;
    }
    .mt-card-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.6;
      margin-bottom: 20px;
      margin-top: 8px;
      min-height: 40px;
    }
    .mt-card-features {
      list-style: none;
      padding: 0;
      margin: 0 0 24px;
      flex: 1;
    }
    .mt-card-features li {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      padding: 8px 0;
      border-bottom: 1px solid var(--empire-divider);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .mt-card-features li:last-child {
      border-bottom: none;
    }
    .mt-card-features li::before {
      content: "✓";
      color: var(--signal-teal);
      font-weight: 700;
    }
    .mt-card-btn {
      display: inline-block;
      padding: 12px 24px;
      font-size: 13px;
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
    .mt-card-btn:hover { opacity: 0.85; }
    .mt-card-btn.outline {
      background: transparent;
      color: var(--signal-teal);
      border: 1px solid var(--signal-teal);
    }
    .mt-card-btn.outline:hover {
      background: var(--signal-teal);
      color: #0A1A2F;
    }

    .mt-faq-list {
      max-width: 720px;
    }
    .mt-faq-item {
      border-bottom: 1px solid var(--empire-divider);
      padding: 18px 0;
    }
    .mt-faq-item:first-child { padding-top: 0; }
    .mt-faq-q {
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
    .mt-faq-q:hover { color: var(--signal-teal); }
    .mt-faq-q[aria-expanded="true"] { color: var(--signal-teal); }
    .mt-faq-chevron {
      flex-shrink: 0;
      margin-left: 12px;
      width: 18px;
      height: 18px;
      transition: transform 0.25s ease;
      color: var(--empire-fog);
      pointer-events: none;
    }
    .mt-faq-q[aria-expanded="true"] .mt-faq-chevron {
      transform: rotate(180deg);
      color: var(--signal-teal);
    }
    .mt-faq-a {
      font-size: 13px;
      color: var(--empire-mist);
      line-height: 1.7;
      overflow: hidden;
      max-height: 0;
      opacity: 0;
      transition: max-height 0.3s ease, opacity 0.25s ease, padding 0.15s ease;
    }
    .mt-faq-a.open {
      max-height: 300px;
      opacity: 1;
    }

    /* Open source badge */
    .mt-oss {
      text-align: center;
      padding: 32px;
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      margin-bottom: 72px;
    }
    .mt-oss-icon { font-size: 32px; margin-bottom: 12px; }
    .mt-oss-title {
      font-weight: 600;
      font-size: 16px;
      color: var(--empire-white);
      margin-bottom: 8px;
    }
    .mt-oss-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.7;
      max-width: 600px;
      margin: 0 auto 16px;
    }

    .mt-foot {
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
    .mt-foot a {
      color: var(--empire-mist);
      text-decoration: none;
    }
    .mt-foot a:hover { color: var(--signal-teal); }

    @media (max-width: 900px) {
      .mt-title { font-size: 36px; }
      .mt-features { grid-template-columns: repeat(2, 1fr); }
      .mt-steps { grid-template-columns: repeat(2, 1fr); }
      .mt-pricing { grid-template-columns: 1fr; max-width: 400px; margin: 0 auto; }
    }
    @media (max-width: 540px) {
      .mt-features { grid-template-columns: 1fr; }
      .mt-steps { grid-template-columns: 1fr; }
    }
    """

    features_html = ""
    for i, f in enumerate(MEETILY_FEATURES):
        features_html += f"""
    <div class="mt-feature" style="animation-delay: {0.04 * i}s">
      <div class="mt-feature-icon">{f['icon']}</div>
      <div class="mt-feature-title">{f['title']}</div>
      <div class="mt-feature-desc">{f['desc']}</div>
    </div>"""

    steps_html = ""
    for i, s in enumerate(MEETILY_HOW_IT_WORKS):
        steps_html += f"""
    <div class="mt-step" style="animation-delay: {0.08 * i}s">
      <div class="mt-step-num">{s['step']}</div>
      <div class="mt-step-title">{s['title']}</div>
      <div class="mt-step-desc">{s['desc']}</div>
    </div>"""

    pricing_html = ""
    for t in MEETILY_TIERS_DISPLAY:
        highlight_class = " highlight" if t["highlight"] else ""
        btn_class = "" if t["highlight"] else " outline"
        features_list = "".join(f"<li>{f}</li>" for f in t["features"])
        pricing_html += f"""
    <div class="mt-card{highlight_class}">
      <div class="mt-card-tier">{t['tier']}</div>
      <div class="mt-card-price">${t['price']}<span>{t['period']}</span></div>
      <div class="mt-card-desc">{t['desc']}</div>
      <ul class="mt-card-features">{features_list}</ul>
      <a class="mt-card-btn{btn_class}" href="mailto:ops@empire-ai.co.uk?subject=Meetily%20{t['tier']}%20Inquiry">{t['cta']}</a>
    </div>"""

    faq_rows = ""
    for i, faq in enumerate(MEETILY_FAQ):
        faq_rows += f"""
    <div class="mt-faq-item">
      <button class="mt-faq-q" onclick="toggleMtFaq(this)" type="button" id="mt-faq-trigger-{i}" aria-controls="mt-faq-answer-{i}" aria-expanded="false">
        <span>{faq['q']}</span>
        <svg class="mt-faq-chevron" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7l5 5 5-5"/></svg>
      </button>
      <div class="mt-faq-a" id="mt-faq-answer-{i}" role="region" aria-labelledby="mt-faq-trigger-{i}" aria-hidden="true">
        {faq['a']}
      </div>
    </div>"""

    head = empire_head(title="Meetily · AI Meeting Assistant · Empire AI", extra=extra_css)

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="mt-wrap">

  <div class="mt-hero">
    <div class="mt-eyebrow">Empire AI Product</div>
    <h1 class="mt-title">Meetily: <em>Privacy-First</em><br>AI Meeting Assistant</h1>
    <p class="mt-sub">
      Capture, transcribe, and summarize meetings entirely on your own infrastructure.
      Zero cloud dependencies for transcription — 100% private by design.
    </p>
    <div class="mt-cta-row">
      <a class="e-btn" href="https://github.com/Zackriya-Solutions/meetily" target="_blank" rel="noopener">View on GitHub</a>
      <a class="e-btn" href="mailto:ops@empire-ai.co.uk?subject=Meetily%20Enterprise%20Inquiry" style="background:transparent;color:var(--signal-teal);border:1px solid var(--signal-teal);">Contact Sales</a>
    </div>
  </div>

  <div class="mt-section">
    <div class="mt-section-h">
      <span class="mt-section-num">01</span>
      <span class="mt-section-title">Key Features</span>
    </div>
    <div class="mt-features">{features_html}</div>
  </div>

  <div class="mt-section">
    <div class="mt-section-h">
      <span class="mt-section-num">02</span>
      <span class="mt-section-title">How It Works</span>
    </div>
    <div class="mt-steps">{steps_html}</div>
  </div>

  <div class="mt-oss">
    <div class="mt-oss-icon">📖</div>
    <div class="mt-oss-title">Open Source (MIT License)</div>
    <div class="mt-oss-desc">
      Meetily is built on open-source technology by Zackriya Solutions.
      Enterprise AI manages deployments, updates, and infrastructure.
    </div>
    <a class="e-btn" href="https://github.com/Zackriya-Solutions/meetily" target="_blank" rel="noopener" style="background:transparent;color:var(--signal-teal);border:1px solid var(--signal-teal);">Star on GitHub</a>
  </div>

  <div class="mt-section">
    <div class="mt-section-h">
      <span class="mt-section-num">03</span>
      <span class="mt-section-title">Pricing</span>
    </div>
    <div class="mt-pricing">{pricing_html}</div>
  </div>

  <div class="mt-section">
    <div class="mt-section-h">
      <span class="mt-section-num">04</span>
      <span class="mt-section-title">FAQ</span>
    </div>
    <div class="mt-faq-list">{faq_rows}</div>
  </div>

  <div class="mt-foot">
    <a href="/">Empire AI</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/pricing">Pricing</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/products/meetily">Meetily</a>
    <br>
    <span style="letter-spacing:0.12em;color:var(--empire-shadow);margin-top:8px;display:block;">
      Privacy-first AI meeting assistant · Local transcription · Open source
    </span>
  </div>

</div>

<script>
(function() {{
  window.toggleMtFaq = function(btn) {{
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
