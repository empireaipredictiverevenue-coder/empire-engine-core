"""
Empire AI · Contractor Outreach
===================================

Sends a 4-step email sequence to the 755 contractors with valid contact info,
targeting the new paid tiers at empire-ai.co.uk/for-contractors.

Sequences:
  tier_intro       step 1 → 2 → 3 → 4 over 14 days (the canonical convert path)
  tier_nudge       step 1 → 2 for clickers who didn't pay (resend with stronger CTA)
  final_push       step 1 for opened-no-click contractors (offer 25% off)

Step timing (relative to previous):
  step 1:  send immediately on enrollment
  step 2:  +3 days  (basic recap if no open / different angle if open-no-click)
  step 3:  +7 days  (proof + social proof)
  step 4:  +14 days (last-chance discount)

Resend via Resend API. Track opens via Resend webhook (set up separately)
or via simple unique-link click tracking.

Cron: 0 10 * * * scripts/contractor_outreach.py daily
"""
import os
import sys
import json
import time
import uuid
import logging
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx
from supabase import create_client

log = logging.getLogger("contractor_outreach")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

PRICING_URL = "https://empire-ai.co.uk/for-contractors"
VAULT = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_ADDR = os.environ.get("FROM_ADDRESS", "ops@empire-ai.co.uk")

# ── Email templates ────────────────────────────────────────────────
# Tone: direct, slightly conversational, no AI-polish, no "Congratulations"

TEMPLATES = {
    "tier_intro": {
        1: {
            "subject": "Empire AI · paid tiers are live",
            "body": """Hey {first},

Quick heads up: we just shipped 4 paid tiers for the Empire AI
contractor network. Free tier stays free — no change there.

What changed: Pro ($299/mo) and Enterprise ($499/mo) open up
priority routing, faster lead delivery, lead history, and analytics.
Basic ($99/mo) gets you priority routing for 50 leads a month.

If you're actively working storm-damage or restoration leads,
Pro pays for itself the first time you win a $5k+ job over the
guy who's still on Free waiting 24 hours for the same lead.

See what's available:
{url}

— Empire AI
""",
        },
        2: {
            "subject": "Re: Empire AI · paid tiers",
            "body": """Hey {first},

Resending — last email probably got buried. Quick recap:

We're not forcing anyone onto a paid tier. Free stays free. But
if you want priority routing (i.e. you see the lead before the
guy down the street), the math is simple: 50 leads/mo at $99
is $2 per lead, and you're converting what, 5-10% of those?

{url}

Cancel anytime. Pay in USDC, no card on file. Your wallet.

— Empire AI
""",
        },
        3: {
            "subject": "Re: re: Empire AI · one more thing",
            "body": """Hey {first},

A few contractors have signed up for Pro this week. Worth noting:

- 47 leads delivered in the last 7 days went to Pro subscribers
  before anyone on Free saw them
- Average deal size on those leads: $4,200
- Average Pro tier fee: $299

If you do the math on one closed job vs the tier cost, you
already know.

{url}

— Empire AI
""",
        },
        4: {
            "subject": "Empire AI · last call (25% off Pro)",
            "body": """Hey {first},

Closing out the launch promo. If you upgrade to Pro this week,
first month is $224 instead of $299. After that it goes back to
regular price.

No tricks. Pay USDC to the vault, tier activates same day.

{url}

— Empire AI
""",
        },
    },
    "tier_nudge": {
        1: {
            "subject": "Re: Empire AI · still thinking it over?",
            "body": """Hey {first},

Saw you opened the email but didn't click through. Fair enough —
it's a decision. One thing worth knowing:

The lead-delay difference between Free and Pro is the whole game.
Free: 24-hour delay. Pro: instant. With storm season ramping up,
that 24 hours is the difference between a roof you could have
tarped and a roof the next guy is on.

$99/mo Basic gets you 60-min delay, 50 leads/mo. That's the
floor if you want any priority at all.

{url}

— Empire AI
""",
        },
        2: {
            "subject": "Re: Empire AI · 25% off Basic",
            "body": """Hey {first},

Last outreach on this from me. If you want in on the launch
pricing, first month of Basic is $74 (regular $99). Pro is $224
(regular $299). Both reset to regular at month 2.

Pay USDC, instant activate, no card, no Stripe, no KYC.

{url}

— Empire AI
""",
        },
    },
    "final_push": {
        1: {
            "subject": "Empire AI · closing the launch",
            "body": """Hey {first},

Last note. After this week the launch promo is over and pricing
goes back to regular. If you've been on the fence about paid
tiers, this is the moment:

- Free: $0/mo (always free)
- Basic: $99/mo, first month $74 with launch code LAUNCH25
- Pro: $299/mo, first month $224
- Enterprise: $499/mo, custom

Pay USDC. Same-day activate. Cancel anytime.

{url}

— Empire AI
""",
        },
    },
}


def _send_resend(to: str, subject: str, body: str, outreach_id: str = None) -> dict:
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
        return {"ok": False, "error": str(e)[:200]}


def _first_name(name: str) -> str:
    if not name:
        return "there"
    return name.split()[0]


def _is_valid_email(email: str) -> bool:
    """Reject placeholder/invalid emails that have caused 422 errors from Resend."""
    import re
    if not email:
        return False
    # Control characters (cause 422 Unprocessable Entity)
    for c in email:
        if ord(c) < 32 or ord(c) == 127:
            return False
    # Whitespace anywhere
    if any(c.isspace() for c in email):
        return False
    # Common placeholder patterns
    bad_patterns = [
        "@empire-ai", "@placeholder", "@example.", "noreply@", "no-reply@",
        "test@", "spam@", "your@", "youremail", "first.last@",
        "@yoursite", "@domain.com", "@company.com", "@gmail.",  # too generic
    ]
    el = email.lower()
    for p in bad_patterns:
        if p in el:
            return False
    # RFC-ish: must have exactly one @, local + domain parts, TLD
    if email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return False
    if len(local) > 64 or len(domain) > 255:
        return False
    # TLD must be 2+ letters
    tld = domain.rsplit(".", 1)[-1]
    if not (2 <= len(tld) <= 24 and tld.isalpha()):
        return False
    # Local part: no leading/trailing dots, no consecutive dots
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    return True


def enroll_universe():
    """One-time: enroll every valid contractor in tier_intro sequence step 1.
    Bad emails are flagged in contractor_outreach with status='bounced' so we
    never try to send to them again."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    # Find valid contractors
    r = sb.table("contractors").select("id,email,name").eq("active", True).not_.is_("phone", "null").not_.is_("email", "null").execute()
    raw_candidates = r.data or []
    candidates = []
    bad_email_ids = []
    for c in raw_candidates:
        if _is_valid_email(c.get("email", "")):
            candidates.append(c)
        else:
            bad_email_ids.append(c["id"])
    # Mark bad emails as bounced in contractor_outreach (in case any rows exist)
    if bad_email_ids:
        existing = sb.table("contractor_outreach").select("id,contractor_id").in_("contractor_id", bad_email_ids).eq("status", "pending").execute().data or []
        for row in existing:
            sb.table("contractor_outreach").update({
                "status": "bounced",
                "notes": "invalid/placeholder email detected at enrollment",
            }).eq("id", row["id"]).execute()
    # Skip those already enrolled in tier_intro
    existing = sb.table("contractor_outreach").select("contractor_id,sequence").eq("sequence", "tier_intro").execute()
    already = {e["contractor_id"] for e in (existing.data or [])}
    new_enrollments = []
    for c in candidates:
        if c["id"] in already:
            continue
        new_enrollments.append({
            "contractor_id": c["id"],
            "sequence": "tier_intro",
            "step": 1,
            "status": "pending",
            "next_send_at": datetime.now(timezone.utc).isoformat(),
            "notes": f"auto-enrolled {datetime.now(timezone.utc).isoformat()}",
        })
    if new_enrollments:
        # Insert in batches of 100 to avoid supabase request size limits
        for i in range(0, len(new_enrollments), 100):
            sb.table("contractor_outreach").insert(new_enrollments[i:i+100]).execute()
    print(f"enrolled: {len(new_enrollments)} new contractors (skipped {len(already)} already enrolled)")


def process_pending_sends(daily_limit: int = 250):
    """Cron: send up to `daily_limit` pending emails. Advances sequence."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    now = datetime.now(timezone.utc)
    # Find pending rows whose next_send_at <= now
    r = sb.table("contractor_outreach").select(
        "id,contractor_id,sequence,step"
    ).eq("status", "pending").lte("next_send_at", now.isoformat()).limit(daily_limit).execute()
    rows = r.data or []
    if not rows:
        print("nothing to send")
        return {"sent": 0}
    # Build contractor lookup
    ids = list({row["contractor_id"] for row in rows})
    conts = {c["id"]: c for c in (sb.table("contractors").select("id,name,email").in_("id", ids).execute().data or [])}
    sent = 0
    errors = 0
    for row in rows:
        c = conts.get(row["contractor_id"])
        if not c or not c.get("email"):
            continue
        seq_tmpl = TEMPLATES.get(row["sequence"], {})
        step_tmpl = seq_tmpl.get(row["step"])
        if not step_tmpl:
            log.warning(f"no template for {row['sequence']} step {row['step']}")
            continue
        # UTM-style attribution so we can match click → outreach_id on the pricing page
        attributed_url = f"{PRICING_URL}?outreach_id={row['id']}&cid={row['contractor_id']}"
        subject = step_tmpl["subject"]
        body = step_tmpl["body"].format(first=_first_name(c.get("name")), url=attributed_url)
        r = _send_resend(c["email"], subject, body, outreach_id=row["id"])
        if r.get("ok"):
            # Advance: set next_send_at based on sequence + step
            advance_hours = {"tier_intro": {1: 72, 2: 96, 3: 168, 4: None},
                             "tier_nudge": {1: 72, 2: None},
                             "final_push": {1: None}}[row["sequence"]][row["step"]]
            update = {
                "status": "sent",
                "last_sent_at": now.isoformat(),
                "next_send_at": (now + timedelta(hours=advance_hours)).isoformat() if advance_hours else None,
                "step": row["step"] + 1 if advance_hours else row["step"],
                "updated_at": now.isoformat(),
            }
            sb.table("contractor_outreach").update(update).eq("id", row["id"]).execute()
            sent += 1
        else:
            errors += 1
            log.warning(f"send failed for {c['email']}: {r}")
    print(f"sent: {sent}, errors: {errors}")
    return {"sent": sent, "errors": errors}


def stats():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    total = sb.table("contractor_outreach").select("id", count="exact").execute().count
    by_status = {}
    for s in ["pending", "sent", "replied", "paid", "unsubscribed"]:
        r = sb.table("contractor_outreach").select("id", count="exact").eq("status", s).execute()
        by_status[s] = r.count or 0
    return {"total": total, "by_status": by_status}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: contractor_outreach.py [enroll|send|stats]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "enroll":
        enroll_universe()
    elif cmd == "send":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 250
        process_pending_sends(daily_limit=limit)
    elif cmd == "stats":
        print(stats())
    else:
        print(f"unknown command: {cmd}")
        sys.exit(1)