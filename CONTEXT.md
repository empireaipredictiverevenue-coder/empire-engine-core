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
- **Token proxy cache speedup:** 30x measured
- **Event bus:** ✅ Active on hub (port 8001)

---

## Running Services

### PM2 Services
| Service | Port | PID | Status |
|---------|------|-----|--------|
| empire-mesh | — | 3451686 | online |
| empire-hub | 8001 | — | online (port changed from 8000) |
| empire-chrome | 9222 | 3451900 | online |
| empire-pulse-cron | — | 3451726 | online |
| empire-matrix-agi | 8010 | 3451695 | online |
| empire-matrix-strategy | 8020 | 3451711 | online |
| empire-matrix-landing | 8030 | 3451703 | online |
| empire-matrix-universal | 8040 | 3451691 | online |
| empire-ppc-inbound | 8045 | 3451718 | online |
| contractor-sniper | — | 3451688 | online |
| traffic-specialist | — | — | online |
| affiliate-recruiter | — | — | online |
| email-pulse-monitor | — | — | online |
| seo-agent | — | — | online |

### Non-PM2 Long-Running
| Service | Port | PID | Notes |
|---------|------|-----|-------|
| synthetic_brain | 8005 | — | LLM brain via uvicorn (currently stopped) |
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
| Event Bus Persistence | event-bus-persist | 5s | ✅ Active — batched writes to agent_activity |

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
| 6 | Event Bus Integration | ✅ Complete | All cron agents emit via event bus (agent/eventbus flow) |
| 7 | Token Proxy Cache | ✅ Complete | 30x speedup verified on brain decisions |

---

## New Architecture: Token Proxy + Event Bus

### Token Proxy (`empire_token_proxy.py`)
Transparent caching layer over the AIRouter. Wraps all LLM calls with:
- **LRU semantic cache** (1000 entries, task-aware TTLs from 60s–1800s)
- **In-flight dedup** — concurrent identical calls share one LLM round-trip
- **Context compression** — collapses blanks, strips whitespace, truncates at 4000 chars
- **Zero behavioral change** — monkey-patches AIRouter.generate/generate_json

**Wiring:** Singleton `get_token_proxy()` wraps `ai_router` in hub.py after creation.
**Verified:** 30x speedup (6.0s → 0.2s) on cached brain decisions.
**Env vars:** None required (auto-activates via the singleton).

### Event Bus (`empire_event_bus.py`)
Centralized async pub/sub system for fleet events:
- **Async pub/sub** (`emit`/`on`/`off`) with wildcard subscriber support
- **Rolling window** of 500 recent events in memory
- **Background batch persistence** to Supabase `agent_activity` every 5s
- **WebSocket broadcast** via LiveBroadcaster
- **Webhook forwarding** for warn/error/critical severity events
- **REST API:**
  - `GET /api/v1/events/recent?limit=N` — recent events
  - `GET /api/v1/events/stats` — event type counts + metrics
  - `POST /api/v1/events/emit` — emit an event (for external callers)

**Cron Agent Integration (`agents/event_emitter.py`)**
All 9 cron agents now emit events via `emit_agent_event()` instead of writing
directly to `agent_activity`. The helper POSTs to the hub's event bus endpoint,
with fallback to direct Supabase insert when the hub is unreachable.

**Agents wired:** lead_scanner, lead_enricher, lead_converter, dispatch,
prospector, prospector_bridge, contractor_outreach, retarget, warp_scout.

### Brain Proxy (`POST /api/v1/brain/chat`)
Generic LLM proxy endpoint on the hub that routes LLM calls through the
AIRouter → TokenProxy cache. Used by the Predictive Cloud (synthetic_brain)
when `BRAIN_HUB_URL` is configured.

**Env vars:**
- `BRAIN_HUB_URL=http://127.0.0.1:8001` (set in /root/.env)
- `BRAIN_HUB_TOKEN=Jaykub20*` (set in /root/.env)

### Key Config Updates

**Storm Pipeline:**
- `STORM_MAX_SENDS_PER_DAY=10000` (was 200, set in /root/.env)
- Brain gate runs BEFORE rate gate → token proxy caches decisions even when rate-limited
- Rate gate fires AFTER brain decision → prevents over-sending

**Supabase Tables (new):**
- Added event bus persistence to `agent_activity` (async batch writes)

---

## Brain System — Wiring Summary

### BrainDecider (`empire_brain_decide.py`)
- **Input:** Dream wisdom ✅ (injected via `get_latest_wisdom()`)
- **Input:** BrainMemory few-shot examples ✅ (queried by orchestrator before each decision)
- **Input:** BrainPersonality per-niche profiles ✅ (set by hub.py at startup)
- **Output:** Recorded to BrainMemory ✅ (after each decision, for future learning)
- **Caching:** Flows through TokenProxy ✅ (30x speedup on repeated decisions)

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

### Token Proxy (`empire_token_proxy.py`)
- Wraps AIRouter at hub boot
- Caches brain decisions, email drafts, enricher calls, narrations
- Singleton shared across Hermes controller and all bot agents

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

## Uncommitted Changes (git diff)

Modified files (all validated, syntax OK):
- `hub.py` — brain proxy endpoint, event bus wiring, token proxy wiring, storm limit bump
- `synthetic_brain.py` — hub brain proxy client (`_ask_hub_brain`)
- `empire_orchestrator.py` — brain gate reorder, rate gate fix, limit bump
- `bots/hermes_controller.py` — token proxy singleton integration
- `agents/lead_scanner/scanner.py` — event emitter
- `agents/lead_enricher/enricher.py` — event emitter
- `agents/lead_converter/converter.py` — event emitter
- `agents/dispatch/dispatcher.py` — event emitter
- `agents/prospector/prospector.py` — event emitter
- `agents/prospector_bridge/prospector_bridge.py` — event emitter
- `agents/contractor_outreach/outreach.py` — event emitter
- `agents/retarget/retarget.py` — event emitter
- `agents/warp_scout/warp_scout.py` — event emitter
- `scripts/test_brain_path.py` — urgency floor arg fix

New files:
- `empire_token_proxy.py` — LRU semantic cache for LLM calls
- `empire_event_bus.py` — centralized fleet event bus
- `agents/event_emitter.py` — shared emitter for cron agents
- `scripts/test_brain_cache.py` — cache hit verification
- `scripts/test_event_bus.py` — event bus verification
- `scripts/test_cache_hit.py` — cache speedup verification
- `scripts/validate_agent_syntax.sh` — syntax helper

**Tags:** `v49-cron-event-bus` (243f1ce)

*Update this file when services change, KPIs update, or strategic items ship.*
