# Empire V49 · Changelog

## Project Layout

Empire is a 32-lane autonomous lead-generation network. The codebase is organized
into horizontal feature slices (revenue, SPA, SI brain, dream loop, adaptive)
rather than vertical tiers (models/views/controllers). Each feature owns its
modules, routes, SPA panels, and database migrations.

| Directory / module | What it does |
| --- | --- |
| `hub.py` | FastAPI entry point. Wires all modules, registers routes, starts background loops. |
| `empire_*.py` | Core feature modules. Each owns one concern (orchestrator, voice, email, payouts, etc.). |
| `bots/*.py` | Autonomous agents (storm, SEO, panel court, mesh dispatchers, revenue brain). |
| `migrations/` | SQL migrations for Supabase. Numbered chronologically. |
| `supabase/migrations/` | Timestamped SQL migrations. |
| `scripts/` | One-off fix and diagnostic scripts. **Not part of the product.** |
| `templates/` | Email/video templates. |
| `outreach_drafts/` | Generated outreach content. Gitignored. |
| `logs/` | Runtime logs. Gitignored. |
| `index.html`, `command.html` | SPA entry points. |
| `empire_command_spa.py` | React SPA served at `/command`. One component per SPA section. |
| `bots/predictive_revenue.py` | Revenue engine: per-lane MRR, LLM narrative, few-shot learning. |
| `empire_si_*.py` | Synthetic Intelligence core: brain, strategy, adaptive engine. |
| `empire_dream.py` | Background dream loop: risk flags, wisdom, rule suggestions. |
| `empire_matching.py` | Contractor matching engine: score-based dispatch, trust evolution. |
| `empire_switchboard.py` | Call routing: buyer auction, cache, acceptance rate. |
| `orchestrator_agent.py` | AGI orchestrator: stats snapshot → Llama 3.2 → action. |

---

## Commit History

The 13 most recent commits (oldest → newest) form a logical narrative of the
SI + Revenue + Adaptive build-out followed by a docs/housekeeping pass.
Read them in order to understand how the system fits together.

### 1. `feat(revenue): predictive engine with per-lane MRR + LLM narrative + few-shot learning`

**Files:** `bots/predictive_revenue.py` (rewritten), `bots/revenue_brain.py` (new)

Rewrote the revenue engine from a single `pipeline_forecast()` into a full
per-lane system: `per_lane_forecast()`, `revenue_health_check()`,
`generate_llm_narrative()`, `comprehensive_forecast()`, and
`adaptive_forecast()` (few-shot from `brain_memory`). Lane-to-niche mapping
is loaded from `mesh_orchestrator` with a 4-niche fallback. 30s in-memory
cache avoids hammering Supabase when called by 4+ endpoints in rapid
succession. Wired into `/api/revenue/{forecast,lanes,health,accuracy}`
endpoints.

### 2. `feat(spa): SiAdaptive panel + SPA assets + entry points`

**Files:** `empire_command_spa.py` (SiAdaptive component + CSS + SECTIONS +
render dispatch), `command.html`, `index.html`, `package.json`

Added the `/api/si/adaptive` SPA panel: 4 stat tiles (subsystems registered,
adaptations applied, recent batches, status), a registered subsystems grid,
and an adoption log feed showing recent batches with per-key changes.
Auto-refreshes every 15s with a `cancelled` guard and `clearInterval` cleanup.
Also switched the existing `SiEvolution` component from `/api/si/snapshot`
to `/api/si/strategy` for naming consistency.

### 3. `feat(si): wire SI Strategy Evolution into live strike loop + brain GO`

**Files (7 modified):** `empire_agi_governor.py`, `empire_brain_decide.py`,
`empire_matching.py`, `empire_orchestrator.py`, `empire_payouts.py`,
`empire_state_manager.py`, `empire_voice.py`, `requirements.txt`

**Files (17 new):** `empire_si_adaptive.py`, `empire_si_brain.py`,
`empire_si_strategy.py`, `agent_mesh.py`, `bots/agi_lane_engine.py`,
`bots/agi_revenue.py`, `bots/hermes_controller.py`, `bots/mesh_dispatcher.py`,
`bots/mesh_outreach.py`, `bots/mesh_scout.py`, `bots/mesh_studio_copy.py`,
`bots/mesh_studio_render.py`, `bots/panel_court.py`, `bots/quality_analyst.py`,
`bots/seo_agent.py`, `migrations/001_seo_panel_court.sql`,
`supabase/migrations/20260609_add_si_tables.sql`,
`supabase/migrations/20260609_create_agent_task_queue.sql`

The big integration commit. When the brain says GO (and confidence ≥ 0.6),
`governor.strategy_for_niche(niche)` picks a strategy and stamps it onto
`strike_log.meta`. The strategy is then threaded into the contractor matching
dispatch path (via `dispatches.meta`) and the voice NCCO. On settlement,
`record_strategy_outcome` feeds the genome back to the SI core so strategies
evolve from real wins/losses. Also introduces the 10-agent Panel Court
ensemble, the agent mesh, and three new Supabase tables
(`si_parameters`, `agent_task_queue`, `seo_panel_court`).

### 4. `feat(dream): dream loop with risk flags + wisdom + spend tracking`

**Files:** `empire_dream.py` (new), `empire_hourly_digest.py` (new),
`migrations/002_dream_memory.sql` (new),
`supabase/migrations/20260609_add_spend_logs_and_quality.sql` (new),
`.gitignore` (added `hourly_digest.txt`)

Background dream loop that runs while the hub is up. Each cycle: scans
recent activity, extracts `risk_flags` and `wisdom_context`, suggests
new rules. The `dream_memory` table stores the full cycle history. The
`spend_logs` and `quality` tables track per-call costs and quality scores
for ROI analysis. The hourly digest loop produces a human-readable
summary at the top of every hour.

### 5. `feat(adaptive): real subsystem configurators replace no-op logging`

**Files:** `hub.py`, `empire_switchboard.py`, `empire_outreach_agent.py`

Replaced the 4 no-op `apply_fn` stubs in `hub.py` with real implementations
that mutate actual module-level runtime config. Each subsystem now exposes
a `read_fn` so the SI core can diff current vs target and avoid unnecessary
re-applies.

- **switchboard**: `cache_ttl_seconds`, `min_offered_for_rate`
- **matching**: `score_weights.<name>`, `default_top_n`
- **corridor**: `min_interval_seconds`
- **outreach**: `hot_threshold`, `score_per_click`, `score_per_reply`

Validation: negative values rejected, weights stay in `[0, 1]`, non-numeric
values caught. The `switchboard.cache_ttl_seconds` apply also calls
`_invalidate_buyers_cache()` so the next call re-fetches.

### 6. `chore: misc module updates + billing test`

**Files:** `empire_auth.py`, `empire_console.py`, `local_brain.py`,
`main.py`, `test_billing_flow.py`, `agent_interface.py`

Assorted updates that didn't fit a feature chunk. Kept separate so the
5 main feature commits stay pure.

### 7. `chore: commit remaining untracked files + expand .gitignore`

**Files:** `.gitignore` (expanded), `empire_seed.py` (new),
`.github/workflows/deploy.yml` (new)

Caught the last untracked files that were at risk of being lost.
`empire_seed.py` seeds the new SI-related Supabase tables. `deploy.yml`
is the GitHub Actions deploy workflow.

### 8. `chore(.gitignore): use broader *.onnx/*.bin patterns + add package-lock.json`

**Files:** `.gitignore`

Replaced narrow `kokoro-*` / `voices-*` with `*.onnx` / `*.bin` so any
future binary model files (Whisper, PyTorch checkpoints, etc.) are caught
automatically. Added `package-lock.json` since the SPA uses `esm.sh`
imports with no build step.

### Follow-up commits (after the initial 8)

### 9. `docs: add CHANGELOG.md with 8-commit history + project layout + conventions`

**Files:** `CHANGELOG.md` (new)

Documents the project layout, per-commit changelog, commit conventions
(prefix taxonomy, body rules, chunking rules), and the 7-step process
for adding a new feature.

### 10. `docs: add CONTRIBUTING.md with Getting Started + env vars + dev server + tests`

**Files:** `CONTRIBUTING.md` (new)

Closes the gap the CHANGELOG reviewer identified: no developer setup
instructions. Covers clone/install, full env-var reference (extracted
from `hub.py`), migrations, seed data, dev server, background loops
table, debugging tips, and code style.

### 11. `docs(contributing): add 3 missing env vars (WEBHOOK_SECRET, ADMIN_TOKEN, SI_FEED_CACHE_TTL_SECONDS)`

**Files:** `CONTRIBUTING.md`

Code review caught 3 env vars used in `hub.py` but missing from the
reference: `WEBHOOK_SECRET` (`/webhook/lead`), `ADMIN_TOKEN`
(`/api/admin/seed`), `SI_FEED_CACHE_TTL_SECONDS` (dream SI feed cache).

### 12. `docs(contributing): flag WEBHOOK_SECRET + ADMIN_TOKEN as required for production`

**Files:** `CONTRIBUTING.md`

Both vars have insecure defaults (`empire_v49_secret` and no auth
respectively). Moved them from the "Optional" section to a dedicated
"⚠️ Required for production" section with a warning emoji.

### 13. `docs(changelog): add follow-up commits 9-12 (docs commits + env var fixes)`

**Files:** `CHANGELOG.md`

After the env-var and production-warning commits were added, the
CHANGELOG was out of date. Added this "Follow-up commits" section so
the history stays self-describing. (This is a self-referential
changelog-update commit — git log is still the source of truth.)

---

## Commit Conventions

### Prefix taxonomy

| Prefix | When to use |
| --- | --- |
| `feat(<area>):` | New feature or significant capability in a horizontal slice (revenue, spa, si, dream, adaptive, voice, email, etc.). |
| `chore:` | Misc changes that don't fit a feature chunk (test files, config tweaks, one-off fixes). |
| `fix(<area>):` | Bug fix in a specific module. |
| `refactor(<area>):` | Internal refactor with no behavior change. |
| `docs:` | Documentation only (CHANGELOG, CONTRIBUTING, README). |
| `infra:` | CI/CD, deployment, infrastructure. |

### Body conventions

- First line ≤ 72 chars, imperative mood, no period.
- Blank line, then a 1-2 paragraph body explaining **what** changed and **why**.
- Bullet list of the major pieces, grouped by intent.
- End with the wire-up impact: "Wired into X endpoint" or "Tested via Y".

### Chunking rules

- One logical feature per commit. If a change touches > 3 unrelated modules,
  split it.
- Never mix refactors with feature changes in the same commit.
- Database migrations go with the feature that requires them.
- `.gitignore` changes go with the first commit that needs the new pattern.
- Lock files (`requirements.txt`, `package.json`) go with the feature that
  introduced the dependency.

### How to add a new feature

1. **Identify the slice** — which feature area does this belong to? (revenue,
   spa, si, dream, adaptive, etc.)
2. **Create or modify modules** — add new files in the right place, follow
   existing naming conventions (`empire_<feature>.py`, `bots/<feature>.py`).
3. **Add a migration if needed** — number it in `migrations/` (chronological)
   or timestamp it in `supabase/migrations/`.
4. **Register routes in `hub.py`** — use the existing `register_*_routes`
   pattern. Wire background loops in `@app.on_event("startup")`.
5. **If SI-related, add a subsystem configurator** — follow the
   `apply_fn` + `read_fn` pattern in `hub.py`. Update the SPA's
   `SiAdaptive` component if operators need visibility.
6. **Add a SPA panel if operator-facing** — follow the existing component
   pattern in `empire_command_spa.py` (one component per section,
   CSS prefix matching the feature).
7. **Commit with the right prefix and body** — follow the conventions above.

---

## .gitignore conventions

The `.gitignore` is organized into sections with comments:

1. **Python** — `__pycache__/`, temp files
2. **JS** — `node_modules/`, `package-lock.json` (no build step)
3. **Binary** — `*.onnx`, `*.bin` (model files)
4. **Generated** — `outreach_drafts/` (runtime content)

When adding a new pattern, put it in the right section with a comment
explaining **why** it's ignored.
