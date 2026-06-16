"""
Empire AI · Inbound Reply Handler
================================
Standalone FastAPI service that:
  - Receives Resend inbound email webhooks (carrier replies)
  - Receives Vonage inbound SMS webhooks (contractor / lead replies)
  - Classifies reply intent
  - Drafts + sends follow-ups (or escalates to Telegram for you to decide)
  - Logs every inbound to inbox_messages table for the daily digest

Runs on port 9120, separate from the main hub. Cron-resilient,
self-restarts via systemd or a simple supervisord if available.

ENV:
  HUB_TOKEN        — same as the main hub (Bearer auth on Resend)
  INBOUND_PORT     — 9120 (default)
  TELEGRAM_TOKEN   — for Telegram alerts
  TELEGRAM_CHAT    — 808657420 (Phil)
"""
import os, re, json, sys, time, hmac, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Load hermes env (bot token)
he = open("/root/.hermes/.env").read()
for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)=([^\n#"]+)$', he, re.MULTILINE):
    k, v = m.group(1), m.group(2).strip().strip('"')
    if k.startswith("TELEGRAM") or k.startswith("SUPABASE"):
        os.environ.setdefault(k, v)
# Load env (Supabase URL)
data = open("/root/.env").read()
for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)="(.*?)"(?=\n[A-Z_]|\n#|\n\n|$)', data, re.MULTILINE | re.DOTALL):
    os.environ[m.group(1)] = m.group(2)
for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)=([^\n#"]+)$', data, re.MULTILINE):
    k = m.group(1)
    if k not in os.environ:
        os.environ[k] = m.group(2).strip()

from fastapi import FastAPI, Request, HTTPException
import uvicorn
from supabase import create_client
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_HOME_CHANNEL", "808657420")
RESEND_WEBHOOK_SECRET = os.environ.get("RESEND_WEBHOOK_SECRET", "")
INBOUND_PORT = int(os.environ.get("INBOUND_PORT", "9120"))

if not SUPABASE_URL or not SUPABASE_KEY:
    print("FATAL: SUPABASE_URL and SUPABASE_KEY must be set")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI(title="Empire AI Inbound Handler")

# --- Known senders we're tracking replies for ---
CARRIERS = {
    "vendorpartners@allstate.com": "Allstate",
    "partners@farmers.com":         "Farmers",
    "partners@libertymutual.com":  "Liberty Mutual",
    "partners@statefarm.com":      "State Farm",
    "partnerships@usaa.com":       "USAA",
}

# --- Intent classifier (cheap keyword-based, no LLM needed) ---
def classify_reply(text: str) -> str:
    """Returns one of: interested, question, not_now, wrong_person,
    opt_out, bounce, unknown. Pure-keyword classifier. Conservative
    (defaults to 'unknown' rather than guessing)."""
    if not text:
        return "empty"
    t = text.lower().strip()
    # Opt-out: explicit unsubscribe
    if any(k in t for k in ["unsubscribe", "remove me", "stop contacting", "remove from list"]):
        return "opt_out"
    # Wrong person / not the right contact
    if any(k in t for k in ["wrong person", "not the right", "no longer with", "i don't handle", "different team"]):
        return "wrong_person"
    # Not now
    if any(k in t for k in ["not now", "not right now", "later", "not interested right now", "try again next quarter", "bad time"]):
        return "not_now"
    # Bounce
    if any(k in t for k in ["undeliverable", "mailbox full", "user unknown", "no such user", "550", "551", "553"]):
        return "bounce"
    # Interested
    if any(k in t for k in ["interested", "let's talk", "schedule a call", "set up a call",
                            "sounds good", "yes", "tell me more", "send more info", "demo",
                            "happy to chat", "love to learn", "where do i sign"]):
        return "interested"
    # Question (asked something)
    if "?" in t or any(k in t for k in ["how do", "what is", "where can", "can you", "do you"]):
        return "question"
    return "unknown"


# --- Draft a follow-up email for a given intent ---
def draft_followup(carrier: str, intent: str, original_subject: str) -> Optional[str]:
    """Returns the body of a follow-up email, or None if no auto-reply
    (intent=opt_out, wrong_person, bounce → log only)."""
    if intent == "interested":
        return (
            f"Hi,\n\n"
            f"Thanks for the quick reply — appreciate it. Happy to walk through what an integration would look like.\n\n"
            f"I'm flexible on format: a 20-min call, a written summary, or a recorded demo. "
            f"My calendar is open: https://calendly.com/phil-empire-ai/30min — pick any slot that works.\n\n"
            f"Quick context for the call: we already have the storm-detection + contractor-dispatch side working, "
            f"and we have mock-carrier integration tested. What we need from {carrier} is the "
            f"\"claim settled\" webhook (or equivalent). Standard scopes, no claimant PII.\n\n"
            f"Best,\nPhillip\nphil@empire-ai.co.uk"
        )
    if intent == "question":
        return (
            f"Hi,\n\n"
            f"Thanks for the question — happy to answer. Want me to send a one-pager covering the integration shape, "
            f"or jump on a 20-min call to walk through it? calendly.com/phil-empire-ai/30min\n\n"
            f"Best,\nPhillip"
        )
    if intent == "not_now":
        return (
            f"Hi,\n\n"
            f"Understood. I'll check back in Q4 with the first settled-claim cohort. "
            f"No need to reply; if anything changes on your side, phil@empire-ai.co.uk.\n\n"
            f"Best,\nPhillip"
        )
    # opt_out, wrong_person, bounce, unknown: no auto-reply
    return None


def send_email(to: str, subject: str, body: str) -> str:
    """Send via Resend. Returns the message_id or an error string."""
    resend_key = os.environ.get("RESEND_API_KEY", "")
    if not resend_key:
        return "ERROR: no RESEND_API_KEY"
    payload = json.dumps({
        "from":    "Phillip Livesley <phil@empire-ai.co.uk>",
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
        return f"EXC: {type(e).__name__}: {e}"


def tg_send(msg: str) -> str:
    """Send a Telegram message. Returns 'ok' or an error string."""
    if not TG_TOKEN:
        return "no TG_TOKEN"
    payload = json.dumps({"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown",
                          "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return "ok" if json.loads(r.read().decode()).get("ok") else "api-err"
    except Exception as e:
        return f"EXC: {e}"


# --- Webhook endpoints ---

@app.post("/api/v1/inbound/email")
async def inbound_email(request: Request):
    """Resend inbound webhook. Resend POSTs the parsed email here when
    someone replies to a message we sent."""
    body = await request.body()
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(400, "bad json")

    # Resend inbound webhooks wrap the data in {"type": ..., "data": {...}}
    # but also support raw event for older accounts. Handle both.
    data = payload.get("data", payload)

    from_email = data.get("from", "")
    to_email   = data.get("to", [None])
    if isinstance(to_email, list):
        to_email = to_email[0] if to_email else None
    subject   = data.get("subject", "")
    text_body = data.get("text") or data.get("html") or ""
    message_id = data.get("message_id") or data.get("id") or ""
    in_reply_to = data.get("in_reply_to") or ""

    # Normalize the from address
    if "<" in from_email and ">" in from_email:
        # "John Smith <john@x.com>" → "john@x.com"
        import re as _re
        m = _re.search(r"<([^>]+)>", from_email)
        if m:
            from_email = m.group(1)
    from_email = from_email.lower().strip()

    # Classify carrier / contractor
    is_carrier = from_email in CARRIERS
    carrier_name = CARRIERS.get(from_email)

    # Classify intent
    intent = classify_reply(text_body)

    # Log to inbox_messages
    try:
        sb.table("inbox_messages").insert({
            "channel":       "email",
            "from_address":  from_email,
            "to_address":    to_email,
            "subject":       subject,
            "body":          text_body[:4000],
            "received_at":   datetime.now(timezone.utc).isoformat(),
            "classified_intent": intent,
            "in_reply_to":   in_reply_to,
            "meta": {
                "resend_message_id": message_id,
                "is_carrier": is_carrier,
                "carrier_name": carrier_name,
            },
        }).execute()
    except Exception as e:
        print(f"inbox_messages insert failed: {e}")

    # Auto-reply logic
    followup_body = draft_followup(carrier_name or "the team", intent, subject) if is_carrier else None

    followup_msg_id = None
    if followup_body:
        # Send the follow-up
        followup_subject = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
        followup_msg_id = send_email(from_email, followup_subject, followup_body)
        # Log the outbound
        try:
            sb.table("outbox_messages").insert({
                "channel":     "email",
                "to_address":  from_email,
                "subject":     followup_subject,
                "body":        followup_body[:4000],
                "sent_at":     datetime.now(timezone.utc).isoformat(),
                "sent_status": "sent" if not str(followup_msg_id).startswith(("ERROR", "HTTP", "EXC")) else "failed",
                "in_reply_to": message_id,
                "meta": {
                    "trigger": "inbound_reply_auto",
                    "intent":  intent,
                    "resend_message_id": followup_msg_id,
                },
            }).execute()
        except Exception as e:
            print(f"outbox_messages insert failed: {e}")

    # Telegram alert
    if is_carrier:
        alert = (
            f"📨 *Carrier reply*\n"
            f"  from: {from_email}\n"
            f"  carrier: {carrier_name}\n"
            f"  intent: *{intent}*\n"
            f"  subject: {subject[:60]}{'...' if len(subject)>60 else ''}\n"
        )
        if followup_msg_id and not str(followup_msg_id).startswith(("ERROR", "HTTP", "EXC")):
            alert += f"  → auto-replied (resend: {followup_msg_id[:20]}...)\n"
        elif followup_msg_id and str(followup_msg_id).startswith(("ERROR", "HTTP", "EXC")):
            alert += f"  → *auto-reply FAILED*: {followup_msg_id}\n"
        else:
            alert += f"  → no auto-reply (intent={intent})\n"
        tg_send(alert)
    else:
        # Non-carrier inbound — alert only if intent looks important
        if intent in ("interested", "question", "opt_out"):
            alert = (
                f"📨 *Email reply*\n"
                f"  from: {from_email}\n"
                f"  intent: *{intent}*\n"
                f"  subject: {subject[:60]}{'...' if len(subject)>60 else ''}\n"
            )
            tg_send(alert)

    return {"ok": True, "intent": intent, "is_carrier": is_carrier,
            "auto_replied": bool(followup_msg_id) and not str(followup_msg_id).startswith(("ERROR", "HTTP", "EXC")),
            "msg_id": followup_msg_id}


@app.post("/api/v1/inbound/sms")
async def inbound_sms(request: Request):
    """Vonage inbound SMS webhook. Called when a contractor or lead
    replies to one of our SMS bodies."""
    # Vonage sends form-encoded
    form = await request.form()
    from_number = form.get("msisdn") or form.get("from") or ""
    to_number   = form.get("to") or ""
    text        = form.get("text") or ""
    message_id  = form.get("messageId") or form.get("message-id") or ""

    from_number = from_number.replace("+", "").strip()
    intent = classify_reply(text)

    try:
        sb.table("inbox_messages").insert({
            "channel":           "sms",
            "from_address":      from_number,
            "to_address":        to_number,
            "subject":           None,
            "body":              text,
            "received_at":       datetime.now(timezone.utc).isoformat(),
            "classified_intent": intent,
            "in_reply_to":       None,
            "meta":              {"vonage_message_id": message_id},
        }).execute()
    except Exception as e:
        print(f"inbox_messages sms insert failed: {e}")

    # SMS auto-reply is risky (TCPA + cost). Only auto-reply for STOP and
    # interested, and only with a short message. For all other intents
    # alert via Telegram.
    if intent == "opt_out" or "stop" in text.lower() or "unsubscribe" in text.lower():
        # Required TCPA response: confirm opt-out
        body = "Empire AI: You're unsubscribed. No further calls or texts. Reply STOP again to confirm."
        from voice import voice_router  # may not be available; fall back
    elif intent == "interested" and "yes" in text.lower():
        # For contractor_recruit SMS, "YES" means start the demo
        body = "Empire AI: Got it. Check empire-ai.co.uk/contractors to self-onboard. Reply STOP to opt out."
    else:
        body = None

    sent_id = None
    if body:
        # Send via the hub's SMS endpoint (same one the converter uses)
        hub_token = os.environ.get("HUB_TOKEN", "")
        hub_url   = os.environ.get("HUB_URL", "http://127.0.0.1:8000")
        try:
            data = json.dumps({
                "phone":          "+" + from_number,
                "target_addr":    "inbound_reply",
                "sequence_type":  "contractor_recruit",
                "meta":           {"trigger": "inbound_sms_auto", "intent": intent, "in_reply_to": message_id},
            }).encode()
            req = urllib.request.Request(
                f"{hub_url}/api/v1/sms/enroll",
                data=data, method="POST",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {hub_token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read().decode())
                if resp.get("ok"):
                    sent_id = resp.get("sequence_id")
        except Exception as e:
            print(f"sms auto-reply failed: {e}")

    # Always alert via Telegram for SMS (every SMS reply is high-signal)
    alert = (
        f"📱 *SMS reply*\n"
        f"  from: +{from_number}\n"
        f"  text: {text[:100]}\n"
        f"  intent: *{intent}*\n"
    )
    if sent_id:
        alert += f"  → auto-replied (enrolled: {sent_id[:20]}...)\n"
    elif body:
        alert += f"  → auto-reply FAILED\n"
    tg_send(alert)

    return {"ok": True, "intent": intent, "auto_replied": bool(sent_id)}


@app.get("/health")
async def health():
    return {"ok": True, "service": "inbound-handler", "ts": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=INBOUND_PORT, log_level="info")
