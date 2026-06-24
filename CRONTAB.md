# Empire-AI Cron Schedule

Generated: 2026-06-24
Host: ubuntu-8gb-hil-2 (5.78.148.141)
Total entries: 128 lines, 57 executable (rest are comments)
Snapshot file: `/tmp/crontab.before.20260624_140007.patch` on the box

## Schedule

| Frequency | Schedule (UTC) | Agent / Script | Log File | Purpose |
|---|---|---|---|---|
| every 5min | `*/5 * * * *` | `scripts/vault_watcher.py` | `logs/vault_watcher.log` | Polls Helius for vault USDC transfers, auto-marks fee_events paid |
| every 5min | `*/5 * * * *` | `bots/empire_facebook_chatbot.run_once` | `logs/facebook_chatbot.log` | Facebook Messenger inbox polling |
| every 5min | `*/5 * * * *` | `agents.system_supervisor --no-tg --auto-fix` | (silent) | Silent supervisor — auto-heals on critical |
| every 5min | `2,7,12,...,57 * * * *` | `agents/dispatch/cron.sh` | `logs/agent_dispatch.log` | Live dispatch (YES replies → contractors) |
| every 10min | `*/10 * * * *` | `empire_dispatch_invoice.py check-all` | `logs/invoice_check.log` | Stripe/crypto invoice checker |
| every 15min | `*/15 * * * *` | `agents.prospector_bridge` | `logs/agent_prospector_bridge.log` | Bridges prospects → contractors |
| every 15min | `*/15 * * * *` | `scripts/fleet_health_monitor.py` | `logs/fleet_health.log` | Fleet health pings |
| every 15min | `*/15 * * * *` | `empire_subscription.py verify-all` | `logs/sub_verify.log` | Subscription status sync |
| every 30min | `*/30 * * * *` | `agents/lead_scanner/cron.sh` | `logs/agent_lead_scanner.log` | radar_targets → enriched_leads |
| every 30min | `*/30 * * * *` | `scripts/vault_monitor.py` | `logs/vault_monitor.log` | Vault top-up monitor |
| every 30min | `*/30 * * * *` | `scripts/call_outcomes.py --since-hours 4` | `logs/call_outcomes.log` | Match call_events to fee_events |
| every 30min | `0,30 * * * *` | `agents.fee_watcher` | `logs/agent_fee_watcher.log` | Polls carrier_claims → fee_events |
| every 30min | `2,32 * * * *` | `scripts/sync_revenue_ledger.py --sync --hours 2` | `logs/sync_revenue_ledger.log` | Unified revenue ledger sync |
| every 30min | `15,30,45 * * * *` | `scripts/dispatch_followup_agent.py` | `logs/agent_dispatch_followup.log` | Dispatch follow-ups |
| every 30min | `30 * * * *` | `scripts/fee_expired_handler.py` | `logs/fee_expired_handler.log` | Expire stale fee_events |
| hourly | `0 * * * *` | `scripts/fee_urgency_push.py` | `logs/fee_urgency_push.log` | Push urgency pings for pending fees |
| hourly | `0 * * * *` | `scripts/monitor_ranking_prediction.sh` | `logs/ranking_monitor_cron.log` | Hourly SEO ranking prediction |
| hourly :25 | `25 * * * *` | `agents/dispatch/cron.sh` | `logs/agent_dispatch.log` | Dispatch safety-net (replaces corrupted combined cron) |
| every 4h | `0 */4 * * *` | `agents/contractor_outreach/cron.sh` | `logs/agent_contractor_outreach.log` | Contractor re-engagement |
| every 4h | `0 */4 * * *` | `agents/sales_agent.py` | `logs/sales_agent.log` | Sales closes |
| every 4h | `0 */4 * * *` | `agents/yt_comment_agent.py` | `logs/yt_comments.log` | YT shorts comment replies |
| every 4h | `15 */4 * * *` | `bots/mass_tort_bridge.py` | `logs/mass_tort_bridge.log` | Routes FDA recalls to legal buyers |
| every 6h :02 | `2 */6 * * *` | `agents/radar_asset_enricher_cron.sh` | `logs/agent_radar_asset_enricher.log` | Backfill radar_targets.asset_value |
| every 6h :05 | `5 */6 * * *` | `agents/prospector/cron.sh` | `logs/agent_prospector.log` | Run bots/prospector.py across metros |
| every 6h :07 | `7 */6 * * *` | `agents/retarget/cron.sh` | `logs/agent_retarget.log` | Re-target dormant leads |
| every 6h :15 | `15 */6 * * *` | `agents/multi_touch_cadence_cron.sh` | `logs/agent_multi_touch_cadence.log` | 4-step SMS cadence (day 0,3,7,14) |
| every 6h :20 | `20 */6 * * *` | `agents.email_outreach` | `logs/agent_email_outreach.log` | Resend cadence |
| **every 6h :30** | `30 */6 * * *` | **`scripts/mass_tort_lane.py`** | **`logs/mass_tort_lane.log`** | **Firecrawl FDA recall scraper (NEW 2026-06-24)** |
| every 6h :50 | `50 */6 * * *` | `agents/warp_scout/cron.sh` | `logs/agent_warp_scout.log` | NOAA Storm Prediction Center |
| every 6h :52 | `52 */6 * * *` | `agents_ab_monitor.py` | `logs/agent_ab_monitor.log` | A/B test results polling |
| every 6h :55 | `55 */6 * * *` | `agents/fee_watcher/cron.sh` | `logs/agent_fee_watcher.log` | Claim-event poller (fixed dedup b645e24) |
| every 6h :55 | `55 */6 * * *` | `scripts/fee_collection_agent.py --follow-up` | `logs/agent_fee_collection.log` | Fee follow-ups |
| every 12h | `0 */12 * * *` | `agents/backlinks/cron.sh` | `logs/agent_backlinks.log` | Backlink monitoring |
| daily 00:00 | `0 0 * * *` | `integrations/recursive_loop_orchestrator.py` | `logs/recursive_loop.log` | Self-healing loop |
| daily 01:00 | `0 1 * * *` | `empire_subscription.py expire-lapsed` | `logs/sub_expire.log` | Expire lapsed subscriptions |
| daily 03:30 | `30 3 * * *` | `bots/bbb_prospector.py --metros 54 --niches 5 --max 8` | `logs/bbb_full.log` | Full BBB prospector (54 metros × 5 niches) |
| daily 04:00 | `0 4 * * *` | `python3 -m graphify update .` | `logs/graphify_update.log` | Graphify update |
| daily 04:00 | `0 4 * * *` | `scripts/track_infra_costs.py --daily` | `logs/track_infra_costs.log` | Track daily infra costs |
| daily 05:00 | `0 5 * * *` | `agents_marketing_health.py` | `logs/agent_marketing_health.log` | Marketing health check |
| daily 06:00/18:00 | `0 6,18 * * *` | `scripts/fee_collection_agent.py` | `logs/fee_collection.log` | Fee collection outreach |
| daily 06:30 | `30 6 * * *` | `agents/tiktok_crosspost.py` | `logs/tiktok_crosspost.log` | TikTok morning post |
| daily 06:30 Sunday | `30 6 * * 0` | `scripts/enrich_contractor_emails.py --apply --agent-reach` | `logs/enrich_contractor_agent_reach.log` | Weekly contractor email enrichment |
| daily 07:00 | `0 7 * * *` | `agents_daily_revenue.py` | `logs/daily_revenue.log` | Daily revenue report |
| daily 08:00 Monday | `0 8 * * 1` | `scripts/send_payment_report.py` | `logs/send_payment_report.log` | Weekly payment report |
| daily 09:00 | `0 9 * * *` | `agents/marketing_agent.py` | `logs/marketing_agent.log` | Marketing A/B detection |
| daily 09:00 | `0 9 * * *` | `agents.system_supervisor` | `logs/agent_system_supervisor.log` | Daily supervisor (Telegram) |
| daily 09:00 | `0 9 * * *` | `agents/youtube_shorts/cron.sh` | `logs/agent_youtube_shorts.log` | YT shorts generation |
| daily 09:00 Sunday | `0 9 * * 0` | `scripts/generate_valuation_pdf.py` | `logs/valuation_pdf.log` | Weekly valuation PDF |
| daily 09:00 | `0 9 * * *` | `scripts/fee_daily_report.py` | `logs/fee_daily_report.log` | Daily fee report |
| daily 10:00 | `0 10 * * *` | `scripts/contractor_outreach.py send 250` | `logs/contractor_outreach.log` | Send up to 250 outreach emails |
| daily 10:00 Mon/Thu | `0 10 * * 1,4` | `scripts/fee_collection_cycle.sh` | `logs/fee_collection_cycle.log` | Fee cycle refresh (discounts, AI calls, SMS) |
| daily 10:30 | `30 10 * * *` | `scripts/contractor_nudge.py` | `logs/contractor_nudge.log` | Contractor follow-up nudge |
| daily 11:00 | `0 11 * * *` | `agents/business_growth_agent.py` | `logs/business_growth_agent.log` | Business growth recommendations |
| daily 18:30 | `30 18 * * *` | `agents/tiktok_crosspost.py` | `logs/tiktok_crosspost.log` | TikTok evening post |
| weekly Sun 03:00 | `0 3 * * 0` | `agents/organic_reach_agent.py` | `logs/organic_reach_agent.log` | Organic reach |

## Recent Changes

- **2026-06-24 19:00** — Added `30 */6 * * *` → `scripts/mass_tort_lane.py` (Firecrawl FDA recall scraper)
- **2026-06-24 19:00** — Fixed broken dispatch cron line (was smushed 2 jobs onto one line)
- **2026-06-24 14:21** — `b645e24` — fee_watcher dedup by dispatch_id in meta (stops webhook double-fire)
- **2026-06-24** — Added 5 legal niches to prospector config (mass_tort, class_action, consumer_product, medical_device, pharma_liability)

## Disabled / Commented Out

- `# 54 */6 * * * agents_settled_monitor.py` — mock carrier settled-claim monitor (Phil: removed simulated revenue)
- `# 0 */6 * * * bots.b2b_lead_scraper` — Google Places scraper (disabled, replaced by camofox-browser path)

## Source of Truth

Live source: `crontab -l` on the box. This file is documentation only — to regenerate after a crontab edit, re-run the gen script (TBD).