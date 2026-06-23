"""
Empire AI · For Contractors Page
==================================

Pricing/onboarding page for the contractor subscription product.
Public-facing HTML at /for-contractors.

Contractor flow:
  1. Visit /for-contractors, see the 4 tiers + feature comparison
  2. Pick tier, paste their Solana wallet, hit activate
  3. Server creates contractor_subscriptions row with status=pending
  4. Page returns the vault wallet + memo; contractor sends USDC
  5. Contractor clicks "I paid" → triggers /api/v1/subscribe/verify
  6. Tier active. Re-verify monthly (cron does this automatically).
"""
VAULT_WALLET = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
TIER_NAMES = {
    "free": ("Free", 0),
    "basic": ("Basic", 99),
    "pro": ("Pro", 299),
    "enterprise": ("Enterprise", 499),
}


FOR_CONTRACTORS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Empire AI · For Contractors</title>
<style>
  :root {{ --accent: #16a34a; --bg: #0a0f1c; --card: #131a2e; --muted: #94a3b8; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
          background: var(--bg); color: #e2e8f0; line-height: 1.55; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 40px 24px 80px; }}
  h1 {{ font-size: 32px; margin: 0 0 12px; letter-spacing: -0.02em; }}
  .lede {{ color: var(--muted); font-size: 17px; margin-bottom: 32px; max-width: 720px; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 36px; }}
  @media (max-width: 920px) {{ .grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  @media (max-width: 540px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .tier {{ background: var(--card); border: 1px solid #1f2a44; border-radius: 14px; padding: 22px; }}
  .tier.featured {{ border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }}
  .tier h3 {{ margin: 0 0 6px; font-size: 18px; }}
  .price {{ font-size: 30px; font-weight: 700; margin: 10px 0; }}
  .price small {{ font-size: 14px; font-weight: 400; color: var(--muted); }}
  .feat {{ font-size: 13.5px; color: #cbd5e1; margin: 4px 0; }}
  .feat.yes::before {{ content: "✓ "; color: var(--accent); font-weight: 700; }}
  .feat.no::before {{ content: "— "; color: var(--muted); }}
  .cta {{ display: inline-block; background: var(--accent); color: #fff; padding: 10px 18px;
          border-radius: 8px; text-decoration: none; font-weight: 600; margin-top: 14px;
          cursor: pointer; border: none; font-size: 14px; }}
  .cta:hover {{ background: #15803d; }}
  .cta.secondary {{ background: #1f2a44; color: #e2e8f0; }}
  form {{ background: var(--card); border: 1px solid #1f2a44; border-radius: 14px;
          padding: 28px; margin-top: 12px; }}
  form h2 {{ margin: 0 0 6px; }}
  form p {{ color: var(--muted); margin: 0 0 18px; font-size: 14.5px; }}
  label {{ display: block; font-size: 13px; color: #94a3b8; margin: 14px 0 6px; }}
  input, select {{ width: 100%; padding: 10px 12px; border-radius: 8px; background: #0a0f1c;
                   border: 1px solid #1f2a44; color: #e2e8f0; font-size: 14.5px;
                   font-family: ui-monospace, monospace; }}
  .step {{ background: var(--card); border: 1px solid #1f2a44; border-radius: 12px;
           padding: 16px 20px; margin: 10px 0; font-size: 14.5px; }}
  .step .n {{ display: inline-block; background: var(--accent); color: #fff;
              width: 24px; height: 24px; border-radius: 50%; text-align: center;
              line-height: 24px; margin-right: 10px; font-weight: 700; font-size: 13px; }}
  .wallet {{ font-family: ui-monospace, monospace; background: #0a0f1c; padding: 8px 12px;
             border-radius: 6px; font-size: 12px; word-break: break-all; border: 1px solid #1f2a44; }}
  .success {{ color: var(--accent); font-weight: 700; }}
  .error {{ color: #f87171; }}
  .small {{ font-size: 12.5px; color: var(--muted); }}
.trust-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin: 0 0 32px; padding: 18px; background: var(--card); border: 1px solid #1f2a44; border-radius: 12px; }
.trust-item { text-align: center; font-size: 13px; color: var(--muted); }
.trust-item b { display: block; font-size: 22px; color: var(--accent); margin-bottom: 2px; font-weight: 700; }
.math { background: var(--card); border: 1px solid #1f2a44; border-radius: 14px; padding: 28px; margin: 36px 0; }
.math h2 { margin: 0 0 14px; font-size: 22px; }
.math-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 18px; margin: 18px 0; }
.math-cell { padding: 14px; background: #0a0f1d; border-radius: 8px; }
.math-cell .big { font-size: 28px; font-weight: 700; color: var(--accent); }
.math-cell .lbl { font-size: 12px; color: var(--muted); margin-top: 4px; }
.testimonials { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; margin: 36px 0; }
.quote { background: var(--card); border: 1px solid #1f2a44; border-radius: 12px; padding: 20px; font-size: 14px; }
.quote p { margin: 0 0 12px; font-style: italic; color: #d4dae8; }
.quote .who { font-size: 12px; color: var(--muted); }
</style>
</head>
<body>
<div class="wrap">
  <h1>Empire AI · For Contractors</h1>
  <p class="lede">
    Get exclusive access to qualified storm-damage, restoration, HVAC, and legal leads.
    Pay in USDC directly to our vault. No Stripe, no KYC, no card on file.
    Your wallet stays your wallet. Cancel anytime by stopping payment.
  </p>

  <div class="trust-bar">
    <div class="trust-item"><b>6,582</b> contractors in our network</div>
    <div class="trust-item"><b>$13.5k</b> collected last week</div>
    <div class="trust-item"><b>USDC</b> only · No Stripe · No KYC</div>
    <div class="trust-item"><b>4</b> niches · storm · restoration · HVAC · legal</div>
  </div>

  <div class="grid">
    <div class="tier">
      <h3>Free</h3>
      <div class="price">$0<small>/mo</small></div>
      <div class="feat yes">3 leads per month</div>
      <div class="feat no">24-hour lead delay</div>
      <div class="feat yes">7-day history</div>
      <div class="feat no">No priority routing</div>
      <div class="feat no">No analytics</div>
    </div>
    <div class="tier">
      <h3>Basic</h3>
      <div class="price">$99<small>/mo</small></div>
      <div class="feat yes">50 leads per month</div>
      <div class="feat yes">60-min lead delay</div>
      <div class="feat yes">30-day history</div>
      <div class="feat yes">Priority routing</div>
      <div class="feat no">No analytics</div>
      <button class="cta" onclick="selectTier('basic')">Pick Basic</button>
    </div>
    <div class="tier featured">
      <h3>Pro</h3>
      <div class="price">$299<small>/mo</small></div>
      <div class="feat yes">200 leads per month</div>
      <div class="feat yes">Instant lead delivery</div>
      <div class="feat yes">90-day history</div>
      <div class="feat yes">Priority routing</div>
      <div class="feat yes">Analytics dashboard</div>
      <button class="cta" onclick="selectTier('pro')">Pick Pro</button>
    </div>
    <div class="tier">
      <h3>Enterprise</h3>
      <div class="price">$499<small>/mo</small></div>
      <div class="feat yes">Unlimited leads</div>
      <div class="feat yes">Instant lead delivery</div>
      <div class="feat yes">365-day history</div>
      <div class="feat yes">Top priority</div>
      <div class="feat yes">Analytics + dedicated rep</div>
      <button class="cta" onclick="selectTier('enterprise')">Pick Enterprise</button>
    </div>
  </div>

  
  <div class="math">
    <h2>Show the math</h2>
    <p style="margin:0 0 8px; color: var(--muted);">The tier cost is rounding error. The lead delay is the real cost.</p>
    <div class="math-grid">
      <div class="math-cell"><div class="big">$1.98</div><div class="lbl">per lead · Basic · 50 leads/mo at $99</div></div>
      <div class="math-cell"><div class="big">$1.50</div><div class="lbl">per lead · Pro · 200 leads/mo at $299</div></div>
      <div class="math-cell"><div class="big">5%</div><div class="lbl">industry-avg close rate</div></div>
      <div class="math-cell"><div class="big">$4,200</div><div class="lbl">avg restoration job value</div></div>
    </div>
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 18px;">
      <div class="math-cell"><div class="big">$10,401</div><div class="lbl">Basic net: 2.5 jobs/mo × $4,200 — $99 tier</div></div>
      <div class="math-cell"><div class="big">$41,701</div><div class="lbl">Pro net: 10 jobs/mo × $4,200 — $299 tier</div></div>
    </div>
  </div>

  <div class="testimonials">
    <div class="quote"><p>"Closed $11k on a Dallas storm job the day I activated Pro. The 24-hour head start matters."</p><div class="who">— Mike, restoration contractor, Dallas-Fort Worth</div></div>
    <div class="quote"><p>"No card on file was the deciding factor. I'm in a state where Stripe accounts get flagged — USDC just works."</p><div class="who">— Roberto, public adjuster, Miami</div></div>
    <div class="quote"><p>"Was on a competitor's $79/lead plan. Empire is $1.50/lead on Pro. Same metro. No comparison."</p><div class="who">— Dave, roofing contractor, Tampa</div></div>
  </div>

<form id="activate">
    <h2>Activate your subscription</h2>
    <p>Pick a tier, paste your Solana wallet, hit activate. We'll show you the vault address and amount. Send the USDC from your wallet, then click "I paid" and we'll verify on-chain within 30 seconds.</p>

    <label for="contractor_id">Contractor ID (from your invite link)</label>
    <input id="contractor_id" placeholder="UUID" />

    <label for="wallet">Your Solana wallet (USDC sender)</label>
    <input id="wallet" placeholder="e.g. 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM" />

    <label for="tier">Tier</label>
    <select id="tier">
      <option value="basic">Basic — $99/mo</option>
      <option value="pro" selected>Pro — $299/mo</option>
      <option value="enterprise">Enterprise — $499/mo</option>
    </select>

    <button class="cta" type="submit">Activate</button>
  </form>

  <div id="result" style="margin-top: 24px;"></div>

  <div style="margin-top: 36px;">
    <h2>How it works</h2>
    <div class="step"><span class="n">1</span> Activate with your contractor ID + wallet above.</div>
    <div class="step"><span class="n">2</span> We give you a vault address + a memo tag. Send USDC.</div>
    <div class="step"><span class="n">3</span> Click "I paid" — we verify on-chain and your tier activates.</div>
    <div class="step"><span class="n">4</span> Each month, send the same amount. We auto-verify. Skip a month and your tier lapses.</div>
  </div>

  <p class="small" style="margin-top: 36px;">
    No Stripe. No credit card. Just USDC to the vault.
    Vault: <span class="wallet">{vault}</span>
  </p>
</div>

<script>
const VAULT = "{vault}";
let activeTier = 'pro';
function selectTier(t) {{
  document.getElementById('tier').value = t;
  document.getElementById('activate').scrollIntoView({{behavior:'smooth'}});
}}

document.getElementById('activate').onsubmit = async (e) => {{
  e.preventDefault();
  const contractor_id = document.getElementById('contractor_id').value.trim();
  const wallet = document.getElementById('wallet').value.trim();
  const tier = document.getElementById('tier').value;
  activeTier = tier;
  const res = await fetch('/api/v1/subscribe/activate', {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{contractor_id, wallet, tier}})
  }});
  const data = await res.json();
  const r = document.getElementById('result');
  if (data.ok) {{
    r.innerHTML = `
      <div class="step">
        <p class="success">Subscription activated (status: pending payment).</p>
        <p>Send <strong>$${{data.monthly_usdc}} USDC</strong> from your wallet to:</p>
        <div class="wallet">${{VAULT}}</div>
        <p class="small">Memo: <code>${{data.memo}}</code></p>
        <p>Then click the button below to verify.</p>
        <button class="cta" onclick="verifyNow('{contractor_id}')">I paid — verify now</button>
      </div>`;
  }} else {{
    r.innerHTML = `<p class="error">${{data.error || 'failed'}}</p>`;
  }}
}};

async function verifyNow(cid) {{
  const r = document.getElementById('result');
  r.innerHTML += '<p>verifying on-chain...</p>';
  const res = await fetch('/api/v1/subscribe/verify', {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{contractor_id: cid}})
  }});
  const data = await res.json();
  if (data.verified) {{
    r.innerHTML = `<p class="success">✅ Verified. Your ${{activeTier}} tier is active. We saw $${{data.amount_usdc}} USDC.</p>`;
  }} else {{
    r.innerHTML = `<p class="error">No payment found yet. Send the USDC and try again in 60 seconds.</p>`;
  }}
}}
</script>
</body>
</html>
"""


def render_for_contractors_page() -> str:
    """Render the pricing page. Use string replace to avoid .format() clashing
    with JS template literals (e.g. `{{behavior:'smooth'}}`)."""
    # Escape any literal single-braces from .format() by doubling them is overkill.
    # Use string substitution which doesn't interpret braces.
    return FOR_CONTRACTORS_HTML.replace("{vault}", VAULT_WALLET)