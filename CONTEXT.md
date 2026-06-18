# CONTEXT.md — Empire AI Agent Context & State

This file tracks the state of the Empire V49 system for agent coordination.
Read this first to understand what's running, what's configured, and what's in flight.

**Last updated:** 2026-06-18
**Maintained by:** Buffy (default operator agent)

---

## System State

### Locked Metrics (from STARTING_POINT.md)
1. ✅ Splash live at empire-ai.co.uk
2. ✅ 1 real lead in Supabase
3. ✅ 1 real contractor recruited
4. ✅ 1 real fee earned

### Current KPIs
- **Enriched leads:** 1,200
- **Converted leads (replied YES):** 96
- **Contractors in DB:** 1,097
- **Fee events:** 2
- **Fee revenue:** $3,750 (3% of settled claims)
- **Active lanes:** 36
- **Active niches:** 13
- **Service metros:** DFW, Houston, San Antonio, Austin

---

## Running Services

### PM2 Services
| Service | Port | PID | Status |
|---------|------|-----|--------|
| empire-mesh | — | 3451686 | online |
| empire-hub | 8000 | 3663717 | online |
| empire-chrome | 9222 | 3451900 | online |
| empire-pulse-cron | — | 3451726 | online |
| empire-matrix-agi | 8010 | 3451695 | online |
| empire-matrix-strategy | 8020 | 3451711 | online |
| empire-matrix-landing | 8030 | 3451703 | online |
| empire-matrix-universal | 8040 | 3451691 | online |
| empire-ppc-inbound | 8045 | 3451718 | online |
| contractor-sniper | — | 3451688 | online |

### Non-PM2 Long-Running
| Service | Port | PID | Notes |
|---------|------|-----|-------|
| synthetic_brain | 8005 | 2603245 | LLM brain via uvicorn |
| hermes gateway | — | 2593898 | Telegram poller (Empire1aibot) |
| hermes dashboard | 9119 | 2995516 | Internal dashboard |

### Background Loops (in-process, started at hub boot)
| Loop | Name | Interval | Status |
|------|------|----------|--------|
| DreamLoop | dream-loop | 6h | ✅ Scheduled |
| HourlyDigest | hourly-digest | 1h | ✅ Scheduled |
| SEO Agent | seo-agent | weekly | ✅ Scheduled |
| Backlinks Agent | backlinks-agent | 12h | ✅ Scheduled |
| Traffic Specialist | traffic-specialist | varies | ✅ Scheduled |
| Affiliate Recruiter | affiliate-recruiter | varies | ✅ Scheduled |
| Bounty Tracker | bounty-tracker | varies | ✅ Scheduled |
| Email Pulse Monitor | email-pulse-monitor | 5min | ✅ Scheduled |
| Brain Learning (nightly tune) | brain-learning | 24h | ✅ Scheduled |
| Mission Control Broadcast | mission-control-broadcast | real-time | ✅ Scheduled |

### Cron-Driven Agents (15 scripts)
Run via crontab. See crontab for full schedule.

---

## Strategic Items — Status

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Contractor Portal | ✅ Complete | Self-service, wired in hub.py |
| 2 | Solana Payout Pipeline | ⏳ Blocked | Needs devnet SOL — run `test_solana_payout.py` |
| 3 | Reply-to-Dispatch Auto | ✅ Complete | `_on_sms_yes_reply` callback in hub.py |
| 4 | Legal Lanes (10-14) | ✅ Complete | Configured, bots exist |
| 5 | Storm Metro Expansion | ⏳ Config | Update `agent_config` table for new metros |

---

## Uncommitted Changes (git diff)

Modified files (all validated, syntax OK):
- `bots/email_pulse_monitor.py` — run_id fix, error logging
- `empire_bridge.py` — JARVIS Command Bridge dashboard HTML
- `empire_command_spa.py`, `empire_console.py`, `empire_contractor_portal.py`
- `empire_contractors.py`, `empire_fee.py`, `empire_fee_operator.py`
- `empire_payouts.py`, `empire_storm_landing.py`, `hub.py` (background loop wiring + bridge)

New files:
- `bots/bounty_tracker.py` — referral bounty system
- `migrations/049_contractor_referral_bounty.sql`
- `migrations/050_generated_pages.sql`

**Deploy:** Run `./hub_safe_restart.sh`

---

## Brain System — Wiring Summary

### BrainDecider (`empire_brain_decide.py`)
- **Input:** Dream wisdom ✅ (injected via `get_latest_wisdom()`)
- **Input:** BrainMemory few-shot examples ✅ (queried by orchestrator before each decision)
- **Input:** BrainPersonality per-niche profiles ✅ (set by hub.py at startup)
- **Output:** Recorded to BrainMemory ✅ (after each decision, for future learning)

### BrainMemory (`empire_brain_memory.py`)
- Queries 5 similar past leads via pgvector similarity before each brain decision
- Renders few-shot examples into the brain prompt
- Records decisions on every GO/NO_GO for compounding learning

### BrainLearning (`empire_brain_learning.py`)
- Nightly urgency floor auto-tuning from past outcomes (24h cycle)
- Started via `_deferred_background_tasks()`

### DreamLoop (`empire_dream.py`)
- 6-hour tick, discovers cross-system patterns
- Wisdom injected into BrainDecider prompts and SI Brain strategies

## Key Config

### Supabase
- URL/Keys in `/root/.env`
- Tables: `radar_targets`, `enriched_leads`, `outreach_log`, `contractors`, `fee_events`, `agent_activity`, `pulse_rollup_hourly`, `brain_memory`, `brain_config`, `brain_personality`

### Solana
- Devnet test keypair: `/root/.hermes/tmp/devnet_test_key.json`
- Pubkey: `BwWzg6Z5dkZNJ1fvdYdCyScnNw6xVjnN8g6R7BNhSkds`
- Status: Needs devnet SOL to run payout tests

### Resend
- API key in `/root/.env`
- Daily quota: 100 (critical 40 / marketing 60)

---

## Agent Coordination

**Kanban:** `/root/.hermes/kanban.db` — SQLite, use `hermes kanban` CLI
**Task lifecycle:** Create → Claim → Work → Comment → Complete
**Communication:** Kanban comments, not chat/memory

---

*Update this file when services change, KPIs update, or strategic items ship.*
