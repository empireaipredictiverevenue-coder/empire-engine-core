"""
EMPIRE V49 · AFFILIATE PORTAL
=============================
Public-facing affiliate dashboard. Every active buyer (is_active=true)
gets a unique referral link. Affiliates log in via email magic link,
see their stats, payout history, and referral performance.

ENDPOINTS
─────────
  GET  /portal/affiliate/login                          → public login form
  POST /api/v1/affiliate/login                          → send magic link email
  GET  /portal/affiliate/{id}/verify?t=...              → verify token, set cookie, redirect
  GET  /portal/affiliate/{id}/dashboard                  → main affiliate dashboard
  GET  /api/v1/affiliate/{id}/stats                     → aggregate stats JSON
  GET  /api/v1/affiliate/{id}/payouts                   → payout history JSON
  GET  /api/v1/affiliate/{id}/links                     → referral links JSON
  GET  /api/v1/affiliate/{id}/referrals                 → recent attributed leads/calls JSON
"""

import os
import re
import time
import json
import secrets
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from supabase import create_client
import base64
import threading


# ── 1x1 TRANSPARENT GIF (base64-encoded) ────────────────────────────
_PIXEL_GIF_B64 = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
_PIXEL_GIF = base64.b64decode(_PIXEL_GIF_B64)

# ── TRACKING COOKIE NAME ────────────────────────────────────────────
_AFF_COOKIE = "affiliate_ref"


log = logging.getLogger("empire.affiliate")

# ── CONFIG ────────────────────────────────────────────────────────────
LOGIN_LINK_TTL_SECONDS = 600  # 10 min
SESSION_TTL_HOURS = 24
_AFF_SESSION_HASHES = {}  # token_hash -> {buyer_id, expires_at}

# ── SUPABASE CLIENT ───────────────────────────────────────────────────
_sb = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", ""),
)


# ── HELPERS ───────────────────────────────────────────────────────────
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _verify_affiliate_session(token: str) -> Optional[dict]:
    """Check an affiliate session token. Returns {buyer_id, buyer_name, ...} or None."""
    th = _hash_token(token)
    sess = _AFF_SESSION_HASHES.get(th)
    if not sess:
        return None
    if datetime.now(timezone.utc) > sess["expires_at"]:
        del _AFF_SESSION_HASHES[th]
        return None
    return sess.get("buyer")


def _resolve_affiliate(request: Request) -> Optional[dict]:
    """Check Authorization header or cookie for affiliate session."""
    # Try Authorization header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        buyer = _verify_affiliate_session(token)
        if buyer:
            return buyer
    # Try cookie
    token = request.cookies.get("affiliate_session", "")
    if token:
        buyer = _verify_affiliate_session(token)
        if buyer:
            return buyer
    return None


# ── AFFILIATE LOGIN PAGE ──────────────────────────────────────────────
_AFF_LOGIN_CSS = """
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
"""

_AFF_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Affiliate Login</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{_AFF_LOGIN_CSS}</style>
</head><body>
<div class="box">
  <div class="brand"><span class="brand-e">EMPIRE</span><span class="brand-ai">AI</span></div>
  <div class="brand-sub">Affiliate Portal</div>
  <h1>Partner <em>Login</em></h1>
  <p class="lead">Enter your email and we'll send a one-time sign-in link.</p>
  <div class="field">
    <label>Email</label>
    <input type="email" id="email" placeholder="you@yourcompany.com" autofocus>
  </div>
  <button class="btn" id="btn" onclick="send()">Send login link</button>
  <div id="flash" class="flash"></div>
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
    const r = await fetch('/api/v1/affiliate/login', {
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


# ── AFFILIATE DASHBOARD PAGE ──────────────────────────────────────────
def _affiliate_dashboard(buyer: dict, base_url: str = "http://localhost:8000") -> str:
    buyer_name = buyer.get("buyer_name", "Partner")
    buyer_id = buyer.get("id", "")
    ref_link = f"{base_url}/portal/affiliate/{buyer_id}/verify?ref="
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Affiliate Dashboard</title>
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
.ref-link {{ background: rgba(0,0,0,0.3); padding: 10px 14px; font-family: var(--mono); font-size: 9px; color: var(--teal); word-break: break-all; border: 1px solid var(--divider); margin-bottom: 16px; }}
.ref-link .lbl {{ color: var(--fg3); font-size: 8px; text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 4px; }}
.ref-link code {{ color: var(--cyan); }}
.tabs {{ display: flex; gap: 4px; border-bottom: 1px solid var(--divider); margin-bottom: 16px; }}
.tab {{
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  padding: 8px 16px; cursor: pointer; border: none; background: transparent;
  color: var(--fg3); border-bottom: 2px solid transparent; transition: all 0.2s;
}}
.tab:hover {{ color: var(--fg2); }}
.tab.active {{ color: var(--teal); border-bottom-color: var(--teal); }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}
.chart-placeholder {{
  background: var(--bg2); border: 1px solid var(--divider);
  padding: 32px; text-align: center; color: var(--fg3); font-family: var(--mono); font-size: 9px;
}}
.ccy {{ font-family: var(--mono); font-weight: 400; font-size: 14px; color: var(--fg3); vertical-align: super; }}
.badge {{
  display: inline-block; font-family: var(--mono); font-size: 8px;
  padding: 1px 6px; text-transform: uppercase; letter-spacing: 0.08em;
}}
.badge.active {{ color: var(--teal); background: rgba(68,229,184,0.1); }}
.badge.inactive {{ color: var(--fg3); background: rgba(122,140,163,0.1); }}
</style>
</head><body>
<div class="header">
  <div class="header-brand"><span class="e">EMPIRE</span><span class="ai">AI</span></div>
  <h1>Affiliate <em>Dashboard</em></h1>
  <div class="header-right">
    <span class="name">{buyer_name}</span>
    <a href="/portal/affiliate/logout" class="logout">Sign out</a>
  </div>
</div>
<div class="container">
  <div class="greeting">
    <h2>Welcome, <em>{buyer_name}</em></h2>
    <div class="sub">Affiliate Portal · Revenue Network</div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('overview')">Overview</button>
    <button class="tab" onclick="switchTab('payouts')">Payouts</button>
    <button class="tab" onclick="switchTab('links')">Referral Links</button>
    <button class="tab" onclick="switchTab('referrals')">Referrals</button>
  </div>

  <div id="tab-overview" class="tab-content active">
    <div class="grid" id="statsGrid">
      <div class="card"><div class="card-label">Total Leads</div><div class="card-value" id="stat-leads">--</div></div>
      <div class="card"><div class="card-label">Calls</div><div class="card-value" id="stat-calls">--</div></div>
      <div class="card"><div class="card-label">Qualified</div><div class="card-value cyan" id="stat-qualified">--</div></div>
      <div class="card"><div class="card-label">Revenue</div><div class="card-value teal" id="stat-revenue">--</div></div>
      <div class="card"><div class="card-label">Commission</div><div class="card-value teal" id="stat-commission">--</div></div>
      <div class="card"><div class="card-label">Links Active</div><div class="card-value" id="stat-links">--</div></div>
    </div>
  </div>

  <div id="tab-payouts" class="tab-content">
    <div class="section-title"><strong>Payout History</strong></div>
    <table>
      <thead><tr><th>Date</th><th>Lead</th><th>Amount</th><th>Commission</th><th>Status</th></tr></thead>
      <tbody id="payoutsBody">
        <tr><td class="empty" colspan="5">Loading...</td></tr>
      </tbody>
    </table>
  </div>

  <div id="tab-links" class="tab-content">
    <div class="section-title"><strong>Your Referral Links</strong></div>
    <table>
      <thead><tr><th>Code</th><th>Label</th><th>Link</th><th>Status</th><th>Clicks</th><th>Conversions</th></tr></thead>
      <tbody id="linksBody">
        <tr><td class="empty" colspan="6">Loading...</td></tr>
      </tbody>
    </table>
  </div>

  <div id="tab-referrals" class="tab-content">
    <div class="section-title"><strong>Recent Referral Activity</strong></div>
    <table>
      <thead><tr><th>Date</th><th>Lead Name</th><th>Source</th><th>Status</th><th>Revenue</th></tr></thead>
      <tbody id="referralsBody">
        <tr><td class="empty" colspan="5">Loading...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<script>
const BUYER_ID = {json.dumps(buyer_id)};

async function apiFetch(path) {{
  const r = await fetch(path, {{ credentials: 'include' }});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}}

function fmtCurrency(v) {{
  if (!v || v === 0) return '$0.00';
  return '$' + Number(v).toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
}}

function fmtPct(v) {{
  if (!v) return '0%';
  return (Number(v) * 100).toFixed(1) + '%';
}}

function fmtDate(ts) {{
  if (!ts) return '--';
  return ts.slice(0, 10);
}}

async function loadStats() {{
  try {{
    const d = await apiFetch('/api/v1/affiliate/' + BUYER_ID + '/stats');
    document.getElementById('stat-leads').textContent = d.total_leads || 0;
    document.getElementById('stat-calls').textContent = d.total_calls || 0;
    document.getElementById('stat-qualified').textContent = d.qualified_calls || 0;
    document.getElementById('stat-revenue').textContent = fmtCurrency(d.total_revenue);
    document.getElementById('stat-commission').textContent = fmtCurrency(d.commission_earned);
    document.getElementById('stat-links').textContent = d.link_count || 0;
  }} catch (e) {{
    document.querySelectorAll('#statsGrid .card-value').forEach(el => el.textContent = 'err');
  }}
}}

async function loadPayouts() {{
  try {{
    const d = await apiFetch('/api/v1/affiliate/' + BUYER_ID + '/payouts');
    const tbody = document.getElementById('payoutsBody');
    if (!d.payouts || d.payouts.length === 0) {{
      tbody.innerHTML = '<tr><td class=\\"empty\\" colspan=\\"5\\">No payouts yet</td></tr>';
      return;
    }}
    tbody.innerHTML = d.payouts.map(p => '<tr>' +
      '<td>' + fmtDate(p.created_at) + '</td>' +
      '<td>' + (p.buyer_name || '--') + '</td>' +
      '<td class=\\"num\\">' + fmtCurrency(p.amount) + '</td>' +
      '<td class=\\"num\\">' + fmtCurrency(p.commission) + '</td>' +
      '<td>' + (p.status || '--') + '</td>' +
    '</tr>').join('');
  }} catch (e) {{
    document.getElementById('payoutsBody').innerHTML = '<tr><td class=\\"empty\\" colspan=\\"5\\">Failed to load</td></tr>';
  }}
}}

async function loadLinks() {{
  try {{
    const d = await apiFetch('/api/v1/affiliate/' + BUYER_ID + '/links');
    const tbody = document.getElementById('linksBody');
    if (!d.links || d.links.length === 0) {{
      tbody.innerHTML = '<tr><td class=\\"empty\\" colspan=\\"6\\">No links yet</td></tr>';
      return;
    }}
    tbody.innerHTML = d.links.map(l => '<tr>' +
      '<td><code>' + (l.code || '--') + '</code></td>' +
      '<td>' + (l.label || '--') + '</td>' +
      '<td style=\\"max-width:200px;overflow:hidden;text-overflow:ellipsis\\">' +
        '<a href=\\"' + l.url + '\\" target=\\"_blank\\" style=\\"color:var(--teal);text-decoration:none;font-size:8px\\">' + (l.url || '').slice(0, 50) + '...</a></td>' +
      '<td><span class=\\"badge ' + (l.active ? 'active' : 'inactive') + '\\">' + (l.active ? 'Active' : 'Inactive') + '</span></td>' +
      '<td class=\\"num\\">' + (l.click_count || 0) + '</td>' +
      '<td class=\\"num\\">' + (l.conversion_count || 0) + '</td>' +
    '</tr>').join('');
  }} catch (e) {{
    document.getElementById('linksBody').innerHTML = '<tr><td class=\\"empty\\" colspan=\\"6\\">Failed to load</td></tr>';
  }}
}}

async function loadReferrals() {{
  try {{
    const d = await apiFetch('/api/v1/affiliate/' + BUYER_ID + '/referrals');
    const tbody = document.getElementById('referralsBody');
    if (!d.referrals || d.referrals.length === 0) {{
      tbody.innerHTML = '<tr><td class=\\"empty\\" colspan=\\"5\\">No referral activity yet</td></tr>';
      return;
    }}
    tbody.innerHTML = d.referrals.map(r => '<tr>' +
      '<td>' + fmtDate(r.created_at) + '</td>' +
      '<td>' + (r.buyer_name || r.lead_name || '--') + '</td>' +
      '<td>' + (r.source || 'affiliate') + '</td>' +
      '<td>' + (r.status || '--') + '</td>' +
      '<td class=\\"num\\">' + fmtCurrency(r.revenue || r.fee_earned || 0) + '</td>' +
    '</tr>').join('');
  }} catch (e) {{
    document.getElementById('referralsBody').innerHTML = '<tr><td class=\\"empty\\" colspan=\\"5\\">Failed to load</td></tr>';
  }}
}}

function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector('.tab[onclick*=\\"' + name + '\\"]').classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'payouts') loadPayouts();
  if (name === 'links') loadLinks();
  if (name === 'referrals') loadReferrals();
}}

loadStats();
</script>
</body></html>"""


def _record_aff_click(code: str):
    """Background worker: increment click_count for an affiliate link and
    update last_click timestamp. Called from the tracking pixel/landing page."""
    try:
        # Fetch current count, increment locally, update
        cur = _sb.table("affiliate_links").select("click_count")             .eq("code", code).limit(1).execute()
        if cur.data:
            current = (cur.data[0].get("click_count") or 0) + 1
            _sb.table("affiliate_links").update({
                "click_count": current,
                "last_click": datetime.now(timezone.utc).isoformat(),
            }).eq("code", code).execute()
    except Exception as e:
        log.warning(f"[affiliate] click recording failed for code {code}: {e}")



# ── ROUTES ────────────────────────────────────────────────────────────
def register_affiliate_routes(
    app: FastAPI,
    *,
    sign_token: Callable,
    verify_token: Callable,
    send_email: Callable,
    public_base_url: str,
    hub_token: str = "",
):
    """Register affiliate portal routes. Pass sign_token and send_email from hub.py."""

    # ── PUBLIC: LOGIN PAGE ────────────────────────────────────────────
    @app.get("/portal/affiliate/login", response_class=HTMLResponse)
    async def aff_login_page():
        return HTMLResponse(_AFF_LOGIN_PAGE)

    # ── PUBLIC: SEND MAGIC LINK ───────────────────────────────────────
    @app.post("/api/v1/affiliate/login")
    async def aff_send_link(request: Request):
        """Send a magic link to an affiliate's email. The email must match
        a buyer with is_active=true. Returns {ok: True} even if email not
        found (don't reveal who's registered)."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        email = (body.get("email") or "").lower().strip()
        if not email or "@" not in email:
            raise HTTPException(400, "Valid email required")

        try:
            res = _sb.table("buyers").select("id, buyer_name, email, is_active, status") \
                .eq("email", email).limit(1).execute()
            if not res.data or not res.data[0].get("is_active"):
                log.info(f"[affiliate] login attempt for unknown/inactive: {email}")
                return {"ok": True}
            buyer = res.data[0]
        except Exception as e:
            log.error(f"[affiliate] DB lookup failed: {e}")
            return {"ok": False, "error": "Service error"}

        # Build magic link token
        payload = {
            "buyer_id": str(buyer["id"]),
            "email": email,
            "exp": int(time.time()) + LOGIN_LINK_TTL_SECONDS,
            "iat": int(time.time()),
            "kind": "affiliate_login",
        }
        token = sign_token(payload)
        link = f"{public_base_url.rstrip('/')}/portal/affiliate/{buyer['id']}/verify?t={token}"

        html = f"""
          <div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
            <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
              <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Affiliate Portal</div>
              <div style="font-size:20px;font-weight:700;color:#44E5B8;margin-top:6px;">Your login link</div>
            </div>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              Hi {buyer['buyer_name']}, click below to sign in to your affiliate dashboard.
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
                subject="Empire AI · Your affiliate login link",
                html=html,
            )
            if not result.get("ok"):
                log.error(f"[affiliate] email send failed: {result.get('error', 'unknown')}")
                return {"ok": False, "error": "Could not send login email"}
            log.info(f"[affiliate] login link sent to {email}")
            return {"ok": True}
        except Exception as e:
            log.error(f"[affiliate] email send error: {e}")
            return {"ok": False, "error": "Could not send login email"}

    # ── PUBLIC: VERIFY MAGIC LINK ─────────────────────────────────────
    @app.get("/portal/affiliate/{buyer_id}/verify", response_class=HTMLResponse)
    async def aff_verify(request: Request, buyer_id: str, t: str = Query(...)):
        """Verify magic link token. If valid, create session cookie and redirect to dashboard."""
        decoded = verify_token(t)
        if not decoded or decoded.get("kind") != "affiliate_login":
            return HTMLResponse("""
                <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                <div style="text-align:center;"><h1 style="font-weight:200;">Link invalid</h1>
                <p style="color:#7a8ca3;">This link has expired or is invalid.</p>
                <a href="/portal/affiliate/login" style="color:#44e5b8;margin-top:16px;display:inline-block;">Request a new one \u2192</a></div></body></html>
            """, status_code=401)

        # Verify buyer_id matches
        if str(decoded.get("buyer_id", "")) != buyer_id:
            return HTMLResponse("<h1>Invalid link</h1>", status_code=401)

        try:
            res = _sb.table("buyers").select("id, buyer_name, email, is_active, niche, status, fee_rate") \
                .eq("id", buyer_id).limit(1).execute()
            if not res.data or not res.data[0].get("is_active"):
                return HTMLResponse("""
                    <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                    <div><h1 style="font-weight:200;">Account inactive</h1>
                    <p style="color:#7a8ca3;">Contact your Empire AI account manager.</p></div></body></html>
                """, status_code=403)
            buyer = res.data[0]
        except Exception as e:
            log.error(f"[affiliate] verify lookup failed: {e}")
            return HTMLResponse("<h1>Service error</h1>", status_code=500)

        # Create session
        session_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        _AFF_SESSION_HASHES[token_hash] = {
            "buyer": {
                "id": str(buyer["id"]),
                "buyer_name": buyer["buyer_name"],
                "email": buyer["email"],
                "niche": buyer.get("niche", ""),
                "status": buyer.get("status", ""),
                "fee_rate": float(buyer.get("fee_rate", 0.01)),
            },
            "expires_at": expires_at,
        }

        response = RedirectResponse(
            url=f"/portal/affiliate/{buyer_id}/dashboard",
            status_code=302,
        )
        use_secure = public_base_url.startswith("https://")
        response.set_cookie(
            key="affiliate_session",
            value=session_token,
            max_age=int(SESSION_TTL_HOURS * 3600),
            httponly=True,
            secure=use_secure,
            samesite="lax",
            path="/",
        )
        log.info(f"[affiliate] verified: {buyer['buyer_name']} ({buyer['email']})")
        return response

    # ── PUBLIC: DASHBOARD PAGE ────────────────────────────────────────
    @app.get("/portal/affiliate/{buyer_id}/dashboard", response_class=HTMLResponse)
    async def aff_dashboard(buyer_id: str, request: Request):
        """Render the affiliate dashboard page. Requires valid session cookie."""
        buyer = _resolve_affiliate(request)
        if not buyer or str(buyer.get("id", "")) != buyer_id:
            return HTMLResponse("""
                <html><body style="background:#0a1a2f;color:#f8fafd;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;">
                <div style="text-align:center;"><h1 style="font-weight:200;">Sign in required</h1>
                <p style="color:#7a8ca3;">Please sign in to view your dashboard.</p>
                <a href="/portal/affiliate/login" style="color:#44e5b8;margin-top:16px;display:inline-block;">Sign in \u2192</a></div></body></html>
            """, status_code=401)
        return HTMLResponse(_affiliate_dashboard(buyer, base_url=public_base_url))

    # ── PUBLIC: LOGOUT ────────────────────────────────────────────────
    @app.get("/portal/affiliate/logout")
    async def aff_logout(request: Request):
        """Clear the affiliate session cookie."""
        token = request.cookies.get("affiliate_session", "")
        if token:
            th = _hash_token(token)
            _AFF_SESSION_HASHES.pop(th, None)
        response = RedirectResponse(url="/portal/affiliate/login", status_code=302)
        response.delete_cookie("affiliate_session", path="/")
        return response

    # ── API: STATS ────────────────────────────────────────────────────
    @app.get("/api/v1/affiliate/{buyer_id}/stats")
    async def aff_stats(buyer_id: str, request: Request):
        """Return aggregate stats for an affiliate from the affiliate_stats view."""
        auth_header = request.headers.get("Authorization", "")
        cookie_token = request.cookies.get("affiliate_session", "")
        hub_auth = bool(hub_token) and auth_header == f"Bearer {hub_token}"
        buyer = _resolve_affiliate(request) if not hub_auth else None
        if not hub_auth and (not buyer or str(buyer.get("id", "")) != buyer_id):
            raise HTTPException(401, "Authentication required")

        try:
            res = _sb.table("affiliate_stats").select("*") \
                .eq("buyer_id", buyer_id).limit(1).execute()
            if res.data:
                return res.data[0]
            # Fallback: pull buyer + link count
            links = _sb.table("affiliate_links").select("id") \
                .eq("buyer_id", buyer_id).execute()
            return {
                "buyer_id": buyer_id,
                "affiliate_code": "",
                "buyer_name": "",
                "affiliate_email": "",
                "fee_rate": 0,
                "base_payout": 0,
                "buyer_status": "",
                "buyer_active": False,
                "total_leads": 0,
                "total_calls": 0,
                "qualified_calls": 0,
                "total_revenue": 0,
                "commission_earned": 0,
                "link_count": len(links.data or []),
            }
        except Exception as e:
            log.error(f"[affiliate] stats error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: PAYOUTS ──────────────────────────────────────────────────
    @app.get("/api/v1/affiliate/{buyer_id}/payouts")
    async def aff_payouts(buyer_id: str, request: Request, limit: int = Query(50, ge=1, le=200)):
        """Return payout records for an affiliate based on attributed calls."""
        auth_header = request.headers.get("Authorization", "")
        hub_auth = bool(hub_token) and auth_header == f"Bearer {hub_token}"
        buyer = _resolve_affiliate(request) if not hub_auth else None
        if not hub_auth and (not buyer or str(buyer.get("id", "")) != buyer_id):
            raise HTTPException(401, "Authentication required")

        try:
            # Get the affiliate's code and fee_rate
            links = _sb.table("affiliate_links").select("code") \
                .eq("buyer_id", buyer_id).eq("active", True).execute()
            codes = [l["code"] for l in (links.data or [])]
            if not codes:
                return {"payouts": [], "total": 0}

            # Get buyer's fee rate
            buyer_res = _sb.table("buyers").select("fee_rate, buyer_name") \
                .eq("id", buyer_id).limit(1).execute()
            fee_rate = float(buyer_res.data[0].get("fee_rate", 0.01)) if buyer_res.data else 0.01
            buyer_name = buyer_res.data[0].get("buyer_name", "") if buyer_res.data else ""

            # Query call_logs with affiliate_code matching any of the buyer's codes
            call_res = _sb.table("call_logs").select("id, created_at, fee_earned, niche, qualified, buyer_name") \
                .in_("affiliate_code", codes) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            payouts = []
            for row in (call_res.data or []):
                amount = float(row.get("fee_earned", 0) or 0)
                commission = round(amount * fee_rate, 2)
                payouts.append({
                    "created_at": row.get("created_at", ""),
                    "buyer_name": row.get("buyer_name") or buyer_name,
                    "amount": amount,
                    "commission": commission,
                    "status": "earned" if row.get("qualified") else "pending",
                })
            return {"payouts": payouts, "total": len(payouts)}
        except Exception as e:
            log.error(f"[affiliate] payouts error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: REFERRAL LINKS ───────────────────────────────────────────
    @app.get("/api/v1/affiliate/{buyer_id}/links")
    async def aff_links(buyer_id: str, request: Request):
        """Return all referral links for an affiliate."""
        auth_header = request.headers.get("Authorization", "")
        hub_auth = bool(hub_token) and auth_header == f"Bearer {hub_token}"
        buyer = _resolve_affiliate(request) if not hub_auth else None
        if not hub_auth and (not buyer or str(buyer.get("id", "")) != buyer_id):
            raise HTTPException(401, "Authentication required")

        try:
            res = _sb.table("affiliate_links").select("*") \
                .eq("buyer_id", buyer_id) \
                .order("created_at", desc=True) \
                .execute()
            base = public_base_url.rstrip("/")
            links = []
            for row in (res.data or []):
                links.append({
                    "id": str(row["id"]),
                    "code": row["code"],
                    "label": row.get("label", ""),
                    "active": row.get("active", True),
                    "click_count": row.get("click_count", 0),
                    "conversion_count": row.get("conversion_count", 0),
                    "last_click": row.get("last_click"),
                    "url": f"{base}/portal/affiliate/{buyer_id}/verify?ref={row['code']}",
                    "pixel_url": f"{base}/track/aff/{row['code']}/pixel.gif",
                    "landing_url": f"{base}/track/aff/{row['code']}",
                })
            return {"links": links, "total": len(links)}
        except Exception as e:
            log.error(f"[affiliate] links error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── API: REFERRALS ────────────────────────────────────────────────
    @app.get("/api/v1/affiliate/{buyer_id}/referrals")
    async def aff_referrals(buyer_id: str, request: Request, limit: int = Query(50, ge=1, le=200)):
        """Return recent referral activity (inbound_leads + call_logs attributed to this affiliate)."""
        auth_header = request.headers.get("Authorization", "")
        hub_auth = bool(hub_token) and auth_header == f"Bearer {hub_token}"
        buyer = _resolve_affiliate(request) if not hub_auth else None
        if not hub_auth and (not buyer or str(buyer.get("id", "")) != buyer_id):
            raise HTTPException(401, "Authentication required")

        try:
            # Get affiliate codes for this buyer
            links = _sb.table("affiliate_links").select("code") \
                .eq("buyer_id", buyer_id).execute()
            codes = [l["code"] for l in (links.data or [])]
            if not codes:
                return {"referrals": [], "total": 0}

            # Inbound leads attributed
            leads = _sb.table("inbound_leads").select("id, created_at, name, source, status, affiliate_code") \
                .in_("affiliate_code", codes) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()

            # Calls attributed
            calls = _sb.table("call_logs").select("id, created_at, buyer_name, fee_earned, niche, qualified, affiliate_code") \
                .in_("affiliate_code", codes) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()

            referrals = []
            for row in (leads.data or []):
                referrals.append({
                    "created_at": row.get("created_at", ""),
                    "lead_name": row.get("name", ""),
                    "source": row.get("source", "affiliate"),
                    "status": row.get("status", "new"),
                    "revenue": 0,
                })
            for row in (calls.data or []):
                referrals.append({
                    "created_at": row.get("created_at", ""),
                    "lead_name": row.get("buyer_name", ""),
                    "source": "call",
                    "status": "qualified" if row.get("qualified") else "pending",
                    "revenue": float(row.get("fee_earned", 0) or 0),
                })

            # Sort by date desc and limit
            referrals.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            referrals = referrals[:limit]

            return {"referrals": referrals, "total": len(referrals)}
        except Exception as e:
            log.error(f"[affiliate] referrals error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── OPERATOR API: LIST ALL AFFILIATES ──────────────────────────────
    @app.get("/api/v1/affiliates/list")
    async def aff_list(request: Request):
        """List all buyers (affiliates) with their stats and link counts.
        Requires hub_token auth (operator-only)."""
        auth_header = request.headers.get("Authorization", "")
        if not hub_token or auth_header != f"Bearer {hub_token}":
            raise HTTPException(401, "Operator auth required")

        try:
            buyers = _sb.table("buyers").select("id, buyer_name, email, niche, is_active, status, fee_rate, created_at") \
                .order("created_at", desc=True) \
                .execute()
            result = []
            for b in (buyers.data or []):
                bid = str(b["id"])
                link_res = _sb.table("affiliate_links").select("id") \
                    .eq("buyer_id", bid).execute()
                link_count = len(link_res.data or [])
                active_links = sum(1 for l in (link_res.data or []) if l.get("active"))
                # Try stats from view
                stats = _sb.table("affiliate_stats").select("*") \
                    .eq("buyer_id", bid).limit(1).execute()
                s = stats.data[0] if stats.data else {}
                result.append({
                    "id": bid,
                    "buyer_name": b.get("buyer_name", ""),
                    "email": b.get("email", ""),
                    "niche": b.get("niche", ""),
                    "is_active": b.get("is_active", False),
                    "status": b.get("status", ""),
                    "fee_rate": float(b.get("fee_rate", 0.01)),
                    "created_at": str(b.get("created_at", "")),
                    "link_count": link_count,
                    "active_links": active_links,
                    "total_leads": s.get("total_leads", 0),
                    "total_calls": s.get("total_calls", 0),
                    "qualified_calls": s.get("qualified_calls", 0),
                    "total_revenue": s.get("total_revenue", 0),
                    "commission_earned": s.get("commission_earned", 0),
                })
            return {"affiliates": result, "total": len(result)}
        except Exception as e:
            log.error(f"[affiliate] list error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── OPERATOR API: CREATE REFERRAL LINK ────────────────────────────
    @app.post("/api/v1/affiliates/{buyer_id}/create-link")
    async def aff_create_link(buyer_id: str, request: Request):
        """Create a new referral link for an affiliate. Requires hub_token auth."""
        auth_header = request.headers.get("Authorization", "")
        if not hub_token or auth_header != f"Bearer {hub_token}":
            raise HTTPException(401, "Operator auth required")

        try:
            body = await request.json()
        except Exception:
            body = {}

        label = (body.get("label") or "").strip()
        if not label:
            raise HTTPException(400, "label is required")

        # Verify buyer exists
        buyer_res = _sb.table("buyers").select("id, buyer_name") \
            .eq("id", buyer_id).limit(1).execute()
        if not buyer_res.data:
            raise HTTPException(404, "Buyer not found")

        # Generate unique code
        base_code = label.lower().replace(" ", "-").replace("_", "-")[:20]
        code = base_code
        for attempt in range(10):
            dup = _sb.table("affiliate_links").select("id") \
                .eq("code", code).limit(1).execute()
            if not dup.data:
                break
            code = f"{base_code}-{attempt+2}"

        try:
            _sb.table("affiliate_links").insert({
                "buyer_id": buyer_id,
                "code": code,
                "label": label,
                "active": True,
                "click_count": 0,
                "conversion_count": 0,
            }).execute()
            log.info(f"[affiliate] link created: {code} for buyer {buyer_id}")
            base = public_base_url.rstrip("/")
            return {
                "ok": True,
                "code": code,
                "label": label,
                "pixel_url": f"{base}/track/aff/{code}/pixel.gif",
                "landing_url": f"{base}/track/aff/{code}",
            }
        except Exception as e:
            log.error(f"[affiliate] create link error: {e}")
            raise HTTPException(500, str(e)[:80])

    # ── OPERATOR API: TOGGLE AFFILIATE ACTIVE STATUS ──────────────────
    @app.post("/api/v1/affiliates/{buyer_id}/toggle-active")
    async def aff_toggle_active(buyer_id: str, request: Request):
        """Toggle a buyer's is_active flag. Requires hub_token auth."""
        auth_header = request.headers.get("Authorization", "")
        if not hub_token or auth_header != f"Bearer {hub_token}":
            raise HTTPException(401, "Operator auth required")

        try:
            body = await request.json()
        except Exception:
            body = {}

        active = body.get("is_active")
        if active is None:
            raise HTTPException(400, "is_active field required")

        if not isinstance(active, bool):
            raise HTTPException(400, "is_active must be boolean")

        try:
            _sb.table("buyers").update({"is_active": active}) \
                .eq("id", buyer_id).execute()
            log.info(f"[affiliate] toggled buyer {buyer_id} active={active}")
            return {"ok": True, "buyer_id": buyer_id, "is_active": active}
        except Exception as e:
            log.error(f"[affiliate] toggle error: {e}")
            raise HTTPException(500, str(e)[:80])

    
    # ── TRACKING PIXEL ────────────────────────────────────────────────
    @app.get("/track/aff/{code}/pixel.gif")
    async def aff_track_pixel(code: str):
        """
        1x1 transparent tracking pixel. Logs a click for the affiliate link
        and returns the GIF bytes. Fire-and-forget — the click record
        happens in a background thread so the pixel loads instantly.
        """
        if _sb:
            try:
                threading.Thread(
                    target=_record_aff_click,
                    args=(code,),
                    daemon=True,
                ).start()
            except Exception:
                pass
        return Response(content=_PIXEL_GIF, media_type="image/gif")

    # ── LANDING PAGE URL (sets affiliate cookie) ──────────────────────
    @app.get("/track/aff/{code}")
    async def aff_track_landing(code: str, request: Request, ref: str = Query(None)):
        """
        Landing page URL that sets an affiliate tracking cookie and
        redirects. Use this as the public-facing link for affiliates.

        The cookie (`affiliate_ref`) is set with a 30-day expiry and is
        read by the inbound lead form to auto-tag new leads with the
        affiliate code.
        """
        if _sb:
            try:
                threading.Thread(
                    target=_record_aff_click,
                    args=(code,),
                    daemon=True,
                ).start()
            except Exception:
                pass

        # Determine redirect destination
        dest = "/"
        # If we have a landing page config for this code, use it
        try:
            res = _sb.table("affiliate_links").select("landing_url")                 .eq("code", code).limit(1).execute()
            if res.data and res.data[0].get("landing_url"):
                dest = res.data[0]["landing_url"]
        except Exception:
            pass

        response = RedirectResponse(url=dest, status_code=302)
        response.set_cookie(
            key=_AFF_COOKIE,
            value=code,
            max_age=60 * 60 * 24 * 30,  # 30 days
            httponly=False,  # Must be accessible from JS for inbound forms
            samesite="lax",
            path="/",
        )
        return response

    # ── Click-recording helper (called in background thread) ──────────
    log.info("[affiliate] Routes registered - /portal/affiliate/{login,verify,dashboard} + /api/v1/affiliate/{stats,payouts,links,referrals} + /api/v1/affiliates/{list,create-link,toggle-active}")
