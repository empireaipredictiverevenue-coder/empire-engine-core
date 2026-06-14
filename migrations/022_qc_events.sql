-- Quality-control events table. The sms_qc daemon writes tier-1
-- (auto-remediated) and tier-2 (Telegram-pinged) events here; the
-- operator dashboard reads them to see what got auto-fixed and what
-- needs human eyes. Tier-3 (daily summary) is a single row per day,
-- not a per-event log, so it lives in a separate column on
-- agent_config rather than a separate table.

create table if not exists public.qc_events (
    id                  uuid primary key default gen_random_uuid(),
    created_at          timestamptz not null default now(),
    severity            text not null,            -- tier_1, tier_2, tier_3
    category            text not null,            -- dispatcher_miss, 422_repeat, stuck_sequence, etc
    source_agent        text,                     -- sms_qc, dispatcher, converter, etc
    subject_kind        text,                     -- sms_sequence, sms_log, enriched_lead, contractor
    subject_id          text,                     -- the uuid or phone or whatever identifies the thing
    summary             text not null,            -- one-line human description
    detail              jsonb default '{}'::jsonb, -- structured context (e.g. failure count, ages)
    auto_remediated     boolean default false,     -- did sms_qc fix this on its own?
    remediation         text,                     -- what it did (e.g. "marked sequence replied")
    telegram_pinged     boolean default false,     -- was a Telegram alert sent?
    resolved            boolean default false,     -- operator marked it handled (or the fix took)
    resolved_at         timestamptz,
    resolved_by         text
);

-- Most queries are: "show me tier_2 events from the last 24h that
-- aren't resolved" or "count tier_1 auto-remediated events by category".
-- These two indexes cover both.
create index if not exists idx_qc_events_severity_created
    on public.qc_events (severity, created_at desc);
create index if not exists idx_qc_events_unresolved_tier2
    on public.qc_events (resolved, severity, created_at desc)
    where resolved = false and severity = 'tier_2';

-- RLS note: this table is written by the backend (sms_qc daemon
-- running as service role). The operator SPA reads it via the
-- same get_db() handle. No row-level security needed.
