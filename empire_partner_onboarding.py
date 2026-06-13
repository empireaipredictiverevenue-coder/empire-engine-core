"""
EMPIRE V49 · PARTNER ONBOARDING PORTAL
=======================================
Public-facing intake form + owner review workflow. Every submission:

  1. Inserts into `buyers` with status='pending_review'
  2. Writes a compliance audit log into `compliance_audit_logs`
  3. Pushes a real-time ntfy notification to the Owner

No existing logic is touched — this is a self-contained module.

ENDPOINTS
─────────
  GET  /partner/signup              → public HTML form
  POST /api/v1/partner/signup       → submit partner application (public)
  GET  /api/v1/partner/pending      → list pending partners (auth required)
  POST /api/v1/partner/{id}/approve → set status='active' (auth required)
  POST /api/v1/partner/{id}/reject  → set status='rejected' (auth required)
  GET  /api/v1/partner/log          → compliance audit trail (auth required)
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from supabase import create_client

log = logging.getLogger("empire.partner_onboarding")

# ─────────────────────────────────────────────────────────────────────────────
# SUPABASE CLIENT (module-level, same pattern as empire_switchboard.py)
# ─────────────────────────────────────────────────────────────────────────────
_sb = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", ""),
)


# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE AUDIT HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _log_compliance(
    action: str,
    entity_type: str,
    entity_id: str = "",
    operator_id: str = "",
    operator_name: str = "",
    details: Optional[dict] = None,
    ip: str = "",
) -> None:
    """Write an entry to compliance_audit_logs. Best-effort, never raises."""
    try:
        _sb.table("compliance_audit_logs").insert({
            "action":        action[:80],
            "entity_type":   entity_type[:40],
            "entity_id":     entity_id[:80] if entity_id else None,
            "operator_id":   operator_id[:80] if operator_id else None,
            "operator_name": operator_name[:160] if operator_name else None,
            "details":       details or {},
            "ip":            ip[:60] if ip else None,
        }).execute()
    except Exception as e:
        log.error(f"[compliance] audit log write failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# NTFY NOTIFICATION HELPER
# ─────────────────────────────────────────────────────────────────────────────
async def _notify_owner(title: str, message: str, tags: str = "bell") -> None:
    """Push a notification via ntfy.sh to the Owner's configured topic.
    Async — non-blocking for the public-facing signup endpoint."""
    topic = os.getenv("NTFY_TOPIC", "")
    token = os.getenv("NTFY_TOKEN", "")
    if not topic:
        log.debug("[notify] NTFY_TOPIC not configured — skipping notification")
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
        log.info(f"[notify] ntfy push sent: {title}")
    except Exception as e:
        log.error(f"[notify] ntfy push failed: {e}")


def _reviewer_id(op: dict) -> Optional[str]:
    """Extract a valid UUID reviewer ID from the operator dict.
    Legacy hub token returns "legacy-hub-token" which is not a valid UUID
    — we map that to None so the uuid column doesn't reject it."""
    rid = op.get("id") or None
    return rid if rid and len(rid) == 36 else None


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC HTML FORM
# ─────────────────────────────────────────────────────────────────────────────
_PARTNER_FORM_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0A1A2F; color: #F8FAFD;
  font-family: 'Inter', -apple-system, system-ui, sans-serif;
  letter-spacing: -0.02em;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  background:
    radial-gradient(ellipse at top right, rgba(68,229,184,0.06), transparent 50%),
    radial-gradient(ellipse at bottom left, rgba(90,200,250,0.05), transparent 50%),
    #0A1A2F;
}
.card {
  max-width: 540px; width: 100%;
  background: #15263F;
  border: 1px solid rgba(122,140,163,0.18);
  padding: 44px 40px;
}
.brand-line {
  display: flex; align-items: baseline; justify-content: center; gap: 8px;
  margin-bottom: 6px;
}
.brand-e { font-weight: 700; font-size: 20px; letter-spacing: 0.22em; }
.brand-ai { font-weight: 700; font-size: 20px; letter-spacing: 0.22em; color: #5AC8FA; }
.brand-sub {
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; color: #4A5A72;
  letter-spacing: 0.32em; text-transform: uppercase;
  margin-bottom: 32px;
}
h1 {
  font-weight: 200; font-size: 28px;
  letter-spacing: -0.04em; margin-bottom: 8px;
  text-align: center;
}
h1 em { font-style: italic; color: #44E5B8; font-weight: 500; }
.lead {
  text-align: center;
  color: #7A8CA3; font-size: 13px;
  line-height: 1.7; margin-bottom: 32px;
}
.field { margin-bottom: 18px; }
.field label {
  display: block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; color: #7A8CA3;
  letter-spacing: 0.14em; text-transform: uppercase;
  margin-bottom: 5px;
}
.field input, .field select, .field textarea {
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
.field input:focus, .field select:focus, .field textarea:focus {
  border-color: #44E5B8;
}
.field textarea { min-height: 80px; resize: vertical; }
.field select { cursor: pointer; }
.field select option { background: #15263F; color: #F8FAFD; }
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
.foot {
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; color: #4A5A72;
  letter-spacing: 0.18em; margin-top: 28px;
}
"""

_PARTNER_FORM_HTML = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Partner Onboarding</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{_PARTNER_FORM_CSS}</style>
</head><body>
<div class="card">
  <div class="brand-line"><span class="brand-e">EMPIRE</span><span class="brand-ai">AI</span></div>
  <div class="brand-sub">Partner Onboarding · Revenue Network</div>
  <h1>Become a <em>Partner</em></h1>
  <p class="lead">Join the Empire AI revenue network. Fill out the form below and we'll review your application within 24 hours.</p>

  <form id="partnerForm" onsubmit="return submitForm(event)">
    <div class="field">
      <label>Business name</label>
      <input type="text" id="buyer_name" placeholder="Apex Property Group, LLC" required>
    </div>
    <div class="field">
      <label>Contact name</label>
      <input type="text" id="contact_name" placeholder="John Smith" required>
    </div>
    <div class="row2">
      <div class="field">
        <label>Email</label>
        <input type="email" id="email" placeholder="john@apexproperty.com" required>
      </div>
      <div class="field">
        <label>Phone</label>
        <input type="tel" id="destination_phone" placeholder="+12145551234" required>
      </div>
    </div>
    <div class="row2">
      <div class="field">
        <label>Niche / Vertical</label>
        <select id="niche">
          <option value="roofing">Roofing</option>
          <option value="Mass Tort Legal">Mass Tort Legal</option>
          <option value="restoration">Restoration</option>
          <option value="hvac">HVAC</option>
          <option value="solar">Solar</option>
          <option value="insurance">Insurance</option>
          <option value="legal">Legal Services</option>
          <option value="other">Other</option>
        </select>
      </div>
      <div class="field">
        <label>State coverage</label>
        <select id="state_coverage">
          <option value="TX">Texas (TX)</option>
          <option value="FL">Florida (FL)</option>
          <option value="CA">California (CA)</option>
          <option value="NY">New York (NY)</option>
          <option value="IL">Illinois (IL)</option>
          <option value="CO">Colorado (CO)</option>
          <option value="AZ">Arizona (AZ)</option>
          <option value="GA">Georgia (GA)</option>
          <option value="NC">North Carolina (NC)</option>
          <option value="TN">Tennessee (TN)</option>
          <option value="OK">Oklahoma (OK)</option>
          <option value="LA">Louisiana (LA)</option>
          <option value="multi">Multi-state</option>
        </select>
      </div>
    </div>
    <div class="field">
      <label>Notes (optional)</label>
      <textarea id="notes" placeholder="Tell us about your operation, capacity, or anything else we should know."></textarea>
    </div>
    <button type="submit" class="btn-submit" id="submitBtn">Submit application →</button>
  </form>
  <div id="flash" class="flash"></div>
  <div class="foot">Empire AI V49 · Predictive Revenue Network</div>
</div>
<script>
async function submitForm(event) {{
  event.preventDefault();
  const flash = document.getElementById('flash');
  const btn = document.getElementById('submitBtn');
  flash.className = 'flash';
  btn.disabled = true; btn.textContent = 'Submitting...';
  try {{
    const r = await fetch('/api/v1/partner/signup', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        buyer_name: document.getElementById('buyer_name').value.trim(),
        contact_name: document.getElementById('contact_name').value.trim(),
        email: document.getElementById('email').value.trim(),
        destination_phone: document.getElementById('destination_phone').value.trim(),
        niche: document.getElementById('niche').value,
        state_coverage: document.getElementById('state_coverage').value,
        notes: document.getElementById('notes').value.trim(),
      }}),
    }});
    const d = await r.json();
    if (r.ok && d.ok) {{
      flash.className = 'flash show success';
      flash.textContent = '✓ Application received! We will review it and get back to you within 24 hours.';
      document.getElementById('partnerForm').reset();
    }} else {{
      flash.className = 'flash show error';
      flash.textContent = '✗ ' + (d.error || 'Submission failed. Please try again.');
    }}
  }} catch (e) {{
    flash.className = 'flash show error';
    flash.textContent = '✗ Network error. Please check your connection and try again.';
  }} finally {{
    btn.disabled = false; btn.textContent = 'Submit application →';
  }}
}}
</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
def register_partner_routes(app: FastAPI, require_auth: Optional[Callable] = None):
    """Register partner onboarding routes. Pass `require_auth` from hub.py."""

    # ── PUBLIC: SIGNUP FORM ────────────────────────────────────────────
    @app.get("/partner/signup", response_class=HTMLResponse)
    async def partner_signup_form():
        return HTMLResponse(_PARTNER_FORM_HTML)

    # ── PUBLIC: SUBMIT APPLICATION ─────────────────────────────────────
    @app.post("/api/v1/partner/signup")
    async def partner_signup(request: Request):
        """Public endpoint. Accepts partner application, inserts into buyers
        with status='pending_review', logs compliance audit, notifies Owner."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON payload")

        buyer_name = (body.get("buyer_name") or "").strip()
        contact_name = (body.get("contact_name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        phone = (body.get("destination_phone") or "").strip()
        niche = (body.get("niche") or "roofing").strip()
        state_raw = (body.get("state_coverage") or "").strip()
        notes = (body.get("notes") or "").strip()

        # ── Validation ────────────────────────────────────────────────
        if not buyer_name:
            raise HTTPException(400, "Business name is required")
        if not contact_name:
            raise HTTPException(400, "Contact name is required")
        if not email or "@" not in email:
            raise HTTPException(400, "A valid email is required")
        if not phone:
            raise HTTPException(400, "Phone number is required")

        ip = request.client.host if request.client else ""

        # ── Insert into buyers with status='pending_review' ────────────
        buyer_row = {
            "buyer_name":       buyer_name,
            "contact_name":     contact_name,
            "email":            email,
            "destination_phone": phone,
            "niche":            niche,
            "state_coverage":   [state_raw],
            "status":           "pending_review",
            "is_active":        False,  # not active until approved
            "notes":            notes,
            "timezone":         "America/Chicago",
            "base_payout":      0,
            "fee_rate":         0.03,
            "per_call_fee":     0,
            "monthly_retainer": 0,
            "daily_cap":        10,
            "hours_open":       8,
            "hours_close":      20,
        }

        try:
            # Try insert with all columns (including new fee model fields)
            res = _sb.table("buyers").insert(buyer_row).execute()
            if not res.data:
                raise HTTPException(500, "Failed to create partner record")
            new_buyer = res.data[0]
            buyer_id = str(new_buyer["id"])
        except Exception as e:
            # If columns don't exist yet (migration not run), retry without new fee fields
            err_msg = str(e).lower()
            if "per_call_fee" in err_msg or "monthly_retainer" in err_msg:
                log.warning("[partner] new fee columns not in DB yet — retrying without them")
                safe_row = {k: v for k, v in buyer_row.items()
                            if k not in ("per_call_fee", "monthly_retainer")}
                try:
                    res = _sb.table("buyers").insert(safe_row).execute()
                    if not res.data:
                        raise HTTPException(500, "Failed to create partner record")
                    new_buyer = res.data[0]
                    buyer_id = str(new_buyer["id"])
                except Exception as e2:
                    log.error(f"[partner] insert failed (fallback): {e2}")
                    raise HTTPException(500, f"Database error: {e2}")
            else:
                log.error(f"[partner] insert failed: {e}")
                raise HTTPException(500, f"Database error: {e}")

        # ── COMPLIANCE HOOK: audit log entry ──────────────────────────
        _log_compliance(
            action="partner_signup",
            entity_type="buyer",
            entity_id=buyer_id,
            details={
                "buyer_name":   buyer_name,
                "contact_name": contact_name,
                "email":        email,
                "niche":        niche,
                "state":        state_raw,
                "status":       "pending_review",
            },
            ip=ip,
        )

        # ── NOTIFY THE OWNER ──────────────────────────────────────────
        await _notify_owner(
            title="New Partner Application",
            message=(
                f"{buyer_name} ({contact_name}, {email}) applied for "
                f"{niche} coverage in {state_raw}. "
                f"Review at: https://empire-ai.co.uk/command#/partners"
            ),
            tags="new_partner,bell",
        )

        log.info(
            f"[partner] signup: {buyer_name} <{email}> → "
            f"buyer_id={buyer_id} status=pending_review"
        )

        return {
            "ok":        True,
            "partner_id": buyer_id,
            "status":    "pending_review",
        }

    # ── AUTH-REQUIRED: LIST PENDING PARTNERS ────────────────────────────
    if require_auth:
        @app.get("/api/v1/partner/pending")
        async def partner_pending(
            op: dict = Depends(require_auth),
            limit: int = Query(50, ge=1, le=200),
        ):
            """List all partners pending review."""
            try:
                res = (
                    _sb.table("buyers")
                    .select("*")
                    .eq("status", "pending_review")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                return {"partners": res.data or []}
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/api/v1/partner/all")
        async def partner_all(
            op: dict = Depends(require_auth),
            limit: int = Query(100, ge=1, le=500),
        ):
            """List all partners (all statuses)."""
            try:
                res = (
                    _sb.table("buyers")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                return {"partners": res.data or []}
            except Exception as e:
                raise HTTPException(500, str(e))

        # ── AUTH-REQUIRED: APPROVE PARTNER ─────────────────────────────
        @app.post("/api/v1/partner/{partner_id}/approve")
        async def partner_approve(
            partner_id: str,
            op: dict = Depends(require_auth),
        ):
            """Approve a pending partner → sets status='active', is_active=True."""
            try:
                # Fetch the current record
                cur = (
                    _sb.table("buyers")
                    .select("id, buyer_name, status")
                    .eq("id", partner_id)
                    .limit(1)
                    .execute()
                )
                if not cur.data:
                    raise HTTPException(404, "Partner not found")
                existing = cur.data[0]
                if existing.get("status") != "pending_review":
                    raise HTTPException(
                        400,
                        f"Partner status is '{existing.get('status')}', "
                        f"expected 'pending_review'",
                    )

                now_iso = datetime.now(timezone.utc).isoformat()

                # Update to active
                # reviewed_by must be a valid UUID or null — legacy hub token
                # returns "legacy-hub-token" which will not fit in a uuid column
                reviewer_id = _reviewer_id(op)
                _sb.table("buyers").update({
                    "status":       "active",
                    "is_active":    True,
                    "reviewed_at":  now_iso,
                    "reviewed_by":  reviewer_id,
                }).eq("id", partner_id).execute()

                # ── COMPLIANCE HOOK ──────────────────────────────────
                _log_compliance(
                    action="partner_approved",
                    entity_type="buyer",
                    entity_id=partner_id,
                    operator_id=op.get("id"),
                    operator_name=op.get("name", ""),
                    details={
                        "buyer_name": existing.get("buyer_name"),
                        "reviewed_by": op.get("email"),
                    },
                    ip="",
                )

                log.info(
                    f"[partner] approved: {existing.get('buyer_name')} "
                    f"by {op.get('name')} ({op.get('email')})"
                )

                return {
                    "ok": True,
                    "partner_id": partner_id,
                    "status": "active",
                }

            except HTTPException:
                raise
            except Exception as e:
                log.error(f"[partner] approve failed: {e}")
                raise HTTPException(500, str(e))

        # ── AUTH-REQUIRED: REJECT PARTNER ──────────────────────────────
        @app.post("/api/v1/partner/{partner_id}/reject")
        async def partner_reject(
            partner_id: str,
            request: Request,
            op: dict = Depends(require_auth),
        ):
            """Reject a pending partner → sets status='rejected', is_active=False."""
            try:
                body = await request.json()
            except Exception:
                body = {}
            rejection_reason = (body.get("reason") or "").strip()

            try:
                cur = (
                    _sb.table("buyers")
                    .select("id, buyer_name, status")
                    .eq("id", partner_id)
                    .limit(1)
                    .execute()
                )
                if not cur.data:
                    raise HTTPException(404, "Partner not found")
                existing = cur.data[0]
                if existing.get("status") != "pending_review":
                    raise HTTPException(
                        400,
                        f"Partner status is '{existing.get('status')}', "
                        f"expected 'pending_review'",
                    )

                now_iso = datetime.now(timezone.utc).isoformat()

                # Update to rejected
                reviewer_id = _reviewer_id(op)
                _sb.table("buyers").update({
                    "status":       "rejected",
                    "is_active":    False,
                    "reviewed_at":  now_iso,
                    "reviewed_by":  reviewer_id,
                    "notes":        rejection_reason or existing.get("notes", ""),
                }).eq("id", partner_id).execute()

                # ── COMPLIANCE HOOK ──────────────────────────────────
                _log_compliance(
                    action="partner_rejected",
                    entity_type="buyer",
                    entity_id=partner_id,
                    operator_id=op.get("id"),
                    operator_name=op.get("name", ""),
                    details={
                        "buyer_name": existing.get("buyer_name"),
                        "reason": rejection_reason or "No reason provided",
                        "reviewed_by": op.get("email"),
                    },
                    ip="",
                )

                log.info(
                    f"[partner] rejected: {existing.get('buyer_name')} "
                    f"by {op.get('name')} — {rejection_reason or 'no reason'}"
                )

                return {
                    "ok": True,
                    "partner_id": partner_id,
                    "status": "rejected",
                }

            except HTTPException:
                raise
            except Exception as e:
                log.error(f"[partner] reject failed: {e}")
                raise HTTPException(500, str(e))

        # ── AUTH-REQUIRED: COMPLIANCE AUDIT LOG ─────────────────────────
        @app.get("/api/v1/partner/log")
        async def partner_compliance_log(
            op: dict = Depends(require_auth),
            limit: int = Query(50, ge=1, le=500),
            entity_id: str = Query(""),
        ):
            """View the compliance audit trail for partner actions."""
            try:
                q = (
                    _sb.table("compliance_audit_logs")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                )
                if entity_id:
                    q = q.eq("entity_id", entity_id)
                res = q.execute()
                return {"entries": res.data or []}
            except Exception as e:
                raise HTTPException(500, str(e))

    log.info(
        "[partner] Routes registered · "
        "/partner/signup · /api/v1/partner/{signup,pending,all,approve,reject,log}"
    )
