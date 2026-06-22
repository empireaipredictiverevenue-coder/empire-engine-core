---
tags: [fee-collection, cron, telegram, attention, 2026-06-22]
---

# Fee Attention System — 3 Cron Jobs (2026-06-22)

**Status:** Active. Three new cron jobs give Phil the right attention on the
$34k+ pending funnel without him checking the dashboard. Combined, they
cover the full lifecycle: pre-expiry urgency → daily visibility → post-expiry
high-touch.

## Jobs

### 1. `scripts/fee_urgency_push.py` — `0 * * * *` (hourly)

For pending fees with `discount_expires_at` in the next 24h: send a final-chance
SMS+email. Tone: direct, numbers up top, deadline up top. Marks the fee so
we don't re-push.

Example push:
> Empire AI: Marcus, in 5 hours your 750 discount expires.
> Pay 3,000 now → empire-ai.co.uk/pay/webhook-93dd7 STOP to opt out.

Marks `meta.urgency_pushed_at` and appends to `meta.urgency_pushes` for audit.

### 2. `scripts/fee_daily_report.py` — `0 9 * * *` (9am UTC daily)

Posts a tight ops report to Telegram (falls back to stdout if no bot token).
Format: cash summary → action item → funnel counts → expiring list → ghosting list.

Sample report (verified live 2026-06-22 09:18):
> 📊 Empire daily report — 2026-06-22
>
> Cash:
>   paid:    $13,500  (today: $0, last 7d: $13,500)
>   pending: $43,559
>   if all pay with discount: $34,847
>
> Action: 💀 8 ghosting contractors, no payments today. Top: Construction máster LLC $10,951. Send another nudge.

To activate: set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `/root/.env`.
Long messages are chunked at 4000 chars (Telegram limit).

### 3. `scripts/fee_expired_handler.py` — `30 * * * *` (hourly)

When a discount expires and the fee is still unpaid:
1. Mark `meta.discount_expires_at = now` (one-time, no double-mark).
2. Send up to 3 high-touch follow-up SMS with stronger language
   ("your discount has expired and the X fee is now due in full").
3. After 3 high-touch pushes, stop auto-nudging. (Future: route to
   manual review queue.)

Notifies Telegram on every run with the count of new expirations + pushes.

## Tunables (in scripts)

| Var | Default | Effect |
|-----|---------|--------|
| `RAG_MAX_CONTEXT_CHARS` | n/a | (this isn't RAG — leftover from earlier) |
| — | — | (no env knobs yet) |

Each script reads env at call time, so cron doesn't need restart for env changes.

## Cron schedule (current)

```
0 * * * *    fee_urgency_push.py            # hourly, top of hour
0 9 * * *    fee_daily_report.py            # 9am UTC daily
30 * * * *   fee_expired_handler.py         # hourly, half-past
```

## Verified live (2026-06-22)

- Daily report: ran, printed $34,847 pending summary with action item. Telegram skipped (no bot token in env).
- Urgency push: backdated one fee to expire in 6h, ran, sent SMS 202 Accepted + email 200 OK to Lakehills. Marked in DB.
- Expired handler: backdated one fee to expire 2h ago, ran, marked expired, sent high-touch push #1 (SMS 202). 0 → 1 push count.

## To activate Telegram push

```bash
echo 'TELEGRAM_BOT_TOKEN=...' >> /root/.env      # from @BotFather
echo 'TELEGRAM_CHAT_ID=...' >> /root/.env        # your chat id
# no cron restart needed — reads env per call
```

## File diff

- `scripts/fee_urgency_push.py` (new, 7.4KB)
- `scripts/fee_daily_report.py` (new, 7.2KB)
- `scripts/fee_expired_handler.py` (new, 7.0KB)
- crontab — 3 new entries

## What this enables

- The $34k pending funnel no longer sits in silence. Phil sees it every morning.
- Fees that are about to expire get a 24h-warning push, not a silent expiry.
- After expiry, contractors get up to 3 high-touch follow-ups before going cold.
- When vault_watcher sees the first on-chain payment, the daily report will
  show it as `paid_today` in the morning summary.

## Related

- [[Sessions/2026-06-22_payment_and_recovery]] — base payment funnel
- [[Brain_MiniMax_Live_2026-06-22]] — brain context (RAG includes these notes)
- [[Obsidian_RAG_2026-06-22]] — how the brain reads this kind of note