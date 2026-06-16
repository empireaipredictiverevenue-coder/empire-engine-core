-- Empire AI · Inbound/Outbound message log
-- 2026-06-16: tracks every email/SMS we send or receive, so the
-- daily digest can summarize inbound activity and we can audit
-- auto-reply decisions.

CREATE TABLE IF NOT EXISTS inbox_messages (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  channel             text NOT NULL,           -- 'email' | 'sms'
  from_address        text,
  to_address          text,
  subject             text,
  body                text,
  received_at         timestamptz NOT NULL DEFAULT now(),
  classified_intent   text,                    -- 'interested'|'question'|'not_now'|'opt_out'|'bounce'|'wrong_person'|'unknown'|'empty'
  in_reply_to         text,                    -- upstream message_id we replied to
  meta                jsonb DEFAULT '{}'::jsonb,
  created_at          timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS inbox_messages_received_at_idx ON inbox_messages (received_at DESC);
CREATE INDEX IF NOT EXISTS inbox_messages_intent_idx     ON inbox_messages (classified_intent);
CREATE INDEX IF NOT EXISTS inbox_messages_channel_idx    ON inbox_messages (channel);

CREATE TABLE IF NOT EXISTS outbox_messages (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  channel             text NOT NULL,           -- 'email' | 'sms'
  to_address          text,
  from_address        text,
  subject             text,
  body                text,
  sent_at             timestamptz NOT NULL DEFAULT now(),
  sent_status         text,                    -- 'sent'|'failed'|'queued'|'dry_run'
  in_reply_to         text,                    -- upstream inbound that triggered this
  meta                jsonb DEFAULT '{}'::jsonb,
  created_at          timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outbox_messages_sent_at_idx ON outbox_messages (sent_at DESC);
CREATE INDEX IF NOT EXISTS outbox_messages_status_idx  ON outbox_messages (sent_status);
