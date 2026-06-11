# Empire AI · Predictive Revenue — Outreach Agent

> **Status: content-layer only. Runtime dispatcher not built yet.**
> See "What this is and isn't" below.

The outreach agent is the part of Empire AI that talks to leads and contractors on your behalf. You're the builder, not a salesperson — this agent does the sales work.

## What this is

Three Python modules you can review, edit, and dry-run today:

| file | purpose |
|------|---------|
| `sms_sequences.py` | TCPA-compliant SMS copy for 3 sequences (storm_strike, contractor_recruit, lead_nurture) |
| `voice_scripts.py` | Phone scripts for 5 call types (initial_strike, no_answer_followup, callback_confirmation, contractor_handoff, opt_out_confirmation) |
| `compliance.py` | Single chokepoint that blocks any send/call that fails DNC, opt-out, consent, time-of-day, or rate-limit checks |
| `seed.py` | CLI helpers to drop your first real lead and contractor into Supabase |

Every message in `sms_sequences.py` and `voice_scripts.py` is a **template with `{{var}}` placeholders** — review the copy without needing any runtime wired up.

## What this isn't

- ❌ **Not a running cron** — there is no dispatcher loop in this package. Building it requires:
  1. Vonage JWT auth working (currently 401s — dashboard fix needed)
  2. At least 1 real contractor in the `contractors` table
  3. At least 1 real lead in `radar_targets` with `urgency_score >= 7`
- ❌ **Not connected to `empire_brain.py` yet** — the brain's `process_lead()` already writes to `hot_queue.json` / `raw_leads.json`, but the handoff to "enroll lead in storm_strike sequence" is the runtime piece that doesn't exist.
- ❌ **Not deployed** — these files live on the server in `/root/empire-v49/agents/outreach/` but are not yet imported by `hub.py` or any cron.

## Sequence triggers (when the runtime is built)

| sequence | fires on | goal |
|----------|----------|------|
| `storm_strike` | radar_targets row with `urgency_score >= 7` AND `tcpa_consent=True` AND not opted-out | get callback or reply → manual dispatch by you |
| `contractor_recruit` | contractors row inserted with `status='prospect'` | get contractor to accept dispatch terms |
| `lead_nurture` | `storm_strike` ends with `replies_count=0` | stay present, learn what they actually need |

## Compliance guarantees

`compliance.py` is the single gate. The runtime **must** call `can_send_sms()` or `can_place_call()` before every send. Returns `(allowed, reason)`. Five checks in order:

1. **`sms_opt_outs` table** → never re-contact (fail closed)
2. **`outbound_dnc` table** → never contact (fail closed)
3. **`tcpa_consent=True`** on the lead/contractor record (fail closed)
4. **Recipient local 8am-9pm** (uses `empire_utils.tz_for_areacode`, fails closed if unknown)
5. **Per-number daily cap** (default 3 SMS/day/number, configurable via `EMPIRE_MAX_SENDS_PER_NUMBER_PER_DAY`)

If Supabase is unreachable, the module:
- Fails **closed** for opt-out / DNC / consent (refuses to send) — TCPA liability
- Fails **open** for time-of-day / rate (logs and sends) — these are quality-of-service, not legal

## What needs to happen before this is useful in production

In order — these are the actual gates, not nice-to-haves:

1. **Fix the Vonage 401** — dashboard work, not code. App `f0fb5906-a75d-4a2c-90ad-981cce01cd7f` may be revoked or have rotated keys.
2. **Recruit 1 real contractor** — phone call, relationship, contract. No AI can do this for you.
3. **Run `pipeline.py` once** to get 10+ real leads in `radar_targets`.
4. **Verify `sms_sequences`, `sms_opt_outs`, `sms_log` tables exist** with the schemas in `/root/empire-v49/REVENUE_FLOW.md` (probed 2026-06-11, all three exist).
5. **Build the dispatcher cron** — 30-50 lines, runs every 5 min, queries sequences where `status='active' AND next_send_at <= now()`, calls `can_send_sms()` then the actual SMS engine.
6. **Build the voice dispatcher** — same pattern, uses `voice_scripts.get_script(name)` and `voice_router.place_strike_call()`.
7. **Add ONE line to crontab** that fires the dispatcher hourly.

## How to review this content layer

Preview a sequence message:
```
cd /root/empire-v49
python3 -c "from agents.outreach import sms_sequences; print(sms_sequences.get_message('storm_strike', 1))"
```

Preview a voice script:
```
python3 -c "from agents.outreach import voice_scripts; print(voice_scripts.get_script('initial_strike'))"
```

Dry-run a compliance check:
```
python3 -c "from agents.outreach import compliance; print(compliance.can_send_sms('+12142277528', consent_flag=True, area_code='214'))"
```

Drop your first real lead into Supabase:
```
python3 -m agents.outreach.seed \
    --address "123 Main St" --city "Wichita" --state "KS" \
    --phone "+13165551234" --urgency 9 --event "severe hail"
```

Drop your first real contractor:
```
python3 -m agents.outreach.seed contractor \
    --business "Acme Roofing" --contact-name "Jane Smith" \
    --phone "+13165555678" --state "KS"
```

## Branding

All copy carries the **Empire AI · Predictive Revenue** brand identifier. SMS prefix is configurable via `EMPIRE_SMS_PREFIX` env var (default: `Empire AI:`).
