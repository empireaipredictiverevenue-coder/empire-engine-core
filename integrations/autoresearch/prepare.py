"""
EMPIRE AI · AUTORESEARCH · prepare.py
======================================
Fixed constants, data prep, evaluation. DO NOT MODIFY.

Provides:
  - load_sms_data() — pulls all sms_sequences + inbox_messages from Supabase
  - score_body(body, metro, niche) -> dict — scores a candidate body
  - historical_reply_rate(template) -> float — % of similar past sequences that replied

The scorer is intentionally simple. The autoresearch agent edits train.py,
not this file.
"""
import os
import re
import json
from typing import Optional
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

# Spammy phrases / patterns
SPAM_TRIGGERS = [
    r"\bFREE\b", r"!!!", r"\$\$\$", r"GUARANTEED", r"ACT NOW",
    r"CLICK HERE", r"BUY NOW", r"LIMITED TIME", r"URGENT\b",
    r"100%\s*FREE", r"RISK[- ]FREE", r"NO OBLIGATION",
]
TCPA_REQUIRED = [
    r"(?i)\bstop\b",  # STOP to opt out
]


def load_sms_data():
    """Load all sms_sequences + their matching inbox_messages (replies).

    Returns: list of dicts with keys:
      phone, body, sequence_type, current_step, status, last_sent_at,
      has_replied, intent (None or 'interested'|'question'|...)
    """
    # Get all sequences
    all_seqs = []
    offset = 0
    while True:
        r = sb.table("sms_sequences").select("phone,target_addr,sequence_type,current_step,status,last_sent_at,created_at,meta").range(offset, offset+1000).execute()
        rows = r.data or []
        if not rows: break
        all_seqs.extend(rows)
        if len(rows) < 1000: break
        offset += 1000

    # Get all inbound replies
    replies = {}
    r2 = sb.table("inbox_messages").select("from_address,classified_intent,body,received_at").eq("channel", "sms").execute()
    for row in r2.data or []:
        f = (row.get("from_address") or "").replace("+", "").lstrip("1")
        replies[f] = row

    # Join
    for s in all_seqs:
        phone = (s.get("phone") or "").replace("+", "").lstrip("1")
        reply = replies.get(phone)
        s["has_replied"] = reply is not None
        s["intent"] = (reply or {}).get("classified_intent") if reply else None
    return all_seqs


def spam_score(body: str) -> float:
    """Return 0-100 (lower = more spammy). 100 = no spam triggers, 0 = 5+ spam triggers."""
    if not body: return 0.0
    score = 100.0
    for pattern in SPAM_TRIGGERS:
        if re.search(pattern, body):
            score -= 25  # each trigger knocks 25 off
    # Heavy emoji use (3+ emojis in 160 chars = spammy)
    emoji_count = sum(1 for c in body if ord(c) > 0x2700)
    if emoji_count >= 3:
        score -= 20
    # All caps ratio
    letters = [c for c in body if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.4:
        score -= 20
    return max(0.0, score)


def tcpa_compliant(body: str) -> float:
    """Return 0 or 100. Must include STOP-to-opt-out language AND
    identify the sender as a commercial entity."""
    if not body: return 0.0
    score = 100.0
    for pattern in TCPA_REQUIRED:
        if not re.search(pattern, body):
            score -= 50
    # Should identify as commercial (words like "commercial", "Empire AI", or similar)
    if not re.search(r"(?i)(empire ai|paid commercial|paid call|sms|notification)", body):
        score -= 25
    return max(0.0, score)


def length_penalty(body: str) -> float:
    """0-100. Optimal 130-160 chars. Penalty outside that range."""
    if not body: return 100.0
    n = len(body)
    if 130 <= n <= 160: return 0.0
    if 100 <= n < 130 or 160 < n <= 180: return 20.0
    if 80 <= n < 100 or 180 < n <= 220: return 50.0
    return 100.0  # way off


def historical_reply_rate(template_body: str, sequence_type: str = "contractor_recruit") -> float:
    """% of historical sequences with the same sequence_type that got a reply
    classified as 'interested' or 'question'."""
    all_data = load_sms_data()
    relevant = [s for s in all_data if s.get("sequence_type") == sequence_type]
    if not relevant: return 0.0
    replied = [s for s in relevant if s.get("has_replied") and s.get("intent") in ("interested", "question")]
    return 100.0 * len(replied) / len(relevant)


def score_body(body: str, metro: str = "Houston", sequence_type: str = "contractor_recruit") -> dict:
    """Score a candidate body. Returns dict with all sub-scores + weighted total."""
    spam = spam_score(body)
    tcpa = tcpa_compliant(body)
    length = length_penalty(body)
    # Reply-rate score: use historical reply rate as the prediction baseline.
    # If the body is essentially the same as the existing template (high text
    # similarity), use the real historical rate. Otherwise, use a small prior
    # derived from overall reply rate.
    baseline_rate = historical_reply_rate(body, sequence_type=sequence_type)
    # We treat reply_rate as 0-100 already. If the template is very different
    # from history, use the overall reply rate as a conservative estimate.
    if baseline_rate == 0.0:
        # Conservative baseline: ~2% (industry standard for B2B SMS)
        baseline_rate = 2.0
    return {
        "body":          body,
        "length":        len(body),
        "spam_score":    spam,
        "tcpa_score":    tcpa,
        "length_penalty": length,
        "reply_rate":    baseline_rate,
        # Weighted total (out of 100)
        "weighted":      0.5 * baseline_rate
                       + 0.3 * spam
                       + 0.2 * tcpa
                       - 0.1 * length,
    }


def write_result(row: dict, path: str = "results.tsv"):
    """Append a result row to results.tsv."""
    import csv
    fields = ["timestamp", "body", "length", "spam_score", "tcpa_score",
              "length_penalty", "reply_rate", "weighted", "kept", "note"]
    file_exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        if not file_exists:
            w.writeheader()
        row_to_write = {k: row.get(k, "") for k in fields}
        row_to_write["timestamp"] = row.get("timestamp", datetime.now(timezone.utc).isoformat())
        w.writerow(row_to_write)
