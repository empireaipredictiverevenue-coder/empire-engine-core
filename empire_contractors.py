"""
EMPIRE V49 · CONTRACTORS LANDING PAGE
=====================================
Public landing page at /contractors. The trust-anchor for the
contractor_recruit funnel: contractor gets a text from us, clicks
the link, lands here, sees the offer, self-onboards.

This page is a sibling of /pricing and / (splash). It is NOT part
of the operator command SPA. Public, no auth, no call required.

The chat widget at the bottom-right is owned by buffy; it's loaded
via <script src="/static/contractors/chat.js"> on the page. This
module does NOT ship the chat JS. If the file is missing, the
chat bubble simply doesn't render (graceful degradation).
"""

import os
import re
import json
import logging
import hashlib
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse

try:
    from empire_tokens import empire_head
except ImportError:
    def empire_head(title: str = "Empire AI", extra: str = "") -> str:
        return f"<head><title>{title}</title></head>"


log = logging.getLogger("empire.contractors_page")


# TCPA-compliant E.164 regex: +[country][number], 8-15 digits total
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TRADE_ENUM = (
    "roofing",
    "general_contractor",
    "restoration",
    "water_mitigation",
    "electrical",
    "plumbing",
    "hvac",
    "other",
)

# Back-compat exports for empire_command_dispatch.py — keeps the old
# import contract (from empire_contractors import SPECIALTIES, METROS)
# working. These are the operator-dashboard's specialty chips + metro
# filter dropdown. Keep these in sync with TRADE_ENUM above.
SPECIALTIES = list(TRADE_ENUM)
METROS = (
    "DFW",
    "Houston",
    "San Antonio",
    "Austin",
    "Waco",
    "Temple",
    "Bryan/College Station",
    "Tyler",
    "Lubbock",
    "Amarillo",
    "El Paso",
    "Corpus Christi",
)


def _page_css() -> str:
    """Page-specific CSS, layered on top of EMPIRE_* tokens."""
    return """
    .co-body {
      min-height: 100vh;
      background: linear-gradient(180deg, #0A1A2F 0%, #08121F 100%);
      color: #E8EEF6;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .co-wrap {
      max-width: 880px;
      margin: 0 auto;
      padding: 32px 20px 80px;
    }
    .co-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 0 28px;
      border-bottom: 1px solid rgba(232,238,246,0.08);
    }
    .co-brand { font-weight: 700; letter-spacing: 0.04em; font-size: 14px; }
    .co-brand span { color: #4FD1C5; }
    .co-toplink { color: #94A3B8; font-size: 12px; text-decoration: none; }
    .co-toplink:hover { color: #4FD1C5; }

    .co-hero {
      padding: 56px 0 32px;
    }
    .co-hero-eyebrow {
      text-transform: uppercase; letter-spacing: 0.18em;
      font-size: 11px; color: #4FD1C5; margin-bottom: 18px;
    }
    .co-hero h1 {
      font-size: 44px; line-height: 1.1; font-weight: 800;
      margin: 0 0 20px; color: #FFFFFF;
    }
    .co-hero h1 em { font-style: normal; color: #4FD1C5; }
    .co-hero-sub {
      font-size: 18px; line-height: 1.55; color: #B8C5D6;
      max-width: 680px;
    }
    .co-trustline {
      margin-top: 24px; font-size: 15px; color: #4FD1C5;
      font-weight: 600; letter-spacing: 0.01em;
    }

    .co-cta-row {
      display: flex; gap: 16px; flex-wrap: wrap;
      margin: 36px 0 0;
    }
    .co-btn {
      display: inline-block; padding: 14px 24px; border-radius: 8px;
      font-size: 15px; font-weight: 600; text-decoration: none;
      cursor: pointer; border: 0; transition: transform 0.15s, opacity 0.15s;
    }
    .co-btn:hover { transform: translateY(-1px); }
    .co-btn-primary {
      background: linear-gradient(135deg, #4FD1C5 0%, #38B2AC 100%);
      color: #0A1A2F;
    }
    .co-btn-secondary {
      background: rgba(232,238,246,0.06); color: #E8EEF6;
      border: 1px solid rgba(232,238,246,0.18);
    }

    .co-section {
      padding: 56px 0; border-top: 1px solid rgba(232,238,246,0.08);
    }
    .co-section h2 {
      font-size: 24px; font-weight: 700; margin: 0 0 28px;
      letter-spacing: -0.01em;
    }

    .co-steps {
      display: grid; grid-template-columns: repeat(3, 1fr);
      gap: 24px; counter-reset: step;
    }
    @media (max-width: 720px) { .co-steps { grid-template-columns: 1fr; } }
    .co-step {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(232,238,246,0.08);
      border-radius: 12px; padding: 24px;
    }
    .co-step-num {
      display: inline-block; width: 32px; height: 32px; line-height: 32px;
      text-align: center; border-radius: 50%;
      background: rgba(79,209,197,0.16); color: #4FD1C5;
      font-weight: 700; margin-bottom: 14px;
    }
    .co-step h3 { font-size: 16px; margin: 0 0 8px; color: #FFFFFF; }
    .co-step p  { font-size: 14px; margin: 0; color: #B8C5D6; line-height: 1.5; }

    .co-form {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(232,238,246,0.10);
      border-radius: 14px; padding: 32px;
    }
    .co-form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 14px; }
    @media (max-width: 720px) { .co-form-row { grid-template-columns: 1fr; } }
    .co-form-row.single { grid-template-columns: 1fr; }
    .co-field label {
      display: block; font-size: 12px; font-weight: 600;
      letter-spacing: 0.04em; text-transform: uppercase;
      color: #94A3B8; margin-bottom: 6px;
    }
    .co-field label .opt { color: #64748B; font-weight: 400; text-transform: none; letter-spacing: 0; }
    .co-field input, .co-field select {
      width: 100%; padding: 11px 12px; border-radius: 8px;
      background: rgba(10,26,47,0.6); color: #E8EEF6;
      border: 1px solid rgba(232,238,246,0.18);
      font-size: 15px; box-sizing: border-box;
    }
    .co-field input:focus, .co-field select:focus {
      outline: 0; border-color: #4FD1C5;
    }
    .co-consent {
      display: flex; align-items: flex-start; gap: 10px;
      font-size: 13px; color: #B8C5D6; margin: 16px 0 22px;
    }
    .co-consent input[type=checkbox] { margin-top: 3px; }
    .co-submit {
      background: linear-gradient(135deg, #4FD1C5 0%, #38B2AC 100%);
      color: #0A1A2F; border: 0; border-radius: 8px;
      padding: 14px 28px; font-size: 15px; font-weight: 700;
      cursor: pointer; letter-spacing: 0.01em;
    }
    .co-submit:disabled { opacity: 0.5; cursor: not-allowed; }
    .co-submit:hover:not(:disabled) { transform: translateY(-1px); }

    .co-status {
      margin-top: 18px; padding: 14px 16px; border-radius: 8px;
      font-size: 14px; display: none;
    }
    .co-status.ok    { background: rgba(79,209,197,0.10); color: #4FD1C5; display: block; }
    .co-status.err   { background: rgba(252,129,129,0.10); color: #FC8181; display: block; }

    .co-fineprint {
      font-size: 12px; color: #64748B; margin-top: 20px; line-height: 1.5;
    }

    .co-faq {
      display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
    }
    @media (max-width: 720px) { .co-faq { grid-template-columns: 1fr; } }
    .co-faq-item h3 { font-size: 14px; margin: 0 0 6px; color: #4FD1C5; }
    .co-faq-item p  { font-size: 14px; margin: 0; color: #B8C5D6; line-height: 1.55; }

    .co-footer {
      text-align: center; padding: 40px 0 20px;
      font-size: 12px; color: #64748B;
    }
    """


def contractors_page() -> str:
    """Render the /contractors page. Returns a complete HTML string."""
    return f"""<!DOCTYPE html>
<html lang="en">
{empire_head(title="Empire AI · For Contractors", extra=_page_css())}
<body class="co-body">
  <div class="co-wrap">
    <header class="co-header">
      <div class="co-brand">EMPIRE <span>AI</span></div>
      <a class="co-toplink" href="/">← empire-ai.co.uk</a>
    </header>

    <section class="co-hero">
      <div class="co-hero-eyebrow">For licensed contractors</div>
      <h1>Get pre-qualified, storm-affected property owners delivered to your queue.</h1>
      <p class="co-hero-sub">
        We detect the storm. We text the property owner. They reply YES. You get the dispatch.
        No marketing budget. No cold calling. No exclusivity.
      </p>
      <p class="co-trustline">
        3% fee on settled insurance claims · first 2 closed deals 100% complimentary · no call needed
      </p>
      <div class="co-cta-row">
        <a class="co-btn co-btn-primary" href="#onboard">Self-onboard (90 seconds)</a>
        <a class="co-btn co-btn-secondary" href="/demo">Watch the 2-min demo</a>
      </div>
    </section>

    <section class="co-section">
      <h2>How it works</h2>
      <div class="co-steps">
        <div class="co-step">
          <div class="co-step-num">1</div>
          <h3>We detect the storm</h3>
          <p>Our radar catches NWS-severe weather events in real time and pinpoints the affected commercial properties.</p>
        </div>
        <div class="co-step">
          <div class="co-step-num">2</div>
          <h3>We text the property owner</h3>
          <p>3-touch SMS sequence with a free damage assessment offer. They reply YES — you do not need a call center.</p>
        </div>
        <div class="co-step">
          <div class="co-step-num">3</div>
          <h3>You get the dispatch</h3>
          <p>Name, address, asset value, severity. You show up, you inspect, you close. We charge a 3% fee only on the settled claim.</p>
        </div>
      </div>
    </section>

    <section class="co-section" id="onboard">
      <h2>Self-onboard</h2>
      <p style="color:#B8C5D6; margin: 0 0 22px; font-size: 15px;">
        Takes about 90 seconds. No call required. We'll text you within 5 minutes to confirm.
      </p>
      <form class="co-form" id="co-form" autocomplete="on">
        <div class="co-form-row">
          <div class="co-field">
            <label for="co-name">Name</label>
            <input type="text" id="co-name" name="name" required maxlength="120" autocomplete="name" />
          </div>
          <div class="co-field">
            <label for="co-company">Company</label>
            <input type="text" id="co-company" name="company" required maxlength="200" autocomplete="organization" />
          </div>
        </div>
        <div class="co-form-row">
          <div class="co-field">
            <label for="co-phone">Phone <span style="color:#94A3B8">(E.164, e.g. +18175551234)</span></label>
            <input type="tel" id="co-phone" name="phone" required maxlength="20" autocomplete="tel" placeholder="+18175551234" />
          </div>
          <div class="co-field">
            <label for="co-email">Email</label>
            <input type="email" id="co-email" name="email" required maxlength="200" autocomplete="email" />
          </div>
        </div>
        <div class="co-form-row">
          <div class="co-field">
            <label for="co-license">License # <span class="opt">(optional but encouraged)</span></label>
            <input type="text" id="co-license" name="license_no" maxlength="80" />
          </div>
          <div class="co-field">
            <label for="co-area">Service area</label>
            <input type="text" id="co-area" name="service_area" required maxlength="120" placeholder="DFW, Houston, San Antonio, ..." />
          </div>
        </div>
        <div class="co-form-row single">
          <div class="co-field">
            <label for="co-trade">Trade</label>
            <select id="co-trade" name="trade" required>
              <option value="">Select your primary trade</option>
              {''.join(f'<option value="{t}">{t.replace("_", " ").title()}</option>' for t in TRADE_ENUM)}
            </select>
          </div>
        </div>
        <label class="co-consent">
          <input type="checkbox" id="co-consent" required />
          <span>I agree to receive SMS and email from Empire AI about storm-affected leads in my service area. Message and data rates may apply. Reply STOP any time to opt out.</span>
        </label>
        <button class="co-submit" type="submit" id="co-submit">Self-onboard</button>
        <div class="co-status" id="co-status"></div>
        <p class="co-fineprint">
          By submitting you confirm you are a licensed contractor (or contracting business) operating in the service area you listed. Empire AI does not share your details with third parties. We charge a 3% referral fee only on insurance claims that actually settle.
        </p>
      </form>
    </section>

    <section class="co-section">
      <h2>Common questions</h2>
      <div class="co-faq">
        <div class="co-faq-item">
          <h3>When do I get charged?</h3>
          <p>Only when an insurance claim settles. Your first 2 closed deals are 100% complimentary — no fee, ever. After that, 3% of the gross settlement, paid within 30 days of fund.</p>
        </div>
        <div class="co-faq-item">
          <h3>Am I locked in?</h3>
          <p>No. No contract, no exclusivity, no monthly minimum. Self-onboarding is a one-time form. You can opt out any time with a single reply STOP.</p>
        </div>
        <div class="co-faq-item">
          <h3>What if the lead is bad?</h3>
          <p>You don't pay for it. The 3% fee only triggers on a settled insurance claim. If the property owner doesn't file, or the claim is denied, you owe nothing.</p>
        </div>
        <div class="co-faq-item">
          <h3>How do you find leads?</h3>
          <p>National Weather Service severe-weather alerts + property records + a TCPA-compliant SMS qualification flow. We don't scrape social, we don't buy lists.</p>
        </div>
      </div>
    </section>

    <footer class="co-footer">
      empire-ai.co.uk · © 2026 · reply STOP to opt out
    </footer>
  </div>

  <script>
    (function() {{
      var form = document.getElementById('co-form');
      var status = document.getElementById('co-status');
      var submitBtn = document.getElementById('co-submit');
      if (!form) return;

      form.addEventListener('submit', async function(e) {{
        e.preventDefault();
        status.className = 'co-status';
        status.textContent = '';
        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';

        var fd = new FormData(form);
        var payload = {{
          name:         (fd.get('name')         || '').toString().trim(),
          company:      (fd.get('company')      || '').toString().trim(),
          phone:        (fd.get('phone')        || '').toString().trim(),
          email:        (fd.get('email')        || '').toString().trim(),
          license_no:   (fd.get('license_no')   || '').toString().trim(),
          service_area: (fd.get('service_area') || '').toString().trim(),
          trade:        (fd.get('trade')        || '').toString().trim(),
        }};

        try {{
          var r = await fetch('/api/contractors/onboard', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload),
          }});
          var data = await r.json().catch(function() {{ return {{ ok: false, error: 'invalid_response' }}; }});
          if (r.ok && data.ok) {{
            status.className = 'co-status ok';
            status.textContent = (data.next_step || "Thanks — we'll be in touch within 5 minutes.");
            form.reset();
          }} else {{
            var msg = (data && data.error) ? data.error.replace(/_/g, ' ') : 'something went wrong';
            status.className = 'co-status err';
            status.textContent = 'Could not submit: ' + msg + '. Please try again or email contractors@empire-ai.co.uk.';
          }}
        }} catch (err) {{
          status.className = 'co-status err';
          status.textContent = 'Network error. Please try again.';
        }} finally {{
          submitBtn.disabled = false;
          submitBtn.textContent = 'Self-onboard';
        }}
      }});
    }})();
  </script>

  <script src="/static/contractors/chat.js" defer></script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Onboard endpoint
# ─────────────────────────────────────────────────────────────────────────────

def _hash_ip(ip: str) -> str:
    if not ip:
        return ""
    return hashlib.sha256((ip + "empire-salt-do-not-rotate").encode("utf-8")).hexdigest()[:32]


def _is_opted_out(db, phone: str) -> bool:
    try:
        r = db.table("sms_opt_outs").select("phone").eq("phone", phone).limit(1).execute()
        return bool(r.data)
    except Exception:
        return False


def _is_on_dnc(db, phone: str) -> bool:
    try:
        r = db.table("outbound_dnc").select("phone").eq("phone", phone).limit(1).execute()
        return bool(r.data)
    except Exception:
        return False


async def contractors_onboard(request: Request) -> JSONResponse:
    """POST /api/contractors/onboard

    Public form. No auth. Validates payload, inserts a row into contractors
    with status='prospect' and tcpa_consent=True. Does NOT auto-enroll in
    contractor_recruit sequence (the recruiter agent picks it up).
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "invalid_payload"}, status_code=400)

    name         = (body.get("name") or "").strip()
    company      = (body.get("company") or "").strip()
    phone        = (body.get("phone") or "").strip()
    email        = (body.get("email") or "").strip()
    license_no   = (body.get("license_no") or "").strip()
    service_area = (body.get("service_area") or "").strip()
    trade        = (body.get("trade") or "").strip()

    # Validation
    if not name:
        return JSONResponse({"ok": False, "error": "missing_name", "field": "name"}, status_code=400)
    if not company:
        return JSONResponse({"ok": False, "error": "missing_company", "field": "company"}, status_code=400)
    if not phone:
        return JSONResponse({"ok": False, "error": "missing_phone", "field": "phone"}, status_code=400)
    if not _E164_RE.match(phone):
        return JSONResponse({"ok": False, "error": "invalid_phone", "field": "phone"}, status_code=400)
    if not email:
        return JSONResponse({"ok": False, "error": "missing_email", "field": "email"}, status_code=400)
    if not _EMAIL_RE.match(email):
        return JSONResponse({"ok": False, "error": "invalid_email", "field": "email"}, status_code=400)
    if not service_area:
        return JSONResponse({"ok": False, "error": "missing_service_area", "field": "service_area"}, status_code=400)
    if not trade:
        return JSONResponse({"ok": False, "error": "missing_trade", "field": "trade"}, status_code=400)
    if trade not in TRADE_ENUM:
        return JSONResponse({"ok": False, "error": "invalid_trade", "field": "trade"}, status_code=400)

    # Get DB handle (the hub normally exposes get_db() in scope; we
    # re-import lazily so this module is import-clean for tests).
    # If register_contractor_routes was called with get_db=...,    # use that override (cleanly handles the hub.py's real client).
    db = None
    if _get_db_override is not None:
        db = _get_db_override()
    if db is None:
        try:
            from hub import get_db  # type: ignore
            db = get_db()
        except Exception:
            try:
                from supabase import create_client
                db = create_client(os.environ.get("SUPABASE_URL",""), os.environ.get("SUPABASE_SERVICE_KEY",""))
            except Exception as e:
                log.error(f"[contractors_onboard] db unavailable: {e}")
                return JSONResponse({"ok": False, "error": "db_unavailable"}, status_code=500)

    # Compliance check
    if _is_opted_out(db, phone):
        return JSONResponse({"ok": False, "error": "phone_opted_out", "field": "phone"}, status_code=400)
    if _is_on_dnc(db, phone):
        return JSONResponse({"ok": False, "error": "phone_on_dnc", "field": "phone"}, status_code=400)

    # Idempotency: if this phone already has a row, return that one
    try:
        existing = db.table("contractors").select("id,active").eq("phone", phone).limit(1).execute()
        if existing.data:
            row = existing.data[0]
            return JSONResponse({
                "ok": True,
                "contractor_id": row["id"],
                "existing": True,
                "next_step": "You're already on the list. You'll get a welcome SMS within 5 minutes. Reply STOP any time to opt out.",
            }, status_code=200)
    except Exception as e:
        log.warning(f"[contractors_onboard] existing-check failed: {e}")

    # Insert
    client_ip = request.client.host if request.client else ""
    meta = {
        "form_source": "self_onboard_widget",
        "first_seen_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "ip_hash": _hash_ip(client_ip),
        "tcpa_consent": True,           # no dedicated column; record in meta
        "contact_name": name,            # the user's individual name, separate from company
        "tcpa_consent_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    if license_no:
        meta["license_no"] = license_no

    # Map UI trade (single) -> specialties (list of strings) to match
    # the real contractors.specialties column type.
    specialties = [trade]

    payload = {
        "name":         company,                # the existing column is "name", holds the company name
        "phone":        phone,
        "email":        email,
        "metro":        service_area,
        "active":       True,
        "specialties":  specialties,
        "meta":         meta,
    }

    try:
        ins = db.table("contractors").insert(payload).execute()
    except Exception as e:
        log.error(f"[contractors_onboard] insert failed: {e}")
        return JSONResponse({"ok": False, "error": "insert_failed"}, status_code=500)

    if not ins.data:
        return JSONResponse({"ok": False, "error": "insert_returned_no_row"}, status_code=500)

    contractor_id = ins.data[0].get("id")
    log.info(f"[contractors_onboard] new prospect: {contractor_id} phone={phone} trade={trade}")
    return JSONResponse({
        "ok": True,
        "contractor_id": contractor_id,
        "next_step": "Thanks! You'll get a welcome SMS within 5 minutes. Reply STOP any time to opt out.",
    }, status_code=200)


# ─────────────────────────────────────────────────────────────────────────────
# Route registration helper
# ─────────────────────────────────────────────────────────────────────────────

def register_contractor_routes(
    app,
    require_auth=None,
    get_db=None,
    sign_token=None,
    verify_token=None,
    send_email=None,
    public_base_url=None,
    broadcaster=None,
):
    """Mount /contractors and /api/contractors/onboard on the FastAPI app.

    The /api/contractors/chat endpoint is owned by buffy (chat widget
    implementation) and is NOT registered here. This module is
    deliberately chat-free so the page and the form work standalone.

    Compatibility signature: the existing hub.py call at line 449 passes
    require_auth, get_db, sign_token, verify_token, send_email,
    public_base_url, broadcaster. We accept them all but only USE
    `app` and `get_db`. The other kwargs are reserved for future
    expansion (e.g. sign_token for a contractor self-link).
    """
    from fastapi.responses import HTMLResponse

    if get_db is not None:
        # Stash on the module so contractors_onboard can use it
        global _get_db_override
        _get_db_override = get_db

    app.add_api_route(
        "/contractors",
        lambda: HTMLResponse(contractors_page()),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/api/contractors/onboard",
        contractors_onboard,
        methods=["POST"],
    )
    log.info("[contractors] routes registered: GET /contractors, POST /api/contractors/onboard")


_get_db_override = None
