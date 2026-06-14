# architecture.md — what empire-ai is

## One-liner

Empire AI is an autonomous revenue engine for commercial
storm-damage lead generation and contractor dispatch. A storm hits,
we text the property owner, they reply YES, we dispatch a vetted
contractor. The contractor pays 3% on the settled insurance claim.

## The funnel

```
NWS storm alert
  -> radar_targets (raw ingest from storm_scraper, runs 2x daily)
  -> enriched_leads (scoring + phone validation, agent runs every 30min)
  -> sms_sequences  (lead_converter enrolls, 50/50 v1/v2 split)
  -> property owner reply (opt-out via STOP, yes via YES, opt-in)
  -> dispatch (2 contractors per YES-reply, fan-out via email)
  -> claim settlement (the locked-directive "fee" event)
```

## The 3 services (and the fee model)

1. **Splash + landing pages** — `empire-ai.co.uk` (splash) and
   `empire-ai.co.uk/contractors` (contractor-recruit landing).
2. **Outbound pipeline** — radar scanner, enricher, converter,
   dispatcher, contractor_outreach recruiter.
3. **Self-serve onboarding** — `/contractors` has a form
   (`/api/contractors/onboard`) and (when buffy ships) a chat widget
   fed by synthetic_brain at `:8005`.

The fee: 3% on the gross settlement, paid within 30 days of fund.
First 2 closed deals are 100% complimentary (free trial framing).
**No contract, no exclusivity, no monthly minimum.**

## The 5 agents in the fleet

- `agents/lead_scanner` — runs every 30min, ingests NWS alerts
- `agents/lead_enricher` — runs every 30min, scores + phone-validates
- `agents/lead_converter` — runs every 15min, enrolls in sequences
- `agents/dispatch` — built into `empire_sms.py`, polls every 60s
- `agents/contractor_outreach` — runs every 4h
- `agents/prospector_bridge` — runs every 1h, moves prospects to
  contractors (committed 2026-06-14 as `cbf9ea6`)
- `agents/sms_qc` — long-running daemon, 60s tick, 8 quality checks
  (committed 2026-06-14 as `007aa47`)

## Tech stack (operational view)

- **Box**: Hetzner ubuntu-8gb-hil-2 at 5.78.148.141
- **Splash + landing + command SPA**: served by `empire-hub` on
  port 8000 via uvicorn
- **Vonage**: SMS gateway (`api.nexmo.com`)
- **Supabase**: `owbeinlfcfdtwcwrttjy.supabase.co`, REST API at
  6543, real-time websocket for live updates
- **Cron**: 8 cron entries + 1 long-running pm2 daemon
- **Synthetic brain**: llm at `synthetic_brain:8005` (Ollama /
  llama-server)

## What "good" looks like

- Storm pipeline: 1+ new lead per day per active metro
- Convert rate: 5-10% of contacted leads reply YES
- Contractor reply rate: 10-20% within 14 days of the v2 sequence
- Settlement cycle: 30-60 days from claim file to fund

## What "broken" looks like

- 422 floods: phones that Vonage rejects (bad area codes, fictional
  555-XX). Should be < 1% of sends.
- SMS log: `delivered=false` rows older than 5min without a
  follow-up 422 entry. Means a phone is in a bad state.
- `sms_sequences` stuck at step 0, status=active, > 48h old. Means
  the dispatcher is wedged.
- Dispatcher poll > 90s between ticks. Means the loop is slow.

## See also

- [`locked-directive.md`](locked-directive.md) — the metric.
- [`dispatcher.md`](dispatcher.md) — the most-active service.
- [`qc.md`](qc.md) — the watcher that catches "broken" early.

## log

- 2026-06-14: created (initial scaffold)
