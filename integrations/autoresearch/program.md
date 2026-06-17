# Empire AI · Autoresearch

> Adapted from [karpathy/autoresearch](https://github.com/karpathy/autoresearch).
> The pattern: an AI agent modifies one file to optimize one measurable outcome.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: `jun16` (today). Branch `autoresearch/jun16` must not exist.
2. **Create the branch**: `git checkout -b autoresearch/jun16` from current master.
3. **Read the in-scope files**:
   - `prepare.py` — fixed constants, data prep, evaluation. **DO NOT MODIFY.**
   - `train.py` — the file you modify. The contractor_recruit SMS body builder.
   - `/root/empire-v49/agents/outreach/sms_sequences.py` — read-only reference. The original template lives there.
4. **Verify data exists**: Check that the agent has access to `/root/empire-v49/agents/contractor_outreach/`, `inbox_messages` table, and `sms_sequences` table. If not, the human needs to grant access.
5. **Initialize results.tsv**: Header row only. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

## Experimentation

Each experiment runs a **1-hour budget** of trials. The training script runs `uv run train.py` which:

1. Loads the existing `sms_sequences` table (4,253+ rows) + `inbox_messages` table (real reply labels).
2. For each candidate body template, simulates rendering + scores via:
   - **Reply-prediction score**: % of similar historical sequences that replied (label = `inbox_messages.classified_intent == "interested"`)
   - **Spam-score**: 0-100, lower is better. Penalties for spam triggers (ALL CAPS, !, $$$, "free", "guaranteed", "click here", excessive emoji, etc.)
   - **Length penalty**: 0-100, scores 0 if body is 130-160 chars, increases as length deviates. (Carrier SMS gateway limit is 160 chars.)
   - **TCPA compliance check**: 0 or 100. Must include sender identity, "STOP to opt out" language.
3. The agent modifies `train.py` (a single function — the body builder), re-runs the scorer, keeps the new body only if the **weighted score** improves.

**The goal**: maximize `0.5 * reply_rate + 0.3 * (100 - spam_score) + 0.2 * tcpa_score - 0.1 * length_penalty`.

**What you CAN do:**
- Modify `train.py` — the only file you edit. Change the body, the greeting, the value prop, the CTA, the send time.
- Add new helper functions in `train.py` (e.g. a function that picks a template variation based on metro).

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only.
- Modify the scorer. The metrics are fixed.
- Modify the dispatcher, the opt-out list, the carrier_outreach logic, or the fee ledger.
- Install new packages. Use only `requests`, `supabase`, `urllib`, `json`, `re` (standard lib + already-installed).
- Send real SMS to real contractors. **Test only against historical data.**

**The first run**: Your very first run must establish the baseline. Run the training script as is. It will:
1. Read the current `CONTRACTOR_RECRUIT` template from `sms_sequences.py`
2. Score it against the historical data
3. Write the baseline score to `results.tsv`

**Then you start modifying.** Each run is logged to `results.tsv` with: timestamp, body_hash, body_text, reply_rate, spam_score, tcpa_score, length_penalty, weighted_score, kept (yes/no).

**Simplicity criterion**: All else being equal, simpler is better. A 0.5% reply-rate improvement that adds 50 chars of fluff is probably not worth it. A 0.5% improvement from deleting a confusing clause? Definitely keep. A simpler body that scores equal? Keep it.

## What this isn't

This is not a tool that ships code. It is a tool that ships **body templates** to the SMS engine. After 30 days of experiments, the highest-scoring body is promoted to `agents/outreach/sms_sequences.py`'s default `CONTRACTOR_RECRUIT` template.

## Permissions

- `prepare.py`: read-only.
- `train.py`: write, this is what you optimize.
- `results.tsv`: append-only.
- All other empire-ai files: read-only reference.

## Why contractor reply rate

Empire-AI has 4,253+ active contractor_recruit SMS sequences. Reply rate today is ~0.1% (5 replies out of 4,253 sequences). Even a 1% improvement means 40+ more contractor conversations per quarter. The autoresearch loop runs nightly, no human needed, and uses real data (inbox_messages, sms_sequences) as the training set.

## Logistics

- Runs nightly at **02:00 UTC** (after money digest at 06:30 UTC, after Resend daily reset at 00:00 UTC).
- Each cycle: max 1 hour. Logs to `results.tsv`. Top result at end of cycle writes to a Telegram summary.
- Cron: `0 2 * * * cd /root/empire-v49/integrations/autoresearch && uv run train.py >> /root/empire-v49/logs/autoresearch.log 2>&1`
- Human-in-loop: a new "best" body is written to `train.py` after each cycle, but the actual deployment to `sms_sequences.py` is gated by Phil's review (one-click in Telegram: "deploy" or "skip").
