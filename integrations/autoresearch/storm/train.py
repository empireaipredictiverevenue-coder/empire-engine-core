"""
EMPIRE AI · AUTORESEARCH · train.py (storm_strike target)
========================================================
The ONLY file the agent is allowed to edit. Modify the body builder
function `_build_storm_touch_zero()` to maximize the weighted score.

Constraint: this is a single-GPU-equivalent runtime, so the body
must be a simple string. No async, no external state, no DB calls
in the hot path.

After you modify _build_storm_touch_zero(), run:
    uv run train.py
(or just `python3 train.py`)

Each run:
  1. Builds a body using your modified _build_storm_touch_zero()
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


def _build_storm_touch_zero(target_short: str = "your area") -> str:
    """Build the storm_strike touch-0 body.

    EDIT THIS FUNCTION. Everything else is fixed.

    Constraints (enforced by the scorer):
      - 130-160 chars (length_penalty outside that range)
      - Must include "STOP" for opt-out (TCPA)
      - Must identify as commercial/Empire AI
      - No spam triggers (all-caps, !!!, $$$, "free", "guaranteed", etc.)
      - Must reference {target_short} (the homeowner's city)

    Variables available:
      target_short: str — the homeowner's area (e.g. "Houston", "Tampa")

    Current baseline (from /root/empire-v49/empire_sms.py):
      "Empire AI: Storm flagged at {target_short}. We dispatch 1 vetted
      roofer to your area — no cost unless claim settles. Reply YES to
      schedule free assessment. STOP to opt out."

    Suggested improvements to try:
      - Lead with the specific urgency (72-hour insurance-doc window)
      - Be more specific about value (free assessment vs no-cost)
      - Drop the "STOP" mention to a cleaner spot
      - Add a concrete number ("$250K claim = $7,500 to you, $7,500 to us")
      - Use a more urgent first sentence
    """
    return (
        f"Empire AI: Storm flagged at {target_short}. "
        f"We dispatch 1 vetted roofer to your area — no cost unless claim settles. "
        f"Reply YES to schedule free assessment. "
        f"STOP to opt out."
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
    # Test the body across a few target cities
    targets = ["Houston", "Tampa", "Austin", "Miami", "New Orleans"]
    body = _build_storm_touch_zero(target_short="Houston")
    print(f"=== TESTING STORM_STRIKE TOUCH-0 BODY ===\n{body}\n")
    print(f"length: {len(body)} chars\n")

    # Score
    score = score_body(body, metro="Houston", sequence_type="storm_strike")
    print("=== SCORE BREAKDOWN ===")
    for k, v in score.items():
        if k == "body": continue
        print(f"  {k:18} {v}")
    print(f"  {'weighted total':18} {score['weighted']:.2f} / 100")

    # Compare to previous best
    prev = get_previous_best()
    if prev is None:
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
