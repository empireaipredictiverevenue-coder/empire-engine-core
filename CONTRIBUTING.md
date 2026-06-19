# Contributing to Empire V49

Welcome! This guide gets you from a fresh clone to a running dev
environment. For the project's history and commit conventions, see
[CHANGELOG.md](CHANGELOG.md).

---

## Getting Started

### 1. Clone & install

```bash
git clone <repo-url> empire-v49
cd empire-v49
pip install -r requirements.txt
```

The SPA uses ESM imports from `esm.sh` — **no `npm install` needed**. All
React/htm dependencies load from the import map in `empire_command_spa.py`.

### 2. Environment variables

Create `/root/.env` (or set in your shell) with the following:

```bash
# Supabase (required)
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_KEY=<service-role-key>

# Auth (required)
HUB_TOKEN=<long-random-string>
PUBLIC_BASE_URL=http://localhost:8001

# Vonage / voice (required for outbound calls)
VONAGE_API_KEY=<key>
VONAGE_API_SECRET=<secret>
VONAGE_APPLICATION_ID=<app-id>
VONAGE_NUMBER=<E.164 number>
VONAGE_PRIVATE_KEY_PATH=/root/empire-v49/private.key

# LLM providers (at least one required)
ANTHROPIC_API_KEY=<key>      # for empire_console + narrator
OPENAI_API_KEY=<key>         # for embeddings + fallback
OLLAMA_URL=http://localhost:11434  # for empire_brain_decide + empire_agi

# Email (required for outreach)
RESEND_API_KEY=<key>
FROM_ADDRESS=noreply@empire-ai.co.uk
FROM_NAME="Empire AI Operations"

# Payouts (required for Solana settlements)
EMPIRE_VAULT_WALLET=<solana-address>
EMPIRE_OPS_WALLET=<solana-address>
EMPIRE_SIGNING_KEY=<base58-private-key>
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Optional
NTFY_TOPIC=<topic>           # for push notifications
NTFY_TOKEN=<token>
EMPIRE_OPERATOR_NUMBER=<E.164>  # for inbound call routing
EMPIRE_POSTAL_ADDRESS="Empire AI Ltd"
EMPIRE_SENDER_NAME="Empire AI Operations"
PAYOUT_AUTO_APPROVE_USD=0    # 0 = require owner approval
STORM_POLL_INTERVAL_SEC=300  # storm orchestrator poll interval
STORM_LANE_COUNT=6
STORM_MAX_SENDS_PER_HOUR=50
STORM_MAX_SENDS_PER_DAY=200
STORM_BOUNCE_BREAKER_PCT=5
SI_FEED_CACHE_TTL_SECONDS=60 # dream SI feed cache TTL

# ⚠️  Required for production (insecure defaults otherwise)
WEBHOOK_SECRET=<long-random-string>  # /webhook/lead · default: empire_v49_secret
ADMIN_TOKEN=<long-random-string>     # /api/admin/seed · no auth if unset
```

### 3. Database migrations

Run the SQL migrations in order:

```bash
# Top-level numbered migrations (chronological)
for f in migrations/*.sql; do
  psql "$SUPABASE_DB_URL" -f "$f"
done

# Timestamped supabase migrations
for f in supabase/migrations/*.sql; do
  psql "$SUPABASE_DB_URL" -f "$f"
done
```

Or via the Supabase CLI:

```bash
supabase db push
```

### 4. Seed data (optional)

Bootstrap the new tables with sample data:

```bash
curl -X POST http://localhost:8001/api/admin/seed
```

If `ADMIN_TOKEN` is set in the env, include it as a header:

```bash
curl -X POST http://localhost:8001/api/admin/seed \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

### 5. Start the dev server

```bash
# Direct (foreground, with hot-reload)
uvicorn hub:app --host 0.0.0.0 --port 8000 --reload

# Production (background, via PM2)
pm2 start ecosystem.config.js
pm2 logs empire-hub
```

The SPA is served at `http://localhost:8001/command`. The legacy
server-rendered pages are at `http://localhost:8001/command/<section>`
(redirects to the SPA hash route).

---

## Project layout

See [CHANGELOG.md § Project Layout](CHANGELOG.md#project-layout) for a
table mapping each module to its purpose.

The codebase is organized into **horizontal feature slices** (revenue, SPA,
SI brain, dream loop, adaptive) rather than vertical tiers. Each feature
owns its modules, routes, SPA panels, and database migrations.

---

## Commit conventions

See [CHANGELOG.md § Commit Conventions](CHANGELOG.md#commit-conventions)
for the full prefix taxonomy, body rules, and chunking rules.

Quick reference:

- **Prefix**: `feat(<area>):` for features, `chore:` for misc, `fix:` for
  bugs, `refactor:` for internal, `docs:` for documentation, `infra:` for
  CI/CD.
- **First line**: ≤ 72 chars, imperative mood, no period.
- **Body**: 1-2 paragraphs explaining what and why, then bullets for the
  major pieces, then the wire-up impact.

---

## How to add a new feature

See [CHANGELOG.md § How to add a new feature](CHANGELOG.md#how-to-add-a-new-feature)
for the 7-step process.

Quick summary:

1. **Identify the slice** — revenue, spa, si, dream, adaptive, etc.
2. **Create or modify modules** — follow existing naming conventions.
3. **Add a migration** if the schema changes.
4. **Register routes in `hub.py`** — use the `register_*_routes` pattern.
5. **If SI-related**, add a subsystem configurator (apply_fn + read_fn).
6. **If operator-facing**, add a SPA panel.
7. **Commit with the right prefix and body**.

---

## Running tests

The project uses a mix of smoke tests and integration tests:

```bash
# Syntax check all Python modules
python3 -c "
import ast, glob
for f in glob.glob('*.py') + glob.glob('bots/*.py'):
    try:
        ast.parse(open(f).read())
        print(f'OK: {f}')
    except SyntaxError as e:
        print(f'FAIL: {f}: {e}')
"

# Smoke test: verify all subsystem configurators mutate real config
python3 -c "
import sys; sys.path.insert(0, '/root/empire-v49')
import empire_switchboard as sb, empire_matching as mt
import orchestrator_agent as orch, empire_outreach_agent as out
assert hasattr(sb, '_MIN_OFFERED_FOR_RATE')
assert hasattr(out, 'HOT_THRESHOLD')
assert hasattr(mt, 'SCORE_WEIGHTS')
assert hasattr(orch, 'CORRIDOR_MIN_INTERVAL')
print('All subsystem configurators: OK')
"

# Billing flow test
python3 test_billing_flow.py

# End-to-end: hit the SPA + API endpoints
curl http://localhost:8001/api/si/strategy | head
curl http://localhost:8001/api/si/adaptive | head
curl http://localhost:8001/api/revenue/forecast | head
```

---

## Background loops

Several modules run background loops on startup (registered in
`hub.py`'s `@app.on_event("startup")`):

| Loop | Interval | Module |
| --- | --- | --- |
| BrainLearning nightly tune | 24h | `empire_brain_learning` |
| SMS dispatcher | continuous | `empire_sms` |
| Email dispatcher | continuous | `empire_email` |
| Storm orchestrator poll | 5min | `empire_orchestrator` |
| Dream loop | continuous | `empire_dream` |
| Hourly digest | 1h | `empire_hourly_digest` |
| SEO loop | 6h | `bots/seo_agent` |
| SI evolution | 5min (evolve) / 60s (adopt) | `hub.py` `_si_evolution_loop` |
| Governor watchdog | 60s | `hub.py` `_gov_watchdog_loop` |

Check loop health:

```bash
# PM2 status
pm2 list

# Governor watchdog log
cat /root/empire-v49/governor_heal_log.jsonl | tail

# Session log (AGI snapshots + actions)
tail -f /root/empire-v49/empire_session_log.md
```

---

## Debugging tips

- **`/api/si/snapshot`** — full strategy evolution state
- **`/api/si/adaptive`** — subsystem configurator state + adoption log
- **`/api/revenue/forecast`** — revenue engine output
- **`/api/governor/health`** — AGI governor health (stale/healthy services)
- **`/api/v1/health/mesh`** — agent mesh + system health
- **`/api/agents/status`** — sniper fleet status
- **`/api/dream/latest-wisdom`** — latest dream insights
- **`/api/panel_court/pool`** — 10-agent panel pool

All require `Authorization: Bearer <HUB_TOKEN>` (or the magic-link
session token from `/auth/verify`).

---

## Code style

- Python: PEP 8, type hints where they clarify intent.
- JavaScript (SPA): modern ES2020+, htm tagged templates, no build step.
- SQL: lowercase keywords, explicit `IF NOT EXISTS` on DDL.
- Commit messages: imperative mood, present tense ("add feature" not
  "added feature").
- Module naming: `empire_<feature>.py` for core, `bots/<feature>.py` for
  autonomous agents.
