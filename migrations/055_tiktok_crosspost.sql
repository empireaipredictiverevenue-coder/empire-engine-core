-- 055: YouTube shorts publish tracking + TikTok upload queue
CREATE TABLE IF NOT EXISTS youtube_shorts_publishes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id text UNIQUE NOT NULL,
    file_path text,
    youtube_uploaded_at timestamptz,
    youtube_error text,
    tiktok_uploaded_at timestamptz,
    tiktok_file_path text,
    tiktok_error text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tiktok_upload_queue (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id text UNIQUE NOT NULL,
    file_path text,
    caption text,
    hashtags text[],
    status text DEFAULT 'queued',
    created_at timestamptz DEFAULT now(),
    published_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_yt_publishes_youtube ON youtube_shorts_publishes(youtube_uploaded_at);
CREATE INDEX IF NOT EXISTS idx_yt_publishes_tiktok ON youtube_shorts_publishes(tiktok_uploaded_at);
CREATE INDEX IF NOT EXISTS idx_tiktok_queue_status ON tiktok_upload_queue(status);