"""
EMPIRE AI · AUTORESEARCH · train.py (email subject target)
==========================================================
The ONLY file the agent is allowed to edit. Modify the subject builder
function `_build_subject()` to maximize the weighted score.

After you modify _build_subject(), run:
    uv run train.py
(or just `python3 train.py`)

Each run:
  1. Builds a subject using your modified _build_subject()
  2. Scores it via prepare.score_subject()
  3. Compares to the previous best (kept in results.tsv)
  4. If better: writes a "kept=yes" row. Else: writes "kept=no".
  5. Prints the comparison.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prepare import score_subject, write_result


def _build_subject(carrier_name: str = "Allstate") -> str:
    """Build the carrier outreach email subject.

    EDIT THIS FUNCTION. Everything else is fixed.

    Returns: subject line string (5-80 chars).

    Constraints (enforced by the scorer):
      - subject: 5-80 chars (optimal 30-50)
      - No all-caps
      - No spam triggers
      - Should hint at value or curiosity

    Variables available:
      carrier_name: str — name of the carrier (e.g. "Allstate", "State Farm")

    Current baseline (from /root/empire-v49/carrier_outreach_drafts/allstate.txt):
      "Vendor partner inquiry: settled-claim webhook for predictive contractor routing"
      (87 chars — too long, generic)

    Suggested improvements to try:
      - Lead with a concrete number: "3% commission on settled claims"
      - Ask a question: "Want 3% of every settled claim?"
      - Drop generic words ("vendor partner inquiry:" etc.)
      - Use the carrier's name for personalization
      - Be specific about the value: "Setup in 10 min, earn 3%"
      - Test short and long variants
    """
    return f"{carrier_name}, want 3% of every settled claim?"


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
                    "subject":       parts[1],
                    "length":        parts[2],
                    "length_pen":    parts[3],
                    "caps":          parts[4],
                    "spam":          parts[5],
                    "spec":          parts[6],
                    "curi":          parts[7],
                    "pers":          parts[8],
                    "weighted":      parts[9],
                    "note":          parts[11] if len(parts) > 11 else "",
                }
    return last


def main():
    # Test against all 5 carriers
    carriers = ["Allstate", "Farmers", "Liberty Mutual", "State Farm", "USAA"]
    subject = _build_subject(carrier_name=carriers[0])
    print(f"=== TESTING SUBJECT ===\n{subject}\n")
    print(f"length: {len(subject)} chars\n")

    score = score_subject(subject, carrier_name=carriers[0])
    print("=== SCORE BREAKDOWN ===")
    for k, v in score.items():
        if k == "subject": continue
        print(f"  {k:25} {v}")
    print(f"  {'weighted total':25} {score['weighted']:.2f} / 100")

    prev = get_previous_best()
    if prev is None:
        print("\n=== FIRST RUN — establishing baseline ===")
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subject":   subject,
            "length":    score["length"],
            "length_penalty": score["length_penalty"],
            "caps_score": score["caps_score"],
            "spam_score": score["spam_score"],
            "specificity_score": score["specificity_score"],
            "curiosity_score":  score["curiosity_score"],
            "personalization_score": score["personalization_score"],
            "weighted":   score["weighted"],
            "kept":       "yes",
            "note":       "baseline (first run)",
        }
        write_result(row)
        print("baseline written to results.tsv")
    else:
        prev_w = float(prev["weighted"]) if isinstance(prev["weighted"], str) else prev["weighted"]
        if score["weighted"] > prev_w:
            print(f"\n=== IMPROVEMENT: {prev_w} -> {score['weighted']} ===")
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "subject":   subject,
                "length":    score["length"],
                "length_penalty": score["length_penalty"],
                "caps_score": score["caps_score"],
                "spam_score": score["spam_score"],
                "specificity_score": score["specificity_score"],
                "curiosity_score":  score["curiosity_score"],
                "personalization_score": score["personalization_score"],
                "weighted":   score["weighted"],
                "kept":       "yes",
                "note":       f"improved over {prev_w}",
            }
            write_result(row)
        else:
            print(f"\n=== NO IMPROVEMENT: {prev_w} -> {score['weighted']} (kept=no) ===")
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "subject":   subject,
                "length":    score["length"],
                "length_penalty": score["length_penalty"],
                "caps_score": score["caps_score"],
                "spam_score": score["spam_score"],
                "specificity_score": score["specificity_score"],
                "curiosity_score":  score["curiosity_score"],
                "personalization_score": score["personalization_score"],
                "weighted":   score["weighted"],
                "kept":       "no",
                "note":       f"regressed from {prev_w}",
            }
            write_result(row)


if __name__ == "__main__":
    main()
