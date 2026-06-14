-- Add converted_at column to enriched_leads.
-- The converter marks leads as status=converted but doesn't set a
-- timestamp. This breaks the sms_qc tier-2 check 'converted_no_sequence'
-- which needs to know when a lead was converted (to limit the
-- query to the last hour).
--
-- Backfill: any row currently status=converted gets converted_at =
-- max(created_at, last_enriched_at, meta->'converted_at' if it
-- happens to be there).

alter table public.enriched_leads
    add column if not exists converted_at timestamptz;

-- Backfill existing converted rows. Use last_enriched_at if present,
-- else created_at.
update public.enriched_leads
    set converted_at = coalesce(last_enriched_at, created_at, now())
    where status = 'converted' and converted_at is null;

create index if not exists idx_enriched_leads_converted_at
    on public.enriched_leads (converted_at desc)
    where status = 'converted' and converted_at is not null;
