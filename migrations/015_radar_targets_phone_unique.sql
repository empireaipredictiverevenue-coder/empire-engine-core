-- 015_radar_targets_phone_unique.sql
-- Deduplicate radar_targets by phone + add unique partial index for pipeline upsert.
-- The pipeline needs upsert(on_conflict="phone") but the column only had a non-unique index.
--
-- Strategy: keep the newest row per phone, re-parent FK references, delete duplicates.

BEGIN;

-- ── 1. Identify and re-parent duplicates ─────────────────────────────
-- For each duplicate phone, keep the most recent row (newest created_at).
-- Update FK references in child tables to point to the kept row.

DO $$
DECLARE
    dup record;
    keep_id uuid;
    del_id uuid;
BEGIN
    -- Loop through each duplicate phone group
    FOR dup IN
        SELECT phone, array_agg(id ORDER BY created_at DESC, id) AS ids
        FROM radar_targets
        WHERE phone IS NOT NULL
        GROUP BY phone
        HAVING COUNT(*) > 1
    LOOP
        -- First id in the ordered array is the one to keep (newest)
        keep_id := dup.ids[1];

        -- Re-parent all FKs from duplicate rows to the kept row
        -- strike_log
        UPDATE strike_log SET target_id = keep_id
        WHERE target_id = ANY(dup.ids[2:]);
        -- brain_decisions
        UPDATE brain_decisions SET lead_id = keep_id
        WHERE lead_id = ANY(dup.ids[2:]);
        -- dispatches
        UPDATE dispatches SET lead_id = keep_id
        WHERE lead_id = ANY(dup.ids[2:]);
        -- claim_outcomes
        UPDATE claim_outcomes SET lead_id = keep_id
        WHERE lead_id = ANY(dup.ids[2:]);
        -- inbound_calls
        UPDATE inbound_calls SET matched_lead_id = keep_id
        WHERE matched_lead_id = ANY(dup.ids[2:]);
        -- brain_memory
        UPDATE brain_memory SET lead_id = keep_id
        WHERE lead_id = ANY(dup.ids[2:]);
        -- email_drafts (has ON DELETE SET NULL, but re-parent anyway)
        UPDATE email_drafts SET target_id = keep_id
        WHERE target_id = ANY(dup.ids[2:]);

        -- Delete the duplicate rows
        DELETE FROM radar_targets WHERE id = ANY(dup.ids[2:]);
    END LOOP;
END $$;

-- ── 2. Verify no duplicates remain (safety check) ────────────────────
DO $$
DECLARE
    dup_count int;
BEGIN
    SELECT COUNT(*) INTO dup_count
    FROM (
        SELECT phone FROM radar_targets
        WHERE phone IS NOT NULL
        GROUP BY phone HAVING COUNT(*) > 1
    ) d;
    IF dup_count > 0 THEN
        RAISE EXCEPTION '% duplicate phones remain after dedup — aborting transaction', dup_count;
    END IF;
END $$;

-- ── 3. Drop old non-unique index ─────────────────────────────────────
DROP INDEX IF EXISTS radar_targets_phone_idx;

-- ── 4. Create unique partial index on phone (only non-null phones) ───
CREATE UNIQUE INDEX IF NOT EXISTS radar_targets_phone_unique
    ON radar_targets (phone)
    WHERE phone IS NOT NULL;

COMMIT;
