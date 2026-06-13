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
Two agents are wired into this project right now:

  - **default** (this profile) — the operator agent. Phil's main point of
    contact via the Empire1aibot Telegram bot. Owns: server, gateway,
    Supabase, splash, hub. SOUL: `/root/.hermes/SOUL.md`.
  - **empireaipredictiverevenue-coder** — the predictive-revenue coder.
    Active in git history (`git log --format='%an' | sort -u`). Owns:
    strike pipeline, predictive revenue modules, AGI calibration. Email:
    empireaipredictiverevenue@proton.me (for git audit only; not a chat).

If you're a new agent and don't recognize your name above: introduce yourself
in the kanban before doing work (see Coordination below).

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
