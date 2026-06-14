-- Contractor referrals table.
-- Captures the (name + phone) pair a current contractor refers to us
-- via "reply REFER name number" in the contractor_recruit v2 sequence.
-- Minimal columns: who referred, who was referred, when, and the
-- outreach_log id of the original reply (if we can match it).
--
-- Compliance: phone is stored as E.164, no TCPA consent at this point
-- (the referred contractor hasn't opted in). The contractor_recruit
-- sequence asks for opt-in via reply when we reach out.

create table if not exists public.contractor_referrals (
    id                  uuid primary key default gen_random_uuid(),
    created_at          timestamptz not null default now(),
    referrer_contractor_id   uuid references public.contractors(id) on delete set null,
    referrer_phone      text,
    referred_name       text not null,
    referred_phone      text not null,
    referred_company    text,
    referred_metro      text,
    status              text not null default 'new',  -- new, contacted, accepted, rejected
    notes               text,
    -- idempotency: same referrer + same referred_phone is unique
    unique (referrer_phone, referred_phone)
);

create index if not exists idx_contractor_referrals_status
    on public.contractor_referrals (status, created_at desc);
