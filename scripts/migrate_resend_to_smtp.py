#!/usr/bin/env python3
"""
EMPIRE V49 · Resend REST API → SMTP Migration Script
======================================================
Replaces direct `api.resend.com/emails` HTTP calls with the shared
`scripts.helpers.smtp_email.send_smtp_email()` helper across the
entire codebase.

Also extends the SMTP helper to support custom from name/address
and Reply-To headers (needed by several callers).

Usage:
    python3 scripts/migrate_resend_to_smtp.py              # live migration
    python3 scripts/migrate_resend_to_smtp.py --dry-run    # preview only
    python3 scripts/migrate_resend_to_smtp.py --file hub   # single file

Three files use api.resend.com/domains (NOT email sending):
  - agents/system_supervisor.py     — domain verification check
  - agents_seo_weekly.py            — domain status in weekly digest
  - agents_resend_monitor.py        — dedicated domain health monitor
These are NOT migrated — they don't send emails.

Files with ATTACHMENTS (not supported by SMTP helper):
  - scripts/send_payment_report.py  — PDF report attachment
  - send_carrier_drafts.py          — no attachments, just HTML
These will be noted but retain their Resend API call for now.
"""

import os
import re
import sys
import ast
import argparse
from pathlib import Path
from typing import List, Tuple, Optional

REPO = Path(__file__).resolve().parent.parent


# ── SMTP helper extension: add from_name/from_addr/reply_to support ───
SMTP_HELPER_PATH = REPO / "scripts" / "helpers" / "smtp_email.py"



# ── Migration rules ──────────────────────────────────────────────────
# Each rule: (file_path, [replacements])
# Where each replacement is (description, old_pattern_regex, new_template)
# Most replacements use AST-level matching where possible, or line-level
# regex for simpler patterns.

Migration = Tuple[str, str, str]  # (description, old_string, new_string)

def _ast_find_imports(source: str) -> set:
    """Return set of top-level module names already imported."""
    try:
        tree = ast.parse(source)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names.add(node.module.split(".")[0])
        return names
    except SyntaxError:
        return set()


def _add_or_replace_import(source: str, target_file: str) -> str:
    """Add 'from scripts.helpers.smtp_email import send_smtp_email'
    at the top of the file, after existing module-level imports,
    before any def or class declaration."""
    if "from scripts.helpers.smtp_email import send_smtp_email" in source:
        return source  # already imported

    lines = source.split("\n")
    
    # Only consider lines BEFORE the first def/class (module-level)
    first_def_line = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            first_def_line = i
            break
    
    # Find the last import in the module-level section
    last_import_idx = -1
    for i in range(min(first_def_line, len(lines))):
        stripped = lines[i].strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            last_import_idx = i

    if last_import_idx >= 0:
        indent = ""
        lines.insert(last_import_idx + 1, "")
        lines.insert(last_import_idx + 2, f"{indent}from scripts.helpers.smtp_email import send_smtp_email")
        return "\n".join(lines)

    # No imports found — add after any docstring or module doc, before first def
    insert_before = min(first_def_line, len(lines))
    lines.insert(insert_before, "\nfrom scripts.helpers.smtp_email import send_smtp_email\n")
    return "\n".join(lines)


# ── File-by-file migration definitions ──────────────────────────────

def _migrate_affiliate_recruiter(source: str) -> Tuple[Optional[str], List[str]]:
    """bots/affiliate_recruiter.py - async httpx."""
    notes = []
    old = '''async def _send_email_direct(to: str, subject: str, html: str) -> dict:
    """Send an email via Resend API using the affiliate-dedicated key.
    Falls back to RESEND_API_KEY if RESEND_AFFILIATE_KEY is not set."""
    if not RESEND_AFFILIATE_KEY:
        return {"ok": False, "error": "RESEND_AFFILIATE_KEY (and RESEND_API_KEY fallback) missing"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_AFFILIATE_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "Empire AI Ops <ops@empire-ai.co.uk>",
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            ok = r.status_code < 300
            if ok:
                log.info(f"[affiliate_recruiter] Email sent to {to}: {data.get('id', '?')}")
            else:
                log.warning(f"[affiliate_recruiter] Email send to {to} failed: {data}")
            return {"ok": ok, "id": data.get("id"), "raw": data}
    except Exception as e:
        log.error(f"[affiliate_recruiter] Email send error for {to}: {e}")
        return {"ok": False, "error": str(e)}'''

    new = '''async def _send_email_direct(to: str, subject: str, html: str) -> dict:
    """Send an email via SMTP (Resend) using the shared SMTP helper.
    Falls back to RESEND_API_KEY if RESEND_AFFILIATE_KEY is not set."""
    if not RESEND_AFFILIATE_KEY:
        return {"ok": False, "error": "RESEND_AFFILIATE_KEY (and RESEND_API_KEY fallback) missing"}
    try:
        result = send_smtp_email(
            to=to,
            subject=subject,
            html=html,
            from_name="Empire AI Ops",
            from_addr="ops@empire-ai.co.uk",
        )
        if result.get("ok"):
            log.info(f"[affiliate_recruiter] Email sent to {to}: {result.get('message_id', '?')}")
        else:
            log.warning(f"[affiliate_recruiter] Email send to {to} failed: {result.get('error', '')}")
        return {"ok": result["ok"], "id": result.get("message_id"), "raw": result}
    except Exception as e:
        log.error(f"[affiliate_recruiter] Email send error for {to}: {e}")
        return {"ok": False, "error": str(e)}'''

    if old not in source:
        notes.append("_send_email_direct: pattern not found (may already be migrated)")
        return None, notes
    notes.append("Migrated _send_email_direct to SMTP with from_name='Empire AI Ops'")
    return source.replace(old, new, 1), notes


def _migrate_agents_email_outreach(source: str) -> Tuple[Optional[str], List[str]]:
    """agents/email_outreach.py - urllib."""
    notes = []
    # Remove RESEND_API constant
    if "RESEND_API = \"https://api.resend.com/emails\"" in source:
        source = source.replace('RESEND_API = "https://api.resend.com/emails"\n', "")
        notes.append("Removed RESEND_API constant")
    else:
        notes.append("RESEND_API constant not found (may already be migrated)")

    old = '''def _send_email(api_key: str, to: str, subject: str, html: str) -> dict:
    try:
        req = urllib.request.Request(
            RESEND_API,
            data=json.dumps({
                "from": FROM_ADDR,
                "to": [to],
                "subject": subject,
                "html": html,
            }).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read())
            return {"ok": True, "id": body.get("id")}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
        except Exception:
            err = {"raw": str(e)}
        return {"ok": False, "error": err}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    new = '''def _send_email(to: str, subject: str, html: str) -> dict:
    try:
        result = send_smtp_email(to=to, subject=subject, html=html)
        if result.get("ok"):
            return {"ok": True, "id": result.get("message_id")}
        return {"ok": False, "error": result.get("error")}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    if old not in source:
        notes.append("_send_email: pattern not found (may already be migrated)")
        return None, notes
    source = source.replace(old, new, 1)
    notes.append("Migrated _send_email to SMTP (removed api_key param)")

    # Update call site
    old_call = '''res = _send_email(api_key, c["email"], subject, body)'''
    new_call = '''res = _send_email(c["email"], subject, body)'''
    if old_call in source:
        source = source.replace(old_call, new_call, 1)
        notes.append("Updated _send_email call site (removed api_key arg)")

    # Remove unused urllib imports if no longer referenced
    for import_line in ['import urllib.request', 'import urllib.error']:
        if import_line in source:
            # Check if the import's module is used elsewhere in the source
            mod_name = import_line.split()[-1]
            if source.count(mod_name) == 1:  # only the import line itself
                source = source.replace(import_line + '\n', '')
                notes.append(f"Removed unused import: {import_line}")

    return source, notes


def _migrate_inbound_handler(source: str) -> Tuple[Optional[str], List[str]]:
    """agents/inbound_handler/server.py - send_email with urllib."""
    notes = []
    old = '''def send_email(to: str, subject: str, body: str) -> str:
    """Send via Resend. Returns the message_id or an error string."""
    resend_key = os.environ.get("RESEND_API_KEY", "")
    if not resend_key:
        return "ERROR: no RESEND_API_KEY"
    payload = json.dumps({
        "from":    "Phillip Livesley <philliplivesley@empire-ai.co.uk>",
        "to":      [to],
        "subject": subject,
        "text":    body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {resend_key}",
            "Content-Type":  "application/json",
            "User-Agent":    "empire-ai-inbound/1.0 (phil@empire-ai.co.uk)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read().decode())
            if resp.get("id"):
                return resp["id"]
            return f"ERROR: {resp}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return f"EXC: {type(e).__name__}: {e}"'''

    new = '''def send_email(to: str, subject: str, body: str) -> str:
    """Send via SMTP (Resend). Returns the message_id or an error string.
    Uses the shared SMTP helper with custom from address."""
    if not os.environ.get("RESEND_API_KEY", ""):
        return "ERROR: no RESEND_API_KEY"
    try:
        # Convert plain text to simple HTML
        html = f"<pre style='font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;line-height:1.6;color:#e4e4e7;white-space:pre-wrap'>{body}</pre>"
        result = send_smtp_email(
            to=to,
            subject=subject,
            html=html,
            text=body,
            from_name="Phillip Livesley",
            from_addr="philliplivesley@empire-ai.co.uk",
        )
        if result.get("ok"):
            return result.get("message_id", "")
        return f"ERROR: {result.get('error', 'unknown')}"
    except Exception as e:
        return f"EXC: {type(e).__name__}: {e}"'''

    if old not in source:
        notes.append("send_email: pattern not found (may already be migrated)")
        return None, notes
    source = source.replace(old, new, 1)
    notes.append("Migrated send_email to SMTP with from_name='Phillip Livesley'")
    return source, notes


def _migrate_send_altpay(source: str) -> Tuple[Optional[str], List[str]]:
    """send_altpay_followup.py - async httpx, standalone script."""
    notes = []
    old_test = '''async with httpx.AsyncClient() as client:
        # Try a quick test to resend.dev first
        test = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": "Phil Livesley <noreply@empire-ai.co.uk>",
                "to": ["delivered@resend.dev"],
                "subject": "Test — quota check",
                "html": "<p>test</p>",
            }
        )
        if test.status_code == 429:
            print("QUOTA EXCEEDED — Resend daily limit hit. Try again after midnight UTC.")
            print(f"Response: {test.json()}")
            return
        elif test.status_code >= 400:
            print(f"Test failed: {test.status_code} — {test.text[:200]}")
            return'''
    new_test = '''# SMTP doesn't have per-day quotas like Resend REST API.
    # The test_smtp_config() call already verified connectivity.'''

    if old_test in source:
        source = source.replace(old_test, new_test, 1)
        notes.append("Replaced Resend quota check with SMTP note")

    old_real = '''        # Send the real email
        r = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": "Phil Livesley <noreply@empire-ai.co.uk>",
                "to": ["jstamatis@alt-pay.net"],
                "subject": "Re: Qualified Merchant Services leads for Alt-Pay",
                "html": REPLY_HTML,
                "reply_to": "phil@empire-ai.co.uk",
            }
        )

        if r.status_code < 300:
            data = r.json()
            print(f"✅ Sent! Resend ID: {data.get('id')}")
            print(f"   To: jstamatis@alt-pay.net")
            print(f"   Subject: Re: Qualified Merchant Services leads for Alt-Pay")
            print(f"   Sample lead included: Schraad Sales & Marketing (OKC)")
        else:
            print(f"❌ Send failed ({r.status_code}):")
            try:
                print(json.dumps(r.json(), indent=2))
            except:
                print(r.text[:500])'''

    new_real = '''        # Send the real email via SMTP
        result = send_smtp_email(
            to="jstamatis@alt-pay.net",
            subject="Re: Qualified Merchant Services leads for Alt-Pay",
            html=REPLY_HTML,
            from_name="Phil Livesley",
            from_addr="noreply@empire-ai.co.uk",
            reply_to="phil@empire-ai.co.uk",
        )

        if result.get("ok"):
            print(f"✅ Sent! SMTP ID: {result.get('message_id')}")
            print(f"   To: jstamatis@alt-pay.net")
            print(f"   Subject: Re: Qualified Merchant Services leads for Alt-Pay")
            print(f"   Sample lead included: Schraad Sales & Marketing (OKC)")
        else:
            print(f"❌ Send failed: {result.get('error', 'unknown')}")'''

    if old_real not in source:
        notes.append("send real email: pattern not found")
        return None, notes
    source = source.replace(old_real, new_real, 1)
    notes.append("Migrated send to SMTP with reply_to header")
    return source, notes


def _migrate_send_carrier_drafts(source: str) -> Tuple[Optional[str], List[str]]:
    """send_carrier_drafts.py - sync httpx."""
    notes = []
    if "https://api.resend.com/emails" not in source:
        return None, notes
    old = '''    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": f"{FROM_NAME} <{FROM_ADDRESS}>", "to": [to], "subject": subject, "html": html},
            timeout=20,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = r.status_code < 300
        resend_id = data.get("id") if ok else None'''

    new = '''    try:
        result = send_smtp_email(to=to, subject=subject, html=html)
        ok = result.get("ok", False)
        resend_id = result.get("message_id") if ok else None'''

    if old not in source:
        notes.append("send_email httpx.post: pattern not found")
        return None, notes
    source = source.replace(old, new, 1)
    # Also replace data.get("id") references in outbox_messages insert
    source = source.replace('"resend_message_id": resend_id,', '"smtp_message_id": resend_id,')
    notes.append("Migrated send_email to SMTP")
    return source, notes


def _migrate_hub(source: str) -> Tuple[Optional[str], List[str]]:
    """hub.py - complex, has quota manager + priority system."""
    notes = []

    # The _send_email function in hub.py
    old = '''async def _send_email(to, subject, html, text: Optional[str] = None, priority: str = "marketing", tags: Optional[list] = None):
    if not RESEND_API_KEY:
        return {"ok": False, "error": "RESEND_API_KEY missing"}

    # ── Quota gate: reject before hitting Resend if tier exhausted ──
    if not await _quota_manager.can_send(priority):
        tier = priority.upper()
        return {
            "ok": False,
            "error": f"daily {tier} email quota exhausted",
            "quota_exceeded": True,
            "quota_tier": priority,
        }

    from_addr = os.environ.get("FROM_ADDRESS", "noreply@empire-ai.co.uk")
    from_name = os.environ.get("FROM_NAME", "Empire AI Operations")
    try:
        payload: dict = {"from": f"{from_name} <{from_addr}>", "to": [to], "subject": subject}
        if html:
            payload["html"] = html
        if text:
            payload["text"] = text
        if tags:
            payload["tags"] = tags
        async with _httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            ok = r.status_code < 300
            if ok:
                await _quota_manager.record_sent(priority)
            return {"ok": ok, "id": data.get("id"), "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    new = '''async def _send_email(to, subject, html, text: Optional[str] = None, priority: str = "marketing", tags: Optional[list] = None):
    if not RESEND_API_KEY:
        return {"ok": False, "error": "RESEND_API_KEY missing"}

    # ── Quota gate: SMTP doesn't have Resend REST API quotas, but we
    # keep the quota system to rate-limit marketing sends ──
    if not await _quota_manager.can_send(priority):
        tier = priority.upper()
        return {
            "ok": False,
            "error": f"daily {tier} email quota exhausted",
            "quota_exceeded": True,
            "quota_tier": priority,
        }

    try:
        result = send_smtp_email(
            to=to,
            subject=subject,
            html=html or "",
            text=text,
        )
        ok = result.get("ok", False)
        if ok:
            await _quota_manager.record_sent(priority)
        return {"ok": ok, "id": result.get("message_id"), "raw": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    if old not in source:
        notes.append("hub _send_email: pattern not found (may already be migrated)")
        return None, notes
    source = source.replace(old, new, 1)
    notes.append("Migrated hub._send_email to SMTP (keeping quota system)")
    return source, notes


def _migrate_contractor_outreach(source: str) -> Tuple[Optional[str], List[str]]:
    """scripts/contractor_outreach.py - sync httpx, uses tags."""
    notes = []
    old = '''def _send_resend(to: str, subject: str, body: str, outreach_id: str = None) -> dict:
    if not RESEND_API_KEY:
        return {"ok": False, "error": "RESEND_API_KEY missing"}
    # Convert to plain text → simple HTML
    html = f"<pre style='font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;line-height:1.6;color:#222;white-space:pre-wrap'>{body}</pre>"
    payload = {"from": f"Empire AI <{FROM_ADDR}>", "to": [to],
               "subject": subject, "text": body, "html": html}
    if outreach_id:
        payload["tags"] = [{"name": "outreach_id", "value": outreach_id}]
    try:
        with httpx.Client(timeout=20) as c:
            r = c.post("https://api.resend.com/emails", json=payload,
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"})
        return {"ok": r.status_code < 400, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}'''

    new = '''def _send_resend(to: str, subject: str, body: str, outreach_id: str = None) -> dict:
    if not RESEND_API_KEY:
        return {"ok": False, "error": "RESEND_API_KEY missing"}
    # Convert to plain text → simple HTML
    html = f"<pre style='font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;line-height:1.6;color:#222;white-space:pre-wrap'>{body}</pre>"
    try:
        result = send_smtp_email(to=to, subject=subject, html=html, text=body)
        if outreach_id:
            log.info(f"[contractor_outreach] sent outreach_id={outreach_id}: {result.get('message_id','')}")
        return {"ok": result.get("ok", False), "status": 200 if result.get("ok") else 500}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}'''

    if old not in source:
        notes.append("_send_resend: pattern not found (may already be migrated)")
        return None, notes
    source = source.replace(old, new, 1)
    notes.append("Migrated _send_resend to SMTP (tags→log)")
    return source, notes


def _migrate_fee_collection(source: str) -> Tuple[Optional[str], List[str]]:
    """scripts/fee_collection_agent.py - async httpx _send_email_resend."""
    notes = []
    old = '''async def _send_email_resend(
    to: str,
    subject: str,
    body: str,
    resend_key: str,
    email_from: str = "noreply@empire-ai.co.uk",
    email_from_name: str = "Empire AI Operations",
) -> dict:
    """Send email via Resend API."""
    if not resend_key:
        return {"ok": False, "error": "RESEND_API_KEY not set"}

    html_body = body.replace("\\n", "<br>\\n")
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,system-ui,sans-serif;background:#0a0a0a;color:#e4e4e7;padding:32px;line-height:1.7;font-size:14px;">
<div style="max-width:580px;margin:0 auto;">
{html_body}
</div>
</body></html>"""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": f"{email_from_name} <{email_from}>",
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            ok = r.status_code < 300
            return {"ok": ok, "id": data.get("id") if ok else None, "status_code": r.status_code, "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    new = '''async def _send_email_resend(
    to: str,
    subject: str,
    body: str,
    resend_key: str = "",
    email_from: str = "noreply@empire-ai.co.uk",
    email_from_name: str = "Empire AI Operations",
) -> dict:
    """Send email via SMTP (Resend). Uses the shared SMTP helper."""
    if not os.environ.get("RESEND_API_KEY", ""):
        return {"ok": False, "error": "RESEND_API_KEY not set"}

    html_body = body.replace("\\n", "<br>\\n")
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,system-ui,sans-serif;background:#0a0a0a;color:#e4e4e7;padding:32px;line-height:1.7;font-size:14px;">
<div style="max-width:580px;margin:0 auto;">
{html_body}
</div>
</body></html>"""

    try:
        result = send_smtp_email(
            to=to,
            subject=subject,
            html=html,
            from_name=email_from_name,
            from_addr=email_from,
        )
        return {"ok": result.get("ok", False), "id": result.get("message_id"), "status_code": 200 if result.get("ok") else 500, "raw": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    if old not in source:
        notes.append("_send_email_resend: pattern not found (may already be migrated)")
        return None, notes
    source = source.replace(old, new, 1)
    notes.append("Migrated _send_email_resend to SMTP")
    return source, notes


def _migrate_send_mrr_email(source: str) -> Tuple[Optional[str], List[str]]:
    """scripts/helpers/send_mrr_email.py - requests.post."""
    notes = []
    old = '''import os, sys, requests
from dotenv import load_dotenv
load_dotenv("/root/.env")

RESEND_KEY = os.getenv("RESEND_API_KEY")
def send(to, subject, text):
    payload = {"from": "Empire AI <hello@empire-ai.co.uk>", "to": [to], "subject": subject, "text": text}
    r = requests.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"}, json=payload)
    print(to, r.status_code)
    return r.status_code == 200'''

    new = '''import os, sys
from dotenv import load_dotenv
load_dotenv("/root/.env")

from scripts.helpers.smtp_email import send_smtp_email

def send(to, subject, text):
    html = f"<pre style='font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;line-height:1.6;white-space:pre-wrap'>{text}</pre>"
    result = send_smtp_email(to=to, subject=subject, html=html, text=text, from_name="Empire AI", from_addr="hello@empire-ai.co.uk")
    print(to, 200 if result.get("ok") else 500)
    return result.get("ok", False)'''

    if old not in source:
        notes.append("send_mrr_email.send: pattern not found")
        return None, notes
    source = source.replace(old, new, 1)
    notes.append("Migrated send_mrr_email to SMTP (removed requests dependency)")
    return source, notes


def _migrate_send_payment_report(source: str) -> Tuple[Optional[str], List[str]]:
    """scripts/send_payment_report.py - has PDF attachment. Keep Resend for now, but note it."""
    notes = []
    notes.append("NOTE: send_payment_report.py uses PDF attachments — SMTP helper doesn't support attachments yet. Keeping Resend API call.")
    return source, notes


def _migrate_omni_channel(source: str) -> Tuple[Optional[str], List[str]]:
    """scripts/omni_channel_announce.py - sync httpx."""
    notes = []
    old = '''    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"{FROM_NAME} <{FROM_ADDRESS}>",
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=20.0,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = r.status_code < 300
        if ok:
            return {"ok": True, "id": data.get("id", "")}
        else:
            error = data.get("message") or data.get("error") or f"HTTP {r.status_code}"
            return {"ok": False, "error": error}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    new = '''    try:
        result = send_smtp_email(to=to, subject=subject, html=html)
        if result.get("ok"):
            return {"ok": True, "id": result.get("message_id", "")}
        else:
            return {"ok": False, "error": result.get("error", "unknown")}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    if old not in source:
        notes.append("send_resend: pattern not found (may already be migrated)")
        return None, notes
    source = source.replace(old, new, 1)
    notes.append("Migrated send_resend to SMTP")
    return source, notes


def _migrate_fee_urgency_push(source: str) -> Tuple[Optional[str], List[str]]:
    """scripts/fee_urgency_push.py - sync httpx."""
    notes = []
    old = '''    try:
        with httpx.Client(timeout=15) as c:
            r = c.post("https://api.resend.com/emails",
                json={"from": f"Empire AI <{from_addr}>", "to": [to], "subject": subject, "html": html},
                headers={"Authorization": f"Bearer {api_key}"})
        return {"ok": r.status_code < 400, "status": r.status_code}'''

    new = '''    try:
        result = send_smtp_email(to=to, subject=subject, html=html)
        return {"ok": result.get("ok", False), "status": 200 if result.get("ok") else 500}'''

    if old not in source:
        notes.append("_send_resend_email: pattern not found (may already be migrated)")
        return None, notes
    source = source.replace(old, new, 1)
    notes.append("Migrated _send_resend_email to SMTP")
    return source, notes


def _migrate_referral_campaign(source: str) -> Tuple[Optional[str], List[str]]:
    """parking_lot/scripts/referral_campaign_send.py - sync httpx."""
    notes = []
    old = '''    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"{FROM_NAME} <{FROM_ADDRESS}>",
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=20.0,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = r.status_code < 300
        if ok:
            return {"ok": True, "id": data.get("id", "")}
        else:
            error = data.get("message") or data.get("error") or f"HTTP {r.status_code}"
            return {"ok": False, "error": error}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    new = '''    try:
        result = send_smtp_email(to=to, subject=subject, html=html)
        if result.get("ok"):
            return {"ok": True, "id": result.get("message_id", "")}
        else:
            return {"ok": False, "error": result.get("error", "unknown")}
    except Exception as e:
        return {"ok": False, "error": str(e)}'''

    if old not in source:
        notes.append("send_resend: pattern not found (may already be migrated)")
        return None, notes
    source = source.replace(old, new, 1)
    notes.append("Migrated referral_campaign send_resend to SMTP")
    return source, notes


# ── Migration manifest ──────────────────────────────────────────────
MIGRATIONS = [
    ("bots/affiliate_recruiter.py",             _migrate_affiliate_recruiter),
    ("agents/email_outreach.py",                _migrate_agents_email_outreach),
    ("agents/inbound_handler/server.py",        _migrate_inbound_handler),
    ("send_altpay_followup.py",                 _migrate_send_altpay),
    ("send_carrier_drafts.py",                  _migrate_send_carrier_drafts),
    ("hub.py",                                  _migrate_hub),
    ("scripts/contractor_outreach.py",          _migrate_contractor_outreach),
    ("scripts/fee_collection_agent.py",         _migrate_fee_collection),
    ("scripts/helpers/send_mrr_email.py",       _migrate_send_mrr_email),
    ("scripts/send_payment_report.py",          _migrate_send_payment_report),
    ("scripts/omni_channel_announce.py",        _migrate_omni_channel),
    ("scripts/fee_urgency_push.py",             _migrate_fee_urgency_push),
    ("parking_lot/scripts/referral_campaign_send.py", _migrate_referral_campaign),
]

# Files using api.resend.com/domains (NOT migrated — not email sending)
DOMAIN_CHECK_FILES = [
    "agents/system_supervisor.py",
    "agents_seo_weekly.py",
    "agents_resend_monitor.py",
]


# ── Main ────────────────────────────────────────────────────────────
def extend_smtp_helper(dry_run: bool) -> List[str]:
    """Extend send_smtp_email to support from_name, from_addr, reply_to params."""
    notes = []
    if not SMTP_HELPER_PATH.exists():
        notes.append(f"SMTP helper not found at {SMTP_HELPER_PATH}")
        return notes

    source = SMTP_HELPER_PATH.read_text()

    # Check if already extended
    if "from_name: Optional[str] = None" in source:
        notes.append("SMTP helper already has from_name/from_addr/reply_to support")
        return notes

    # Replace the function signature
    old_sig = """def send_smtp_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    timeout: int = 30,
) -> dict:"""

    new_sig = """def send_smtp_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    timeout: int = 30,
    from_name: Optional[str] = None,
    from_addr: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> dict:"""

    if old_sig not in source:
        notes.append("SMTP helper signature not found (unexpected format)")
        return notes
    source = source.replace(old_sig, new_sig, 1)

    # Update the _build_message call and From header logic
    old_from = '    msg["From"] = f"{FROM_NAME} <{FROM_ADDR}>"'
    new_from = """    sender_name = from_name or FROM_NAME
    sender_addr = from_addr or FROM_ADDR
    msg["From"] = f"{sender_name} <{sender_addr}>"
    if reply_to:
        msg["Reply-To"] = reply_to"""

    if old_from not in source:
        notes.append("SMTP From header not found")
        return notes
    source = source.replace(old_from, new_from, 1)

    # NOTE: sendmail() envelope-from stays as FROM_ADDR (module-level constant).
    # The From header is embedded in msg_text by _build_message(), so
    # sender_addr from that function is already in the MIME message.

    # Update the docstring
    old_doc = """    Uses STARTTLS on port 587 with the Resend SMTP relay.
    Returns {ok, message_id} on success, {ok, error} on failure."""
    new_doc = """    Uses STARTTLS on port 587 with the Resend SMTP relay.
    Returns {ok, message_id} on success, {ok, error} on failure.

    If from_name/from_addr are provided, they override the module-level
    defaults (FROM_NAME, FROM_ADDRESS). reply_to sets the Reply-To header."""
    source = source.replace(old_doc, new_doc, 1)

    if dry_run:
        print(f"[DRY-RUN] Would extend SMTP helper at {SMTP_HELPER_PATH}")
        print(f"  Changes: signature + from_name/from_addr/reply_to + docstring")
    else:
        SMTP_HELPER_PATH.write_text(source)
    notes.append("Extended SMTP helper with from_name/from_addr/reply_to support")
    return notes


def migrate_file(rel_path: str, migrator, dry_run: bool) -> List[str]:
    """Apply a migration to a single file. Returns notes."""
    abs_path = (REPO / rel_path).resolve()
    notes = []
    if not abs_path.exists():
        return [f"FILE NOT FOUND: {rel_path}"]

    source = abs_path.read_text()

    # Apply the migration
    new_source, file_notes = migrator(source)
    notes.extend(file_notes)

    if new_source is None:
        return notes

    # Add import if not present
    if "from scripts.helpers.smtp_email import send_smtp_email" not in new_source:
        new_source = _add_or_replace_import(new_source, rel_path)
        notes.append("Added import for send_smtp_email")

    # Check for syntax validity
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        notes.append(f"⚠️  SYNTAX ERROR after migration: {e}")
        return notes

    if dry_run:
        print(f"\n─── {rel_path} ───")
        for n in notes:
            print(f"  {n}")
    else:
        abs_path.write_text(new_source)

    return notes


def main():
    p = argparse.ArgumentParser(
        description="Migrate all api.resend.com/emails calls to SMTP helper"
    )
    p.add_argument("--dry-run", action="store_true", help="Preview changes only")
    p.add_argument("--file", type=str, default="",
                    help="Migrate a single file (by path substring, e.g. 'hub' or 'fee_collection')")
    args = p.parse_args()

    total_files = 0
    total_notes = []

    # 1) Extend SMTP helper
    print("=== Step 1: Extend SMTP helper ===")
    smtp_notes = extend_smtp_helper(args.dry_run)
    for n in smtp_notes:
        print(f"  {n}")
    total_notes.extend(smtp_notes)

    # 2) Migrate email-sending files
    print("\n=== Step 2: Migrate email-sending files ===")
    for rel_path, migrator in MIGRATIONS:
        if args.file and args.file not in rel_path:
            continue
        notes = migrate_file(rel_path, migrator, args.dry_run)
        for n in notes:
            print(f"  [{rel_path}] {n}")
        if any("Migrated" in n or "FILE NOT FOUND" in n for n in notes):
            total_files += 1
        total_notes.extend(notes)

    # 3) Report files NOT migrated
    print("\n=== Step 3: Files NOT migrated (domain checks, not email) ===")
    for f in DOMAIN_CHECK_FILES:
        if args.file and args.file not in f:
            continue
        if (REPO / f).exists():
            print(f"  ⏭  {f} — uses api.resend.com/domains (not email sending)")
        else:
            print(f"  ⏭  {f} — not found (moved?)")
        total_files += 1

    # 4) Report files needing manual attention (attachments)
    if not args.file or "payment_report" in args.file:
        print("\n=== Step 4: Files needing manual attention ===")
        print("  ⚠️  scripts/send_payment_report.py — uses PDF attachments")
        print("      SMTP helper doesn't support attachments yet.")
        print("      Either extend SMTP helper or keep the Resend API call for this file.")
        print(f"      Current: keeps Resend API call (not migrated)")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Migration {'preview' if args.dry_run else 'complete'} for {total_files} files")
    print(f"Total notes: {len(total_notes)}")
    print(f"{'DRY RUN — no files changed' if args.dry_run else 'Files updated'}")

    if not args.dry_run and not args.file:
        print("\nNext steps:")
        print("  1. Verify each file with: python3 -c \"import ast; ast.parse(open('<file>').read()); print('OK')\"")
        print("  2. Run: python3 scripts/helpers/smtp_email.py  (verify SMTP still works)")
        print("  3. Run: python3 -m agents.system_supervisor --no-tg --json | grep resend (verify domain checks still work)")


if __name__ == "__main__":
    main()
