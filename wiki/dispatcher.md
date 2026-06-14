# dispatcher.md — the runtime SMS dispatcher

## What it is

The SMS dispatcher is the `SMSSequenceEngine` class in
`/root/empire-v49/empire_sms.py`. It's a long-running async loop
inside the `empire-hub` pm2 process (pid rotates on restart). It
polls every 60s for due sequences, sends via Vonage, advances
state, and handles errors.

## Lifecycle of a single sequence

1. **Enroll**: `/api/v1/sms/enroll` (called by `lead_converter`)
   inserts a row in `sms_sequences` with `status=active`,
   `current_step=0`, `next_send_at=now()`. Meta carries the lead id
   and the body preview.
2. **Send**: dispatcher's poll finds the row, renders the template
   for the current step, calls `voice_router.send_sms`, logs the
   attempt to `sms_log` with `delivered = result.ok`.
3. **Advance**: if delivered, `current_step += 1`, schedule next
   touch via `STEP_DELAYS.get(next_step, timedelta(hours=24))`.
4. **Reply**: an inbound SMS hits `/api/v1/sms/inbound` ->
   `handle_inbound`. If body is in `STOP_KEYWORDS`, opt out. If
   body is YES, mark the sequence `replied`. Anything else,
   `replied` too (treated as a human reply, no further sends).

## The 13 templates (5 + 5 + 3)

| sequence | step | angle | commit |
|---|---|---|---|
| `storm_strike` | 1 | initial contact + opt-out | runtime |
| `storm_strike` | 2 | social proof (now: "Other property owners in your area are being contacted") | ff27c69 |
| `storm_strike` | 3 | value math ($2M -> $250K -> $2,500 fee) + STOP | ff27c69 |
| `storm_strike` | 4 | last-call + STOP | ff27c69 |
| `storm_strike` | 5 | final + STOP confirm | runtime |
| `storm_strike_v2` | 1 | scarcity initial + STOP | 4d153ad |
| `storm_strike_v2` | 2 | scarcity reinforce + STOP | 828359a (this turn) |
| `storm_strike_v2` | 3 | soft social proof + STOP | ff27c69 |
| `storm_strike_v2` | 4 | last-call scarcity + STOP | 4d153ad |
| `storm_strike_v2` | 5 | slot-filled soft opt-out + STOP | 4d153ad |
| `contractor_recruit` | 1 | free-trial pitch + STOP + splash CTA | 114ce2d |
| `contractor_recruit` | 2 | demo follow-up + REFER ask + STOP | 114ce2d / 4d153ad |
| `contractor_recruit` | 3 | soft close + REFER + STOP | 114ce2d / 4d153ad |

All 13 templates have `Reply STOP to opt out` (verified 2026-06-14).

## The compliance gates

The dispatcher sends in a specific order, **with two compliance
gates now in place**:

1. **Quiet hours** — DFW is in CDT (UTC-5/6). Quiet hours
   (21:00-08:00 local) reschedules to 8:05am next day via
   `_is_quiet_hours(phone) -> _reschedule_after_quiet(row)`.
2. **Send-time opt-out check** (commit `ff27c69`) — before every
   `voice_router.send_sms` call, the dispatcher checks
   `compliance.is_opted_out(phone)`. If true, mark the sequence
   `replied` with `blocked_reason=opted_out_at_send` and skip.
3. **Send-time DNC check** (same commit) — same pattern with
   `compliance.is_on_dnc(phone)`. DNC list was previously only
   checked at enroll time (in the converter); now also at send
   time, in case a phone was added to DNC after enrollment.

The send-time gates were the missing piece identified by the
compliance audit (commit 828359a's prior). Without them, a
phone added to DNC post-enrollment would still receive sends.

## The 422 counter (commit 0e0b6a1)

When `voice_router.send_sms` returns `ok=False` (typically 422
from Vonage for bad recipients), the dispatcher:

1. Increments `meta.failed_send_count`.
2. At 3 consecutive failures, marks the sequence `replied` with
   `blocked_reason=consecutive_send_failures` so the poll skips it.

**Why this matters**: with 12 known-bad phones, the dispatcher
was wasting ~360 cron cycles/hr (12 phones * 60s polls). The
counter caps that at 3 cycles per phone (~3 minutes) then the
phone is permanently skipped.

**Known false-positive risk**: Vonage 422s for fictional 555-XX
phone numbers. The 12 caught on 2026-06-14 are a mix of
hand-seeded fictions + storm-pipeline data with unassigned area
codes (275, 384, 178).

## The A/B test (commit 4d153ad)

`lead_converter` does a 50/50 split between `storm_strike` and
`storm_strike_v2` based on `md5(lead.id) % 2`. Same lead id
always picks the same cohort. Reply-rate comparison is clean over
a week.

`storm_strike` = urgency + social proof + value math (3 angles
proven in marketing).
`storm_strike_v2` = scarcity ("1 slot in your area this week").
**Hypothesis**: scarcity wins for storm-damage leads (time-sensitive
property). **Measurement window**: ~7 days. If v2 reply rate > v1
by 1.5x, swap the default.

## Known gaps

- `handle_inbound` for `NOTNOW` keyword: marks the sequence
  replied (treated as opt-out). Doesn't preserve the "ask again
  next quarter" promise that the v2 copy makes. **bug, not
  critical.**
- `compliance.has_consent` is defined but never called. The
  converter checks it at enroll; if you wanted a re-check on
  every send, that'd be a 1-line addition.
- The dispatcher's `voice_router.send_sms` is sync (urllib). If
  Vonage is slow, the loop is slow. **No async batching.** Could
  be 10x faster with httpx async.

## See also

- [`compliance.md`](compliance.md) — the full TCPA story
- [`qc.md`](qc.md) — the watcher that catches dispatcher
  regressions (stuck sequences, gate regressions, etc.)
- [`architecture.md`](architecture.md) — where the dispatcher
  fits in the funnel

## log

- 2026-06-14: created (initial scaffold; 13 templates, 2 send-time
  compliance gates, 422 counter, A/B test all live)
