# Empire AI · Autoresearch · B2B Buyer Outreach

> Third target for the karpathy autoresearch pattern.
> Optimizes the BUYER_OUTREACH_TEMPLATE in `bots/affiliate_recruiter.py`.
> This is the B2B pipeline that runs via `automate_empire.sh` (predictive-revenue
> coder's lane, hourly at :30). It targets buyers in the Empire-AI network
> (alt-pay.net was one, with a confirmed reply).

## Setup

Same as `autoresearch/program.md`. Run tag: `buyer_jun16`.

## Goal

Maximize **recipient click + signup rate** for the B2B affiliate recruitment email.

The buyer outreach currently sends to ~53 buyers per cycle. The pipeline
sends from `Empire-AI Operations <noreply@empire-ai.co.uk>` (NOT my lane).
The body is HTML-rendered with `{name}`, `{commission}`, `{referral_url}`,
`{dashboard_url}` placeholders.

## In-scope file

`train.py` — the editable email body builder. Specifically `_build_buyer_email()`.

## What you CAN do

- Modify `_build_buyer_email()`. The function takes a name and the referral
  link dict, returns a tuple `(subject, html_body)`.
- Change the value prop, the CTA, the framing, the math.
- The current template has been generating ~1-2% reply rate (1 of 53 known).

## What you CANNOT do

- Modify `prepare.py`. Read-only.
- Modify `affiliate_recruiter.py` directly. The deploy happens after
  autoresearch finds a winning body, manually via the deploy command.
- Install new packages.

## Constraints (enforced by the scorer)

- subject: 30-80 chars (email subject best practice)
- body html: 200-2000 chars
- Must include sender identity (Empire AI)
- Must include a clear CTA (the referral link)
- Must NOT include spam triggers (all-caps, !!!, $$$, "guaranteed", etc.)
- Should personalize via {name} (if available)

## Metrics

The scorer loads the B2B reply data from `inbox_messages` where:
- `meta.gmail_folder = "INBOX"` (B2B replies land in the gmail inbox)
- `classified_intent = "interested"` or "question"

Currently 1 confirmed reply (jstamatis@alt-pay.net → "I would like to learn more").
The scorer uses this as a labeled example.

Reply-rate baseline: **1.85% (1/53)**
Industry average for B2B cold email: **1-5%**
Goal: 5%+ within 30 days of autoresearch

## Why this is higher-leverage than the SMS targets

The B2B pipeline runs hourly at :30 (vs SMS which runs on-demand from cron).
The buyer list is much higher-value (alt-pay's worth ~$30k/year in
referral fees if they convert). And the body is HTML so it can have
more sophisticated CTAs, graphics, and links.

## Cron

Same as the other targets: `0 2 * * *`. This target runs in **series**:
contractor_recruit (60 min), storm_strike (60 min), buyer (60 min). Total 3h.

## Logistics

- Runs nightly at **02:00 UTC** (after Resend daily reset).
- Logs to `results.tsv` with `target = buyer`.
- Top result at end of cycle writes to a Telegram summary.
- Human-in-loop deploy: "deploy" or "skip" in Telegram.
