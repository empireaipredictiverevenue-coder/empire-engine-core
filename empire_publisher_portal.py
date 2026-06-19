"""
EMPIRE V49 · PUBLISHER PORTAL
==============================
Self-serve ad network publisher accounts. Publishers sign up, get an
API key + embed snippet, and track their earnings.

ENDPOINTS
─────────
  GET  /publishers/signup                              → public signup form
  POST /api/v1/publishers/signup                       → create publisher account
  GET  /publishers/login                               → public login form
  POST /api/v1/publishers/login                        → send magic link email
  GET  /publishers/{id}/verify?t=...                   → verify token, set cookie, redirect
  GET  /publishers/{id}/dashboard                      → main publisher dashboard
  GET  /publishers/{id}/embed                          → embed code generation page
  GET  /api/v1/publishers/{id}/stats                   → aggregate stats JSON
  GET  /api/v1/publishers/{id}/slots                   → list ad slots JSON
  POST /api/v1/publishers/{id}/slots                   → create a new ad slot
  GET  /api/v1/publishers/{id}/payouts                 → payout history JSON
  GET  /api/v1/publishers/{id}/embed-code              → raw embed snippet JSON
  POST /api/v1/publishers/{id}/api-key/regenerate      → generate new API key
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

log = logging.getLogger("empire.publisher")

# ── CONFIG ───────────────────────────────────────────────────────────
_SB = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", ""),
)

LOGIN_LINK_TTL_SECONDS = 600  # 10 min
SESSION_TTL_HOURS = 24

# In-memory session store (same pattern as affiliate portal)
_PUB_SESSION_HASHES: dict[str, dict] = {}


# ── HELPERS ──────────────────────────────────────────────────────────
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _verify_session(token: str) -> Optional[dict]:
    th = _hash_token(token)
    sess = _PUB_SESSION_HASHES.get(th)
    if not sess:
        return None
    if datetime.now(timezone.utc) > sess["expires_at"]:
        del _PUB_SESSION_HASHES[th]
        return None
    return sess.get("publisher")


def _resolve_publisher(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        pub = _verify_session(auth[7:])
        if pub:
            return pub
    token = request.cookies.get("publisher_session", "")
    if token:
        pub = _verify_session(token)
        if pub:
            return pub
    return None


def _generate_embed_code(publisher_id: str, slot_name: str, base_url: str) -> str:
    """Generate the publisher embed snippet for a specific slot."""
    escaped_slot = slot_name.replace("'", "\\'")
    return f"""<!-- Empire AI · Native Ad Embed -->
<div id="empire-ad-{escaped_slot}"></div>
<script>
(function() {{
  var slot = '{escaped_slot}';
  var visitor = localStorage.getItem('empire_visitor_id') || 'v_' + Math.random().toString(36).slice(2, 10);
  localStorage.setItem('empire_visitor_id', visitor);

  fetch('{base_url.rstrip("/")}/api/v1/ads/serve?slot=' + encodeURIComponent(slot) + '&visitor_id=' + visitor)
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (!data.ok || !data.ad) return;
      var ad = data.ad;
      var el = document.getElementById('empire-ad-' + slot);
      if (!el) return;
      var w = (ad.ad_size || '300x250').split('x')[0];
      var html = '<div style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;background:#fff;max-width:' + w + 'px;">';
      if (ad.image_url) {{
        html += '<a href="#" onclick="return empireAdClick(' + "'" + ad.impression_id + "','" + ad.creative_id + "','" + ad.campaign_id + "','" + visitor + "'" + ')" style="display:block;">';
        html += '<img src="' + ad.image_url + '" alt="" style="width:100%;display:block;">';
        html += '</a>';
      }}
      html += '<div style="padding:12px;">';
      html += '<div style="font-size:14px;font-weight:600;color:#1a202c;margin-bottom:4px;">' + ad.headline + '</div>';
      html += '<div style="font-size:12px;color:#718096;margin-bottom:10px;">' + ad.body + '</div>';
      html += '<a href="#" onclick="return empireAdClick(' + "'" + ad.impression_id + "','" + ad.creative_id + "','" + ad.campaign_id + "','" + visitor + "'" + ')" style="display:inline-block;background:#4FD1C5;color:#fff;padding:6px 14px;border-radius:4px;font-size:12px;font-weight:600;text-decoration:none;">' + ad.cta_text + '</a>';
      html += '</div></div>';
      el.innerHTML = html;
    }})
    .catch(function() {{}});

  window.empireAdClick = function(impressionId, creativeId, campaignId, visitorId) {{
    fetch('{base_url.rstrip("/")}/api/v1/ads/click/redirect', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        impression_id: impressionId,
        creative_id: creativeId,
        campaign_id: campaignId,
        visitor_id: visitorId
      }})
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.destination) {{ window.location.href = data.destination; }}
    }});
    return false;
  }};
}})();
</script>"""


# ── CSS ──────────────────────────────────────────────────────────────
_PUB_CSS = """
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
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--divider); margin-bottom: 16px; }
.tab {
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  padding: 8px 16px; cursor: pointer; border: none; background: transparent;
  color: var(--fg3); border-bottom: 2px solid transparent; transition: all 0.2s;
}
.tab:hover { color: var(--fg2); }
.tab.active { color: var(--teal); border-bottom-color: var(--teal); }
.tab-content { display: none; }
.tab-content.active { display: block; }
.copy-box {
  background: rgba(0,0,0,0.3); border: 1px solid var(--divider);
  padding: 16px; font-family: var(--mono); font-size: 10px; line-height: 1.6;
  color: var(--fg2); white-space: pre-wrap; word-break: break-all;
  max-height: 300px; overflow-y: auto; margin-bottom: 12px;
  position: relative;
}
.copy-btn {
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em;
  text-transform: uppercase; background: var(--teal); color: #000;
  border: none; padding: 8px 16px; cursor: pointer; transition: all 0.2s;
}
.copy-btn:hover { background: transparent; color: var(--teal); outline: 1px solid var(--teal); }
.slot-form { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; margin-bottom: 16px; align-items: end; }
.slot-form .field { margin-bottom: 0; }
.slot-form .field label { display: block; font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 4px; }
.slot-form input {
  width: 100%; background: rgba(0,0,0,0.4); color: var(--fg);
  border: 1px solid var(--divider); font-family: var(--mono); font-size: 12px;
  padding: 8px 10px; outline: none; transition: border-color 0.2s;
}
.slot-form input:focus { border-color: var(--teal); }
.slot-form button {
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  background: var(--teal); color: #000; border: none; padding: 8px 16px; cursor: pointer;
  white-space: nowrap;
}
.slot-form button:hover { background: transparent; color: var(--teal); outline: 1px solid var(--teal); }
.api-key-row { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; }
.api-key-row code { background: rgba(0,0,0,0.3); padding: 8px 12px; font-family: var(--mono); font-size: 11px; color: var(--teal); flex: 1; word-break: break-all; }
.api-key-row .regenerate { font-family: var(--mono); font-size: 9px; color: var(--amber); cursor: pointer; text-decoration: underline; }
.api-key-row .regenerate:hover { color: var(--fg2); }
.block-label { font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 6px; }
.btn { font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase; padding: 8px 16px; cursor: pointer; border: none; transition: all 0.2s; }
.btn-teal { background: var(--teal); color: #000; }
.btn-teal:hover { background: transparent; color: var(--teal); outline: 1px solid var(--teal); }
.cta-link { display: inline-block; font-family: var(--mono); font-size: 9px; color: var(--cyan); text-decoration: none; margin-top: 4px; }
.cta-link:hover { text-decoration: underline; }
"""


# ── SIGNUP FORM PAGE ─────────────────────────────────────────────────
_PUB_SIGNUP_CSS = """
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
.field input { width: 100%; background: rgba(0,0,0,0.4); color: #f8fafd; border: 1px solid rgba(122,140,163,0.18); font-family: 'JetBrains Mono', monospace; font-size: 13px; padding: 12px 14px; outline: none; transition: border-color 0.2s; }
.field input:focus { border-color: #44e5b8; }
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

_PUB_SIGNUP_PAGE = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Publisher Signup</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{_PUB_SIGNUP_CSS}</style>
</head><body>
<div class="box">
  <div class="brand"><span class="brand-e">EMPIRE</span><span class="brand-ai">AI</span></div>
  <div class="brand-sub">Publisher Network · Ad Revenue</div>
  <h1>Become a <em>Publisher</em></h1>
  <p class="lead">Join our ad network and earn revenue by displaying native ads on your website. Sign up in 60 seconds.</p>
  <form id="signupForm" onsubmit="return submitForm(event)">
    <div class="row2">
      <div class="field">
        <label>Business name</label>
        <input type="text" id="name" placeholder="Your Company, LLC" required>
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
        <label>Website</label>
        <input type="url" id="website" placeholder="https://yourcompany.com">
      </div>
    </div>
    <button type="submit" class="btn" id="submitBtn">Create publisher account →</button>
  </form>
  <div id="flash" class="flash"></div>
  <div class="login-link">Already a publisher? <a href="/publishers/login">Sign in →</a></div>
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
    const r = await fetch('/api/v1/publishers/signup', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        name: document.getElementById('name').value.trim(),
        contact_name: document.getElementById('contact_name').value.trim(),
        email: document.getElementById('email').value.trim(),
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
    btn.disabled = false; btn.textContent = 'Create publisher account →';
  }}
}}
</script>
</body></html>"""


# ── LOGIN PAGE ───────────────────────────────────────────────────────
_PUB_LOGIN_PAGE = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Publisher Login</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{_PUB_SIGNUP_CSS}</style>
</head><body>
<div class="box">
  <div class="brand"><span class="brand-e">EMPIRE</span><span class="brand-ai">AI</span></div>
  <div class="brand-sub">Publisher Portal</div>
  <h1>Publisher <em>Login</em></h1>
  <p class="lead">Enter your email and we'll send a one-time sign-in link.</p>
  <div class="field">
    <label>Email</label>
    <input type="email" id="email" placeholder="jane@yourcompany.com" autofocus>
  </div>
  <button class="btn" id="btn" onclick="send()">Send login link</button>
  <div id="flash" class="flash"></div>
  <div class="login-link">New publisher? <a href="/publishers/signup">Sign up →</a></div>
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
    const r = await fetch('/api/v1/publishers/login', {{
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
def _publisher_dashboard(publisher: dict, base_url: str = "http://localhost:8001") -> str:
    pub_id = publisher.get("id", "")
    pub_name = publisher.get("name", "Publisher")
    api_key = publisher.get("api_key", "")
    pid_json = json.dumps(pub_id)
    base_json = json.dumps(base_url)
    html = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Publisher Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>__PUB_CSS__</style>
</head><body>
<div class="header">
  <div class="header-brand"><span class="e">EMPIRE</span><span class="ai">AI</span></div>
  <h1>Publisher <em>Dashboard</em></h1>
  <div class="header-right">
    <span class="name">__PUB_NAME__</span>
    <a href="/publishers/logout" class="logout">Sign out</a>
  </div>
</div>
<div class="container">
  <div class="greeting">
    <h2>Welcome, <em>__PUB_NAME__</em></h2>
    <div class="sub">Publisher Portal · Ad Revenue Network</div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('overview')">Overview</button>
    <button class="tab" onclick="switchTab('slots')">Ad Slots</button>
    <button class="tab" onclick="switchTab('embed')">Embed Code</button>
    <button class="tab" onclick="switchTab('payouts')">Payouts</button>
  </div>

  <div id="tab-overview" class="tab-content active">
    <div class="grid" id="statsGrid">
      <div class="card"><div class="card-label">Impressions</div><div class="card-value teal" id="stat-impressions">--</div></div>
      <div class="card"><div class="card-label">Clicks</div><div class="card-value cyan" id="stat-clicks">--</div></div>
      <div class="card"><div class="card-label">CTR</div><div class="card-value" id="stat-ctr">--</div></div>
      <div class="card"><div class="card-label">Revenue (est.)</div><div class="card-value teal" id="stat-revenue">--</div></div>
      <div class="card"><div class="card-label">Active Slots</div><div class="card-value" id="stat-slots">--</div></div>
      <div class="card"><div class="card-label">Rev Share</div><div class="card-value" id="stat-revshare">--</div></div>
    </div>
    <div class="section">
      <div class="section-title"><strong>Quick Links</strong></div>
      <a href="/publishers/__PUB_ID__/embed" class="cta-link" style="margin-right:16px;">Get embed code &rarr;</a>
      <a href="/publishers/login" class="cta-link">Visit portal &rarr;</a>
    </div>
  </div>

  <div id="tab-slots" class="tab-content">
    <div class="section-title"><strong>Your Ad Slots</strong></div>
    <div class="slot-form">
      <div class="field">
        <label>Slot name</label>
        <input type="text" id="newSlotName" placeholder="e.g. sidebar-top, content-mid">
      </div>
      <div class="field">
        <label>Ad size</label>
        <input type="text" id="newSlotSize" placeholder="300x250" value="300x250">
      </div>
      <button onclick="createSlot()">Create Slot</button>
    </div>
    <table>
      <thead><tr><th>Slot Name</th><th>Size</th><th>Status</th><th>Impressions</th><th>Clicks</th><th>CTR</th><th>Embed</th></tr></thead>
      <tbody id="slotsBody">
        <tr><td class="empty" colspan="7">Loading...</td></tr>
      </tbody>
    </table>
  </div>

  <div id="tab-embed" class="tab-content">
    <div class="section-title"><strong>Your Embed Code</strong></div>
    <p style="color:var(--fg3);font-family:var(--mono);font-size:10px;margin-bottom:16px;">
      Copy and paste this snippet into your website's HTML where you want the ad to appear.
    </p>
    <div class="block-label">Select a slot:</div>
    <select id="embedSlotSelect" style="background:rgba(0,0,0,0.4);color:var(--fg);border:1px solid var(--divider);padding:8px 12px;font-family:var(--mono);font-size:10px;margin-bottom:12px;width:100%;max-width:300px;" onchange="showEmbedCode()">
      <option value="">-- No slots yet --</option>
    </select>
    <div class="copy-box" id="embedCodeBox">Create a slot first to see your embed code.</div>
    <button class="copy-btn" onclick="copyEmbedCode()">Copy to Clipboard</button>
    <div id="embedCopied" style="font-family:var(--mono);font-size:9px;color:var(--teal);margin-top:8px;display:none;">&#10003; Copied!</div>
  </div>

  <div id="tab-payouts" class="tab-content">
    <div class="section-title"><strong>Payout History</strong></div>
    <table>
      <thead><tr><th>Date</th><th>Impressions</th><th>Clicks</th><th>Revenue</th><th>Status</th></tr></thead>
      <tbody id="payoutsBody">
        <tr><td class="empty" colspan="5">Loading...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<script>
const PUBLISHER_ID = __PID_JSON__;
const BASE_URL = __BASE_JSON__;

async function apiFetch(path) {
  const r = await fetch(path, { credentials: 'include' });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function fmtCurrency(v) {
  if (!v || v === 0) return '$0.00';
  return '$' + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtNumber(v) {
  if (!v) return '0';
  return Number(v).toLocaleString();
}

function fmtPct(v) {
  if (!v) return '0%';
  return Number(v).toFixed(2) + '%';
}

function fmtDate(ts) {
  if (!ts) return '--';
  return ts.slice(0, 10);
}

async function loadStats() {
  try {
    const d = await apiFetch('/api/v1/publishers/' + PUBLISHER_ID + '/stats');
    document.getElementById('stat-impressions').textContent = fmtNumber(d.total_impressions);
    document.getElementById('stat-clicks').textContent = fmtNumber(d.total_clicks);
    document.getElementById('stat-ctr').textContent = fmtPct(d.ctr);
    document.getElementById('stat-revenue').textContent = fmtCurrency(d.estimated_revenue);
    document.getElementById('stat-slots').textContent = d.active_slots || 0;
    document.getElementById('stat-revshare').textContent = (d.revenue_share_pct || 70) + '%';
  } catch (e) {
    document.querySelectorAll('#statsGrid .card-value').forEach(el => el.textContent = 'err');
  }
}

async function loadSlots() {
  try {
    const d = await apiFetch('/api/v1/publishers/' + PUBLISHER_ID + '/slots');
    const tbody = document.getElementById('slotsBody');
    const slotSelect = document.getElementById('embedSlotSelect');
    if (!d.slots || d.slots.length === 0) {
      tbody.innerHTML = '<tr><td class="empty" colspan="7">No ad slots yet. Create one using the form above.</td></tr>';
      slotSelect.innerHTML = '<option value="">-- No slots yet --</option>';
      return;
    }
    tbody.innerHTML = d.slots.map(function(s) {
      var imp = s.impressions || 0;
      var clk = s.clicks || 0;
      var ctr = imp > 0 ? ((clk / imp) * 100).toFixed(2) : '0.00';
      return '<tr>' +
        '<td><code>' + _esc(s.slot_name || '--') + '</code></td>' +
        '<td>' + _esc(s.ad_size || '300x250') + '</td>' +
        '<td><span style="color:' + (s.is_active ? 'var(--teal)' : 'var(--fg3)') + '">' + (s.is_active ? 'Active' : 'Inactive') + '</span></td>' +
        '<td class="num">' + fmtNumber(imp) + '</td>' +
        '<td class="num">' + fmtNumber(clk) + '</td>' +
        '<td class="num">' + ctr + '%</td>' +
        '<td><a href="#" onclick="showEmbedForSlot(\'' + s.slot_name.replace(/\'/g, '\\\'') + '\');switchTab(\'embed\');return false;" style="color:var(--cyan);font-family:var(--mono);font-size:9px;">Get code</a></td>' +
      '</tr>';
    }).join('');

    slotSelect.innerHTML = d.slots.map(function(s) {
      return '<option value="' + _esc(s.slot_name) + '">' + _esc(s.slot_name) + ' (' + _esc(s.ad_size || '300x250') + ')</option>';
    }).join('');
    if (d.slots.length > 0) {
      showEmbedCode();
    }
  } catch (e) {
    document.getElementById('slotsBody').innerHTML = '<tr><td class="empty" colspan="7">Failed to load</td></tr>';
  }
}

function _esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function createSlot() {
  var name = document.getElementById('newSlotName').value.trim();
  var size = document.getElementById('newSlotSize').value.trim() || '300x250';
  if (!name) { alert('Slot name is required'); return; }
  try {
    var r = await fetch('/api/v1/publishers/' + PUBLISHER_ID + '/slots', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot_name: name, ad_size: size }),
    });
    var d = await r.json();
    if (r.ok && d.ok) {
      document.getElementById('newSlotName').value = '';
      loadSlots();
    } else {
      alert(d.error || 'Failed to create slot');
    }
  } catch (e) {
    alert('Network error');
  }
}

function showEmbedForSlot(slotName) {
  var select = document.getElementById('embedSlotSelect');
  for (var i = 0; i < select.options.length; i++) {
    if (select.options[i].value === slotName) {
      select.selectedIndex = i;
      break;
    }
  }
  showEmbedCode();
}

function showEmbedCode() {
  var select = document.getElementById('embedSlotSelect');
  var slot = select.value;
  var box = document.getElementById('embedCodeBox');
  if (!slot) {
    box.textContent = 'Select a slot above to see its embed code.';
    return;
  }
  fetch('/api/v1/publishers/' + PUBLISHER_ID + '/embed-code?slot=' + encodeURIComponent(slot))
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok && d.embed_code) {
        box.textContent = d.embed_code;
      } else {
        box.textContent = d.error || 'Failed to generate embed code';
      }
    })
    .catch(function() {
      box.textContent = 'Error loading embed code';
    });
}

function copyEmbedCode() {
  var box = document.getElementById('embedCodeBox');
  var text = box.textContent;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(function() {
      var msg = document.getElementById('embedCopied');
      msg.style.display = 'block';
      setTimeout(function() { msg.style.display = 'none'; }, 2000);
    });
  } else {
    var ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    var msg = document.getElementById('embedCopied');
    msg.style.display = 'block';
    setTimeout(function() { msg.style.display = 'none'; }, 2000);
  }
}

async function loadPayouts() {
  try {
    const d = await apiFetch('/api/v1/publishers/' + PUBLISHER_ID + '/payouts');
    const tbody = document.getElementById('payoutsBody');
    if (!d.payouts || d.payouts.length === 0) {
      tbody.innerHTML = '<tr><td class="empty" colspan="5">No payouts yet. Revenue will appear here once ads start serving.</td></tr>';
      return;
    }
    tbody.innerHTML = d.payouts.map(function(p) {
      return '<tr>' +
        '<td>' + fmtDate(p.period_start) + ' - ' + fmtDate(p.period_end) + '</td>' +
        '<td class="num">' + fmtNumber(p.impressions) + '</td>' +
        '<td class="num">' + fmtNumber(p.clicks) + '</td>' +
        '<td class="num">' + fmtCurrency(p.revenue) + '</td>' +
        '<td>' + (p.status || 'pending') + '</td>' +
      '</tr>';
    }).join('');
  } catch (e) {
    document.getElementById('payoutsBody').innerHTML = '<tr><td class="empty" colspan="5">Failed to load</td></tr>';
  }
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
  document.querySelectorAll('.tab-content').forEach(function(t) { t.classList.remove('active'); });
  var tabs = document.querySelectorAll('.tab');
  var tabMap = { 'overview': 0, 'slots': 1, 'embed': 2, 'payouts': 3 };
  if (tabMap[name] !== undefined && tabs[tabMap[name]]) {
    tabs[tabMap[name]].classList.add('active');
  }
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'slots') loadSlots();
  if (name === 'payouts') loadPayouts();
}

loadStats();
loadSlots();
</script>
</body></html>"""
    return (html
        .replace("__PUB_CSS__", _PUB_CSS)
        .replace("__PUB_NAME__", pub_name)
        .replace("__PUB_ID__", pub_id)
        .replace("__PID_JSON__", pid_json)
        .replace("__BASE_JSON__", base_json)
    )


# ── ROUTES ───────────────────────────────────────────────────────────
def register_publisher_routes(
    app: FastAPI,
    *,
    sign_token: Callable,
    verify_token: Callable,
    send_email: Callable,
    public_base_url: str,
):
    """Register publisher portal routes. Pass sign_token, verify_token, and send_email from hub.py."""

    # ── PUBLIC: SIGNUP PAGE ───────────────────────────────────────────
    @app.get("/publishers/signup", response_class=HTMLResponse)
    async def pub_signup_page():
        return HTMLResponse(_PUB_SIGNUP_PAGE)

    # ── PUBLIC: LOGIN PAGE ────────────────────────────────────────────
    @app.get("/publishers/login", response_class=HTMLResponse)
    async def pub_login_page():
        return HTMLResponse(_PUB_LOGIN_PAGE)

    # ── PUBLIC: CREATE ACCOUNT ────────────────────────────────────────
    @app.post("/api/v1/publishers/signup")
    async def pub_signup(request: Request):
        """Create a new publisher account. Sends a welcome + magic link email."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        name = (body.get("name") or "").strip()
        contact_name = (body.get("contact_name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        website = (body.get("website") or "").strip()

        if not name:
            raise HTTPException(400, "Business name is required")
        if not contact_name:
            raise HTTPException(400, "Contact name is required")
        if not email or "@" not in email:
            raise HTTPException(400, "Valid email is required")

        # Check for existing publisher
        try:
            existing = _SB.table("publishers").select("id").eq("email", email).limit(1).execute()
            if existing.data:
                raise HTTPException(409, "A publisher with that email already exists. Please sign in.")
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[publisher] lookup error: {e}")
            if "does not exist" in str(e):
                # Table might not exist yet — migration not run
                raise HTTPException(503, "Publisher system is being set up. Try again shortly.")
            raise HTTPException(500, "Service error")

        # Generate API key
        api_key = f"emp_pub_{secrets.token_urlsafe(24)}"

        try:
            ins = _SB.table("publishers").insert({
                "name": name,
                "contact_name": contact_name,
                "email": email,
                "website": website,
                "api_key": api_key,
                "is_active": True,
                "status": "active",
                "revenue_share_pct": 70.00,
            }).execute()
            publisher = ins.data[0]
            pub_id = str(publisher["id"])
        except Exception as e:
            log.error(f"[publisher] insert error: {e}")
            raise HTTPException(500, "Could not create publisher account")

        log.info(f"[publisher] new signup: {name} <{email}> -> {pub_id}")

        # Send welcome + magic link email
        payload = {
            "publisher_id": pub_id,
            "email": email,
            "exp": int(time.time()) + LOGIN_LINK_TTL_SECONDS,
            "iat": int(time.time()),
            "kind": "publisher_login",
        }
        token = sign_token(payload)
        link = f"{public_base_url.rstrip('/')}/publishers/{pub_id}/verify?t={token}"

        html = f"""
          <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
            <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
              <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Publisher Network</div>
              <div style="font-size:20px;font-weight:700;color:#44E5B8;margin-top:6px;">Welcome to the Publisher Network!</div>
            </div>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              Hi {name}, your publisher account has been created. Click below to sign in and get your embed code.<br><br>
              <strong>Your API Key:</strong><br>
              <code style="background:#1a1a1a;padding:4px 8px;color:#44E5B8;font-size:12px;">{api_key}</code>
            </p>
            <div style="margin:28px 0;text-align:center;">
              <a href="{link}" style="display:inline-block;background:#44E5B8;color:#000;padding:12px 28px;text-decoration:none;font-weight:700;letter-spacing:.04em;">Sign in &rarr;</a>
            </div>
            <div style="font-size:11px;color:#52525b;line-height:1.7;">
              Place the embed code on your site to start earning. This link expires in 10 minutes.
            </div>
          </div>
        """
        try:
            result = await send_email(
                to=email,
                subject="Empire AI · Your publisher account is ready",
                html=html,
            )
            if not result.get("ok"):
                log.error(f"[publisher] welcome email failed: {result.get('error', 'unknown')}")
        except Exception as e:
            log.error(f"[publisher] welcome email error: {e}")

        return {"ok": True, "publisher_id": pub_id, "message": "Account created. Check your email for the login link."}

    # ── PUBLIC: SEND MAGIC LINK ───────────────────────────────────────
    @app.post("/api/v1/publishers/login")
    async def pub_send_link(request: Request):
        """Send a magic link to a publisher's email."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        email = (body.get("email") or "").lower().strip()
        if not email or "@" not in email:
            raise HTTPException(400, "Valid email required")

        try:
            res = _SB.table("publishers").select("id, name, email, is_active, status") \
                .eq("email", email).limit(1).execute()
            if not res.data or not res.data[0].get("is_active"):
                log.info(f"[publisher] login attempt for unknown/inactive: {email}")
                return {"ok": True}
            publisher = res.data[0]
        except Exception as e:
            log.error(f"[publisher] DB lookup failed: {e}")
            return {"ok": False, "error": "Service error"}

        payload = {
            "publisher_id": str(publisher["id"]),
            "email": email,
            "exp": int(time.time()) + LOGIN_LINK_TTL_SECONDS,
            "iat": int(time.time()),
            "kind": "publisher_login",
        }
        token = sign_token(payload)
        link = f"{public_base_url.rstrip('/')}/publishers/{publisher['id']}/verify?t={token}"

        html = f"""
          <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
            <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
              <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Publisher Portal</div>
              <div style="font-size:20px;font-weight:700;color:#44E5B8;margin-top:6px;">Your login link</div>
            </div>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              Hi {publisher['name']}, click below to sign in to your publisher dashboard.
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
                subject="Empire AI · Your publisher login link",
                html=html,
            )
            if not result.get("ok"):
                log.error(f"[publisher] email send failed: {result.get('error', 'unknown')}")
                return {"ok": False, "error": "Could not send login email"}
            return {"ok": True}
        except Exception as e:
            log.error(f"[publisher] email send error: {e}")
            return {"ok": False, "error": "Could not send login email"}

    # ── PUBLIC: VERIFY MAGIC LINK ─────────────────────────────────────
    @app.get("/publishers/{publisher_id}/verify", response_class=HTMLResponse)
    async def pub_verify(request: Request, publisher_id: str, t: str = Query(...)):
        """Verify magic link token. If valid, create session cookie and redirect to dashboard."""
        decoded = verify_token(t)
        if not decoded or decoded.get("kind") != "publisher_login":
            return HTMLResponse("""
                <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                <div style="text-align:center;"><h1 style="font-weight:200;">Link invalid</h1>
                <p style="color:#7a8ca3;">This link has expired or is invalid.</p>
                <a href="/publishers/login" style="color:#44e5b8;margin-top:16px;display:inline-block;">Request a new one →</a></div></body></html>
            """, status_code=401)

        if str(decoded.get("publisher_id", "")) != publisher_id:
            return HTMLResponse("<h1>Invalid link</h1>", status_code=401)

        try:
            res = _SB.table("publishers").select("id, name, email, website, revenue_share_pct, api_key, is_active") \
                .eq("id", publisher_id).limit(1).execute()
            if not res.data or not res.data[0].get("is_active"):
                return HTMLResponse("""
                    <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                    <div><h1 style="font-weight:200;">Account inactive</h1>
                    <p style="color:#7a8ca3;">Contact support to reactivate your account.</p></div></body></html>
                """, status_code=403)
            publisher = res.data[0]
        except Exception as e:
            log.error(f"[publisher] verify lookup failed: {e}")
            return HTMLResponse("<h1>Service error</h1>", status_code=500)

        # Create session
        session_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        _PUB_SESSION_HASHES[token_hash] = {
            "publisher": {
                "id": str(publisher["id"]),
                "name": publisher["name"],
                "email": publisher["email"],
                "website": publisher.get("website", ""),
                "revenue_share_pct": float(publisher.get("revenue_share_pct", 70)),
                "api_key": publisher.get("api_key", ""),
            },
            "expires_at": expires_at,
        }

        response = RedirectResponse(
            url=f"/publishers/{publisher_id}/dashboard",
            status_code=302,
        )
        use_secure = public_base_url.startswith("https://")
        response.set_cookie(
            key="publisher_session",
            value=session_token,
            max_age=int(SESSION_TTL_HOURS * 3600),
            httponly=True,
            secure=use_secure,
            samesite="lax",
            path="/",
        )
        log.info(f"[publisher] verified: {publisher['name']} ({publisher['email']})")
        return response

    # ── PUBLIC: DASHBOARD ─────────────────────────────────────────────
    @app.get("/publishers/{publisher_id}/dashboard", response_class=HTMLResponse)
    async def pub_dashboard(publisher_id: str, request: Request):
        """Render the publisher dashboard page."""
        publisher = _resolve_publisher(request)
        if not publisher or str(publisher.get("id", "")) != publisher_id:
            return HTMLResponse("""
                <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                <div style="text-align:center;"><h1 style="font-weight:200;">Sign in required</h1>
                <p style="color:#7a8ca3;">Please sign in to view your dashboard.</p>
                <a href="/publishers/login" style="color:#44e5b8;margin-top:16px;display:inline-block;">Sign in →</a></div></body></html>
            """, status_code=401)
        return HTMLResponse(_publisher_dashboard(publisher, base_url=public_base_url))

    # ── PUBLIC: EMBED PAGE ────────────────────────────────────────────
    @app.get("/publishers/{publisher_id}/embed", response_class=HTMLResponse)
    async def pub_embed_page(publisher_id: str, request: Request):
        """Embed code generation page."""
        publisher = _resolve_publisher(request)
        if not publisher or str(publisher.get("id", "")) != publisher_id:
            return HTMLResponse("""
                <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                <div style="text-align:center;"><h1 style="font-weight:200;">Sign in required</h1>
                <p style="color:#7a8ca3;">Please sign in to view your embed codes.</p>
                <a href="/publishers/login" style="color:#44e5b8;margin-top:16px;display:inline-block;">Sign in →</a></div></body></html>
            """, status_code=401)
        # Redirect to dashboard with embed tab active
        return RedirectResponse(f"/publishers/{publisher_id}/dashboard#embed", status_code=302)

    # ── PUBLIC: LOGOUT ────────────────────────────────────────────────
    @app.get("/publishers/logout")
    async def pub_logout(request: Request):
        """Clear the publisher session cookie."""
        token = request.cookies.get("publisher_session", "")
        if token:
            th = _hash_token(token)
            _PUB_SESSION_HASHES.pop(th, None)
        response = RedirectResponse(url="/publishers/login", status_code=302)
        response.delete_cookie("publisher_session", path="/")
        return response

    # ── API: STATS ────────────────────────────────────────────────────
    @app.get("/api/v1/publishers/{publisher_id}/stats")
    async def pub_stats(publisher_id: str, request: Request):
        """Return aggregate stats for a publisher: impressions, clicks, CTR, revenue."""
        publisher = _resolve_publisher(request)
        if not publisher or str(publisher.get("id", "")) != publisher_id:
            raise HTTPException(401, "Authentication required")

        try:
            # Get publisher info
            pub_res = _SB.table("publishers").select("revenue_share_pct, api_key") \
                .eq("id", publisher_id).limit(1).execute()
            rev_share = float(pub_res.data[0].get("revenue_share_pct", 70)) if pub_res.data else 70.00

            # Get publisher's slots
            slots = _SB.table("ad_slots").select("id, slot_name, is_active") \
                .eq("publisher_id", publisher_id).execute()
            slot_ids = [str(s["id"]) for s in (slots.data or [])]
            active_slots = sum(1 for s in (slots.data or []) if s.get("is_active"))

            total_impressions = 0
            total_clicks = 0
            estimated_revenue = 0.0

            if slot_ids:
                # Get impressions for these slots
                imp = _SB.table("ad_impressions").select("id, cost_per_impression, revenue_share_pct") \
                    .in_("slot_id", slot_ids).execute()
                total_impressions = len(imp.data or [])
                for row in (imp.data or []):
                    cpm = float(row.get("cost_per_impression", 0.001) or 0.001)
                    rs = float(row.get("revenue_share_pct", rev_share) or rev_share)
                    estimated_revenue += cpm * (rs / 100.0)

                # Get clicks
                # We need to join: clicks where creative_id matches a creative that was served in these slots
                # Simplified: count clicks that reference impressions in these slots
                imp_ids = [str(i["id"]) for i in (imp.data or [])]
                if imp_ids:
                    clk = _SB.table("ad_clicks").select("id") \
                        .in_("impression_id", imp_ids).execute()
                    total_clicks = len(clk.data or [])

            ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0.0

            return {
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "ctr": round(ctr, 2),
                "estimated_revenue": round(estimated_revenue, 2),
                "active_slots": active_slots,
                "revenue_share_pct": rev_share,
            }
        except Exception as e:
            log.error(f"[publisher] stats error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: SLOTS ────────────────────────────────────────────────────
    @app.get("/api/v1/publishers/{publisher_id}/slots")
    async def pub_slots(publisher_id: str, request: Request):
        """Return all ad slots for a publisher."""
        publisher = _resolve_publisher(request)
        if not publisher or str(publisher.get("id", "")) != publisher_id:
            raise HTTPException(401, "Authentication required")

        try:
            slots = _SB.table("ad_slots").select("*") \
                .eq("publisher_id", publisher_id) \
                .order("created_at", desc=True) \
                .execute()

            slot_list = []
            for s in (slots.data or []):
                sid = str(s["id"])
                # Count impressions for this slot
                imp = _SB.table("ad_impressions").select("id", count="exact") \
                    .eq("slot_id", sid).limit(10000).execute()
                impressions = imp.count if hasattr(imp, 'count') else 0

                # Count clicks via impressions
                imp_rows = _SB.table("ad_impressions").select("id") \
                    .eq("slot_id", sid).execute()
                imp_ids = [str(i["id"]) for i in (imp_rows.data or [])]
                clicks = 0
                if imp_ids:
                    clk = _SB.table("ad_clicks").select("id", count="exact") \
                        .in_("impression_id", imp_ids).limit(10000).execute()
                    clicks = clk.count if hasattr(clk, 'count') else 0

                slot_list.append({
                    "id": sid,
                    "slot_name": s.get("slot_name", ""),
                    "ad_size": s.get("ad_size", "300x250"),
                    "ad_format": s.get("ad_format", "native"),
                    "niches": s.get("niches", []),
                    "is_active": s.get("is_active", True),
                    "revenue_share_pct": float(s.get("revenue_share_pct", 70)),
                    "impressions": impressions,
                    "clicks": clicks,
                    "created_at": str(s.get("created_at", "")),
                })

            return {"slots": slot_list, "total": len(slot_list)}
        except Exception as e:
            log.error(f"[publisher] slots error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: CREATE SLOT ──────────────────────────────────────────────
    @app.post("/api/v1/publishers/{publisher_id}/slots")
    async def pub_create_slot(publisher_id: str, request: Request):
        """Create a new ad slot for a publisher."""
        publisher = _resolve_publisher(request)
        if not publisher or str(publisher.get("id", "")) != publisher_id:
            raise HTTPException(401, "Authentication required")

        try:
            body = await request.json()
        except Exception:
            body = {}

        slot_name = (body.get("slot_name") or "").strip().lower().replace(" ", "-")
        ad_size = body.get("ad_size", "300x250")

        if not slot_name:
            raise HTTPException(400, "slot_name is required")

        # Check for duplicate
        try:
            existing = _SB.table("ad_slots").select("id") \
                .eq("publisher_id", publisher_id) \
                .eq("slot_name", slot_name).limit(1).execute()
            if existing.data:
                raise HTTPException(409, f"Slot '{slot_name}' already exists for this publisher")
        except HTTPException:
            raise
        except Exception:
            pass

        try:
            ins = _SB.table("ad_slots").insert({
                "publisher_id": publisher_id,
                "publisher_name": publisher.get("name", ""),
                "slot_name": slot_name,
                "ad_size": ad_size,
                "ad_format": "native",
                "is_active": True,
                "revenue_share_pct": float(publisher.get("revenue_share_pct", 70)),
            }).execute()
            log.info(f"[publisher] slot created: {slot_name} for publisher {publisher_id}")
            return {"ok": True, "slot": ins.data[0]}
        except Exception as e:
            log.error(f"[publisher] create slot error: {e}")
            raise HTTPException(500, str(e)[:200])

    # ── API: EMBED CODE ──────────────────────────────────────────────
    @app.get("/api/v1/publishers/{publisher_id}/embed-code")
    async def pub_embed_code(publisher_id: str, request: Request, slot: str = Query("")):
        """Generate the raw embed snippet for a specific slot."""
        publisher = _resolve_publisher(request)
        if not publisher or str(publisher.get("id", "")) != publisher_id:
            raise HTTPException(401, "Authentication required")

        if not slot:
            raise HTTPException(400, "slot query parameter is required")

        # Verify the slot belongs to this publisher
        try:
            slot_res = _SB.table("ad_slots").select("id, slot_name") \
                .eq("publisher_id", publisher_id) \
                .eq("slot_name", slot).limit(1).execute()
            if not slot_res.data:
                raise HTTPException(404, f"Slot '{slot}' not found")
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[publisher] slot lookup error: {e}")
            raise HTTPException(500, "Service error")

        embed = _generate_embed_code(publisher_id, slot, public_base_url)
        return {"ok": True, "embed_code": embed, "slot": slot}

    # ── API: PAYOUTS ─────────────────────────────────────────────────
    @app.get("/api/v1/publishers/{publisher_id}/payouts")
    async def pub_payouts(publisher_id: str, request: Request, limit: int = Query(50, ge=1, le=200)):
        """Return payout history for a publisher (aggregated by month)."""
        publisher = _resolve_publisher(request)
        if not publisher or str(publisher.get("id", "")) != publisher_id:
            raise HTTPException(401, "Authentication required")

        try:
            # Get publisher's revenue share
            pub_res = _SB.table("publishers").select("revenue_share_pct") \
                .eq("id", publisher_id).limit(1).execute()
            rev_share = float(pub_res.data[0].get("revenue_share_pct", 70)) if pub_res.data else 70.00

            # Get slots
            slots = _SB.table("ad_slots").select("id") \
                .eq("publisher_id", publisher_id).execute()
            slot_ids = [str(s["id"]) for s in (slots.data or [])]

            if not slot_ids:
                return {"payouts": [], "total": 0}

            # Get impressions grouped by month
            imp = _SB.table("ad_impressions").select("id, created_at, cost_per_impression") \
                .in_("slot_id", slot_ids) \
                .order("created_at", desc=True) \
                .execute()

            # Aggregate by month
            monthly: dict[str, dict] = {}
            for row in (imp.data or []):
                created = (row.get("created_at") or "")[:7]  # "2026-06"
                if created not in monthly:
                    monthly[created] = {
                        "period_start": created + "-01",
                        "impressions": 0,
                        "clicks": 0,
                        "revenue": 0.0,
                    }
                monthly[created]["impressions"] += 1
                cpm = float(row.get("cost_per_impression", 0.001) or 0.001)
                monthly[created]["revenue"] += cpm * (rev_share / 100.0)

            # Get clicks per month via impression IDs
            imp_ids = [str(i["id"]) for i in (imp.data or [])]
            if imp_ids:
                clk = _SB.table("ad_clicks").select("id, created_at") \
                    .in_("impression_id", imp_ids).execute()
                for row in (clk.data or []):
                    month = (row.get("created_at") or "")[:7]
                    if month in monthly:
                        monthly[month]["clicks"] += 1

            payouts = []
            for period in sorted(monthly.keys(), reverse=True)[:limit]:
                payouts.append({
                    "period_start": monthly[period]["period_start"],
                    "period_end": "",
                    "impressions": monthly[period]["impressions"],
                    "clicks": monthly[period]["clicks"],
                    "revenue": round(monthly[period]["revenue"], 2),
                    "status": "pending" if monthly[period]["revenue"] > 0 else "none",
                })

            return {"payouts": payouts, "total": len(payouts)}
        except Exception as e:
            log.error(f"[publisher] payouts error: {e}")
            return {"payouts": [], "total": 0}

    # ── API: REGENERATE API KEY ───────────────────────────────────────
    @app.post("/api/v1/publishers/{publisher_id}/api-key/regenerate")
    async def pub_regenerate_api_key(publisher_id: str, request: Request):
        """Generate a new API key for the publisher."""
        publisher = _resolve_publisher(request)
        if not publisher or str(publisher.get("id", "")) != publisher_id:
            raise HTTPException(401, "Authentication required")

        new_key = f"emp_pub_{secrets.token_urlsafe(24)}"

        try:
            _SB.table("publishers").update({"api_key": new_key}) \
                .eq("id", publisher_id).execute()
            log.info(f"[publisher] API key regenerated for {publisher_id}")
            return {"ok": True, "api_key": new_key}
        except Exception as e:
            log.error(f"[publisher] regenerate API key error: {e}")
            raise HTTPException(500, str(e)[:80])

    log.info("[publisher] Routes registered — /publishers/{signup,login,verify,dashboard,embed} + /api/v1/publishers/{stats,slots,embed-code,payouts,api-key}")
