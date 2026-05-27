EMPIRE V49 · MASTER QUICKSTART
================================
Read once. Deploy in sequence. Skip nothing.

You have 14 files. They form one integrated revenue machine. Here's the order.


───────────────────────────────────────────────────────────────────────────────
THE 14 FILES — what each does
───────────────────────────────────────────────────────────────────────────────

CORE STACK (in hub.py's directory)
  empire_tokens.py           Design system · CSS variables, fonts, motion
  empire_layout.py           Shared chrome · sidebar + topbar + ticker
  empire_live.py             WebSocket broadcaster · real-time push
  empire_splash.py           Cinematic gateway · 1.5s focus entry
  empire_command_deck.py     Owner Mode flagship view
  empire_voice.py            Vonage hybrid voice engine
  empire_sms.py              TCPA-safe SMS sequence engine

LEAD GENERATION (standalone, runs on cron)
  pipeline.py                Master scraper · 4 phases
  smoke_test.py              Verifies Open-Meteo before live runs

DEPLOY FILES (root of repo)
  Procfile                   Dokku launch command
  runtime.txt                Python 3.11 pin
  requirements.txt           All pinned dependencies
  app.json                   Healthchecks + scale config
  nginx-websocket.conf       WebSocket proxy rules

GUIDES (markdown, not deployed)
  INTEGRATION.md             Hub upgrade — 9 surgical edits to hub.py
  PIPELINE_CRON.md           Cron + log rotation setup
  REVENUE_FLOW.md            End-to-end wire-up + TCPA checklist


───────────────────────────────────────────────────────────────────────────────
PHASE A · INFRASTRUCTURE (Day 1 · 2 hours)
───────────────────────────────────────────────────────────────────────────────

A1. Spin up Hetzner box (CCX13 or larger · Ubuntu 24.04)
A2. Install Dokku:
       wget -NP . https://dokku.com/install/v0.34.0/bootstrap.sh
       sudo DOKKU_TAG=v0.34.0 bash bootstrap.sh

A3. Add SSH key for git push:
       cat ~/.ssh/id_rsa.pub | ssh root@HETZNER_IP "sudo sshcommand acl-add dokku admin"

A4. Create the app:
       ssh root@HETZNER_IP "dokku apps:create empire-ai-uk"

A5. Wire your domain:
       dokku domains:add empire-ai-uk empire-ai.co.uk

A6. Install Dokku plugins:
       sudo dokku plugin:install https://github.com/dokku/dokku-letsencrypt.git
       sudo dokku plugin:install https://github.com/dokku/dokku-postgres.git
       sudo dokku plugin:install https://github.com/dokku/dokku-redis.git

A7. Provision Postgres + Redis (for caching, optional but recommended):
       dokku postgres:create empire-db
       dokku postgres:link empire-db empire-ai-uk
       dokku redis:create empire-redis
       dokku redis:link empire-redis empire-ai-uk

A8. WebSocket proxy timeouts:
       dokku nginx:set empire-ai-uk proxy-read-timeout 3600s
       dokku nginx:set empire-ai-uk proxy-send-timeout 3600s
       dokku proxy:build-config empire-ai-uk


───────────────────────────────────────────────────────────────────────────────
PHASE B · CONFIG (Day 1 · 30 minutes)
───────────────────────────────────────────────────────────────────────────────

B1. Get all your credentials in one place. You need:

      SUPABASE_URL=https://...
      SUPABASE_SERVICE_KEY=eyJhbGc...
      ANTHROPIC_API_KEY=sk-ant-...
      HUB_SECRET_TOKEN=pick_a_long_string
      NTFY_TOPIC=empire_private_alerts_xyz
      NTFY_TOKEN=tk_...                          (optional)

      VONAGE_API_KEY=...
      VONAGE_API_SECRET=...
      VONAGE_APP_ID=...                          (from developer.vonage.com)
      VONAGE_NUMBER=+18005550199                 (your purchased DID)

      RESEND_API_KEY=re_...                      (optional · for emails)
      RESEND_FROM="Empire AI <ops@empire-ai.co.uk>"
      RESEND_DIGEST_TO=your_email@domain.com

      USDC_WALLET=egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM
      EMPIRE_OPERATOR_NUMBER=+12145559999        (your phone)
      PUBLIC_BASE_URL=https://empire-ai.co.uk

B2. Set them all on Dokku at once:
       dokku config:set empire-ai-uk \
         SUPABASE_URL=... \
         SUPABASE_SERVICE_KEY=... \
         ANTHROPIC_API_KEY=... \
         HUB_SECRET_TOKEN=... \
         ...

B3. Upload Vonage private key (file Vonage gave you):
       scp vonage_private.key root@HETZNER_IP:/var/lib/dokku/data/storage/empire-ai-uk/

       dokku storage:mount empire-ai-uk \
         /var/lib/dokku/data/storage/empire-ai-uk/vonage_private.key:/app/vonage_private.key

       dokku config:set empire-ai-uk VONAGE_PRIVATE_KEY_PATH=/app/vonage_private.key


───────────────────────────────────────────────────────────────────────────────
PHASE C · SUPABASE SCHEMA (Day 1 · 15 minutes)
───────────────────────────────────────────────────────────────────────────────

C1. Open Supabase → SQL Editor

C2. Run the schema additions from REVENUE_FLOW.md
    (sms_sequences, sms_opt_outs, sms_log, call_events, radar_targets.phone)

C3. Verify the existing tables still exist:
       SELECT count(*) FROM radar_targets;
       SELECT count(*) FROM strike_log;
       SELECT count(*) FROM settlements;
       SELECT count(*) FROM ab_assignments;


───────────────────────────────────────────────────────────────────────────────
PHASE D · CODE INTEGRATION (Day 2 · 1 hour)
───────────────────────────────────────────────────────────────────────────────

D1. In your local repo, drop the 7 .py modules next to hub.py:
       empire_tokens.py
       empire_layout.py
       empire_live.py
       empire_splash.py
       empire_command_deck.py
       empire_voice.py
       empire_sms.py

D2. Drop Procfile, runtime.txt, requirements.txt, app.json in repo root

D3. Open hub.py and follow INTEGRATION.md steps 1-7
    (imports, HUB_TOKEN wiring, WebSocket route, heartbeat, broadcast calls,
     root route swap)

D4. Open hub.py and follow REVENUE_FLOW.md "Wire-up in hub.py" section
    (voice router, SMS engine, brain-triggered enrollment)

D5. Test locally first:
       pip install -r requirements.txt
       export $(cat .env | xargs)
       uvicorn hub:app --reload

       Visit http://localhost:8000 — splash should load


───────────────────────────────────────────────────────────────────────────────
PHASE E · DEPLOY (Day 2 · 15 minutes)
───────────────────────────────────────────────────────────────────────────────

E1. Commit and push:
       git add .
       git commit -m "Empire V49 · full stack"
       git remote add dokku dokku@HETZNER_IP:empire-ai-uk
       git push dokku main

E2. Watch the deploy log:
       ssh root@HETZNER_IP "dokku logs empire-ai-uk -t"

E3. Enable SSL:
       dokku letsencrypt:enable empire-ai-uk

E4. Visit https://empire-ai.co.uk — splash gateway loads

E5. Click anywhere → 1.5s engagement bar fills → Command Deck appears


───────────────────────────────────────────────────────────────────────────────
PHASE F · VONAGE WEBHOOKS (Day 2 · 10 minutes)
───────────────────────────────────────────────────────────────────────────────

F1. developer.vonage.com → Your application → Capabilities

F2. Voice Answer URL:      https://empire-ai.co.uk/api/v1/voice/answer
    Voice Event URL:       https://empire-ai.co.uk/api/v1/voice/events
    Messages Inbound URL:  https://empire-ai.co.uk/api/v1/sms/inbound

F3. Link your DID to the application

F4. Test inbound: call your Vonage number from your cell
    Expected: voice answers with Empire AI identification, ntfy push to your phone


───────────────────────────────────────────────────────────────────────────────
PHASE G · LEAD PIPELINE (Day 3 · 1 hour)
───────────────────────────────────────────────────────────────────────────────

G1. SSH to Hetzner: ssh root@HETZNER_IP

G2. Follow PIPELINE_CRON.md exactly
    (mkdir, venv, .env file, smoke test, cron entry, logrotate)

G3. Put your URL list in /opt/empire-pipeline/master_whales.txt

G4. Run smoke test manually:
       cd /opt/empire-pipeline
       source .env && export $(cut -d= -f1 .env)
       ./venv/bin/python smoke_test.py

       Expect: weather readings for Dallas, Houston, Mobile

G5. Run pipeline manually once:
       ./venv/bin/python pipeline.py

       Expect: phase banners, X verified hits, CSV written, Supabase pushed,
               ntfy pinged your phone

G6. Wire the cron entry from PIPELINE_CRON.md


───────────────────────────────────────────────────────────────────────────────
PHASE H · END-TO-END VERIFICATION (Day 3 · 30 minutes)
───────────────────────────────────────────────────────────────────────────────

The full loop test. Use YOUR phone as the test target.

H1. Insert a fake target with your number in Supabase:
       INSERT INTO radar_targets
         (address, phone, location, status, damage_severity, urgency_score)
       VALUES
         ('Test Whale', '+1YOUR_NUMBER', 'POINT(-96.7970 32.7767)',
          'active', 'severe', 9);

H2. Enroll it in the SMS sequence manually:
       curl -X POST https://empire-ai.co.uk/api/v1/sms/enroll \
            -H "Authorization: Bearer $HUB_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"phone":"+1YOUR_NUMBER","target_addr":"Test Whale"}'

H3. Within 60 seconds: your phone receives the first SMS

H4. Reply STOP from your phone

H5. Within 5 seconds: your phone receives the opt-out confirmation

H6. Check Supabase:
       SELECT * FROM sms_opt_outs WHERE phone = '+1YOUR_NUMBER';
       SELECT status FROM sms_sequences WHERE phone = '+1YOUR_NUMBER';
       (should show: opt-out row exists, sequence status = 'opted_out')

H7. Delete the test row:
       DELETE FROM radar_targets WHERE address = 'Test Whale';
       DELETE FROM sms_sequences WHERE phone = '+1YOUR_NUMBER';
       DELETE FROM sms_opt_outs  WHERE phone = '+1YOUR_NUMBER';

If H1-H6 all worked, the full loop is live.


───────────────────────────────────────────────────────────────────────────────
WHAT YOU HAVE NOW
───────────────────────────────────────────────────────────────────────────────

  ✓ Hetzner bare metal · cooling pods · sovereign infrastructure
  ✓ Dokku PaaS · git push deploys · WebSocket-capable
  ✓ empire-ai.co.uk · SSL · cinematic splash gateway
  ✓ /command Owner Mode dashboard · live brain decisions, revenue stream
  ✓ Empire Brain · Claude-powered GO/NO_GO with calibration
  ✓ Subconscious Mind · 24/7 storm + NWS cross-referencing
  ✓ Storm Pipeline · cron-driven lead scraper every 2 hours
  ✓ Vonage Voice Engine · hybrid-ready, in-house SIP migration path
  ✓ SMS Sequence Engine · 5-touch drip, TCPA-compliant
  ✓ Contractor Strike Portal · magic-link dispatch
  ✓ Solana Revenue Watcher · auto-detects 1% fee payments
  ✓ Calibration Layer · brain self-tunes from settled outcomes
  ✓ Manus Operator hook · armed and ready
  ✓ TCPA opt-out registry · global · honored on re-enrollment

This is what a real predictive-cloud business looks like under the hood.
Now go close whales.
