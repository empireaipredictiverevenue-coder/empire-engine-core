-- ──────────────────────────────────────────────────────────────────────────────
-- Empire AI · Market Eye (migration 034) Phase 1
-- Competitive Intelligence Engine — real DB-backed competitor tracking,
-- website scrape & diff detection, price change monitoring, alert system,
-- weekly competitive briefs.
-- Tiers: MARKET_EYE_STARTER ($199/mo) · MARKET_EYE_GROWTH ($499/mo)
--        MARKET_EYE_ENTERPRISE ($999/mo)
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 1. competitor_tracking — registered competitors per account ──────────────
CREATE TABLE IF NOT EXISTS competitor_tracking (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    account_id          TEXT NOT NULL DEFAULT 'demo',
    name                TEXT NOT NULL,
    website             TEXT NOT NULL,
    niche               TEXT DEFAULT '',
    notes               TEXT DEFAULT '',
    is_active           INTEGER DEFAULT 1,
    scrape_interval_h   INTEGER DEFAULT 24,      -- hours between scrapes
    last_scraped_at     TEXT,
    last_title          TEXT DEFAULT '',
    last_status         INTEGER,
    last_content_hash   TEXT DEFAULT '',          -- sha256 of last scrape body
    last_price_change   TEXT,                      -- detected price changes
    change_count        INTEGER DEFAULT 0,         -- total detected changes
    UNIQUE(account_id, name)
);

CREATE INDEX IF NOT EXISTS idx_competitor_active
    ON competitor_tracking (account_id, is_active, last_scraped_at);

-- ── 2. competitor_snapshots — periodic scrape results ────────────────────────
CREATE TABLE IF NOT EXISTS competitor_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    competitor_id   INTEGER NOT NULL,
    account_id      TEXT NOT NULL DEFAULT 'demo',
    status_code     INTEGER,
    title           TEXT DEFAULT '',
    headers_json    TEXT DEFAULT '{}',         -- key meta/og tags
    body_snippet    TEXT DEFAULT '',           -- first 2000 chars of body
    content_hash    TEXT DEFAULT '',
    word_count      INTEGER DEFAULT 0,
    links_found     INTEGER DEFAULT 0,
    diff_detected   INTEGER DEFAULT 0,         -- 1 if content changed since last
    diff_summary    TEXT DEFAULT '',            -- brief description of changes
    meta            TEXT DEFAULT '{}',          -- extra scrape signals
    FOREIGN KEY (competitor_id) REFERENCES competitor_tracking(id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_competitor
    ON competitor_snapshots (competitor_id, created_at DESC);

-- ── 3. competitor_alerts — generated alerts when significant changes ─────────
CREATE TABLE IF NOT EXISTS competitor_alerts (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    account_id      TEXT NOT NULL DEFAULT 'demo',
    competitor_id   INTEGER,
    alert_type      TEXT NOT NULL CHECK (alert_type IN (
                        'price_change', 'content_change', 'new_page',
                        'site_down', 'repositioning', 'new_offering',
                        'review_change', 'brief_ready', 'custom'
                    )),
    severity        TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical')),
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    old_value       TEXT DEFAULT '',
    new_value       TEXT DEFAULT '',
    acknowledged    INTEGER DEFAULT 0,
    acknowledged_at TEXT,
    meta            TEXT DEFAULT '{}',
    FOREIGN KEY (competitor_id) REFERENCES competitor_tracking(id)
);

CREATE INDEX IF NOT EXISTS idx_alerts_account
    ON competitor_alerts (account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unread
    ON competitor_alerts (account_id, acknowledged, created_at DESC);

-- ── 4. market_briefs — generated weekly competitive intelligence briefs ──────
CREATE TABLE IF NOT EXISTS market_briefs (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    account_id      TEXT NOT NULL DEFAULT 'demo',
    brief_period    TEXT NOT NULL,             -- '2026-W25' ISO week format
    competitor_count INTEGER DEFAULT 0,
    changes_detected INTEGER DEFAULT 0,
    alerts_generated INTEGER DEFAULT 0,
    summary         TEXT DEFAULT '',            -- AI-generated or templated summary
    highlights_json TEXT DEFAULT '[]',          -- key changes / notable events
    meta            TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_briefs_account
    ON market_briefs (account_id, brief_period DESC);

-- ── 5. Update product_usage_log CHECK constraint ─────────────────────────────
-- Already handled in previous migration — just seed a usage entry if table exists
INSERT INTO product_usage_log
    (customer_account_id, product_name, usage_event, quantity, unit, metadata)
SELECT 'demo_market_eye_starter', 'market_eye', 'competitor_added', 1, 'count',
       '{"note": "seed_demo", "competitor": "Angi"}'
WHERE EXISTS (SELECT 1 FROM product_usage_log LIMIT 1);
