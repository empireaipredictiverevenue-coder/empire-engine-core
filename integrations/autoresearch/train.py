"""
EMPIRE AI · AUTORESEARCH · train.py
===================================
The ONLY file the agent is allowed to edit. Modify the body builder
function `_build_body()` to maximize the weighted score.

Constraint: this is a single-GPU-equivalent runtime, so the body
must be a simple string. No async, no external state, no DB calls
in the hot path.

After you modify _build_body(), run:
    uv run train.py
(or just `python3 train.py`)

Each run:
  1. Builds a body using your modified _build_body()
  2. Scores it via prepare.score_body()
  3. Compares to the previous best (kept in results.tsv, last "kept=yes" row)
  4. If better: writes a "kept=yes" row. Else: writes "kept=no".
  5. Prints the comparison.
"""
import os
import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prepare import score_body, write_result, load_sms_data


def _build_body(metro: str = "Houston", first_name: str = "") -> str:
    """Build the contractor_recruit SMS body.

    EDIT THIS FUNCTION. Everything else is fixed.

    Constraints (enforced by the scorer):
      - 130-160 chars (length_penalty outside that range)
      - Must include "STOP" for opt-out (TCPA)
      - Must identify as commercial/Empire AI
      - No spam triggers (all-caps, !!!, $$$, "free", "guaranteed", etc.)

    Variables available:
      metro:      str — the contractor's market (e.g. "Houston", "Austin")
      first_name: str — contractor's first name (empty string if unknown)

    Current baseline (from /root/empire-v49/empire_sms.py):
      "Hi {first_name}, storm leads for roofers in your metro — first 2 closed
      deals on us, 3% after. 90-sec self-onboard at empire-ai.co.uk/contractors.
      STOP to opt out."

    Suggested improvements to try:
      - Lead with the value (3% vs 0% on first 2 deals) more concretely
      - Personalize by metro ("in Houston" feels different from "in Wichita")
      - Add a specific time-saving claim ("5-min signup" or similar)
      - Drop the "STOP" mention to a separate line for cleaner reading
      - Add "Reply YES for the demo" as a clearer CTA
    """
    greeting = f"Hi {first_name}," if first_name else "Hi,"
    # TCPA: include sender identity (Empire AI) + STOP for opt-out
    return (
        f"{greeting} Empire AI here — storm leads for roofers in {metro}. "
        f"First 2 closed deals free, 3% after. "
        f"90-sec signup at empire-ai.co.uk/contractors. "
        f"Reply STOP to opt out."
    )


def get_previous_best(path: str = "results.tsv"):
    """Read the last 'kept=yes' row from results.tsv. None if empty."""
    if not os.path.exists(path):
        return None
    last = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("timestamp"):
                continue
            parts = line.split("\t")
            if len(parts) < 9:
                continue
            if parts[8] == "yes":
                last = {
                    "timestamp": parts[0],
                    "body": parts[1],
                    "length": float(parts[2]),
                    "spam_score": float(parts[3]),
                    "tcpa_score": float(parts[4]),
                    "length_penalty": float(parts[5]),
                    "reply_rate": float(parts[6]),
                    "weighted": float(parts[7]),
                    "note": parts[9] if len(parts) > 9 else "",
                }
    return last


def main():
    # Test the body across a few metros
    metros = ["Houston", "Austin", "Dallas-FW", "San Antonio", "Wichita"]
    body = _build_body(metro="Houston", first_name="")
    print(f"=== TESTING BODY ===\n{body}\n")
    print(f"length: {len(body)} chars\n")

    # Score
    score = score_body(body, metro="Houston")
    print("=== SCORE BREAKDOWN ===")
    for k, v in score.items():
        if k == "body": continue
        print(f"  {k:18} {v}")
    print(f"  {'weighted total':18} {score['weighted']:.2f} / 100")

    # Compare to previous best
    prev = get_previous_best()
    if prev is None:
        # First run — establish baseline
        print("\n=== FIRST RUN — establishing baseline ===")
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "body": body,
            "length": score["length"],
            "spam_score": score["spam_score"],
            "tcpa_score": score["tcpa_score"],
            "length_penalty": score["length_penalty"],
            "reply_rate": score["reply_rate"],
            "weighted": score["weighted"],
            "kept": "yes",
            "note": "baseline (first run)",
        }
        write_result(row)
        print("baseline written to results.tsv")
    else:
        if score["weighted"] > prev["weighted"]:
            print(f"\n=== IMPROVEMENT: {prev['weighted']:.2f} -> {score['weighted']:.2f} ===")
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "body": body,
                "length": score["length"],
                "spam_score": score["spam_score"],
                "tcpa_score": score["tcpa_score"],
                "length_penalty": score["length_penalty"],
                "reply_rate": score["reply_rate"],
                "weighted": score["weighted"],
                "kept": "yes",
                "note": f"improved over {prev['weighted']:.2f}",
            }
            write_result(row)
        else:
            print(f"\n=== NO IMPROVEMENT: {prev['weighted']:.2f} -> {score['weighted']:.2f} (kept=no) ===")
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "body": body,
                "length": score["length"],
                "spam_score": score["spam_score"],
                "tcpa_score": score["tcpa_score"],
                "length_penalty": score["length_penalty"],
                "reply_rate": score["reply_rate"],
                "weighted": score["weighted"],
                "kept": "no",
                "note": f"regressed from {prev['weighted']:.2f}",
            }
            write_result(row)


if __name__ == "__main__":
    main()
