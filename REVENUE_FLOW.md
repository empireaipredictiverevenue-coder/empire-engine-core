EMPIRE V49 · REVENUE FLOW INTEGRATION
========================================

How the pieces actually connect into a closed-loop revenue machine.


───────────────────────────────────────────────────────────────────────────────
THE FULL FLYWHEEL
───────────────────────────────────────────────────────────────────────────────

  STEP 1  pipeline.py (cron, every 2h)
            ↓ scrapes URLs, verifies storms via Open-Meteo
            ↓ writes to radar_targets, pushes to ntfy
            ↓
  STEP 2  Subconscious Mind (hub.py, every 5min)
            ↓ cross-references radar_targets with live NWS alerts
            ↓ fires strike_log entry on a real hit
            ↓
  STEP 3  Empire Brain (Claude · GO/NO_GO per strike)
            ↓ evaluates urgency, asset value, calibration history
            ↓ returns GO if urgency >= 7
            ↓
  STEP 4  Outreach launches IN PARALLEL:
            ┌──────────────────┬──────────────────┐
            ↓                  ↓                  ↓
       SMS sequence      Vonage strike call    Manus operator
       (5 touches/7d)    (immediate)           (deep research)
            ↓                  ↓                  ↓
            └──────────────────┴──────────────────┘
                              ↓
  STEP 5  Lead responds (reply, callback, email)
            ↓
  STEP 6  Contractor dispatch (magic link · empire-ai.co.uk/contractor/...)
            ↓ contractor accepts, goes on-site, marks complete
            ↓
  STEP 7  Insurance claim filed by property owner
            ↓ (Empire AI is NOT the filer · the owner files)
            ↓
  STEP 8  Outcome recorded (POST /api/v1/record-outcome)
            ↓ settled = success, 3% fee due
            ↓
  STEP 9  USDC fee paid to Solana wallet
            ↓ Solana revenue watcher detects (every 2min)
            ↓ pushes to live dashboard
            ↓
  STEP 10 Calibration layer learns
            ↓ brain reads track record on next decision
            ↓ thresholds self-tune over time
            ↓
            └─→ (back to STEP 1, smarter)


───────────────────────────────────────────────────────────────────────────────
WIRE-UP IN hub.py — full sequence
───────────────────────────────────────────────────────────────────────────────

After the V49 base imports (empire_tokens, empire_layout, etc.), add these:

    # ────────────────────────────────────────────────────────────────────
    # OUTREACH ENGINE — Voice + SMS
    # ────────────────────────────────────────────────────────────────────
    from empire_voice import VoiceRouter, register_voice_routes
    from empire_sms   import SMSSequenceEngine, register_sms_routes

    # Voice router
    voice_router = VoiceRouter(
        vonage_api_key=          os.environ.get("VONAGE_API_KEY", ""),
        vonage_api_secret=       os.environ.get("VONAGE_API_SECRET", ""),
        vonage_app_id=           os.environ.get("VONAGE_APP_ID", ""),
        vonage_private_key_path= os.environ.get("VONAGE_PRIVATE_KEY_PATH", ""),
        vonage_number=           os.environ.get("VONAGE_NUMBER", ""),
        public_base_url=         PUBLIC_BASE_URL,
    )

    register_voice_routes(
        app,
        voice_router,
        require_auth= require_auth,
        get_db=       get_db,
        ntfy_topic=   NTFY_TOPIC,
        ntfy_token=   NTFY_TOKEN,
        broadcaster=  live_broadcaster,
    )

    # SMS engine
    sms_engine = SMSSequenceEngine(
        voice_router=    voice_router,
        get_db=          get_db,
        identity_prefix= os.environ.get("EMPIRE_SMS_PREFIX", "Empire AI:"),
        max_per_minute=  int(os.environ.get("EMPIRE_SMS_RATE", "6")),
    )

    register_sms_routes(
        app,
        sms_engine,
        require_auth= require_auth,
        broadcaster=  live_broadcaster,
    )


And in your @app.on_event("startup") handler, ADD this line:

    # Empire V49 — SMS dispatcher loop
    asyncio.create_task(sms_engine.dispatcher_loop())


───────────────────────────────────────────────────────────────────────────────
WIRE THE BRAIN TO TRIGGER OUTREACH ON A GO
───────────────────────────────────────────────────────────────────────────────

Inside _subconscious_cycle(), at the point where the brain returns GO and
trigger_manus_operator(p, analysis) is called, ADD this AFTER the Manus call:

                        # High-confidence GO → fire Manus AND launch outreach
                        if (analysis["decision"] == "GO"
                            and analysis.get("urgency", 0) >= BRAIN_MIN_URGENCY):
                            print(f"[brain] GO · urgency {analysis['urgency']}/10 · {p.get('address')}")
                            await trigger_manus_operator(p, analysis)

                            # ─────────────────────────────────────────────
                            # Empire V49 — auto-launch SMS sequence
                            # ─────────────────────────────────────────────
                            target_phone = p.get("phone", "")
                            if target_phone:
                                await sms_engine.enroll(
                                    phone=         target_phone,
                                    target_addr=   p.get("address", ""),
                                    sequence_type="storm_strike",
                                    meta={
                                        "urgency":     analysis.get("urgency"),
                                        "asset_value": asset_val_num,
                                        "event":       alert.get("event"),
                                        "severity":    severity,
                                    },
                                )

                            # ─────────────────────────────────────────────
                            # Empire V49 — auto-place voice strike if number is known
                            # ─────────────────────────────────────────────
                            operator_number = os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
                            if target_phone and operator_number:
                                await voice_router.place_strike_call(
                                    to_number=        target_phone,
                                    target_address=   p.get("address", ""),
                                    asset_value=      asset_val_num,
                                    operator_number=  operator_number,
                                    broadcaster=      live_broadcaster,
                                )


───────────────────────────────────────────────────────────────────────────────
SUPABASE SCHEMA — run these once
───────────────────────────────────────────────────────────────────────────────

The voice + SMS engines need three new tables. Run this in your Supabase
SQL editor:

    -- ────────────────────────────────────────────────────────────────────
    -- SMS sequences
    -- ────────────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS sms_sequences (
      id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at      timestamptz NOT NULL DEFAULT now(),
      phone           text NOT NULL UNIQUE,
      target_addr     text,
      sequence_type   text NOT NULL DEFAULT 'storm_strike',
      current_step    int  NOT NULL DEFAULT 0,
      status          text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','paused','completed','opted_out','replied')),
      last_sent_at    timestamptz,
      next_send_at    timestamptz,
      replies_count   int DEFAULT 0,
      meta            jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS sms_sequences_dispatch_idx
      ON sms_sequences (status, next_send_at);
    CREATE INDEX IF NOT EXISTS sms_sequences_phone_idx
      ON sms_sequences (phone);

    -- TCPA opt-out registry
    CREATE TABLE IF NOT EXISTS sms_opt_outs (
      phone       text PRIMARY KEY,
      created_at  timestamptz NOT NULL DEFAULT now(),
      reason      text DEFAULT 'STOP keyword',
      meta        jsonb DEFAULT '{}'::jsonb
    );

    -- SMS log (every send + receive)
    CREATE TABLE IF NOT EXISTS sms_log (
      id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at    timestamptz NOT NULL DEFAULT now(),
      phone         text NOT NULL,
      direction     text CHECK (direction IN ('outbound','inbound')),
      body          text,
      step          int,
      message_uuid  text,
      delivered     boolean DEFAULT false
    );
    CREATE INDEX IF NOT EXISTS sms_log_phone_idx
      ON sms_log (phone, created_at DESC);

    -- Call lifecycle events
    CREATE TABLE IF NOT EXISTS call_events (
      id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at  timestamptz NOT NULL DEFAULT now(),
      call_uuid   text,
      status      text,
      direction   text,
      duration    int DEFAULT 0,
      meta        jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS call_events_uuid_idx
      ON call_events (call_uuid);
    CREATE INDEX IF NOT EXISTS call_events_recent_idx
      ON call_events (created_at DESC);

    -- ────────────────────────────────────────────────────────────────────
    -- radar_targets needs a phone column to be useful for outreach.
    -- This may already exist — the IF NOT EXISTS makes it safe to re-run.
    -- ────────────────────────────────────────────────────────────────────
    ALTER TABLE radar_targets
      ADD COLUMN IF NOT EXISTS phone text;
    CREATE INDEX IF NOT EXISTS radar_targets_phone_idx
      ON radar_targets (phone) WHERE phone IS NOT NULL;


───────────────────────────────────────────────────────────────────────────────
ENVIRONMENT VARIABLES — add to .env / Dokku config
───────────────────────────────────────────────────────────────────────────────

    # Vonage Voice API (sign up at developer.vonage.com)
    VONAGE_API_KEY=your_key
    VONAGE_API_SECRET=your_secret
    VONAGE_APP_ID=your_app_uuid
    VONAGE_PRIVATE_KEY_PATH=/app/vonage_private.key   # the file Vonage gave you
    VONAGE_NUMBER=+18005550199                         # your purchased DID

    # Where outbound calls should bridge to once the prospect answers
    EMPIRE_OPERATOR_NUMBER=+12145559999                 # your phone

    # SMS engine
    EMPIRE_SMS_PREFIX=Empire AI:                        # TCPA-required prefix
    EMPIRE_SMS_RATE=6                                   # max sends/minute

    # Public URL (used for webhook callbacks)
    PUBLIC_BASE_URL=https://empire-ai.co.uk

    # Dokku set them with:
    #   dokku config:set empire-ai-uk VONAGE_API_KEY=...

Push the private key file to Dokku separately:
    scp vonage_private.key root@HETZNER_IP:/var/lib/dokku/data/storage/empire-ai-uk/
    dokku storage:mount empire-ai-uk /var/lib/dokku/data/storage/empire-ai-uk/vonage_private.key:/app/vonage_private.key


───────────────────────────────────────────────────────────────────────────────
VONAGE APPLICATION SETUP — one-time
───────────────────────────────────────────────────────────────────────────────

1. Sign in to developer.vonage.com
2. Applications → Create a new application
3. Name: "Empire AI Voice"
4. Generate public/private keys → save the private key file
5. Capabilities → Enable Voice and Messages
6. Voice Answer URL:  https://empire-ai.co.uk/api/v1/voice/answer
7. Voice Event URL:   https://empire-ai.co.uk/api/v1/voice/events
8. Messages Inbound: https://empire-ai.co.uk/api/v1/sms/inbound
9. Messages Status:  https://empire-ai.co.uk/api/v1/voice/events
10. Link your purchased DID to the application


───────────────────────────────────────────────────────────────────────────────
TCPA COMPLIANCE CHECKLIST — non-negotiable
───────────────────────────────────────────────────────────────────────────────

The SMS + Voice engines are designed to be TCPA-safe out of the box, but the
LEGAL OBLIGATION is yours. Verify:

  [ ] Every SMS starts with "Empire AI:" (paid commercial identification)
  [ ] First message in every sequence includes "Reply STOP to opt out"
  [ ] STOP / UNSUBSCRIBE / CANCEL keywords trigger immediate opt-out
  [ ] HELP keyword returns identification + opt-out info
  [ ] No SMS sent 9 PM - 8 AM local time
  [ ] Confirmation SMS sent after STOP (TCPA-required)
  [ ] opt-out registry is honored across ALL future enrollments
  [ ] Voice calls identify as paid commercial within the first 5 seconds
  [ ] Inbound calls have a clear "this is Empire AI" greeting
  [ ] Call recording disclosures if you enable recording
  [ ] DNC list scrubbing if you scale beyond warm-lead outreach
  [ ] Consult a TCPA attorney before bulk outreach above 1,000/day

If any of these are missing or broken, fix them BEFORE going live.
TCPA fines are $500-$1,500 per violation. One bad campaign = real money.


───────────────────────────────────────────────────────────────────────────────
TESTING THE FULL LOOP — end-to-end smoke test
───────────────────────────────────────────────────────────────────────────────

After everything is wired:

1. Insert a test lead with YOUR phone number:
       INSERT INTO radar_targets (address, phone, location, status, damage_severity, urgency_score)
       VALUES ('Test Facility', '+12145551234', 'POINT(-96.7970 32.7767)', 'active', 'severe', 9);

2. Enroll it manually:
       curl -X POST https://empire-ai.co.uk/api/v1/sms/enroll \
            -H "Authorization: Bearer $HUB_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"phone":"+12145551234","target_addr":"Test Facility"}'

3. Check /view/calibration → see the enrollment
4. Wait ~60 seconds for the dispatcher → first SMS lands on your phone
5. Reply STOP to your test phone
6. Verify opt_out registered in Supabase: SELECT * FROM sms_opt_outs;
7. Verify sequence status = 'opted_out'

If all three pieces fire, the loop is closed.
