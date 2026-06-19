"""
EMPIRE V49 · CONTRACTOR PORTAL
===============================
Self-service portal for active contractors. Contractors log in via email
magic link, see their dispatch history, earnings, accept new dispatches,
and manage their profile.

ENDPOINTS
─────────
  GET  /portal/contractors/login                          → public login form
  POST /api/v1/contractors/portal/login                   → send magic link email
  GET  /portal/contractors/{id}/verify?t=...              → verify token, set cookie, redirect
  GET  /portal/contractors/{id}/dashboard                  → main contractor dashboard
  GET  /portal/contractors/logout                          → clear session
  GET  /api/v1/contractors/{id}/stats                     → aggregate stats JSON
  GET  /api/v1/contractors/{id}/dispatches                → dispatch history JSON
  GET  /api/v1/contractors/{id}/earnings                  → payout/earnings JSON
  PATCH /api/v1/contractors/{id}/profile                  → update profile fields
  GET  /api/v1/contractors/{id}/active-dispatch           → accept a dispatch from the dashboard
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

log = logging.getLogger("empire.contractor_portal")

# ── CONFIG ───────────────────────────────────────────────────────────
_SB = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", ""),
)

LOGIN_LINK_TTL_SECONDS = 600  # 10 min
SESSION_TTL_HOURS = 24 * 7   # 7 days (contractors check less often)

# In-memory session store
_CTR_SESSION_HASHES: dict[str, dict] = {}


# ── HELPERS ──────────────────────────────────────────────────────────
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _verify_session(token: str) -> Optional[dict]:
    th = _hash_token(token)
    sess = _CTR_SESSION_HASHES.get(th)
    if not sess:
        return None
    if datetime.now(timezone.utc) > sess["expires_at"]:
        del _CTR_SESSION_HASHES[th]
        return None
    return sess.get("contractor")


def _resolve_contractor(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        ctr = _verify_session(auth[7:])
        if ctr:
            return ctr
    token = request.cookies.get("contractor_session", "")
    if token:
        ctr = _verify_session(token)
        if ctr:
            return ctr
    return None


# ── LOGIN PAGE ──────────────────────────────────────────────────────
_CTR_LOGIN_CSS = """
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
.box {
  max-width: 420px; width: 100%;
  background: #15263f; border: 1px solid rgba(122,140,163,0.18);
  padding: 40px 36px;
}
.brand {
  display: flex; align-items: baseline; justify-content: center; gap: 8px;
  margin-bottom: 6px;
}
.brand-e { font-weight: 700; font-size: 20px; letter-spacing: 0.22em; }
.brand-ai { font-weight: 700; font-size: 20px; letter-spacing: 0.22em; color: #5ac8fa; }
.brand-sub {
  text-align: center; font-family: 'JetBrains Mono', monospace;
  font-size: 9px; color: #4a5a72; letter-spacing: 0.32em; text-transform: uppercase;
  margin-bottom: 32px;
}
h1 { font-weight: 200; font-size: 26px; letter-spacing: -0.04em; margin-bottom: 8px; text-align: center; }
h1 em { font-style: italic; color: #44e5b8; font-weight: 500; }
.lead { text-align: center; color: #7a8ca3; font-size: 13px; line-height: 1.7; margin-bottom: 28px; }
.field { margin-bottom: 16px; }
.field label {
  display: block; font-family: 'JetBrains Mono', monospace;
  font-size: 9px; color: #7a8ca3; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 5px;
}
.field input {
  width: 100%; background: rgba(0,0,0,0.4); color: #f8fafd;
  border: 1px solid rgba(122,140,163,0.18); font-family: 'JetBrains Mono', monospace;
  font-size: 13px; padding: 12px 14px; outline: none; transition: border-color 0.2s;
}
.field input:focus { border-color: #44e5b8; }
.btn {
  width: 100%; background: #44e5b8; color: #000; border: none; padding: 14px;
  font-family: 'Inter', sans-serif; font-weight: 700; font-size: 14px; letter-spacing: 0.04em;
  cursor: pointer; transition: all 0.2s; margin-top: 8px;
}
.btn:hover { background: transparent; color: #44e5b8; outline: 1px solid #44e5b8; }
.btn:disabled { opacity: 0.4; cursor: wait; }
.flash {
  display: none; padding: 12px 16px; margin-top: 14px;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.04em;
}
.flash.show { display: block; }
.flash.success { color: #44e5b8; background: rgba(68,229,184,0.06); border: 1px solid rgba(68,229,184,0.25); }
.flash.error { color: #f43f5e; background: rgba(244,63,94,0.06); border: 1px solid rgba(244,63,94,0.25); }
.foot { text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #4a5a72; letter-spacing: 0.18em; margin-top: 28px; }
.onboard-link { text-align: center; margin-top: 16px; font-family: 'JetBrains Mono', monospace; font-size: 10px; }
.onboard-link a { color: #44e5b8; text-decoration: none; }
.onboard-link a:hover { text-decoration: underline; }
"""

_CTR_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Contractor Login</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>""" + _CTR_LOGIN_CSS + """</style>
</head><body>
<div class="box">
  <div class="brand"><span class="brand-e">EMPIRE</span><span class="brand-ai">AI</span></div>
  <div class="brand-sub">Contractor Portal</div>
  <h1>Contractor <em>Login</em></h1>
  <p class="lead">Enter your email and we'll send a one-time sign-in link.</p>
  <div class="field">
    <label>Email</label>
    <input type="email" id="email" placeholder="you@yourcompany.com" autofocus>
  </div>
  <button class="btn" id="btn" onclick="send()">Send login link</button>
  <div id="flash" class="flash"></div>
  <div class="onboard-link">Not yet registered? <a href="/contractors">Self-onboard →</a></div>
  <div class="foot">Empire AI V49 · Predictive Revenue Network</div>
</div>
<script>
async function send() {
  const email = document.getElementById('email').value.trim();
  const flash = document.getElementById('flash');
  const btn = document.getElementById('btn');
  flash.className = 'flash';
  if (!email || !email.includes('@')) {
    flash.className = 'flash show error';
    flash.textContent = 'Enter a valid email';
    return;
  }
  btn.disabled = true; btn.textContent = 'Sending...';
  try {
    const r = await fetch('/api/v1/contractors/portal/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    const d = await r.json();
    if (r.ok && d.ok) {
      flash.className = 'flash show success';
      flash.textContent = 'If that email is registered, a login link is on its way.';
    } else {
      flash.className = 'flash show error';
      flash.textContent = d.error || 'Could not send';
    }
  } catch (e) {
    flash.className = 'flash show error';
    flash.textContent = 'Network error';
  } finally {
    btn.disabled = false; btn.textContent = 'Send login link';
  }
}
document.getElementById('email').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
</script>
</body></html>"""


# ── DASHBOARD PAGE ───────────────────────────────────────────────────
def _contractor_dashboard(contractor: dict, base_url: str = "http://localhost:8001") -> str:
    ctr_id = contractor.get("id", "")
    ctr_name = contractor.get("name", "Contractor")
    pid_json = json.dumps(ctr_id)
    base_json = json.dumps(base_url)
    trust = float(contractor.get("trust_score", 5.0))
    metro = contractor.get("metro", "—")
    specialties = contractor.get("specialties", [])

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Contractor Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg: #0a1a2f; --bg2: #15263f; --bg3: #1a2f4a;
  --fg: #f8fafd; --fg2: #c8d0dc; --fg3: #7a8ca3;
  --teal: #44e5b8; --cyan: #5ac8fa; --amber: #ffb800; --red: #f43f5e;
  --divider: rgba(122,140,163,0.18); --radius: 8px;
  --font: 'Inter', -apple-system, sans-serif;
  --mono: 'JetBrains Mono', monospace;
}}
body {{ background: var(--bg); color: var(--fg); font-family: var(--font); letter-spacing: -0.02em; min-height: 100vh; }}
.header {{
  background: var(--bg2); border-bottom: 1px solid var(--divider);
  padding: 20px 32px; display: flex; align-items: center; justify-content: space-between;
}}
.header-brand {{ display: flex; align-items: baseline; gap: 8px; }}
.header-brand .e {{ font-weight: 700; font-size: 18px; letter-spacing: 0.22em; }}
.header-brand .ai {{ font-weight: 700; font-size: 18px; letter-spacing: 0.22em; color: var(--cyan); }}
.header h1 {{ font-weight: 200; font-size: 20px; letter-spacing: -0.04em; }}
.header h1 em {{ color: var(--teal); font-style: italic; font-weight: 500; }}
.header-right {{ display: flex; align-items: center; gap: 16px; font-family: var(--mono); font-size: 10px; color: var(--fg3); }}
.header-right .name {{ color: var(--fg2); }}
.logout {{ color: var(--red); text-decoration: none; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }}
.logout:hover {{ text-decoration: underline; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 28px 24px; }}
.greeting {{ margin-bottom: 28px; }}
.greeting h2 {{ font-weight: 200; font-size: 22px; letter-spacing: -0.04em; }}
.greeting h2 em {{ color: var(--teal); font-style: italic; font-weight: 500; }}
.greeting .sub {{ font-family: var(--mono); font-size: 10px; color: var(--fg3); margin-top: 4px; letter-spacing: 0.08em; }}
.bio-bar {{
  background: var(--bg2); border: 1px solid var(--divider);
  padding: 16px 20px; margin-bottom: 20px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}}
.bio-chip {{
  font-family: var(--mono); font-size: 9px; color: var(--fg2);
  background: rgba(122,140,163,0.1); padding: 4px 10px;
}}
.bio-chip strong {{ color: var(--teal); font-weight: 500; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 28px; }}
.card {{
  background: var(--bg2); border: 1px solid var(--divider); padding: 18px 20px;
  transition: border-color 0.2s;
}}
.card:hover {{ border-color: rgba(68,229,184,0.3); }}
.card-label {{ font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 6px; }}
.card-value {{ font-family: var(--font); font-weight: 200; font-size: 26px; color: var(--fg); line-height: 1; }}
.card-value.teal {{ color: var(--teal); }}
.card-value.cyan {{ color: var(--cyan); }}
.card-value.amber {{ color: var(--amber); }}
.card-meta {{ font-family: var(--mono); font-size: 9px; color: var(--fg3); margin-top: 6px; }}
.section {{ margin-bottom: 32px; }}
.section-title {{ font-family: var(--mono); font-size: 10px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }}
.section-title strong {{ color: var(--fg2); font-weight: 500; }}
.section-title .count {{ color: var(--teal); font-size: 9px; background: rgba(68,229,184,0.1); padding: 2px 8px; }}
table {{ width: 100%; border-collapse: collapse; background: var(--bg2); border: 1px solid var(--divider); }}
thead th {{
  font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em;
  text-transform: uppercase; text-align: left; padding: 10px 14px;
  border-bottom: 1px solid var(--divider); background: rgba(0,0,0,0.15);
}}
tbody td {{ padding: 10px 14px; border-bottom: 1px solid rgba(122,140,163,0.08); font-family: var(--mono); font-size: 10px; color: var(--fg2); }}
tbody tr:last-child td {{ border-bottom: none; }}
.num {{ text-align: right; }}
.empty {{ text-align: center; padding: 32px; color: var(--fg3); font-family: var(--mono); font-size: 10px; }}
.tabs {{ display: flex; gap: 4px; border-bottom: 1px solid var(--divider); margin-bottom: 16px; flex-wrap: wrap; }}
.tab {{
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  padding: 8px 16px; cursor: pointer; border: none; background: transparent;
  color: var(--fg3); border-bottom: 2px solid transparent; transition: all 0.2s;
}}
.tab:hover {{ color: var(--fg2); }}
.tab.active {{ color: var(--teal); border-bottom-color: var(--teal); }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}
.badge {{
  display: inline-block; font-family: var(--mono); font-size: 8px;
  padding: 2px 6px; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.08em;
}}
.badge.sent {{ color: var(--cyan); background: rgba(90,200,250,0.1); }}
.badge.accepted {{ color: var(--teal); background: rgba(68,229,184,0.1); }}
.badge.completed {{ color: var(--teal); background: rgba(68,229,184,0.1); }}
.badge.ghosted {{ color: var(--red); background: rgba(244,63,94,0.1); }}
.badge.expired {{ color: var(--fg3); background: rgba(122,140,163,0.1); }}
.action-link {{ color: var(--cyan); text-decoration: none; cursor: pointer; font-family: var(--mono); font-size: 9px; }}
.action-link:hover {{ text-decoration: underline; }}
.action-link.danger {{ color: var(--red); }}
.profile-form {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }}
.profile-form .field-full {{ grid-column: 1 / -1; }}
.profile-form .field {{ margin-bottom: 0; }}
.profile-form .field label {{ display: block; font-family: var(--mono); font-size: 8px; color: var(--fg3); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 4px; }}
.profile-form input, .profile-form select, .profile-form textarea {{
  width: 100%; background: rgba(0,0,0,0.4); color: var(--fg);
  border: 1px solid var(--divider); font-family: var(--mono); font-size: 12px;
  padding: 8px 10px; outline: none; transition: border-color 0.2s;
}}
.profile-form input:focus, .profile-form select:focus, .profile-form textarea:focus {{ border-color: var(--teal); }}
.profile-form textarea {{ resize: vertical; min-height: 50px; }}
.profile-form select option {{ background: var(--bg2); color: var(--fg); }}
.profile-form button {{
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  background: var(--teal); color: #000; border: none; padding: 8px 16px; cursor: pointer;
  white-space: nowrap; align-self: end;
}}
.profile-form button:hover {{ background: transparent; color: var(--teal); outline: 1px solid var(--teal); }}
.btn {{ font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase; padding: 8px 16px; cursor: pointer; border: none; transition: all 0.2s; }}
.modal-overlay {{ position:fixed; inset:0; background:rgba(0,0,0,0.6); display:none; align-items:center; justify-content:center; z-index:9999; }}
.modal-overlay.show {{ display:flex; }}
.modal-box {{ background:var(--bg2); border:1px solid var(--divider); padding:28px 32px; max-width:420px; width:90%; position:relative; }}
.modal-close {{ position:absolute; top:12px; right:16px; background:none; border:none; color:var(--fg3); font-size:18px; cursor:pointer; font-family:var(--mono); }}
.modal-close:hover {{ color:var(--red); }}
.modal-name {{ font-size:18px; font-weight:500; color:var(--fg); margin-bottom:4px; }}
.modal-meta-sub {{ font-family:var(--mono); font-size:10px; color:var(--fg3); margin-bottom:16px; }}
.modal-stat {{ display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--divider); font-family:var(--mono); font-size:10px; }}
.modal-stat-label {{ color:var(--fg3); }}
.modal-stat-value {{ color:var(--teal); font-weight:600; }}
.btn-teal {{ background: var(--teal); color: #000; }}
.btn-teal:hover {{ background: transparent; color: var(--teal); outline: 1px solid var(--teal); }}
.ccy {{ font-family: var(--mono); font-weight: 400; font-size: 14px; color: var(--fg3); vertical-align: super; }}
</style>
</head><body>
<div class="header">
  <div class="header-brand"><span class="e">EMPIRE</span><span class="ai">AI</span></div>
  <h1>Contractor <em>Dashboard</em></h1>
  <div class="header-right">
    <div id="navRefSection" style="display:none;align-items:center;gap:6px;flex-shrink:1;min-width:0;">
      <code id="navRefLink" title="Referral link — click Copy to share" style="background:rgba(0,0,0,0.3);padding:4px 8px;font-size:9px;color:var(--amber);border:1px solid rgba(255,184,0,0.15);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px;">Loading...</code>
      <button onclick="copyNavRefLink()" style="font-family:var(--mono);font-size:8px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--amber);border:1px solid rgba(255,184,0,0.3);padding:3px 7px;cursor:pointer;white-space:nowrap;flex-shrink:0;">Copy</button>
    </div>
    <span class="name">{ctr_name}</span>
    <a href="/portal/contractors/logout" class="logout">Sign out</a>
  </div>
</div>
<div class="container">
  <div class="greeting">
    <h2>Welcome, <em>{ctr_name}</em></h2>
    <div class="sub">Contractor Portal · Dispatch Network</div>
  </div>

  <div class="bio-bar">
    <span class="bio-chip">Metro: <strong>{metro}</strong></span>
    <span class="bio-chip">Trust Score: <strong>{trust:.1f}/10</strong></span>
    <span class="bio-chip">Specialties: <strong>{', '.join(specialties) if specialties else '—'}</strong></span>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('overview')">Overview</button>
    <button class="tab" onclick="switchTab('dispatches')">Dispatches</button>
    <button class="tab" onclick="switchTab('earnings')">Earnings</button>
    <button class="tab" onclick="switchTab('referrals')">Referrals</button>
    <button class="tab" onclick="switchTab('profile')">Profile</button>
  </div>

  <div id="tab-overview" class="tab-content active">
    <div class="grid" id="statsGrid">
      <div class="card"><div class="card-label">Dispatches Received</div><div class="card-value" id="stat-total">--</div></div>
      <div class="card"><div class="card-label">Accepted</div><div class="card-value teal" id="stat-accepted">--</div></div>
      <div class="card"><div class="card-label">Completed</div><div class="card-value cyan" id="stat-completed">--</div></div>
      <div class="card"><div class="card-label">Ghosted</div><div class="card-value" id="stat-ghosted">--</div></div>
      <div class="card"><div class="card-label">Total Earnings</div><div class="card-value teal" id="stat-earnings">$0.00</div></div>
      <div class="card"><div class="card-label">Referral Bounty Earned</div><div class="card-value amber" id="stat-ref-earned">$0.00</div></div>
      <div class="card"><div class="card-label">Pending Bounties</div><div class="card-value" id="stat-ref-pending">0</div></div>
      <div class="card"><div class="card-label">Trust Score</div><div class="card-value" id="stat-trust">--</div></div>
      <div class="card"><div class="card-label">Your Referral Rank</div><div class="card-value amber" id="stat-ref-rank">--</div><div class="card-meta" id="stat-ref-rank-meta"></div></div>
    </div>
    <div class="section">
      <div class="section-title"><strong>Quick Links</strong></div>
      <button class="btn btn-teal" onclick="switchTab('dispatches')" style="margin-right:8px;">View Dispatches →</button>
      <button class="btn btn-teal" onclick="switchTab('earnings')" style="margin-right:8px;">Earnings →</button>
      <button class="btn btn-teal" onclick="switchTab('referrals')" style="margin-right:8px;">Referrals →</button>
    </div>

    <!-- ── Referral Quick-View ── -->
    <div class="section" style="margin-top:0;">
      <div class="section-title"><strong>Your Referral Link</strong> <span class="count" id="ov-ref-status">—</span></div>
      <div style="background:var(--bg2);border:1px solid var(--divider);padding:14px 18px;">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <code id="ovRefLink" style="flex:1;background:rgba(0,0,0,0.3);padding:8px 12px;font-family:var(--mono);font-size:11px;color:var(--amber);word-break:break-all;border:1px solid rgba(255,184,0,0.2);min-width:160px;">Loading...</code>
          <button onclick="copyOvRefLink()" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:var(--teal);color:#000;border:none;padding:8px 12px;cursor:pointer;white-space:nowrap;">Copy</button>
          <button onclick="copyMessage(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--amber);border:1px solid var(--amber);padding:8px 12px;cursor:pointer;white-space:nowrap;">Copy Msg</button>
          <button onclick="shareViaSms(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">SMS</button>
          <button onclick="shareViaWhatsApp(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">WhatsApp</button>
          <button onclick="shareViaTelegram(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">Telegram</button>
          <button onclick="toggleMoreShare('ov')" id="more-toggle-ov" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--fg3);border:1px solid var(--divider);padding:8px 12px;cursor:pointer;white-space:nowrap;">+ More</button>
        </div>
        <div id="more-share-ov" style="display:none;margin-top:4px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <button onclick="shareViaEmail(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">Email</button>
          <button onclick="shareViaTwitter(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">X</button>
          <button onclick="shareViaLinkedIn(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">LinkedIn</button>
          <button onclick="shareViaFacebook(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">Facebook</button>
          <button onclick="shareViaReddit(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">Reddit</button>
          <button onclick="shareViaPinterest(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">Pinterest</button>
          <button onclick="shareViaMessenger(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">Messenger</button>
          <button onclick="shareViaTikTok(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">TikTok</button>
          <button onclick="shareViaSnapchat(document.getElementById('ovRefLink').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:8px 12px;cursor:pointer;white-space:nowrap;">Snapchat</button>
        </div>
        </div>
        <div style="font-family:var(--mono);font-size:9px;color:var(--fg3);margin-top:8px;display:flex;gap:16px;flex-wrap:wrap;">
          <span>Earned: <strong style="color:var(--amber);font-weight:600;" id="ov-ref-earned">$0.00</strong></span>
          <span>Pending: <strong style="color:var(--fg2);font-weight:600;" id="ov-ref-pending-count">0</strong></span>
          <span>Total Referrals: <strong style="color:var(--teal);font-weight:600;" id="ov-ref-total">0</strong></span>
        </div>
        <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--divider);display:flex;align-items:center;gap:16px;">
          <img id="ovQrCode" src="" alt="QR Code" onerror="this.style.display='none'" style="width:100px;height:100px;border-radius:4px;background:white;padding:4px;display:none;" />
          <div style="font-size:10px;color:var(--fg3);line-height:1.5;">
            Scan to share your referral link — post on flyers, job boards, or in person.
          </div>
        </div>
      </div>
    </div>
  </div>

  <div id="tab-dispatches" class="tab-content">
    <div class="section-title"><strong>Dispatch History</strong></div>
    <table>
      <thead><tr><th>Date</th><th>Lead Metro</th><th>Match Score</th><th>Status</th><th>Accepted</th><th>Completed</th></tr></thead>
      <tbody id="dispatchesBody">
        <tr><td class="empty" colspan="6">Loading...</td></tr>
      </tbody>
    </table>
  </div>

  <div id="tab-earnings" class="tab-content">
    <div class="grid" style="margin-bottom:16px;">
      <div class="card"><div class="card-label">Lifetime Earnings</div><div class="card-value teal" id="earnings-total">$0.00</div></div>
      <div class="card"><div class="card-label">Completed Jobs</div><div class="card-value" id="earnings-jobs">0</div></div>
      <div class="card"><div class="card-label">Est. Fee Revenue</div><div class="card-value amber" id="earnings-fees">$0.00</div></div>
    </div>
    <div class="section-title"><strong>Payout History</strong></div>
    <table>
      <thead><tr><th>Date</th><th>Dispatch</th><th>Amount</th><th>Status</th></tr></thead>
      <tbody id="earningsBody">
        <tr><td class="empty" colspan="4">No payouts yet</td></tr>
      </tbody>
    </table>
  </div>

  <div id="tab-referrals" class="tab-content">
    <div class="section-title"><strong>Your Referral Link</strong></div>
    <div style="background:var(--bg2);border:1px solid var(--divider);padding:16px 20px;margin-bottom:20px;">
      <div style="font-family:var(--mono);font-size:8px;color:var(--fg3);letter-spacing:0.14em;text-transform:uppercase;margin-bottom:6px;">Share this link with other contractors</div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <code id="referralLinkDisplay" style="flex:1;background:rgba(0,0,0,0.3);padding:10px 14px;font-family:var(--mono);font-size:11px;color:var(--cyan);word-break:break-all;border:1px solid var(--divider);min-width:200px;">Loading...</code>
        <button onclick="copyReferralLink()" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:var(--teal);color:#000;border:none;padding:10px 14px;cursor:pointer;white-space:nowrap;">Copy Link</button>
        <button onclick="copyMessage(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--amber);border:1px solid var(--amber);padding:10px 14px;cursor:pointer;white-space:nowrap;">Copy Msg</button>
        <button onclick="shareViaSms(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">SMS</button>
        <button onclick="shareViaWhatsApp(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">WhatsApp</button>
        <button onclick="shareViaTelegram(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">Telegram</button>
          <button onclick="toggleMoreShare('ref')" id="more-toggle-ref" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--fg3);border:1px solid var(--divider);padding:10px 14px;cursor:pointer;white-space:nowrap;">+ More</button>
        </div>
        <div id="more-share-ref" style="display:none;margin-top:4px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <button onclick="shareViaEmail(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">Email</button>
          <button onclick="shareViaTwitter(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">X</button>
          <button onclick="shareViaLinkedIn(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">LinkedIn</button>
          <button onclick="shareViaFacebook(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">Facebook</button>
          <button onclick="shareViaReddit(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">Reddit</button>
          <button onclick="shareViaPinterest(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">Pinterest</button><button onclick="shareViaMessenger(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">Messenger</button>
          <button onclick="shareViaTikTok(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">TikTok</button>
          <button onclick="shareViaSnapchat(document.getElementById('referralLinkDisplay').textContent)" style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:transparent;color:var(--teal);border:1px solid var(--teal);padding:10px 14px;cursor:pointer;white-space:nowrap;">Snapchat</button>
          </div>
        </div>
      <div style="font-family:var(--mono);font-size:9px;color:var(--fg3);margin-top:8px;">
        When a contractor signs up through your link and closes their first deal, you earn <strong style="color:var(--teal);font-weight:600;">$500</strong>.
      </div>
      <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--divider);display:flex;align-items:center;gap:16px;">
        <img id="refQrCode" src="" alt="QR Code" onerror="this.style.display='none'" style="width:120px;height:120px;border-radius:4px;background:white;padding:4px;display:none;" />
        <div style="font-size:10px;color:var(--fg3);line-height:1.5;">
          <strong style="color:var(--teal);font-weight:600;">Scan to share</strong> — print this QR code on flyers, business cards, or job site boards. Anyone who scans it lands on the contractor sign-up page with your referral code pre-attached.
        </div>
      </div>

    <div class="grid" style="margin-bottom:20px;">
      <div class="card"><div class="card-label">Contractors Referred</div><div class="card-value" id="ref-total">--</div></div>
      <div class="card"><div class="card-label">Signed Up</div><div class="card-value cyan" id="ref-signed">--</div></div>
      <div class="card"><div class="card-label">Bounties Earned</div><div class="card-value teal" id="ref-earned">$0.00</div></div>
      <div class="card"><div class="card-label">Pending Bounties</div><div class="card-value" id="ref-pending">0</div></div>
      <div class="card"><div class="card-label">Bounties Paid</div><div class="card-value teal" id="ref-paid">$0.00</div></div>
    </div>

    <!-- ── Payout Request Section ── -->
    <div class="section">
      <div class="section-title"><strong>Request Payout</strong></div>
      <div style="background:var(--bg2);border:1px solid var(--divider);padding:20px;">
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:14px;">
          <div>
            <div style="font-family:var(--mono);font-size:8px;color:var(--fg3);letter-spacing:0.14em;text-transform:uppercase;margin-bottom:4px;">Available for Payout</div>
            <div style="font-size:28px;font-weight:200;color:var(--teal);" id="payout-available">$0.00</div>
          </div>
          <div id="payout-status" style="display:none;font-family:var(--mono);font-size:10px;color:var(--teal);padding:8px 14px;background:rgba(68,229,184,0.06);border:1px solid rgba(68,229,184,0.2);"></div>
        </div>
        <div style="margin-bottom:14px;">
          <label style="font-family:var(--mono);font-size:8px;color:var(--fg3);letter-spacing:0.14em;text-transform:uppercase;margin-bottom:4px;display:block;">USDC Wallet (Solana)</label>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <input type="text" id="payout-wallet" placeholder="Your Solana wallet address for USDC..."
                   style="flex:1;min-width:200px;background:rgba(0,0,0,0.4);color:var(--fg);border:1px solid var(--divider);font-family:var(--mono);font-size:12px;padding:10px 12px;outline:none;" />
            <button id="payout-btn" onclick="requestPayout()"
                    style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;background:var(--amber);color:#000;border:none;padding:10px 18px;cursor:pointer;font-weight:600;white-space:nowrap;">Request Payout</button>
          </div>
          <div style="font-family:var(--mono);font-size:8px;color:var(--fg3);margin-top:6px;">Leave blank to use your default payout method (USDC).</div>
        </div>
        <div id="payout-err" style="display:none;font-family:var(--mono);font-size:10px;color:var(--red);padding:8px 12px;background:rgba(244,63,94,0.06);border:1px solid rgba(244,63,94,0.2);margin-bottom:10px;"></div>
      </div>
    </div>

    <div class="section-title"><strong>Referral History</strong></div>
    <table>
      <thead><tr><th>Date</th><th>Contractor</th><th>Company</th><th>Metro</th><th>Status</th><th>Bounty</th><th>Bounty Status</th></tr></thead>
      <tbody id="referralsBody">
        <tr><td class="empty" colspan="7">Loading...</td></tr>
      </tbody>
    </table>

    <!-- ── Payout History ── -->
    <div class="section-title" style="margin-top:28px;"><strong>Payout History</strong></div>
    <table>
      <thead><tr><th>Date</th><th class="num">Amount</th><th>Status</th><th>TX ID</th><th>Method</th></tr></thead>
      <tbody id="payoutHistoryBody">
        <tr><td class="empty" colspan="5">No payouts yet</td></tr>
      </tbody>
    </table>

    <!-- ── Referral Leaderboard ── -->
    <div class="section-title" style="margin-top:28px;"><strong>Referral Leaderboard</strong> <span class="count" id="lb-total">—</span></div>
    <table>
      <thead><tr><th class="num">#</th><th>Referrer</th><th class="num">Referred</th><th class="num">Total Earned</th><th class="num">Paid</th></tr></thead>
      <tbody id="leaderboardBody">
        <tr><td class="empty" colspan="5">Loading...</td></tr>
      </tbody>
    </table>
    <div style="font-family:var(--mono);font-size:8px;color:var(--fg3);margin-top:8px;text-align:right;letter-spacing:0.04em;">Across all contractors · updated on page load</div>
  </div>

  <!-- ── Contractor Profile Modal ── -->
  <div class="modal-overlay" id="profileModal" onclick="if(event.target===this)closeProfileModal()">
    <div class="modal-box">
      <button class="modal-close" onclick="closeProfileModal()">✕</button>
      <div id="pmContent">
        <div class="modal-name" id="pmName">Loading...</div>
        <div class="modal-meta-sub" id="pmMetro">—</div>
        <div class="modal-stat"><span class="modal-stat-label">Trust Score</span><span class="modal-stat-value" id="pmTrust">—</span></div>
        <div class="modal-stat"><span class="modal-stat-label">Specialties</span><span class="modal-stat-value" id="pmSpecs">—</span></div>
      </div>
    </div>
  </div>

  <div id="tab-profile" class="tab-content">
    <div class="section-title"><strong>Edit Your Profile</strong></div>
    <div class="profile-form">
      <div class="field">
        <label>Company Name</label>
        <input type="text" id="pf-name" value="{ctr_name.replace('"', '&quot;')}" maxlength="200">
      </div>
      <div class="field">
        <label>Metro / Service Area</label>
        <input type="text" id="pf-metro" value="{metro.replace('"', '&quot;')}" maxlength="120">
      </div>
      <div class="field">
        <label>Phone</label>
        <input type="tel" id="pf-phone" value="{str(contractor.get('phone','')).replace('"', '&quot;')}" maxlength="20">
      </div>
      <div class="field">
        <label>License #</label>
        <input type="text" id="pf-license" value="{str(contractor.get('license_no','') or '').replace('"', '&quot;')}" maxlength="80">
      </div>
      <div class="field field-full">
        <label>Specialties (comma separated)</label>
        <input type="text" id="pf-specialties" value="{', '.join(specialties) if specialties else ''}" maxlength="300" placeholder="roofing, restoration, hvac, ...">
      </div>
      <div class="field field-full" style="margin-top:8px;">
        <button onclick="saveProfile()">Save Changes</button>
      </div>
    </div>
    <div id="profile-flash" style="font-family:var(--mono);font-size:10px;margin-top:8px;"></div>
  </div>
</div>
<script>
const CTR_ID = {pid_json};
const BASE_URL = {base_json};

async function apiFetch(path, opts) {{
  const r = await fetch(path, {{ credentials: 'include', ...opts }});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}}

function fmtCurrency(v) {{
  if (v === null || v === undefined) return '$0.00';
  return '$' + Number(v).toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
}}

function fmtDate(ts) {{
  if (!ts) return '--';
  return ts.slice(0, 10);
}}

function _esc(s) {{
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;').replace(/'/g, '&#39;');
}}

function statusBadge(status) {{
  var cls = (status || 'sent').toLowerCase();
  var labels = {{ sent: 'Sent', accepted: 'Accepted', completed: 'Completed', ghosted: 'Ghosted', expired: 'Expired', rejected: 'Rejected' }};
  return '<span class="badge ' + cls + '">' + (labels[cls] || cls) + '</span>';
}}

// ── Overview Stats ──────────────────────────────────────────────
async function loadStats() {{
  try {{
    const d = await apiFetch('/api/v1/contractors/' + CTR_ID + '/stats');
    document.getElementById('stat-total').textContent = d.total_dispatches || 0;
    document.getElementById('stat-accepted').textContent = d.accepted || 0;
    document.getElementById('stat-completed').textContent = d.completed || 0;
    document.getElementById('stat-ghosted').textContent = d.ghosted || 0;
    document.getElementById('stat-earnings').textContent = fmtCurrency(d.earnings);
    document.getElementById('stat-trust').textContent = d.trust_score || '--';
    document.getElementById('earnings-total').textContent = fmtCurrency(d.earnings);
    document.getElementById('earnings-jobs').textContent = d.completed || 0;
    document.getElementById('earnings-fees').textContent = fmtCurrency(d.fee_revenue || 0);
  }} catch (e) {{
    document.querySelectorAll('#statsGrid .card-value').forEach(function(el) {{ el.textContent = 'err'; }});
  }}
  // Also load referral summary for overview
  loadReferralSummary();
  // Load your referral rank
  loadYourRank();
}}

async function loadReferralSummary() {{
  try {{
    const d = await apiFetch('/api/v1/contractors/' + CTR_ID + '/referrals');
    document.getElementById('stat-ref-earned').textContent = fmtCurrency(d.total_earned);
    document.getElementById('stat-ref-pending').textContent = d.pending_count || 0;
    // Update overview quick-view
    document.getElementById('ov-ref-earned').textContent = fmtCurrency(d.total_earned);
    document.getElementById('ov-ref-pending-count').textContent = d.pending_count || 0;
    document.getElementById('ov-ref-total').textContent = d.total || 0;
    const statusEl = document.getElementById('ov-ref-status');
    if (d.total && d.total > 0) {{
      statusEl.textContent = d.total + ' referral' + (d.total === 1 ? '' : 's');
      statusEl.style.color = 'var(--teal)';
    }} else {{
      statusEl.textContent = 'No referrals yet';
      statusEl.style.color = 'var(--fg3)';
    }}
  }} catch (e) {{
    /* non-critical */
  }}
}}

// ── Dispatches ───────────────────────────────────────────────────
async function loadDispatches() {{
  try {{
    const d = await apiFetch('/api/v1/contractors/' + CTR_ID + '/dispatches');
    const tbody = document.getElementById('dispatchesBody');
    if (!d.dispatches || d.dispatches.length === 0) {{
      tbody.innerHTML = '<tr><td class="empty" colspan="6">No dispatches yet</td></tr>';
      return;
    }}
    tbody.innerHTML = d.dispatches.map(function(dp) {{
      var meta = dp.meta || {{}};
      var metro = meta.lead_metro || '--';
      var accepted = dp.accepted_at ? fmtDate(dp.accepted_at) : '--';
      var completed = dp.completed_at ? fmtDate(dp.completed_at) : '--';
      return '<tr>' +
        '<td>' + fmtDate(dp.created_at) + '</td>' +
        '<td>' + _esc(metro) + '</td>' +
        '<td class="num">' + (dp.match_score ? (dp.match_score * 100).toFixed(0) + '%' : '--') + '</td>' +
        '<td>' + statusBadge(dp.status) + '</td>' +
        '<td>' + accepted + '</td>' +
        '<td>' + completed + '</td>' +
      '</tr>';
    }}).join('');
  }} catch (e) {{
    document.getElementById('dispatchesBody').innerHTML = '<tr><td class="empty" colspan="6">Failed to load</td></tr>';
  }}
}}

// ── Earnings ────────────────────────────────────────────────────
async function loadEarnings() {{
  try {{
    const d = await apiFetch('/api/v1/contractors/' + CTR_ID + '/earnings');
    const tbody = document.getElementById('earningsBody');
    if (!d.payouts || d.payouts.length === 0) {{
      tbody.innerHTML = '<tr><td class="empty" colspan="4">No payouts yet</td></tr>';
      return;
    }}
    tbody.innerHTML = d.payouts.map(function(p) {{
      return '<tr>' +
        '<td>' + fmtDate(p.created_at) + '</td>' +
        '<td>' + _esc(p.dispatch_id || '--') + '</td>' +
        '<td class="num">' + fmtCurrency(p.amount) + '</td>' +
        '<td>' + _esc(p.status || 'pending') + '</td>' +
      '</tr>';
    }}).join('');
  }} catch (e) {{
    document.getElementById('earningsBody').innerHTML = '<tr><td class="empty" colspan="4">Failed to load</td></tr>';
  }}
}}

// ── Profile ────────────────────────────────────────────────────
async function saveProfile() {{
  var name = document.getElementById('pf-name').value.trim();
  var metro = document.getElementById('pf-metro').value.trim();
  var phone = document.getElementById('pf-phone').value.trim();
  var license = document.getElementById('pf-license').value.trim();
  var specialtiesRaw = document.getElementById('pf-specialties').value.trim();
  var specialties = specialtiesRaw ? specialtiesRaw.split(',').map(function(s) {{ return s.trim(); }}).filter(Boolean) : [];
  var flash = document.getElementById('profile-flash');

  try {{
    var r = await fetch('/api/v1/contractors/' + CTR_ID + '/profile', {{
      method: 'PATCH',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        name: name || undefined,
        metro: metro || undefined,
        phone: phone || undefined,
        license_no: license || undefined,
        specialties: specialties.length > 0 ? specialties : undefined,
      }}),
    }});
    var d = await r.json();
    if (r.ok && d.ok) {{
      flash.style.color = 'var(--teal)';
      flash.textContent = '✓ Profile updated successfully';
      if (d.trust_penalty) {{
        flash.textContent += ' (note: ' + d.trust_penalty + ')';
      }}
      loadStats();
    }} else {{
      flash.style.color = 'var(--red)';
      flash.textContent = '✗ ' + (d.error || 'Update failed');
    }}
  }} catch (e) {{
    flash.style.color = 'var(--red)';
    flash.textContent = '✗ Network error';
  }}
}}

// ── Tab Switching ──────────────────────────────────────────────
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(function(t) {{ t.classList.remove('active'); }});
  document.querySelectorAll('.tab-content').forEach(function(t) {{ t.classList.remove('active'); }});
  var tabs = document.querySelectorAll('.tab');
  var tabMap = {{ overview: 0, dispatches: 1, earnings: 2, referrals: 3, profile: 4 }};
  if (tabMap[name] !== undefined && tabs[tabMap[name]]) {{
    tabs[tabMap[name]].classList.add('active');
  }}
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'dispatches') loadDispatches();
  if (name === 'earnings') loadEarnings();
  if (name === 'referrals') {{
    loadReferrals();
    loadLeaderboard();
  }}
}}

// ── Referral Link ──────────────────────────────────────────────
let referralCode = null;

async function loadReferralLink() {{
  try {{
    const d = await apiFetch('/api/v1/contractors/' + CTR_ID + '/referral-link');
    if (d.referral_code) {{
      referralCode = d.referral_code;
      const link = window.location.origin + '/ref/contractor/' + d.referral_code;
      document.getElementById('referralLinkDisplay').textContent = link;
      // Also update overview link
      const ovEl = document.getElementById('ovRefLink');
      if (ovEl) ovEl.textContent = link;
      // Update nav bar link
      const navEl = document.getElementById('navRefLink');
      const navSection = document.getElementById('navRefSection');
      if (navEl) {{ navEl.textContent = link; navEl.title = 'Referral link: ' + link; }}
      if (navSection) navSection.style.display = 'flex';
      // Set QR code images (use a free QR code API)
      const encoded = encodeURIComponent(link);
      const qrSrc = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encoded;
      const ovQr = document.getElementById('ovQrCode');
      if (ovQr) {{ ovQr.src = qrSrc; ovQr.style.display = 'inline'; }}
      const refQr = document.getElementById('refQrCode');
      if (refQr) {{ refQr.src = qrSrc; refQr.style.display = 'inline'; }}
    }}
  }} catch (e) {{
    const msg = 'Could not load referral link';
    document.getElementById('referralLinkDisplay').textContent = msg;
    const ovEl = document.getElementById('ovRefLink');
    if (ovEl) ovEl.textContent = msg;
  }}
}}

function copyNavRefLink() {{
  const el = document.getElementById('navRefLink');
  if (!el) return;
  const link = el.textContent;
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  navigator.clipboard.writeText(link).then(function() {{
    const btn = document.querySelector('#navRefSection button');
    if (btn) {{
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      btn.style.borderColor = 'var(--teal)';
      btn.style.color = 'var(--teal)';
      setTimeout(function() {{
        btn.textContent = orig;
        btn.style.borderColor = 'rgba(255,184,0,0.3)';
        btn.style.color = 'var(--amber)';
      }}, 2000);
    }}
  }}).catch(function() {{}});
}}

function copyReferralLink() {{
  const el = document.getElementById('referralLinkDisplay');
  const link = el.textContent;
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  navigator.clipboard.writeText(link).then(function() {{
    const orig = el.textContent;
    el.textContent = '✓ Copied!';
    el.style.color = 'var(--teal)';
    setTimeout(function() {{
      el.textContent = orig;
      el.style.color = 'var(--cyan)';
    }}, 2000);
  }}).catch(function() {{}});
}}

function copyOvRefLink() {{
  const el = document.getElementById('ovRefLink');
  const link = el.textContent;
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  navigator.clipboard.writeText(link).then(function() {{
    const orig = el.textContent;
    el.textContent = '✓ Copied!';
    el.style.color = 'var(--teal)';
    setTimeout(function() {{
      el.textContent = orig;
      el.style.color = 'var(--amber)';
    }}, 2000);
  }}).catch(function() {{}});
}}

function trackShareClick(platform) {{
  if (!platform) return;
  try {{
    navigator.sendBeacon('/api/v1/track/share-click',
      new Blob([JSON.stringify({{platform: platform}})], {{type: 'application/json'}}));
  }} catch(e) {{}}
}}

function shareViaSms(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  const msg = encodeURIComponent(
    'Check out Empire AI - earn $500 per contractor you refer! Use my link: ' + link
  );
  trackShareClick('sms');
  window.location.href = 'sms:?body=' + msg;
}}

function shareViaWhatsApp(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  const msg = encodeURIComponent(
    'Check out Empire AI - earn $500 per contractor you refer! Use my link: ' + link
  );
  trackShareClick('whatsapp');
  window.location.href = 'whatsapp://send?text=' + msg;
}}

// ── Your Referral Rank ───────────────────────────────────────────
async function loadYourRank() {{
  try {{
    const d = await apiFetch('/api/v1/referral-leaderboard?limit=50&current_contractor_id=' + encodeURIComponent(CTR_ID));
    const rankEl = document.getElementById('stat-ref-rank');
    const metaEl = document.getElementById('stat-ref-rank-meta');
    if (!rankEl) return;
    if (d.your_rank && d.your_rank.rank) {{
      const rank = d.your_rank.rank;
      const total = d.total_referrers || 0;
      const medal = rank === 1 ? '\\uD83E\\uDD47 ' : (rank === 2 ? '\\uD83E\\uDD48 ' : (rank === 3 ? '\\uD83E\\uDD49 ' : ''));
      rankEl.textContent = medal + '#' + rank;
      rankEl.className = 'card-value' + (rank <= 3 ? ' amber' : '');
      if (metaEl) metaEl.textContent = 'of ' + total + ' referrer' + (total === 1 ? '' : 's');
    }} else {{
      rankEl.textContent = 'Not ranked';
      rankEl.className = 'card-value';
      if (metaEl) metaEl.textContent = 'Refer others to earn bounties';
    }}
  }} catch (e) {{
    /* non-critical */
    const rankEl = document.getElementById('stat-ref-rank');
    if (rankEl) rankEl.textContent = '--';
    if (rankEl) rankEl.className = 'card-value';
  }}
}}

function shareViaTelegram(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  const msg = encodeURIComponent(
    'Check out Empire AI - earn $500 per contractor you refer! Use my link: ' + link
  );
  trackShareClick('telegram');
  window.location.href = 'tg://msg_url?text=' + msg;
}}

function shareViaEmail(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  const subj = encodeURIComponent('Empire AI - Contractor Referral');
  const body = encodeURIComponent(
    'Check out Empire AI - earn $500 per contractor you refer! Use my link: ' + link
  );
  trackShareClick('email');
  window.location.href = 'mailto:?subject=' + subj + '&body=' + body;
}}

function shareViaTwitter(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  const msg = encodeURIComponent(
    'Earn $500 per contractor you refer to Empire AI! Use my link: ' + link
  );
  trackShareClick('x');
  window.location.href = 'https://twitter.com/intent/tweet?text=' + msg;
}}

function shareViaLinkedIn(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  trackShareClick('linkedin');
  window.location.href = 'https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(link);
}}

function shareViaFacebook(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  trackShareClick('facebook');
  window.location.href = 'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(link);
}}

function shareViaReddit(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  trackShareClick('reddit');
  window.location.href = 'https://www.reddit.com/submit?url=' + encodeURIComponent(link);
}}

function shareViaPinterest(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  trackShareClick('pinterest');
  window.location.href = 'https://www.pinterest.com/pin/create/button/?url=' + encodeURIComponent(link);
}}

function shareViaMessenger(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  trackShareClick('messenger');
  window.location.href = 'fb-messenger://share/?link=' + encodeURIComponent(link);
}}

function shareViaTikTok(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  trackShareClick('tiktok');
  var text = 'Check out Empire AI - earn $500 per contractor you refer! Use my link: ' + link;
  // Try Web Share API (mobile) first, fall back to clipboard
  if (navigator.share) {{
    navigator.share({{ text: text }}).catch(function() {{}});
  }} else {{
    navigator.clipboard.writeText(text).then(function() {{
      document.querySelectorAll('button[onclick*="shareViaTikTok"]').forEach(function(btn) {{
        var orig = btn.textContent;
        btn.textContent = 'Copied!';
        btn.style.borderColor = 'var(--teal)';
        btn.style.color = 'var(--teal)';
        setTimeout(function() {{
          btn.textContent = orig;
          btn.style.borderColor = '';
          btn.style.color = '';
        }}, 2000);
      }});
    }}).catch(function() {{}});
  }}
}}

function shareViaSnapchat(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  trackShareClick('snapchat');
  window.location.href = 'https://www.snapchat.com/share?link=' + encodeURIComponent(link);
}}

function toggleMoreShare(id) {{
  const div = document.getElementById('more-share-' + id);
  const btn = document.getElementById('more-toggle-' + id);
  if (!div || !btn) return;
  const isHidden = div.style.display === 'none' || div.style.display === '';
  div.style.display = isHidden ? 'flex' : 'none';
  btn.textContent = isHidden ? '▲ Less' : '+ More';
  btn.style.borderColor = isHidden ? 'var(--teal)' : 'var(--divider)';
  btn.style.color = isHidden ? 'var(--teal)' : 'var(--fg3)';
}}

function copyMessage(link) {{
  if (!link || link === 'Loading...' || link === 'Could not load referral link') return;
  const text = 'Check out Empire AI - earn $500 per contractor you refer! Use my link: ' + link;
  trackShareClick('copy_msg');
  navigator.clipboard.writeText(text).then(function() {{
    // Flash feedback on all Copy Msg buttons
    document.querySelectorAll('button[onclick*="copyMessage"]').forEach(function(btn) {{
      var orig = btn.textContent;
      btn.textContent = 'Copied!';
      btn.style.borderColor = 'var(--teal)';
      btn.style.color = 'var(--teal)';
      setTimeout(function() {{
        btn.textContent = orig;
        btn.style.borderColor = '';
        btn.style.color = '';
      }}, 2000);
    }});
  }}).catch(function() {{}});
}}

// ── Referrals ────────────────────────────────────────────────────
async function loadReferrals() {{
  try {{
    const d = await apiFetch('/api/v1/contractors/' + CTR_ID + '/referrals');
    document.getElementById('ref-total').textContent = d.total || 0;
    document.getElementById('ref-signed').textContent = d.signed_up || 0;
    document.getElementById('ref-earned').textContent = fmtCurrency(d.total_earned);
    document.getElementById('ref-pending').textContent = d.pending_count || 0;
    document.getElementById('ref-paid').textContent = fmtCurrency(d.total_paid);

    // Update payout section: earned bounties not yet paid = available for payout
    const available = d.available_for_payout || 0;
    document.getElementById('payout-available').textContent = fmtCurrency(available);
    const payoutBtn = document.getElementById('payout-btn');
    if (available > 0) {{
      payoutBtn.disabled = false;
      payoutBtn.textContent = 'Request Payout — ' + fmtCurrency(available);
    }} else {{
      payoutBtn.disabled = true;
      payoutBtn.textContent = 'No bounties available';
    }}

    const tbody = document.getElementById('referralsBody');
    if (!d.referrals || d.referrals.length === 0) {{
      tbody.innerHTML = '<tr><td class="empty" colspan="7">No referrals yet. Share your link to start earning $500 per contractor who signs up and closes their first deal.</td></tr>';
      return;
    }}
    tbody.innerHTML = d.referrals.map(function(r) {{
      const bountyStatus = r.bounty_status || 'pending';
      const bountyLabel = {{ pending: 'Pending', earned: 'Earned \u2713', paid: 'Paid', cancelled: 'Cancelled', payout_requested: 'Payout Requested' }};
      const bountyColor = {{ pending: 'var(--fg3)', earned: 'var(--teal)', paid: 'var(--teal)', cancelled: 'var(--red)', payout_requested: 'var(--amber)' }};
      const refStatus = r.referral_status || 'new';
      return '<tr>' +
        '<td>' + fmtDate(r.created_at) + '</td>' +
        '<td>' + _esc(r.referred_name || '--') + '</td>' +
        '<td>' + _esc(r.referred_company || '--') + '</td>' +
        '<td>' + _esc(r.referred_metro || '--') + '</td>' +
        '<td>' + _esc(refStatus) + '</td>' +
        '<td class="num" style="font-weight:600">$' + (r.bounty_amount || 500).toLocaleString() + '</td>' +
        '<td style="color:' + (bountyColor[bountyStatus] || 'var(--fg3)') + ';font-weight:600">' + (bountyLabel[bountyStatus] || bountyStatus) + '</td>' +
      '</tr>';
    }}).join('');

    // Render payout history
    const payoutBody = document.getElementById('payoutHistoryBody');
    if (d.payout_history && d.payout_history.length > 0) {{
      payoutBody.innerHTML = d.payout_history.map(function(p) {{
        const pStatus = p.status || 'paid';
        const dt = p.paid_at || p.created_at;
        const txId = p.payout_tx_id || '';
        const pMethod = p.payout_method || 'usdc';
        return '<tr>' +
          '<td>' + fmtDate(dt) + '</td>' +
          '<td class="num" style="font-weight:600">$' + Number(p.bounty_amount).toLocaleString(undefined, {{ minimumFractionDigits: 2 }}) + '</td>' +
          '<td><span class="badge ' + (pStatus === 'paid' ? 'sent' : (pStatus === 'cancelled' ? 'expired' : '')) + '">' + _esc(pStatus) + '</span></td>' +
          '<td style="font-size:9px;color:var(--fg3);font-family:var(--mono);max-width:120px;overflow:hidden;text-overflow:ellipsis" title="' + _esc(txId) + '">' + (txId ? txId.slice(0, 12) + '…' : '—') + '</td>' +
          '<td style="font-size:9px;color:var(--fg3);font-family:var(--mono)">' + _esc(pMethod) + '</td>' +
        '</tr>';
      }}).join('');
    }} else {{
      payoutBody.innerHTML = '<tr><td class="empty" colspan="5">No payouts yet</td></tr>';
    }}
  }} catch (e) {{
    document.getElementById('referralsBody').innerHTML = '<tr><td class="empty" colspan="7">Failed to load referrals</td></tr>';
  }}
}}

// ── Referral Leaderboard ────────────────────────────────────────────
async function loadLeaderboard() {{
  try {{
    const d = await apiFetch('/api/v1/referral-leaderboard?current_contractor_id=' + encodeURIComponent(CTR_ID));
    const tbody = document.getElementById('leaderboardBody');
    const totalEl = document.getElementById('lb-total');
    if (totalEl) totalEl.textContent = d.total_referrers + ' referrer' + (d.total_referrers === 1 ? '' : 's');
    if (!d.leaderboard || d.leaderboard.length === 0) {{
      tbody.innerHTML = '<tr><td class="empty" colspan="5">No referrals with earned bounties yet — be the first!</td></tr>';
      return;
    }}
    var rows = d.leaderboard.map(function(e) {{
      var rankCls = e.rank === 1 ? 'color:var(--amber);font-weight:700' : (e.rank <= 3 ? 'color:var(--teal);font-weight:600' : 'color:var(--fg3)');
      var medal = e.rank === 1 ? '\\uD83E\\uDD47 ' : (e.rank === 2 ? '\\uD83E\\uDD48 ' : (e.rank === 3 ? '\\uD83E\\uDD49 ' : ''));
      var bgStyle = e.is_you ? 'background:rgba(68,229,184,0.08);outline:1px solid rgba(68,229,184,0.25);' : '';
      var nameLabel = e.is_you ? '<strong style="color:var(--teal)">' + _esc(e.name) + ' ← You</strong>' : '<span style="color:var(--fg2);cursor:pointer;border-bottom:1px dotted var(--fg3)" onclick="showContractorProfile('' + _esc(e.id || '') + '')">' + _esc(e.name) + '</span>';
      return '<tr style="' + bgStyle + '">' +
        '<td class="num" style="' + rankCls + '">' + medal + e.rank + '</td>' +
        '<td style="font-weight:600">' + nameLabel + '</td>' +
        '<td class="num">' + e.total_referrals + '</td>' +
        '<td class="num" style="color:var(--amber);font-weight:600">' + fmtCurrency(e.total_earned) + '</td>' +
        '<td class="num" style="color:var(--teal)">' + fmtCurrency(e.total_paid) + '</td>' +
      '</tr>';
    }}).join('');

    // If the logged-in contractor is outside the top 10, add a "Your Position" row
    if (d.your_rank && d.your_rank.rank > 10) {{
      rows += '<tr style="border-top:2px solid var(--divider)"><td class="empty" colspan="5" style="font-family:var(--mono);font-size:8px;color:var(--fg3);padding:6px 14px;text-align:center;letter-spacing:0.08em;text-transform:uppercase;">Your Position</td></tr>';
      rows += '<tr style="background:rgba(68,229,184,0.08);outline:1px solid rgba(68,229,184,0.25);">' +
        '<td class="num" style="color:var(--teal);font-weight:700">' + d.your_rank.rank + '</td>' +
        '<td style="font-weight:600;color:var(--teal)">' + _esc(d.your_rank.name) + ' ← You</td>' +
        '<td class="num">' + d.your_rank.total_referrals + '</td>' +
        '<td class="num" style="color:var(--amber);font-weight:600">' + fmtCurrency(d.your_rank.total_earned) + '</td>' +
        '<td class="num" style="color:var(--teal)">' + fmtCurrency(d.your_rank.total_paid) + '</td>' +
      '</tr>';
    }}

    tbody.innerHTML = rows;
  }} catch (e) {{
    document.getElementById('leaderboardBody').innerHTML = '<tr><td class="empty" colspan="5">Failed to load leaderboard</td></tr>';
  }}
}}

// ── Request Payout ────────────────────────────────────────────────
async function requestPayout() {{
  const btn = document.getElementById('payout-btn');
  const wallet = document.getElementById('payout-wallet').value.trim();
  const statusEl = document.getElementById('payout-status');
  const errEl = document.getElementById('payout-err');

  statusEl.style.display = 'none';
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Requesting...';

  try {{
    const r = await fetch('/api/v1/contractors/' + CTR_ID + '/bounty-payout-request', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        payout_method: wallet ? 'usdc' : 'usdc',
        payout_address: wallet || '',
      }}),
      credentials: 'include',
    }});
    const d = await r.json();
    if (r.ok && d.ok) {{
      statusEl.style.display = 'block';
      statusEl.textContent = '✓ Payout requested! ' + fmtCurrency(d.total_amount) + ' (' + d.payout_count + ' bounties) — we\'ll process within 30 days.';
      // Reset UI
      document.getElementById('payout-available').textContent = '$0.00';
      btn.textContent = 'No bounties available';
      // Refresh referral stats
      loadReferrals();
    }} else {{
      errEl.style.display = 'block';
      errEl.textContent = '✗ ' + (d.error || 'Request failed. Please try again.');
      btn.disabled = false;
      btn.textContent = 'Request Payout';
    }}
  }} catch (e) {{
    errEl.style.display = 'block';
    errEl.textContent = '✗ Network error. Please try again.';
    btn.disabled = false;
    btn.textContent = 'Request Payout';
  }}
}}

// ── Contractor Profile Modal (from leaderboard click) ──────────
async function showContractorProfile(ctrId) {{
  const overlay = document.getElementById('profileModal');
  const nameEl = document.getElementById('pmName');
  const metroEl = document.getElementById('pmMetro');
  const trustEl = document.getElementById('pmTrust');
  const specsEl = document.getElementById('pmSpecs');
  nameEl.textContent = 'Loading...';
  metroEl.textContent = '';
  trustEl.textContent = '';
  specsEl.textContent = '';
  overlay.classList.add('show');
  try {{
    const r = await fetch('/api/v1/contractor-public/' + encodeURIComponent(ctrId));
    const d = await r.json();
    if (d.ok) {{
      nameEl.textContent = _esc(d.name);
      metroEl.textContent = _esc(d.metro || '—');
      trustEl.textContent = d.trust_score != null ? d.trust_score.toFixed(1) + ' / 10' : '—';
      specsEl.textContent = d.specialties && d.specialties.length > 0 ? _esc(d.specialties.join(', ')) : '—';
    }} else {{
      nameEl.textContent = 'Not found';
    }}
  }} catch (e) {{
    nameEl.textContent = 'Error loading profile';
  }}
}}
function closeProfileModal() {{
  document.getElementById('profileModal').classList.remove('show');
}}

loadStats();
loadReferralLink();
</script>
</body></html>"""


# ── ROUTES ───────────────────────────────────────────────────────────
def register_contractor_portal_routes(
    app: FastAPI,
    *,
    sign_token: Callable,
    verify_token: Callable,
    send_email: Callable,
    public_base_url: str,
):
    """Register contractor portal routes + referral tracking routes.

    Also registers the public /ref/contractor/{code} tracking endpoint
    and its companion register_contractor_referral_tracking_routes().
    """
    # Always register the tracking routes (no auth required)
    register_contractor_referral_tracking_routes(app, public_base_url=public_base_url)

    # ── PUBLIC: LOGIN PAGE ────────────────────────────────────────────
    @app.get("/portal/contractors/login", response_class=HTMLResponse)
    async def ctr_login_page():
        return HTMLResponse(_CTR_LOGIN_PAGE)

    # ── PUBLIC: SEND MAGIC LINK ───────────────────────────────────────
    @app.post("/api/v1/contractors/portal/login")
    async def ctr_send_link(request: Request):
        """Send a magic link to a contractor's email. The email must match
        an active contractor. Returns {ok: True} even if email not found."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        email = (body.get("email") or "").lower().strip()
        if not email or "@" not in email:
            raise HTTPException(400, "Valid email required")

        try:
            res = _SB.table("contractors").select("id, name, email, phone, active, metro") \
                .eq("email", email).limit(1).execute()
            if not res.data or not res.data[0].get("active"):
                log.info(f"[contractor_portal] login attempt for unknown/inactive: {email}")
                return {"ok": True}
            contractor = res.data[0]
        except Exception as e:
            log.error(f"[contractor_portal] DB lookup failed: {e}")
            return {"ok": False, "error": "Service error"}

        # Build magic link token
        payload = {
            "contractor_id": str(contractor["id"]),
            "email": email,
            "exp": int(time.time()) + LOGIN_LINK_TTL_SECONDS,
            "iat": int(time.time()),
            "kind": "contractor_login",
        }
        token = sign_token(payload)
        link = f"{public_base_url.rstrip('/')}/portal/contractors/{contractor['id']}/verify?t={token}"

        html = f"""
          <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
            <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
              <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Contractor Portal</div>
              <div style="font-size:20px;font-weight:700;color:#44E5B8;margin-top:6px;">Your login link</div>
            </div>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              Hi {contractor['name']}, click below to sign in to your contractor dashboard.
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
                subject="Empire AI · Your contractor login link",
                html=html,
            )
            if not result.get("ok"):
                log.error(f"[contractor_portal] email send failed: {result.get('error', 'unknown')}")
                return {"ok": False, "error": "Could not send login email"}
            log.info(f"[contractor_portal] login link sent to {email}")
            return {"ok": True}
        except Exception as e:
            log.error(f"[contractor_portal] email send error: {e}")
            return {"ok": False, "error": "Could not send login email"}

    # ── PUBLIC: VERIFY MAGIC LINK ─────────────────────────────────────
    @app.get("/portal/contractors/{contractor_id}/verify", response_class=HTMLResponse)
    async def ctr_verify(request: Request, contractor_id: str, t: str = Query(...)):
        """Verify magic link token. If valid, create session cookie and redirect to dashboard."""
        decoded = verify_token(t)
        if not decoded or decoded.get("kind") != "contractor_login":
            return HTMLResponse("""
                <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                <div style="text-align:center;"><h1 style="font-weight:200;">Link invalid</h1>
                <p style="color:#7a8ca3;">This link has expired or is invalid.</p>
                <a href="/portal/contractors/login" style="color:#44e5b8;margin-top:16px;display:inline-block;">Request a new one →</a></div></body></html>
            """, status_code=401)

        if str(decoded.get("contractor_id", "")) != contractor_id:
            return HTMLResponse("<h1>Invalid link</h1>", status_code=401)

        try:
            res = _SB.table("contractors").select("*") \
                .eq("id", contractor_id).limit(1).execute()
            if not res.data or not res.data[0].get("active"):
                return HTMLResponse("""
                    <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                    <div><h1 style="font-weight:200;">Account inactive</h1>
                    <p style="color:#7a8ca3;">Your account is inactive. Contact Empire AI support to reactivate.</p></div></body></html>
                """, status_code=403)
            contractor = res.data[0]
        except Exception as e:
            log.error(f"[contractor_portal] verify lookup failed: {e}")
            return HTMLResponse("<h1>Service error</h1>", status_code=500)

        # Create session
        session_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        _CTR_SESSION_HASHES[token_hash] = {
            "contractor": {
                "id": str(contractor["id"]),
                "name": contractor["name"],
                "email": contractor["email"],
                "phone": contractor.get("phone", ""),
                "metro": contractor.get("metro", ""),
                "specialties": contractor.get("specialties", []),
                "trust_score": float(contractor.get("trust_score", 5.0)),
                "license_no": contractor.get("license_no", ""),
            },
            "expires_at": expires_at,
        }

        response = RedirectResponse(
            url=f"/portal/contractors/{contractor_id}/dashboard",
            status_code=302,
        )
        use_secure = public_base_url.startswith("https://")
        response.set_cookie(
            key="contractor_session",
            value=session_token,
            max_age=int(SESSION_TTL_HOURS * 3600),
            httponly=True,
            secure=use_secure,
            samesite="lax",
            path="/",
        )
        log.info(f"[contractor_portal] verified: {contractor['name']} ({contractor['email']})")
        return response

    # ── PUBLIC: DASHBOARD PAGE ────────────────────────────────────────
    @app.get("/portal/contractors/{contractor_id}/dashboard", response_class=HTMLResponse)
    async def ctr_dashboard(contractor_id: str, request: Request):
        """Render the contractor dashboard page. Requires valid session cookie."""
        contractor = _resolve_contractor(request)
        if not contractor or str(contractor.get("id", "")) != contractor_id:
            return HTMLResponse("""
                <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                <div style="text-align:center;"><h1 style="font-weight:200;">Sign in required</h1>
                <p style="color:#7a8ca3;">Please sign in to view your dashboard.</p>
                <a href="/portal/contractors/login" style="color:#44e5b8;margin-top:16px;display:inline-block;">Sign in →</a></div></body></html>
            """, status_code=401)

        # Refresh contractor data from DB
        try:
            refresh = _SB.table("contractors").select("name, metro, specialties, trust_score, license_no, phone") \
                .eq("id", contractor_id).limit(1).execute()
            if refresh.data:
                row = refresh.data[0]
                contractor["name"] = row.get("name", contractor["name"])
                contractor["metro"] = row.get("metro", contractor["metro"])
                contractor["specialties"] = row.get("specialties", contractor["specialties"])
                contractor["trust_score"] = float(row.get("trust_score", contractor["trust_score"]))
                contractor["license_no"] = row.get("license_no", contractor["license_no"])
                contractor["phone"] = row.get("phone", contractor["phone"])
        except Exception:
            pass

        return HTMLResponse(_contractor_dashboard(contractor, base_url=public_base_url))

    # ── PUBLIC: LOGOUT ────────────────────────────────────────────────
    @app.get("/portal/contractors/logout")
    async def ctr_logout(request: Request):
        """Clear session cookie."""
        token = request.cookies.get("contractor_session", "")
        if token:
            th = _hash_token(token)
            _CTR_SESSION_HASHES.pop(th, None)
        response = RedirectResponse(url="/portal/contractors/login", status_code=302)
        response.delete_cookie("contractor_session", path="/")
        return response

    # ── API: STATS ────────────────────────────────────────────────────
    @app.get("/api/v1/contractors/{contractor_id}/stats")
    async def ctr_stats(contractor_id: str, request: Request):
        """Return aggregate stats for a contractor."""
        contractor = _resolve_contractor(request)
        if not contractor or str(contractor.get("id", "")) != contractor_id:
            raise HTTPException(401, "Authentication required")

        try:
            # Get all dispatches for this contractor
            disp = _SB.table("dispatches").select("status, payout_amount") \
                .eq("contractor_id", contractor_id).execute()
            rows = disp.data or []

            total = len(rows)
            accepted = sum(1 for r in rows if r.get("status") == "accepted")
            completed = sum(1 for r in rows if r.get("status") in ("completed", "settled"))
            ghosted = sum(1 for r in rows if r.get("status") == "ghosted")
            earnings = sum(float(r.get("payout_amount", 0) or 0) for r in rows if r.get("status") in ("completed", "settled"))
            fee_revenue = round(earnings * 0.03, 2)  # 3% Empire fee on settled

            # Get trust score
            ctr_res = _SB.table("contractors").select("trust_score, completed_jobs") \
                .eq("id", contractor_id).limit(1).execute()
            trust = float(ctr_res.data[0].get("trust_score", 5.0)) if ctr_res.data else 5.0
            completed_jobs = ctr_res.data[0].get("completed_jobs", 0) if ctr_res.data else 0

            return {
                "total_dispatches": total,
                "accepted": accepted,
                "completed": completed,
                "ghosted": ghosted,
                "earnings": round(earnings, 2),
                "fee_revenue": round(fee_revenue, 2),
                "trust_score": trust,
                "completed_jobs": completed_jobs,
            }
        except Exception as e:
            log.error(f"[contractor_portal] stats error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: DISPATCHES ───────────────────────────────────────────────
    @app.get("/api/v1/contractors/{contractor_id}/dispatches")
    async def ctr_dispatches(
        contractor_id: str,
        request: Request,
        limit: int = Query(50, ge=1, le=200),
    ):
        """Return dispatch history for a contractor."""
        contractor = _resolve_contractor(request)
        if not contractor or str(contractor.get("id", "")) != contractor_id:
            raise HTTPException(401, "Authentication required")

        try:
            res = _SB.table("dispatches").select("*") \
                .eq("contractor_id", contractor_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()

            # Sanitize: remove token from response
            sanitized = []
            for row in (res.data or []):
                row.pop("token", None)
                sanitized.append(row)

            return {"dispatches": sanitized, "total": len(sanitized)}
        except Exception as e:
            log.error(f"[contractor_portal] dispatches error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: EARNINGS ─────────────────────────────────────────────────
    @app.get("/api/v1/contractors/{contractor_id}/earnings")
    async def ctr_earnings(
        contractor_id: str,
        request: Request,
        limit: int = Query(50, ge=1, le=200),
    ):
        """Return payout/earnings history for a contractor."""
        contractor = _resolve_contractor(request)
        if not contractor or str(contractor.get("id", "")) != contractor_id:
            raise HTTPException(401, "Authentication required")

        try:
            # First check for contractor_payouts table
            try:
                payouts_res = _SB.table("contractor_payouts").select("*") \
                    .eq("contractor_id", contractor_id) \
                    .order("created_at", desc=True) \
                    .limit(limit) \
                    .execute()
                if payouts_res.data:
                    return {"payouts": payouts_res.data, "total": len(payouts_res.data)}
            except Exception:
                pass

            # Fallback: derive from dispatches with payout_amount
            disp = _SB.table("dispatches").select("id, created_at, payout_amount, status, completed_at") \
                .eq("contractor_id", contractor_id) \
                .in_("status", ["completed", "settled"]) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()

            payouts = []
            for row in (disp.data or []):
                payouts.append({
                    "dispatch_id": row.get("id"),
                    "created_at": row.get("completed_at") or row.get("created_at"),
                    "amount": float(row.get("payout_amount", 0) or 0),
                    "status": row.get("status", "completed"),
                })

            return {"payouts": payouts, "total": len(payouts)}
        except Exception as e:
            log.error(f"[contractor_portal] earnings error: {e}")
            return {"payouts": [], "total": 0}

    # ── API: UPDATE PROFILE ───────────────────────────────────────────
    @app.patch("/api/v1/contractors/{contractor_id}/profile")
    async def ctr_update_profile(contractor_id: str, request: Request):
        """Update contractor profile fields (name, metro, phone, license_no, specialties)."""
        contractor = _resolve_contractor(request)
        if not contractor or str(contractor.get("id", "")) != contractor_id:
            raise HTTPException(401, "Authentication required")

        try:
            body = await request.json()
        except Exception:
            body = {}

        updates = {}
        trust_penalty = None

        name = body.get("name")
        if name is not None:
            name = str(name).strip()
            if len(name) > 200:
                raise HTTPException(400, "name too long")
            updates["name"] = name

        metro = body.get("metro")
        if metro is not None:
            metro = str(metro).strip()
            if len(metro) > 120:
                raise HTTPException(400, "metro too long")
            updates["metro"] = metro

        phone = body.get("phone")
        if phone is not None:
            phone = str(phone).strip()
            if len(phone) > 20:
                raise HTTPException(400, "phone too long")
            updates["phone"] = phone

        license_no = body.get("license_no")
        if license_no is not None:
            license_no = str(license_no).strip()
            if len(license_no) > 80:
                raise HTTPException(400, "license_no too long")
            updates["license_no"] = license_no or None

        specialties = body.get("specialties")
        if specialties is not None:
            if not isinstance(specialties, list):
                raise HTTPException(400, "specialties must be a list")
            if len(specialties) > 20:
                raise HTTPException(400, "too many specialties")
            # Applying a small trust penalty for changing specialties
            # (switching focus looks unreliable to the matching engine)
            old_ctr = _SB.table("contractors").select("specialties").eq("id", contractor_id).limit(1).execute()
            if old_ctr.data:
                old_specs = set(old_ctr.data[0].get("specialties", []) or [])
                new_specs = set(specialties)
                if old_specs and old_specs != new_specs:
                    trust_penalty = "Changing specialties may affect your match priority"
            updates["specialties"] = specialties

        if not updates:
            return {"ok": False, "error": "No fields to update"}

        try:
            _SB.table("contractors").update(updates).eq("id", contractor_id).execute()
            log.info(f"[contractor_portal] profile updated: {contractor_id}: {list(updates.keys())}")
            return {
                "ok": True,
                "updated": list(updates.keys()),
                "trust_penalty": trust_penalty,
            }
        except Exception as e:
            log.error(f"[contractor_portal] profile update error: {e}")
            raise HTTPException(500, str(e)[:200])

    # ── API: ACTIVE DISPATCH (accept from dashboard) ──────────────────
    @app.get("/api/v1/contractors/{contractor_id}/active-dispatch")
    async def ctr_active_dispatch(contractor_id: str, request: Request):
        """Return the most recent 'sent' dispatch for this contractor
        so the dashboard can show an 'Accept Now' action."""
        contractor = _resolve_contractor(request)
        if not contractor or str(contractor.get("id", "")) != contractor_id:
            raise HTTPException(401, "Authentication required")

        try:
            res = _SB.table("dispatches").select("*") \
                .eq("contractor_id", contractor_id) \
                .eq("status", "sent") \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()

            if not res.data:
                return {"active": False, "dispatch": None}

            row = res.data[0]
            # Don't expose the token — the contractor uses the magic link from email
            row.pop("token", None)
            return {"active": True, "dispatch": row}
        except Exception as e:
            log.error(f"[contractor_portal] active-dispatch error: {e}")
            return {"active": False, "dispatch": None, "error": str(e)[:80]}

    # ── API: REFERRAL LINK (get or create unique referral code) ───────
    @app.get("/api/v1/contractors/{contractor_id}/referral-link")
    async def ctr_referral_link(contractor_id: str, request: Request):
        """Return the contractor's unique referral link/code for the $500 bounty program.
        Creates one if the contractor doesn't have a referral_code yet.
        Returns {referral_code, referral_url}."""
        contractor = _resolve_contractor(request)
        if not contractor or str(contractor.get("id", "")) != contractor_id:
            raise HTTPException(401, "Authentication required")

        try:
            # Check if contractor already has a referral_code
            res = _SB.table("contractors").select("referral_code, name") \
                .eq("id", contractor_id).limit(1).execute()
            if not res.data:
                raise HTTPException(404, "Contractor not found")

            ref_code = res.data[0].get("referral_code")
            if ref_code:
                base_url = public_base_url.rstrip("/")
                return {
                    "referral_code": ref_code,
                    "referral_url": f"{base_url}/ref/contractor/{ref_code}",
                }

            # Generate a new referral code
            name = res.data[0].get("name", "contractor")
            base = name.strip().lower()
            base = "".join(c if c.isalnum() else "-" for c in base)[:20].rstrip("-")
            suffix = secrets.token_hex(2).upper()
            ref_code = f"{base}-{suffix}" if base else f"ctr-{suffix}"

            _SB.table("contractors").update({"referral_code": ref_code}) \
                .eq("id", contractor_id).execute()

            log.info(f"[contractor_portal] referral code created for {contractor_id}: {ref_code}")
            base_url = public_base_url.rstrip("/")
            return {
                "referral_code": ref_code,
                "referral_url": f"{base_url}/ref/contractor/{ref_code}",
            }
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[contractor_portal] referral-link error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: REFERRALS LIST ───────────────────────────────────────────
    @app.get("/api/v1/contractors/{contractor_id}/referrals")
    async def ctr_referrals_list(
        contractor_id: str,
        request: Request,
        limit: int = Query(50, ge=1, le=200),
    ):
        """Return referrals made by this contractor with bounty tracking."""
        contractor = _resolve_contractor(request)
        if not contractor or str(contractor.get("id", "")) != contractor_id:
            raise HTTPException(401, "Authentication required")

        try:
            # Query the contractor_referral_view for this referrer
            refs = _SB.table("contractor_referral_view").select("*") \
                .eq("referrer_contractor_id", contractor_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            rows = refs.data or []

            # Aggregate stats
            total = len(rows)
            signed_up = sum(1 for r in rows if r.get("referred_contractor_id") is not None)
            total_earned = sum(float(r.get("bounty_amount", 0) or 0) for r in rows if r.get("bounty_status") in ("earned", "paid"))
            total_paid = sum(float(r.get("bounty_amount", 0) or 0) for r in rows if r.get("bounty_status") == "paid")
            pending_count = sum(1 for r in rows if r.get("bounty_status") == "pending")

            # Also query referral_payouts for additional paid info
            try:
                payouts = _SB.table("referral_payouts").select("bounty_amount") \
                    .eq("referrer_contractor_id", contractor_id) \
                    .eq("status", "paid") \
                    .execute()
                total_paid_from_payouts = sum(float(p.get("bounty_amount", 0) or 0) for p in (payouts.data or []))
                if total_paid_from_payouts > total_paid:
                    total_paid = total_paid_from_payouts
            except Exception:
                pass

            # Calculate available_for_payout: earned bounties that haven't been paid yet
            # Query referral_payouts for this referrer with status='earned' (not yet paid/requested)
            available_for_payout = 0
            try:
                payout_rows = _SB.table("referral_payouts").select("bounty_amount") \
                    .eq("referrer_contractor_id", contractor_id) \
                    .eq("status", "earned") \
                    .execute()
                available_for_payout = sum(float(p.get("bounty_amount", 0) or 0) for p in (payout_rows.data or []))
            except Exception:
                pass

            # Query payout history: paid, cancelled, payout_requested payouts with tx IDs
            payout_history = []
            try:
                hist_res = _SB.table("referral_payouts").select("*") \
                    .eq("referrer_contractor_id", contractor_id) \
                    .in_("status", ["paid", "cancelled", "payout_requested"]) \
                    .order("paid_at", desc=True, nullslast=True) \
                    .order("created_at", desc=True) \
                    .limit(limit) \
                    .execute()
                payout_history = hist_res.data or []
            except Exception:
                pass

            return {
                "referrals": rows,
                "total": total,
                "signed_up": signed_up,
                "total_earned": round(total_earned, 2),
                "total_paid": round(total_paid, 2),
                "pending_count": pending_count,
                "available_for_payout": round(available_for_payout, 2),
                "payout_history": payout_history,
            }
        except Exception as e:
            log.error(f"[contractor_portal] referrals error: {e}")
            return {"referrals": [], "total": 0, "signed_up": 0, "total_earned": 0, "total_paid": 0}

    # ── API: BOUNTY PAYOUT REQUEST ────────────────────────────────────
    @app.post("/api/v1/contractors/{contractor_id}/bounty-payout-request")
    async def ctr_bounty_payout_request(contractor_id: str, request: Request):
        """
        Request payout for all earned bounties.

        Finds all referral_payouts for this contractor with status='earned'
        and marks them as 'payout_requested'. Records the payout method
        (default: USDC). Sends an ntfy notification to operators.

        Body:
            payout_method (str, optional): 'usdc' (default)
            payout_address (str, optional): Solana wallet address

        Returns:
            {ok, payout_count, total_amount}
        """
        contractor = _resolve_contractor(request)
        if not contractor or str(contractor.get("id", "")) != contractor_id:
            raise HTTPException(401, "Authentication required")

        try:
            body = await request.json()
        except Exception:
            body = {}

        payout_method = (body.get("payout_method") or "usdc").strip()
        payout_address = (body.get("payout_address") or "").strip()
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            # Find all earned bounties for this contractor
            earned_rows = _SB.table("referral_payouts").select("id,bounty_amount,contractor_referral_id") \
                .eq("referrer_contractor_id", contractor_id) \
                .eq("status", "earned") \
                .limit(100) \
                .execute()

            if not earned_rows.data:
                return {"ok": False, "error": "No earned bounties available for payout"}

            payout_ids = [r["id"] for r in earned_rows.data]
            total_amount = sum(float(r.get("bounty_amount", 0) or 0) for r in earned_rows.data)
            payout_count = len(payout_ids)

            # Update all earned payouts to payout_requested
            meta_update = {
                "payout_method": payout_method,
            }
            if payout_address:
                meta_update["payout_address"] = payout_address

            _SB.table("referral_payouts").update({
                "status": "payout_requested",
                "notes": f"Payout requested via contractor portal ({now_iso}). Method: {payout_method}.",
                "meta": meta_update,
            }).eq("referrer_contractor_id", contractor_id).eq("status", "earned").execute()

            # Also mark the related contractor_referrals rows
            for r in earned_rows.data:
                ref_id = r.get("contractor_referral_id")
                if ref_id:
                    try:
                        _SB.table("contractor_referrals").update({
                            "bounty_status": "payout_requested",
                            "notes": f"Payout requested via portal. {now_iso}",
                        }).eq("id", ref_id).execute()
                    except Exception:
                        pass

            # Send ntfy notification to operators
            try:
                import httpx as _httpx
                ctr_name = contractor.get("name", "Contractor")
                ctr_phone = contractor.get("phone", "")
                ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
                ntfy_token = os.environ.get("NTFY_TOKEN", "").strip()
                if ntfy_topic:
                    headers = {
                        "Title": f"💸 Bounty Payout Request — ${total_amount:,.0f}",
                        "Tags": "money-with-wings",
                        "Priority": "4",
                    }
                    if ntfy_token:
                        headers["Authorization"] = f"Bearer {ntfy_token}"
                    ntfy_msg = (
                        f"{ctr_name} ({ctr_phone[:15]}) requested ${total_amount:,.2f} "
                        f"payout for {payout_count} bounties. "
                        f"Method: {payout_method}. "
                        f"Wallet: {payout_address[:20] if payout_address else '—'}."
                    )
                    async with _httpx.AsyncClient(timeout=10) as _client:
                        await _client.post(
                            f"https://ntfy.sh/{ntfy_topic}",
                            content=ntfy_msg,
                            headers=headers,
                        )
            except Exception as e:
                log.warning(f"[bounty_payout] ntfy notification failed: {e}")

            log.info(
                f"[bounty_payout] Payout requested: contractor={contractor_id} "
                f"count={payout_count} total=${total_amount:,.2f} method={payout_method}"
            )

            return {
                "ok": True,
                "payout_count": payout_count,
                "total_amount": round(total_amount, 2),
                "payout_method": payout_method,
            }

        except Exception as e:
            log.error(f"[bounty_payout] payout request error: {e}")
            raise HTTPException(500, str(e)[:200])

    # ── API: REFERRAL LEADERBOARD ───────────────────────────────────
    @app.get("/api/v1/referral-leaderboard")
    async def ctr_referral_leaderboard(
        limit: int = Query(10, ge=1, le=50),
        current_contractor_id: str = Query("", description="If provided, returns this contractor's rank"),
    ):
        """Return top referrers by total bounty earned across all contractors.
        No auth required — displayed publicly in the contractor dashboard.
        If current_contractor_id is provided, computes your_rank for that contractor.
        Returns {leaderboard, total_referrers, your_rank}
        """
        try:
            # Fetch all referral_payouts with status in (earned, paid)
            res = _SB.table("referral_payouts").select("referrer_contractor_id, bounty_amount, status") \
                .in_("status", ["earned", "paid"]) \
                .limit(5000) \
                .execute()

            if not res.data:
                return {"leaderboard": [], "total_referrers": 0, "your_rank": None}

            # Aggregate by referrer_contractor_id
            agg: dict[str, dict] = {}
            for row in res.data:
                rid = row.get("referrer_contractor_id")
                if not rid:
                    continue
                if rid not in agg:
                    agg[rid] = {
                        "referrer_contractor_id": rid,
                        "total_referrals": 0,
                        "total_earned": 0.0,
                        "total_paid": 0.0,
                    }
                bounty = float(row.get("bounty_amount", 0) or 0)
                agg[rid]["total_referrals"] += 1
                agg[rid]["total_earned"] += bounty
                if row.get("status") == "paid":
                    agg[rid]["total_paid"] += bounty

            # Fetch names from contractors table
            ref_ids = list(agg.keys())
            names_map: dict[str, str] = {}
            try:
                ctr_res = _SB.table("contractors").select("id, name") \
                    .in_("id", ref_ids).execute()
                for c in (ctr_res.data or []):
                    cid = c.get("id")
                    if cid:
                        names_map[cid] = c.get("name", "Unknown")
            except Exception:
                pass

            # Sort by total_earned descending
            sorted_refs = sorted(agg.values(), key=lambda x: x["total_earned"], reverse=True)

            # Assign rank and trim
            result = []
            your_rank = None
            for i, entry in enumerate(sorted_refs):
                rank = i + 1
                is_current = bool(current_contractor_id) and str(entry["referrer_contractor_id"]) == current_contractor_id
                if rank <= limit:
                    result.append({
                        "id": entry["referrer_contractor_id"],
                        "rank": rank,
                        "name": names_map.get(entry["referrer_contractor_id"], "Unknown"),
                        "total_referrals": entry["total_referrals"],
                        "total_earned": round(entry["total_earned"], 2),
                        "total_paid": round(entry["total_paid"], 2),
                        "is_you": is_current,
                    })
                if is_current:
                    your_rank = {
                        "rank": rank,
                        "name": names_map.get(current_contractor_id, "You"),
                        "total_referrals": entry["total_referrals"],
                        "total_earned": round(entry["total_earned"], 2),
                        "total_paid": round(entry["total_paid"], 2),
                    }

            return {"leaderboard": result, "total_referrers": len(agg), "your_rank": your_rank}
        except Exception as e:
            log.error(f"[referral_leaderboard] query error: {e}")
            return {"leaderboard": [], "total_referrers": 0, "your_rank": None}

    # ── API: PUBLIC CONTRACTOR PROFILE (no auth) ────────────────────────
    @app.get("/api/v1/contractor-public/{contractor_id}")
    async def ctr_public_profile(contractor_id: str):
        """Return basic public info for any contractor. No auth required.
        Used by the leaderboard modal to show contractor details."""
        try:
            res = _SB.table("contractors").select("name, metro, specialties, trust_score, active")                 .eq("id", contractor_id).limit(1).execute()
            if not res.data:
                return {"ok": False, "error": "Contractor not found"}
            c = res.data[0]
            return {
                "ok": True,
                "id": contractor_id,
                "name": c.get("name", "Unknown"),
                "metro": c.get("metro", "—"),
                "specialties": c.get("specialties", []),
                "trust_score": float(c.get("trust_score", 5.0)),
            }
        except Exception as e:
            log.error(f"[contractor_public] profile error: {e}")
            return {"ok": False, "error": str(e)[:80]}

    log.info("[contractor_portal] Routes registered - /portal/contractors/{login,verify,dashboard,logout} + /api/v1/contractors/{stats,dispatches,earnings,profile,active-dispatch,referral-link,referrals,bounty-payout-request} + /api/v1/referral-leaderboard + /api/v1/contractor-public/{id} + /ref/contractor/{code}")


# ─────────────────────────────────────────────────────────────────────
# CONTRACTOR REFERRAL TRACKING ROUTES (standalone, no auth)
# ─────────────────────────────────────────────────────────────────────
def register_contractor_referral_tracking_routes(
    app: FastAPI,
    *,
    public_base_url: str,
):
    """Register the /ref/contractor/{code} tracking landing page.
    No auth required — this is a public redirect endpoint.
    """

    _CONTRACTOR_REF_REFERRAL_COOKIE = "contractor_ref"

    @app.get("/ref/contractor/{code}")
    async def contractor_ref_redirect(code: str):
        """
        Landing page for contractor-to-contractor referrals. Sets a
        tracking cookie and redirects to the contractor self-onboard page.

        The cookie (`contractor_ref`) is read by the onboard form to
        auto-tag new signups with the referrer code.

        When the referred contractor completes the onboard form at
        /api/contractors/onboard, the handler checks for this cookie
        and creates a contractor_referrals record linking back to
        the referrer.

        Cookie: 90-day expiry (contractors network slowly).
        """
        base = public_base_url.rstrip("/")

        # Log the click in a lightweight way
        try:
            # Check if this referral_code exists — if not, redirect anyway
            from supabase import create_client as _create_client
            _tmp_sb = _create_client(
                os.getenv("SUPABASE_URL", ""),
                os.getenv("SUPABASE_SERVICE_KEY", ""),
            )
            res = _tmp_sb.table("contractors").select("name") \
                .eq("referral_code", code).limit(1).execute()
            if res.data:
                log.info(f"[contractor_ref] tracking click: {code} -> {res.data[0].get('name', '?')}")
        except Exception:
            pass

        response = RedirectResponse(url=f"{base}/contractors", status_code=302)
        response.set_cookie(
            key=_CONTRACTOR_REF_REFERRAL_COOKIE,
            value=code,
            max_age=60 * 60 * 24 * 90,  # 90 days
            httponly=False,
            samesite="lax",
            path="/",
        )
        return response

    log.info("[contractor_ref] Routes registered - /ref/contractor/{code}")
