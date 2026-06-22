-- 053: Business Growth Agent — recommendations + actions log

CREATE TABLE IF NOT EXISTS business_recommendations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category text NOT NULL,                   -- 'funnel' | 'leads' | 'pricing' | 'outreach' | 'verticals'
    severity text NOT NULL DEFAULT 'info',     -- info | warning | critical
    title text NOT NULL,
    description text,
    recommended_action text,
    auto_executable boolean DEFAULT false,
    status text NOT NULL DEFAULT 'open',       -- open | accepted | dismissed | executed
    detected_at timestamptz DEFAULT now(),
    resolved_at timestamptz,
    metadata jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_rec_status ON business_recommendations(status);
CREATE INDEX IF NOT EXISTS idx_rec_category ON business_recommendations(category);

CREATE TABLE IF NOT EXISTS business_actions_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type text NOT NULL,
    action_payload jsonb DEFAULT '{}'::jsonb,
    result text,
    executed_at timestamptz DEFAULT now(),
    duration_ms int
);
CREATE INDEX IF NOT EXISTS idx_act_type ON business_actions_log(action_type);
CREATE INDEX IF NOT EXISTS idx_act_at ON business_actions_log(executed_at);