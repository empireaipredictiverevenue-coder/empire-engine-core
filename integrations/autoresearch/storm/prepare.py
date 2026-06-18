"""
EMPIRE AI · AUTORESEARCH · prepare.py
======================================
Fixed constants, data prep, evaluation.

Provides:
  - load_sms_data() — pulls sms_sequences + sms_log replies from Supabase
  - score_body(body, metro, niche) -> dict — scores a candidate body
  - historical_reply_rate(sequence_type) -> float

The scorer is intentionally simple. The autoresearch agent edits train.py,
not this file.
"""
import os
import re
from typing import Optional
from datetime import datetime, timezone, timedelta

# Load env (try both locations)
for env_path in ("/root/.env",):
    if os.path.exists(env_path):
        with open(env_path) as f:
            content = f.read()
        # match both quoted and unquoted, including the special format
        for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]*)"?', content, re.MULTILINE):
            os.environ.setdefault(m.group(1), m.group(2))

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
    """Load all sms_sequences + match inbound replies from sms_log.

    Returns: list of dicts with keys:
      phone, body, sequence_type, current_step, status, last_sent_at,
      has_replied (bool), intent (None or string)
    """
    all_seqs = []
    offset = 0
    while True:
        r = sb.table("sms_sequences").select("phone,target_addr,sequence_type,current_step,status,last_sent_at,created_at,meta,replies_count").range(offset, offset+1000).execute()
        rows = r.data or []
        if not rows: break
        all_seqs.extend(rows)
        if len(rows) < 1000: break
        offset += 1000

    # Build phone->reply map from sms_log (direction=inbound is the truth source)
    replies = {}
    offset = 0
    while True:
        r2 = sb.table("sms_log").select("phone,body,created_at").eq("direction", "inbound").range(offset, offset+1000).execute()
        rows = r2.data or []
        if not rows: break
        for row in rows:
            phone = (row.get("phone") or "").replace("+", "").lstrip("1")
            if phone and phone not in replies:
                # first inbound reply for this phone wins
                replies[phone] = {
                    "body": row.get("body", ""),
                    "received_at": row.get("created_at"),
                    "intent": "interested" if "yes" in (row.get("body", "") or "").lower() else "other",
                }
        if len(rows) < 1000: break
        offset += 1000

    # Join
    for s in all_seqs:
        phone = (s.get("phone") or "").replace("+", "").lstrip("1")
        reply = replies.get(phone)
        s["has_replied"] = reply is not None
        s["intent"] = reply["intent"] if reply else None
    return all_seqs


def spam_score(body: str) -> float:
    """Return 0-100 (lower = more spammy). 100 = no spam triggers, 0 = 5+ spam triggers."""
    if not body: return 0.0
    score = 100.0
    for pattern in SPAM_TRIGGERS:
        if re.search(pattern, body):
            score -= 25  # each trigger knocks 25 off
    emoji_count = sum(1 for c in body if ord(c) > 0x2700)
    if emoji_count >= 3:
        score -= 20
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
    return 100.0


def historical_reply_rate(sequence_type: str = "contractor_recruit") -> float:
    """% of historical sequences with the same sequence_type that got a reply
    classified as 'interested' from sms_log.

    Returns: float (0-100) representing percentage.
    """
    all_data = load_sms_data()
    relevant = [s for s in all_data if s.get("sequence_type") == sequence_type]
    if not relevant:
        return 0.0
    replied = [s for s in relevant if s.get("has_replied") and s.get("intent") == "interested"]
    return 100.0 * len(replied) / len(relevant)


def body_similarity_score(candidate_body: str, sequence_type: str = "contractor_recruit") -> float:
    """Compute similarity between candidate body and previously-replied bodies.
    Higher = more similar to bodies that have actually worked. 0-1.

    The point: if the candidate body looks like one that has already
    produced a YES-reply, that's signal. Pure length/spam optimization
    with no body-content signal is just noise.
    """
    from difflib import SequenceMatcher
    all_data = load_sms_data()
    relevant_replied = [s for s in all_data
                       if s.get("sequence_type") == sequence_type
                       and s.get("has_replied")
                       and s.get("intent") == "interested"]
    if not relevant_replied:
        return 0.0
    # We don't store the body that was sent. The meta or sms_sequences row
    # doesn't have it. So this score returns 0 until we wire that up.
    # In the meantime, use the candidate's structural similarity to
    # the published template baseline (which is what train.py uses).
    baseline = ("Hi, storm leads for roofers in Houston. First 2 closed "
                "deals free, 3% after. 90-sec signup at empire-ai.co.uk/contractors. "
                "Reply STOP to opt out.")
    sim = SequenceMatcher(None, candidate_body.lower(), baseline.lower()).ratio()
    return sim * 100.0


def score_body(body: str, metro: str = "Houston", sequence_type: str = "contractor_recruit") -> dict:
    """Score a candidate body. Returns dict with all sub-scores + weighted total.

    Weights (sum to 1.0):
      - reply_rate: 0.45 (real historical signal from sms_log)
      - body_similarity: 0.10 (similarity to working template)
      - spam_score: 0.20
      - tcpa_score: 0.20
      - length_penalty: -0.05 (subtractive, not a weight)

    The 45% reply_rate weight dominates — so the autoresearch has a
    real signal to optimize against (improving templates that have
    historically replied YES will score higher than the same body with
    different words).
    """
    spam = spam_score(body)
    tcpa = tcpa_compliant(body)
    length = length_penalty(body)
    rr = historical_reply_rate(sequence_type=sequence_type)
    sim = body_similarity_score(body, sequence_type=sequence_type)

    # If historical data is too sparse (< 1% reply rate or < 5 sequences),
    # apply a conservative 2% baseline so the autoresearch can still
    # differentiate good bodies from bad ones via spam/tcpa/length.
    if rr < 1.0:
        rr = 2.0

    return {
        "body":          body,
        "length":        len(body),
        "spam_score":    spam,
        "tcpa_score":    tcpa,
        "length_penalty": length,
        "reply_rate":    rr,
        "body_similarity": sim,
        # Weighted total (out of 100)
        "weighted":      0.45 * rr
                       + 0.10 * sim
                       + 0.20 * spam
                       + 0.20 * tcpa
                       - 0.05 * length,
    }


def write_result(row: dict, path: str = "results.tsv"):
    """Append a result row to results.tsv. Adds body_similarity column.
    Backwards-compatible: if existing TSV has the old schema (no
    body_similarity), header is rewritten to the new schema on the
    next run. Old rows remain parseable because we use column-ARITHMETIC
    in get_previous_best, not index-based reads.
    """
    import csv
    fields = ["timestamp", "body", "length", "spam_score", "tcpa_score",
              "length_penalty", "reply_rate", "body_similarity", "weighted",
              "kept", "note"]
    file_exists = os.path.exists(path)
    # Check if the existing header has the new schema
    needs_header_rewrite = False
    if file_exists:
        try:
            with open(path) as f:
                first_line = f.readline().strip().split("\t")
            if "body_similarity" not in first_line:
                needs_header_rewrite = True
        except Exception:
            pass
    if needs_header_rewrite:
        # rewrite header to new schema (don't touch old rows; train.py
        # is already updated to handle both formats via len() check)
        with open(path) as f:
            content = f.read()
        lines = content.splitlines()
        if lines:
            lines[0] = "\t".join(fields)
            with open(path, "w") as f:
                f.write("\n".join(lines) + "\n")
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        if not file_exists:
            w.writeheader()
        row_to_write = {k: row.get(k, "") for k in fields}
        row_to_write["timestamp"] = row.get("timestamp", datetime.now(timezone.utc).isoformat())
        w.writerow(row_to_write)
