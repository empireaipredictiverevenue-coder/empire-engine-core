# Empire AI · Predictive Revenue — Idea Parking Lot

# Format: - [YYYY-MM-DD] one-line idea · ~why
# See README.md for the KEEP / DEFER / DROP filter

- [2026-06-11] outreach agent (sms + voice sequences) for leads and contractors · dispatch loop blocked on vonage 401 + 0 contractors
- [2026-06-11] sales + marketing agent with "god prompt" · same blockers as outreach
- [2026-06-11] predictive-revenue ecosystem on top of empire-v49 · no real fees yet, model would train on stub data
- [2026-06-11] god mode command · unclear scope, asked 3 times, never pinned down
- [2026-06-11] youtube production agent (script + record + edit + publish pipeline) · needs content strategy + video pipeline + distribution plan, none of which exist
- [2026-06-11] social media manager agent (run all pages and channel of Empire-AI) · needs existing accounts (which platforms? do they exist?), no measurable outcome, fails STARTING_POINT filter
- [2026-06-11] every agent needs soul.md · done for outreach, deferred for the 30+ legacy scripts in bots/ (would take an hour, requires reading code i haven't read, no real outcome)
- [2026-06-11] empire_lead_router: 4-persona panel debate (CFO/Growth/Strategy/Purist) for lead routing · needs 4 storm-specific persona prompts + JSON decision schema + real lead volume + conversion feedback loop. "1.7B context" framing is a misunderstanding — design as 4 small calls, not one super-prompt. Currently stub data.
- [2026-06-11] /opt/empire-pipeline/pipeline.py replaced with 15-line stub · real scraper (phase_2_clean/phase_3_radar/phase_4_vault/log) ran 5/13-5/14, then was deleted, no backup, no git history. smoke_test.py imports symbols that don't exist anymore. Last real run 2026-05-14. venv still has openmeteo_requests + pyiceberg + pandas. Reconstruct from docs (PIPELINE_CRON.md describes phases) or restore from a backup you have elsewhere.
