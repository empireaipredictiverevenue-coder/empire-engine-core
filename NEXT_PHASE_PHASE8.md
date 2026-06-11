# PHASE 8: PULSE + HARDENING + BRIDGE

## OBJECTIVE
Three parallel tracks ship together as Phase 8:
1. **Pulse view** — the insight layer at `/view/pulse`. The dashboard no
   competitor has because they don't have the underlying data model.
2. **Production hardening** — close the operational gaps (leaked key,
   missing signing path, dead CI workflow, untested configurators).
3. **Bridge view** — the full-screen voice-first experience at `/bridge`.

This is the "ship the empire" phase. After this, every module has a
front-end, the system can actually pay out, and the deploy story is
real.

---

## WHY THIS PHASE MATTERS

- **Pulse** is what makes the data moat visible. Right now the data is
  there (per-lane MRR, per-niche health, per-corridor outcomes) but the
  operator can't see it. Pulse makes the invisible visible.
- **Hardening** closes the gaps that would block a real customer
  onboarding: you can't legally pay out USDC without finishing the
  signing path, you can't deploy via GitHub Actions without the workflow,
  you can't trust the SI configurators without unit tests.
- **Bridge** is the showpiece. The voice-first interface is the demo
  that closes enterprise deals.

---

## TRACK 1 · PULSE VIEW

### MODULES
- `empire_pulse.py` (new) — rollup engine + view template
- `migrations/003_pulse_rollup.sql` (new) — materialized view + indexes
- `empire_command_spa.py` (modify) — add Pulse section component
- `hub.py` (modify) — register `/view/pulse` route + `/api/pulse/*` APIs

### WHAT IT SHOWS

Per-niche, per-corridor, per-contractor, per-channel, per-hour ROI.
Five breakdowns the operator can switch between with a tab control.

```
┌─────────────────────────────────────────────────────────────┐
│  PULSE · 24h                  [Niche|Channel|Contractor|...] │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  Revenue     │  │  Spend       │  │  Margin      │       │
│  │  $1,247      │  │  $312        │  │  75%         │       │
│  │  ▲ +18%      │  │  ▼ -3%       │  │  ▲ +5pp      │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │  Per-lane bar chart                              │       │
│  │  Lane 0 ████████████ $312                        │       │
│  │  Lane 1 ██████ $168                              │       │
│  │  ...                                             │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │  Hourly heatmap (24h × 4 niches)                 │       │
│  │  00 01 02 03 04 05 06 07 08 09 10 11 12 ... 23    │       │
│  │   .  .  .  .  .  .  .  .  █  █  █  █  █  ...  .   │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### SUPABASE SCHEMA

```sql
-- Materialized view, refreshed every 5 min by a cron in hub.py
CREATE MATERIALIZED VIEW IF NOT EXISTS pulse_rollup_hourly AS
SELECT
  date_trunc('hour', created_at) AS hour_bucket,
  niche,
  corridor,
  channel,
  contractor_id,
  SUM(fee_earned) FILTER (WHERE is_billable) AS revenue,
  COUNT(*) AS calls,
  SUM(cost_usd) AS spend,
  SUM(fee_earned) FILTER (WHERE is_billable) - SUM(cost_usd) AS margin
FROM call_logs
WHERE created_at > now() - interval '7 days'
GROUP BY 1, 2, 3, 4, 5;

CREATE UNIQUE INDEX IF NOT EXISTS pulse_rollup_hourly_pk
  ON pulse_rollup_hourly (hour_bucket, niche, corridor, channel, contractor_id);
CREATE INDEX IF NOT EXISTS pulse_rollup_hourly_hour
  ON pulse_rollup_hourly (hour_bucket DESC);
```

### API ENDPOINTS

- `GET /api/pulse/summary?window=24h|7d|30d` — totals + deltas
- `GET /api/pulse/breakdown?dimension=niche|channel|contractor|corridor|hour` — grouped data
- `GET /api/pulse/lanes` — per-lane table
- `POST /api/pulse/refresh` — force materialized view refresh (owner-only)

### SUCCESS METRICS
- Page loads in < 500ms with 7d window
- All 5 dimensions switch in < 100ms
- Hourly heatmap renders 168 cells × 4 niches = 672 cells
- Materialized view refreshes in < 5s

---

## TRACK 2 · PRODUCTION HARDENING

### TASKS

1. **Key rotation runbook** — `docs/KEY_ROTATION.md` (new)
   - Documents the leaked `private.key` situation
   - Step-by-step Solana key rotation (generate new → update env → redeploy → wipe old)
   - 30-day rotation policy

2. **Solana signing path** — `empire_payouts.py` (modify)
   - Replace `NotImplementedError` in `_build_and_send_usdc_transfer`
   - Use `solders` library (already in requirements)
   - Real on-chain transfer with retry + confirmation polling
   - Start with devnet, add mainnet switch via `EMPIRE_SOLANA_NETWORK`

3. **CI workflow** — `.github/workflows/deploy.yml` (fix)
   - Currently broken: no trigger, no secrets, no actual deploy
   - Add: push-to-master trigger, `dokku` remote add, git push, smoke test
   - Required secrets: `DOKKU_SSH_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `VONAGE_*`, `ANTHROPIC_API_KEY`

4. **Unit tests for SI configurators** — `tests/test_si_configurators.py` (new)
   - Test each apply_fn with valid + invalid inputs
   - Test cache invalidation for switchboard
   - Test weight sum assertion for matching
   - Test rejection of out-of-range values
   - Run with `pytest tests/test_si_configurators.py`

5. **`.env.example`** — `.env.example` (new)
   - Full list of env vars with comments
   - No real secrets, just placeholders
   - CI fails if any required var missing at startup

### SUCCESS METRICS
- `pytest tests/` passes with > 80% line coverage on configurator code
- `empire_payouts.py` can send a $0.01 USDC tx on devnet end-to-end
- GitHub Actions: green check on every push to master
- `KEY_ROTATION.md` reviewed by you (the operator)

---

## TRACK 3 · BRIDGE VIEW

### MODULES
- `empire_bridge.py` (new) — full-screen voice-first experience
- `migrations/004_bridge_sessions.sql` (new) — bridge session log
- `empire_command_spa.py` (modify) — link to /bridge from main nav
- `hub.py` (modify) — register `/bridge` route + WebSocket

### WHAT IT SHOWS

A single screen, no chrome, no nav, no other modules visible. Just:

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│                                                              │
│                                                              │
│                       ┌──────────┐                          │
│                       │          │                          │
│                       │   🎙     │                          │
│                       │          │                          │
│                       └──────────┘                          │
│                                                              │
│                  "Listening..."                             │
│                                                              │
│         "Press space, click, or just talk"                  │
│                                                              │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │  Recent transcript:                              │       │
│  │  > "show me hottest leads in Dallas"             │       │
│  │  < 3 leads in Dallas · top: 1234 Main St · $9k   │       │
│  │  > "approve the top one"                         │       │
│  │  < ✓ Lead accepted for dispatch                  │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│                              [esc] to close                 │
└─────────────────────────────────────────────────────────────┘
```

### INTERACTION MODEL

- Continuous listening (Web Speech API, falls back to space-to-talk)
- Single transcript stream — no separate input box
- Responses stream in as they're generated
- Destructive actions show a confirmation card inline
- `esc` to close, returns to normal SPA

### SUPABASE SCHEMA

```sql
CREATE TABLE IF NOT EXISTS bridge_sessions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at   timestamptz NOT NULL DEFAULT now(),
  ended_at     timestamptz,
  operator_id  uuid REFERENCES operators(id),
  duration_sec int,
  actions_taken int DEFAULT 0,
  meta         jsonb DEFAULT '{}'::jsonb
);
```

### SUCCESS METRICS
- Page loads in < 300ms
- Voice → text → action round-trip in < 2s
- Confirmation flow: action shows card → operator says "confirm" → fires
- 10-minute bridge session uses < 1MB bandwidth

---

## EXECUTION ORDER

1. **Week 1: Hardening first** — get key rotation, signing path, CI, tests
   out of the way. These are foundational, not user-facing.
2. **Week 2: Pulse** — front-end heavy, uses hardened infra from week 1.
3. **Week 3: Bridge** — showpiece, uses Pulse data + hardened infra.

This order means: if we have to ship early, we still have a hardened
system with Pulse as the visible win.

---

## COMMIT STRATEGY

Like Phase 7, ship as logical chunks:
1. `chore(hardening)` — KEY_ROTATION.md + .env.example
2. `feat(payouts)` — finish Solana signing path + tests
3. `chore(ci)` — fix deploy.yml + add test workflow
4. `test(si)` — unit tests for SI configurators
5. `feat(pulse)` — pulse rollup + view + API
6. `feat(bridge)` — bridge view + sessions

Total: 6 commits. Read in order they make a complete narrative.

---

## WHAT'S COMING AFTER PHASE 8

Phase 9 · Brain personality
- Operator-configurable persona (conservative / aggressive / balanced)
- Per-niche brain instances
- Memory of operator preferences over time

Phase 10 · Multi-tenant
- Org-level isolation in Supabase (row-level security)
- Per-tenant billing + payouts
- White-label SPA

Phase 11 · Mobile
- React Native shell
- Push notifications for urgent brain GOs
- Offline playbook queue

---

## ENVIRONMENT VARIABLES · Phase 8 additions

```bash
# Pulse
PULSE_REFRESH_INTERVAL_SEC=300          # materialized view refresh cadence
PULSE_DEFAULT_WINDOW=24h                # default time window

# Bridge
EMPIRE_BRIDGE_ENABLED=true              # toggle the /bridge route
EMPIRE_BRIDGE_LISTEN_MODE=continuous    # continuous | push-to-talk

# Solana (Payouts hardening)
EMPIRE_SOLANA_NETWORK=devnet            # devnet | mainnet-beta
EMPIRE_SOLANA_COMMITMENT=confirmed      # processed | confirmed | finalized
EMPIRE_SOLANA_TIMEOUT_SEC=30

# CI (no env, all in GitHub secrets)
# DOKKU_SSH_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY,
# VONAGE_API_KEY, VONAGE_API_SECRET, VONAGE_APPLICATION_ID,
# VONAGE_NUMBER, ANTHROPIC_API_KEY, OPENAI_API_KEY
```

Set them with:
```bash
dokku config:set empire-ai-uk \
  PULSE_REFRESH_INTERVAL_SEC=300 \
  PULSE_DEFAULT_WINDOW=24h \
  EMPIRE_BRIDGE_ENABLED=true \
  EMPIRE_SOLANA_NETWORK=devnet \
  EMPIRE_SOLANA_COMMITMENT=confirmed \
  EMPIRE_SOLANA_TIMEOUT_SEC=30
```

---

## SUCCESS CRITERIA · THE WHOLE PHASE

- [ ] Operator can see ROI broken down 5 ways at /view/pulse
- [ ] $0.01 USDC test tx confirms on devnet end-to-end
- [ ] GitHub Actions green on every push to master
- [ ] pytest passes with > 80% coverage on configurator code
- [ ] /bridge voice-first experience works in Chrome + Safari
- [ ] `KEY_ROTATION.md` reviewed and signed off
- [ ] `.env.example` is the source of truth for env vars
- [ ] All commits follow the prefix taxonomy (chore/feat/fix/test/docs)
- [ ] No regression: existing SPA panels still render

---

## THE EMPIRE GETS A PULSE, A BRIDGE, AND A SAFETY NET. SHIP IT.
