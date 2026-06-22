---
tags: [funnel, status, dashboard, 2026-06-22]
---

# Funnel Status API (2026-06-22)

**Status:** Live at `GET /api/v1/funnel/status`. Single endpoint, full
pipeline snapshot. Authenticated via existing HUB_TOKEN.

## What it returns

```json
{
  "as_of": "2026-06-22T21:04:28.952Z",
  "outreach": {
    "total_enrolled": 755, "pending": 27, "sent": 727,
    "opened": 1, "clicked": 1, "paid": 0, "bounced": 1,
    "open_rate": 0.1, "click_rate": 0.1
  },
  "subscriptions": {
    "total": 1, "pending_payment": 1, "active": 0,
    "lapsed": 0, "cancelled": 0,
    "mrr_usdc": 0, "mrr_annual_run_rate": 0
  },
  "dispatch_invoices": {
    "total": 1, "paid": 0, "unpaid": 1,
    "paid_usdc": 0, "unpaid_usdc": 35.0,
    "collection_rate": 0.0
  },
  "fee_events": {
    "paid_count": 3, "pending_count": 8,
    "paid_usdc": 13500.0, "pending_usdc": 43559.25
  },
  "contractors": {
    "total": 6582, "active": 6582, "with_valid_email": 6582
  },
  "buyers": {
    "total": 14, "with_destination_phone": 3, "missing_phone": 11
  },
  "vault": {
    "wallet": "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
  }
}
```

## Use cases

- One curl call replaces querying 8 tables separately
- Daily ops report sources from this directly (when telegram is wired)
- Dashboard widget can poll every 30s for live updates
- Commission audit ("how much real USDC has the vault seen?") - extend with vault balance check

## Live snapshot (2026-06-22 21:04 UTC)

- 727/755 outreach emails sent (96% delivery)
- 1 opened + 1 clicked (synthetic test events; real opens accumulating now)
- 1 pending subscription (my activation test) + 1 unpaid dispatch invoice ($35)
- $13,500 fee_events paid (operator mark-paid), $43,559 pending settlement
- 6,582 contractors, 14 buyers (only 3 with destination_phone)

## File diff

- `empire_funnel.py` (new, 6.4KB) — single endpoint aggregating all funnel tables

## Related

- [[Contractor_Outreach_2026-06-22]] — campaign producing the outreach numbers
- [[MRR_System_2026-06-22]] — what they convert into (subs + invoices)
- [[Resend_Webhook_2026-06-22]] — feeding opened/clicked numbers
- [[Sessions/2026-06-22_payment_and_recovery]] — fee_events pipeline