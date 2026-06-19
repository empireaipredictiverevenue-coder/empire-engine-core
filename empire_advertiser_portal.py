"""
EMPIRE V49 · ADVERTISER PORTAL
===============================
Self-serve ad network advertiser accounts. Advertisers sign up, deposit
ad credits, create campaigns + creatives, and monitor performance.

ENDPOINTS
─────────
  GET  /advertisers/signup                                → public signup form
  POST /api/v1/advertisers/signup                         → create advertiser account
  GET  /advertisers/login                                  → public login form
  POST /api/v1/advertisers/login                           → send magic link email
  GET  /advertisers/{id}/verify?t=...                     → verify token, set cookie, redirect
  GET  /advertisers/{id}/dashboard                         → main advertiser dashboard
  GET  /advertisers/logout                                 → clear session
  GET  /api/v1/advertisers/{id}/stats                      → aggregate stats JSON
  GET  /api/v1/advertisers/{id}/campaigns                  → list campaigns JSON
  POST /api/v1/advertisers/{id}/campaigns                  → create campaign + creative
  PATCH /api/v1/advertisers/campaigns/{campaign_id}        → update campaign
  POST /api/v1/advertisers/campaigns/{campaign_id}/toggle  → pause/activate campaign
  POST /api/v1/advertisers/{id}/creatives                  → create creative
  PATCH /api/v1/advertisers/creatives/{creative_id}        → update creative
  GET  /api/v1/advertisers/{id}/transactions               → payment history JSON
  GET  /api/v1/advertisers/{id}/balance                    → current balance JSON
"""

import os
import re
import time
import json
import uuid
import secrets
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from supabase import create_client

log = logging.getLogger("empire.advertiser")

# ── CONFIG ───────────────────────────────────────────────────────────
_SB = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", ""),
)

LOGIN_LINK_TTL_SECONDS = 600  # 10 min
SESSION_TTL_HOURS = 24

# In-memory session store (same pattern as affiliate/publisher portals)
_ADV_SESSION_HASHES: dict[str, dict] = {}


# ── HELPERS ──────────────────────────────────────────────────────────
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _verify_session(token: str) -> Optional[dict]:
    th = _hash_token(token)
    sess = _ADV_SESSION_HASHES.get(th)
    if not sess:
        return None
    if datetime.now(timezone.utc) > sess["expires_at"]:
        del _ADV_SESSION_HASHES[th]
        return None
    return sess.get("advertiser")


def _resolve_advertiser(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        adv = _verify_session(auth[7:])
        if adv:
            return adv
    token = request.cookies.get("advertiser_session", "")
    if token:
        adv = _verify_session(token)
        if adv:
            return adv
    return None


# ── CSS ──────────────────────────────────────────────────────────────
_ADV_SIGNUP_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0a1a2f; color: #f8fafd;
  font-family: 'Inter', -apple-system, sans-serif;
  letter-spacing: -0.02em;
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  padding: 40px 20px;
  background:
    radial-gradient(ellipse at top right, rgba(68,229,184,0.06), transparent 50%),
    radial-gradient(ellipse at bottom left, rgba(90,200,250,0.05), transparent 50%),
    #0a1a2f;
}
.box { max-width: 480px; width: 100%; background: #15263f; border: 1px solid rgba(122,140,163,0.18); padding: 44px 40px; }
.brand { display: flex; align-items: baseline; justify-content: center; gap: 8px; margin-bottom: 6px; }
.brand-e { font-weight: 700; font-size: 20px; letter-spacing: 0.22em; }
.brand-ai { font-weight: 700; font-size: 20px; letter-spacing: 0.22em; color: #5ac8fa; }
.brand-sub { text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #4a5a72; letter-spacing: 0.32em; text-transform: uppercase; margin-bottom: 28px; }
h1 { font-weight: 200; font-size: 26px; letter-spacing: -0.04em; margin-bottom: 8px; text-align: center; }
h1 em { font-style: italic; color: #44e5b8; font-weight: 500; }
.lead { text-align: center; color: #7a8ca3; font-size: 13px; line-height: 1.7; margin-bottom: 28px; }
.field { margin-bottom: 16px; }
.field label { display: block; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #7a8ca3; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 5px; }
.field input, .field select { width: 100%; background: rgba(0,0,0,0.4); color: #f8fafd; border: 1px solid rgba(122,140,163,0.18); font-family: 'JetBrains Mono', monospace; font-size: 13px; padding: 12px 14px; outline: none; transition: border-color 0.2s; }
.field input:focus, .field select:focus { border-color: #44e5b8; }
.field select option { background: #15263f; color: #f8fafd; }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 560px) { .row2 { grid-template-columns: 1fr; } }
.btn { width: 100%; background: #44e5b8; color: #000; border: none; padding: 14px; font-family: 'Inter', sans-serif; font-weight: 700; font-size: 14px; letter-spacing: 0.04em; cursor: pointer; transition: all 0.2s; margin-top: 8px; }
.btn:hover { background: transparent; color: #44e5b8; outline: 1px solid #44e5b8; }
.btn:disabled { opacity: 0.4; cursor: wait; }
.flash { display: none; padding: 12px 16px; margin-top: 14px; font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.04em; }
.flash.show { display: block; }
.flash.success { color: #44e5b8; background: rgba(68,229,184,0.06); border: 1px solid rgba(68,229,184,0.25); }
.flash.error { color: #f43f5e; background: rgba(244,63,94,0.06); border: 1px solid rgba(244,63,94,0.25); }
.foot { text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #4a5a72; letter-spacing: 0.18em; margin-top: 28px; }
.login-link { text-align: center; margin-top: 16px; font-family: 'JetBrains Mono', monospace; font-size: 10px; }
.login-link a { color: #44e5b8; text-decoration: none; }
.login-link a:hover { text-decoration: underline; }
"""

_ADV_DASHBOARD_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0a1a2f; --bg2: #15263f; --bg3: #1a2f4a;
  --fg: #f8fafd; --fg2: #c8d0dc; --fg3: #7a8ca3;
  --teal: #44e5b8; --cyan: #5ac8fa; --amber: #ffb800; --red: #f43f5e;
  --divider: rgba(122,140,163,0.18); --radius: 8px;
  --font: 'Inter', -apple-system, sans-serif;
  --mono: 'JetBrains Mono', monospace;
}
body { background: var(--bg); color: var(--fg); font-family: var(--font); letter-spacing: -0.02em; min-height: 100vh; }
.header {
  background: var(--bg2); border-bottom: 1px solid var(--divider);
  padding: 20px 32px; display: flex; align-items: center; justify-content: space-between;
}
.header-brand { display: flex; align-items: baseline; gap: 8px; }
.header-brand .e { font-weight: 700; font-size: 18px; letter-spacing: 0.22em; }
.header-brand .ai { font-weight: 700; font-size: 18px; letter-spacing: 0.22em; color: var(--cyan); }
.header h1 { font-weight: 200; font-size: 20px; letter-spacing: -0.04em; }
.header h1 em { color: var(--teal); font-style: italic; font-weight: 500; }
.header-right { display: flex; align-items: center; gap: 16px; font-family: var(--mono); font-size: 10px; color: var(--fg3); }
.header-right .name { color: var(--fg2); }
.logout { color: var(--red); text-decoration: none; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }
.logout:hover { text-decoration: underline; }
.container { max-width: 1100px; margin: 0 auto; padding: 28px 24px; }
.greeting { margin-bottom: 28px; }
.greeting h2 { font-weight: 200; font-size: 22px; letter-spacing: -0.04em; }
.greeting h2 em { color: var(--teal); font-style: italic; font-weight: 500; }
.greeting .sub { font-family: var(--mono); font-size: 10px; color: var(--fg3); margin-top: 4px; letter-spacing: 0.08em; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 28px; }
.card {
  background: var(--bg2); border: 1px solid var(--divider); padding: 18px 20px;
  transition: border-color 0.2s;
}
.card:hover { border-color: rgba(68,229,184,0.3); }
.card-label { font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 6px; }
.card-value { font-family: var(--font); font-weight: 200; font-size: 26px; color: var(--fg); line-height: 1; }
.card-value.teal { color: var(--teal); }
.card-value.cyan { color: var(--cyan); }
.card-value.amber { color: var(--amber); }
.card-value.red { color: var(--red); }
.card-meta { font-family: var(--mono); font-size: 9px; color: var(--fg3); margin-top: 6px; }
.section { margin-bottom: 32px; }
.section-title { font-family: var(--mono); font-size: 10px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
.section-title strong { color: var(--fg2); font-weight: 500; }
.section-title .count { color: var(--teal); font-size: 9px; background: rgba(68,229,184,0.1); padding: 2px 8px; }
table { width: 100%; border-collapse: collapse; background: var(--bg2); border: 1px solid var(--divider); }
thead th {
  font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em;
  text-transform: uppercase; text-align: left; padding: 10px 14px;
  border-bottom: 1px solid var(--divider); background: rgba(0,0,0,0.15);
}
tbody td { padding: 10px 14px; border-bottom: 1px solid rgba(122,140,163,0.08); font-family: var(--mono); font-size: 10px; color: var(--fg2); }
tbody tr:last-child td { border-bottom: none; }
.num { text-align: right; }
.empty { text-align: center; padding: 32px; color: var(--fg3); font-family: var(--mono); font-size: 10px; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--divider); margin-bottom: 16px; flex-wrap: wrap; }
.tab {
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  padding: 8px 16px; cursor: pointer; border: none; background: transparent;
  color: var(--fg3); border-bottom: 2px solid transparent; transition: all 0.2s;
}
.tab:hover { color: var(--fg2); }
.tab.active { color: var(--teal); border-bottom-color: var(--teal); }
.tab-content { display: none; }
.tab-content.active { display: block; }
.badge {
  display: inline-block; font-family: var(--mono); font-size: 8px;
  padding: 2px 6px; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.08em;
}
.badge.active { color: var(--teal); background: rgba(68,229,184,0.1); }
.badge.paused { color: var(--amber); background: rgba(255,184,0,0.1); }
.badge.ended { color: var(--fg3); background: rgba(122,140,163,0.1); }
.badge.archived { color: var(--fg3); background: rgba(122,140,163,0.1); }
.btn { font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase; padding: 8px 16px; cursor: pointer; border: none; transition: all 0.2s; }
.btn-teal { background: var(--teal); color: #000; }
.btn-teal:hover { background: transparent; color: var(--teal); outline: 1px solid var(--teal); }
.btn-cyan { background: var(--cyan); color: #000; }
.btn-cyan:hover { background: transparent; color: var(--cyan); outline: 1px solid var(--cyan); }
.btn-amber { background: var(--amber); color: #000; }
.btn-amber:hover { background: transparent; color: var(--amber); outline: 1px solid var(--amber); }
.campaign-form { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; align-items: end; }
.campaign-form .field { margin-bottom: 0; }
.campaign-form .field label { display: block; font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 4px; }
.campaign-form input, .campaign-form select, .campaign-form textarea {
  width: 100%; background: rgba(0,0,0,0.4); color: var(--fg);
  border: 1px solid var(--divider); font-family: var(--mono); font-size: 12px;
  padding: 8px 10px; outline: none; transition: border-color 0.2s;
}
.campaign-form input:focus, .campaign-form select:focus, .campaign-form textarea:focus { border-color: var(--teal); }
.campaign-form textarea { resize: vertical; min-height: 60px; }
.campaign-form select option { background: var(--bg2); color: var(--fg); }
.campaign-form button {
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  background: var(--teal); color: #000; border: none; padding: 8px 16px; cursor: pointer;
  white-space: nowrap; align-self: end;
}
.campaign-form button:hover { background: transparent; color: var(--teal); outline: 1px solid var(--teal); }
.campaign-full { grid-column: 1 / -1; }
.action-link { color: var(--cyan); text-decoration: none; cursor: pointer; font-family: var(--mono); font-size: 9px; }
.action-link:hover { text-decoration: underline; }
.action-link.danger { color: var(--red); }
.copy-box {
  background: rgba(0,0,0,0.3); border: 1px solid var(--divider);
  padding: 16px; font-family: var(--mono); font-size: 10px; line-height: 1.6;
  color: var(--fg2); white-space: pre-wrap; word-break: break-all;
  max-height: 200px; overflow-y: auto; margin-bottom: 12px;
}
.creative-form { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.creative-form .field-full { grid-column: 1 / -1; }
.creative-form .field { margin-bottom: 0; }
.creative-form .field label { display: block; font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 4px; }
.creative-form input, .creative-form select, .creative-form textarea {
  width: 100%; background: rgba(0,0,0,0.4); color: var(--fg);
  border: 1px solid var(--divider); font-family: var(--mono); font-size: 12px;
  padding: 8px 10px; outline: none; transition: border-color 0.2s;
}
.creative-form input:focus, .creative-form select:focus, .creative-form textarea:focus { border-color: var(--teal); }
.creative-form textarea { resize: vertical; min-height: 50px; }
.creative-form select option { background: var(--bg2); color: var(--fg); }
.creative-form button {
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  background: var(--cyan); color: #000; border: none; padding: 8px 16px; cursor: pointer;
  white-space: nowrap; align-self: end;
}
.creative-form button:hover { background: transparent; color: var(--cyan); outline: 1px solid var(--cyan); }
.balance-bar {
  background: rgba(0,0,0,0.3); border: 1px solid var(--divider);
  padding: 18px 20px; margin-bottom: 20px;
  display: flex; align-items: center; justify-content: space-between;
}
.balance-amount { font-weight: 200; font-size: 28px; color: var(--teal); }
.balance-amount .ccy { font-size: 14px; color: var(--fg3); vertical-align: super; }
.balance-label { font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; }
.modal-overlay {
  display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.6); z-index: 100; align-items: center; justify-content: center;
}
.modal-overlay.show { display: flex; }
.modal {
  background: var(--bg2); border: 1px solid var(--divider); padding: 32px;
  max-width: 640px; width: 90%; max-height: 80vh; overflow-y: auto;
}
.modal h3 { font-weight: 200; font-size: 18px; margin-bottom: 16px; }
.modal h3 em { color: var(--teal); font-style: italic; font-weight: 500; }
.modal-close { float: right; color: var(--fg3); cursor: pointer; font-family: var(--mono); font-size: 18px; }
.modal-close:hover { color: var(--red); }
"""


# ── SIGNUP FORM PAGE ─────────────────────────────────────────────────
_ADV_SIGNUP_PAGE = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Advertiser Signup</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{_ADV_SIGNUP_CSS}</style>
</head><body>
<div class="box">
  <div class="brand"><span class="brand-e">EMPIRE</span><span class="brand-ai">AI</span></div>
  <div class="brand-sub">Ad Network · Reach Your Customers</div>
  <h1>Become an <em>Advertiser</em></h1>
  <p class="lead">Reach property owners and contractors across our publisher network. Set your budget, create campaigns, and track results.</p>
  <form id="signupForm" onsubmit="return submitForm(event)">
    <div class="row2">
      <div class="field">
        <label>Company name</label>
        <input type="text" id="company_name" placeholder="Your Company, LLC" required>
      </div>
      <div class="field">
        <label>Contact name</label>
        <input type="text" id="contact_name" placeholder="Jane Doe" required>
      </div>
    </div>
    <div class="row2">
      <div class="field">
        <label>Email</label>
        <input type="email" id="email" placeholder="jane@yourcompany.com" required>
      </div>
      <div class="field">
        <label>Phone (optional)</label>
        <input type="tel" id="phone" placeholder="+1 555-0123">
      </div>
    </div>
    <div class="field">
      <label>Website</label>
      <input type="url" id="website" placeholder="https://yourcompany.com">
    </div>
    <button type="submit" class="btn" id="submitBtn">Create advertiser account →</button>
  </form>
  <div id="flash" class="flash"></div>
  <div class="login-link">Already have an account? <a href="/advertisers/login">Sign in →</a></div>
  <div class="foot">Empire AI V49 · Predictive Revenue Network</div>
</div>
<script>
async function submitForm(event) {{
  event.preventDefault();
  const flash = document.getElementById('flash');
  const btn = document.getElementById('submitBtn');
  flash.className = 'flash';
  btn.disabled = true; btn.textContent = 'Creating account...';
  try {{
    const r = await fetch('/api/v1/advertisers/signup', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        company_name: document.getElementById('company_name').value.trim(),
        contact_name: document.getElementById('contact_name').value.trim(),
        email: document.getElementById('email').value.trim(),
        phone: document.getElementById('phone').value.trim(),
        website: document.getElementById('website').value.trim(),
      }}),
    }});
    const d = await r.json();
    if (r.ok && d.ok) {{
      flash.className = 'flash show success';
      flash.textContent = '✓ Account created! Check your email for the login link.';
      document.getElementById('signupForm').reset();
    }} else {{
      flash.className = 'flash show error';
      flash.textContent = '✗ ' + (d.error || 'Signup failed. Please try again.');
    }}
  }} catch (e) {{
    flash.className = 'flash show error';
    flash.textContent = '✗ Network error. Please check your connection.';
  }} finally {{
    btn.disabled = false; btn.textContent = 'Create advertiser account →';
  }}
}}
</script>
</body></html>"""


# ── LOGIN PAGE ───────────────────────────────────────────────────────
_ADV_LOGIN_PAGE = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Advertiser Login</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{_ADV_SIGNUP_CSS}</style>
</head><body>
<div class="box">
  <div class="brand"><span class="brand-e">EMPIRE</span><span class="brand-ai">AI</span></div>
  <div class="brand-sub">Advertiser Portal</div>
  <h1>Advertiser <em>Login</em></h1>
  <p class="lead">Enter your email and we'll send a one-time sign-in link.</p>
  <div class="field">
    <label>Email</label>
    <input type="email" id="email" placeholder="jane@yourcompany.com" autofocus>
  </div>
  <button class="btn" id="btn" onclick="send()">Send login link</button>
  <div id="flash" class="flash"></div>
  <div class="login-link">New advertiser? <a href="/advertisers/signup">Sign up →</a></div>
  <div class="foot">Empire AI V49 · Predictive Revenue Network</div>
</div>
<script>
async function send() {{
  const email = document.getElementById('email').value.trim();
  const flash = document.getElementById('flash');
  const btn = document.getElementById('btn');
  flash.className = 'flash';
  if (!email || !email.includes('@')) {{
    flash.className = 'flash show error';
    flash.textContent = 'Enter a valid email';
    return;
  }}
  btn.disabled = true; btn.textContent = 'Sending...';
  try {{
    const r = await fetch('/api/v1/advertisers/login', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ email }}),
    }});
    const d = await r.json();
    if (r.ok && d.ok) {{
      flash.className = 'flash show success';
      flash.textContent = 'If that email is registered, a login link is on its way.';
    }} else {{
      flash.className = 'flash show error';
      flash.textContent = d.error || 'Could not send';
    }}
  }} catch (e) {{
    flash.className = 'flash show error';
    flash.textContent = 'Network error';
  }} finally {{
    btn.disabled = false; btn.textContent = 'Send login link';
  }}
}}
document.getElementById('email').addEventListener('keydown', e => {{ if (e.key === 'Enter') send(); }});
</script>
</body></html>"""


# ── DASHBOARD PAGE ───────────────────────────────────────────────────
def _advertiser_dashboard(advertiser: dict, base_url: str = "http://localhost:8001") -> str:
    adv_id = advertiser.get("id", "")
    adv_name = advertiser.get("company_name", "Advertiser")
    pid_json = json.dumps(adv_id)
    base_json = json.dumps(base_url)
    balance = float(advertiser.get("balance", 0) or 0)
    balance_str = f"${balance:,.2f}" if balance else "$0.00"

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Advertiser Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>{_ADV_DASHBOARD_CSS}</style>
</head><body>
<div class="header">
  <div class="header-brand"><span class="e">EMPIRE</span><span class="ai">AI</span></div>
  <h1>Advertiser <em>Dashboard</em></h1>
  <div class="header-right">
    <span class="name">{adv_name}</span>
    <a href="/advertisers/logout" class="logout">Sign out</a>
  </div>
</div>
<div class="container">
  <div class="greeting">
    <h2>Welcome, <em>{adv_name}</em></h2>
    <div class="sub">Advertiser Portal · Native Ad Network</div>
  </div>

  <div class="balance-bar">
    <div>
      <div class="balance-label">Ad Credit Balance</div>
      <div class="balance-amount"><span class="ccy">$</span>{balance:,.2f}</div>
    </div>
    <div style="display:flex;gap:8px;">
      <button class="btn btn-teal" onclick="showDepositModal()">+ Deposit Funds</button>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('overview')">Overview</button>
    <button class="tab" onclick="switchTab('campaigns')">Campaigns</button>
    <button class="tab" onclick="switchTab('creatives')">Creatives</button>
    <button class="tab" onclick="switchTab('payments')">Payments</button>
  </div>

  <div id="tab-overview" class="tab-content active">
    <div class="grid" id="statsGrid">
      <div class="card"><div class="card-label">Active Campaigns</div><div class="card-value" id="stat-campaigns">--</div></div>
      <div class="card"><div class="card-label">Total Spend</div><div class="card-value teal" id="stat-spend">--</div></div>
      <div class="card"><div class="card-label">Impressions</div><div class="card-value" id="stat-impressions">--</div></div>
      <div class="card"><div class="card-label">Clicks</div><div class="card-value cyan" id="stat-clicks">--</div></div>
      <div class="card"><div class="card-label">CTR</div><div class="card-value" id="stat-ctr">--</div></div>
      <div class="card"><div class="card-label">Daily Budget Used</div><div class="card-value amber" id="stat-budget">--</div></div>
    </div>
    <div class="section">
      <div class="section-title"><strong>Quick Actions</strong></div>
      <button class="btn btn-teal" onclick="switchTab('campaigns')" style="margin-right:8px;">Create Campaign →</button>
      <button class="btn btn-cyan" onclick="showDepositModal()">Deposit Funds →</button>
    </div>
  </div>

  <div id="tab-campaigns" class="tab-content">
    <div class="section-title"><strong>Your Campaigns</strong></div>
    <button class="btn btn-teal" onclick="showNewCampaignModal()" style="margin-bottom:16px;">+ New Campaign</button>
    <table>
      <thead><tr><th>Name</th><th>Niche</th><th>Status</th><th>Daily Budget</th><th>Spent Today</th><th>Impressions</th><th>Clicks</th><th>CTR</th><th>Actions</th></tr></thead>
      <tbody id="campaignsBody">
        <tr><td class="empty" colspan="9">Loading...</td></tr>
      </tbody>
    </table>
  </div>

  <div id="tab-creatives" class="tab-content">
    <div class="section-title"><strong>Your Creatives</strong></div>
    <button class="btn btn-cyan" onclick="showNewCreativeModal()" style="margin-bottom:16px;">+ New Creative</button>
    <table>
      <thead><tr><th>Headline</th><th>Campaign</th><th>Status</th><th>Impressions</th><th>Clicks</th><th>CTR</th><th>Actions</th></tr></thead>
      <tbody id="creativesBody">
        <tr><td class="empty" colspan="7">Loading...</td></tr>
      </tbody>
    </table>
  </div>

  <div id="tab-payments" class="tab-content">
    <div class="section-title"><strong>Transaction History</strong></div>
    <table>
      <thead><tr><th>Date</th><th>Type</th><th>Amount</th><th>Balance</th><th>Description</th></tr></thead>
      <tbody id="paymentsBody">
        <tr><td class="empty" colspan="5">Loading...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<!-- Deposit Modal -->
<div id="depositModal" class="modal-overlay">
  <div class="modal">
    <span class="modal-close" onclick="hideDepositModal()">&times;</span>
    <h3>Deposit <em>Ad Credits</em></h3>
    <p style="color:var(--fg3);font-family:var(--mono);font-size:10px;margin-bottom:16px;">
      To deposit funds, send USDC (Solana) to the Empire AI vault wallet and we'll credit your account.
    </p>
    <div class="balance-label" style="margin-bottom:4px;">Empire AI Vault Wallet</div>
    <div class="copy-box" id="vaultWalletDisplay" style="font-size:11px;">Loading...</div>
    <p style="color:var(--fg3);font-family:var(--mono);font-size:9px;margin:8px 0 16px;">
      After sending, email support@empire-ai.co.uk with your transaction hash for credit.<br>
      Credits are typically applied within 1 business hour.
    </p>
    <button class="btn btn-teal" onclick="hideDepositModal()" style="width:auto;">Got it</button>
  </div>
</div>

<!-- New Campaign Modal -->
<div id="newCampaignModal" class="modal-overlay">
  <div class="modal">
    <span class="modal-close" onclick="hideNewCampaignModal()">&times;</span>
    <h3>New <em>Campaign</em></h3>
    <div class="campaign-form">
      <div class="field campaign-full">
        <label>Campaign Name</label>
        <input type="text" id="newCampName" placeholder="e.g. Roofing Q3 DFW">
      </div>
      <div class="field">
        <label>Niche</label>
        <select id="newCampNiche">
          <option value="Roofing Restoration">Roofing Restoration</option>
          <option value="HVAC">HVAC</option>
          <option value="Restoration">Restoration</option>
          <option value="General Contractor">General Contractor</option>
          <option value="Plumbing">Plumbing</option>
          <option value="Electrical">Electrical</option>
          <option value="Mold Remediation">Mold Remediation</option>
          <option value="Affiliate Program">Affiliate Program</option>
        </select>
      </div>
      <div class="field">
        <label>Daily Budget ($)</label>
        <input type="number" id="newCampBudget" value="50" min="5" step="5">
      </div>
      <div class="field">
        <label>Target URL</label>
        <input type="url" id="newCampUrl" placeholder="https://yourcompany.com/landing">
      </div>
      <div class="field">
        <label>Target Metros (comma sep)</label>
        <input type="text" id="newCampMetros" placeholder="dallas, houston, san antonio">
      </div>
      <div class="field campaign-full" style="margin-top:8px;">
        <div class="balance-label" style="margin-bottom:8px;">First Creative</div>
      </div>
      <div class="field">
        <label>Headline (max 80 chars)</label>
        <input type="text" id="newCreativeHeadline" placeholder="Need Roof Repairs? We Can Help">
      </div>
      <div class="field">
        <label>Body (max 200 chars)</label>
        <input type="text" id="newCreativeBody" placeholder="Get a free estimate from top-rated contractors in your area.">
      </div>
      <div class="field">
        <label>CTA Text</label>
        <input type="text" id="newCreativeCta" placeholder="Get Free Quote" value="Learn More">
      </div>
      <div class="field">
        <label>Destination URL (override)</label>
        <input type="url" id="newCreativeDest" placeholder="Same as campaign URL if blank">
      </div>
      <button onclick="createCampaign()" style="grid-column:1/-1;">Create Campaign + Creative</button>
    </div>
  </div>
</div>

<!-- New Creative Modal -->
<div id="newCreativeModal" class="modal-overlay">
  <div class="modal">
    <span class="modal-close" onclick="hideNewCreativeModal()">&times;</span>
    <h3>New <em>Creative</em></h3>
    <div class="creative-form">
      <div class="field field-full">
        <label>Campaign</label>
        <select id="newCreativeCampaign"><option value="">-- Loading campaigns --</option></select>
      </div>
      <div class="field">
        <label>Headline (max 80 chars)</label>
        <input type="text" id="newCrHeadline" placeholder="Need Roof Repairs?">
      </div>
      <div class="field">
        <label>CTA Text</label>
        <input type="text" id="newCrCta" value="Learn More">
      </div>
      <div class="field field-full">
        <label>Body (max 200 chars)</label>
        <textarea id="newCrBody" placeholder="Describe your offer..."></textarea>
      </div>
      <div class="field">
        <label>Destination URL</label>
        <input type="url" id="newCrDest" placeholder="Leave blank to use campaign URL">
      </div>
      <div class="field">
        <label>Ad Size</label>
        <select id="newCrSize">
          <option value="300x250">300x250 (Medium Rectangle)</option>
          <option value="728x90">728x90 (Leaderboard)</option>
          <option value="160x600">160x600 (Skyscraper)</option>
        </select>
      </div>
      <button onclick="createCreative()">Create Creative</button>
    </div>
  </div>
</div>

<script>
const ADV_ID = {pid_json};
const BASE_URL = {base_json};

async function apiFetch(path) {{
  const r = await fetch(path, {{ credentials: 'include' }});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}}

function fmtCurrency(v) {{
  if (v === null || v === undefined || v === 0) return '$0.00';
  return '$' + Number(v).toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
}}

function fmtNumber(v) {{
  if (!v) return '0';
  return Number(v).toLocaleString();
}}

function fmtPct(v) {{
  if (!v) return '0%';
  return Number(v).toFixed(2) + '%';
}}

function fmtDate(ts) {{
  if (!ts) return '--';
  return ts.slice(0, 10);
}}

function _esc(s) {{
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}}

function statusBadge(status) {{
  var cls = status || 'paused';
  if (cls === 'active') return '<span class="badge active">Active</span>';
  if (cls === 'paused') return '<span class="badge paused">Paused</span>';
  if (cls === 'ended') return '<span class="badge ended">Ended</span>';
  return '<span class="badge archived">' + _esc(cls) + '</span>';
}}

// ── Overview Stats ──────────────────────────────────────────────
async function loadStats() {{
  try {{
    const d = await apiFetch('/api/v1/advertisers/' + ADV_ID + '/stats');
    document.getElementById('stat-campaigns').textContent = d.active_campaigns || 0;
    document.getElementById('stat-spend').textContent = fmtCurrency(d.total_spend);
    document.getElementById('stat-impressions').textContent = fmtNumber(d.total_impressions);
    document.getElementById('stat-clicks').textContent = fmtNumber(d.total_clicks);
    document.getElementById('stat-ctr').textContent = fmtPct(d.ctr);
    document.getElementById('stat-budget').textContent = fmtCurrency(d.daily_budget_used);
  }} catch (e) {{
    document.querySelectorAll('#statsGrid .card-value').forEach(function(el) {{ el.textContent = 'err'; }});
  }}
}}

// ── Campaigns ───────────────────────────────────────────────────
async function loadCampaigns() {{
  try {{
    const d = await apiFetch('/api/v1/advertisers/' + ADV_ID + '/campaigns');
    const tbody = document.getElementById('campaignsBody');
    if (!d.campaigns || d.campaigns.length === 0) {{
      tbody.innerHTML = '<tr><td class="empty" colspan="9">No campaigns yet. Create your first one above.</td></tr>';
      return;
    }}
    tbody.innerHTML = d.campaigns.map(function(c) {{
      var imp = c.impressions || 0;
      var clk = c.clicks || 0;
      var ctr = imp > 0 ? ((clk / imp) * 100).toFixed(2) : '0.00';
      var daily = fmtCurrency(c.daily_budget);
      var spent = fmtCurrency(c.spent_today);
      return '<tr>' +
        '<td><strong>' + _esc(c.name || '--') + '</strong></td>' +
        '<td>' + _esc(c.niche || '--') + '</td>' +
        '<td>' + statusBadge(c.status) + '</td>' +
        '<td class="num">' + daily + '</td>' +
        '<td class="num">' + spent + '</td>' +
        '<td class="num">' + fmtNumber(imp) + '</td>' +
        '<td class="num">' + fmtNumber(clk) + '</td>' +
        '<td class="num">' + ctr + '%</td>' +
        '<td><a class="action-link" onclick="toggleCampaign(\\'' + c.id + '\\',\\'' + (c.status === 'active' ? 'paused' : 'active') + '\\')">' + (c.status === 'active' ? 'Pause' : 'Activate') + '</a></td>' +
      '</tr>';
    }}).join('');
  }} catch (e) {{
    document.getElementById('campaignsBody').innerHTML = '<tr><td class="empty" colspan="9">Failed to load</td></tr>';
  }}
}}

async function toggleCampaign(campaignId, newStatus) {{
  try {{
    var r = await fetch('/api/v1/advertisers/campaigns/' + campaignId + '/toggle', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ status: newStatus }}),
    }});
    var d = await r.json();
    if (r.ok && d.ok) {{
      loadCampaigns();
      loadStats();
    }}
  }} catch (e) {{}}
}}

function showNewCampaignModal() {{
  document.getElementById('newCampaignModal').classList.add('show');
}}
function hideNewCampaignModal() {{
  document.getElementById('newCampaignModal').classList.remove('show');
}}

async function createCampaign() {{
  var name = document.getElementById('newCampName').value.trim();
  var niche = document.getElementById('newCampNiche').value;
  var budget = parseFloat(document.getElementById('newCampBudget').value) || 50;
  var url = document.getElementById('newCampUrl').value.trim();
  var metros = document.getElementById('newCampMetros').value.trim();
  var headline = document.getElementById('newCreativeHeadline').value.trim();
  var body = document.getElementById('newCreativeBody').value.trim();
  var cta = document.getElementById('newCreativeCta').value.trim() || 'Learn More';
  var dest = document.getElementById('newCreativeDest').value.trim();

  if (!name) {{ alert('Campaign name is required'); return; }}
  if (!headline || !body) {{ alert('Headline and body are required for the first creative'); return; }}

  try {{
    var r = await fetch('/api/v1/advertisers/' + ADV_ID + '/campaigns', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        name: name,
        niche: niche,
        daily_budget: budget,
        target_url: url,
        target_metros: metros ? metros.split(',').map(function(m) {{ return m.trim(); }}).filter(Boolean) : [],
        creative: {{ headline: headline, body: body, cta_text: cta, destination_url: dest || undefined }},
      }}),
    }});
    var d = await r.json();
    if (r.ok && d.ok) {{
      hideNewCampaignModal();
      document.getElementById('newCampName').value = '';
      document.getElementById('newCreativeHeadline').value = '';
      document.getElementById('newCreativeBody').value = '';
      loadCampaigns();
      loadStats();
    }} else {{
      alert(d.error || 'Failed to create campaign');
    }}
  }} catch (e) {{
    alert('Network error');
  }}
}}

// ── Creatives ───────────────────────────────────────────────────
async function loadCreatives() {{
  try {{
    const d = await apiFetch('/api/v1/advertisers/' + ADV_ID + '/creatives');
    const tbody = document.getElementById('creativesBody');
    if (!d.creatives || d.creatives.length === 0) {{
      tbody.innerHTML = '<tr><td class="empty" colspan="7">No creatives yet. Create one above.</td></tr>';
      return;
    }}
    tbody.innerHTML = d.creatives.map(function(cr) {{
      var imp = cr.impressions || 0;
      var clk = cr.clicks || 0;
      var ctr = imp > 0 ? ((clk / imp) * 100).toFixed(2) : '0.00';
      return '<tr>' +
        '<td><strong>' + _esc(cr.headline || '--') + '</strong></td>' +
        '<td>' + _esc(cr.campaign_name || '--') + '</td>' +
        '<td>' + statusBadge(cr.status) + '</td>' +
        '<td class="num">' + fmtNumber(imp) + '</td>' +
        '<td class="num">' + fmtNumber(clk) + '</td>' +
        '<td class="num">' + ctr + '%</td>' +
        '<td><a class="action-link" onclick="toggleCreative(\\'' + cr.id + '\\',\\'' + (cr.status === 'active' ? 'paused' : 'active') + '\\')">' + (cr.status === 'active' ? 'Pause' : 'Activate') + '</a></td>' +
      '</tr>';
    }}).join('');
  }} catch (e) {{
    document.getElementById('creativesBody').innerHTML = '<tr><td class="empty" colspan="7">Failed to load</td></tr>';
  }}
}}

async function toggleCreative(creativeId, newStatus) {{
  try {{
    var r = await fetch('/api/v1/advertisers/creatives/' + creativeId, {{
      method: 'PATCH',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ status: newStatus }}),
    }});
    var d = await r.json();
    if (r.ok && d.ok) {{
      loadCreatives();
    }}
  }} catch (e) {{}}
}}

function showNewCreativeModal() {{
  document.getElementById('newCreativeModal').classList.add('show');
  loadCreativeCampaigns();
}}
function hideNewCreativeModal() {{
  document.getElementById('newCreativeModal').classList.remove('show');
}}

async function loadCreativeCampaigns() {{
  try {{
    const d = await apiFetch('/api/v1/advertisers/' + ADV_ID + '/campaigns');
    var select = document.getElementById('newCreativeCampaign');
    if (d.campaigns && d.campaigns.length > 0) {{
      select.innerHTML = d.campaigns.map(function(c) {{
        return '<option value="' + c.id + '">' + _esc(c.name) + ' (' + _esc(c.niche) + ')</option>';
      }}).join('');
    }} else {{
      select.innerHTML = '<option value="">-- No campaigns yet --</option>';
    }}
  }} catch (e) {{}}
}}

async function createCreative() {{
  var campaignId = document.getElementById('newCreativeCampaign').value;
  var headline = document.getElementById('newCrHeadline').value.trim();
  var body = document.getElementById('newCrBody').value.trim();
  var cta = document.getElementById('newCrCta').value.trim() || 'Learn More';
  var dest = document.getElementById('newCrDest').value.trim();
  var size = document.getElementById('newCrSize').value;

  if (!campaignId) {{ alert('Select a campaign'); return; }}
  if (!headline || !body) {{ alert('Headline and body are required'); return; }}

  try {{
    var r = await fetch('/api/v1/advertisers/' + ADV_ID + '/creatives', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        campaign_id: campaignId,
        headline: headline,
        body: body,
        cta_text: cta,
        destination_url: dest || undefined,
        ad_size: size,
      }}),
    }});
    var d = await r.json();
    if (r.ok && d.ok) {{
      hideNewCreativeModal();
      document.getElementById('newCrHeadline').value = '';
      document.getElementById('newCrBody').value = '';
      loadCreatives();
    }} else {{
      alert(d.error || 'Failed to create creative');
    }}
  }} catch (e) {{
    alert('Network error');
  }}
}}

// ── Payments ────────────────────────────────────────────────────
async function loadPayments() {{
  try {{
    const d = await apiFetch('/api/v1/advertisers/' + ADV_ID + '/transactions');
    const tbody = document.getElementById('paymentsBody');
    if (!d.transactions || d.transactions.length === 0) {{
      tbody.innerHTML = '<tr><td class="empty" colspan="5">No transactions yet. Deposit funds to get started.</td></tr>';
      return;
    }}
    tbody.innerHTML = d.transactions.map(function(t) {{
      var isDeposit = t.transaction_type === 'deposit' || t.transaction_type === 'bonus';
      var amt = isDeposit ? '+' : '';
      amt += fmtCurrency(t.amount);
      return '<tr>' +
        '<td>' + fmtDate(t.created_at) + '</td>' +
        '<td>' + _esc(t.transaction_type) + '</td>' +
        '<td class="num" style="color:' + (isDeposit ? 'var(--teal)' : 'var(--red)') + '">' + amt + '</td>' +
        '<td class="num">' + fmtCurrency(t.balance_after) + '</td>' +
        '<td>' + _esc(t.description || '--') + '</td>' +
      '</tr>';
    }}).join('');
  }} catch (e) {{
    document.getElementById('paymentsBody').innerHTML = '<tr><td class="empty" colspan="5">Failed to load</td></tr>';
  }}
}}

function showDepositModal() {{
  document.getElementById('depositModal').classList.add('show');
  var wallet = document.getElementById('vaultWalletDisplay');
  var hw = localStorage.getItem('empire_vault_wallet');
  if (hw) {{
    wallet.textContent = hw;
  }} else {{
    wallet.textContent = 'Loading wallet address...';
  }}
}}
function hideDepositModal() {{
  document.getElementById('depositModal').classList.remove('show');
}}

// ── Tab Switching ──────────────────────────────────────────────
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(function(t) {{ t.classList.remove('active'); }});
  document.querySelectorAll('.tab-content').forEach(function(t) {{ t.classList.remove('active'); }});
  var tabs = document.querySelectorAll('.tab');
  var tabMap = {{ 'overview': 0, 'campaigns': 1, 'creatives': 2, 'payments': 3 }};
  if (tabMap[name] !== undefined && tabs[tabMap[name]]) {{
    tabs[tabMap[name]].classList.add('active');
  }}
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'campaigns') loadCampaigns();
  if (name === 'creatives') loadCreatives();
  if (name === 'payments') loadPayments();
}}

loadStats();
loadCampaigns();
</script>
</body></html>"""


# ── ROUTES ───────────────────────────────────────────────────────────
def register_advertiser_routes(
    app: FastAPI,
    *,
    sign_token: Callable,
    verify_token: Callable,
    send_email: Callable,
    public_base_url: str,
):
    """Register advertiser portal routes."""

    # ── PUBLIC: SIGNUP PAGE ───────────────────────────────────────────
    @app.get("/advertisers/signup", response_class=HTMLResponse)
    async def adv_signup_page():
        return HTMLResponse(_ADV_SIGNUP_PAGE)

    # ── PUBLIC: LOGIN PAGE ────────────────────────────────────────────
    @app.get("/advertisers/login", response_class=HTMLResponse)
    async def adv_login_page():
        return HTMLResponse(_ADV_LOGIN_PAGE)

    # ── PUBLIC: CREATE ACCOUNT ────────────────────────────────────────
    @app.post("/api/v1/advertisers/signup")
    async def adv_signup(request: Request):
        """Create a new advertiser account."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        company_name = (body.get("company_name") or "").strip()
        contact_name = (body.get("contact_name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        phone = (body.get("phone") or "").strip()
        website = (body.get("website") or "").strip()

        if not company_name:
            raise HTTPException(400, "Company name is required")
        if not contact_name:
            raise HTTPException(400, "Contact name is required")
        if not email or "@" not in email:
            raise HTTPException(400, "Valid email is required")

        # Check for existing
        try:
            existing = _SB.table("advertisers").select("id").eq("email", email).limit(1).execute()
            if existing.data:
                raise HTTPException(409, "An account with that email already exists. Please sign in.")
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[advertiser] lookup error: {e}")
            if "does not exist" in str(e):
                raise HTTPException(503, "Advertiser system is being set up. Try again shortly.")
            raise HTTPException(500, "Service error")

        try:
            ins = _SB.table("advertisers").insert({
                "company_name": company_name,
                "contact_name": contact_name,
                "email": email,
                "phone": phone,
                "website": website,
                "balance": 0.00,
                "is_active": True,
                "status": "active",
            }).execute()
            advertiser = ins.data[0]
            adv_id = str(advertiser["id"])
        except Exception as e:
            log.error(f"[advertiser] insert error: {e}")
            raise HTTPException(500, "Could not create advertiser account")

        log.info(f"[advertiser] new signup: {company_name} <{email}> -> {adv_id}")

        # Send welcome + magic link email
        payload = {
            "advertiser_id": adv_id,
            "email": email,
            "exp": int(time.time()) + LOGIN_LINK_TTL_SECONDS,
            "iat": int(time.time()),
            "kind": "advertiser_login",
        }
        token = sign_token(payload)
        link = f"{public_base_url.rstrip('/')}/advertisers/{adv_id}/verify?t={token}"

        html = f"""
          <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
            <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
              <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Advertiser Network</div>
              <div style="font-size:20px;font-weight:700;color:#44E5B8;margin-top:6px;">Welcome to the Ad Network!</div>
            </div>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              Hi {contact_name}, your advertiser account for <strong>{company_name}</strong> is ready.<br><br>
              Sign in to create your first campaign and reach our publisher network.
            </p>
            <div style="margin:28px 0;text-align:center;">
              <a href="{link}" style="display:inline-block;background:#44E5B8;color:#000;padding:12px 28px;text-decoration:none;font-weight:700;letter-spacing:.04em;">Sign in &rarr;</a>
            </div>
            <div style="font-size:11px;color:#52525b;line-height:1.7;">
              This link expires in 10 minutes.
            </div>
          </div>
        """
        try:
            result = await send_email(
                to=email,
                subject="Empire AI · Your advertiser account is ready",
                html=html,
            )
            if not result.get("ok"):
                log.error(f"[advertiser] welcome email failed: {result.get('error', 'unknown')}")
        except Exception as e:
            log.error(f"[advertiser] welcome email error: {e}")

        return {"ok": True, "advertiser_id": adv_id, "message": "Account created. Check your email for the login link."}

    # ── PUBLIC: SEND MAGIC LINK ───────────────────────────────────────
    @app.post("/api/v1/advertisers/login")
    async def adv_send_link(request: Request):
        """Send magic link to advertiser email."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        email = (body.get("email") or "").lower().strip()
        if not email or "@" not in email:
            raise HTTPException(400, "Valid email required")

        try:
            res = _SB.table("advertisers").select("id, company_name, contact_name, email, is_active, status") \
                .eq("email", email).limit(1).execute()
            if not res.data or not res.data[0].get("is_active"):
                log.info(f"[advertiser] login attempt for unknown/inactive: {email}")
                return {"ok": True}
            advertiser = res.data[0]
        except Exception as e:
            log.error(f"[advertiser] DB lookup failed: {e}")
            return {"ok": False, "error": "Service error"}

        payload = {
            "advertiser_id": str(advertiser["id"]),
            "email": email,
            "exp": int(time.time()) + LOGIN_LINK_TTL_SECONDS,
            "iat": int(time.time()),
            "kind": "advertiser_login",
        }
        token = sign_token(payload)
        link = f"{public_base_url.rstrip('/')}/advertisers/{advertiser['id']}/verify?t={token}"

        name = advertiser.get("company_name") or advertiser.get("contact_name", "")
        html = f"""
          <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
            <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
              <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Advertiser Portal</div>
              <div style="font-size:20px;font-weight:700;color:#44E5B8;margin-top:6px;">Your login link</div>
            </div>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              Hi {name}, click below to sign in to your advertiser dashboard.
              This link expires in 10 minutes.
            </p>
            <div style="margin:28px 0;text-align:center;">
              <a href="{link}" style="display:inline-block;background:#44E5B8;color:#000;padding:12px 28px;text-decoration:none;font-weight:700;letter-spacing:.04em;">Sign in &rarr;</a>
            </div>
            <div style="font-size:11px;color:#52525b;line-height:1.7;">
              If you didn't request this, ignore the email.
            </div>
          </div>
        """
        try:
            result = await send_email(
                to=email,
                subject="Empire AI · Your advertiser login link",
                html=html,
            )
            if not result.get("ok"):
                log.error(f"[advertiser] email send failed: {result.get('error', 'unknown')}")
                return {"ok": False, "error": "Could not send login email"}
            return {"ok": True}
        except Exception as e:
            log.error(f"[advertiser] email send error: {e}")
            return {"ok": False, "error": "Could not send login email"}

    # ── PUBLIC: VERIFY MAGIC LINK ─────────────────────────────────────
    @app.get("/advertisers/{advertiser_id}/verify", response_class=HTMLResponse)
    async def adv_verify(request: Request, advertiser_id: str, t: str = Query(...)):
        """Verify magic link token. Sets session cookie and redirects to dashboard."""
        decoded = verify_token(t)
        if not decoded or decoded.get("kind") != "advertiser_login":
            return HTMLResponse("""
                <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                <div style="text-align:center;"><h1 style="font-weight:200;">Link invalid</h1>
                <p style="color:#7a8ca3;">This link has expired or is invalid.</p>
                <a href="/advertisers/login" style="color:#44e5b8;margin-top:16px;display:inline-block;">Request a new one →</a></div></body></html>
            """, status_code=401)

        if str(decoded.get("advertiser_id", "")) != advertiser_id:
            return HTMLResponse("<h1>Invalid link</h1>", status_code=401)

        try:
            res = _SB.table("advertisers").select("*") \
                .eq("id", advertiser_id).limit(1).execute()
            if not res.data or not res.data[0].get("is_active"):
                return HTMLResponse("""
                    <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                    <div><h1 style="font-weight:200;">Account inactive</h1>
                    <p style="color:#7a8ca3;">Contact support to reactivate your account.</p></div></body></html>
                """, status_code=403)
            advertiser = res.data[0]
        except Exception as e:
            log.error(f"[advertiser] verify lookup failed: {e}")
            return HTMLResponse("<h1>Service error</h1>", status_code=500)

        # Create session
        session_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        _ADV_SESSION_HASHES[token_hash] = {
            "advertiser": {
                "id": str(advertiser["id"]),
                "company_name": advertiser["company_name"],
                "contact_name": advertiser.get("contact_name", ""),
                "email": advertiser["email"],
                "balance": float(advertiser.get("balance", 0) or 0),
                "website": advertiser.get("website", ""),
            },
            "expires_at": expires_at,
        }

        response = RedirectResponse(
            url=f"/advertisers/{advertiser_id}/dashboard",
            status_code=302,
        )
        use_secure = public_base_url.startswith("https://")
        response.set_cookie(
            key="advertiser_session",
            value=session_token,
            max_age=int(SESSION_TTL_HOURS * 3600),
            httponly=True,
            secure=use_secure,
            samesite="lax",
            path="/",
        )
        log.info(f"[advertiser] verified: {advertiser['company_name']} ({advertiser['email']})")
        return response

    # ── PUBLIC: DASHBOARD ─────────────────────────────────────────────
    @app.get("/advertisers/{advertiser_id}/dashboard", response_class=HTMLResponse)
    async def adv_dashboard(advertiser_id: str, request: Request):
        """Render the advertiser dashboard page."""
        advertiser = _resolve_advertiser(request)
        if not advertiser or str(advertiser.get("id", "")) != advertiser_id:
            return HTMLResponse("""
                <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                <div style="text-align:center;"><h1 style="font-weight:200;">Sign in required</h1>
                <p style="color:#7a8ca3;">Please sign in to view your dashboard.</p>
                <a href="/advertisers/login" style="color:#44e5b8;margin-top:16px;display:inline-block;">Sign in →</a></div></body></html>
            """, status_code=401)

        # Refresh balance from DB
        try:
            refresh = _SB.table("advertisers").select("balance") \
                .eq("id", advertiser_id).limit(1).execute()
            if refresh.data:
                advertiser["balance"] = float(refresh.data[0].get("balance", 0) or 0)
        except Exception:
            pass

        return HTMLResponse(_advertiser_dashboard(advertiser, base_url=public_base_url))

    # ── PUBLIC: LOGOUT ────────────────────────────────────────────────
    @app.get("/advertisers/logout")
    async def adv_logout(request: Request):
        """Clear session cookie."""
        token = request.cookies.get("advertiser_session", "")
        if token:
            th = _hash_token(token)
            _ADV_SESSION_HASHES.pop(th, None)
        response = RedirectResponse(url="/advertisers/login", status_code=302)
        response.delete_cookie("advertiser_session", path="/")
        return response

    # ── API: STATS ────────────────────────────────────────────────────
    @app.get("/api/v1/advertisers/{advertiser_id}/stats")
    async def adv_stats(advertiser_id: str, request: Request):
        """Return aggregate stats for an advertiser."""
        advertiser = _resolve_advertiser(request)
        if not advertiser or str(advertiser.get("id", "")) != advertiser_id:
            raise HTTPException(401, "Authentication required")

        try:
            # Get advertiser campaigns
            campaigns_res = _SB.table("ad_campaigns").select("*") \
                .eq("advertiser_id", advertiser_id).execute()
            campaigns = campaigns_res.data or []

            total_spend = 0.0
            daily_budget_used = 0.0
            active_campaigns = 0
            campaign_ids = []

            for c in campaigns:
                total_spend += float(c.get("spent_total", 0) or 0)
                daily_budget_used += float(c.get("spent_today", 0) or 0)
                if c.get("status") == "active":
                    active_campaigns += 1
                campaign_ids.append(str(c["id"]))

            total_impressions = 0
            total_clicks = 0

            if campaign_ids:
                # Get impressions
                imp = _SB.table("ad_impressions").select("id") \
                    .in_("campaign_id", campaign_ids).execute()
                total_impressions = len(imp.data or [])

                # Get clicks
                clk = _SB.table("ad_clicks").select("id") \
                    .in_("campaign_id", campaign_ids).execute()
                total_clicks = len(clk.data or [])

            ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0.0

            return {
                "total_campaigns": len(campaigns),
                "active_campaigns": active_campaigns,
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "ctr": round(ctr, 2),
                "total_spend": round(total_spend, 2),
                "daily_budget_used": round(daily_budget_used, 2),
                "balance": advertiser.get("balance", 0),
            }
        except Exception as e:
            log.error(f"[advertiser] stats error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: CAMPAIGNS LIST ──────────────────────────────────────────
    @app.get("/api/v1/advertisers/{advertiser_id}/campaigns")
    async def adv_campaigns_list(advertiser_id: str, request: Request):
        """Return all campaigns for an advertiser."""
        advertiser = _resolve_advertiser(request)
        if not advertiser or str(advertiser.get("id", "")) != advertiser_id:
            raise HTTPException(401, "Authentication required")

        try:
            campaigns_res = _SB.table("ad_campaigns").select("*") \
                .eq("advertiser_id", advertiser_id) \
                .order("created_at", desc=True) \
                .execute()

            result = []
            for c in (campaigns_res.data or []):
                # Get creative stats for this campaign
                cr = _SB.table("ad_creatives").select("impressions, clicks") \
                    .eq("campaign_id", str(c["id"])).execute()
                imp = sum(int(cr2.get("impressions", 0) or 0) for cr2 in (cr.data or []))
                clk = sum(int(cr2.get("clicks", 0) or 0) for cr2 in (cr.data or []))

                result.append({
                    "id": str(c["id"]),
                    "name": c.get("name", ""),
                    "niche": c.get("niche", ""),
                    "status": c.get("status", "paused"),
                    "daily_budget": float(c.get("daily_budget", 0) or 0),
                    "spent_today": float(c.get("spent_today", 0) or 0),
                    "spent_total": float(c.get("spent_total", 0) or 0),
                    "target_url": c.get("target_url", ""),
                    "target_metros": c.get("target_metros", []),
                    "impressions": imp,
                    "clicks": clk,
                    "created_at": str(c.get("created_at", "")),
                })

            return {"campaigns": result, "total": len(result)}
        except Exception as e:
            log.error(f"[advertiser] campaigns list error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: CREATE CAMPAIGN ──────────────────────────────────────────
    @app.post("/api/v1/advertisers/{advertiser_id}/campaigns")
    async def adv_create_campaign(advertiser_id: str, request: Request):
        """Create a new campaign with an optional first creative."""
        advertiser = _resolve_advertiser(request)
        if not advertiser or str(advertiser.get("id", "")) != advertiser_id:
            raise HTTPException(401, "Authentication required")

        try:
            body = await request.json()
        except Exception:
            body = {}

        name = (body.get("name") or "").strip()
        niche = (body.get("niche") or "").strip()
        daily_budget = float(body.get("daily_budget", 50))
        target_url = (body.get("target_url") or "").strip()
        target_metros = body.get("target_metros", [])
        creative_data = body.get("creative", {})

        if not name:
            raise HTTPException(400, "Campaign name is required")
        if not niche:
            raise HTTPException(400, "Niche is required")

        # Create campaign
        try:
            payload = {
                "name": name,
                "advertiser_id": advertiser_id,
                "niche": niche,
                "daily_budget": daily_budget,
                "target_url": target_url,
                "target_metros": target_metros,
                "status": "active",
                "spent_today": 0.00,
                "spent_total": 0.00,
            }
            ins = _SB.table("ad_campaigns").insert(payload).execute()
            campaign = ins.data[0]
            campaign_id = str(campaign["id"])
        except Exception as e:
            log.error(f"[advertiser] create campaign error: {e}")
            raise HTTPException(500, str(e)[:200])

        # Create first creative if provided
        creative_created = False
        if creative_data and isinstance(creative_data, dict):
            headline = (creative_data.get("headline") or "").strip()[:80]
            ad_body = (creative_data.get("body") or "").strip()[:200]
            cta_text = (creative_data.get("cta_text") or "Learn More").strip()[:40]
            dest_url = (creative_data.get("destination_url") or target_url or "").strip()

            if headline and ad_body:
                try:
                    _SB.table("ad_creatives").insert({
                        "campaign_id": campaign_id,
                        "headline": headline,
                        "body": ad_body,
                        "cta_text": cta_text,
                        "destination_url": dest_url,
                        "ad_size": "300x250",
                        "ad_format": "native",
                        "status": "active",
                    }).execute()
                    creative_created = True
                except Exception as e:
                    log.warning(f"[advertiser] creative creation failed for campaign {campaign_id}: {e}")

        log.info(f"[advertiser] campaign created: {campaign_id} ({name}) for {advertiser_id}")
        return {"ok": True, "campaign_id": campaign_id, "name": name, "creative_created": creative_created}

    # ── API: TOGGLE CAMPAIGN ─────────────────────────────────────────
    @app.post("/api/v1/advertisers/campaigns/{campaign_id}/toggle")
    async def adv_toggle_campaign(campaign_id: str, request: Request):
        """Pause or activate a campaign."""
        adv = _resolve_advertiser(request)
        if not adv:
            raise HTTPException(401, "Authentication required")

        try:
            body = await request.json()
        except Exception:
            body = {}

        new_status = (body.get("status") or "").strip()
        if new_status not in ("active", "paused", "ended", "archived"):
            raise HTTPException(400, "Invalid status")

        # Verify ownership
        try:
            camp = _SB.table("ad_campaigns").select("advertiser_id") \
                .eq("id", campaign_id).limit(1).execute()
            if not camp.data:
                raise HTTPException(404, "Campaign not found")
            if str(camp.data[0].get("advertiser_id", "")) != str(adv.get("id", "")):
                raise HTTPException(403, "Not your campaign")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e)[:80])

        try:
            _SB.table("ad_campaigns").update({"status": new_status}) \
                .eq("id", campaign_id).execute()
            return {"ok": True, "campaign_id": campaign_id, "status": new_status}
        except Exception as e:
            raise HTTPException(500, str(e)[:80])

    # ── API: CREATIVES LIST ──────────────────────────────────────────
    @app.get("/api/v1/advertisers/{advertiser_id}/creatives")
    async def adv_creatives_list(advertiser_id: str, request: Request):
        """Return all creatives across an advertiser's campaigns."""
        advertiser = _resolve_advertiser(request)
        if not advertiser or str(advertiser.get("id", "")) != advertiser_id:
            raise HTTPException(401, "Authentication required")

        try:
            # Get advertiser's campaign IDs
            campaigns_res = _SB.table("ad_campaigns").select("id, name") \
                .eq("advertiser_id", advertiser_id).execute()
            campaign_ids = [str(c["id"]) for c in (campaigns_res.data or [])]
            campaign_map = {str(c["id"]): c.get("name", "") for c in (campaigns_res.data or [])}

            if not campaign_ids:
                return {"creatives": [], "total": 0}

            creatives_res = _SB.table("ad_creatives").select("*") \
                .in_("campaign_id", campaign_ids) \
                .order("created_at", desc=True) \
                .execute()

            result = []
            for cr in (creatives_res.data or []):
                result.append({
                    "id": str(cr["id"]),
                    "campaign_id": str(cr["campaign_id"]),
                    "campaign_name": campaign_map.get(str(cr["campaign_id"]), ""),
                    "headline": cr.get("headline", ""),
                    "body": cr.get("body", ""),
                    "cta_text": cr.get("cta_text", "Learn More"),
                    "destination_url": cr.get("destination_url", ""),
                    "ad_size": cr.get("ad_size", "300x250"),
                    "ad_format": cr.get("ad_format", "native"),
                    "status": cr.get("status", "paused"),
                    "impressions": cr.get("impressions", 0),
                    "clicks": cr.get("clicks", 0),
                    "created_at": str(cr.get("created_at", "")),
                })

            return {"creatives": result, "total": len(result)}
        except Exception as e:
            log.error(f"[advertiser] creatives list error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: CREATE CREATIVE ─────────────────────────────────────────
    @app.post("/api/v1/advertisers/{advertiser_id}/creatives")
    async def adv_create_creative(advertiser_id: str, request: Request):
        """Create a new creative under a campaign."""
        advertiser = _resolve_advertiser(request)
        if not advertiser or str(advertiser.get("id", "")) != advertiser_id:
            raise HTTPException(401, "Authentication required")

        try:
            body = await request.json()
        except Exception:
            body = {}

        campaign_id = (body.get("campaign_id") or "").strip()
        headline = (body.get("headline") or "").strip()[:80]
        ad_body = (body.get("body") or "").strip()[:200]
        cta_text = (body.get("cta_text") or "Learn More").strip()[:40]
        dest_url = (body.get("destination_url") or "").strip()
        ad_size = body.get("ad_size", "300x250")

        if not campaign_id:
            raise HTTPException(400, "campaign_id is required")
        if not headline or not ad_body:
            raise HTTPException(400, "headline and body are required")

        # Verify campaign ownership
        try:
            camp = _SB.table("ad_campaigns").select("advertiser_id, target_url") \
                .eq("id", campaign_id).limit(1).execute()
            if not camp.data:
                raise HTTPException(404, "Campaign not found")
            if str(camp.data[0].get("advertiser_id", "")) != advertiser_id:
                raise HTTPException(403, "Not your campaign")

            if not dest_url:
                dest_url = camp.data[0].get("target_url", "")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e)[:80])

        try:
            ins = _SB.table("ad_creatives").insert({
                "campaign_id": campaign_id,
                "headline": headline,
                "body": ad_body,
                "cta_text": cta_text,
                "destination_url": dest_url,
                "ad_size": ad_size,
                "ad_format": "native",
                "status": "active",
            }).execute()
            return {"ok": True, "creative": ins.data[0]}
        except Exception as e:
            raise HTTPException(500, str(e)[:200])

    # ── API: UPDATE CREATIVE ─────────────────────────────────────────
    @app.patch("/api/v1/advertisers/creatives/{creative_id}")
    async def adv_update_creative(creative_id: str, request: Request):
        """Update a creative (e.g., pause/activate)."""
        adv = _resolve_advertiser(request)
        if not adv:
            raise HTTPException(401, "Authentication required")

        try:
            body = await request.json()
        except Exception:
            body = {}

        updates = {}
        for key in ("headline", "body", "cta_text", "destination_url", "ad_size", "status"):
            if key in body:
                updates[key] = body[key]

        if not updates:
            raise HTTPException(400, "No updates provided")

        # Verify ownership via campaign
        try:
            cr = _SB.table("ad_creatives").select("campaign_id") \
                .eq("id", creative_id).limit(1).execute()
            if not cr.data:
                raise HTTPException(404, "Creative not found")
            camp = _SB.table("ad_campaigns").select("advertiser_id") \
                .eq("id", str(cr.data[0]["campaign_id"])).limit(1).execute()
            if not camp.data or str(camp.data[0].get("advertiser_id", "")) != str(adv.get("id", "")):
                raise HTTPException(403, "Not your creative")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e)[:80])

        try:
            _SB.table("ad_creatives").update(updates).eq("id", creative_id).execute()
            return {"ok": True, "creative_id": creative_id}
        except Exception as e:
            raise HTTPException(500, str(e)[:80])

    # ── API: TRANSACTIONS ────────────────────────────────────────────
    @app.get("/api/v1/advertisers/{advertiser_id}/transactions")
    async def adv_transactions(advertiser_id: str, request: Request, limit: int = Query(50, ge=1, le=200)):
        """Return transaction history for an advertiser."""
        advertiser = _resolve_advertiser(request)
        if not advertiser or str(advertiser.get("id", "")) != advertiser_id:
            raise HTTPException(401, "Authentication required")

        try:
            tx_res = _SB.table("advertiser_transactions").select("*") \
                .eq("advertiser_id", advertiser_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()

            return {"transactions": tx_res.data or [], "total": len(tx_res.data or [])}
        except Exception as e:
            log.error(f"[advertiser] transactions error: {e}")
            return {"transactions": [], "total": 0}

    # ── API: BALANCE ─────────────────────────────────────────────────
    @app.get("/api/v1/advertisers/{advertiser_id}/balance")
    async def adv_balance(advertiser_id: str, request: Request):
        """Return current balance."""
        advertiser = _resolve_advertiser(request)
        if not advertiser or str(advertiser.get("id", "")) != advertiser_id:
            raise HTTPException(401, "Authentication required")

        try:
            res = _SB.table("advertisers").select("balance") \
                .eq("id", advertiser_id).limit(1).execute()
            balance = float(res.data[0].get("balance", 0)) if res.data else 0.0
            return {"balance": balance, "advertiser_id": advertiser_id}
        except Exception as e:
            log.error(f"[advertiser] balance error: {e}")
            raise HTTPException(500, str(e)[:80])

    log.info("[advertiser] Routes registered — /advertisers/{signup,login,verify,dashboard} + /api/v1/advertisers/{stats,campaigns,creatives,transactions,balance}")
