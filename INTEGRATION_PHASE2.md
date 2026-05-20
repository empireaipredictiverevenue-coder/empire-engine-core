EMPIRE V49 · PHASE 2 INTEGRATION
==================================
Three new modules close the remaining gaps in the revenue machine.


───────────────────────────────────────────────────────────────────────────────
WHAT'S NEW
───────────────────────────────────────────────────────────────────────────────

  empire_contractors.py    Public signup, magic-link verify, operator approve
                           → /contractors/signup
                           → /contractors/verify
                           → /api/v1/contractors/{apply,applications,approve,reject}

  empire_attribution.py    Operator scorecard view + 3 funnel APIs
                           → /view/attribution
                           → /api/v1/attribution/{funnel,by-corridor,timeseries}

  empire_email.py          Property-owner email drip · CAN-SPAM compliant
                           → /email/unsubscribe
                           → /api/v1/email/{enroll,bulk-enroll,stats,webhook}


───────────────────────────────────────────────────────────────────────────────
WHAT THE THREE MODULES UNLOCK — the closed loop
───────────────────────────────────────────────────────────────────────────────

BEFORE these modules:
  Storm scraper finds leads → SMS/Voice fires → black box → ???

AFTER:

  STEP 1  pipeline.py scrapes leads (already wired)
            ↓
  STEP 2  Subconscious Mind validates with NWS (already wired)
            ↓
  STEP 3  Empire Brain returns GO (already wired)
            ↓
  STEP 4  THREE outreach channels fire in parallel:
            ├─ SMS sequence  (existing · empire_sms)
            ├─ Voice strike  (existing · empire_voice)
            └─ Email drip    (NEW · empire_email)
            ↓
  STEP 5  Lead engagement tracked in attribution layer (NEW · empire_attribution)
            ↓
  STEP 6  Lead reply → contractor pool matched (existing · contractor_strike_portal)
            ↓
  STEP 7  Contractor accepts via magic link (existing)

            ── meanwhile, the recruitment side ──

            Contractors find empire-ai.co.uk/contractors/signup (NEW)
            → email-verified
            → operator approves
            → live in pool
            → match into STEP 6
            ↓
  STEP 8  Claim settles · USDC paid · calibration improves (already wired)
            ↓
  STEP 9  Operator sees the full funnel at /view/attribution (NEW)


───────────────────────────────────────────────────────────────────────────────
SUPABASE SCHEMA — run these once
───────────────────────────────────────────────────────────────────────────────

    -- ────────────────────────────────────────────────────────────────────
    -- CONTRACTOR APPLICATIONS
    -- ────────────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS contractor_applications (
      id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at        timestamptz NOT NULL DEFAULT now(),
      name              text NOT NULL,
      email             text NOT NULL,
      phone             text NOT NULL,
      company           text,
      metro             text NOT NULL,
      license_no        text,
      license_state     text,
      specialties       text[] DEFAULT '{}',
      years_in_biz      int,
      insurance_carrier text,
      ein               text,
      notes             text,
      status            text NOT NULL DEFAULT 'pending_email'
        CHECK (status IN ('pending_email','pending_review','approved','rejected','withdrawn')),
      approved_at       timestamptz,
      rejected_at       timestamptz,
      rejected_reason   text,
      contractor_id     uuid REFERENCES contractors(id),
      meta              jsonb DEFAULT '{}'::jsonb
    );
    CREATE UNIQUE INDEX IF NOT EXISTS contractor_applications_active_email
      ON contractor_applications (email)
      WHERE status NOT IN ('rejected', 'withdrawn');
    CREATE INDEX IF NOT EXISTS contractor_applications_status_idx
      ON contractor_applications (status, created_at DESC);

    -- ────────────────────────────────────────────────────────────────────
    -- EMAIL SEQUENCES (mirrors sms_sequences pattern)
    -- ────────────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS email_sequences (
      id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at      timestamptz NOT NULL DEFAULT now(),
      email           text NOT NULL UNIQUE,
      target_addr     text,
      sequence_type   text NOT NULL DEFAULT 'storm_strike',
      current_step    int  NOT NULL DEFAULT 0,
      status          text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','paused','completed','unsubscribed','bounced','replied')),
      last_sent_at    timestamptz,
      next_send_at    timestamptz,
      bounces         int DEFAULT 0,
      meta            jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS email_sequences_dispatch_idx
      ON email_sequences (status, next_send_at);

    CREATE TABLE IF NOT EXISTS email_unsubscribes (
      email      text PRIMARY KEY,
      created_at timestamptz NOT NULL DEFAULT now(),
      reason     text DEFAULT 'one-click unsubscribe',
      meta       jsonb DEFAULT '{}'::jsonb
    );

    CREATE TABLE IF NOT EXISTS email_log (
      id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at  timestamptz NOT NULL DEFAULT now(),
      email       text NOT NULL,
      direction   text CHECK (direction IN ('outbound','bounce','reply')),
      subject     text,
      step        int,
      message_id  text,
      delivered   boolean DEFAULT false,
      meta        jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS email_log_email_idx
      ON email_log (email, created_at DESC);

    -- ────────────────────────────────────────────────────────────────────
    -- radar_targets needs an email column for the email engine
    -- ────────────────────────────────────────────────────────────────────
    ALTER TABLE radar_targets
      ADD COLUMN IF NOT EXISTS email text;


───────────────────────────────────────────────────────────────────────────────
WIRE-UP IN hub.py — add these imports
───────────────────────────────────────────────────────────────────────────────

    from empire_contractors import register_contractor_routes
    from empire_attribution  import register_attribution_routes, attribution_view
    from empire_email        import EmailSequenceEngine, register_email_routes


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — register routes (after existing V49 wire-up)
───────────────────────────────────────────────────────────────────────────────

    # ────────────────────────────────────────────────────────────────────
    # CONTRACTOR ONBOARDING
    # ────────────────────────────────────────────────────────────────────
    register_contractor_routes(
        app,
        require_auth=    require_auth,
        get_db=          get_db,
        sign_token=      _sign_token,     # the HMAC helpers already in hub.py
        verify_token=    _verify_token,
        send_email=      _send_email,
        public_base_url= PUBLIC_BASE_URL,
        ntfy_topic=      NTFY_TOPIC,
        ntfy_token=      NTFY_TOKEN,
        link_ttl_seconds=72 * 3600,
    )

    # ────────────────────────────────────────────────────────────────────
    # ATTRIBUTION DASHBOARD
    # ────────────────────────────────────────────────────────────────────
    register_attribution_routes(
        app,
        require_auth= require_auth,
        get_db=       get_db,
    )

    @app.get("/view/attribution", response_class=HTMLResponse)
    async def view_attribution(token: str = Query("")):
        return HTMLResponse(attribution_view(token=token))

    # ────────────────────────────────────────────────────────────────────
    # EMAIL SEQUENCE ENGINE
    # ────────────────────────────────────────────────────────────────────
    email_engine = EmailSequenceEngine(
        get_db=           get_db,
        send_email=       _send_email,
        sign_token=       _sign_token,
        verify_token=     _verify_token,
        public_base_url=  PUBLIC_BASE_URL,
        physical_address= os.environ.get("EMPIRE_POSTAL_ADDRESS", "Empire AI Ltd · United Kingdom"),
        sender_name=      os.environ.get("EMPIRE_SENDER_NAME", "Empire AI Operations"),
        max_per_minute=   int(os.environ.get("EMPIRE_EMAIL_RATE", "12")),
    )

    register_email_routes(
        app,
        email_engine,
        require_auth= require_auth,
        broadcaster=  live_broadcaster,
    )


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — add to existing @app.on_event("startup")
───────────────────────────────────────────────────────────────────────────────

    # Phase 2: email dispatcher loop
    asyncio.create_task(email_engine.dispatcher_loop())


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — auto-enroll brain GO leads into the email channel
───────────────────────────────────────────────────────────────────────────────

Inside _subconscious_cycle(), in the same block where the SMS engine and
voice router are triggered on a brain GO, add the email enrollment:

                            # Phase 2 · email channel (third outreach leg)
                            target_email = p.get("email", "")
                            if target_email:
                                await email_engine.enroll(
                                    email=         target_email,
                                    target_addr=   p.get("address", ""),
                                    sequence_type="storm_strike",
                                    meta={
                                        "urgency":     analysis.get("urgency"),
                                        "asset_value": asset_val_num,
                                        "event":       alert.get("event"),
                                    },
                                )


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — add Attribution to the sidebar nav
───────────────────────────────────────────────────────────────────────────────

In empire_layout.py, add this row to the MODULES list (insert before Sovereign):

    ("attribution", "09", "Attribution", "ti-chart-arrows", False),
    ("sovereign",   "10", "Sovereign Vault", "ti-shield-lock", True),


───────────────────────────────────────────────────────────────────────────────
ENVIRONMENT VARIABLES — add to Dokku
───────────────────────────────────────────────────────────────────────────────

    # CAN-SPAM: physical address shown in every email footer (required by US
    # federal law). Use your actual registered business address.
    EMPIRE_POSTAL_ADDRESS="Empire AI Ltd, [your registered address]"

    # Optional · sender name shown in From line (defaults to "Empire AI Operations")
    EMPIRE_SENDER_NAME="Empire AI Operations"

    # Optional · rate limit (default 12 emails/minute)
    EMPIRE_EMAIL_RATE=12

Set them with:
    dokku config:set empire-ai-uk \
      EMPIRE_POSTAL_ADDRESS="Empire AI Ltd, ..." \
      EMPIRE_SENDER_NAME="Empire AI Operations"


───────────────────────────────────────────────────────────────────────────────
RESEND WEBHOOK — wire bounce + complaint handling
───────────────────────────────────────────────────────────────────────────────

1. Log in to resend.com → Webhooks → Add Endpoint
2. URL: https://empire-ai.co.uk/api/v1/email/webhook
3. Events to subscribe to:
     - email.bounced
     - email.complained
     - email.unsubscribed
4. Save. Test with the "Send Test Event" button.

Bounces auto-remove the email from active sequences after 2 soft bounces
or 1 hard bounce. Complaints auto-add to the unsubscribe registry.


───────────────────────────────────────────────────────────────────────────────
CAN-SPAM COMPLIANCE CHECKLIST — non-negotiable
───────────────────────────────────────────────────────────────────────────────

The email engine is designed CAN-SPAM-safe out of the box. Verify:

  [ ] Every email has a working unsubscribe link
  [ ] Unsubscribe works in one click (no login required)
  [ ] Unsubscribe is honored within 10 business days (we honor immediately)
  [ ] Every email shows a physical postal address
  [ ] From line shows a real sender name, not a faked domain
  [ ] Subject lines accurately describe the email's content
  [ ] Email identifies as paid commercial outreach
  [ ] Honor unsubscribes for at least 5 years
  [ ] Don't sell or transfer the unsubscribe list

Fines under CAN-SPAM: up to $51,744 PER email in violation.


───────────────────────────────────────────────────────────────────────────────
END-TO-END SMOKE TEST
───────────────────────────────────────────────────────────────────────────────

1. CONTRACTOR ONBOARDING TEST
   - Visit https://empire-ai.co.uk/contractors/signup
   - Fill in YOUR details
   - Submit · check your email for verify link
   - Click verify link · check ntfy receives "ready for review"
   - Operator approves via curl:
       curl -X POST https://empire-ai.co.uk/api/v1/contractors/approve \
            -H "Authorization: Bearer $HUB_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"application_id":"<uuid from supabase>"}'
   - You receive welcome email · contractor row exists

2. EMAIL ENGINE TEST
   - Insert a fake target with YOUR email:
       INSERT INTO radar_targets
         (address, email, phone, location, status, damage_severity, urgency_score)
       VALUES
         ('Test Whale', 'YOUR_EMAIL@x.com', '+12145559999',
          'POINT(-96.7970 32.7767)', 'active', 'severe', 9);
   - Enroll manually:
       curl -X POST https://empire-ai.co.uk/api/v1/email/enroll \
            -H "Authorization: Bearer $HUB_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"email":"YOUR_EMAIL@x.com","target_addr":"Test Whale"}'
   - Within 60 seconds: first email lands in your inbox
   - Click the unsubscribe link at the bottom
   - You're redirected to a confirmation page
   - Check Supabase: SELECT * FROM email_unsubscribes; — row exists
   - Sequence shows status='unsubscribed'

3. ATTRIBUTION DASHBOARD TEST
   - Navigate to https://empire-ai.co.uk/view/attribution
   - Should see funnel showing the test enrollments
   - Adjust time window 1d/7d/30d/90d — funnel updates
   - Corridor breakdown shows your test city
   - Daily volume chart renders


───────────────────────────────────────────────────────────────────────────────
WHAT'S NOW LIVE
───────────────────────────────────────────────────────────────────────────────

  ✓ Three outreach channels (SMS, Voice, Email) all firing on brain GO
  ✓ Contractor recruitment funnel · self-service signup → operator approve
  ✓ End-to-end attribution from scrape to settled
  ✓ TCPA + CAN-SPAM compliance built in (the operator still owns final liability)
  ✓ One-click unsubscribe for email · STOP keyword for SMS
  ✓ Bounce + complaint handling via Resend webhook
  ✓ Operator daily scorecard showing what's working

The revenue machine is now fully closed-loop.
