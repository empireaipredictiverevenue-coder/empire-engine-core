-- ──────────────────────────────────────────────────────────────────────────────
-- Empire AI · Sales Funnel (migration 033)
-- Tables for sales events, trial registrations, and upsell tracking.
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 1. sales_events — unified log of all sales funnel actions ────────────────
CREATE TABLE IF NOT EXISTS sales_events (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    customer_account_id TEXT,
    email               TEXT,
    product_slug        TEXT NOT NULL,
    event_type          TEXT NOT NULL CHECK (event_type IN (
                            'trial_start', 'trial_converted', 'trial_expired',
                            'purchase', 'upsell', 'downgrade',
                            'renewal', 'renewal_reminder',
                            'churn', 'reactivation',
                            'promo_applied'
                        )),
    tier                TEXT,
    amount_usd          REAL DEFAULT 0.0,
    promo_code          TEXT DEFAULT '',
    trial_end           TEXT,
    max_checks          INTEGER DEFAULT 0,
    name                TEXT DEFAULT '',
    company             TEXT DEFAULT '',
    notes               TEXT DEFAULT '',
    meta                TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sales_events_account
    ON sales_events (customer_account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sales_events_product
    ON sales_events (product_slug, event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sales_events_email
    ON sales_events (email, created_at DESC);

-- ── 2. trial_registrations — active trial tracking ───────────────────────────
CREATE TABLE IF NOT EXISTS trial_registrations (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    email               TEXT NOT NULL,
    product_slug        TEXT NOT NULL,
    tier                TEXT NOT NULL,
    trial_start         TEXT NOT NULL,
    trial_end           TEXT NOT NULL,
    max_checks          INTEGER DEFAULT 0,
    checks_used         INTEGER DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
                            'active', 'converted', 'expired', 'canceled'
                        )),
    converted_at        TEXT,
    UNIQUE(email, product_slug)
);

CREATE INDEX IF NOT EXISTS idx_trial_active
    ON trial_registrations (status, trial_end);

-- ── 3. upsell_paths — recommended upgrade tiers per product ──────────────────
CREATE TABLE IF NOT EXISTS upsell_paths (
    id              BIGSERIAL PRIMARY KEY,
    product_slug    TEXT NOT NULL,
    from_tier       TEXT NOT NULL,
    to_tier         TEXT NOT NULL,
    price_increase  REAL DEFAULT 0.0,
    savings_note    TEXT DEFAULT '',
    is_active       INTEGER DEFAULT 1,
    UNIQUE(product_slug, from_tier)
);

INSERT INTO upsell_paths (product_slug, from_tier, to_tier, price_increase, savings_note) VALUES
    ('lead_score',           'LEADSCORE_STARTER',    'LEADSCORE_GROWTH',     300, '+300/mo for batch scoring + export'),
    ('lead_score',           'LEADSCORE_GROWTH',     'LEADSCORE_ENTERPRISE', 400, '+400/mo for custom models + API'),
    ('compliant',            'COMPLIANT_STARTER',    'COMPLIANT_GROWTH',     300, '+300/mo for quiet hours + audit log'),
    ('compliant',            'COMPLIANT_GROWTH',     'COMPLIANT_ENTERPRISE', 500, '+500/mo for custom rules + reports'),
    ('strike_campaigns',     'STRIKE_STARTER',       'STRIKE_GROWTH',       150, '+150/mo for email + analytics'),
    ('strike_campaigns',     'STRIKE_GROWTH',        'STRIKE_ENTERPRISE',   250, '+250/mo for unlimited + SI opt'),
    ('forecast',             'FORECAST_LITE',        'FORECAST_PRO',        300, '+300/mo for LLM narrative + accuracy'),
    ('forecast',             'FORECAST_PRO',         'FORECAST_ENTERPRISE', 500, '+500/mo for what-if scenarios'),
    ('market_eye',           'MARKET_EYE_STARTER',   'MARKET_EYE_GROWTH',   300, '+300/mo for weekly briefs + alerts'),
    ('market_eye',           'MARKET_EYE_GROWTH',    'MARKET_EYE_ENTERPRISE',500, '+500/mo for unlimited + API'),
    ('content_pulse',        'CONTENT_PULSE_STARTER','CONTENT_PULSE_GROWTH',150, '+150/mo for bulk + email content'),
    ('content_pulse',        'CONTENT_PULSE_GROWTH', 'CONTENT_PULSE_ENTERPRISE',250, '+250/mo for unlimited + API'),
    ('contractor_exchange',  'CONTRACTOR_EXCHANGE_STARTER','CONTRACTOR_EXCHANGE_GROWTH',300, '+300/mo for vetting + matching'),
    ('contractor_exchange',  'CONTRACTOR_EXCHANGE_GROWTH','CONTRACTOR_EXCHANGE_ENTERPRISE',400, '+400/mo for unlimited + API')
ON CONFLICT (product_slug, from_tier) DO NOTHING;

-- ── 4. product_email_sequences — which email sequences are active per product ─
CREATE TABLE IF NOT EXISTS product_email_sequences (
    id              BIGSERIAL PRIMARY KEY,
    product_slug    TEXT NOT NULL,
    sequence_type   TEXT NOT NULL CHECK (sequence_type IN (
                        'onboarding', 'trial', 'upsell', 'renewal', 'reactivation'
                    )),
    step            INTEGER NOT NULL DEFAULT 1,
    subject         TEXT NOT NULL,
    body_html       TEXT NOT NULL DEFAULT '',
    delay_hours     INTEGER DEFAULT 0,
    is_active       INTEGER DEFAULT 1,
    UNIQUE(product_slug, sequence_type, step)
);
