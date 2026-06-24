"""
Empire AI · SMTP Email Helper
================================
Sends emails via SMTP (smtp.resend.com) instead of the Resend REST API.
Uses STARTTLS on port 587 for encryption.

Usage:
    from scripts.helpers.smtp_email import send_smtp_email

    result = send_smtp_email(
        to="contractor@example.com",
        subject="Hello",
        html="<p>Hi there</p>",
    )
    if result["ok"]:
        print(f"Sent: {result['message_id']}")
    else:
        print(f"Failed: {result['error']}")
"""

import os
import re
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from dotenv import load_dotenv

load_dotenv("/root/.env", override=True)

log = logging.getLogger("smtp_email")

SMTP_HOST = "smtp.resend.com"
SMTP_PORT = 587  # STARTTLS
SMTP_USER = "resend"  # Resend SMTP username is always "resend"
SMTP_PASSWORD = os.environ.get("RESEND_API_KEY", "")
FROM_ADDR = os.environ.get("FROM_ADDRESS", "ops@empire-ai.co.uk")
FROM_NAME = os.environ.get("FROM_NAME", "Empire AI")


def _build_message(to: str, subject: str, html: str, text: Optional[str] = None) -> str:
    """Build a multipart/alternative MIME message with HTML and optional text."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{FROM_NAME} <{FROM_ADDR}>"
    msg["To"] = to
    msg["Subject"] = subject

    # Plain text fallback
    if text:
        msg.attach(MIMEText(text, "plain"))
    else:
        # Strip tags for a rough plain-text version
        plain = re.sub(r"<[^>]+>", "", html)
        plain = re.sub(r"\n{3,}", "\n\n", plain)
        msg.attach(MIMEText(plain.strip(), "plain"))

    # HTML version
    msg.attach(MIMEText(html, "html"))

    return msg.as_string()


def send_smtp_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    timeout: int = 30,
) -> dict:
    """Send an email via SMTP (Resend).

    Uses STARTTLS on port 587 with the Resend SMTP relay.
    Returns {ok, message_id} on success, {ok, error} on failure.
    """
    if not SMTP_PASSWORD:
        return {"ok": False, "error": "RESEND_API_KEY not set in environment"}

    if not to or not subject or not html:
        return {"ok": False, "error": "Missing required fields: to, subject, html"}

    try:
        msg_text = _build_message(to, subject, html, text)

        context = ssl.create_default_context()

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=timeout) as server:
            server.ehlo()
            # Upgrade to STARTTLS
            server.starttls(context=context)
            server.ehlo()
            # Login with Resend SMTP credentials
            server.login(SMTP_USER, SMTP_PASSWORD)
            # Send
            result = server.sendmail(FROM_ADDR, [to], msg_text)

        if result:
            # sendmail returns a dict of failed recipients
            return {"ok": False, "error": f"Delivery failed for: {result}"}

        return {"ok": True, "message_id": f"smtp:{to}"}

    except smtplib.SMTPAuthenticationError as e:
        log.error(f"SMTP auth failed: {e}")
        return {"ok": False, "error": f"SMTP authentication failed — check RESEND_API_KEY"}
    except smtplib.SMTPException as e:
        log.error(f"SMTP error: {e}")
        return {"ok": False, "error": f"SMTP error: {e}"}
    except (TimeoutError, ConnectionError) as e:
        log.error(f"SMTP connection failed: {e}")
        return {"ok": False, "error": f"SMTP connection failed: {e}"}
    except Exception as e:
        log.error(f"Unexpected SMTP error: {e}")
        return {"ok": False, "error": f"Unexpected error: {e}"}


def test_smtp_config() -> dict:
    """Test the SMTP configuration by connecting and authenticating.

    Does NOT send an email — just verifies the connection works.
    Returns {ok} or {ok, error}.
    """
    if not SMTP_PASSWORD:
        return {"ok": False, "error": "RESEND_API_KEY not set"}

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.quit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    result = test_smtp_config()
    if result["ok"]:
        print("✅ SMTP connection and authentication successful")
    else:
        print(f"❌ SMTP test failed: {result.get('error', 'unknown')}")
