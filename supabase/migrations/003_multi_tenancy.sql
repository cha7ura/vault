-- Multi-tenancy: Add channels table and link all content to channels

-- Channels table (YouTube channels we're tracking)
CREATE TABLE channels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  youtube_channel_id TEXT UNIQUE NOT NULL,  -- e.g., UCrPseYLGpNygVi34QpGNqpA
  name TEXT NOT NULL,                        -- e.g., "The Diary of a CEO"
  slug TEXT UNIQUE NOT NULL,                 -- e.g., "diary-of-a-ceo"
  description TEXT,
  thumbnail_url TEXT,
  banner_url TEXT,
  subscriber_count INT,
  video_count INT,
  -- Customization
  primary_color TEXT DEFAULT '#000000',
  accent_color TEXT DEFAULT '#3b82f6',
  -- Settings
  auto_ingest BOOLEAN DEFAULT true,
  ingest_schedule TEXT DEFAULT '0 */6 * * *',  -- Cron expression
  -- Metadata
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  last_synced_at TIMESTAMP
);

-- Add channel_id to episodes
ALTER TABLE episodes ADD COLUMN channel_id UUID REFERENCES channels(id) ON DELETE CASCADE;

-- Add channel_id to guests (guests can appear on multiple channels, but we track per-channel)
ALTER TABLE guests ADD COLUMN channel_id UUID REFERENCES channels(id) ON DELETE CASCADE;

-- Update unique constraint on guests to be per-channel
ALTER TABLE guests DROP CONSTRAINT IF EXISTS guests_slug_key;
ALTER TABLE guests ADD CONSTRAINT guests_channel_slug_unique UNIQUE (channel_id, slug);

-- Update unique constraint on episodes to be per-channel
ALTER TABLE episodes DROP CONSTRAINT IF EXISTS episodes_youtube_id_key;
ALTER TABLE episodes ADD CONSTRAINT episodes_channel_youtube_unique UNIQUE (channel_id, youtube_id);

-- Add indexes for channel filtering
CREATE INDEX idx_episodes_channel ON episodes(channel_id);
CREATE INDEX idx_guests_channel ON guests(channel_id);
CREATE INDEX idx_channels_slug ON channels(slug);
CREATE INDEX idx_channels_youtube_id ON channels(youtube_channel_id);

-- Update semantic search function to filter by channel
CREATE OR REPLACE FUNCTION semantic_search_episodes(
  query_embedding vector(1536),
  p_channel_id UUID DEFAULT NULL,
  match_count INT DEFAULT 20,
  match_threshold FLOAT DEFAULT 0.5
)
RETURNS TABLE (
  id UUID,
  channel_id UUID,
  youtube_id TEXT,
  title TEXT,
  description TEXT,
  thumbnail_url TEXT,
  published_at TIMESTAMP,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.channel_id,
    e.youtube_id,
    e.title,
    e.description,
    e.thumbnail_url,
    e.published_at,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM episodes e
  WHERE e.embedding IS NOT NULL
    AND 1 - (e.embedding <=> query_embedding) > match_threshold
    AND (p_channel_id IS NULL OR e.channel_id = p_channel_id)
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Update semantic search insights to filter by channel
CREATE OR REPLACE FUNCTION semantic_search_insights(
  query_embedding vector(1536),
  p_channel_id UUID DEFAULT NULL,
  match_count INT DEFAULT 20,
  match_threshold FLOAT DEFAULT 0.5,
  insight_type TEXT DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  episode_id UUID,
  guest_id UUID,
  type TEXT,
  title TEXT,
  content TEXT,
  start_time_seconds INT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    i.id,
    i.episode_id,
    i.guest_id,
    i.type,
    i.title,
    i.content,
    i.start_time_seconds,
    1 - (i.embedding <=> query_embedding) AS similarity
  FROM insights i
  JOIN episodes e ON i.episode_id = e.id
  WHERE i.embedding IS NOT NULL
    AND 1 - (i.embedding <=> query_embedding) > match_threshold
    AND (insight_type IS NULL OR i.type = insight_type)
    AND (p_channel_id IS NULL OR e.channel_id = p_channel_id)
  ORDER BY i.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Function to get or create channel from YouTube URL/ID
CREATE OR REPLACE FUNCTION get_or_create_channel(
  p_youtube_channel_id TEXT,
  p_name TEXT,
  p_slug TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  v_channel_id UUID;
  v_slug TEXT;
BEGIN
  -- Check if channel exists
  SELECT id INTO v_channel_id FROM channels WHERE youtube_channel_id = p_youtube_channel_id;
  
  IF v_channel_id IS NOT NULL THEN
    RETURN v_channel_id;
  END IF;
  
  -- Generate slug if not provided
  v_slug := COALESCE(p_slug, LOWER(REGEXP_REPLACE(p_name, '[^a-zA-Z0-9]+', '-', 'g')));
  v_slug := TRIM(BOTH '-' FROM v_slug);
  
  -- Insert new channel
  INSERT INTO channels (youtube_channel_id, name, slug)
  VALUES (p_youtube_channel_id, p_name, v_slug)
  RETURNING id INTO v_channel_id;
  
  RETURN v_channel_id;
END;
$$;
