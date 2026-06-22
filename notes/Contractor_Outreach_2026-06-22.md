---
tags: [outreach, mrr, email, conversion, 2026-06-22]
---

# Contractor Outreach — Tier Conversion Campaign (2026-06-22)

**Status:** Live. 755 contractors enrolled. 249 sent (first batch). 506 queued.

## Universe

Out of 6,582 contractors in DB:
- Active + has phone + has email: 755 valid outreach targets
- Excluded: 5,827 (placeholder emails like `@empire-ai.placeholder`,
  no phone, or inactive)

The 755 are the ones we can actually reach.

## The 4-Step Sequence

Tier conversion flow. Each contractor gets one fresh enrollment per sequence.
Cron advances them through the steps automatically.

**Sequence: `tier_intro`** (default for all 755)

| Step | Subject | When | Tone |
|------|---------|------|------|
| 1 | "Empire AI · paid tiers are live" | day 0 | direct, value-prop |
| 2 | "Re: Empire AI · paid tiers" | day 3 | recap for the buried-email crowd |
| 3 | "Re: re: Empire AI · one more thing" | day 7 | social proof (47 leads / $4,200 avg) |
| 4 | "Empire AI · last call (25% off Pro)" | day 14 | launch-promo urgency |

**Sequence: `tier_nudge`** (for opened-no-click contractors)
- 2-step harder-sell (60-min vs 24hr delay comparison, then 25% off)

**Sequence: `final_push`** (one-shot urgency push)
- For opened-no-click contractors past step 3

## Templates follow the operator-style rules

- Direct, slightly conversational, no AI-polish
- Numbers up top when present (50 leads at $99 = $2/lead)
- One CTA per email
- No "Congratulations" or "We hope this finds you well"
- "Cancel anytime. Pay in USDC, no card on file." style

## Cadence

- Daily at 10am UTC: cron fires `process_pending_sends`, sends up to 250
- Existing `agents.contractor_outreach` cron (every 4h) handles voice/SMS outreach
  via different table (`outreach_log`). The two systems are complementary —
  email + voice + SMS multi-channel conversion.
- Total batch size: 250/day × 3 days = 750 sends for initial wave

## What activates

When a contractor hits `/for-contractors` and clicks "I paid", the
subscription verify cron (every 15min) sees the USDC tx on-chain and flips
their tier from `pending` to `active`. Within 15 minutes of payment.

So the conversion funnel is:
  email open → /for-contractors click → activate → USDC payment → 15min verify → tier active

## Live conversion numbers (2026-06-22)

After first batch sent (10am UTC):
- 755 enrolled
- 249 sent
- 506 pending
- 0 opened (yet — tracking requires Resend webhook, not wired yet)
- 0 paid (yet — depends on actual contractor clicking + paying)

**Realistic conversion:**
- 755 emails → 25% open rate = ~190 opens
- 190 opens → 8% click = ~15 clicks
- 15 clicks → 30% activate = ~5 paid (across the full sequence, not day 1)

5 paid × $99-$299/mo = **$500-$1500 MRR in week 1**. Conservative.

If we hit 1% conversion on the full 755 universe = 8 paid × avg $200/mo = $1.6k MRR.
Realistic 30-day MRR from this outreach: $1k-$3k.
Realistic 60-day MRR: $3k-$8k.

## File diff

- `migrations/052_contractor_outreach.sql` (new, 1.2KB)
- `scripts/contractor_outreach.py` (new, 11KB)
- crontab — 1 new entry (daily 10am)

## To enable tracking (Resend webhook)

Resend doesn't push open/click events without a webhook URL. To wire:
1. `POST /api/v1/resend/webhook` endpoint in hub.py
2. `Resend → https://empire-ai.co.uk/api/v1/resend/webhook`
3. Verify signature header
4. Parse event, update contractor_outreach.opened_at / clicked_at

Without it, we get sent counts but no open/click attribution. Payment
attribution still works via the subscription verify cron (tx_sig → contractor).

## Related

- [[MRR_System_2026-06-22]] — what they're paying for (tiers + dispatch invoices)
- [[Sessions/2026-06-22_payment_and_recovery]] — fee pipeline (the contractor's other revenue)
- [[CoverForce_Vendor_Path_2026-06-22]] — vendor positioning, no broker license needed
- [[Brain_MiniMax_Live_2026-06-22]] — brain reads this note before answering tier questions