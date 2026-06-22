---
tags: [mrr, subscription, dispatch-invoice, usdc, 2026-06-22]
---

# MRR System — USDC Subscriptions + Per-Lead Invoicing (2026-06-22)

**Status:** Live. Public at empire-ai.co.uk/for-contractors. Three cron jobs.
Two monetization paths from the same vault. Zero Stripe, zero KYC.

## The Two Paths

### 1. Subscriptions (Streamflow-style monthly USDC)

Contractor picks tier, sends X USDC/month to the vault. We verify on-chain
via Helius every 15 minutes. Auto-downgrades if they stop paying.

Tiers (live in `subscription_tiers` table):

| Tier | Price/mo | Leads/mo | Lead delay | Features |
|------|---------:|---------:|-----------:|----------|
| Free | $0 | 3 | 24h | history:7d |
| Basic | $99 | 50 | 60min | history:30d, priority |
| Pro | $299 | 200 | instant | history:90d, analytics |
| Enterprise | $499 | ∞ | instant | history:365d, dedicated rep |

Endpoints:
- `GET  /api/v1/subscribe/tiers` (public, returns pricing table)
- `POST /api/v1/subscribe/activate` {contractor_id, wallet, tier}
- `POST /api/v1/subscribe/verify` {contractor_id}
- `POST /api/v1/subscribe/cancel` {contractor_id}
- `GET  /api/v1/subscribe/me?contractor_id=`
- `POST /api/v1/subscribe/expire-lapsed` (cron)

### 2. Dispatch Invoicing (pay-per-lead USDC)

Every contractor outreach (call, SMS, email) creates a USDC invoice. Active
subscribers skip this (subscription covers it).

Pricing per outreach event by niche:

| Niche | Call | SMS | Email |
|-------|-----:|-----:|------:|
| roofing | $35 | $21 | $14 |
| hvac | $40 | $24 | $16 |
| legal | $75 | $45 | $30 |
| insurance | $60 | $36 | $24 |
| mass tort | $100 | $60 | $40 |

Endpoints:
- `POST /api/v1/dispatch/invoice` {contractor_id, dispatch_id, niche, outreach_type}
- `POST /api/v1/dispatch/invoice/check` {invoice_id}
- `POST /api/v1/dispatch/invoice/check-all` (cron)
- `GET  /api/v1/dispatch/invoice/list?contractor_id=&status=`

## How payments work

No Stripe. Contractor flow:
1. Visit empire-ai.co.uk/for-contractors, see tiers + features
2. Pick tier, paste their Solana wallet, click activate
3. Server creates `contractor_subscriptions` row with status=pending
4. Page returns vault address + memo + tier amount
5. Contractor sends X USDC from their wallet (Phantom, Solflare, etc) to:
   `egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM`
6. Click "I paid" → triggers verify → on-chain check via Helius
7. Tier activates for 30 days, re-verifies monthly

Same pattern for dispatch invoices — just a different amount per event.

## Verification: helius RPC + solders

`empire_subscription.py` and `empire_dispatch_invoice.py` both:
1. Get recent tx signatures on the vault (Helius `getSignaturesForAddress`)
2. For each tx after the relevant since_ts, parse with `getTransaction` (jsonParsed)
3. Inspect `preTokenBalances` / `postTokenBalances` / `innerInstructions`
4. Look for USDC transfers from the contractor wallet → vault
5. Match amount + tolerance (5% for dust)
6. Mark paid with tx_sig

If amount ≥ tier monthly_usdc → tier=active, expires_at = +30 days.

## Cron schedule

```
*/15 * * * *    empire_subscription.py verify-all      # 4x per hour
0  1 * * *    empire_subscription.py expire-lapsed  # daily 1am
*/10 * * * *    empire_dispatch_invoice.py check-all    # 6x per hour
```

## Realistic 30-60 day MRR

With 6,556 contractors in DB and **zero** active subscribers today:
- 30-day: 1-3 paying subs = $99-$1500 MRR (depends on outreach push to existing list)
- 60-day: 5-15 = $1k-$7.5k MRR
- 90-day: 25-50 = $5k-$25k MRR

Per-lead billing adds variable revenue on top, gated on dispatch volume
(still blocked on vonage numbers — but the invoice path works).

## File diff

- `migrations/050_subscription_and_invoicing.sql` (new, 3.4KB)
- `migrations/051_subscription_fixes.sql` (new, 0.9KB)
- `empire_subscription.py` (new, 11.8KB)
- `empire_dispatch_invoice.py` (new, 9.3KB)
- `empire_mrr.py` (new, 7.8KB)
- `empire_for_contractors.py` (new, 9.9KB)
- `hub.py` — added 2 imports + 1 route registration + 1 /for-contractors endpoint
- crontab — 3 new entries

## To make real money: outreach

The infrastructure is live. The bottleneck is now awareness:
1. Email blast to the 6,556 existing contractors with the new pricing page
2. WhatsApp / SMS the active 30-day ones with a "we've added paid tiers"
3. Reddit / forums for restoration contractors in TX/FL/CA

A 2-3% conversion of 6,556 contractors = 130-200 paid subs = $13k-60k MRR.
That requires sales motion — separate from this build.

## Related

- [[CoverForce_Vendor_Path_2026-06-22]] — vendor positioning, no broker license needed
- [[Three_Niches_Activated_2026-06-22]] — HVAC/debt/legal prospects this can monetize
- [[Sessions/2026-06-22_payment_and_recovery]] — existing fee_events pipeline
- [[Brain_MiniMax_Live_2026-06-22]] — brain can decide pricing/tier in real-time