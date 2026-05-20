"""
EMPIRE V49 · CONTRACTOR ONBOARDING
====================================
The recruitment pipeline. Closes the loop: contractors find empire-ai.co.uk,
sign up via the public form, get magic-link verified, enter the vetting queue,
operator approves them, they're live in the dispatch pool.

Three surfaces:

  1. PUBLIC SIGNUP   GET  /contractors/signup
                      POST /api/v1/contractors/apply
                      → contractor fills the form
                      → applications row created with status=pending_email
                      → magic link emailed via Resend

  2. EMAIL VERIFY    GET  /contractors/verify?t=...
                      → magic link landing
                      → applications.status flips to pending_review
                      → operator gets ntfy push

  3. OPERATOR REVIEW POST /api/v1/contractors/approve
                      POST /api/v1/contractors/reject
                      → on approval, contractors row created
                      → welcome email sent
                      → contractor is live in dispatch pool

Schema:
    CREATE TABLE contractor_applications (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at      timestamptz NOT NULL DEFAULT now(),
        name            text NOT NULL,
        email           text NOT NULL,
        phone           text NOT NULL,
        company         text,
        metro           text NOT NULL,
        license_no      text,
        license_state   text,
        specialties     text[] DEFAULT '{}',
        years_in_biz    int,
        insurance_carrier text,
        ein             text,
        notes           text,
        status          text NOT NULL DEFAULT 'pending_email'
            CHECK (status IN ('pending_email','pending_review','approved','rejected','withdrawn')),
        approved_at     timestamptz,
        rejected_at     timestamptz,
        rejected_reason text,
        contractor_id   uuid REFERENCES contractors(id),
        meta            jsonb DEFAULT '{}'::jsonb
    );
    CREATE UNIQUE INDEX ON contractor_applications (email)
        WHERE status NOT IN ('rejected','withdrawn');
    CREATE INDEX ON contractor_applications (status, created_at DESC);

Wire-up in hub.py:
    from empire_contractors import register_contractor_routes

    register_contractor_routes(
        app,
        require_auth=require_auth,
        get_db=get_db,
        sign_token=_sign_token,        # reuse the HMAC helpers from hub
        verify_token=_verify_token,
        send_email=_send_email,
        public_base_url=PUBLIC_BASE_URL,
        ntfy_topic=NTFY_TOPIC,
        ntfy_token=NTFY_TOKEN,
        link_ttl_seconds=72 * 3600,
    )
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse


log = logging.getLogger("empire.contractors")


# Valid specialties — keep tight so contractors self-select cleanly
SPECIALTIES = [
    "roofing", "siding", "gutters", "windows",
    "water_damage", "fire_damage", "mold_remediation",
    "structural", "concrete", "foundation",
    "hvac", "electrical", "plumbing",
    "general_contracting", "emergency_response",
]

# Metro options matching the radar_targets corridors
METROS = [
    "Dallas / Fort Worth", "Houston", "San Antonio", "Austin",
    "Plano", "Mobile", "Atlanta", "Miami", "Other (specify in notes)",
]


# ─────────────────────────────────────────────────────────────────────────────
# HTML RENDERING — public-facing pages
# ─────────────────────────────────────────────────────────────────────────────
def _empire_page_shell(title: str, body_html: str, *, success: bool = False, error: bool = False) -> str:
    """Standalone public-facing Empire page (no operator sidebar)."""
    accent_color = "#10b981" if success else ("#f43f5e" if error else "#10b981")
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Empire AI · {title}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@100;200;300;400;500;700;900&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --empire-canvas: #0A1A2F;
  --empire-surface: #15263F;
  --empire-border: rgba(122,140,163,0.18);
  --signal-teal: #44E5B8;
  --strike-cyan: #5AC8FA;
  --empire-white: #F8FAFD;
  --empire-silver: #C8D4E4;
  --empire-mist: #7A8CA3;
  --empire-fog: #4A5A72;
  --accent: {accent_color};
}}
html, body {{ background: var(--empire-canvas); min-height: 100vh; }}
body {{
  font-family: 'Inter', -apple-system, sans-serif;
  color: var(--empire-white); letter-spacing: -0.02em;
  -webkit-font-smoothing: antialiased;
  padding: 32px 20px;
  background:
    radial-gradient(ellipse at top right, rgba(68,229,184,0.06) 0%, transparent 50%),
    radial-gradient(ellipse at bottom left, rgba(90,200,250,0.05) 0%, transparent 50%),
    var(--empire-canvas);
  min-height: 100vh;
}}
.wrap {{ max-width: 640px; margin: 0 auto; }}
.brand {{
  display: flex; align-items: baseline; justify-content: center;
  margin-bottom: 8px; gap: 8px;
}}
.brand .empire {{
  font-weight: 700; font-size: 24px; letter-spacing: 0.22em;
}}
.brand .ai {{
  font-weight: 700; font-size: 24px; letter-spacing: 0.22em;
  color: var(--strike-cyan);
}}
.tag {{
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--empire-fog);
  letter-spacing: 0.32em;
  text-transform: uppercase;
  margin-bottom: 40px;
}}
h1 {{
  font-weight: 200; font-size: 32px;
  letter-spacing: -0.04em; line-height: 1.2;
  margin-bottom: 12px;
}}
h1 em {{ font-style: italic; color: var(--signal-teal); font-weight: 500; }}
.sub {{
  color: var(--empire-mist); font-size: 15px;
  line-height: 1.6; margin-bottom: 32px;
}}
.panel {{
  background: var(--empire-surface);
  border: 1px solid var(--empire-border);
  padding: 32px 28px;
  margin-bottom: 16px;
}}
.field {{ margin-bottom: 18px; }}
.field label {{
  display: block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px; color: var(--empire-mist);
  letter-spacing: 0.14em; text-transform: uppercase;
  margin-bottom: 6px;
}}
.field label .req {{ color: var(--accent); }}
input, select, textarea {{
  width: 100%;
  background: rgba(0,0,0,0.4);
  color: var(--empire-white);
  border: 1px solid var(--empire-border);
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  padding: 12px 14px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}}
input:focus, select:focus, textarea:focus {{
  border-color: var(--signal-teal);
  box-shadow: 0 0 0 1px rgba(68,229,184,0.25);
}}
textarea {{ resize: vertical; min-height: 80px; line-height: 1.6; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
.checks {{
  display: grid; grid-template-columns: repeat(2, 1fr);
  gap: 10px; margin-top: 8px;
}}
.checks label {{
  display: flex; align-items: center; gap: 8px;
  background: rgba(0,0,0,0.3);
  border: 1px solid var(--empire-border);
  padding: 10px 12px;
  font-family: 'Inter', sans-serif;
  font-size: 12px;
  color: var(--empire-silver);
  letter-spacing: 0;
  text-transform: none;
  margin-bottom: 0;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}}
.checks label:hover {{ border-color: var(--empire-mist); }}
.checks input[type="checkbox"] {{ width: 14px; height: 14px; accent-color: var(--signal-teal); }}
.btn {{
  width: 100%;
  background: var(--signal-teal); color: #000;
  border: none; padding: 16px;
  font-family: 'Inter', sans-serif;
  font-weight: 700; font-size: 14px;
  letter-spacing: 0.04em;
  cursor: pointer; transition: all 0.2s;
  margin-top: 8px;
}}
.btn:hover {{ background: transparent; color: var(--signal-teal); outline: 1px solid var(--signal-teal); box-shadow: 0 0 24px rgba(68,229,184,0.3); }}
.btn:disabled {{ opacity: 0.4; cursor: wait; }}
.terms {{
  margin-top: 16px;
  padding: 16px;
  background: rgba(0,0,0,0.3);
  border: 1px solid rgba(122,140,163,0.1);
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--empire-mist);
  line-height: 1.7;
}}
.terms strong {{ color: var(--empire-silver); }}
.flash {{
  display: none;
  padding: 14px 18px;
  margin-bottom: 16px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.08em;
}}
.flash.success {{
  display: block;
  color: var(--signal-teal);
  background: rgba(68,229,184,0.06);
  border: 1px solid rgba(68,229,184,0.25);
}}
.flash.error {{
  display: block;
  color: #f43f5e;
  background: rgba(244,63,94,0.06);
  border: 1px solid rgba(244,63,94,0.25);
}}
.icon-large {{
  font-size: 48px;
  text-align: center;
  margin-bottom: 24px;
  color: var(--accent);
}}
.footnote {{
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--empire-fog);
  letter-spacing: 0.18em;
  margin-top: 24px;
}}
</style></head><body>
<div class="wrap">
  <div class="brand">
    <span class="empire">EMPIRE</span><span class="ai">AI</span>
  </div>
  <div class="tag">Predictive Revenue · Contractor Portal</div>
  {body_html}
  <div class="footnote">Empire AI Ltd · empire-ai.co.uk · Sovereign Operator</div>
</div>
</body></html>"""


def _signup_form_html() -> str:
    specialties_html = "\n".join([
        f'<label><input type="checkbox" name="specialties" value="{s}">'
        f'<span>{s.replace("_", " ").title()}</span></label>'
        for s in SPECIALTIES
    ])
    metros_html = "\n".join([
        f'<option value="{m}">{m}</option>'
        for m in METROS
    ])

    return f"""
    <h1>Apply to the <em>Empire</em> Network</h1>
    <p class="sub">
      Empire AI dispatches storm-verified commercial repair leads to vetted
      local contractors. Independent contractor agreement · 1% success fee
      on settled claims is paid by the property owner, not by you.
    </p>

    <div id="flash" class="flash"></div>

    <div class="panel">
      <div class="field">
        <label>Full name <span class="req">*</span></label>
        <input type="text" id="name" required maxlength="120" placeholder="Jane Smith">
      </div>

      <div class="grid-2">
        <div class="field">
          <label>Email <span class="req">*</span></label>
          <input type="email" id="email" required maxlength="200" placeholder="jane@example.com">
        </div>
        <div class="field">
          <label>Phone <span class="req">*</span></label>
          <input type="tel" id="phone" required maxlength="20" placeholder="+1 214 555 1234">
        </div>
      </div>

      <div class="field">
        <label>Company name</label>
        <input type="text" id="company" maxlength="160" placeholder="Smith Roofing LLC">
      </div>

      <div class="grid-2">
        <div class="field">
          <label>Primary metro <span class="req">*</span></label>
          <select id="metro" required>
            <option value="">— select —</option>
            {metros_html}
          </select>
        </div>
        <div class="field">
          <label>Years in business</label>
          <input type="number" id="years_in_biz" min="0" max="100" placeholder="8">
        </div>
      </div>

      <div class="grid-2">
        <div class="field">
          <label>Contractor license #</label>
          <input type="text" id="license_no" maxlength="40" placeholder="if applicable">
        </div>
        <div class="field">
          <label>License state</label>
          <input type="text" id="license_state" maxlength="2" placeholder="TX">
        </div>
      </div>

      <div class="grid-2">
        <div class="field">
          <label>Insurance carrier</label>
          <input type="text" id="insurance_carrier" maxlength="100" placeholder="Liability + workers comp">
        </div>
        <div class="field">
          <label>EIN (last 4)</label>
          <input type="text" id="ein" maxlength="9" placeholder="optional">
        </div>
      </div>

      <div class="field">
        <label>Specialties (select all that apply)</label>
        <div class="checks">
          {specialties_html}
        </div>
      </div>

      <div class="field">
        <label>Notes (anything relevant)</label>
        <textarea id="notes" maxlength="1000" rows="3" placeholder="Service radius, equipment, crew size, prior storm work..."></textarea>
      </div>

      <button class="btn" id="submit-btn" onclick="submitApplication()">Submit application</button>
    </div>

    <div class="terms">
      <strong>What happens next:</strong>
      <ol style="margin: 8px 0 0 18px; line-height: 1.8;">
        <li>We email you a verification link (check spam if not seen)</li>
        <li>Click the link to confirm your email</li>
        <li>Our team reviews your application within 1 business day</li>
        <li>Approved contractors enter the dispatch pool immediately</li>
      </ol>
      <br>
      <strong>How payment works:</strong> Empire AI tracks the underlying
      insurance claim. On settlement, your contractor share of the 1%
      success fee is wired automatically. No upfront cost, no monthly fee.
      You operate as an independent business and verify all property owner
      details directly.
    </div>

    <script>
    async function submitApplication() {{
      const flash = document.getElementById('flash');
      flash.className = 'flash';
      const btn = document.getElementById('submit-btn');
      btn.disabled = true; btn.textContent = 'Submitting...';

      const specialties = Array.from(document.querySelectorAll('input[name="specialties"]:checked'))
                              .map(el => el.value);

      const payload = {{
        name:              document.getElementById('name').value.trim(),
        email:             document.getElementById('email').value.trim().toLowerCase(),
        phone:             document.getElementById('phone').value.trim(),
        company:           document.getElementById('company').value.trim(),
        metro:             document.getElementById('metro').value,
        license_no:        document.getElementById('license_no').value.trim(),
        license_state:     document.getElementById('license_state').value.trim().toUpperCase(),
        years_in_biz:      parseInt(document.getElementById('years_in_biz').value) || null,
        insurance_carrier: document.getElementById('insurance_carrier').value.trim(),
        ein:               document.getElementById('ein').value.trim(),
        specialties:       specialties,
        notes:             document.getElementById('notes').value.trim(),
      }};

      if (!payload.name || !payload.email || !payload.phone || !payload.metro) {{
        flash.className = 'flash error';
        flash.textContent = '✗ Please fill in all required fields (name, email, phone, metro)';
        btn.disabled = false; btn.textContent = 'Submit application';
        return;
      }}

      try {{
        const r = await fetch('/api/v1/contractors/apply', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload),
        }});
        const data = await r.json();
        if (r.ok && data.ok) {{
          flash.className = 'flash success';
          flash.textContent = '✓ Application received. Check your email for a verification link.';
          setTimeout(() => {{ location.href = '/contractors/thanks'; }}, 1500);
        }} else {{
          flash.className = 'flash error';
          flash.textContent = '✗ ' + (data.error || 'Submission failed. Please try again.');
          btn.disabled = false; btn.textContent = 'Submit application';
        }}
      }} catch (e) {{
        flash.className = 'flash error';
        flash.textContent = '✗ Network error · ' + e.message;
        btn.disabled = false; btn.textContent = 'Submit application';
      }}
    }}
    </script>
    """


def _thanks_html() -> str:
    return """
    <h1>Check your <em>inbox</em></h1>
    <p class="sub">
      We've sent a verification link to the email you provided. Click it
      to confirm your application and enter the operator review queue.
    </p>
    <div class="panel">
      <div class="icon-large">✓</div>
      <p style="text-align:center; color: var(--empire-silver); font-size: 14px; line-height: 1.7;">
        Most applications are reviewed within 1 business day.<br>
        We'll email you the moment your account goes live.
      </p>
    </div>
    """


def _verified_html(applicant_name: str) -> str:
    return f"""
    <h1>Email <em>verified</em></h1>
    <p class="sub">
      Thanks, {applicant_name}. Your application is now in the operator
      review queue.
    </p>
    <div class="panel">
      <div class="icon-large">✓</div>
      <p style="text-align:center; color: var(--empire-silver); font-size: 14px; line-height: 1.7;">
        We'll review within 1 business day.<br>
        Watch your inbox for an approval notice.
      </p>
    </div>
    """


def _error_html(message: str) -> str:
    return f"""
    <h1>Something went <em>wrong</em></h1>
    <div class="panel">
      <div class="icon-large" style="color:#f43f5e;">✗</div>
      <p style="text-align:center; color: var(--empire-silver); font-size: 14px; line-height: 1.7;">
        {message}
      </p>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────
def register_contractor_routes(
    app: FastAPI,
    *,
    require_auth: Callable,
    get_db: Callable,
    sign_token: Callable,         # reuse hub's _sign_token
    verify_token: Callable,       # reuse hub's _verify_token
    send_email: Callable,         # reuse hub's _send_email
    public_base_url: str,
    ntfy_topic: str = "",
    ntfy_token: str = "",
    link_ttl_seconds: int = 72 * 3600,
):
    """
    Wire all contractor onboarding routes. Reuses the HMAC token helpers
    and email sender already in hub.py so contractor magic links work
    identically to dispatch magic links.
    """

    # ── PUBLIC SIGNUP PAGE ──────────────────────────────────────────────
    @app.get("/contractors/signup", response_class=HTMLResponse)
    async def contractor_signup_page():
        return HTMLResponse(_empire_page_shell("Apply", _signup_form_html()))

    @app.get("/contractors/thanks", response_class=HTMLResponse)
    async def contractor_thanks_page():
        return HTMLResponse(_empire_page_shell("Thanks", _thanks_html(), success=True))

    # ── APPLICATION SUBMIT ──────────────────────────────────────────────
    @app.post("/api/v1/contractors/apply")
    async def contractor_apply(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON"}, 400)

        # Validate required fields
        name  = (body.get("name")  or "").strip()
        email = (body.get("email") or "").strip().lower()
        phone = (body.get("phone") or "").strip()
        metro = (body.get("metro") or "").strip()

        if not (name and email and phone and metro):
            return JSONResponse(
                {"ok": False, "error": "name, email, phone, and metro are required"},
                400,
            )

        if "@" not in email or "." not in email.split("@", 1)[-1]:
            return JSONResponse({"ok": False, "error": "Invalid email"}, 400)

        # Validate specialties (drop any not in our enum)
        raw_specialties = body.get("specialties") or []
        specialties = [s for s in raw_specialties if s in SPECIALTIES][:10]

        try:
            db = get_db()
        except Exception as e:
            log.error(f"DB unavailable: {e}")
            return JSONResponse({"ok": False, "error": "Service temporarily unavailable"}, 503)

        # Check for existing pending/approved application on this email
        try:
            existing = db.table("contractor_applications").select("id, status") \
                .eq("email", email) \
                .not_.in_("status", ["rejected", "withdrawn"]) \
                .limit(1).execute()
            if existing.data:
                return JSONResponse(
                    {"ok": False, "error": f"An application for this email already exists (status: {existing.data[0]['status']})"},
                    409,
                )
        except Exception as e:
            log.debug(f"[contractors] dup-check failed: {e}")

        record = {
            "name":              name[:120],
            "email":             email[:200],
            "phone":             phone[:20],
            "company":           (body.get("company") or "").strip()[:160] or None,
            "metro":             metro[:80],
            "license_no":        (body.get("license_no") or "").strip()[:40] or None,
            "license_state":     (body.get("license_state") or "").strip().upper()[:2] or None,
            "specialties":       specialties,
            "years_in_biz":      body.get("years_in_biz"),
            "insurance_carrier": (body.get("insurance_carrier") or "").strip()[:100] or None,
            "ein":               (body.get("ein") or "").strip()[:9] or None,
            "notes":             (body.get("notes") or "").strip()[:1000] or None,
            "status":            "pending_email",
            "meta": {
                "user_agent": request.headers.get("user-agent", "")[:200],
                "ip":         request.client.host if request.client else "",
            },
        }

        try:
            ins = db.table("contractor_applications").insert(record).execute()
        except Exception as e:
            log.error(f"[contractors] insert failed: {e}")
            return JSONResponse({"ok": False, "error": "Failed to save application"}, 500)

        if not ins.data:
            return JSONResponse({"ok": False, "error": "Failed to save application"}, 500)

        application_id = ins.data[0]["id"]

        # Build magic-link token (HMAC-signed via hub's helper)
        token_payload = {
            "app_id": application_id,
            "email":  email,
            "exp":    int(time.time()) + link_ttl_seconds,
            "iat":    int(time.time()),
            "kind":   "contractor_verify",
        }
        token = sign_token(token_payload)
        verify_link = f"{public_base_url.rstrip('/')}/contractors/verify?t={token}"

        # Send the verification email
        html = f"""
          <div style="font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
            <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
              <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Contractor Application</div>
              <div style="font-size:22px;font-weight:700;color:#10b981;margin-top:6px;letter-spacing:-0.02em;">
                Verify your email
              </div>
            </div>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              Hi {name}, thanks for applying to the Empire AI contractor network.
              Click the button below to verify your email and enter the review queue.
            </p>
            <div style="margin:28px 0;text-align:center;">
              <a href="{verify_link}" style="display:inline-block;background:#10b981;color:#000;padding:14px 32px;text-decoration:none;font-weight:700;letter-spacing:.04em;">Verify email &rarr;</a>
            </div>
            <div style="font-size:11px;color:#52525b;line-height:1.7;">
              Link expires in 72 hours. If you didn't apply, ignore this email.
            </div>
          </div>
        """
        email_result = await send_email(
            to=email,
            subject="Empire AI · Verify your contractor application",
            html=html,
        )

        # Ntfy the operator
        if ntfy_topic:
            try:
                headers = {
                    "Title":    "🤝 New contractor application",
                    "Priority": "default",
                    "Tags":     "wrench",
                }
                if ntfy_token:
                    headers["Authorization"] = f"Bearer {ntfy_token}"
                async with httpx.AsyncClient() as c:
                    await c.post(
                        f"https://ntfy.sh/{ntfy_topic}",
                        data=f"{name} · {metro}\n{email}\nSpecialties: {', '.join(specialties) or 'none'}",
                        headers=headers,
                        timeout=5.0,
                    )
            except Exception:
                pass

        return {
            "ok":             True,
            "application_id": application_id,
            "email_sent":     email_result.get("ok", False) if isinstance(email_result, dict) else bool(email_result),
        }

    # ── EMAIL VERIFICATION LANDING ──────────────────────────────────────
    @app.get("/contractors/verify", response_class=HTMLResponse)
    async def contractor_verify(t: str = Query(...)):
        payload = verify_token(t)
        if not payload or payload.get("kind") != "contractor_verify":
            return HTMLResponse(
                _empire_page_shell(
                    "Link invalid",
                    _error_html("This verification link is invalid or expired. Please reapply or contact us."),
                    error=True,
                ),
                status_code=401,
            )

        try:
            db = get_db()
            res = db.table("contractor_applications").select("*") \
                .eq("id", payload["app_id"]).limit(1).execute()
            if not res.data:
                return HTMLResponse(
                    _empire_page_shell("Not found", _error_html("Application not found."), error=True),
                    status_code=404,
                )

            app_row = res.data[0]
            if app_row["status"] == "pending_email":
                db.table("contractor_applications").update({
                    "status": "pending_review",
                }).eq("id", payload["app_id"]).execute()
        except Exception as e:
            log.error(f"[contractors] verify update failed: {e}")
            return HTMLResponse(
                _empire_page_shell("Error", _error_html("Service error — please try again."), error=True),
                status_code=500,
            )

        # Push operator ntfy
        if ntfy_topic:
            try:
                headers = {
                    "Title":    "✅ Application email verified",
                    "Priority": "default",
                    "Tags":     "white_check_mark",
                }
                if ntfy_token:
                    headers["Authorization"] = f"Bearer {ntfy_token}"
                async with httpx.AsyncClient() as c:
                    await c.post(
                        f"https://ntfy.sh/{ntfy_topic}",
                        data=f"{app_row['name']} · {app_row['email']}\nReady for review",
                        headers=headers,
                        timeout=5.0,
                    )
            except Exception:
                pass

        return HTMLResponse(
            _empire_page_shell("Verified", _verified_html(app_row["name"]), success=True),
        )

    # ── OPERATOR: LIST PENDING APPLICATIONS ─────────────────────────────
    @app.get("/api/v1/contractors/applications")
    async def list_applications(
        status: str = Query("pending_review"),
        limit:  int = Query(50),
        auth:   bool = Depends(require_auth),
    ):
        try:
            db = get_db()
            q = db.table("contractor_applications").select("*") \
                .order("created_at", desc=True).limit(limit)
            if status and status != "all":
                q = q.eq("status", status)
            return q.execute().data or []
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── OPERATOR: APPROVE ───────────────────────────────────────────────
    @app.post("/api/v1/contractors/approve")
    async def approve_application(request: Request, auth: bool = Depends(require_auth)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        application_id = body.get("application_id")
        if not application_id:
            raise HTTPException(400, "application_id required")

        try:
            db = get_db()
            res = db.table("contractor_applications").select("*") \
                .eq("id", application_id).limit(1).execute()
            if not res.data:
                raise HTTPException(404, "Application not found")
            app_row = res.data[0]
            if app_row["status"] != "pending_review":
                raise HTTPException(409, f"Cannot approve — status is '{app_row['status']}'")

            # Create the contractor record (becomes live in dispatch pool)
            contractor_record = {
                "name":          app_row["name"],
                "email":         app_row["email"],
                "phone":         app_row["phone"],
                "metro":         app_row["metro"],
                "license_no":    app_row.get("license_no"),
                "license_state": app_row.get("license_state"),
                "specialties":   app_row.get("specialties") or [],
                "active":        True,
                "trust_score":   5.0,  # neutral starting point
                "completed_jobs": 0,
            }
            ins = db.table("contractors").insert(contractor_record).execute()
            contractor_id = ins.data[0]["id"] if ins.data else None

            # Update application
            db.table("contractor_applications").update({
                "status":         "approved",
                "approved_at":    datetime.now(timezone.utc).isoformat(),
                "contractor_id":  contractor_id,
            }).eq("id", application_id).execute()
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[contractors] approve failed: {e}")
            raise HTTPException(500, str(e))

        # Send welcome email
        welcome_html = f"""
          <div style="font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
            <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
              <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Approved</div>
              <div style="font-size:22px;font-weight:700;color:#10b981;margin-top:6px;letter-spacing:-0.02em;">
                Welcome to the network
              </div>
            </div>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              Hi {app_row['name']}, your application has been approved. You are now
              live in the {app_row['metro']} dispatch pool.
            </p>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              When a verified storm hit matches your metro and specialties,
              you'll receive a strike dispatch email with a single-tap accept
              link. The first one to accept wins the job.
            </p>
            <div style="margin-top:24px;padding:16px;background:#18181b;border-left:2px solid #10b981;font-size:12px;line-height:1.7;color:#a1a1aa;">
              <strong style="color:#d4d4d8;">How payment works:</strong><br>
              When the underlying claim settles, your contractor share of the
              1% success fee is wired automatically. No upfront cost, no monthly fee.
            </div>
          </div>
        """
        await send_email(
            to=app_row["email"],
            subject="Empire AI · Application approved",
            html=welcome_html,
        )

        return {"ok": True, "contractor_id": contractor_id}

    # ── OPERATOR: REJECT ────────────────────────────────────────────────
    @app.post("/api/v1/contractors/reject")
    async def reject_application(request: Request, auth: bool = Depends(require_auth)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        application_id = body.get("application_id")
        reason         = (body.get("reason") or "Application declined").strip()[:500]
        if not application_id:
            raise HTTPException(400, "application_id required")

        try:
            db = get_db()
            res = db.table("contractor_applications").select("*") \
                .eq("id", application_id).limit(1).execute()
            if not res.data:
                raise HTTPException(404, "Application not found")
            app_row = res.data[0]

            db.table("contractor_applications").update({
                "status":          "rejected",
                "rejected_at":     datetime.now(timezone.utc).isoformat(),
                "rejected_reason": reason,
            }).eq("id", application_id).execute()
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[contractors] reject failed: {e}")
            raise HTTPException(500, str(e))

        # Optional: send rejection email (commented out by default — many
        # operators prefer silent reject over notifying. Enable if you want.)
        # await send_email(
        #     to=app_row["email"],
        #     subject="Empire AI · Application update",
        #     html=f"<p>Hi {app_row['name']}, we are not able to approve your "
        #          f"application at this time. {reason}</p>",
        # )

        return {"ok": True}

    log.info("[contractors] Routes registered · /contractors/{signup,verify,thanks} · /api/v1/contractors/{apply,applications,approve,reject}")
