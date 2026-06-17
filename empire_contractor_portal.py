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
def _contractor_dashboard(contractor: dict, base_url: str = "http://localhost:8000") -> str:
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
.btn { font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase; padding: 8px 16px; cursor: pointer; border: none; transition: all 0.2s; }
.btn-teal {{ background: var(--teal); color: #000; }}
.btn-teal:hover {{ background: transparent; color: var(--teal); outline: 1px solid var(--teal); }}
.ccy {{ font-family: var(--mono); font-weight: 400; font-size: 14px; color: var(--fg3); vertical-align: super; }}
</style>
</head><body>
<div class="header">
  <div class="header-brand"><span class="e">EMPIRE</span><span class="ai">AI</span></div>
  <h1>Contractor <em>Dashboard</em></h1>
  <div class="header-right">
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
    <button class="tab" onclick="switchTab('profile')">Profile</button>
  </div>

  <div id="tab-overview" class="tab-content active">
    <div class="grid" id="statsGrid">
      <div class="card"><div class="card-label">Dispatches Received</div><div class="card-value" id="stat-total">--</div></div>
      <div class="card"><div class="card-label">Accepted</div><div class="card-value teal" id="stat-accepted">--</div></div>
      <div class="card"><div class="card-label">Completed</div><div class="card-value cyan" id="stat-completed">--</div></div>
      <div class="card"><div class="card-label">Ghosted</div><div class="card-value" id="stat-ghosted">--</div></div>
      <div class="card"><div class="card-label">Total Earnings</div><div class="card-value teal" id="stat-earnings">$0.00</div></div>
      <div class="card"><div class="card-label">Trust Score</div><div class="card-value" id="stat-trust">--</div></div>
    </div>
    <div class="section">
      <div class="section-title"><strong>Quick Links</strong></div>
      <button class="btn btn-teal" onclick="switchTab('dispatches')" style="margin-right:8px;">View Dispatches →</button>
      <button class="btn btn-teal" onclick="switchTab('earnings')" style="margin-right:8px;">Earnings →</button>
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
  </div>    <div id="tab-profile" class="tab-content">
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
  var tabMap = {{ overview: 0, dispatches: 1, earnings: 2, profile: 3 }};
  if (tabMap[name] !== undefined && tabs[tabMap[name]]) {{
    tabs[tabMap[name]].classList.add('active');
  }}
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'dispatches') loadDispatches();
  if (name === 'earnings') loadEarnings();
}}

loadStats();
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
    """Register contractor portal routes."""

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

    log.info("[contractor_portal] Routes registered - /portal/contractors/{login,verify,dashboard,logout} + /api/v1/contractors/{stats,dispatches,earnings,profile,active-dispatch}")
