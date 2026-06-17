"""
EMPIRE AI · AUTORESEARCH · prepare.py (buyer target)
====================================================
Loads B2B reply data and scores candidate email bodies.
DO NOT MODIFY.
"""
import os
import re
import json
from datetime import datetime, timezone, timedelta

# Load env
data = open("/root/.env").read()
for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)="(.*?)"(?=\n[A-Z_]|\n#|\n\n|$)', data, re.MULTILINE | re.DOTALL):
    os.environ[m.group(1)] = m.group(2)
for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)=([^\n#"]+)$', data, re.MULTILINE):
    k = m.group(1)
    if k not in os.environ:
        os.environ[k] = m.group(2).strip()

from supabase import create_client
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Spam triggers for HTML email
SPAM_TRIGGERS = [
    r"\bFREE\b", r"!!!", r"\$\$\$", r"GUARANTEED", r"ACT NOW",
    r"CLICK HERE", r"BUY NOW", r"LIMITED TIME", r"URGENT\b",
    r"100%\s*FREE", r"RISK[- ]FREE", r"NO OBLIGATION", r"MAKE MONEY FAST",
]


def load_buyer_replies():
    """Load B2B buyer outreach replies from inbox_messages.
    Returns: list of dicts with from_address, body, intent, received_at.
    """
    all_msgs = []
    offset = 0
    while True:
        r = sb.table("inbox_messages").select("from_address,body,classified_intent,received_at,meta").eq("channel", "email").range(offset, offset+1000).execute()
        rows = r.data or []
        if not rows: break
        # Only the B2B lane ones
        for row in rows:
            meta = row.get("meta") or {}
            if meta.get("campaign") == "affiliate_recruiter (affiliate program, 10% commission)":
                all_msgs.append(row)
        if len(rows) < 1000: break
        offset += 1000
    return all_msgs


def historical_buyer_reply_rate() -> float:
    """% of B2B outreach that got a reply classified as interested/question."""
    replies = load_buyer_replies()
    positive = [m for m in replies if m.get("classified_intent") in ("interested", "question")]
    # Total sent: 53 per cycle × N cycles. We don't track total sent for B2B,
    # so use a conservative assumption: 53 unique recipients per cycle
    # × 1 cycle today = 53 sent. The 1 interested reply = 1.85%.
    sent = 53
    if not positive: return 0.0
    return 100.0 * len(positive) / sent


def spam_score_html(body: str) -> float:
    """Return 0-100 (lower = more spammy)."""
    if not body: return 0.0
    # Strip HTML tags for spam check
    text = re.sub(r"<[^>]+>", " ", body)
    score = 100.0
    for pattern in SPAM_TRIGGERS:
        if re.search(pattern, text):
            score -= 25
    # Heavy emoji use
    emoji_count = sum(1 for c in text if ord(c) > 0x2700)
    if emoji_count >= 3:
        score -= 20
    return max(0.0, score)


def subject_score(subject: str) -> float:
    """Score the email subject. Best practice: 30-80 chars, no spam."""
    if not subject: return 0.0
    score = 100.0
    n = len(subject)
    if 30 <= n <= 80: pass
    elif 20 <= n < 30 or 80 < n <= 100: score -= 20
    elif 10 <= n < 20 or 100 < n <= 150: score -= 50
    else: score -= 100
    # Spam in subject is worse
    text = subject.upper()
    if "FREE" in text or "$$$" in text or "!!!" in text:
        score -= 50
    if re.search(r"^[A-Z\s]{20,}$", subject):
        score -= 30  # all caps
    return max(0.0, score)


def personalization_score(body_html: str, name: str = "") -> float:
    """Higher = uses a personalized greeting."""
    if not body_html: return 0.0
    score = 0.0
    # Check for the rendered personalized greeting: "<strong>Name</strong>"
    if re.search(r"<strong>[^<]+</strong>", body_html):
        score += 100.0
    return score


def cta_score(body_html: str) -> float:
    """Has a clear call-to-action (a link/button with the referral URL)."""
    if not body_html: return 0.0
    score = 0.0
    # Look for either the placeholder or the rendered link
    if ("referral_url" in body_html or "empire-ai.co.uk" in body_html) and "<a" in body_html:
        score += 50.0
    if ("dashboard_url" in body_html or "affiliate/dashboard" in body_html) and "<a" in body_html:
        score += 25.0
    if "Sign up" in body_html or "Get started" in body_html or "Start sharing" in body_html:
        score += 25.0
    return min(100.0, score)


def length_score_html(body_html: str) -> float:
    """200-2000 chars is the sweet spot. Penalty outside."""
    if not body_html: return 0.0
    text = re.sub(r"<[^>]+>", "", body_html)
    n = len(text)
    if 200 <= n <= 2000: return 0.0
    if 100 <= n < 200 or 2000 < n <= 3000: return 20.0
    if 50 <= n < 100 or 3000 < n <= 5000: return 50.0
    return 100.0


def score_body(subject: str, body_html: str, name: str = "") -> dict:
    spam = spam_score_html(body_html)
    subj = subject_score(subject)
    pers = personalization_score(body_html, name)
    cta = cta_score(body_html)
    length = length_score_html(body_html)
    base_rate = historical_buyer_reply_rate() or 1.85
    return {
        "subject":     subject,
        "body":        body_html,
        "spam_score":  spam,
        "subject_score": subj,
        "personalization_score": pers,
        "cta_score":   cta,
        "length_penalty": length,
        "reply_rate":  base_rate,
        # Weighted: prioritize reply rate + cta + personalization
        "weighted":    0.5 * base_rate
                     + 0.15 * spam
                     + 0.10 * subj
                     + 0.10 * pers
                     + 0.10 * cta
                     - 0.05 * length,
    }


def write_result(row: dict, path: str = "results.tsv"):
    """Append a result row to results.tsv."""
    import csv
    fields = ["timestamp", "subject", "body", "spam_score", "subject_score",
              "personalization_score", "cta_score", "length_penalty", "reply_rate",
              "weighted", "kept", "note"]
    file_exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        if not file_exists:
            w.writeheader()
        row_to_write = {k: row.get(k, "") for k in fields}
        row_to_write["timestamp"] = row.get("timestamp", datetime.now(timezone.utc).isoformat())
        w.writerow(row_to_write)
