-- 049: fee settlement discount
-- Adds a discount window so we can offer contractors a reduced fee if
-- they pay within a deadline. Original fee is preserved; discount_amount
-- and discount_expires_at are nullable.
ALTER TABLE fee_events
  ADD COLUMN IF NOT EXISTS discount_percent numeric(5,2) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS discount_amount numeric(12,2) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS discount_expires_at timestamptz DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS discount_offered_at timestamptz DEFAULT NULL;

COMMENT ON COLUMN fee_events.discount_percent IS 'e.g. 0.20 for 20% off, null if no discount';
COMMENT ON COLUMN fee_events.discount_amount IS 'dollar amount subtracted from fee_amount at settlement';
COMMENT ON COLUMN fee_events.discount_expires_at IS 'contractor must pay by this to get the discount';
COMMENT ON COLUMN fee_events.discount_offered_at IS 'when we offered the discount (SMS / call / page)';