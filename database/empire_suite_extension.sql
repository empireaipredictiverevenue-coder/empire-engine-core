-- =============================================================================
-- EMPIRE AI · MULTI-PRODUCT SUITE EXTENSION
-- =============================================================================
-- Extends the database to track user subscriptions, lock features based on tier,
-- and meter usage for billing across all three products simultaneously.
--
-- Products:
--   1. Inbound Router  (Traffic Control)
--   2. Data Retention  (Asset Vault)
--   3. Buyer Spy AI    (Network Bypass)
--
-- Tiers: ROUTER_SaaS, DATA_ENTERPRISE, SPY_DATA, ALL_ACCESS
-- =============================================================================

-- ── Product Subscriptions ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS product_subscriptions (
    subscription_id       TEXT PRIMARY KEY,
    customer_account_id   TEXT NOT NULL UNIQUE,
    tier_level            TEXT NOT NULL CHECK (tier_level IN (
                              'ROUTER_SaaS', 'DATA_ENTERPRISE', 'SPY_DATA', 'ALL_ACCESS'
                          )),
    subscription_status   TEXT DEFAULT 'ACTIVE' CHECK (
                              subscription_status IN ('ACTIVE', 'PAST_DUE', 'CANCELED', 'TRIALING')
                          ),
    monthly_recurring_revenue REAL DEFAULT 0.00,
    billing_anchor_day    INTEGER DEFAULT 1,  -- day of month billing starts
    current_period_start  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_period_end    TIMESTAMP,
    trial_end             TIMESTAMP,
    stripe_customer_id    TEXT,
    stripe_subscription_id TEXT,
    notes                 TEXT DEFAULT '',
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Product Feature Flags ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS product_feature_flags (
    customer_account_id        TEXT PRIMARY KEY,
    inbound_router_enabled     INTEGER DEFAULT 0,  -- 0 = Locked, 1 = Active
    data_retention_enabled     INTEGER DEFAULT 0,
    buyer_spy_enabled          INTEGER DEFAULT 0,
    -- Per-feature limits & config (caps stored in meta for flexibility)
    inbound_router_max_calls   INTEGER DEFAULT 0,  -- 0 = unlimited
    data_retention_days        INTEGER DEFAULT 90,
    buyer_spy_analyze_per_day  INTEGER DEFAULT 100,
    meta                       TEXT DEFAULT '{}',  -- JSONB: additional per-account config
    created_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_account_id)
        REFERENCES product_subscriptions(customer_account_id)
);

-- ── Usage Metering (for billing) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS product_usage_log (
    log_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account_id   TEXT NOT NULL,
    product_name          TEXT NOT NULL CHECK (product_name IN (
                              'inbound_router', 'data_vault', 'buyer_spy'
                          )),
    usage_event           TEXT NOT NULL,  -- 'inbound_call', 'data_upload', 'spy_analysis', etc.
    quantity              INTEGER DEFAULT 1,
    unit                  TEXT DEFAULT 'count',
    metadata              TEXT DEFAULT '{}',  -- event-specific JSON payload
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usage_log_account
    ON product_usage_log (customer_account_id, product_name, created_at);

-- ── Customer Usage Ledger (for per-pipeline billing) ─────────────────
CREATE TABLE IF NOT EXISTS customer_usage_ledger (
    transaction_id        TEXT PRIMARY KEY,
    customer_account_id   TEXT NOT NULL,
    api_endpoint_accessed TEXT NOT NULL,
    computed_raw_cost     REAL DEFAULT 0.0,
    client_billed_amount  REAL DEFAULT 0.0,
    metadata              TEXT DEFAULT '{}',
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ledger_account
    ON customer_usage_ledger (customer_account_id, created_at);

-- ── Autonomous Agent Lifecycle & Task Ledger ─────────────────────────
-- Tracks autonomous agent lifetimes and task execution paths for
-- billing, orchestration visibility, and cost attribution.
CREATE TABLE IF NOT EXISTS autonomous_agents (
    agent_id            TEXT PRIMARY KEY,
    agent_name          TEXT NOT NULL,
    assigned_niche      TEXT NOT NULL,  -- mass_tort, commercial_roofing, etc.
    current_status      TEXT DEFAULT 'IDLE',  -- IDLE, EXECUTING, CRASHED, SUCCESS
    total_tasks_completed INTEGER DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_task_ledger (
    task_id             TEXT PRIMARY KEY,
    associated_agent_id TEXT NOT NULL,
    task_instruction    TEXT NOT NULL,
    execution_log       TEXT,
    step_count          INTEGER DEFAULT 1,
    billing_cost_units  REAL DEFAULT 0.0000,
    completed_at        TIMESTAMP,
    FOREIGN KEY (associated_agent_id) REFERENCES autonomous_agents(agent_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_status ON autonomous_agents(current_status);
CREATE INDEX IF NOT EXISTS idx_task_agent ON agent_task_ledger(associated_agent_id);

-- ── Niche Social Terrain ──────────────────────────────────────────
-- Maps where each niche's audience hangs out, tracks observations,
-- and persists learned habit traits. Used by NicheTerrain engine.
CREATE TABLE IF NOT EXISTS social_observations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    niche             TEXT NOT NULL,
    platform          TEXT NOT NULL,
    community_name    TEXT NOT NULL DEFAULT '',
    observation_type  TEXT NOT NULL DEFAULT 'mention',
    content           TEXT DEFAULT '',
    engagement_count  INTEGER DEFAULT 0,
    sentiment         TEXT DEFAULT 'neutral',
    source_url        TEXT DEFAULT '',
    observed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_social_obs_niche_platform
    ON social_observations (niche, platform, observed_at DESC);

CREATE TABLE IF NOT EXISTS niche_habit_traits (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    niche             TEXT NOT NULL,
    trait_key         TEXT NOT NULL,
    trait_value       TEXT NOT NULL,
    confidence        REAL DEFAULT 0.5,
    source            TEXT DEFAULT 'seed',
    learned_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(niche, trait_key)
);

CREATE INDEX IF NOT EXISTS idx_habit_traits_niche
    ON niche_habit_traits (niche, trait_key);

-- ── Preseed an enterprise tier account for immediate validation ────────
INSERT OR IGNORE INTO product_subscriptions (
    subscription_id, customer_account_id, tier_level,
    monthly_recurring_revenue, billing_anchor_day,
    current_period_end, notes
) VALUES (
    'sub_test_99', 'client_alpha_operator', 'ALL_ACCESS',
    1495.00, 1,
    datetime('now', '+30 days'),
    'Enterprise test account — all features enabled'
);

INSERT OR IGNORE INTO product_feature_flags (
    customer_account_id, inbound_router_enabled, data_retention_enabled, buyer_spy_enabled,
    inbound_router_max_calls, data_retention_days, buyer_spy_analyze_per_day
) VALUES (
    'client_alpha_operator', 1, 1, 1,
    10000, 365, 500
);
