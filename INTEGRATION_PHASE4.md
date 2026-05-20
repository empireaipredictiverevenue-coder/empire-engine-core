EMPIRE V49 · PHASE 4 INTEGRATION
==================================
The final two modules. After this, all 8 gaps closed.


───────────────────────────────────────────────────────────────────────────────
WHAT'S NEW IN PHASE 4
───────────────────────────────────────────────────────────────────────────────

  empire_auth.py     Multi-operator authentication + audit log
                     → magic-link login (no passwords)
                     → roles: owner / operator / viewer
                     → per-request operator attribution
                     → audit trail of every privileged action
                     → backwards-compatible with HUB_TOKEN for cron

  empire_inbound.py  Inbound call triage (SAFE VERSION)
                     → automated answering with explicit AI disclosure
                     → DTMF routing: 1=forward, 2=voicemail, 3=opt-out
                     → Whisper transcription of voicemails
                     → Claude urgency scoring of transcripts
                     → high-urgency calls push to playbook + ntfy


───────────────────────────────────────────────────────────────────────────────
WHY THE INBOUND MODULE IS DELIBERATELY LIMITED
───────────────────────────────────────────────────────────────────────────────

I drew a hard line in this module. Here's exactly what it does and doesn't:

  ✅ DOES                              ❌ DOES NOT
  ────────────                         ──────────────
  Identify itself as AI in greeting    Pretend to be a human
  Capture caller's choice (DTMF)       Have a conversational AI dialogue
  Forward to a real human operator     Conduct AI-driven sales pitches
  Take a voicemail                     Collect personal/financial info via AI
  Transcribe AFTER the call            Make legal/insurance claims to caller
  Score urgency AFTER the call         Auto-call people back with AI voice
  Surface priority callbacks           Generate AI voice outbound messages

WHY THIS MATTERS
────────────────
California SB-942 (signed Sep 2024), Illinois HB-3773 (AI in calls,
effective Jan 2026), New York AB-9314, and the FCC's TCPA AI Declaratory
Ruling (Feb 2024) all impose stricter disclosure requirements when AI is
used in voice interactions.

The SAFE design above is:
  - Always discloses AI at the start
  - Hands off to humans for any conversational interaction
  - AI does post-call processing where there's no caller present
  - No risk of "AI mistaken for human" lawsuits

If you later want richer AI-driven voice interactions (e.g. AI screening
callers conversationally before forwarding), that's possible — but it
needs:
  1. Per-state disclosure logic (different states have different rules)
  2. Recorded consent before AI takes any action
  3. Real legal review · not from this assistant

Until you have all three, the SAFE version is the right product.


───────────────────────────────────────────────────────────────────────────────
SUPABASE SCHEMA
───────────────────────────────────────────────────────────────────────────────

Run all of this in your SQL editor:

    -- ──────────────────── MULTI-OPERATOR AUTH ──────────────────────
    CREATE TABLE IF NOT EXISTS operators (
      id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at   timestamptz NOT NULL DEFAULT now(),
      email        text NOT NULL UNIQUE,
      name         text NOT NULL,
      role         text NOT NULL DEFAULT 'operator'
        CHECK (role IN ('owner','operator','viewer')),
      active       boolean NOT NULL DEFAULT true,
      last_login   timestamptz,
      invited_by   uuid REFERENCES operators(id),
      meta         jsonb DEFAULT '{}'::jsonb
    );

    CREATE TABLE IF NOT EXISTS operator_sessions (
      id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at   timestamptz NOT NULL DEFAULT now(),
      operator_id  uuid NOT NULL REFERENCES operators(id),
      token_hash   text NOT NULL,
      expires_at   timestamptz NOT NULL,
      revoked_at   timestamptz,
      user_agent   text,
      ip           text
    );
    CREATE INDEX IF NOT EXISTS operator_sessions_hash_idx
      ON operator_sessions (token_hash);

    CREATE TABLE IF NOT EXISTS audit_log (
      id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at    timestamptz NOT NULL DEFAULT now(),
      operator_id   uuid,
      operator_name text,
      action        text NOT NULL,
      target_type   text,
      target_id     text,
      details       jsonb DEFAULT '{}'::jsonb,
      ip            text
    );
    CREATE INDEX IF NOT EXISTS audit_log_created_idx
      ON audit_log (created_at DESC);
    CREATE INDEX IF NOT EXISTS audit_log_operator_idx
      ON audit_log (operator_id, created_at DESC);

    -- ⚠ CRITICAL · run this with your actual email to bootstrap the owner:
    INSERT INTO operators (email, name, role)
    VALUES ('YOUR_REAL_EMAIL@empire-ai.co.uk', 'Empire Owner', 'owner')
    ON CONFLICT (email) DO NOTHING;

    -- ──────────────────── INBOUND CALLS ────────────────────────────
    CREATE TABLE IF NOT EXISTS inbound_calls (
      id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at      timestamptz NOT NULL DEFAULT now(),
      call_uuid       text UNIQUE NOT NULL,
      from_number     text NOT NULL,
      to_number       text,
      duration        int DEFAULT 0,
      disposition     text
        CHECK (disposition IN ('forwarded','voicemail','opt_out','hung_up')),
      recording_url   text,
      recording_path  text,
      transcript      text,
      urgency_score   int,
      intent          text,
      matched_lead_id uuid,
      status          text DEFAULT 'new'
        CHECK (status IN ('new','reviewed','called_back','closed')),
      meta            jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS inbound_calls_status_idx
      ON inbound_calls (status, urgency_score DESC, created_at DESC);
    CREATE INDEX IF NOT EXISTS inbound_calls_from_idx
      ON inbound_calls (from_number);


───────────────────────────────────────────────────────────────────────────────
WIRE-UP IN hub.py
───────────────────────────────────────────────────────────────────────────────

Add the imports:

    from empire_auth import (
        AuthEngine,
        register_auth_routes,
        require_role,
    )
    from empire_inbound import (
        InboundCallTriage,
        register_inbound_routes,
        build_safe_inbound_ncco,
    )

Initialize before existing route registration:

    # ────────────────────────────────────────────────────────────────────
    # MULTI-OPERATOR AUTH (replaces shared-token model)
    # ────────────────────────────────────────────────────────────────────
    auth_engine = AuthEngine(
        get_db=          get_db,
        sign_token=      _sign_token,
        verify_token=    _verify_token,
        send_email=      _send_email,
        public_base_url= PUBLIC_BASE_URL,
        legacy_hub_token=HUB_TOKEN,           # keep cron + pipeline working
        session_ttl_hours=12,
    )

    # The require_auth dependency is now per-operator with backwards compat:
    require_auth     = auth_engine.require_auth
    require_owner    = require_role(auth_engine, "owner")
    require_operator = require_role(auth_engine, "operator")

    register_auth_routes(
        app,
        auth_engine= auth_engine,
        require_auth=require_auth,
    )

    # ────────────────────────────────────────────────────────────────────
    # INBOUND CALL TRIAGE (safe version)
    # ────────────────────────────────────────────────────────────────────
    inbound_triage = InboundCallTriage(
        get_db=          get_db,
        anthropic_key=   os.environ.get("ANTHROPIC_API_KEY", ""),
        openai_key=      os.environ.get("OPENAI_API_KEY", ""),
        operator_number= os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
        broadcaster=     live_broadcaster,
        ntfy_topic=      NTFY_TOPIC,
        ntfy_token=      NTFY_TOKEN,
    )

    register_inbound_routes(app, inbound_triage, require_auth=require_auth)


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — switch the existing Vonage inbound handler to the safe NCCO
───────────────────────────────────────────────────────────────────────────────

In empire_voice.py's `voice_answer` route, REPLACE:

    ncco = ncco_inbound_strike(
        target_address=target_address,
        severity=severity,
        forward_to=operator_number,
    )

WITH:

    ncco = build_safe_inbound_ncco(
        business_name="Empire AI",
        operator_number=operator_number,
        recording_url=f"{PUBLIC_BASE_URL}/api/v1/inbound",
    )


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — protect privileged endpoints with role checks
───────────────────────────────────────────────────────────────────────────────

For OWNER-ONLY endpoints (payout approval, role changes, etc), update
the dependency:

    # BEFORE (any token works):
    @app.post("/api/v1/payouts/approve")
    async def payouts_approve(..., auth: bool = Depends(require_auth)):
        ...

    # AFTER (only owners can approve payouts):
    @app.post("/api/v1/payouts/approve")
    async def payouts_approve(..., op: dict = Depends(require_owner)):
        # op['id'] is the operator UUID for audit logging
        await auth_engine.audit(
            operator_id=op["id"],
            operator_name=op["name"],
            action="payout_approved",
            target_type="settlement",
            target_id=body.get("settlement_id"),
        )
        ...

For OPERATOR-OR-OWNER endpoints (most everyday actions), use require_operator:

    @app.post("/api/v1/contractors/approve")
    async def approve_application(..., op: dict = Depends(require_operator)):
        ...

For VIEWER-AND-ABOVE endpoints (read-only dashboards), use require_auth:

    @app.get("/api/v1/attribution/funnel")
    async def funnel(..., op: dict = Depends(require_auth)):
        ...

ROLE MATRIX TO ENFORCE
─────────────────────
                              dep             example endpoints
  owner-only                  require_owner   /api/v1/payouts/{approve,cancel}
                                              /api/v1/auth/{invite,operators,audit}
  operator-or-owner           require_operator /api/v1/contractors/approve
                                              /api/v1/matching/dispatch
                                              /api/v1/record-outcome
  viewer-or-above             require_auth     /api/v1/attribution/*
                                              /api/v1/playbook/*
                                              all /view/* routes


───────────────────────────────────────────────────────────────────────────────
ENVIRONMENT VARIABLES — Phase 4 additions
───────────────────────────────────────────────────────────────────────────────

    # For Whisper transcription of voicemails
    OPENAI_API_KEY=sk-...

    # Where inbound "press 1 for operator" forwards to
    EMPIRE_OPERATOR_NUMBER=+12145559999

Set them with:
    dokku config:set empire-ai-uk \
      OPENAI_API_KEY=sk-... \
      EMPIRE_OPERATOR_NUMBER=+12145559999


───────────────────────────────────────────────────────────────────────────────
VONAGE WEBHOOK CONFIG — update one URL
───────────────────────────────────────────────────────────────────────────────

In your Vonage Application:
  - Event URL stays the same
  - Inbound Messages stays the same
  - Voice Answer URL stays the same (now serves the safe NCCO)
  - ADD: a "Recording" event URL pointing to:
        https://empire-ai.co.uk/api/v1/inbound/recording


───────────────────────────────────────────────────────────────────────────────
END-TO-END TEST · the auth flow
───────────────────────────────────────────────────────────────────────────────

1. Bootstrap the owner account in Supabase (already in schema above)

2. Visit https://empire-ai.co.uk/auth/login
   - Enter the owner email · click "Send login link"
   - Check inbox · click magic link
   - You're redirected to a success page
   - Click "Open Command Deck" · should work normally

3. Invite a second operator:
       curl -X POST https://empire-ai.co.uk/api/v1/auth/invite \
            -H "Authorization: Bearer <YOUR_SESSION_TOKEN>" \
            -H "Content-Type: application/json" \
            -d '{
              "email": "operator2@empire-ai.co.uk",
              "name": "Operator Two",
              "role": "operator"
            }'

4. They get an invite email · click magic link · they're logged in

5. Operator Two tries to approve a payout:
       (returns 403 · Forbidden · payouts are owner-only)

6. Check audit log:
       curl https://empire-ai.co.uk/api/v1/auth/audit \
            -H "Authorization: Bearer <YOUR_SESSION_TOKEN>"
   (shows: login events, operator_invited, the 403 attempt, etc)


───────────────────────────────────────────────────────────────────────────────
END-TO-END TEST · the inbound call flow
───────────────────────────────────────────────────────────────────────────────

1. Call your Vonage DID from your cell

2. You hear: "Thank you for calling Empire AI. You have reached our
   automated answering service..."

3. Press 2 to leave a voicemail

4. Record a 10-second message · press # to end

5. Within ~30 seconds:
   - inbound_calls row appears in Supabase
   - transcript column populated
   - urgency_score scored
   - operator gets a ntfy push if urgency >= 8

6. Visit /view/playbook · the call appears in the 5-min tasks queue


───────────────────────────────────────────────────────────────────────────────
THE COMPLETE V49 BUILD · 15 MODULES · ALL GAPS CLOSED
───────────────────────────────────────────────────────────────────────────────

Phase 1 (Foundation):
  ✓ empire_tokens.py
  ✓ empire_layout.py
  ✓ empire_live.py
  ✓ empire_splash.py
  ✓ empire_command_deck.py
  ✓ empire_voice.py
  ✓ empire_sms.py

Phase 2 (Outreach completion):
  ✓ empire_contractors.py
  ✓ empire_attribution.py
  ✓ empire_email.py

Phase 3 (Revenue loop closure):
  ✓ empire_matching.py
  ✓ empire_playbook.py
  ✓ empire_payouts.py

Phase 4 (Team + inbound):
  ✓ empire_auth.py
  ✓ empire_inbound.py

Lead generation:
  ✓ pipeline.py
  ✓ smoke_test.py

Deploy + Guides:
  ✓ All deploy artifacts, 5 integration guides, master quickstart


THIS IS A COMPLETE PLATFORM. SHIP IT.
