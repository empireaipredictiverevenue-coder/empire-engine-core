-- ============================================================================
-- EMPIRE V49 · DDL MIGRATION 010: STRIKE PACKS SUBSCRIPTION ENGINE
-- ============================================================================
-- Productizes the 32 lanes into sellable Strike Packs with pricing tiers.
--
-- Tables created:
--   1. strike_packs — the product catalog (one row per SKU)
--   2. strike_pack_lanes — which lanes a pack covers (M:N join)
--   3. buyer_subscriptions — who's subscribed to what, billing state
--   4. buyer_pack_stats — daily rollup of leads delivered per subscription
--
-- Usage in Python:
--   STRIKE_PACKS = {row["slug"]: row for row in sb.table("strike_packs").select("*").execute().data}
--   SUBSCRIPTIONS = sb.table("buyer_subscriptions").select("*").eq("buyer_id", X).eq("active", true).execute().data
--
-- Idempotent: All CREATEs use IF NOT EXISTS. Safe to re-run.
-- ============================================================================


-- ── 1. STRIKE PACKS CATALOG ──────────────────────────────────────────
-- One row per sellable product. The slug is the stable identifier used
-- in code and URLs. Price is in USD cents (stripe-compatible) for
-- future Stripe integration; monthly_price_cents is the subscription
-- rate, price_per_lead_cents is the overage/per-lead rate.
CREATE TABLE IF NOT EXISTS public.strike_packs (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    -- Identity
    slug              text NOT NULL UNIQUE,              -- e.g. "roofing_strike"
    name              text NOT NULL,                     -- e.g. "Roofing Strike Pack"
    description       text NOT NULL DEFAULT '',

    -- Tier classification
    tier              text NOT NULL DEFAULT 'standard'
        CHECK (tier IN ('standard', 'combo', 'whale', 'enterprise')),

    -- Pricing (USD cents, stripe-compatible)
    monthly_price_cents    integer NOT NULL DEFAULT 0,   -- $500 = 50000
    price_per_lead_cents   integer NOT NULL DEFAULT 0,   -- $5 = 500
    max_leads_per_day      integer NOT NULL DEFAULT 10,
    max_leads_per_month    integer NOT NULL DEFAULT 300,

    -- Delivery channels (text array: email, webhook, api, dashboard)
    delivery_channels      text[] NOT NULL DEFAULT '{email}',

    -- Target buyer segment (for UI filtering)
    target_buyer           text,                          -- e.g. "contractor", "law_firm", "insurance_carrier", "reit"

    -- Feature flags (used by the delivery engine)
    features               jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- Lane coverage summary (denormalized for fast display)
    lane_count             integer NOT NULL DEFAULT 0,
    niches                 text[] NOT NULL DEFAULT '{}',

    -- Display
    sort_order             integer NOT NULL DEFAULT 0,
    is_public              boolean NOT NULL DEFAULT true, -- false = hidden from public catalog
    is_active              boolean NOT NULL DEFAULT true
);

COMMENT ON TABLE  public.strike_packs IS 'Product catalog: one row per sellable Strike Pack SKU';
COMMENT ON COLUMN public.strike_packs.slug IS 'URL-safe stable identifier, referenced in code (e.g. roofing_strike)';
COMMENT ON COLUMN public.strike_packs.tier IS 'standard=single niche, combo=bundled, whale=high-ticket enterprise, enterprise=custom';
COMMENT ON COLUMN public.strike_packs.features IS 'JSON array of feature strings shown on the product page';


-- ── 2. STRIKE PACK LANES (M:N join) ─────────────────────────────────
-- Maps each Strike Pack to the lane IDs it covers. Lane IDs reference
-- mesh_orchestrator.LANES (0-31).
CREATE TABLE IF NOT EXISTS public.strike_pack_lanes (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    pack_id         uuid NOT NULL REFERENCES public.strike_packs(id) ON DELETE CASCADE,
    lane_id         integer NOT NULL,                    -- 0-31, matches mesh_orchestrator.LANES
    niche           text NOT NULL,                       -- denormalized from mesh_orchestrator for query speed
    sub_niche       text,                                -- NULL for single-niche lanes
    strategy        text NOT NULL,                       -- denormalized strategy name

    CONSTRAINT strike_pack_lanes_unique UNIQUE (pack_id, lane_id)
);

CREATE INDEX IF NOT EXISTS strike_pack_lanes_pack_idx ON public.strike_pack_lanes (pack_id);
CREATE INDEX IF NOT EXISTS strike_pack_lanes_lane_idx ON public.strike_pack_lanes (lane_id);

COMMENT ON TABLE  public.strike_pack_lanes IS 'M:N join between Strike Packs and their lane IDs';
COMMENT ON COLUMN public.strike_pack_lanes.lane_id IS 'Lane ID from mesh_orchestrator.LANES (0-31)';


-- ── 3. BUYER SUBSCRIPTIONS ───────────────────────────────────────────
-- Links a buyer to a Strike Pack with billing state. Supports Stripe
-- integration: stripe_subscription_id and stripe_customer_id let us
-- sync subscription lifecycle via webhooks.
CREATE TABLE IF NOT EXISTS public.buyer_subscriptions (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    -- Who
    buyer_id                uuid NOT NULL REFERENCES public.buyers(id) ON DELETE CASCADE,
    pack_id                 uuid NOT NULL REFERENCES public.strike_packs(id) ON DELETE RESTRICT,

    -- What they get (snapshot at subscription time, so price changes
    -- don't affect active subscriptions until renewal)
    monthly_price_cents     integer NOT NULL,
    price_per_lead_cents    integer NOT NULL,
    max_leads_per_day       integer NOT NULL,
    max_leads_per_month     integer NOT NULL,

    -- Status
    status                  text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'canceled', 'expired', 'trialing')),
    active                  boolean NOT NULL DEFAULT true,

    -- Current billing period (UTC)
    period_start            timestamptz NOT NULL DEFAULT now(),
    period_end              timestamptz,                 -- NULL = perpetual / no end

    -- Usage this period (reset on period_start change)
    leads_delivered_period  integer NOT NULL DEFAULT 0,

    -- Stripe integration (null until Stripe is connected)
    stripe_customer_id      text,
    stripe_subscription_id  text UNIQUE,

    -- Metadata
    notes                   text,
    meta                    jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS buyer_subs_buyer_idx    ON public.buyer_subscriptions (buyer_id);
CREATE INDEX IF NOT EXISTS buyer_subs_pack_idx     ON public.buyer_subscriptions (pack_id);
CREATE INDEX IF NOT EXISTS buyer_subs_active_idx   ON public.buyer_subscriptions (buyer_id) WHERE active = true;
CREATE INDEX IF NOT EXISTS buyer_subs_stripe_idx   ON public.buyer_subscriptions (stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;

COMMENT ON TABLE  public.buyer_subscriptions IS 'Active and historical subscriptions linking buyers to Strike Packs';
COMMENT ON COLUMN public.buyer_subscriptions.leads_delivered_period IS 'Counter of leads delivered in the current billing period, reset on period_start change';
COMMENT ON COLUMN public.buyer_subscriptions.stripe_subscription_id IS 'Stripe subscription ID when billing is handled by Stripe';


-- ── 4. BUYER PACK STATS (daily rollup) ───────────────────────────────
-- Denormalized daily per-subscription stats so the dashboard and
-- delivery engine don't need to COUNT(*) across large tables every
-- time. Updated by the delivery engine after each lead is routed.
CREATE TABLE IF NOT EXISTS public.buyer_pack_stats (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),

    -- Who + what
    subscription_id     uuid NOT NULL REFERENCES public.buyer_subscriptions(id) ON DELETE CASCADE,
    buyer_id            uuid NOT NULL REFERENCES public.buyers(id) ON DELETE CASCADE,
    pack_id             uuid NOT NULL REFERENCES public.strike_packs(id) ON DELETE CASCADE,

    -- Date bucket (UTC date)
    stat_date           date NOT NULL,

    -- Counters
    leads_delivered     integer NOT NULL DEFAULT 0,
    leads_qualified     integer NOT NULL DEFAULT 0,
    calls_placed        integer NOT NULL DEFAULT 0,
    calls_connected     integer NOT NULL DEFAULT 0,
    revenue_generated   numeric(12,2) NOT NULL DEFAULT 0.00,
    fee_earned          numeric(12,2) NOT NULL DEFAULT 0.00,

    -- Constraints
    CONSTRAINT buyer_pack_stats_unique UNIQUE (subscription_id, stat_date)
);

CREATE INDEX IF NOT EXISTS buyer_pack_stats_sub_idx  ON public.buyer_pack_stats (subscription_id, stat_date DESC);
CREATE INDEX IF NOT EXISTS buyer_pack_stats_buyer_idx ON public.buyer_pack_stats (buyer_id, stat_date DESC);
CREATE INDEX IF NOT EXISTS buyer_pack_stats_pack_idx  ON public.buyer_pack_stats (pack_id, stat_date DESC);

COMMENT ON TABLE  public.buyer_pack_stats IS 'Daily rollup per subscription: leads, calls, revenue. Updated by the delivery engine after each lead route.';
COMMENT ON COLUMN public.buyer_pack_stats.stat_date IS 'UTC date of the stats bucket';


-- ── 5. SEED THE STRIKE PACK CATALOG ──────────────────────────────────
-- Inserts the initial product catalog. Idempotent via ON CONFLICT.
INSERT INTO public.strike_packs (slug, name, description, tier, monthly_price_cents, price_per_lead_cents, max_leads_per_day, max_leads_per_month, delivery_channels, target_buyer, features, lane_count, niches, sort_order)
VALUES
    -- ── STANDARD TIER (single-niche packs) ──
    ('roofing_strike',
     'Roofing Strike Pack',
     'Storm-verified commercial roofing leads in TX/OK. Each lead includes property address, damage severity, asset value, urgency score, and phone.',
     'standard', 50000, 500, 10, 300, '{email,webhook,api}',
     'contractor',
     '["Storm-verified commercial leads", "Damage severity + asset value included", "Delivered within 4 hours of storm event", "Phone-verified contacts"]',
     8, ARRAY['Roofing Restoration'], 10),

    ('hvac_strike',
     'HVAC Strike Pack',
     'SEO-scraped local HVAC leads pre-qualified by web audit. Includes contact info, estimated job value, and intent score.',
     'standard', 35000, 300, 15, 450, '{email,webhook}',
     'contractor',
     '["Web-audited lead qualification", "Intent score + job value estimate", "Phone + email contacts"]',
     8, ARRAY['Local SEO & HVAC'], 20),

    ('legal_strike',
     'Legal Strike Pack',
     'FDA recall-triggered mass tort leads classified into 5 sub-niches. Each lead includes recall product, FDA alert date, and claimant proximity.',
     'standard', 50000, 1500, 20, 600, '{email}',
     'law_firm',
     '["FDA recall-triggered leads", "5 sub-niche classification", "Claimant geographic proximity scoring", "Urgency-ranked"]',
     5, ARRAY['Legal'], 30),

    ('cpa_strike',
     'Consumer CPA Strike Pack',
     'Consumer inbound leads filtered by credit signal, intent score, and metro. Volume tier suitable for high-throughput campaigns.',
     'standard', 30000, 200, 25, 750, '{email,webhook}',
     'buyer',
     '["Credit-signal filtered", "Intent-scored leads", "Metro-targeted delivery"]',
     8, ARRAY['Consumer CPA'], 40),

    -- ── COMBO TIER (bundled packs) ──
    ('storm_pro',
     'Storm Pro Pack',
     'Combined Roofing + HVAC leads. Everything in both packs at a discounted rate.',
     'combo', 70000, 400, 20, 600, '{email,webhook,api}',
     'contractor',
     '["Roofing + HVAC combined feed", "Storm-verified + web-audited", "Priority delivery: 2-hour SLA"]',
     16, ARRAY['Roofing Restoration', 'Local SEO & HVAC'], 100),

    ('legal_shield',
     'Legal Shield Pack',
     'All 5 legal sub-niches in one subscription. Full mass tort coverage across Pharma, Medical Device, Consumer Product, Class Action, and Mass Tort.',
     'combo', 70000, 1200, 40, 1200, '{email}',
     'law_firm',
     '["All 5 legal sub-niches", "Dedicated lane per sub-niche", "Weekly trend report", "Priority classification"]',
     5, ARRAY['Legal'], 110),

    ('full_spectrum',
     'Full Spectrum Pack',
     'All 29 active lanes across all niches. Maximum lead volume for enterprise buyers.',
     'combo', 120000, 300, 50, 1500, '{email,webhook,api,dashboard}',
     'enterprise',
     '["All 29 active lanes", "Cross-niche lead feed", "Real-time dashboard access", "Custom delivery webhook"]',
     29, ARRAY['Roofing Restoration', 'Local SEO & HVAC', 'Legal', 'Consumer CPA'], 120),

    -- ── WHALE TIER (high-ticket enterprise products) ──
    ('insurance_intel',
     'Commercial Insurance Intelligence',
     'Real-time storm damage predictions for insurance portfolios. Every weather event triggers a scored list of affected properties with predicted damage severity.',
     'whale', 1000000, 0, 0, 0, '{api,dashboard}',
     'insurance_carrier',
     '["Real-time storm events on portfolio", "Property-level damage scoring", "4-hour alert SLA", "Historical claim correlation", "Executive weekly briefing"]',
     1, ARRAY['Commercial Insurance'], 200),

    ('executive_pulse',
     'Executive Market Pulse',
     'Live portfolio monitoring dashboard with AI-generated executive briefings. Track weather risk, contractor dispatch, and claim pipeline for your entire portfolio.',
     'whale', 2500000, 0, 0, 0, '{dashboard}',
     'reit',
     '["Live portfolio weather monitoring", "AI-generated executive briefings", "Contractor dispatch status", "Claim pipeline tracker", "White-label subdomain"]',
     1, ARRAY['Executive Pulse'], 210),

    ('compliance_api',
     'Compliance Infrastructure API',
     'TCPA/DNC compliance checking as a service. Submit a phone + campaign, get back PASS/FAIL with reason and safe window. Enterprise SLA.',
     'whale', 2000000, 0, 500000, 500000, '{api}',
     'enterprise',
     '["TCPA/DNC compliance checking", "Quiet hours enforcement", "Opt-out registry", "Audit trail export", "99.9% API SLA"]',
     0, ARRAY['Compliance'], 220)

ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    monthly_price_cents = EXCLUDED.monthly_price_cents,
    delivery_channels = EXCLUDED.delivery_channels,
    features = EXCLUDED.features
RETURNING id, slug, name;

-- NOTE: After seeding strike_packs, run the lane mapping script
-- (see VERIFICATION section below) to populate strike_pack_lanes.


-- ── 6. SEED STRIKE PACK LANES ────────────────────────────────────────
-- Maps each pack to its lane IDs. Idempotent via ON CONFLICT.
-- Lane definitions from mesh_orchestrator.LANES.
INSERT INTO public.strike_pack_lanes (pack_id, lane_id, niche, sub_niche, strategy)
SELECT
    p.id, l.lane_id, l.niche, l.sub_niche, l.strategy
FROM (
    VALUES
        -- Roofing Strike → lanes 0-7
        ('roofing_strike', 0,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('roofing_strike', 1,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('roofing_strike', 2,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('roofing_strike', 3,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('roofing_strike', 4,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('roofing_strike', 5,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('roofing_strike', 6,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('roofing_strike', 7,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),

        -- HVAC Strike → lanes 8-15
        ('hvac_strike',      8,  'Local SEO & HVAC',     NULL, 'UGLY_BANNER'),
        ('hvac_strike',      9,  'Local SEO & HVAC',     NULL, 'UGLY_BANNER'),
        ('hvac_strike',      10, 'Local SEO & HVAC',     NULL, 'UGLY_BANNER'),
        ('hvac_strike',      11, 'Local SEO & HVAC',     NULL, 'UGLY_BANNER'),
        ('hvac_strike',      12, 'Local SEO & HVAC',     NULL, 'UGLY_BANNER'),
        ('hvac_strike',      13, 'Local SEO & HVAC',     NULL, 'UGLY_BANNER'),
        ('hvac_strike',      14, 'Local SEO & HVAC',     NULL, 'UGLY_BANNER'),
        ('hvac_strike',      15, 'Local SEO & HVAC',     NULL, 'UGLY_BANNER'),

        -- Legal Strike → lanes 16-20
        ('legal_strike',     16, 'Legal', 'Pharma Liability',  'RECALL_SNIPER'),
        ('legal_strike',     17, 'Legal', 'Medical Device',    'RECALL_SNIPER'),
        ('legal_strike',     18, 'Legal', 'Consumer Product',  'RECALL_SNIPER'),
        ('legal_strike',     19, 'Legal', 'Class Action',      'RECALL_SNIPER'),
        ('legal_strike',     20, 'Legal', 'Mass Tort',         'RECALL_SNIPER'),

        -- CPA Strike → lanes 21-28
        ('cpa_strike',       21, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('cpa_strike',       22, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('cpa_strike',       23, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('cpa_strike',       24, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('cpa_strike',       25, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('cpa_strike',       26, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('cpa_strike',       27, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('cpa_strike',       28, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),

        -- Storm Pro = Roofing + HVAC (16 lanes)
        ('storm_pro',        0,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('storm_pro',        1,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('storm_pro',        2,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('storm_pro',        3,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('storm_pro',        4,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('storm_pro',        5,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('storm_pro',        6,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('storm_pro',        7,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('storm_pro',        8,  'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('storm_pro',        9,  'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('storm_pro',        10, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('storm_pro',        11, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('storm_pro',        12, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('storm_pro',        13, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('storm_pro',        14, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('storm_pro',        15, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),

        -- Legal Shield = all 5 legal lanes
        ('legal_shield',     16, 'Legal', 'Pharma Liability',  'RECALL_SNIPER'),
        ('legal_shield',     17, 'Legal', 'Medical Device',    'RECALL_SNIPER'),
        ('legal_shield',     18, 'Legal', 'Consumer Product',  'RECALL_SNIPER'),
        ('legal_shield',     19, 'Legal', 'Class Action',      'RECALL_SNIPER'),
        ('legal_shield',     20, 'Legal', 'Mass Tort',         'RECALL_SNIPER'),

        -- Full Spectrum = all 29 active lanes (Roofing 0-7, HVAC 8-15, Legal 16-20, CPA 21-28)
        ('full_spectrum',    0,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('full_spectrum',    1,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('full_spectrum',    2,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('full_spectrum',    3,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('full_spectrum',    4,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('full_spectrum',    5,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('full_spectrum',    6,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('full_spectrum',    7,  'Roofing Restoration', NULL, 'AGGRESSIVE_STRIKE'),
        ('full_spectrum',    8,  'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('full_spectrum',    9,  'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('full_spectrum',    10, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('full_spectrum',    11, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('full_spectrum',    12, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('full_spectrum',    13, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('full_spectrum',    14, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('full_spectrum',    15, 'Local SEO & HVAC',   NULL, 'UGLY_BANNER'),
        ('full_spectrum',    16, 'Legal', 'Pharma Liability',  'RECALL_SNIPER'),
        ('full_spectrum',    17, 'Legal', 'Medical Device',    'RECALL_SNIPER'),
        ('full_spectrum',    18, 'Legal', 'Consumer Product',  'RECALL_SNIPER'),
        ('full_spectrum',    19, 'Legal', 'Class Action',      'RECALL_SNIPER'),
        ('full_spectrum',    20, 'Legal', 'Mass Tort',         'RECALL_SNIPER'),
        ('full_spectrum',    21, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('full_spectrum',    22, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('full_spectrum',    23, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('full_spectrum',    24, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('full_spectrum',    25, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('full_spectrum',    26, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('full_spectrum',    27, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),
        ('full_spectrum',    28, 'Consumer CPA',        NULL, 'FINANCIAL_STRIKE'),

        -- Insurance Intel → lane 29 (after reallocation)
        ('insurance_intel',  29, 'Commercial Insurance', 'Storm Risk Feed', 'STANDARD'),

        -- Executive Pulse → lane 31 (after reallocation)
        ('executive_pulse',  31, 'Executive Pulse',      'REIT Portfolio',  'STANDARD')
) AS l(slug, lane_id, niche, sub_niche, strategy)
JOIN public.strike_packs p ON p.slug = l.slug
ON CONFLICT (pack_id, lane_id) DO NOTHING;

-- NOTE: Compliance API (slug=compliance_api) has no lane mapping —
-- it's a pure API product, not a lead-gen lane. lane_count stays 0.


-- ============================================================================
-- VERIFICATION (run separately after migration)
-- ============================================================================
-- -- All packs with their lane count (should match lane_count column):
-- SELECT p.slug, p.name, p.tier, p.monthly_price_cents / 100 AS price_usd,
--        COUNT(pl.id) AS actual_lanes
-- FROM public.strike_packs p
-- LEFT JOIN public.strike_pack_lanes pl ON pl.pack_id = p.id
-- GROUP BY p.id, p.slug, p.name, p.tier, p.monthly_price_cents
-- ORDER BY p.sort_order;
--
-- -- Active subscriptions with usage:
-- SELECT bs.id, b.buyer_name, sp.name AS pack, bs.status,
--        bs.leads_delivered_period, bs.max_leads_per_day
-- FROM public.buyer_subscriptions bs
-- JOIN public.buyers b ON b.id = bs.buyer_id
-- JOIN public.strike_packs sp ON sp.id = bs.pack_id
-- WHERE bs.active = true
-- ORDER BY bs.created_at DESC;
--
-- -- Daily stat rollup for a specific subscription:
-- SELECT stat_date, leads_delivered, calls_placed, revenue_generated
-- FROM public.buyer_pack_stats
-- WHERE subscription_id = '<subscription-uuid>'
-- ORDER BY stat_date DESC
-- LIMIT 30;
-- ============================================================================
