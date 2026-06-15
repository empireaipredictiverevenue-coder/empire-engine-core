EMPIRE V49 · PHASE 3 INTEGRATION
==================================
The final three modules. After this, the revenue machine is closed-loop.


───────────────────────────────────────────────────────────────────────────────
WHAT'S NEW IN PHASE 3
───────────────────────────────────────────────────────────────────────────────

  empire_matching.py    Contractor scoring + dispatch fan-out
                        → 5-factor weighted scoring (metro × specialty × trust × freshness × capacity)
                        → First-to-accept wins, race-safe
                        → Trust score auto-updates on outcomes

  empire_playbook.py    Operator daily morning view
                        → /view/playbook
                        → Hot leads, 5-min tasks, time decay, anomalies

  empire_payouts.py     Solana USDC settlement → split → contractor wire
                        → 70/20/10 default rule, configurable
                        → Auto-attribution + manual override
                        → Human approval gate (configurable threshold)


───────────────────────────────────────────────────────────────────────────────
THE AUTOMATION POSTURE — what runs hands-off vs what needs you
───────────────────────────────────────────────────────────────────────────────

FULLY AUTOMATED (zero human input):
  ✓ pipeline.py scrapes leads on cron
  ✓ Subconscious Mind cross-references NWS every 5 min
  ✓ Empire Brain returns GO/NO_GO
  ✓ SMS sequence dispatches per recipient timezone
  ✓ Email sequence dispatches with CAN-SPAM footer
  ✓ Voice strike calls placed via Vonage
  ✓ Contractor matching scores and ranks
  ✓ Top-N dispatch fan-out emails sent
  ✓ First-to-accept race resolved atomically
  ✓ Trust score updates on outcomes
  ✓ Solana watcher detects USDC settlement
  ✓ Settlement attributed to dispatch
  ✓ Payouts queued with splits computed

HUMAN GATES (intentional · 5-15 min/day total):
  → Approve contractor applications (30 sec each)
  → Confirm SMS replies (auto-paused for review)
  → Confirm claim outcomes (settled/denied/withdrawn)
  → Approve payout batches (30 sec per settlement)
  → Resolve anomalies surfaced by playbook

The human gates are the difference between "a system that runs" and
"a system that runs safely." We don't auto-fire $50K USDC to a wallet
without a human glance. That single rule saves you from disasters.


───────────────────────────────────────────────────────────────────────────────
SUPABASE SCHEMA — run all of this in SQL editor
───────────────────────────────────────────────────────────────────────────────

    -- ────────────────────────────────────────────────────────────────────
    -- DISPATCHES (used by matching engine)
    -- ────────────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS dispatches (
      id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at        timestamptz NOT NULL DEFAULT now(),
      lead_id           uuid,
      contractor_id     uuid NOT NULL,
      match_score       numeric(4,3),
      match_components  jsonb DEFAULT '{}'::jsonb,
      token             text UNIQUE,
      status            text NOT NULL DEFAULT 'sent'
        CHECK (status IN ('sent','accepted','rejected','expired','completed','ghosted')),
      accepted_at       timestamptz,
      completed_at      timestamptz,
      ghosted_at        timestamptz,
      payout_amount     numeric(12,2),
      meta              jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS dispatches_lead_idx       ON dispatches (lead_id);
    CREATE INDEX IF NOT EXISTS dispatches_contractor_idx ON dispatches (contractor_id);
    CREATE INDEX IF NOT EXISTS dispatches_status_idx     ON dispatches (status, created_at DESC);

    -- Metro adjacency for matching
    CREATE TABLE IF NOT EXISTS metro_adjacency (
      metro       text NOT NULL,
      adjacent_to text NOT NULL,
      distance_km numeric(6,1),
      PRIMARY KEY (metro, adjacent_to)
    );
    INSERT INTO metro_adjacency (metro, adjacent_to) VALUES
      ('Dallas / Fort Worth', 'Plano'),
      ('Plano', 'Dallas / Fort Worth'),
      ('Houston', 'Galveston'),
      ('Galveston', 'Houston')
    ON CONFLICT DO NOTHING;

    -- Contractors table columns
    ALTER TABLE contractors
      ADD COLUMN IF NOT EXISTS trust_score        numeric(4,2) DEFAULT 5.0,
      ADD COLUMN IF NOT EXISTS completed_jobs     int  DEFAULT 0,
      ADD COLUMN IF NOT EXISTS active             boolean DEFAULT true,
      ADD COLUMN IF NOT EXISTS specialties        text[] DEFAULT '{}',
      ADD COLUMN IF NOT EXISTS metro              text,
      ADD COLUMN IF NOT EXISTS last_dispatched_at timestamptz,
      ADD COLUMN IF NOT EXISTS max_concurrent     int DEFAULT 3,
      ADD COLUMN IF NOT EXISTS solana_wallet      text;
    CREATE INDEX IF NOT EXISTS contractors_active_metro_idx
      ON contractors (active, metro) WHERE active = true;

    -- Trust score audit log
    CREATE TABLE IF NOT EXISTS contractor_trust_log (
      id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at    timestamptz NOT NULL DEFAULT now(),
      contractor_id uuid NOT NULL,
      outcome       text,
      delta         numeric(4,2),
      before        numeric(4,2),
      after         numeric(4,2),
      notes         text
    );

    -- ────────────────────────────────────────────────────────────────────
    -- PAYOUTS
    -- ────────────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS payout_rules (
      id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at      timestamptz NOT NULL DEFAULT now(),
      name            text NOT NULL,
      active          boolean DEFAULT true,
      contractor_pct  numeric(5,4) NOT NULL,
      ops_pct         numeric(5,4) NOT NULL,
      vault_pct       numeric(5,4) NOT NULL,
      min_settlement  numeric(12,2) DEFAULT 0,
      max_settlement  numeric(12,2),
      CHECK (ABS(contractor_pct + ops_pct + vault_pct - 1.0) < 0.001)
    );

    INSERT INTO payout_rules (name, contractor_pct, ops_pct, vault_pct)
    VALUES ('Default 70/20/10', 0.70, 0.20, 0.10)
    ON CONFLICT DO NOTHING;

    CREATE TABLE IF NOT EXISTS payout_log (
      id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at          timestamptz NOT NULL DEFAULT now(),
      settlement_id       text,
      claim_outcome_id    uuid,
      dispatch_id         uuid,
      contractor_id       uuid,
      recipient_type      text CHECK (recipient_type IN ('contractor','ops','vault')),
      recipient_wallet    text NOT NULL,
      amount_usdc         numeric(12,4) NOT NULL,
      rule_applied        uuid,
      status              text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','executing','sent','failed','cancelled')),
      tx_sig              text,
      approved_by         text,
      approved_at         timestamptz,
      executed_at         timestamptz,
      failure_reason      text,
      meta                jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS payout_log_status_idx
      ON payout_log (status, created_at DESC);
    CREATE INDEX IF NOT EXISTS payout_log_settlement_idx
      ON payout_log (settlement_id);


───────────────────────────────────────────────────────────────────────────────
WIRE-UP IN hub.py
───────────────────────────────────────────────────────────────────────────────

Add the imports:

    from empire_matching import (
        ContractorMatcher,
        register_matching_routes,
    )
    from empire_playbook import (
        register_playbook_routes,
        playbook_view,
    )
    from empire_payouts import (
        PayoutEngine,
        register_payout_routes,
    )

Register everything (after the Phase 2 wire-up):

    # ────────────────────────────────────────────────────────────────────
    # MATCHING
    # ────────────────────────────────────────────────────────────────────
    matcher = ContractorMatcher(get_db=get_db)
    register_matching_routes(
        app,
        matcher=         matcher,
        require_auth=    require_auth,
        sign_token=      _sign_token,
        verify_token=    _verify_token,
        send_email=      _send_email,
        broadcaster=     live_broadcaster,
        public_base_url= PUBLIC_BASE_URL,
    )

    # ────────────────────────────────────────────────────────────────────
    # PLAYBOOK
    # ────────────────────────────────────────────────────────────────────
    register_playbook_routes(
        app,
        require_auth= require_auth,
        get_db=       get_db,
    )

    @app.get("/view/playbook", response_class=HTMLResponse)
    async def view_playbook(token: str = Query("")):
        return HTMLResponse(playbook_view(token=token))

    # ────────────────────────────────────────────────────────────────────
    # PAYOUTS — note the deliberate human-gate posture
    # ────────────────────────────────────────────────────────────────────
    payout_engine = PayoutEngine(
        get_db=                 get_db,
        empire_vault_wallet=    os.environ.get("EMPIRE_VAULT_WALLET", ""),
        empire_ops_wallet=      os.environ.get("USDC_OPS_WALLET", ""),
        empire_signing_key=     os.environ.get("SOLANA_SIGNING_KEY", ""),
        solana_rpc_url=         os.environ.get("SOLANA_RPC_URL",
                                                "https://api.mainnet-beta.solana.com"),
        auto_approve_under_usd= float(os.environ.get("EMPIRE_PAYOUT_AUTO_USD", "0")),
        broadcaster=            live_broadcaster,
        matcher=                matcher,
        ntfy_topic=             NTFY_TOPIC,
        ntfy_token=             NTFY_TOKEN,
    )

    register_payout_routes(
        app,
        engine=        payout_engine,
        require_auth=  require_auth,
    )


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — replace the existing dispatch logic in _subconscious_cycle
───────────────────────────────────────────────────────────────────────────────

The OLD broadcast-to-all dispatch path is replaced with intelligent matching.
In the brain-GO block where dispatch was previously fired:

    # Phase 3 · intelligent matching + first-to-accept fan-out
    matched = await matcher.match_for_lead(
        metro=p.get("city", ""),
        required_specialties=["roofing", "storm_damage"],  # niche config
        top_n=5,
    )

    if matched:
        await matcher.dispatch_to_matched(
            matched=         matched,
            lead=            p,
            urgency=         analysis.get("urgency", 7),
            sign_token=      _sign_token,
            send_email=      _send_email,
            public_base_url= PUBLIC_BASE_URL,
            broadcaster=     live_broadcaster,
        )


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — hook payouts into the Solana revenue watcher
───────────────────────────────────────────────────────────────────────────────

In the existing _solana_cycle() watcher in hub.py, after detecting a USDC
transfer, add the on_settlement_detected call:

    if usdc_in > 0:
        await payout_engine.on_settlement_detected(
            amount_usdc=  usdc_in,
            tx_signature= sig,
            memo=         memo or "",
        )


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — record_outcome hook updates trust scores
───────────────────────────────────────────────────────────────────────────────

In the existing /api/v1/record-outcome endpoint, after the claim_outcomes
insert, add the trust update:

    # Phase 3 · update contractor trust score
    if outcome["contractor_id"] and outcome["outcome"] in TRUST_OUTCOMES:
        await matcher.update_trust_from_outcome(
            contractor_id= outcome["contractor_id"],
            outcome=       outcome["outcome"],
            notes=         outcome.get("notes", ""),
        )


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — add new modules to sidebar nav
───────────────────────────────────────────────────────────────────────────────

In empire_layout.py MODULES list, replace the existing list with:

    MODULES = [
        ("scout",       "01", "Warp Scout",      "ti-radar-2",         False),
        ("cabinet",     "02", "The Cabinet",     "ti-message-2",       False),
        ("sales",       "03", "Sales Forge",     "ti-coin",            False),
        ("yard",        "04", "Yard Sniper",     "ti-crosshair",       False),
        ("settle",      "05", "Settlements",     "ti-receipt-2",       False),
        ("ab",          "06", "A/B Splitter",    "ti-arrows-split",    False),
        ("calibration", "07", "Calibration",     "ti-target-arrow",    False),
        ("attribution", "08", "Attribution",     "ti-chart-arrows",    False),
        ("playbook",    "09", "Daily Playbook",  "ti-list-check",      False),
        ("sovereign",   "10", "Sovereign Vault", "ti-shield-lock",     True),
    ]


───────────────────────────────────────────────────────────────────────────────
ENVIRONMENT VARIABLES — Phase 3 additions
───────────────────────────────────────────────────────────────────────────────

    # Payout splits
    USDC_OPS_WALLET=<your ops wallet>
    SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
    EMPIRE_PAYOUT_AUTO_USD=0      # 0 = require approval for ALL payouts
                                    # e.g. 500 = auto-approve payouts under $500

    # ⚠ The Solana signing key is the keys to the kingdom. Treat like
    # ⚠ production database credentials.
    SOLANA_SIGNING_KEY=<base58-encoded private key>

Set them with:
    dokku config:set empire-ai-uk \
      USDC_OPS_WALLET=... \
      SOLANA_SIGNING_KEY=... \
      EMPIRE_PAYOUT_AUTO_USD=0


───────────────────────────────────────────────────────────────────────────────
SOLANA SIGNING — PRODUCTION CHECKLIST
───────────────────────────────────────────────────────────────────────────────

The empire_payouts.py module ships in DRY-RUN posture for execution.
Pending → Approved works. Approved → Sent is intentionally a NotImplementedError
until you complete this checklist:

  [ ] Install solders: pip install solders==0.21.0
  [ ] Generate (or import) your vault wallet keypair
  [ ] Store the base58 private key in Dokku secrets, NEVER in git
  [ ] Test with $1 USDC to a known test wallet first
  [ ] Implement the _build_and_send_usdc_transfer body in empire_payouts.py
  [ ] Test on devnet first, then move to mainnet
  [ ] Keep a small SOL balance in vault wallet (~0.1 SOL) for gas
  [ ] Set EMPIRE_PAYOUT_AUTO_USD=0 for the first 30 days
  [ ] Manually wire approved payouts using Phantom or Solflare until confident

This module deliberately won't blindly send USDC. You implement the signing
path when you have your operational security buttoned up.


───────────────────────────────────────────────────────────────────────────────
END-TO-END SMOKE TEST · the full revenue loop
───────────────────────────────────────────────────────────────────────────────

1. SEED MATCHING TEST
   - Add 3 contractors with varying metros + specialties + trust scores
   - Preview the match for a Dallas storm lead:
       curl -X POST https://empire-ai.co.uk/api/v1/matching/preview \
            -H "Authorization: Bearer $HUB_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"metro":"Dallas / Fort Worth","specialties":["roofing","storm_damage"]}'
   - Verify the top match has highest score; check components are reasonable

2. DISPATCH TEST (full loop)
   - Insert a test lead in radar_targets with YOUR email as contractor
   - Trigger dispatch:
       curl -X POST https://empire-ai.co.uk/api/v1/matching/dispatch \
            -H "Authorization: Bearer $HUB_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"lead_id":"<uuid>","urgency":8,"specialties":["roofing"]}'
   - Check your email · click the magic link
   - Verify dispatch row marked 'accepted', others 'expired'

3. PLAYBOOK VIEW
   - Visit /view/playbook
   - Confirm: today strip populated, hot leads ranked, tasks queue working,
     time decay buckets showing, anomalies scanning

4. PAYOUT FLOW (dry run)
   - Insert a fake settlement:
       INSERT INTO payout_log (settlement_id, recipient_type, recipient_wallet,
                                amount_usdc, status, meta)
       VALUES ('test_sig_001', 'vault', '<vault_wallet>', 1000, 'pending',
               '{"unattributed": true, "needs_review": true}');
   - Manually attribute to a dispatch:
       curl -X POST https://empire-ai.co.uk/api/v1/payouts/attribute \
            -H "Authorization: Bearer $HUB_TOKEN" \
            -d '{"settlement_id":"test_sig_001","dispatch_id":"<uuid>"}'
   - Verify three payout_log rows now exist (contractor/ops/vault)
   - Approve the batch:
       curl -X POST https://empire-ai.co.uk/api/v1/payouts/approve \
            -d '{"settlement_id":"test_sig_001"}'
   - Verify contractor + ops rows show 'approved' status
   - Until signing path enabled, the rows stay at 'approved' (manual wire from there)


───────────────────────────────────────────────────────────────────────────────
THE COMPLETE V49 BUILD · 13 MODULES
───────────────────────────────────────────────────────────────────────────────

Phase 1 (Foundation):
  ✓ empire_tokens.py        Design system
  ✓ empire_layout.py        Shared chrome
  ✓ empire_live.py          WebSocket broadcaster
  ✓ empire_splash.py        Cinematic gateway
  ✓ empire_command_deck.py  Owner Mode dashboard
  ✓ empire_voice.py         Vonage hybrid voice
  ✓ empire_sms.py           TCPA-safe SMS engine

Phase 2 (Outreach completion):
  ✓ empire_contractors.py   Recruitment funnel
  ✓ empire_attribution.py   Operator scorecard
  ✓ empire_email.py         CAN-SPAM email engine

Phase 3 (Revenue loop closure):
  ✓ empire_matching.py      Contractor scoring + dispatch
  ✓ empire_playbook.py      Daily operator view
  ✓ empire_payouts.py       Solana split engine

Lead generation (standalone):
  ✓ pipeline.py             Master scraper · cron-driven
  ✓ smoke_test.py           Open-Meteo verifier

Deploy + Guides:
  ✓ Procfile, runtime.txt, requirements.txt, app.json, nginx-websocket.conf
  ✓ QUICKSTART.md, INTEGRATION.md, INTEGRATION_PHASE2.md, this file
  ✓ REVENUE_FLOW.md, PIPELINE_CRON.md


THE EMPIRE IS NOW CLOSED-LOOP. SHIP IT.
