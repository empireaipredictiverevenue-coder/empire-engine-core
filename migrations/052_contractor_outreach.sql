-- 052: contractor outreach tracking + sequence state

CREATE TABLE IF NOT EXISTS contractor_outreach (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contractor_id uuid REFERENCES contractors(id),
    sequence text NOT NULL,                              -- 'tier_intro' | 'tier_nudge' | 'final_push'
    step int NOT NULL DEFAULT 1,                           -- 1..4 within sequence
    status text NOT NULL DEFAULT 'pending',               -- pending | sent | replied | paid | unsubscribed
    last_sent_at timestamptz,
    next_send_at timestamptz,
    opened_at timestamptz,
    clicked_at timestamptz,
    paid_at timestamptz,
    notes text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outreach_contractor ON contractor_outreach(contractor_id);
CREATE INDEX IF NOT EXISTS idx_outreach_status ON contractor_outreach(status);
CREATE INDEX IF NOT EXISTS idx_outreach_next ON contractor_outreach(next_send_at);

-- Unique enrollment: one row per contractor per sequence (so they get one fresh start)
CREATE UNIQUE INDEX IF NOT EXISTS uq_outreach_enrollment ON contractor_outreach(contractor_id, sequence);