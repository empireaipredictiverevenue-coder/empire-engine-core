"""
Empire AI - Public /demo page.

A scrollable walkthrough of the funnel. NOT a video, NOT an
animation. Static HTML + CSS, no JS dependencies. ~30s to read.
The /contractors landing page's "Watch the 2-min demo" button
points here.
"""
from fastapi.responses import HTMLResponse


def demo_page() -> str:
    """Render the public /demo walkthrough."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0A1A2F">
<title>Empire AI \u00b7 How the funnel works</title>
<style>
  :root { --bg: #0A1A2F; --panel: #0F1E2F; --text: #E8EEF6;
          --muted: #94A3B8; --accent: #4FD1C5; --border: rgba(232,238,246,0.10); }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         line-height: 1.6; }
  .wrap { max-width: 720px; margin: 0 auto; padding: 48px 24px 80px; }
  .brand { font-weight: 700; letter-spacing: 0.04em; font-size: 14px;
           color: var(--accent); margin-bottom: 32px; }
  .hero h1 { font-size: 36px; line-height: 1.15; font-weight: 800;
             margin: 0 0 16px; color: #FFFFFF; }
  .hero p.lede { font-size: 18px; color: var(--muted); margin: 0 0 40px; }
  .step { background: var(--panel); border: 1px solid var(--border);
          border-radius: 12px; padding: 28px; margin: 24px 0; }
  .step .num { display: inline-block; width: 36px; height: 36px;
               line-height: 36px; text-align: center; border-radius: 50%;
               background: rgba(79,209,197,0.16); color: var(--accent);
               font-weight: 700; margin-bottom: 16px; }
  .step h2 { font-size: 20px; margin: 0 0 12px; color: #FFFFFF; }
  .step p  { margin: 0 0 12px; color: #B8C5D6; font-size: 15px; }
  .step .example { background: rgba(0,0,0,0.25); border-radius: 8px;
                  padding: 14px 18px; margin-top: 14px;
                  font-family: ui-monospace, "SF Mono", Menlo, monospace;
                  font-size: 13px; color: #B8C5D6; line-height: 1.5; }
  .step .example .you  { color: var(--accent); font-weight: 600; }
  .step .example .them { color: #E8EEF6; }
  .cta { display: inline-block; margin-top: 40px; padding: 14px 28px;
         background: linear-gradient(135deg, #4FD1C5 0%, #38B2AC 100%);
         color: #0A1A2F; border-radius: 8px; font-weight: 700;
         text-decoration: none; font-size: 15px; }
  .footer { text-align: center; padding: 40px 0 20px; font-size: 12px;
            color: var(--muted); }
  .arrow { text-align: center; color: var(--muted); margin: 4px 0;
           font-size: 18px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">EMPIRE <span style="color: #4FD1C5">AI</span></div>

  <div class="hero">
    <h1>How the funnel works.</h1>
    <p class="lede">A 30-second scroll through what happens when a storm hits a commercial property. No video, no signup. Just the flow.</p>
  </div>

  <div class="step">
    <div class="num">1</div>
    <h2>The storm hits.</h2>
    <p>Our radar catches a National Weather Service severe-weather alert in your area. Within minutes, we cross-reference the affected zone against a property records database and identify commercial properties likely to have roof or structural damage.</p>
    <p>What you don't see: a background process matching 1,500+ radar signals a day against 200,000+ property records to find the ones that matter.</p>
  </div>

  <div class="arrow">&#8595;</div>

  <div class="step">
    <div class="num">2</div>
    <h2>We text the property owner.</h2>
    <p>The owner of an affected commercial property gets a text from us. Not a call \u2014 a text. Three touches over a few days, each one a free no-cost offer to assess the damage.</p>
    <div class="example">
      <span class="them">Empire AI: Severe weather flagged at your facility (1500 Main St, Fort Worth). We can dispatch 1 vetted contractor to your area this week. Reply YES for a free assessment. Reply STOP to opt out.</span>
    </div>
    <p>Property owner replies YES \u2014 or doesn't. If they don't, we stop. TCPA-clean every step.</p>
  </div>

  <div class="arrow">&#8595;</div>

  <div class="step">
    <div class="num">3</div>
    <h2>You get the dispatch.</h2>
    <p>If the property owner says yes, the lead goes to a vetted contractor in our network. You get the name, the address, the property value, the damage severity. You show up, you inspect, you close.</p>
    <p>You only pay when the insurance claim settles. 3% referral fee, first 2 closed deals on us. No exclusivity, no contract, no monthly minimum.</p>
  </div>

  <div class="arrow">&#8595;</div>

  <div class="step">
    <div class="num">4</div>
    <h2>The settlement happens. We get paid.</h2>
    <p>You do the work. The property owner files the claim. The insurance pays out. We get 3% of the gross settlement, paid within 30 days of fund. Your first 2 closed deals are 100% complimentary \u2014 no fee, ever.</p>
  </div>

  <a class="cta" href="/contractors">Self-onboard (90 seconds)</a>
  <div class="footer">empire-ai.co.uk \u00b7 \u00a9 2026</div>
</div>
</body>
</html>"""
