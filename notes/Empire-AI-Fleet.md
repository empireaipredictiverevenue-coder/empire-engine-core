---
tags: [fleet, inventory, 2026-06-22]
---

# Empire-AI Fleet (as of 2026-06-22)

Updated from the 06-13 inventory. Many PM2 entries were removed/renamed since
the old map was written. Cron fleet was silently truncated at one point; restored
2026-06-22 with the predictive-revenue fragment. Full audit: see
[[Sessions/2026-06-22_payment_and_recovery]].

## PM2 (top services that matter for revenue)

| name | exec | status |
|------|------|--------|
| empire-hub | `hub.py` uvicorn :8001 | online (restarts at 8194 — pre-existing flapping) |
| mesh-marketing | `bots/mesh_marketing_worker.py` | online |
| mesh-dispatcher | `bots/mesh_dispatcher.py --loop` | online |
| camofox-scraper | `camofox-browser server --port 9377 --background` | manual (re-spawn when browser disconnects) |

## Uvicorn (external-listening)

- hub `:8001` (empire-v49, public at empire-ai.co.uk via cloudflared)
- synthetic_brain `:8005` — see [[Empire_AI_Brain]]
- agent_orchestrator `:8042`
- hook_analytics `:8046`

## Internal-only matrix services

- `:8010` empire-matrix-agi
- `:8020` empire-matrix-strategy
- `:8030` empire-matrix-landing
- `:8040` empire-matrix-universal
- `:8045` empire-ppc-inbound

## Cron (live, 2026-06-22)

### Predictive Revenue Fleet (restored 2026-06-22 from `agents/CRONTAB.fragment`)

```
*/30 * * * *   agents/lead_scanner/cron.sh
5,35 * * * *  agents/lead_enricher/cron.sh
10,25,40,55  agents/lead_converter/cron.sh
*/5           agents/dispatch/cron.sh
0 */4         agents/contractor_outreach/cron.sh
0 */12        agents/backlinks/cron.sh
0 */6         bots/b2b_lead_scraper
5 */6         agents/prospector/cron.sh
7 */6         agents/retarget/cron.sh
50 */6        agents/warp_scout/cron.sh
52 */6        agents_ab_monitor
54 */6        agents_settled_monitor
```

### Fee + payment recovery (added 2026-06-22)

```
*/5 * * * *   scripts/vault_watcher.py                  — Helius USDC polling, auto-mark paid
*/30 * * * *  scripts/call_outcomes.py                  — match call_events to fee_events
0 10 * * 1,4  scripts/fee_collection_cycle.sh           — refresh discounts + AI calls + SMS + email
30 3 * * *    bots/bbb_prospector.py --metros 54 --niches 5 --max 8
              — full BBB supply sweep nightly
```

### Pre-existing ops crons

- `0,30` `agents.fee_watcher`
- `15` `dispatch_followup_agent.py`
- `0 6,18` `fee_collection_agent.py`
- `55 */6` `fee_collection_agent.py --follow-up`
- `0 7` `agents_daily_revenue.py`
- `0 9 * * 0` `generate_valuation_pdf.py`

## Other

- camofox `:9377` (manually started)
- cloudflared `:9120` → public empire-ai.co.uk (transient retry errors — tunnel recovers)
- ollama `:11434` (degraded — `llama3:8b` 404; brain using fallback model)

## Related

- [[Obsidian_RAG_2026-06-22]] — vault-aware brain (active 2026-06-22)
- [[Empire_AI_Brain]] — predictive cloud (voice + video)
- [[Sessions/2026-06-22_payment_and_recovery]] — today's work
- [[Parking_Lot]] — deferred ideas