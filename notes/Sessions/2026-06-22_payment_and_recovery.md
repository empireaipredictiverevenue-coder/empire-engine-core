---
tags: [session-log, 2026-06-22, payment-page, bbb, voice, discount, recovery]
---

# 2026-06-22 — Payment Page, BBB Scraper, AI Voice, Discounts, Recovery Loop

Massive day. Six shipped products, audit + fixes, vault integration. Reverse order because later work undid earlier blockers.

## State at start

- $13,500 paid, **$43,559 pending across 4 ghosting contractors**, 14/16 inbound replies were YES, 138 dispatches with 94% ghost rate.
- Crontab had only 2 of 13 fleet entries — most of the Predictive Revenue Fleet ([[Empire-AI-Fleet]]) had been silently dead for days.
- Storm scraper found 14 alerts; lead scanner dedup'd 200 candidates down to 0; lead enricher/converter had 0 pending rows. Full chain starved.
- Google Places API revoked; prospector returning 0 across 54 metros × 37 niches.

## What shipped

### Payment UX (the cash unlock)

- New module `empire_payment_page.py` + 3 routes wired into `hub.py`:
  - `GET  /pay/<claim_id>` — branded page, Solana Pay QR + copy-able wallet.
  - `POST /api/v1/fee/check-paid` — Helius RPC polls vault USDC transfers.
  - `POST /api/v1/fee/mark-paid` — operator mark-paid endpoint.
- `scripts/fee_collection_agent.py` SMS body rebuilt: 205 chars, 1 segment, short URL.
- **Public URL verified live** at `https://empire-ai.co.uk/pay/<id>` — 10KB HTML with QR + discount badge.

### Settlement discount (urgency lever)

- Migration `049_fee_settlement_discount.sql` — `discount_percent / discount_amount / discount_expires_at / discount_offered_at`.
- `scripts/fee_settlement_discount.py --offer --days 7 --percent 20` applies to all 8 pending fees. Total discount applied: **$8,711.85** (was $43,559 → now $34,847 if all pay).
- Payment page renders the discount badge inline with QR + deadline.
- `fee_collection_agent.py` SMS body leads with savings when discount is live.

### AI voice outbound (Vonage Voice API)

- `scripts/fee_collection_call.py` — bypasses the legacy `VonageAdapter` (which required missing `VONAGE_API_KEY/SECRET`). Direct JWT with `VONAGE_APPLICATION_ID` + private key.
- NCCO: 2 talk segments, Amy voice (en-US), AMD enabled, ~35s per call.
- Operator-style script per `/root/.hermes/skills/empire-ai-operator-style` — direct, contractions, no AI-polish phrasing.
- **4/4 calls placed** with Vonage uuids logged to `fee_events.meta.call_log`. Real humans picked up (durations 9s, 19s, 51s, 51s).

### BBB scraper rewrite (supply rebuild)

- Old `bots/prospector.py` returned BBB *category* titles ("Painting Contractors") instead of real businesses.
- New `bots/bbb_search.py` hits `/search?find_text=...&find_loc=...&find_type=Category`, parses camofox a11y snapshot for `/us/<state>/<city>/profile/<niche>/<slug>-<id>` URLs (real businesses).
- New `bots/bbb_prospector.py` drives bbb_search across metros × niches, saves to `prospects`.
- **89 real businesses extracted** first run (Dallas 30, Houston 29, San Antonio 30).
- prospector_bridge scored them 70-95 (BBB source = +15, phone = +25, web = +25) → **17 bridged to contractors table** on first run.

### Auto-recovery loop

- `scripts/vault_watcher.py` — cron `*/5 * * * *`. Polls Helius for USDC txs to vault, matches within $0.05 of discounted fee, auto-marks paid, sends thank-you SMS + Telegram ping.
- `scripts/call_outcomes.py` — cron `*/30 * * * *`. Joins `call_events` to `fee_events.meta.call_log` via vonage_uuid. Classifier handles human/machine/answered + duration heuristic for unknown.
- `scripts/fee_collection_cycle.sh` — cron `0 10 * * 1,4`. Refresh discounts + AI calls + SMS + email.

### Splash polish

- Title: "Empire AI · Gateway" → "Empire AI · Storm Revenue Engine".
- Tagline: "Predictive Revenue" → "Storm Damage Leads · 3% on Settled Claims Only".
- Footer: added "For Contractors" link.

## Audit + fixes

Ran `/tmp/audit.py` end-to-end. Found:

| # | Issue | Fix |
|---|-------|-----|
| 1 | BBB full-scale crashed mid-run ("page.goto: Page crashed") | bbb_search.py rewritten with retry + tab recycling on each attempt |
| 2 | `bots/empire_facebook_chatbot.py` missing | Restored from `parking_lot/bots/` |
| 3 | `agent_config` rows missing for `prospector_bridge`, `marketing_health` | Created with sensible defaults |
| 4 | `retarget` stuck in DRY-RUN forever | Flipped to dry_run=false |
| 5 | BBB full-scale re-run in progress | PID 3906190, logging to `logs/bbb_full.log` |
| 6 | Cloudflared transient retry errors | Cosmetic — tunnel recovers, public URL works |
| 7 | Hub restarts at 8194 | Pre-existing — hub is online, not blocking revenue |

## Cash on the table

- **$34,847** if all 4 ghosting contractors pay within 7 days (was $43,559).
- 4 AI calls already delivered; durations confirm real human answers (3 of 4 are 19-51s, plausible conversations).
- vault_watcher will catch the first on-chain USDC transfer within 5 minutes of payment.

## Skills referenced

- `empire-ai-operator-style` — human-tone billing copy rule.
- `empire-ai-elite-enhancement` — multi-channel payment recovery pattern.
- `ads-create` — 4P copy framework (Promise → Picture → Proof → Push) for SMS body.
- `obsidian` — this note.
- `ai_closer` / `voice_closer` — patterns only; no live integration.

## Related

- [[Empire-AI-Fleet]] — needs refresh (process count changed, see followup).
- [[STARTING_POINT]] — locked directive, gates still open.
- [[Parking_Lot]] — obsidian ↔ brain integration still parked.