---
tags: [resend, webhook, tracking, mrr, 2026-06-22]
---

# Resend Webhook — Open/Click Tracking (2026-06-22)

**Status:** Live at `/api/v1/resend/webhook`. Signature-verified. Tested with
3 event types (opened, clicked, bounced). DB updates verified.

## Endpoint

```
POST /api/v1/resend/webhook
Content-Type: application/json
Resend-Signature: t=1234567890,v1=abc123def...
```

## Events handled

| Event | Action |
|-------|--------|
| `email.delivered` | update `delivered_at` |
| `email.opened`    | update `opened_at` |
| `email.clicked`   | update `clicked_at` |
| `email.bounced`   | update `status = 'bounced'` (skip future retries) |
| `email.complained` | update `status = 'unsubscribed'` |

All other events: 200 OK with `unhandled event` body. Never crash on unknown types.

## Signature verification

Resend sends `Resend-Signature: t=<unix_ts>,v1=<hmac_sha256>`. We:
1. Reject events older than 5 minutes (replay protection)
2. Compute `HMAC-SHA256(RESEND_WEBHOOK_SECRET, f"{t}.{raw_body}")`
3. Compare with `v1=` value (constant-time)

Tests:
- Unsigned POST → 401 invalid signature
- Signed POST with valid event → 200, DB updated

## Tag correlation

Each outbound email in `scripts/contractor_outreach.py` now includes:
```python
payload["tags"] = [{"name": "outreach_id", "value": row["id"]}]
```

Webhook reads `data.tags[]`, finds the `outreach_id` tag, updates that row.
No need for email→contractor lookup table.

## How to activate (Resend dashboard)

1. Login to resend.com → Webhooks → Add Endpoint
2. URL: `https://empire-ai.co.uk/api/v1/resend/webhook`
3. Events to send: email.delivered, email.opened, email.clicked,
   email.bounced, email.complained
4. Save → Resend sends a test event to verify

Once wired, the existing 249 sent emails will start generating events.
Open/click rates will populate automatically.

## What this enables

- **A/B subject lines**: see which subject lines get opened most
- **Conversion funnel**: track email → open → click → /for-contractors → pay
- **List hygiene**: bounces marked, future sends skip them
- **Unsubscribe compliance**: complaints stop further outreach

## File diff

- `empire_resend_webhook.py` (new, 5.3KB) — webhook handler + signature verify
- `hub.py` — 1 import + 1 route registration
- `scripts/contractor_outreach.py` — tag each email with outreach_id

## Verified live (2026-06-22 15:18 UTC)

- POST `/api/v1/resend/webhook` (no sig) → `401 invalid signature` ✓
- POST signed event type=email.opened → `200 {"ok":true,"event":"email.opened"}` ✓
- POST signed event type=email.clicked → `200 {"ok":true,"event":"email.clicked"}` ✓
- POST signed event type=email.bounced → `200 {"ok":true,"event":"email.bounced"}` ✓
- DB row updated: opened_at + clicked_at populated, status='bounced' ✓

## Related

- [[Contractor_Outreach_2026-06-22]] — the campaign that produces the events
- [[MRR_System_2026-06-22]] — what they convert into
- [[Brain_MiniMax_Live_2026-06-22]] — brain can summarize which templates convert best