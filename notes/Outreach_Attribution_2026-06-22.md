---
tags: [outreach, attribution, conversion, 2026-06-22, shipped]
---

# Outreach Conversion Attribution (2026-06-22)

**Status:** Live. End-to-end attribution from email → /for-contractors click → activate.

## Attribution chain

Each outbound email in `scripts/contractor_outreach.py` now includes:
```
{url}?outreach_id={row['id']}&cid={contractor_id}
```

When the contractor hits /for-contractors and clicks "Activate", the JS
form sends `outreach_id` along with the activation request. The
subscribe_activate endpoint:

1. Creates the subscription row (existing behavior)
2. **NEW**: Updates `contractor_outreach.paid_at` + notes="clicked /for-contractors + activated subscription"
3. Returns `attributed_to: <outreach_id>` so the frontend can confirm

Webhook tracking still works in parallel via Resend events (open/click
signals update opened_at/clicked_at regardless of activation).

## Live numbers (2026-06-22 15:35 UTC)

After the second batch send (479 more emails):

| status | count |
|--------|------:|
| sent | 727 |
| pending | 27 |
| bounced | 1 (synthetic test) |
| paid | 0 (yet) |

96% delivery success rate on the 755-contractor universe.

## What this enables

- Track which emails drive activation (subject line A/B winners)
- See which step in the 4-step sequence converts
- Attribute revenue per outreach_id → tier × outreach ROI
- Per-contractor funnel: open → click → activate → pay (15min verify)

## File diff

- `scripts/contractor_outreach.py` — added UTM params to URLs
- `empire_mrr.py` — activate endpoint accepts `outreach_id`, marks paid_at + notes
- Verified: 727 sent + 1 attribution roundtrip + DB updated correctly

## Cron schedule

- Daily 10am UTC: 250 new emails + advance sequence for prior sends
- Every 15min: subscription verify (Helius on-chain check)
- Every 10min: dispatch invoice check (unpaid invoice verification)
- Daily 1am UTC: expire-lapsed subscriptions

## To activate the loop

The funnel is fully open. What's needed:
1. A contractor to receive one of the 727 emails
2. Click /for-contractors
3. Activate (any tier — basic $99 is the cheapest test)
4. Send USDC to the vault
5. Verify cron flips tier to active within 15 min

When that happens, the daily report (9am UTC) shows the first ✅.

## Related

- [[Contractor_Outreach_2026-06-22]] — the campaign that produces the emails
- [[Resend_Webhook_2026-06-22]] — open/click tracking
- [[MRR_System_2026-06-22]] — what they convert into
- [[Sessions/2026-06-22_payment_and_recovery]] — existing fee pipeline
- [[Brain_MiniMax_Live_2026-06-22]] — brain reads these notes to decide tier recommendations