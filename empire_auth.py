"""
EMPIRE V49 · MULTI-OPERATOR AUTH
==================================
Replaces the shared HUB_TOKEN with per-operator accounts. Every action
gets attributed to a real person. Audit trail per operator. Role-based
access. Magic-link login (no passwords to lose).

THE PROBLEM WE'RE SOLVING
─────────────────────────
Today: one shared HUB_TOKEN. If you bring on a second operator, they
have the same God-mode token as you. If a token leaks, you can't tell
WHO leaked it. If someone makes a bad call, you can't tell WHO did it.

After this module:
  - Each operator has their own account
  - Each request is attributed to that operator
  - Roles: owner (you) / operator (full ops, no payout sign-off) / viewer
  - Audit log captures actor + action + target
  - Sessions expire after 12h
  - Magic-link login via email (no passwords)
  - HUB_TOKEN still works for cron jobs / pipeline / backwards compat


ROLE MATRIX
───────────
                          owner   operator   viewer
  view dashboards           ✓        ✓         ✓
  approve contractors       ✓        ✓         ·
  trigger dispatch          ✓        ✓         ·
  record outcomes           ✓        ✓         ·
  approve payouts           ✓        ·         ·     ← owner-only
  cancel payouts            ✓        ·         ·     ← owner-only
  modify payout rules       ✓        ·         ·     ← owner-only
  invite operators          ✓        ·         ·
  modify operator roles     ✓        ·         ·


SCHEMA
──────
    CREATE TABLE IF NOT EXISTS operators (
      id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at   timestamptz NOT NULL DEFAULT now(),
      email        text NOT NULL UNIQUE,
      name         text NOT NULL,
      role         text NOT NULL DEFAULT 'operator'
        CHECK (role IN ('owner','operator','viewer')),
      active       boolean NOT NULL DEFAULT true,
      last_login   timestamptz,
      invited_by   uuid REFERENCES operators(id),
      meta         jsonb DEFAULT '{}'::jsonb
    );

    CREATE TABLE IF NOT EXISTS operator_sessions (
      id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at   timestamptz NOT NULL DEFAULT now(),
      operator_id  uuid NOT NULL REFERENCES operators(id),
      token_hash   text NOT NULL,
      expires_at   timestamptz NOT NULL,
      revoked_at   timestamptz,
      user_agent   text,
      ip           text
    );
    CREATE INDEX IF NOT EXISTS operator_sessions_hash_idx
      ON operator_sessions (token_hash);

    CREATE TABLE IF NOT EXISTS audit_log (
      id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at   timestamptz NOT NULL DEFAULT now(),
      operator_id  uuid,
      operator_name text,
      action       text NOT NULL,
      target_type  text,
      target_id    text,
      details      jsonb DEFAULT '{}'::jsonb,
      ip           text
    );
    CREATE INDEX IF NOT EXISTS audit_log_created_idx
      ON audit_log (created_at DESC);
    CREATE INDEX IF NOT EXISTS audit_log_operator_idx
      ON audit_log (operator_id, created_at DESC);

    -- Bootstrap the owner account (run once with your real email)
    INSERT INTO operators (email, name, role)
    VALUES ('YOUR_EMAIL@empire-ai.co.uk', 'Empire Owner', 'owner')
    ON CONFLICT (email) DO NOTHING;


WIRE-UP IN hub.py
─────────────────
    from empire_auth import (
        AuthEngine,
        register_auth_routes,
        require_role,
    )

    auth_engine = AuthEngine(
        get_db=          get_db,
        sign_token=      _sign_token,
        verify_token=    _verify_token,
        send_email=      _send_email,
        public_base_url= PUBLIC_BASE_URL,
        legacy_hub_token=HUB_TOKEN,        # backwards compat
        session_ttl_hours=12,
    )

    register_auth_routes(
        app,
        auth_engine=auth_engine,
        require_auth=require_auth,
    )

    # Replace the existing require_auth dependency with auth_engine's version:
    require_auth   = auth_engine.require_auth
    require_owner  = require_role(auth_engine, "owner")
    require_operator = require_role(auth_engine, "operator")  # operator+owner

    # On every privileged endpoint, switch to the role-aware decorator:
    @app.post("/api/v1/payouts/approve")
    async def payouts_approve(..., op: dict = Depends(require_owner)):
        # op is the operator dict; use op['id'] for audit logging
        ...
"""

import os
import re
import hmac
import time
import hashlib
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional


def parse_pg_timestamptz(s: str) -> datetime:
    """
    Tolerant ISO-8601 parser. PostgreSQL serializes timestamptz with
    trailing-zeros-stripped microseconds (e.g. `.52529+00:00`), but
    Python 3.10's `datetime.fromisoformat` requires exactly 3 or 6
    digits. Pad to 6 before delegating.
    """
    s = s.replace("Z", "+00:00")
    m = re.match(r"^(.*\.)(\d+)([+-].*|$)", s)
    if m:
        prefix, micros, suffix = m.groups()
        if 0 < len(micros) < 6:
            micros = micros.ljust(6, "0")
        elif len(micros) > 6:
            micros = micros[:6]
        s = prefix + micros + suffix
    return datetime.fromisoformat(s)

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


log = logging.getLogger("empire.auth")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
SESSION_TTL_HOURS_DEFAULT = 12
LOGIN_LINK_TTL_SECONDS    = 600  # 10 min · login links are short-lived
ROLE_HIERARCHY = {"owner": 3, "operator": 2, "viewer": 1}


# ─────────────────────────────────────────────────────────────────────────────
# AUTH ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class AuthEngine:
    """
    Per-operator authentication + audit logging. Magic-link login,
    session tokens, role-based access.
    """

    def __init__(
        self,
        *,
        get_db: Callable,
        sign_token: Callable,
        verify_token: Callable,
        send_email: Callable,
        public_base_url: str,
        legacy_hub_token: str = "",
        session_ttl_hours: int = SESSION_TTL_HOURS_DEFAULT,
    ):
        self.get_db           = get_db
        self.sign_token       = sign_token
        self.verify_token     = verify_token
        self.send_email       = send_email
        self.public_base_url  = public_base_url.rstrip("/")
        self.legacy_hub_token = legacy_hub_token
        self.session_ttl      = timedelta(hours=session_ttl_hours)
        self.bearer           = HTTPBearer(auto_error=False)
        self.stats = {
            "logins":           0,
            "sessions_created": 0,
            "audit_entries":    0,
            "rejections":       0,
        }

    # ── PUBLIC: SEND MAGIC LINK ─────────────────────────────────────────
    async def send_login_link(self, email: str, ip: str = "") -> dict:
        """Send a magic-link login email. Returns {ok, error?}."""
        email = (email or "").lower().strip()
        if not email or "@" not in email:
            return {"ok": False, "error": "valid email required"}

        try:
            db = self.get_db()
            res = db.table("operators").select("id, name, role, active") \
                .eq("email", email).limit(1).execute()
            if not res.data:
                # Don't reveal whether email exists — return ok regardless
                log.info(f"[auth] login attempt for unknown email: {email}")
                return {"ok": True}
            operator = res.data[0]
            if not operator.get("active"):
                log.info(f"[auth] login attempt for inactive operator: {email}")
                return {"ok": True}
        except Exception as e:
            log.error(f"[auth] DB lookup failed: {e}")
            return {"ok": False, "error": "service error"}

        # Build the magic link token
        payload = {
            "operator_id": str(operator["id"]),
            "email":       email,
            "exp":         int(time.time()) + LOGIN_LINK_TTL_SECONDS,
            "iat":         int(time.time()),
            "kind":        "login_link",
        }
        token = self.sign_token(payload)
        link = f"{self.public_base_url}/auth/verify?t={token}"

        html = f"""
          <div style="font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;padding:32px;background:#0a0a0a;color:#e4e4e7;">
            <div style="border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:22px;">
              <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Operator Login</div>
              <div style="font-size:22px;font-weight:700;color:#44E5B8;margin-top:6px;letter-spacing:-0.02em;">
                Your login link
              </div>
            </div>
            <p style="font-size:14px;line-height:1.7;color:#a1a1aa;">
              Hi {operator['name']}, click below to sign in to the Empire AI operator console.
              This link expires in 10 minutes.
            </p>
            <div style="margin:28px 0;text-align:center;">
              <a href="{link}" style="display:inline-block;background:#44E5B8;color:#000;padding:14px 32px;text-decoration:none;font-weight:700;letter-spacing:.04em;">Sign in &rarr;</a>
            </div>
            <div style="font-size:11px;color:#52525b;line-height:1.7;">
              If you didn't request this, ignore the email. Someone may have entered your address by mistake.
              {f'Request from {ip}.' if ip else ''}
            </div>
          </div>
        """
        try:
            await self.send_email(
                to=email,
                subject="Empire AI · Your login link",
                html=html,
            )
            self.stats["logins"] += 1
            return {"ok": True}
        except Exception as e:
            log.error(f"[auth] login email send failed: {e}")
            return {"ok": False, "error": "could not send login email"}

    # ── PUBLIC: VERIFY MAGIC LINK & CREATE SESSION ──────────────────────
    async def verify_login_link(
        self,
        token: str,
        user_agent: str = "",
        ip: str = "",
    ) -> dict:
        """Verify the magic link and create a session. Returns {ok, session_token?, error?}."""
        payload = self.verify_token(token)
        if not payload or payload.get("kind") != "login_link":
            return {"ok": False, "error": "invalid or expired link"}

        operator_id = payload.get("operator_id")
        try:
            db = self.get_db()
            res = db.table("operators").select("id, name, email, role, active") \
                .eq("id", operator_id).limit(1).execute()
            if not res.data or not res.data[0].get("active"):
                return {"ok": False, "error": "account not active"}
            operator = res.data[0]
        except Exception as e:
            log.error(f"[auth] verify DB lookup failed: {e}")
            return {"ok": False, "error": "service error"}

        # Generate session token
        session_token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(session_token)
        expires = datetime.now(timezone.utc) + self.session_ttl

        try:
            db.table("operator_sessions").insert({
                "operator_id": operator["id"],
                "token_hash":  token_hash,
                "expires_at":  expires.isoformat(),
                "user_agent":  user_agent[:300] if user_agent else None,
                "ip":          ip[:60] if ip else None,
            }).execute()

            db.table("operators").update({
                "last_login": datetime.now(timezone.utc).isoformat(),
            }).eq("id", operator["id"]).execute()

            self.stats["sessions_created"] += 1
        except Exception as e:
            log.error(f"[auth] session insert failed: {e}")
            return {"ok": False, "error": "could not create session"}

        # Audit log entry
        await self.audit(
            operator_id=str(operator["id"]),
            operator_name=operator["name"],
            operator_email=operator["email"],
            action="login",
            target_type="session",
            ip=ip,
        )

        return {
            "ok":            True,
            "session_token": session_token,
            "expires_at":    expires.isoformat(),
            "operator":      {
                "id":    str(operator["id"]),
                "name":  operator["name"],
                "email": operator["email"],
                "role":  operator["role"],
            },
        }

    # ── PUBLIC: REVOKE SESSION (logout) ─────────────────────────────────
    async def revoke_session(self, session_token: str) -> dict:
        token_hash = self._hash_token(session_token)
        try:
            db = self.get_db()
            db.table("operator_sessions").update({
                "revoked_at": datetime.now(timezone.utc).isoformat(),
            }).eq("token_hash", token_hash).execute()
            return {"ok": True}
        except Exception as e:
            log.error(f"[auth] revoke failed: {e}")
            return {"ok": False, "error": str(e)}

    # ── PUBLIC: RESOLVE A REQUEST TO AN OPERATOR ────────────────────────
    async def resolve_request(self, request: Request) -> Optional[dict]:
        """
        Find which operator (if any) this request is from. Returns the
        operator dict or None.

        Auth priority:
          1. Authorization: Bearer <session_token> (per-operator)
          2. Authorization: Bearer <legacy_hub_token> (cron / backwards compat)
        """
        creds: Optional[HTTPAuthorizationCredentials] = await self.bearer(request)
        token = None
        if creds and creds.scheme.lower() == "bearer":
            token = creds.credentials

        if not token:
            # Try ?token= query parameter as fallback (used by view routes)
            token = request.query_params.get("token", "")

        if not token:
            # Cookie fallback — set by /auth/verify on magic-link success
            token = request.cookies.get("empire_session", "")

        if not token:
            return None

        # Legacy HUB_TOKEN path → return synthetic "system" operator with owner role
        if self.legacy_hub_token and token == self.legacy_hub_token:
            return {
                "id":     "legacy-hub-token",
                "name":   "Legacy System",
                "email":  "system@empire-ai",
                "role":   "owner",
                "legacy": True,
            }

        # Session token lookup
        token_hash = self._hash_token(token)
        try:
            db = self.get_db()
            res = db.table("operator_sessions").select(
                "operator_id, expires_at, revoked_at"
            ).eq("token_hash", token_hash).limit(1).execute()
            if not res.data:
                return None
            session = res.data[0]
            if session.get("revoked_at"):
                return None
            expires_at = session["expires_at"]
            if isinstance(expires_at, str):
                expires_at = parse_pg_timestamptz(expires_at)
            if expires_at < datetime.now(timezone.utc):
                return None

            # Pull the operator
            op_res = db.table("operators").select("id, name, email, role, active") \
                .eq("id", session["operator_id"]).limit(1).execute()
            if not op_res.data:
                return None
            operator = op_res.data[0]
            if not operator.get("active"):
                return None
            return {
                "id":     str(operator["id"]),
                "name":   operator["name"],
                "email":  operator["email"],
                "role":   operator["role"],
                "legacy": False,
            }
        except Exception as e:
            log.error(f"[auth] resolve failed: {e}")
            return None

    # ── DEPENDENCY: require any authenticated operator ──────────────────
    async def require_auth(self, request: Request) -> dict:
        operator = await self.resolve_request(request)
        if not operator:
            self.stats["rejections"] += 1
            raise HTTPException(401, "Authentication required")
        return operator

    # ── PUBLIC: AUDIT LOG ENTRY ─────────────────────────────────────────
    async def audit(
        self,
        *,
        operator_id:    str = "",
        operator_name:  str = "",
        operator_email: str = "",
        action:         str,
        target_type:    str = "",
        target_id:      str = "",
        details:        Optional[dict] = None,
        ip:             str = "",
    ) -> None:
        """Persist an audit log entry. Best-effort — never raises."""
        try:
            db = self.get_db()
            # NB: live schema uses resource_type/resource_id (not target_*),
            # and operator_name/operator_email/resource_type are NOT NULL.
            db.table("audit_log").insert({
                "operator_id":    operator_id or None,
                "operator_name":  (operator_name or "")[:160],
                "operator_email": (operator_email or "")[:160],
                "action":         action[:80],
                "resource_type":  (target_type or "")[:40],
                "resource_id":    target_id[:80] if target_id else None,
                "details":        details or {},
                "ip":             ip[:60] if ip else None,
            }).execute()
            self.stats["audit_entries"] += 1
        except Exception as e:
            log.debug(f"[auth] audit log failed: {e}")

    def _hash_token(self, token: str) -> str:
        """SHA-256 the session token before storing — never store plaintext."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    # ── OPERATOR MANAGEMENT ──────────────────────────────────────────────
    async def invite_operator(
        self,
        *,
        email: str,
        name: str,
        role: str,
        invited_by_id: str,
        invited_by_name: str = "",
        invited_by_email: str = "",
    ) -> dict:
        """Owner invites a new operator. Creates the row + sends a login link."""
        if role not in ROLE_HIERARCHY:
            return {"ok": False, "error": "invalid role"}

        email = email.lower().strip()
        try:
            db = self.get_db()
            existing = db.table("operators").select("id").eq("email", email).limit(1).execute()
            if existing.data:
                return {"ok": False, "error": "operator with that email already exists"}

            ins = db.table("operators").insert({
                "email":      email,
                "name":       name[:160],
                "role":       role,
                "active":     True,
                "invited_by": invited_by_id if invited_by_id != "legacy-hub-token" else None,
            }).execute()

            await self.audit(
                operator_id=invited_by_id,
                operator_name=invited_by_name,
                operator_email=invited_by_email,
                action="operator_invited",
                target_type="operator",
                target_id=str(ins.data[0]["id"]) if ins.data else None,
                details={"email": email, "role": role},
            )
        except Exception as e:
            log.error(f"[auth] invite insert failed: {e}")
            return {"ok": False, "error": str(e)}

        # Send the first login link
        await self.send_login_link(email)
        return {"ok": True, "operator_id": str(ins.data[0]["id"]) if ins.data else None}


# ─────────────────────────────────────────────────────────────────────────────
# ROLE DEPENDENCIES
# ─────────────────────────────────────────────────────────────────────────────
def require_role(auth_engine: AuthEngine, min_role: str):
    """
    Returns a FastAPI dependency that requires at least the given role.
    Use as: op: dict = Depends(require_role(auth_engine, "owner"))
    """
    if min_role not in ROLE_HIERARCHY:
        raise ValueError(f"invalid role: {min_role}")
    min_level = ROLE_HIERARCHY[min_role]

    async def _dependency(request: Request) -> dict:
        operator = await auth_engine.require_auth(request)
        op_level = ROLE_HIERARCHY.get(operator.get("role"), 0)
        if op_level < min_level:
            raise HTTPException(403, f"This action requires {min_role} role")
        return operator

    return _dependency


# ─────────────────────────────────────────────────────────────────────────────
# HTML PAGES
# ─────────────────────────────────────────────────────────────────────────────
def _login_page() -> str:
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Sign in</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0A1A2F; color: #F8FAFD;
  font-family: 'Inter', sans-serif; letter-spacing: -0.02em;
  min-height: 100vh; padding: 60px 20px;
  display: flex; align-items: center; justify-content: center;
  background:
    radial-gradient(ellipse at top right, rgba(68,229,184,0.06), transparent 50%),
    radial-gradient(ellipse at bottom left, rgba(90,200,250,0.05), transparent 50%),
    #0A1A2F;
}
.box {
  max-width: 440px; width: 100%;
  background: #15263F; border: 1px solid rgba(122,140,163,0.18);
  padding: 40px 36px;
}
.brand-mark { display: flex; align-items: baseline; justify-content: center; gap: 8px; margin-bottom: 8px; }
.brand-mark .e { font-weight: 700; font-size: 22px; letter-spacing: 0.22em; }
.brand-mark .ai { font-weight: 700; font-size: 22px; letter-spacing: 0.22em; color: #5AC8FA; }
.tag { text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 9px;
  color: #4A5A72; letter-spacing: 0.32em; text-transform: uppercase; margin-bottom: 36px; }
h1 { font-weight: 200; font-size: 28px; letter-spacing: -0.04em; margin-bottom: 12px; }
h1 em { font-style: italic; color: #44E5B8; font-weight: 500; }
.sub { color: #7A8CA3; font-size: 14px; line-height: 1.7; margin-bottom: 28px; }
label { display: block; font-family: 'JetBrains Mono', monospace; font-size: 10px;
  color: #7A8CA3; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 6px; }
input { width: 100%; background: rgba(0,0,0,0.4); color: #F8FAFD;
  border: 1px solid rgba(122,140,163,0.18); font-family: 'JetBrains Mono', monospace;
  font-size: 14px; padding: 14px; outline: none; transition: border-color 0.2s; }
input:focus { border-color: #44E5B8; }
button { width: 100%; background: #44E5B8; color: #000; border: none;
  padding: 16px; font-family: 'Inter', sans-serif; font-weight: 700; font-size: 14px;
  letter-spacing: 0.04em; cursor: pointer; transition: all 0.2s; margin-top: 16px; }
button:hover { background: transparent; color: #44E5B8; outline: 1px solid #44E5B8; }
button:disabled { opacity: 0.4; cursor: wait; }
.flash { display: none; padding: 12px 16px; margin-top: 16px;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.04em; }
.flash.show { display: block; }
.flash.success { color: #44E5B8; background: rgba(68,229,184,0.06); border: 1px solid rgba(68,229,184,0.25); }
.flash.error { color: #f43f5e; background: rgba(244,63,94,0.06); border: 1px solid rgba(244,63,94,0.25); }
.foot { text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 9px;
  color: #4A5A72; letter-spacing: 0.18em; margin-top: 28px; }
</style></head><body>
<div class="box">
  <div class="brand-mark"><span class="e">EMPIRE</span><span class="ai">AI</span></div>
  <div class="tag">Operator Console</div>
  <h1>Sign <em>in</em></h1>
  <p class="sub">Enter your email · we'll send a one-time login link.</p>
  <label>Email</label>
  <input type="email" id="email" placeholder="you@empire-ai.co.uk" autofocus>
  <button id="btn" onclick="send()">Send login link</button>
  <div id="flash" class="flash"></div>
  <div class="foot">Sovereign Operator · V49</div>
</div>
<script>
async function send() {
  const email = document.getElementById('email').value.trim();
  const flash = document.getElementById('flash');
  const btn = document.getElementById('btn');
  flash.className = 'flash';
  if (!email || !email.includes('@')) {
    flash.className = 'flash show error';
    flash.textContent = '✗ Enter a valid email';
    return;
  }
  btn.disabled = true; btn.textContent = 'Sending...';
  try {
    const r = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    const d = await r.json();
    if (r.ok && d.ok) {
      flash.className = 'flash show success';
      flash.textContent = '✓ If that email is registered, a login link is on its way';
    } else {
      flash.className = 'flash show error';
      flash.textContent = '✗ ' + (d.error || 'Could not send');
    }
  } catch (e) {
    flash.className = 'flash show error';
    flash.textContent = '✗ Network error';
  } finally {
    btn.disabled = false; btn.textContent = 'Send login link';
  }
}
document.getElementById('email').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
</script>
</body></html>"""


def _verified_page(operator: dict, session_token: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Signed in</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
body {{ background: #0A1A2F; color: #F8FAFD; font-family: 'Inter', sans-serif;
  min-height: 100vh; margin: 0; display: flex; align-items: center; justify-content: center; padding: 20px;
  background:
    radial-gradient(ellipse at top right, rgba(68,229,184,0.06), transparent 50%),
    #0A1A2F;
}}
.box {{ max-width: 440px; background: #15263F; border: 1px solid rgba(122,140,163,0.18);
  padding: 40px 36px; text-align: center; }}
.icon {{ font-size: 48px; color: #44E5B8; margin-bottom: 18px; }}
h1 {{ font-weight: 200; font-size: 26px; letter-spacing: -0.04em; margin-bottom: 12px; }}
.meta {{ font-family: 'JetBrains Mono', monospace; font-size: 11px;
  color: #7A8CA3; letter-spacing: 0.04em; margin: 16px 0 28px; line-height: 1.7; }}
.meta strong {{ color: #F8FAFD; }}
a.cta {{ display: inline-block; background: #44E5B8; color: #000;
  padding: 14px 32px; text-decoration: none; font-weight: 700; letter-spacing: 0.04em; }}
</style></head><body>
<div class="box">
  <div class="icon">✓</div>
  <h1>Signed in</h1>
  <div class="meta">
    Welcome back, <strong>{operator['name']}</strong><br>
    Role: <strong>{operator['role']}</strong>
  </div>
  <a class="cta" href="/command">Open Command Deck →</a>
</div>
<script>
// Persist token in localStorage for SPA fetches that prefer Authorization headers.
// The server-side Set-Cookie on this response is what authenticates plain navigation.
try {{ localStorage.setItem('hub_token', {session_token!r}); }} catch (e) {{}}
</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
def register_auth_routes(
    app: FastAPI,
    *,
    auth_engine: AuthEngine,
    require_auth: Callable,
):
    """Register auth routes. Pass auth_engine and the require_auth dep."""

    # ── PUBLIC: LOGIN PAGE ─────────────────────────────────────────────
    @app.get("/auth/login", response_class=HTMLResponse)
    async def login_page():
        return HTMLResponse(_login_page())

    # ── PUBLIC: SEND MAGIC LINK ────────────────────────────────────────
    @app.post("/api/v1/auth/login")
    async def auth_send_link(request: Request):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        email = body.get("email", "")
        ip = request.client.host if request.client else ""
        result = await auth_engine.send_login_link(email=email, ip=ip)
        return result

    # ── PUBLIC: VERIFY MAGIC LINK ──────────────────────────────────────
    @app.get("/auth/verify", response_class=HTMLResponse)
    async def auth_verify(request: Request, t: str = Query(...)):
        ua = request.headers.get("user-agent", "")
        ip = request.client.host if request.client else ""
        result = await auth_engine.verify_login_link(token=t, user_agent=ua, ip=ip)
        if not result.get("ok"):
            return HTMLResponse(f"""
                <!DOCTYPE html><html><body style="background:#0A1A2F;color:#F8FAFD;
                font-family:system-ui;display:flex;align-items:center;justify-content:center;
                min-height:100vh;margin:0;">
                <div style="text-align:center;max-width:400px;padding:32px;">
                  <div style="font-size:48px;color:#f43f5e;margin-bottom:16px;">✗</div>
                  <h1 style="font-weight:200;margin-bottom:12px;">Link invalid</h1>
                  <p style="color:#7A8CA3;">{result.get('error', 'Unknown error')}</p>
                  <a href="/auth/login" style="color:#44E5B8;display:inline-block;margin-top:24px;">Try again →</a>
                </div>
                </body></html>
            """, status_code=401)

        response = HTMLResponse(_verified_page(result["operator"], result["session_token"]))
        response.set_cookie(
            key="empire_session",
            value=result["session_token"],
            max_age=int(auth_engine.session_ttl.total_seconds()),
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
        return response

    # ── PUBLIC: LOGOUT ─────────────────────────────────────────────────
    @app.post("/api/v1/auth/logout")
    async def auth_logout(request: Request, op: dict = Depends(auth_engine.require_auth)):
        # Grab the actual token to revoke it — check Bearer header, then cookie
        creds: Optional[HTTPAuthorizationCredentials] = await auth_engine.bearer(request)
        token_to_revoke = None
        if creds and creds.credentials != auth_engine.legacy_hub_token:
            token_to_revoke = creds.credentials
        if not token_to_revoke:
            token_to_revoke = request.cookies.get("empire_session", "")
        if token_to_revoke:
            await auth_engine.revoke_session(token_to_revoke)

        await auth_engine.audit(
            operator_id=op.get("id", ""),
            operator_name=op.get("name", ""),
            operator_email=op.get("email", ""),
            action="logout",
            ip=request.client.host if request.client else "",
        )
        response = JSONResponse({"ok": True})
        response.delete_cookie("empire_session", path="/")
        return response

    # ── OPERATOR: WHO AM I ─────────────────────────────────────────────
    @app.get("/api/v1/auth/me")
    async def auth_me(op: dict = Depends(auth_engine.require_auth)):
        return op

    # ── OWNER: INVITE OPERATOR ─────────────────────────────────────────
    @app.post("/api/v1/auth/invite")
    async def auth_invite(
        request: Request,
        op: dict = Depends(require_role(auth_engine, "owner")),
    ):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        email = (body.get("email") or "").strip().lower()
        name  = (body.get("name") or "").strip()
        role  = (body.get("role") or "operator").strip().lower()

        if not (email and name):
            raise HTTPException(400, "email and name required")
        if role not in ROLE_HIERARCHY:
            raise HTTPException(400, "invalid role")

        return await auth_engine.invite_operator(
            email=email,
            name=name,
            role=role,
            invited_by_id=op.get("id", ""),
            invited_by_name=op.get("name", ""),
            invited_by_email=op.get("email", ""),
        )

    # ── OWNER: LIST OPERATORS ──────────────────────────────────────────
    @app.get("/api/v1/auth/operators")
    async def auth_list_operators(
        op: dict = Depends(require_role(auth_engine, "owner")),
    ):
        try:
            db = auth_engine.get_db()
            res = db.table("operators").select(
                "id, email, name, role, active, last_login, created_at"
            ).order("created_at", desc=False).execute()
            return {"operators": res.data or []}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── OWNER: UPDATE OPERATOR ROLE / DEACTIVATE ──────────────────────
    @app.post("/api/v1/auth/operators/update")
    async def auth_update_operator(
        request: Request,
        op: dict = Depends(require_role(auth_engine, "owner")),
    ):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        target_id = body.get("operator_id")
        if not target_id:
            raise HTTPException(400, "operator_id required")

        update = {}
        if "role" in body:
            if body["role"] not in ROLE_HIERARCHY:
                raise HTTPException(400, "invalid role")
            update["role"] = body["role"]
        if "active" in body:
            update["active"] = bool(body["active"])
        if "name" in body:
            update["name"] = body["name"][:160]

        if not update:
            raise HTTPException(400, "no changes provided")

        try:
            db = auth_engine.get_db()
            db.table("operators").update(update).eq("id", target_id).execute()
            await auth_engine.audit(
                operator_id=op.get("id", ""),
                operator_name=op.get("name", ""),
                operator_email=op.get("email", ""),
                action="operator_updated",
                target_type="operator",
                target_id=target_id,
                details=update,
            )
            return {"ok": True}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── OWNER: AUDIT LOG VIEWER ────────────────────────────────────────
    @app.get("/api/v1/auth/audit")
    async def auth_audit_log(
        limit: int = Query(100, ge=1, le=500),
        operator_id: str = Query(""),
        op: dict = Depends(require_role(auth_engine, "owner")),
    ):
        try:
            db = auth_engine.get_db()
            q = db.table("audit_log").select("*").order("created_at", desc=True).limit(limit)
            if operator_id:
                q = q.eq("operator_id", operator_id)
            return {"audit": q.execute().data or []}
        except Exception as e:
            raise HTTPException(500, str(e))

    log.info("[auth] Routes registered · /auth/{login,verify} · /api/v1/auth/{login,logout,me,invite,operators,audit}")
