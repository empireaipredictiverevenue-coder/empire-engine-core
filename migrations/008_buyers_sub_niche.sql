-- ============================================================================
-- EMPIRE V49 · DDL MIGRATION 008: ADD sub_niche TO buyers
-- ============================================================================
-- The 32-lane grid is being rebalanced so Legal is a first-class niche
-- with 5 sub-niches (Pharma Liability, Medical Device, Consumer Product,
-- Class Action, Mass Tort). The buyers table needs a sub_niche column so
-- the call router can match a recall classification to the right buyer.
--
-- Also renames the legacy 'Mass Tort Legal' niche to 'Legal' (the new
-- lane config uses 'Legal' as the niche label, with sub_niche doing the
-- further breakdown). The 34 inactive duplicate rows keep the old value
-- for now (they will be DELETEd in step 6 of the lane-sort plan).
--
-- Idempotent: ADD COLUMN IF NOT EXISTS, UPDATE is guarded by the new
-- value check.
-- ============================================================================


-- ── 1. ADD sub_niche COLUMN ────────────────────────────────────────────
ALTER TABLE buyers
    ADD COLUMN IF NOT EXISTS sub_niche text DEFAULT NULL;


-- ── 2. RETAG CANONICAL ACTIVE BUYER ────────────────────────────────────
-- The single active Mass Tort Legal row (Apex Mass Tort Group) becomes
-- niche='Legal', sub_niche='Mass Tort'. The 34 inactive dup rows are
-- left untouched (they'll be DELETEd later; flipping their niche now
-- would make step 6 harder to verify).
UPDATE buyers
SET niche = 'Legal', sub_niche = 'Mass Tort'
WHERE buyer_name = 'Apex Mass Tort Group'
  AND is_active = true
  AND niche = 'Mass Tort Legal';


-- ── 3. RETAG OTHER KNOWN LOWERCASE NICHES ──────────────────────────────
-- 'roofing' and 'restoration' are old-format niche names. Normalize to
-- the new display labels. Only touches active rows to avoid churn on
-- inactive duplicates.
UPDATE buyers
SET niche = 'Roofing Restoration'
WHERE niche = 'roofing' AND is_active = true;

UPDATE buyers
SET niche = 'Consumer CPA'
WHERE niche = 'restoration' AND is_active = true;


-- ============================================================================
-- VERIFICATION (run separately after this migration)
-- ============================================================================
-- SELECT niche, sub_niche, count(*)
--   FROM buyers
--   WHERE is_active = true
--   GROUP BY niche, sub_niche
--   ORDER BY niche;
--
-- Expected output after this migration:
--   Legal  | Mass Tort | 1
--   (other niches depend on real buyers added later)
-- ============================================================================
