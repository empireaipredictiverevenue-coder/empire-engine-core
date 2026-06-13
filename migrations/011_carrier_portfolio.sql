-- ============================================================================
-- EMPIRE V49 · DDL MIGRATION 011: CARRIER PORTFOLIO MANAGEMENT
-- ============================================================================
-- Enables the Commercial Insurance Intelligence product ($10k/mo whale tier).
-- Carriers upload their book of insured commercial properties; when a storm
-- hits their coverage area, they get a scored damage report within 4 hours.
--
-- Tables created:
--   1. carrier_portfolios      — one per carrier subscription
--   2. carrier_properties      — each insured property in a carrier's book
--   3. storm_reports           — one report per storm event per carrier
--   4. storm_report_properties — per-property damage assessment within a report
--
-- The insurance_intel pack is already seeded in migrations/010_strike_packs.sql.
-- Carriers subscribe via the existing buyer_subscriptions table and
-- SubscriptionEngine from empire_strike_packs.py.
--
-- Usage in Python:
--   sb.table("carrier_portfolios").select("*").eq("subscription_id", sub_id).execute()
--   sb.table("carrier_properties").select("*").eq("portfolio_id", pid).execute()
--   sb.table("storm_reports").select("*").eq("portfolio_id", pid).execute()
--
-- Idempotent: All CREATEs use IF NOT EXISTS. Safe to re-run.
-- ============================================================================


-- ── 1. CARRIER PORTFOLIOS ────────────────────────────────────────────
-- One row per carrier subscription. Links to buyer_subscriptions for
-- billing state. The carrier on-boards by creating a portfolio, then
-- uploading their book of properties.
CREATE TABLE IF NOT EXISTS public.carrier_portfolios (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    -- Identity
    carrier_name      text NOT NULL,
    contact_email     text NOT NULL,
    contact_name      text,
    contact_phone     text,

    -- Billing link (the carrier subscribes via Strike Packs)
    subscription_id   uuid REFERENCES public.buyer_subscriptions(id) ON DELETE SET NULL,

    -- Portfolio metadata
    property_count    integer NOT NULL DEFAULT 0,
    total_value       numeric(16,2) NOT NULL DEFAULT 0.00,
    coverage_metros   text[] NOT NULL DEFAULT '{}',

    -- Status lifecycle
    status            text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'onboarding', 'canceled')),

    -- Preferences
    report_delivery   text NOT NULL DEFAULT 'email'
        CHECK (report_delivery IN ('email', 'webhook', 'both')),
    report_frequency  text NOT NULL DEFAULT 'immediate'
        CHECK (report_frequency IN ('immediate', 'daily', 'weekly')),

    -- Metadata
    notes             text,
    meta              jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS carrier_portfolios_sub_idx ON public.carrier_portfolios (subscription_id);
CREATE INDEX IF NOT EXISTS carrier_portfolios_status_idx ON public.carrier_portfolios (status);

COMMENT ON TABLE  public.carrier_portfolios IS 'One per carrier subscription. Links to buyer_subscriptions for billing.';
COMMENT ON COLUMN public.carrier_portfolios.subscription_id IS 'Links to buyer_subscriptions for the insurance_intel pack (or other whale products)';
COMMENT ON COLUMN public.carrier_portfolios.coverage_metros IS 'Array of metro areas the carrier has coverage in (e.g. ARRAY[Dallas-Fort Worth, Houston])';
COMMENT ON COLUMN public.carrier_portfolios.report_delivery IS 'How reports are delivered: email, webhook, or both';


-- ── 2. CARRIER PROPERTIES ────────────────────────────────────────────
-- Each insured property in a carrier's book. The carrier uploads these
-- when they on-board (CSV/JSON). Lat/lon is geocoded from the address
-- for storm proximity matching.
CREATE TABLE IF NOT EXISTS public.carrier_properties (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    -- Portfolio link
    portfolio_id      uuid NOT NULL REFERENCES public.carrier_portfolios(id) ON DELETE CASCADE,

    -- Address
    address           text NOT NULL,
    city              text NOT NULL,
    state             text NOT NULL,
    zip               text,
    lat               numeric(10,6),
    lon               numeric(10,6),

    -- Property details
    property_value    numeric(14,2) NOT NULL DEFAULT 0.00,
    coverage_type     text DEFAULT 'commercial'
        CHECK (coverage_type IN ('commercial', 'residential', 'industrial', 'mixed_use')),
    building_type     text DEFAULT 'warehouse',
    year_built        integer,
    sq_ft             integer,
    stories           integer,
    occupancy_type    text DEFAULT 'commercial',
    roof_type         text,
    construction_type text,

    -- Carrier's internal reference
    carrier_ref       text,              -- carrier's internal property ID
    policy_number     text,              -- insurance policy number
    deductible_amount numeric(12,2),     -- property deductible

    -- Last storm match (denormalized for dashboard speed)
    last_matched_at   timestamptz,
    last_storm_event  text,
    last_damage_score numeric(5,2),     -- 0-100 damage score from last match

    -- Constraints
    CONSTRAINT carrier_properties_unique UNIQUE (portfolio_id, address)
);

CREATE INDEX IF NOT EXISTS carrier_properties_portfolio_idx ON public.carrier_properties (portfolio_id);
CREATE INDEX IF NOT EXISTS carrier_properties_geo_idx ON public.carrier_properties (lat, lon);
CREATE INDEX IF NOT EXISTS carrier_properties_zip_idx ON public.carrier_properties (zip);
CREATE INDEX IF NOT EXISTS carrier_properties_lm_idx ON public.carrier_properties (last_matched_at DESC NULLS LAST);

COMMENT ON TABLE  public.carrier_properties IS 'Each insured property in a carriers book. Geocoded for storm matching.';
COMMENT ON COLUMN public.carrier_properties.carrier_ref IS 'Carriers internal property ID for cross-referencing';
COMMENT ON COLUMN public.carrier_properties.last_damage_score IS '0-100 damage severity score from the most recent storm match (0=none, 100=total loss)';


-- ── 3. STORM REPORTS ─────────────────────────────────────────────────
-- One report per storm event per carrier. Generated by the StormMatcher
-- when a storm event overlaps with a carrier's portfolio.
CREATE TABLE IF NOT EXISTS public.storm_reports (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    -- Links
    portfolio_id      uuid NOT NULL REFERENCES public.carrier_portfolios(id) ON DELETE CASCADE,

    -- Storm context
    storm_event       text NOT NULL,          -- e.g. "Severe Thunderstorm Watch"
    storm_severity    text NOT NULL,           -- e.g. "Severe", "Extreme"
    storm_metro       text NOT NULL,           -- e.g. "Dallas-Fort Worth"
    storm_start       timestamptz,
    storm_end         timestamptz,
    storm_id          text,                    -- NWS storm event ID for cross-reference

    -- Report content
    title             text NOT NULL DEFAULT '',
    summary           text NOT NULL DEFAULT '',
    severity_score    numeric(5,2) DEFAULT 0.00,  -- 0-100 aggregate severity
    affected_count    integer NOT NULL DEFAULT 0,  -- number of carrier properties affected
    total_exposure    numeric(16,2) NOT NULL DEFAULT 0.00,  -- total value of affected properties
    estimated_loss    numeric(16,2),                -- estimated total loss range
    recommendations   text DEFAULT '',

    -- Status
    status            text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'generated', 'delivered', 'acknowledged', 'archived')),

    -- Delivery tracking
    delivered_at      timestamptz,
    delivery_method   text DEFAULT 'email',
    delivery_status   text DEFAULT 'pending',

    -- Metadata
    meta              jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS storm_reports_portfolio_idx ON public.storm_reports (portfolio_id, created_at DESC);
CREATE INDEX IF NOT EXISTS storm_reports_status_idx ON public.storm_reports (status);
CREATE INDEX IF NOT EXISTS storm_reports_storm_idx ON public.storm_reports (storm_metro, storm_severity);

COMMENT ON TABLE  public.storm_reports IS 'One report per storm event per carrier. Generated when a storm overlaps portfolio coverage.';
COMMENT ON COLUMN public.storm_reports.severity_score IS 'Aggregate 0-100 severity of this storm for the carriers portfolio';
COMMENT ON COLUMN public.storm_reports.affected_count IS 'Number of the carriers properties within the storm footprint';
COMMENT ON COLUMN public.storm_reports.total_exposure IS 'Total insured value of affected properties';
COMMENT ON COLUMN public.storm_reports.estimated_loss IS 'Estimated total loss range computed from severity + property values';


-- ── 4. STORM REPORT PROPERTIES ───────────────────────────────────────
-- Per-property damage assessment within a storm report. Each row is one
-- carrier property and its storm-specific damage score, distance, etc.
CREATE TABLE IF NOT EXISTS public.storm_report_properties (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),

    -- Links
    report_id         uuid NOT NULL REFERENCES public.storm_reports(id) ON DELETE CASCADE,
    portfolio_id      uuid NOT NULL REFERENCES public.carrier_portfolios(id) ON DELETE CASCADE,
    property_id       uuid NOT NULL REFERENCES public.carrier_properties(id) ON DELETE CASCADE,

    -- Storm context at this property
    distance_to_storm numeric(8,2),           -- miles from property to storm centroid
    wind_gust         numeric(6,2),           -- estimated peak wind gust (mph) at property
    hail_size         numeric(4,2),           -- estimated max hail size (inches)
    precipitation     numeric(6,2),           -- estimated rainfall (inches)
    flood_risk        numeric(5,2),           -- 0-100 flood risk score

    -- Damage scoring
    damage_score      numeric(5,2) NOT NULL DEFAULT 0.00,  -- 0-100 per-property damage score
    damage_category   text DEFAULT 'none'
        CHECK (damage_category IN ('none', 'minor', 'moderate', 'severe', 'total_loss')),
    confidence        numeric(5,2) DEFAULT 0.00,          -- 0-100 confidence in damage score
    estimated_loss    numeric(14,2),                       -- estimated loss for this property

    -- Notes
    notes             text,
    meta              jsonb DEFAULT '{}'::jsonb,

    CONSTRAINT storm_report_properties_unique UNIQUE (report_id, property_id)
);

CREATE INDEX IF NOT EXISTS storm_report_properties_report_idx ON public.storm_report_properties (report_id);
CREATE INDEX IF NOT EXISTS storm_report_properties_property_idx ON public.storm_report_properties (property_id);
CREATE INDEX IF NOT EXISTS storm_report_properties_damage_idx ON public.storm_report_properties (damage_score DESC);

COMMENT ON TABLE  public.storm_report_properties IS 'Per-property damage assessment within a storm report. One row per affected property.';
COMMENT ON COLUMN public.storm_report_properties.damage_score IS '0-100 damage score for this property from this storm event';
COMMENT ON COLUMN public.storm_report_properties.damage_category IS 'Categorical damage: none, minor, moderate, severe, total_loss';
COMMENT ON COLUMN public.storm_report_properties.confidence IS '0-100 confidence in the damage assessment (higher = closer to storm centroid + better data)';


-- ============================================================================
-- VERIFICATION (run separately after migration)
-- ============================================================================
-- -- All carriers with subscription info:
-- SELECT cp.carrier_name, cp.status, cp.property_count, cp.total_value,
--        bs.status AS sub_status, sp.name AS pack_name
-- FROM public.carrier_portfolios cp
-- LEFT JOIN public.buyer_subscriptions bs ON bs.id = cp.subscription_id
-- LEFT JOIN public.strike_packs sp ON sp.id = bs.pack_id
-- ORDER BY cp.created_at DESC;
--
-- -- Properties per carrier (top 5 by count):
-- SELECT cp.carrier_name, COUNT(cpr.id) AS props, SUM(cpr.property_value) AS total_value
-- FROM public.carrier_portfolios cp
-- JOIN public.carrier_properties cpr ON cpr.portfolio_id = cp.id
-- GROUP BY cp.carrier_name
-- ORDER BY props DESC
-- LIMIT 5;
--
-- -- Recent unreported storms (storms with no generated report yet):
-- SELECT sf.id, sf.metro, sf.risk_level, sf.updated_at
-- FROM public.storm_forecasts sf
-- WHERE sf.updated_at >= now() - interval '48 hours'
--   AND NOT EXISTS (
--     SELECT 1 FROM public.storm_reports sr
--     WHERE sr.storm_metro = sf.metro
--       AND sr.created_at >= now() - interval '24 hours'
--   );
-- ============================================================================
