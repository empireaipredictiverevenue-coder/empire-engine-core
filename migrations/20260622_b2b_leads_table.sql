-- EMPIRE V49 · b2b_leads table
-- Created 2026-06-22
-- Stores B2B leads from b2b_leads_export.csv — potential Suite product buyers
-- (HR & Staffing, Managed IT, Merchant Services across TX/OK/MO/CO/KS/AZ/GA)

CREATE TABLE IF NOT EXISTS b2b_leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    metro TEXT,
    niche TEXT NOT NULL,
    website TEXT,
    lead_score INT DEFAULT 0,
    urgency INT DEFAULT 0,
    product_fit TEXT[] DEFAULT '{}',
    source TEXT DEFAULT 'b2b_leads_export',
    source_created_at TEXT,
    status TEXT DEFAULT 'new',
    meta JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_b2b_leads_niche ON b2b_leads(niche);
CREATE INDEX IF NOT EXISTS idx_b2b_leads_state ON b2b_leads(state);
CREATE INDEX IF NOT EXISTS idx_b2b_leads_metro ON b2b_leads(metro);
CREATE INDEX IF NOT EXISTS idx_b2b_leads_status ON b2b_leads(status);
CREATE INDEX IF NOT EXISTS idx_b2b_leads_score ON b2b_leads(lead_score DESC);

-- Unique constraint on email to prevent duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_b2b_leads_email ON b2b_leads(email) WHERE email IS NOT NULL AND email != '';

COMMENT ON TABLE b2b_leads IS 'B2B leads from CSV import — potential Suite product buyers (not storm leads)';
