-- 054: youtube_comments table for comment engagement agent
CREATE TABLE IF NOT EXISTS youtube_comments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_id text UNIQUE NOT NULL,
    video_id text,
    author text,
    text text,
    reply text,
    replied boolean DEFAULT false,
    like_count int DEFAULT 0,
    published_at timestamptz,
    updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_yt_comments_replied ON youtube_comments(replied);
CREATE INDEX IF NOT EXISTS idx_yt_comments_video ON youtube_comments(video_id);
