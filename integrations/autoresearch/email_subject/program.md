# Empire AI · Autoresearch · Email Subject Lines

> Fourth target for the karpathy autoresearch pattern.
> Optimizes the email subject line for carrier outreach (5 carriers: Allstate,
> Farmers, Liberty Mutual, State Farm, USAA). Subject line is the
> **highest-leverage lever** for cold email — a 2x improvement in open
> rate roughly doubles the downstream conversion funnel.

## Setup

Run tag: `subject_jun16`.

## Goal

Maximize **email open rate** for the carrier outreach subject line.

The 5 current subjects are generic ("Vendor partner inquiry: settled-claim
webhook for predictive contractor routing" — 87 chars, no curiosity, no
value prop). autoresearch can find shorter, sharper, more curiosity-driven
subjects.

## In-scope file

`train.py` — the editable subject builder. Specifically `_build_subject()`.

## What you CAN do

- Modify `_build_subject()`. The function takes a carrier name and returns
  a subject line string (5-80 chars).
- Add helper functions in `train.py` (e.g. a function that picks a
  subject variation per carrier).

## What you CANNOT do

- Modify `prepare.py`. Read-only.
- Modify the carrier_outreach_drafts/*.txt files directly. The deploy
  happens after autoresearch finds a winning subject, manually.
- Install new packages.

## Constraints (enforced by the scorer)

- subject: 5-80 chars (email subject best practice)
- No all-caps (email clients flag it as spam)
- No spam triggers (FREE, $$$, !!!, URGENT, etc.)
- No excessive punctuation (3+ in a row)
- Should hint at value or curiosity (not generic "Inquiry:")

## Metrics

The scorer uses **heuristic scoring** (no historical data yet for subject
lines, since we don't have open-rate telemetry on the carrier drafts).
The heuristics reward:
- Conciseness (shorter is better, optimal 30-50 chars)
- Concrete numbers (e.g. "3% commission", "$10k claim", "10 minutes")
- Specificity (names a specific thing — "settled-claim", "webhook", "30-sec")
- Curiosity (question mark, "how to", "what if")
- Personalization (mentions the carrier name)

When we have real open-rate data from the carrier outreach, the scorer
will be replaced with one that weights by actual outcomes.

## Why this is the highest-leverage autoresearch target

Email subject line is the **single biggest lever** in cold email. A 1%
improvement in subject line = 1% improvement in open rate ≈ 0.5% in
response rate (industry rule of thumb). With 5 carrier drafts, that's
~1 extra "yes" if all 5 reply (they currently don't reply at all).

## Cron

Series: contractor_recruit → storm_strike → buyer → subject. Total 4h budget.

## Logistics

- Runs nightly at **02:00 UTC**.
- Logs to `results.tsv` with `target = subject`.
- Top result writes to a Telegram summary.
- Human-in-loop deploy: "deploy" or "skip" in Telegram.
