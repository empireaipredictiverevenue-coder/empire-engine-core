# AGENTS.md — Empire-AI Agent Coordination

This file is read by every agent (claude, codex, hermes, the predictive-revenue
coder) that touches `/root/empire-v49/`. Read it FIRST, follow the protocol,
write back when you're done.

## The Locked Directive
`/root/empire-v49/STARTING_POINT.md` is the source of truth for the business.
**Do not read past this paragraph without reading it.** Success metric, in order:

  1. Splash live at empire-ai.co.uk
  2. 1 real lead in Supabase
  3. 1 real contractor recruited
  4. 1 real fee earned

Until those are hit, anything not on that path is parking-lot work. If you're
about to build a SaaS billing layer, predictive AGI module, or cinematic
dashboard, stop. The lock is in STARTING_POINT.md, not here.

## Who Is Working
The fleet is bigger than the two agents. Last enumerated 2026-06-13
08:35 UTC. This section is the source of truth; if it drifts, run
`python3 scripts/dump_fleet.py` to refresh and update.

### Coordinators (2, both non-PM2)
  - **agent_orchestrator** — `uvicorn agent_orchestrator:app :8042`
    (PID 3099292, 2 workers + 2 forks). Re-exported from
    `products/agent_orchestrator.py`. Log: `logs/agent_orchestrator.log`.
    The router. Speaks HTTP; assumes every backend is on localhost.
  - **hook_analytics** — `uvicorn hook_analytics:app :8046`
    (PID 3106758, 2 workers). Analytics event router.

### PM2 services (10, all online; restart with `pm2 restart <name>`)
  - **empire-mesh** (PID 3451686) — `main.py`. The fleet orchestrator script
    (signal handler, lib import, env bootstrap). Logs to `/var/log/empire.log`.
  - **empire-hub** (PID 3663717) — `hub.py` on `:8000` via uvicorn. The main
    Empire-AI FastAPI app. `/api/v1/*` routes, contractor signup, voice,
    SMS, attribution dashboard. Restart after code changes (12s downtime).
  - **empire-chrome** (PID 3451900) — `scripts/chrome_headless.sh` + xvfb.
    Headless Chrome on `:9222` for screenshots / scraping. See
    AGENTS.md / `scripts/screenshot_dashboards.py`.
  - **empire-pulse-cron** (PID 3451726) — `scripts/pulse_refresh_cron.py
    --interval 300`. Backup for the hub's pulse refresh loop. Keeps
    `pulse_rollup_hourly` materialised view fresh if the hub is down.
  - **empire-matrix-agi** (PID 3451695) — `matrix/sovereign_agi_matrix.py`
    on `:8010`.
  - **empire-matrix-strategy** (PID 3451711) — `strategy/roi_marketing_matrix.py`
    on `:8020`.
  - **empire-matrix-landing** (PID 3451703) — `landing/landing_matrix.py`
    on `:8030`.
  - **empire-matrix-universal** (PID 3451691) — `universal/universal_matrix.py`
    on `:8040`.
  - **empire-ppc-inbound** (PID 3451718) — `matrix/main.py` on `:8045`.
    Pay-per-call inbound routing (Ventura high-intent filter).
  - **contractor-sniper** (PID 3451688) — `bots/contractor_sniper.py`.
    Background worker; what it does, check the file header.

### Non-PM2 long-running
  - **synthetic_brain** (PID 2603245) — `uvicorn synthetic_brain:app :8005`
    (1 worker). The LLM brain. Uses Ollama (PID 2955959, `:11434`) and
    llama-server (PID 3450892, `:46841`) for inference.
  - **hermes gateway** (PID 2593898) — `hermes gateway run`. Telegram
    poller on Empire1aibot, chat 808657420. The mainline for Phil's DMs.
  - **hermes dashboard** (PID 2995516) — `hermes dashboard --port 9119`.
    Internal-only, not exposed publicly.

### Profile-aware agents (2)
  - **default** (this profile) — the operator agent. Phil's main point of
    contact via the Empire1aibot Telegram bot. SOUL:
    `/root/.hermes/SOUL.md`. Owns: server, gateway, Supabase, splash, hub.
  - **empireaipredictiverevenue-coder** — the predictive-revenue coder.
    Active in git history (`git log --format='%an' | sort -u`). Owns:
    strike pipeline, predictive revenue modules, AGI calibration. Email:
    empireaipredictiverevenue@proton.me (git audit only; not a chat).

### Cron-driven agents (5 entries, NOT counted as "live services")
  - `empire_brain.py` — every hour at :00, → `logs/bridge.log`.
  - `automate_empire.sh` — every hour at :30, → `logs/agents.log`. The
    predictive-revenue coder's main cron tick.
  - `hermes-backup.sh` — daily 03:00, → `~/hermes-backup/cron.log`.
  - `opt/empire-pipeline/run_safe.sh` — every 2h 06:00-22:00 Central.
    The storm lead pipeline. The actual revenue path.
  - `scripts/run_storm_scraper.sh` — daily 00:00 and 12:00,
    → `logs/storm_scraper.log`.

If you're a new service and don't see yourself above: edit this file
and add a row. The fleet changes often; this list drifts. Regenerate
with `python3 scripts/dump_fleet.py`.

If you're a brand-new agent and don't recognize your name anywhere:
introduce yourself in the kanban before doing work (see Coordination).

### Fee copy is CI-guarded
The per-claim fee was bumped from 1% to 3% on 2026-06-13 (commits 2a038ef,
f81f868). `scripts/check_fee_copy.py` scans 426 files for any stale
1% fee reference and exits non-zero if it finds one. Run it before
committing marketing changes:

    python3 scripts/check_fee_copy.py

Allow-list lives in the script (CSS widths, the 1% wire-tolerance
heuristic in empire_payouts.py:413, etc.). To wire it as a pre-commit
hook, add `.git/hooks/pre-commit` running this script.

## Coordination Protocol — Read This
**Use the kanban. Not chat. Not memory. Not the SOUL.** The kanban is the only
durable, queryable, multi-agent queue.

  - DB: `/root/.hermes/kanban.db` (SQLite, 8 tables, lives in the default
    Hermes home).
  - CLI: `hermes kanban <subcommand>`. Run `hermes kanban --help` for the
    full list. The important ones: `boards`, `create`, `list`/`ls`, `claim`,
    `show`, `comment`, `complete`, `tail`, `assign`.
  - Default board: `default`. Don't create more boards unless the work
    spans >20 tasks; one board per project is the convention.

**Lifecycle of a task:**

  1. Create it: `hermes kanban create --title "..." --body "..." --priority P1`
     Every task body must answer: what does "done" look like? Verification
     step is mandatory (the user holds commits for un-verified work).
  2. Claim it before working: `hermes kanban claim <task-id> --assignee me`
     Two agents claiming the same task wastes time. If you see an unclaimed
     task in your lane, claim it. If it's already claimed, ask the claimer
     via `hermes kanban comment` first.
  3. Work it. As you find things the other agent needs, comment in-thread:
     `hermes kanban comment <task-id> --body "..."`. Don't DM Phil unless
     the kanban is blocked.
  4. Complete it only when verified: `hermes kanban complete <task-id>`.
     "Verified" means: end-to-end against the real system, or confirmed
     external blocker with proof. Stubbed code does not complete a task.
  5. If you get stuck after 2 attempts at the same approach: comment in
     the task with the blocker and stop. Do not attempt a third time.
     The user values "tried X, Y; here's the actual blocker" over silent
     thrash.

**Don't:**

  - Don't write state to your own memory/notes and assume the other agent
    will see it. They won't. Kanban or nothing.
  - Don't edit files in the other agent's working tree mid-task. Comment
    and wait. If the work is urgent, file a blocking task and link it.
  - Don't push directly to master without a comment in the relevant
    kanban task. (Pull-requests are for human review, not for two
    agents reviewing each other.)

## State of the Project (2026-06-13)

**Save point:** 4 commits on master, working tree clean. Prod gateway PID
2593898 on Empire1aibot, polling chat 808657420.

**Recently shipped:**
  - `7d8e848` chore(buyers): dedup 36 Apex Mass Tort Group rows
  - `2a038ef` fee(bump): 1% → 3% on per-claim settlement
  - `630c971` revert(phase10): multi-tenant orgs out of scope
  - `4746af2` feat(phase10) — REVERTED, was the SaaS scope-creep commit

**Open queue (see kanban `default` board):**
  - Task #1 (in flight, this session): Coordination with the predictive-revenue
    coder about the 6 placeholder buyers in the buyers table.

**Locked / parking-lot (don't start without Phil's go-ahead):**
  - Multi-tenant SaaS (orgs, RLS, billing, Stripe/Solana subscription
    engines). 4746af2 was reverted. Do not re-introduce.
  - Predictive AGI/SI expansion beyond what predictive_revenue.py +
    agi_revenue.py already do. Calibration tuning only.
  - Anything in `/root/_to_delete_20260525-0808/` — the previous Empire-AI
    stack, scheduled for deletion 2026-05-25. Read-only if at all.

## File Layout (so you don't grep the wrong place)

  - `/root/empire-v49/` — current codebase (this repo, master branch).
  - `/root/.hermes/` — Hermes home. SOUL, config, state, kanban, logs.
  - `/root/empire-v49/migrations/` — SQL migrations, run via
    `/root/empire-v49/scripts/run_migrations.py`.
  - `/root/empire-v49/deploy/` — SQL bundled with the deploy, NOT
    run automatically.
  - `/root/empire-v49/.env` — does not exist. Env lives at `/root/.env`
    and is sourced by run_migrations.py and most scripts.
  - `/root/_to_delete_20260525-0808/` — dead previous stack, do not
    import or depend on.

## When You're Done With Your Turn

  1. `hermes kanban comment <your-task-id> --body "summary: ..."`
     so the next agent (or Phil) sees what you shipped.
  2. `hermes kanban complete <your-task-id>` — only if verified.
  3. If you started something you can't finish, leave the task claimed
     with a comment. Don't abandon. The other agent needs to know it's
     still in flight.
  4. Don't touch the other agent's claimed tasks unless invited.

— end AGENTS.md —
