"""
EMPIRE V49 · AFFILIATE RECRUITMENT
===================================
Public-facing recruitment page + signup workflow.

Every signup:
  1. Creates a new affiliate record with auto-generated referral code
  2. Sends an ntfy notification to the Owner
  3. Returns the referral link for immediate sharing

ENDPOINTS
─────────
  GET  /affiliates                   → public recruitment page (HTML)
  POST /api/v1/affiliates/signup     → sign up as an affiliate (public)
  GET  /api/v1/affiliates/list       → list all affiliates (auth required)
  GET  /api/v1/affiliates/stats      → aggregate affiliate stats (auth required)
"""

import os
import json
import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from supabase import create_client

log = logging.getLogger("empire.affiliate_recruit")

# ─────────────────────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────────────────────────────────────
_sb = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", ""),
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _generate_referral_code(name: str) -> str:
    """Generate a unique referral code from a name + random suffix."""
    base = name.strip().lower()
    base = "".join(c if c.isalnum() else "-" for c in base)
    base = "-".join(part for part in base.split("-") if part)
    base = base[:20].rstrip("-")
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"{base}-{suffix}"


async def _notify_owner(title: str, message: str, tags: str = "bell") -> None:
    """Push an ntfy notification to the Owner."""
    topic = os.getenv("NTFY_TOPIC", "")
    token = os.getenv("NTFY_TOKEN", "")
    if not topic:
        return
    try:
        import httpx
        headers = {"Title": title[:200], "Tags": tags, "Priority": "4"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://ntfy.sh/{topic}",
                content=message[:1000],
                headers=headers,
            )
    except Exception as e:
        log.warning(f"[affiliate] ntfy push failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# RECRUITMENT PAGE — HTML
# ─────────────────────────────────────────────────────────────────────────────
_AFFILIATE_PAGE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0A1A2F; color: #F8FAFD;
  font-family: 'Inter', -apple-system, system-ui, sans-serif;
  letter-spacing: -0.02em;
  min-height: 100vh;
  background:
    radial-gradient(ellipse at top right, rgba(68,229,184,0.06), transparent 50%),
    radial-gradient(ellipse at bottom left, rgba(90,200,250,0.05), transparent 50%),
    #0A1A2F;
}
.container { max-width: 720px; margin: 0 auto; padding: 60px 24px 80px; }

/* ── Hero ── */
.hero { text-align: center; margin-bottom: 48px; }
.brand-line { display: flex; align-items: baseline; justify-content: center; gap: 8px; margin-bottom: 8px; }
.brand-e { font-weight: 700; font-size: 22px; letter-spacing: 0.22em; }
.brand-ai { font-weight: 700; font-size: 22px; letter-spacing: 0.22em; color: #5AC8FA; }
.brand-sub {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; color: #4A5A72;
  letter-spacing: 0.32em; text-transform: uppercase;
}
.hero h1 {
  font-weight: 200; font-size: 40px;
  letter-spacing: -0.04em; margin: 32px 0 12px;
}
.hero h1 em { font-style: italic; color: #44E5B8; font-weight: 500; }
.hero p { color: #7A8CA3; font-size: 14px; line-height: 1.7; max-width: 540px; margin: 0 auto; }

/* ── Value Props ── */
.props { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 48px; }
@media (max-width: 600px) { .props { grid-template-columns: 1fr; } }
.prop-card {
  background: #15263F;
  border: 1px solid rgba(122,140,163,0.12);
  padding: 24px 22px;
  transition: border-color 0.2s;
}
.prop-card:hover { border-color: rgba(68,229,184,0.25); }
.prop-icon { font-size: 24px; margin-bottom: 12px; }
.prop-title { font-weight: 600; font-size: 14px; margin-bottom: 6px; color: #F8FAFD; }
.prop-desc { color: #7A8CA3; font-size: 12px; line-height: 1.6; }

/* ── How It Works ── */
.how { margin-bottom: 48px; }
.how h2 {
  font-weight: 200; font-size: 22px;
  letter-spacing: -0.03em; text-align: center; margin-bottom: 28px;
}
.how h2 em { font-style: italic; color: #44E5B8; font-weight: 500; }
.steps { display: flex; flex-direction: column; gap: 20px; }
.step {
  display: flex; gap: 20px; align-items: flex-start;
  background: #15263F;
  border: 1px solid rgba(122,140,163,0.08);
  padding: 20px 24px;
}
.step-num {
  width: 36px; height: 36px; border-radius: 50%;
  background: rgba(68,229,184,0.1);
  border: 1px solid rgba(68,229,184,0.25);
  display: flex; align-items: center; justify-content: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px; color: #44E5B8; font-weight: 600; flex-shrink: 0;
}
.step-body { flex: 1; }
.step-title { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
.step-desc { color: #7A8CA3; font-size: 12px; line-height: 1.6; }

/* ── Signup Form ── */
.form-section { margin-bottom: 48px; }
.form-section h2 {
  font-weight: 200; font-size: 22px;
  letter-spacing: -0.03em; text-align: center; margin-bottom: 8px;
}
.form-section h2 em { font-style: italic; color: #44E5B8; font-weight: 500; }
.form-section > p {
  text-align: center;
  color: #7A8CA3; font-size: 13px; margin-bottom: 28px;
}
.signup-card {
  background: #15263F;
  border: 1px solid rgba(122,140,163,0.18);
  padding: 40px;
  max-width: 480px; margin: 0 auto;
}
.field { margin-bottom: 18px; }
.field label {
  display: block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; color: #7A8CA3;
  letter-spacing: 0.14em; text-transform: uppercase;
  margin-bottom: 5px;
}
.field input {
  width: 100%;
  background: rgba(0,0,0,0.4);
  color: #F8FAFD;
  border: 1px solid rgba(122,140,163,0.18);
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  padding: 12px 14px;
  outline: none;
  transition: border-color 0.2s;
}
.field input:focus { border-color: #44E5B8; }
.field .hint {
  font-size: 10px; color: #4A5A72;
  margin-top: 4px;
}
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 560px) { .row2 { grid-template-columns: 1fr; } }
.btn-submit {
  width: 100%;
  background: #44E5B8; color: #000;
  border: none; padding: 16px;
  font-family: 'Inter', sans-serif; font-weight: 700;
  font-size: 14px; letter-spacing: 0.04em;
  cursor: pointer; transition: all 0.2s;
  margin-top: 8px;
}
.btn-submit:hover { background: transparent; color: #44E5B8; outline: 1px solid #44E5B8; }
.btn-submit:disabled { opacity: 0.4; cursor: wait; }
.flash {
  display: none; padding: 12px 16px; margin-top: 14px;
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  letter-spacing: 0.04em; word-break: break-word;
}
.flash.show { display: block; }
.flash.success { color: #44E5B8; background: rgba(68,229,184,0.06); border: 1px solid rgba(68,229,184,0.25); }
.flash.error { color: #f43f5e; background: rgba(244,63,94,0.06); border: 1px solid rgba(244,63,94,0.25); }

/* ── Success State (after signup) ── */
.success-box { display: none; }
.success-box.show { display: block; }
.referral-link {
  background: rgba(0,0,0,0.4);
  border: 1px solid rgba(68,229,184,0.25);
  padding: 14px 18px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #44E5B8;
  word-break: break-all;
  margin: 14px 0;
  cursor: pointer;
  user-select: all;
}
.copy-hint {
  font-size: 10px; color: #4A5A72;
  text-align: center; margin-bottom: 18px;
}

/* ── Footer ── */
.foot {
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; color: #4A5A72;
  letter-spacing: 0.18em;
}
.foot a { color: #5AC8FA; text-decoration: none; }
.foot a:hover { text-decoration: underline; }
"""

_AFFILIATE_RECRUIT_HTML = ("""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Affiliate Program</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{_AFFILIATE_PAGE_CSS}</style>
</head><body>
<div class="container">

  <div class="hero">
    <div class="brand-line"><span class="brand-e">EMPIRE</span><span class="brand-ai">AI</span></div>
    <div class="brand-sub">Affiliate Partner Program</div>
    <h1>Earn <em>10% Commission</em><br>on Every Lead You Refer</h1>
    <p>Join the Empire AI revenue network. Share your unique referral link, and earn 10% on every qualified lead that converts. No contracts, no exclusivity — just a simple revenue share.</p>
  </div>

  <div class="props">
    <div class="prop-card">
      <div class="prop-icon">💰</div>
      <div class="prop-title">10% Commission</div>
      <div class="prop-desc">Earn 10% on every qualified lead you refer that converts into a settled claim or signed deal.</div>
    </div>
    <div class="prop-card">
      <div class="prop-icon">🔗</div>
      <div class="prop-title">Unique Referral Link</div>
      <div class="prop-desc">Get your own personalized referral link to share via email, social media, or your website.</div>
    </div>
    <div class="prop-card">
      <div class="prop-icon">📊</div>
      <div class="prop-title">Real-Time Dashboard</div>
      <div class="prop-desc">Track clicks, leads, conversions, and earnings in real-time through your affiliate dashboard.</div>
    </div>
    <div class="prop-card">
      <div class="prop-icon">🚀</div>
      <div class="prop-title">No Commitment</div>
      <div class="prop-desc">No contracts, no exclusivity, no minimums. Start earning immediately with zero risk.</div>
    </div>
  </div>

  <div class="how">
    <h2>How It <em>Works</em></h2>
    <div class="steps">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-body">
          <div class="step-title">Sign up below</div>
          <div class="step-desc">Fill out the form with your name, email, and phone. We'll create your account instantly.</div>
        </div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-body">
          <div class="step-title">Share your referral link</div>
          <div class="step-desc">We'll generate a unique link like empire-ai.co.uk/ref/your-name. Share it anywhere — email, social media, your website.</div>
        </div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-body">
          <div class="step-title">Earn commissions</div>
          <div class="step-desc">When someone clicks your link and submits their information, you earn 10% on any qualified lead that converts into revenue.</div>
        </div>
      </div>
    </div>
  </div>

  <div class="form-section" id="signupSection">
    <h2>Become an <em>Affiliate</em></h2>
    <p>Sign up below and get your referral link immediately.</p>
    <div class="signup-card">
      <form id="affiliateForm" onsubmit="return submitForm(event)">
        <div class="field">
          <label>Your name</label>
          <input type="text" id="name" placeholder="John Smith" required>
        </div>
        <div class="row2">
          <div class="field">
            <label>Email</label>
            <input type="email" id="email" placeholder="john@example.com" required>
          </div>
          <div class="field">
            <label>Phone</label>
            <input type="tel" id="phone" placeholder="+12145551234">
          </div>
        </div>
        <div class="field">
          <label>Company / Business (optional)</label>
          <input type="text" id="company" placeholder="Your Roofing Co">
          <div class="hint">If you own a business, enter the name so we can personalize your referral link.</div>
        </div>
        <button type="submit" class="btn-submit" id="submitBtn">Get Your Referral Link →</button>
      </form>
      <div id="flash" class="flash"></div>

      <div id="successBox" class="success-box">
        <div style="text-align:center;margin-bottom:14px">
          <span style="font-size:36px">🎉</span>
          <div style="font-weight:600;font-size:16px;margin-top:8px">You're in!</div>
          <div style="color:#7A8CA3;font-size:12px;margin-top:4px">Here's your unique referral link:</div>
        </div>
        <div id="referralLink" class="referral-link" onclick="copyLink(this)"></div>
        <div class="copy-hint">Click the link above to copy it to your clipboard</div>
        <div style="text-align:center;color:#7A8CA3;font-size:11px;line-height:1.6">
          Share this link via email, text, or social media.<br>
          You'll earn <strong style="color:#44E5B8">10% commission</strong> on every qualified lead that converts.
        </div>
      </div>
    </div>
  </div>

  <div class="foot">
    <a href="/">Empire AI</a> · <a href="/pricing">Pricing</a> · <a href="/support">Support</a><br>
    &copy; 2026 Empire AI Ltd
  </div>
</div>

<script>
async function submitForm(event) {
  event.preventDefault();
  const flash = document.getElementById('flash');
  const btn = document.getElementById('submitBtn');
  const form = document.getElementById('affiliateForm');
  const successBox = document.getElementById('successBox');
  const linkEl = document.getElementById('referralLink');

  flash.className = 'flash';
  btn.disabled = true; btn.textContent = 'Creating your link...';

  try {
    const r = await fetch('/api/v1/affiliates/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('name').value.trim(),
        email: document.getElementById('email').value.trim(),
        phone: document.getElementById('phone').value.trim(),
        company: document.getElementById('company').value.trim(),
      }),
    });
    const d = await r.json();
    if (r.ok && d.ok) {
      form.style.display = 'none';
      flash.className = 'flash';
      linkEl.textContent = window.location.origin + '/ref/' + d.referral_code;
      successBox.classList.add('show');
    } else {
      flash.className = 'flash show error';
      flash.textContent = '✗ ' + (d.error || 'Signup failed. Please try again.');
    }
  } catch (e) {
    flash.className = 'flash show error';
    flash.textContent = '✗ Network error. Please check your connection.';
  } finally {
    btn.disabled = false; btn.textContent = 'Get Your Referral Link →';
  }
  return false;
}

function copyLink(el) {
  navigator.clipboard.writeText(url).then(() => {
    const orig = el.style.borderColor;
    el.style.borderColor = '#44E5B8';
    el.textContent = '✓ Copied!';
    setTimeout(() => {
      el.style.borderColor = 'rgba(68,229,184,0.25)';
      el.textContent = window.location.origin + '/ref/' + el.textContent.replace(/^.*ref\\//, 'ref/');
    }, 1500);
  }).catch(() => {});
}
</script>
</body></html>""").replace("{_AFFILIATE_PAGE_CSS}", _AFFILIATE_PAGE_CSS)


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
def register_affiliate_recruit_routes(app: FastAPI, require_auth: Optional[Callable] = None):
    """Register affiliate recruitment routes."""

    # ── PUBLIC: RECRUITMENT PAGE ──────────────────────────────────────
    @app.get("/affiliates", response_class=HTMLResponse)
    async def affiliates_page():
        return HTMLResponse(_AFFILIATE_RECRUIT_HTML)

    # ── PUBLIC: REFERRAL LINK REDIRECT ─────────────────────────────────
    @app.get("/ref/{code}")
    async def affiliate_ref_redirect(code: str):
        """Redirect through /track/aff/{code} for cookie-based tracking."""
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/track/aff/{code}", status_code=302)

    # ── PUBLIC: SIGNUP ─────────────────────────────────────────────────
    @app.post("/api/v1/affiliates/signup")
    async def affiliates_signup(request: Request):
        """Public endpoint. Creates an affiliate record with auto-generated referral code."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON payload")

        name = (body.get("name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        phone = (body.get("phone") or "").strip()
        company = (body.get("company") or "").strip()

        # ── Validation ────────────────────────────────────────────────
        if not name:
            raise HTTPException(400, "Name is required")
        if not email or "@" not in email:
            raise HTTPException(400, "A valid email is required")

        # ── Check for duplicate email ─────────────────────────────────
        dup = _sb.table("affiliates").select("id, name") \
            .eq("email", email).limit(1).execute()
        if dup.data:
            raise HTTPException(409, "An affiliate with this email already exists")

        # ── Generate unique referral code ─────────────────────────────
        ref_name = company if company else name
        referral_code = _generate_referral_code(ref_name)
        # Ensure uniqueness
        for _ in range(10):
            chk = _sb.table("affiliates").select("id") \
                .eq("referral_code", referral_code).limit(1).execute()
            if not chk.data:
                break
            referral_code = _generate_referral_code(ref_name)

        # ── Insert affiliate ──────────────────────────────────────────
        ip = request.client.host if request.client else ""
        row = {
            "name":           name,
            "email":          email,
            "phone":          phone or None,
            "company":        company or "",
            "referral_code":  referral_code,
            "commission_rate": 0.10,
            "status":         "active",
            "is_active":      True,
            "source":         "web_form",
            "metadata":       {"signup_ip": ip},
        }

        try:
            res = _sb.table("affiliates").insert(row).execute()
            if not res.data:
                raise HTTPException(500, "Failed to create affiliate record")
            new_aff = res.data[0]
            aff_id = str(new_aff["id"])
        except Exception as e:
            err_str = str(e).lower()
            if "unique" in err_str or "duplicate" in err_str:
                raise HTTPException(409, "An affiliate with this email already exists")
            log.error(f"[affiliate] insert failed: {e}")
            raise HTTPException(500, f"Database error: {e}")

        # ── Notify owner ──────────────────────────────────────────────
        await _notify_owner(
            title="New Affiliate Signup",
            message=(
                f"{name} ({email}) signed up as an affiliate. "
                f"Referral code: {referral_code}. "
                f"Manage at: https://empire-ai.co.uk/command#/affiliates"
            ),
            tags="new_affiliate,bell",
        )

        log.info(f"[affiliate] signup: {name} <{email}> → code={referral_code} id={aff_id}")

        return {
            "ok":            True,
            "affiliate_id":  aff_id,
            "referral_code": referral_code,
            "referral_url":  f"/ref/{referral_code}",
            "commission_rate": 0.10,
        }

    # ── AUTH-REQUIRED: LIST AFFILIATES ─────────────────────────────────
    if require_auth:
        @app.get("/api/v1/affiliates/list")
        async def affiliates_list(
            op: dict = Depends(require_auth),
            limit: int = Query(100, ge=1, le=500),
            status: str = Query("", pattern="^(active|paused|suspended|)$"),
        ):
            """List all affiliates with optional status filter."""
            try:
                q = _sb.table("affiliates").select("*") \
                    .order("created_at", desc=True) \
                    .limit(limit)
                if status:
                    q = q.eq("status", status)
                res = q.execute()
                return {"affiliates": res.data or [], "count": len(res.data or [])}
            except Exception as e:
                raise HTTPException(500, str(e)[:200])

        @app.get("/api/v1/affiliates/stats")
        async def affiliates_stats(
            op: dict = Depends(require_auth),
        ):
            """Aggregate affiliate program stats."""
            try:
                # Total affiliates
                total = _sb.table("affiliates").select("id", count="exact") \
                    .limit(1).execute()
                total_count = getattr(total, "count", 0)

                # Active affiliates
                active = _sb.table("affiliates").select("id", count="exact") \
                    .eq("status", "active").limit(1).execute()
                active_count = getattr(active, "count", 0)

                # Summary from performance view
                perf = _sb.table("affiliate_performance").select(
                    "total_earned_usd,total_paid_usd,total_clicks,total_leads,total_conversions"
                ).limit(500).execute()
                perf_rows = perf.data or []

                total_earned = sum(float(r.get("total_earned_usd", 0) or 0) for r in perf_rows)
                total_paid = sum(float(r.get("total_paid_usd", 0) or 0) for r in perf_rows)
                total_clicks = sum(int(r.get("total_clicks", 0) or 0) for r in perf_rows)
                total_leads = sum(int(r.get("total_leads", 0) or 0) for r in perf_rows)
                total_conversions = sum(int(r.get("total_conversions", 0) or 0) for r in perf_rows)

                return {
                    "total_affiliates": total_count,
                    "active_affiliates": active_count,
                    "total_clicks": total_clicks,
                    "total_leads": total_leads,
                    "total_conversions": total_conversions,
                    "total_earned_usd": round(total_earned, 2),
                    "total_paid_usd": round(total_paid, 2),
                    "outstanding_balance": round(total_earned - total_paid, 2),
                    "pending_payouts": round(total_earned - total_paid, 2),
                }
            except Exception as e:
                log.warning(f"[affiliate] stats error: {e}")
                return {
                    "total_affiliates": 0,
                    "active_affiliates": 0,
                    "error": str(e)[:200],
                }

    log.info(
        "[affiliate] Routes registered · "
        "/affiliates · /ref/{code} · "
        "/api/v1/affiliates/{signup,list,stats}"
    )
