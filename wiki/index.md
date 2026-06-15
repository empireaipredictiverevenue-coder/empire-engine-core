# index.md — the empire-ai wiki catalog

The content catalog. Every wiki page has an entry here with a
one-line summary. **This file is the LLM's first stop on every
query.** If a topic isn't here, the wiki doesn't have it.

Pages are grouped by topic. Within a group, the most-recently-updated
page is listed first.

## Architecture

- [`architecture.md`](architecture.md) — what empire-ai is, the
  locked-directive metric, the funnel shape.
- [`locked-directive.md`](locked-directive.md) — the 4-step definition
  of "done" (splash, lead, contractor, fee).

## Pipeline

- [`dispatcher.md`](dispatcher.md) — the runtime SMS dispatcher.
  Templates, send-time compliance gates, the 422 counter, quiet
  hours, the storm_strike v1/v2 A/B test.
- [`enricher.md`](enricher.md) — lead_enricher agent. Phone
  validation gate (rejecting bad area codes, fictional 555-XX).
- [`converter.md`](converter.md) — lead_converter agent. 50/50
  A/B split between storm_strike and storm_strike_v2 by lead id
  hash.
- [`prospector.md`](prospector.md) — bots/prospector.py + the
  prospector_bridge agent. The closed-loop from prospects table
  to contractors table.

## Contractors

- [`contractor-recruit.md`](contractor-recruit.md) — the 3-touch
  contractor sequence. Free-trial pitch, no-call ask, splash
  CTA, plus the REFER reply path.
- [`contractor-outreach.md`](contractor-outreach.md) — the
  recruiter agent that enrolls contractors in the recruit sequence.
  Runs every 4 hours.
- [`contractors-landing.md`](contractors-landing.md) — the
  /contractors public page + the self-onboard form + the chat
  widget (when buffy ships it).

## Quality control

- [`qc.md`](qc.md) — the sms_qc daemon. 8 checks, tier-1
  auto-remediate, tier-2 Telegram ping, tier-3 daily summary at
  23:00 UTC.
- [`qc-events-api.md`](qc-events-api.md) — the GET / PATCH
  endpoints for resolving QC events.

## Forecasting

- [`forecaster.md`](forecaster.md) — the predictive_revenue engine.
  8 functions, 4 input sources, sms_log-based calibration. The
  3x over-forecast gap, the audit, the fix.

## Operators

- [`hermes-dashboard.md`](hermes-dashboard.md) — the operator
  dashboard. Single endpoint that aggregates gateway, daemons,
  agent activity, funnel snapshot, QC summary, inbound stats.
- [`command-spa.md`](command-spa.md) — the /command SPA (operator
  view of the system).

## Compliance

- [`compliance.md`](compliance.md) — TCPA footer audit, DNC
  opt-out handling, STOP keyword processing, the synthetic-email
  bridge for prospects.

## Lanes

- [`lanes.md`](lanes.md) — the 36-lane grid the other agent
  shipped. Per-lane CPL benchmarks.

## Conventions

- [`AGENTS.md`](AGENTS.md) — this wiki's schema. Read first.
- [`log.md`](log.md) — chronological ingest log. Newest entries at
  the bottom.

## log

- 2026-06-14: index created (initial scaffold with 11 page stubs)
