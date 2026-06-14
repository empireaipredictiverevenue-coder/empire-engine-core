# Lead-Gen + Conversions Agent — Build Plan

## Goal
Three agents that form a pipeline: radar_targets → enriched_leads → outreach_log. First session delivers a fully verified dry-run pipeline. Flip to live with a single config flag.

## Agents
1. **lead_scanner** — reads `radar_targets` (status=active, new since last run), copies to `enriched_leads` with `status=pending_enrichment`. Idempotent on `radar_target_id`.
2. **lead_enricher** — reads `enriched_leads` (status=pending_enrichment), computes a score (urgency × confidence × recency × asset_value), writes back with `score` + `status=pending_outreach` (or `status=blocked` if missing required fields).
3. **lead_converter (dry-run)** — reads `enriched_leads` (status=pending_outreach, top N by score), runs compliance gate, picks the right SMS sequence + voice script, logs the would-send to `outreach_log` with `mode=dry_run`. Never actually sends.

## Schema (migrations)
- `enriched_leads` (id, radar_target_id, address, city, state, phone, email, warehouse_name, asset_value, source, created_at, score, status, last_enriched_at, meta)
- `outreach_log` (id, enriched_lead_id, channel, sequence, step, body_preview, would_send_at, compliance_passed, mode, created_at)
- `agent_activity` (id, agent_name, run_id, started_at, finished_at, status, rows_processed, rows_blocked, error, summary)
- `agent_config` (id, agent_name, enabled, dry_run, last_run_at, last_run_status, config_json)

## Cron
- lead_scanner: hourly
- lead_enricher: hourly (offset 5 min)
- lead_converter: every 30 min

## Build order (this session)
1. Migrations + soul.md templates for all 3 agents
2. lead_scanner agent + cron + first run on real data
3. You review: what got pulled from radar_targets
4. lead_enricher agent + cron + first run
5. You review: top-5 scored leads
6. lead_converter (dry-run) + cron + first run
7. You review: first 5 would-send messages
8. We flip the dry_run flag to live when you say go

## Known limitations
- Radar targets have NULL phone/email — contact discovery is a stub until we wire a skip-trace provider
- Vonage not actually wired (webhooks 404, app may need re-rotation) — dry-run doesn't need it, but live does
- Scoring is heuristic until we have outcome data — will be re-tuned after first 10 outreach attempts

## Verification per agent
- Code path exercised (run cron manually, see rows in DB)
- Non-zero exit
- Agent activity row written to agent_activity
- Config flag respected (enabled=false = no-op)
- Idempotent (re-running doesn't double-process)
