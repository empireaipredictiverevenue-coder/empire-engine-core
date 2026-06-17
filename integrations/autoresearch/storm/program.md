# Empire AI · Autoresearch · Storm Strike

> Second target for the karpathy autoresearch pattern.
> Optimizes the storm_strike SMS body — sent to homeowners in storm-impacted areas.
> The first 24-72 hours after a storm are the highest-value window.

## Setup

Same as `autoresearch/program.md`. Run tag: `storm_jun16`.

## Goal

Maximize **homeowner reply rate** on the storm_strike touch-0 body.

`storm_strike` is the first sequence type fired after a storm alert. The recipient
is a homeowner (not a contractor) — different audience, different message, different
autoresearch loop.

## In-scope file

`train.py` — the editable body builder. Specifically `_build_storm_touch_zero()`.

## What you CAN do

- Modify `_build_storm_touch_zero()`. The function takes `target_addr` (the
  homeowner's city) and returns a single body string.
- Add helper functions in `train.py` (e.g. a function that picks a template variation
  based on `target_addr`).
- Change the value prop, the urgency, the CTA, the math, the format.

## What you CANNOT do

- Modify `prepare.py`. Read-only.
- Modify the dispatcher, the opt-out list, the carrier_outreach logic, or the fee ledger.
- Install new packages.
- Send real SMS to real homeowners. **Test only against historical data.**

## Constraints (enforced by the scorer)

- 130-160 chars (length_penalty outside that range)
- Must include "STOP" for opt-out (TCPA)
- Must identify as commercial/Empire AI
- No spam triggers (all-caps, !!!, $$$, "free", "guaranteed", etc.)
- Must include `{target_addr}` placeholder (the homeowner's city)

## Why storm_strike is the highest-leverage autoresearch target

1. **The revenue path:** storm_strike → homeowner says YES → roofer dispatched
   → claim settled → 3% fee to empire-ai. **This is the only sequence that
   generates the fee events** that pay our bills.
2. **High frequency:** every storm event triggers N storm_strike sequences. Volume
   scales with storm activity. Recent storm alert batch had 8 new alerts and 7,204
   new radar targets in 7 days.
3. **Time-sensitive:** the 72-hour insurance-doc window means a better body
   gets more YES replies in the same window. Even a 1% improvement × 7,000 leads
   = 70 more YES replies = 70 more dispatched roofers = up to 70 more settled claims.
4. **Real data:** 69 active sequences in the system + 8 inbox replies (5 interested,
   1 question, 1 followup_with_sample, 1 opted_out). Small but real training set.

## Metrics

`score_body()` in `prepare.py` returns a weighted score:
- 0.5 * reply_rate (from historical data)
- 0.3 * spam_score
- 0.2 * tcpa_score
- 0.1 * length_penalty

The reply_rate baseline is 7.25% (5 interested / 69 sequences). This is much
better than contractor_recruit (0.1%) because storm_strike targets homeowners
who are actively in need of help.

## First run

The first run establishes the baseline. Don't change the body in `train.py`
for the first run. It will:
1. Read the current storm_strike touch-0 body from `empire_sms.py`
2. Score it against the historical data
3. Write the baseline to `results.tsv`

## Permissions

- `prepare.py`: read-only.
- `train.py`: write, this is what you optimize.
- `results.tsv`: append-only.

## Cron

Same as the contractor_recruit autoresearch: `0 2 * * *`. But this target
runs in **series** with the contractor target — first the contractor cycle
(60 min), then the storm_strike cycle (60 min). Total 2h budget. Human-in-loop
deploy for both, with separate Telegram alerts.

## Why this matters more than contractor_recruit optimization

A 1% improvement in storm_strike reply rate directly impacts fee events.
A 1% improvement in contractor_recruit reply rate only impacts the contractor
funnel, which is upstream of the storm_strike funnel, which is upstream of
the fee event. The closer-to-money target is storm_strike.

## Logistics

- Runs nightly at **02:00 UTC** (after Resend daily reset, after money digest at 06:30 UTC).
- Two cycles per night: contractor_recruit (60 min) then storm_strike (60 min).
- Logs to `results.tsv` (separate column for `target` = contractor_recruit or storm_strike).
- Top result at end of cycle writes to a Telegram summary per target.
