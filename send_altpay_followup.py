"""
Send Alt-Pay (James Stamatis) follow-up reply + sample OKC lead.
Run after midnight UTC when the Resend daily quota (100/day) resets.

Usage:
    python3 send_altpay_followup.py
"""

import os
import httpx
import json
import asyncio
from dotenv import load_dotenv

load_dotenv("/root/.env")


ALT_PAY_CONTACT = {
    "name": "James Stamatis",
    "email": "jstamatis@alt-pay.net",
    "company": "Alt-Pay",
    "phone": "405-226-6550",
    "address": "3000 United Founders Blvd, Suite 139D, Oklahoma City, OK 73112",
}


SAMPLE_LEAD = {
    "business_name": "Schraad Sales & Marketing",
    "contact_name": "Patrick Thompson",
    "contact_email": "patrick.thompson@schraadinc.com",
    "contact_phone": "+1 (405) 528-3327",
    "address": "10 NW 6th St, Oklahoma City, OK 73102",
    "metro": "Oklahoma City",
    "state": "OK",
    "biz_type": "Sales & Marketing Firm",
    "why_qualifies": (
        "B2B sales firm processing client invoices and payments. "
        "Likely needs merchant services for credit card acceptance, "
        "Level 3 processing for B2B transactions, and potential POS integration. "
        "Established business with a physical office in downtown OKC."
    ),
    "verification_status": "Phone-verified · Address-confirmed · Contact-name identified",
    "intent_signals": "Active business · Regular invoice/payment cycle · B2B payment processing need",
}


REPLY_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,system-ui,'Helvetica Neue',sans-serif;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#0a0a0a;">
<tr><td align="center" style="padding:32px 16px;">
  <table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background:#0a0a0a;color:#e4e4e7;">
    <tr><td style="padding-bottom:18px;border-bottom:1px solid #27272a;">
      <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · B2B Lead Network</div>
    </td></tr>
    <tr><td style="padding:24px 0;">
      <p style="font-size:14px;line-height:1.7;color:#e4e4e7;margin:0 0 14px;">Hi James,</p>
      <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">Thanks for the reply. Glad to connect.</p>

      <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
        A bit about how we work: Empire AI operates a predictive lead generation network that
        identifies businesses actively seeking merchant services. We verify contact information
        and deliver qualified leads directly to you. Our model is zero-risk — no upfront cost,
        no retainer. We earn 3% only when you close the deal.
      </p>

      <div style="margin:24px 0;padding:18px 20px;background:#15263F;border-left:3px solid #44E5B8;font-size:13px;color:#c8d4e4;line-height:1.7;">
        <strong style="color:#f8fafd;">Sample Lead — Oklahoma City:</strong><br><br>
        <strong style="color:#f8fafd;">Schraad Sales & Marketing</strong><br>
        Contact: Patrick Thompson · patrick.thompson@schraadinc.com · (405) 528-3327<br>
        Address: 10 NW 6th St, Oklahoma City, OK 73102<br><br>
        <strong>Why they qualify:</strong> B2B sales firm processing client invoices and payments.
        Likely needs merchant services for card acceptance and Level 3 processing.
        Phone-verified, address-confirmed, contact name identified.
      </div>

      <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
        To make sure we're targeting the right prospects for Alt-Pay, could you let me know:
      </p>
      <ol style="font-size:14px;line-height:1.8;color:#a1a1aa;margin:0 0 14px;padding-left:20px;">
        <li>What's your ideal customer profile? (retail, e-commerce, high-risk, B2B?)</li>
        <li>Any specific verticals you're focused on right now?</li>
        <li>What geographic areas do you cover?</li>
      </ol>

      <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
        Happy to hop on a quick call if that's easier. I can send more leads matching your
        exact profile once we dial in the criteria.
      </p>

      <p style="font-size:14px;line-height:1.7;color:#e4e4e7;margin:24px 0 0;">Best,<br>Phil<br>Empire AI · phil@empire-ai.co.uk</p>
    </td></tr>
    <tr><td style="padding-top:24px;border-top:1px solid #27272a;font-size:11px;color:#71717a;line-height:1.7;">
      Empire AI Ltd · United Kingdom<br>
      You are receiving this because you replied to our earlier outreach about B2B lead generation.
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""


async def send():
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        print("ERROR: RESEND_API_KEY not found in /root/.env")
        return

    # First check if we're within quota
    async with httpx.AsyncClient() as client:
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
            return

        print("Quota available. Sending to Alt-Pay...")

        # Send the real email
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
                print(r.text[:500])


if __name__ == "__main__":
    asyncio.run(send())
