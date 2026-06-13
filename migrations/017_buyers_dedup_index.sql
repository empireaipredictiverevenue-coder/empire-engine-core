-- 017_buyers_dedup_index: prevent (buyer_name, niche) duplicates
-- After manual dedup of 36 duplicate "Apex Mass Tort Group" rows on 2026-06-13,
-- this partial unique index makes the dedup permanent at the schema level.
--
-- Partial index: only enforced when both buyer_name and niche are NOT NULL.
-- Excludes rows where either is null (so test fixtures / partial inserts still work).

CREATE UNIQUE INDEX IF NOT EXISTS buyers_name_niche_unique
  ON public.buyers (buyer_name, niche)
  WHERE buyer_name IS NOT NULL AND niche IS NOT NULL;
