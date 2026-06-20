"""
EMPIRE V49 · SUPPORT PAGE
=========================
Public support page at /support. FAQ + contact info + customer-service chat widget.
Like /contractors but for general customer support.

Wire-up in hub.py:
    from empire_support import support_page
    @app.get("/support", response_class=HTMLResponse)
    async def support():
        return HTMLResponse(support_page())
"""

from empire_tokens import empire_head


_FAQ_ITEMS = [
    ("What is Empire AI?",
     "Empire AI is an autonomous revenue engine that detects storm-affected commercial "
     "properties, qualifies them via SMS, and delivers pre-vetted leads to licensed "
     "contractors. We charge a 3% referral fee only on settled insurance claims."),
    ("How does the 3% fee work?",
     "We charge 3% of the gross settlement amount on insurance claims that actually "
     "pay out. If the property owner doesn't file a claim, or the claim is denied, "
     "you owe nothing. Your first 2 closed deals are 100% complimentary."),
    ("What service areas do you cover?",
     "Currently DFW, Houston, San Antonio, Austin, and expanding. Each lane targets "
     "specific metros based on storm activity and property density. We add new "
     "metros as the network grows."),
    ("How do contractors get started?",
     'Visit the <a href="/contractors" style="color:#4FD1C5">contractors page</a> '
     "and complete the self-onboard form. It takes about 90 seconds — no call "
     "required. We'll text you a welcome message within 5 minutes."),
    ("Is there a contract or minimum?",
     "No. There's no contract, no exclusivity clause, and no monthly minimum. You "
     "can opt out any time by replying STOP to any message. The 3% fee only triggers "
     "on claims that actually settle."),
    ("I'm a property owner — how does this affect me?",
     "If you own commercial property in an area affected by a severe storm, we may "
     "text you with a free damage assessment offer. There's no obligation, and you "
     "can reply STOP any time to opt out of future messages."),
    ("What suite products do you offer?",
     "Empire AI offers 15 suite products including Inbound Router (call routing &amp; "
     "qualification), Data Vault (compliance storage), Buyer Spy AI (call transcript "
     "analysis), Omni Bridge (STT + social distribution), Agent Orchestrator (autonomous "
     "agents), B2B Pro (property intel), LeadScore AI (SI-powered scoring), Compliant "
     "(TCPA/DNC), Strike Campaigns (multi-touch SMS/email), Forecast (predictive "
     "revenue), Market Eye (competitor intel), Content Pulse (auto SEO), Contractor "
     "Exchange (marketplace), Sales Funnel (trial &amp; conversion), and Command Center "
     "Pro. Most products start with a free trial."),
    ("How much does Empire AI cost?",
     'Contractors pay nothing upfront — just a 3% referral fee on settled insurance '
     'claims, and the first 2 deals are free. Suite product pricing starts at '
     '$29/month for core products and scales with usage. See the '
     '<a href="/pricing" style="color:#4FD1C5">pricing page</a> for full details. '
     "There are no contracts, no setup fees, and you can cancel anytime."),
    ("What are the technical requirements?",
     "For contractors: a smartphone capable of receiving SMS and email, with a web "
     "browser for the self-onboard portal. No app download required. For suite "
     "products: a modern browser (Chrome, Firefox, Safari, Edge) and an internet "
     "connection. The platform works on desktop and mobile. Our API is RESTful with "
     "JSON payloads; API keys are issued on account creation."),
]


def _build_faq_html() -> str:
    """Build the FAQ collapse/expand HTML with ARIA attributes."""
    rows = []
    for i, (q, a) in enumerate(_FAQ_ITEMS):
        rows.append(
            f'''        <div class="sp-faq-item">
          <button class="sp-faq-trigger" onclick="toggleFaq(this)" type="button" id="faq-trigger-{i}" aria-controls="faq-answer-{i}" aria-expanded="false">
            <h3>{q}</h3>
            <svg class="sp-faq-chevron" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7l5 5 5-5"/></svg>
          </button>
          <div class="sp-faq-answer" id="faq-answer-{i}" role="region" aria-labelledby="faq-trigger-{i}">
            <p>{a}</p>
          </div>
        </div>'''
        )
    return '\n'.join(rows)


def support_page() -> str:
    _faq_html = _build_faq_html()
    css = """
    .sp-body {
      min-height: 100vh;
      background: linear-gradient(180deg, #0A1A2F 0%, #08121F 100%);
      color: #E8EEF6;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .sp-wrap {
      max-width: 880px;
      margin: 0 auto;
      padding: 32px 20px 80px;
    }
    .sp-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 0 28px;
      border-bottom: 1px solid rgba(232,238,246,0.08);
    }
    .sp-brand { font-weight: 700; letter-spacing: 0.04em; font-size: 14px; }
    .sp-brand span { color: #4FD1C5; }
    .sp-toplink { color: #94A3B8; font-size: 12px; text-decoration: none; }
    .sp-toplink:hover { color: #4FD1C5; }

    .sp-hero {
      padding: 48px 0 24px;
    }
    .sp-hero h1 {
      font-size: 36px; line-height: 1.15; font-weight: 800;
      margin: 0 0 16px; color: #FFFFFF;
    }
    .sp-hero h1 em { font-style: normal; color: #4FD1C5; }
    .sp-hero-sub {
      font-size: 16px; line-height: 1.55; color: #B8C5D6;
      max-width: 620px;
    }

    .sp-section {
      padding: 40px 0; border-top: 1px solid rgba(232,238,246,0.08);
    }
    .sp-section h2 {
      font-size: 22px; font-weight: 700; margin: 0 0 24px;
      letter-spacing: -0.01em;
    }

    .sp-faq {
      display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
    }
    @media (max-width: 720px) { .sp-faq { grid-template-columns: 1fr; } }
    .sp-faq-item {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(232,238,246,0.08);
      border-radius: 10px;
      transition: border-color 0.2s, background 0.2s;
    }
    .sp-faq-item:hover { border-color: rgba(79,209,197,0.25); }
    .sp-faq-item.expanded {
      border-color: rgba(79,209,197,0.35);
      background: rgba(79,209,197,0.04);
    }
    .sp-faq-trigger {
      display: flex; align-items: center; justify-content: space-between;
      width: 100%; padding: 18px 20px;
      cursor: pointer; border: none; background: none;
      font: inherit; text-align: left; color: inherit;
      -webkit-appearance: none; appearance: none;
      user-select: none;
    }
    .sp-faq-trigger h3 {
      font-size: 14px; margin: 0; color: #4FD1C5; font-weight: 600;
      pointer-events: none;
    }
    .sp-faq-chevron {
      flex-shrink: 0; margin-left: 12px;
      width: 18px; height: 18px;
      transition: transform 0.25s ease;
      color: #64748B;
      pointer-events: none;
    }
    .sp-faq-item.expanded .sp-faq-chevron {
      transform: rotate(180deg);
      color: #4FD1C5;
    }
    .sp-faq-answer {
      overflow: hidden;
      max-height: 0;
      opacity: 0;
      transition: max-height 0.3s ease, opacity 0.25s ease, padding 0.3s ease;
      padding: 0 20px;
    }
    .sp-faq-item.expanded .sp-faq-answer {
      max-height: 300px;
      opacity: 1;
      padding: 0 20px 18px;
    }
    .sp-faq-answer p {
      font-size: 14px; margin: 0; color: #B8C5D6; line-height: 1.6;
    }

    .sp-contact-cards {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
    }
    @media (max-width: 720px) { .sp-contact-cards { grid-template-columns: 1fr; } }
    .sp-card {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(232,238,246,0.08);
      border-radius: 10px; padding: 20px; text-align: center;
    }
    .sp-card-icon { font-size: 28px; margin-bottom: 10px; }
    .sp-card h3 { font-size: 13px; margin: 0 0 4px; color: #FFFFFF; }
    .sp-card p { font-size: 13px; margin: 0; color: #94A3B8; }
    .sp-card a { color: #4FD1C5; text-decoration: none; }
    .sp-card a:hover { text-decoration: underline; }

    .sp-footer {
      text-align: center; padding: 40px 0 20px;
      font-size: 12px; color: #64748B;
    }
    .sp-footer a { color: #94A3B8; text-decoration: none; }
    .sp-footer a:hover { color: #4FD1C5; }
    """

    return f"""<!DOCTYPE html>
<html lang="en">
{empire_head(title="Empire AI · Support", extra=css)}
<body class="sp-body">
  <div class="sp-wrap">
    <header class="sp-header">
      <div class="sp-brand">EMPIRE <span>AI</span></div>
      <a class="sp-toplink" href="/">← home</a>
    </header>

    <section class="sp-hero">
      <h1>How can we <em>help</em> you?</h1>
      <p class="sp-hero-sub">
        Browse common questions below, or open the chat bubble at the bottom-right
        to ask Empire AI directly. All questions answered — no call required.
      </p>
    </section>

    <section class="sp-section">
      <h2>Common questions</h2>
      <div class="sp-faq">
{_faq_html}
      </div>
    </section>

    <section class="sp-section">
      <h2>Contact us directly</h2>
      <div class="sp-contact-cards">
        <div class="sp-card">
          <div class="sp-card-icon">📧</div>
          <h3>Email</h3>
          <p><a href="mailto:support@empire-ai.co.uk">support@empire-ai.co.uk</a></p>
        </div>
        <div class="sp-card">
          <div class="sp-card-icon">🏗️</div>
          <h3>Contractors</h3>
          <p><a href="mailto:contractors@empire-ai.co.uk">contractors@empire-ai.co.uk</a></p>
        </div>
        <div class="sp-card">
          <div class="sp-card-icon">💬</div>
          <h3>Live chat</h3>
          <p>Open the chat bubble below — powered by Empire AI</p>
        </div>
        <div class="sp-card">
          <div class="sp-card-icon">📡</div>
          <h3>Carriers</h3>
          <p><a href="/carrier/enroll">Webhook enrollment →</a></p>
        </div>
      </div>
    </section>

    <footer class="sp-footer">
      <a href="/">empire-ai.co.uk</a> · © 2026 · <a href="mailto:support@empire-ai.co.uk">support@empire-ai.co.uk</a>
    </footer>
  </div>

  <script>
  function toggleFaq(btn) {{
    var item = btn.closest('.sp-faq-item');
    if (!item) return;
    var answer = item.querySelector('.sp-faq-answer');
    if (!answer) return;
    var isExpanded = btn.getAttribute('aria-expanded') === 'true';
    // Close any other open items (accordion behavior)
    var siblings = item.parentElement.querySelectorAll('.sp-faq-item.expanded');
    for (var i = 0; i < siblings.length; i++) {{
      if (siblings[i] !== item) {{
        siblings[i].classList.remove('expanded');
        var otherBtn = siblings[i].querySelector('.sp-faq-trigger');
        if (otherBtn) otherBtn.setAttribute('aria-expanded', 'false');
      }}
    }}
    var open = !isExpanded;
    item.classList.toggle('expanded', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }}
  </script>
  <script src="/static/customer-service/chat.js" defer></script>
</body>
</html>"""
