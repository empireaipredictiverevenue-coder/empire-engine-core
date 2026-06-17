"""
EMPIRE AI · AUTORESEARCH · train.py (buyer outreach target)
============================================================
The ONLY file the agent is allowed to edit. Modify the body builder
function `_build_buyer_email()` to maximize the weighted score.

After you modify _build_buyer_email(), run:
    uv run train.py
(or just `python3 train.py`)

Each run:
  1. Builds an email using your modified _build_buyer_email()
  2. Scores it via prepare.score_body()
  3. Compares to the previous best (kept in results.tsv, last "kept=yes" row)
  4. If better: writes a "kept=yes" row. Else: writes "kept=no".
  5. Prints the comparison.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prepare import score_body, write_result


def _build_buyer_email(name: str = "Friend", commission: str = "10%",
                      referral_url: str = "https://empire-ai.co.uk/r/jstamatis",
                      dashboard_url: str = "https://empire-ai.co.uk/affiliate/dashboard",
                      source: str = "buyer") -> tuple:
    """Build the B2B buyer outreach email.

    EDIT THIS FUNCTION. Everything else is fixed.

    Returns: (subject, html_body) tuple.

    Constraints (enforced by the scorer):
      - subject: 30-80 chars
      - body html: 200-2000 chars
      - No spam triggers
      - Must include {name} placeholder for personalization
      - Must include CTA with the referral link
      - Must identify as Empire AI (commercial sender)

    Variables available:
      name:           str — recipient's first name (or "Friend" fallback)
      commission:     str — "10%" by default
      referral_url:   str — the unique referral link
      dashboard_url:  str — the affiliate dashboard URL
      source:         str — "buyer" or "contractor" (which template)

    Current baseline (from bots/affiliate_recruiter.py):
      Subject: "Empire AI Affiliate Program — Your {offer_type} Link Inside"
      Body: "Hi {name}, You're already a valued partner in the Empire AI
      revenue network. We'd like to invite you to join our Affiliate
      Program and earn {commission} commission on every qualified lead
      you refer. Your unique referral link is ready: ..."

    Suggested improvements to try:
      - Lead with the dollar amount, not the percentage
      - Use "your business" not "valued partner" (more concrete)
      - Add a specific success story: "Jstamatis at alt-pay just joined"
      - Move the CTA higher in the body (above the referral link)
      - Add social proof: "Join 50+ buyers already earning ..."
      - Reduce HTML styling (sends look spammy with all the color blocks)
    """
    subject = f"Empire AI Affiliate Program — Your {source.title()} Link Inside"
    body = (
        f'<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">'
        f"Hi <strong>{name}</strong>,</p>"
        f'<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">'
        f"You're already a valued partner in the Empire AI revenue network. "
        f"We'd like to invite you to <strong>join our Affiliate Program</strong> and earn "
        f'<strong style="color:#44E5B8;">{commission} commission</strong> '
        f"on every qualified lead you refer.</p>"
        f'<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">'
        f"Get started in under 2 minutes — your unique referral link is ready:"
        f"</p>"
        f'<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(68,229,184,0.25);'
        f'padding:14px 18px;font-family:monospace;font-size:13px;color:#44E5B8;'
        f'word-break:break-all;margin:16px 0;text-align:center;">'
        f'<a href="{referral_url}" style="color:#44E5B8;text-decoration:none;">{referral_url}</a>'
        f"</div>"
        f'<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">'
        f'<strong>Sign up</strong> with this link to start earning. '
        f"Share it with your network. When someone clicks and converts, "
        f"{commission} is yours. No minimums, no exclusivity.</p>"
        f'<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">'
        f"Track your clicks, leads, and earnings anytime at your affiliate dashboard: "
        f'<a href="{dashboard_url}" style="color:#44E5B8;text-decoration:none;">{dashboard_url}</a>'
        f"</p>"
        f'<p style="font-size:14px;line-height:1.7;color:#a1a1aa;">'
        f"Welcome to the team.<br>"
        f"<strong>— Empire AI Ops</strong></p>"
    )
    return subject, body


def get_previous_best(path: str = "results.tsv"):
    if not os.path.exists(path):
        return None
    last = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("timestamp"):
                continue
            parts = line.split("\t")
            if len(parts) < 12:
                continue
            if parts[10] == "yes":
                last = {
                    "timestamp": parts[0],
                    "subject": parts[1],
                    "body":    parts[2],
                    "spam":    parts[3],
                    "subject_score": parts[4],
                    "personalization_score": parts[5],
                    "cta_score": parts[6],
                    "length_pen": parts[7],
                    "reply":   parts[8],
                    "weighted": parts[9],
                    "note":    parts[11] if len(parts) > 11 else "",
                }
    return last


def main():
    subject, body = _build_buyer_email(name="Friend", source="buyer")
    print(f"=== TESTING BUYER EMAIL ===\nsubject: {subject}\n")
    print(f"body:\n{body}\n")

    score = score_body(subject, body, name="Friend")
    print("=== SCORE BREAKDOWN ===")
    for k, v in score.items():
        if k in ("body", "subject"): continue
        print(f"  {k:25} {v}")
    print(f"  {'weighted total':25} {score['weighted']:.2f} / 100")

    prev = get_previous_best()
    if prev is None:
        print("\n=== FIRST RUN — establishing baseline ===")
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subject":    subject,
            "body":       body,
            "spam_score": score["spam_score"],
            "subject_score": score["subject_score"],
            "personalization_score": score["personalization_score"],
            "cta_score":   score["cta_score"],
            "length_penalty": score["length_penalty"],
            "reply_rate":  score["reply_rate"],
            "weighted":   score["weighted"],
            "kept":        "yes",
            "note":        "baseline (first run)",
        }
        write_result(row)
        print("baseline written to results.tsv")
    else:
        if score["weighted"] > prev["weighted"]:
            print(f"\n=== IMPROVEMENT: {prev['weighted']} -> {score['weighted']} ===")
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "subject":    subject,
                "body":       body,
                "spam_score": score["spam_score"],
                "subject_score": score["subject_score"],
                "personalization_score": score["personalization_score"],
                "cta_score":   score["cta_score"],
                "length_penalty": score["length_penalty"],
                "reply_rate":  score["reply_rate"],
                "weighted":   score["weighted"],
                "kept":        "yes",
                "note":        f"improved over {prev['weighted']}",
            }
            write_result(row)
        else:
            print(f"\n=== NO IMPROVEMENT: {prev['weighted']} -> {score['weighted']} (kept=no) ===")
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "subject":    subject,
                "body":       body,
                "spam_score": score["spam_score"],
                "subject_score": score["subject_score"],
                "personalization_score": score["personalization_score"],
                "cta_score":   score["cta_score"],
                "length_penalty": score["length_penalty"],
                "reply_rate":  score["reply_rate"],
                "weighted":   score["weighted"],
                "kept":        "no",
                "note":        f"regressed from {prev['weighted']}",
            }
            write_result(row)


if __name__ == "__main__":
    main()
