# Empire-AI · Carrier Integration Guide

> How to swap the mock carrier API for real insurance carrier webhooks.
> The 1 fee event in our system (3% = $3,750) is from `operator_mark_settled`,
> a manual flag. **The first real fee event comes when a real carrier
> webhook hits `/api/v1/fee/claim-settled`.**

## Current state

- **Mock carrier:** `empire_carrier.py` exposes `/api/v1/carrier/claims` and
  `/api/v1/carrier/claims/{id}/settle`. When a claim is "settled" via the
  mock, the system writes a `fee_events` row with `source=mock_carrier`,
  3% of `settled_amount`.
- **Real path:** `/api/v1/fee/claim-settled` (the hub endpoint that real
  carrier webhooks would hit). Same shape, same result.
- **Why it's not in production:** we don't have access to real carrier
  webhooks yet. State Farm, Allstate, USAA, etc. have private claim
  systems. We sent them partnership inquiries 2026-06-16 (drafts at
  `/root/empire-v49/carrier_outreach_drafts/`). When a carrier
  responds with a vendor partner program, we get webhooks.

## How to integrate a real carrier webhook

When a carrier says "yes, we'll send you settled-claim events," they
need to POST to an endpoint. **The endpoint already exists.** Just
point them at:

```
POST https://empire-ai.co.uk/api/v1/fee/claim-settled
Content-Type: application/json
Authorization: Bearer <EMPIRE_INBOUND_TOKEN>

{
  "claim_id":       "<their internal claim id>",
  "settled_amount": 250000,
  "property_city":   "Houston",
  "property_state":  "TX",
  "carrier_name":    "Allstate",
  "settled_at":      "2026-06-17T14:00:00+00:00"
}
```

The hub endpoint writes a `fee_events` row with:
- `claim_id`: their id
- `fee_amount`: 3% of `settled_amount`
- `status`: paid
- `source`: `<carrier_name>` (overrides the `mock_carrier` default)
- `settled_at`: their timestamp

**The fee path is identical to the mock. The chain is the same:**
1. Carrier webhook → hub
2. Hub writes `fee_events` row
3. `fee_events` triggers downstream (carrier portfolio, ledger, digest)
4. Phil sees a real money event in the daily digest

## What to ask each carrier

The 5 drafts in `/root/empire-v49/carrier_outreach_drafts/` cover the
minimum. When a carrier responds with a vendor partner program, ask
for:

1. **Webhook URL** (give them `https://empire-ai.co.uk/api/v1/fee/claim-settled`)
2. **Auth method** (most use Bearer token; we have `EMPIRE_INBOUND_TOKEN` ready)
3. **Field mapping** (most use their own claim_id format; we accept any string)
4. **Retry policy** (we have retry logic in the hub; let them know we can dedup on claim_id)
5. **Test event** (ask them to send a test event so we can verify the integration)

## What to do when the first real event lands

1. **Verify the row in `fee_events`** — should have `source=<carrier_name>`, `status=paid`, real `settled_amount` and `fee_amount`.
2. **Confirm the contractor + lead link** — `contractor_id` and `lead_id` should be filled in if the dispatch was linked to a real contractor.
3. **Update the daily money digest** — the `real_insurance` total should now reflect the real amount, not the mock $3,750.
4. **Send a Telegram alert** — the autoresearch + money_report scripts both check `real_revenue` and report it. The first real revenue event triggers a celebration in the digest.

## What's left to do

- [ ] Wait for carrier responses (drafts sent 2026-06-16, will likely take 1-2 weeks)
- [ ] When a carrier responds with a partner program, do the technical integration (10 min per carrier)
- [ ] Send a test event to verify
- [ ] Update the `source` field mapping per carrier
- [ ] Document the real-world SLA (do they retry on failure? how long until the event fires after settlement?)

## Why the mock matters

Until we have real carriers, the mock is how we validate the chain end-to-end:

```
storm alert → radar_target → enriched_lead → lead_converter → storm_strike sequence
       → homeowner replies YES → contractor_dispatch → claim created via mock
       → claim settled via mock → fee_event written → daily digest shows money
```

When a real carrier is wired in, **only the "claim settled" step changes**.
Everything upstream (storm → lead → dispatch) is the same. **One
integration per carrier = one real money event per settlement.**

## Edge cases to handle

- **Duplicate webhooks:** the hub's `fee/claim-settled` endpoint should dedup
  on `claim_id`. If the same carrier sends the same event twice (network
  retry), the second one is a no-op.
- **Out-of-order events:** if a webhook arrives before the dispatch is
  linked to a contractor, the fee_event is still created but with null
  contractor_id. The link can be backfilled later.
- **Time zone:** the `settled_at` field accepts any ISO 8601 timestamp.
  We store it as UTC. The daily digest handles the conversion.
- **Currency:** the `settled_amount` is in USD. Multi-currency carriers
  need to convert before sending. (Most US carriers are USD-only.)

## File map

| File | Purpose |
|---|---|
| `empire_carrier.py` | Mock carrier API. Read-only once real carriers are wired. |
| `hub.py` | The `/api/v1/fee/claim-settled` endpoint that real webhooks hit. |
| `fee_events` (Supabase table) | The ledger of settled claims + fees. |
| `carrier_outreach_drafts/*.txt` | The 5 emails to carriers (already sent). |
