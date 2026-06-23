-- email_outreach tables
CREATE TABLE IF NOT EXISTS email_sequences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT now(),
    contractor_id UUID REFERENCES contractors(id) ON DELETE CASCADE,
    sequence_type TEXT NOT NULL,
    step INT DEFAULT 1,
    last_sent_at TIMESTAMPTZ,
    meta JSONB
);
CREATE INDEX IF NOT EXISTS idx_email_sequences_contractor
    ON email_sequences (contractor_id, sequence_type);

CREATE TABLE IF NOT EXISTS email_outreach_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contractor_id UUID REFERENCES contractors(id) ON DELETE CASCADE,
    step INT NOT NULL,
    status TEXT NOT NULL,
    resend_id TEXT,
    detail TEXT,
    fired_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_outreach_dedupe
    ON email_outreach_log (contractor_id, step, fired_at DESC);

CREATE TABLE IF NOT EXISTS email_replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contractor_id UUID REFERENCES contractors(id) ON DELETE CASCADE,
    from_email TEXT,
    body TEXT,
    received_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_replies_contractor
    ON email_replies (contractor_id, received_at DESC);