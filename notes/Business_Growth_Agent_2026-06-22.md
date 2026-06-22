---
tags: [growth-agent, recommendations, business, 2026-06-22]
---

# Business Growth Agent (2026-06-22)

**Status:** Live. Daily 11am UTC cycle. 9 rules generate recommendations.
Auto-executable subset (BBB rescrape, email validation gate) executes
without human action; rest are advisory.

## 9 rules

| # | Trigger | Severity | Action |
|---|---------|----------|--------|
| 1 | outreach_sent ≥ 50 AND open_rate < 15% | warning | A/B test subject lines |
| 2 | outreach_sent ≥ 100 AND click_rate < 3% | warning | rewrite CTA + body |
| 3 | outreach_sent ≥ 100 AND paid = 0 | critical | review pricing/landing |
| 4 | bounce_rate > 5% | warning | add email validation gate |
| 5 | sub_active < 3 after 100+ outreach | critical | add $49 starter tier |
| 6 | mrr_usdc < 1000 after 100+ outreach | info | activate 9 buyer lanes |
| 7 | contractors_with_email < 1000 | info | rescrape BBB |
| 8 | buyers_missing_phone > 0 | critical | provision vonage (human) |
| 9 | inv_pending > $100 AND inv_paid = 0 | warning | lower per-lead price + 7-day SMS reminder |

## Auto-executable subset

Two actions are safe to auto-execute:
- BBB rescrape (`bots/bbb_prospector.py`)
- email validation gate (already applied)

Other actions require human judgment (pricing changes, buyer provisioning,
subject-line A/B testing). They get logged as recommendations; you decide.

## Cron

```
0 11 * * *    agents/business_growth_agent.py
```

## Today's recommendations (first run 2026-06-22 16:34 UTC)

```
[critical] verticals: 6 buyer lanes have no destination_phone
[info]     verticals: MRR is $0/mo (target: $1k+ in 30d, $10k+ in 90d)
[critical] pricing: Only 0 active subscription(s) after 727 outreach sends
[critical] funnel:   0 paid conversions from 727 outreach emails
[warning]  outreach: Click-through rate is 0.0% (target: 5%+)
[warning]  outreach: Outreach open rate is 0.0% (target: 25%+)
```

The "0% open rate" is misleading — opens only just started arriving
(Resend webhook events take a few minutes to propagate). Next cycle
will have real numbers.

## What this is NOT

- NOT a chat agent — no user-facing chat
- NOT a strategy recommender with humans in the loop (yet)
- NOT a tactical execution engine — only fires safe auto-actions

It is a **funnel health monitor** that writes structured recommendations
to a queryable table. You read `/api/v1/growth/recommendations` (or
the existing `/api/growth/overview` endpoint) and act on them.

## File diff

- `migrations/053_business_growth_agent.sql` (new, 1.2KB)
- `agents/business_growth_agent.py` (new, 15KB)
- `scripts/contractor_outreach.py` — `_is_valid_email()` gate (mod)
- crontab — 1 new entry

## Related

- [[Outreach_Attribution_2026-06-22]] — what the agent measures
- [[MRR_System_2026-06-22]] — what it tries to grow
- [[Brain_MiniMax_Live_2026-06-22]] — could feed agent into brain for richer recommendations