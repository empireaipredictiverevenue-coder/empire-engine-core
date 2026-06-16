# Empire-AI Quick Access

> Operator-agent memory file. Read at session start so I don't have to
> re-learn the system.

## Inbound email
- **Gmail IMAP** is wired. `flavag83@gmail.com` (app password in `/root/.env`).
  - IMAP creds: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` (16-char)
  - Scanner: `/tmp/gmail_scan2.py` (also at `/root/empire-v49/scripts/gmail_scan.py`)
  - Scans INBOX + Spam + Trash + Promotions for `empire-ai`/`empire ai` mentions
  - Classifies intent (interested/question/opt_out/not_now), backfills to `inbox_messages`,
    sends Telegram alert for interesting intents
  - Cron: `0 6 * * *` (daily 06:00 UTC, after Resend cron at 06:00 but before money digest at 06:30)
  - Robust to IMAP disconnects — reconnects per message
- **Resend inbound** is wired (cloudflared tunnel + webhook).
  - Tunnel URL: `https://mailed-transcript-completing-stripes.trycloudflare.com`
  - Webhook: `cebebccd-...` → tunnel → `/api/v1/inbound/email` on port 9120
  - `agents/inbound_handler/server.py` runs on port 9120
  - Domain: empire-ai.co.uk MX → `inbound-smtp.us-east-1.amazonaws.com` (verified)
  - Carrier emails from `Phillip Livesley <philliplivesley@empire-ai.co.uk>` (NOT `phil@`)
- **Don't read both `phil@` and `philliplivesley@` as the same.** They are different
  inboxes on the same domain. Use `philliplivesley@` for the canonical From address.

## Storm pipeline (the only proven revenue path)
- `/opt/empire-pipeline/pipeline.py` — storm URL → scrape → wind check → Supabase push
- **address=null bug FIXED** (was losing storm hits): use city as fallback
- State cache: 7-day TTL on processed URLs (was: forever, so re-scans never happened)
- Pipeline runs every 2h 06:00-22:00 Central

## Outbound
- **Carrier drafts**: `/root/empire-v49/carrier_outreach_drafts/`
  - Send script: `/tmp/send_carrier_drafts.py`
  - Resend daily quota: 100/day. Burns fast. Retry cron: `*/30 * * * *`
  - 5 drafts queued: Allstate, Farmers, Liberty Mutual, State Farm, USAA
  - From: `Phillip Livesley <philliplivesley@empire-ai.co.uk>` (changed 2026-06-16)
- **Affiliate recruiter**: was burning quota with garbage emails. **DISABLED** in
  agent_config. Keep disabled until affiliate pipeline is fixed.

## Voice
- `agents/contractor_outreach/outreach.py` — voice lane for named contractors
- Cron every 4h, 5 calls/run, dry_run=false
- 24 named contractors (real first names from decision_makers)
- `voice_outcome`, `last_voice_call_at`, `voice_call_count` columns on contractors
- Manual CLI: `/tmp/call_one_contractor.py`
- ENV: `EMPIRE_BYPASS_CALL_HOURS=1` skips the call-hours check (for testing only)

## Hub
- `hub.py` on port 8000 (PM2: `empire-hub`)
- **Restart safely**: `bash /root/empire-v49/scripts/hub_restart.sh` — clears
  __pycache__ first (root cause of "port 8000 not bound" issues), restarts, waits
  for port to come up
- Common port-bind race: clear `__pycache__` before restart
- After any empire_sms.py change: also restart, give ~90s for slow imports

## Bigger picture (don't reduce empire-ai to "storm damage company")
- Multi-niche autonomous revenue engine: storm + mass tort + legal + B2B + affiliate + SEO
- See `/root/empire-v49/STARTING_POINT.md` (source of truth) and `AGENTS.md`
- 43 bots, 21 agents, 20 products, 4 matrices (sovereign AGI, ROI marketing, landing, universal)
- 10+ PM2 services running in parallel
- Predictive-revenue coder is a separate profile (`empireaipredictiverevenue-coder`)

## Money report
- `/tmp/money_report.py` — 6-section one-pager, plain text
- `/tmp/money_digest.py` — sends to Telegram daily at 06:30 UTC
- `/tmp/qcheck.py` — SMS queue status
- `/tmp/money_json` — JSON for custom reports

## Triage
- If a user pastes an email and says "what is this" / "the alt-pay reply" — **read the
  source code first** (e.g. `bots/affiliate_recruiter.py` to see what was actually sent)
  before drafting a response. Don't assume from memory.

## Commit protocol
- Branch: `fix/<name>-<date>` or `feat/<name>-<date>`
- Commit author: `striker@empire-ai.co.uk` (per AGENTS.md)
- Fee-copy guard runs on every commit. Don't include 1% fee references.
- Push to origin, don't auto-merge to master unless user said.
