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


def support_page() -> str:
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
      display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
    }
    @media (max-width: 720px) { .sp-faq { grid-template-columns: 1fr; } }
    .sp-faq-item {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(232,238,246,0.08);
      border-radius: 10px; padding: 20px;
    }
    .sp-faq-item h3 {
      font-size: 14px; margin: 0 0 6px; color: #4FD1C5; font-weight: 600;
    }
    .sp-faq-item p {
      font-size: 14px; margin: 0; color: #B8C5D6; line-height: 1.55;
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
        <div class="sp-faq-item">
          <h3>What is Empire AI?</h3>
          <p>Empire AI is an autonomous revenue engine that detects storm-affected commercial properties, qualifies them via SMS, and delivers pre-vetted leads to licensed contractors. We charge a 3% referral fee only on settled insurance claims.</p>
        </div>
        <div class="sp-faq-item">
          <h3>How does the 3% fee work?</h3>
          <p>We charge 3% of the gross settlement amount on insurance claims that actually pay out. If the property owner doesn't file a claim, or the claim is denied, you owe nothing. Your first 2 closed deals are 100% complimentary.</p>
        </div>
        <div class="sp-faq-item">
          <h3>What service areas do you cover?</h3>
          <p>Currently DFW, Houston, San Antonio, Austin, and expanding. Each lane targets specific metros based on storm activity and property density. We add new metros as the network grows.</p>
        </div>
        <div class="sp-faq-item">
          <h3>How do contractors get started?</h3>
          <p>Visit the <a href="/contractors" style="color:#4FD1C5">contractors page</a> and complete the self-onboard form. It takes about 90 seconds — no call required. We'll text you a welcome message within 5 minutes.</p>
        </div>
        <div class="sp-faq-item">
          <h3>Is there a contract or minimum?</h3>
          <p>No. There's no contract, no exclusivity clause, and no monthly minimum. You can opt out any time by replying STOP to any message. The 3% fee only triggers on claims that actually settle.</p>
        </div>
        <div class="sp-faq-item">
          <h3>I'm a property owner — how does this affect me?</h3>
          <p>If you own commercial property in an area affected by a severe storm, we may text you with a free damage assessment offer. There's no obligation, and you can reply STOP any time to opt out of future messages.</p>
        </div>
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
      </div>
    </section>

    <footer class="sp-footer">
      <a href="/">empire-ai.co.uk</a> · © 2026 · <a href="mailto:support@empire-ai.co.uk">support@empire-ai.co.uk</a>
    </footer>
  </div>

  <script src="/static/customer-service/chat.js" defer></script>
</body>
</html>"""
