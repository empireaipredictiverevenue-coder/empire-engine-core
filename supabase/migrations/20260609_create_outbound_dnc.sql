-- Create outbound_dnc table for manual DNC entries
CREATE TABLE IF NOT EXISTS outbound_dnc (
    phone      text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    reason     text DEFAULT 'manual',
    meta       jsonb DEFAULT '{}'::jsonb
);
