"""
EMPIRE AI · AUTORESEARCH · prepare.py (email subject target)
============================================================
Heuristic scorer for email subject lines. No historical data yet
(no open-rate telemetry on the carrier drafts) — uses best practices
from cold-email research.
DO NOT MODIFY.
"""
import os
import csv
import re
from datetime import datetime, timezone


def length_score(subject: str) -> float:
    """30-50 chars is the sweet spot. Penalty outside."""
    if not subject: return 100.0
    n = len(subject)
    if 30 <= n <= 50: return 0.0
    if 20 <= n < 30 or 50 < n <= 70: return 20.0
    if 10 <= n < 20 or 70 < n <= 90: return 50.0
    return 100.0


def caps_score(subject: str) -> float:
    """0-100, lower is worse. All-caps subjects go to spam."""
    if not subject: return 0.0
    score = 100.0
    letters = [c for c in subject if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.5:
        score -= 80
    return max(0.0, score)


def spam_score(subject: str) -> float:
    """0-100, lower is more spammy."""
    if not subject: return 0.0
    score = 100.0
    triggers = [
        r"\bFREE\b", r"!!+", r"\$\$\$", r"\bGUARANTEED\b",
        r"\bACT NOW\b", r"\bLIMITED TIME\b", r"\bURGENT\b",
        r"\b100%\s*FREE\b", r"RISK[- ]FREE",
    ]
    for pat in triggers:
        if re.search(pat, subject):
            score -= 30
    # Excessive punctuation (3+ same char)
    if re.search(r"([!?])\1{2,}", subject):
        score -= 30
    return max(0.0, score)


def specificity_score(subject: str) -> float:
    """Higher = mentions specific things (numbers, products, time)."""
    if not subject: return 0.0
    score = 0.0
    # Has a number
    if re.search(r"\d+", subject):
        score += 30
    # Has a percent or dollar
    if re.search(r"\d+%|\$\d+", subject):
        score += 30
    # Has a time-bound word
    if re.search(r"(?i)(minute|hour|day|week|month|sec\b|now|today)", subject):
        score += 20
    # Has a specific product/feature word
    if re.search(r"(?i)(webhook|api|claim|storm|lead|contractor|insurance|settle|payout)", subject):
        score += 20
    return min(100.0, score)


def curiosity_score(subject: str) -> float:
    """Higher = creates curiosity (question, hint, FOMO)."""
    if not subject: return 0.0
    score = 0.0
    if "?" in subject: score += 50
    if re.search(r"^(How|Why|What|Who|When|Where)", subject, re.IGNORECASE): score += 30
    if re.search(r"(?i)(secret|discover|reveal|hidden|missed|little[- ]known)", subject): score += 20
    return min(100.0, score)


def personalization_score(subject: str, carrier_name: str = "") -> float:
    """Higher = uses the carrier name (shows personalization)."""
    if not subject or not carrier_name: return 0.0
    if carrier_name.lower() in subject.lower(): return 100.0
    return 0.0


def score_subject(subject: str, carrier_name: str = "") -> dict:
    length = length_score(subject)
    caps   = caps_score(subject)
    spam   = spam_score(subject)
    spec   = specificity_score(subject)
    curi   = curiosity_score(subject)
    pers   = personalization_score(subject, carrier_name)
    return {
        "subject": subject,
        "length": len(subject),
        "length_penalty": length,
        "caps_score": caps,
        "spam_score": spam,
        "specificity_score": spec,
        "curiosity_score": curi,
        "personalization_score": pers,
        # Weighted: prioritize specificity + curiosity + length
        "weighted":    0.30 * spec
                     + 0.25 * curi
                     + 0.20 * pers
                     + 0.15 * spam
                     + 0.10 * caps
                     - 0.20 * length,
    }


def write_result(row: dict, path: str = "results.tsv"):
    fields = ["timestamp", "subject", "length", "length_penalty", "caps_score",
              "spam_score", "specificity_score", "curiosity_score",
              "personalization_score", "weighted", "kept", "note"]
    file_exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        if not file_exists:
            w.writeheader()
        row_to_write = {k: row.get(k, "") for k in fields}
        row_to_write["timestamp"] = row.get("timestamp", datetime.now(timezone.utc).isoformat())
        w.writerow(row_to_write)
