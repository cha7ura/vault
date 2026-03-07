-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Episodes table
CREATE TABLE episodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  youtube_id TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  thumbnail_url TEXT,
  duration_seconds INT,
  published_at TIMESTAMP,
  transcript TEXT,
  transcript_formatted TEXT,  -- AI-formatted with bold, quotes
  embedding VECTOR(1536),     -- For semantic search
  references JSONB,           -- URLs parsed from description
  processed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Guests table
CREATE TABLE guests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  bio TEXT,
  photo_url TEXT,
  twitter TEXT,
  linkedin TEXT,
  website TEXT,
  books_authored JSONB,  -- [{title, year, amazon_url}]
  companies JSONB,       -- [{name, role, url}]
  created_at TIMESTAMP DEFAULT NOW()
);

-- Episode-Guest junction
CREATE TABLE episode_guests (
  episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
  guest_id UUID REFERENCES guests(id) ON DELETE CASCADE,
  PRIMARY KEY (episode_id, guest_id)
);

-- Insights (frameworks, quotes, advice, etc.)
CREATE TABLE insights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
  guest_id UUID REFERENCES guests(id) ON DELETE SET NULL,
  type TEXT NOT NULL,  -- 'framework', 'insight', 'quote', 'story', 'health', 'mindset'
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  start_time_seconds INT,
  end_time_seconds INT,
  embedding VECTOR(1536),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Books mentioned in episodes
CREATE TABLE books (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  author TEXT,
  amazon_url TEXT,
  mentioned_by_guest_id UUID REFERENCES guests(id) ON DELETE SET NULL,
  context TEXT,  -- Why it was mentioned
  timestamp_seconds INT
);

-- Papers/Research mentioned
CREATE TABLE papers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  authors TEXT,
  url TEXT,
  context TEXT,
  timestamp_seconds INT
);

-- Create indexes
CREATE INDEX idx_episodes_youtube_id ON episodes(youtube_id);
CREATE INDEX idx_episodes_published ON episodes(published_at DESC);
CREATE INDEX idx_insights_type ON insights(type);
CREATE INDEX idx_insights_episode ON insights(episode_id);
CREATE INDEX idx_guests_slug ON guests(slug);

-- Vector similarity search indexes
CREATE INDEX idx_episodes_embedding ON episodes 
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_insights_embedding ON insights 
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Function for semantic search
CREATE OR REPLACE FUNCTION semantic_search_episodes(
  query_embedding vector(1536),
  match_count INT DEFAULT 20,
  match_threshold FLOAT DEFAULT 0.5
)
RETURNS TABLE (
  id UUID,
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
    e.youtube_id,
    e.title,
    e.description,
    e.thumbnail_url,
    e.published_at,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM episodes e
  WHERE e.embedding IS NOT NULL
    AND 1 - (e.embedding <=> query_embedding) > match_threshold
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Function for semantic search insights
CREATE OR REPLACE FUNCTION semantic_search_insights(
  query_embedding vector(1536),
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
  WHERE i.embedding IS NOT NULL
    AND 1 - (i.embedding <=> query_embedding) > match_threshold
    AND (insight_type IS NULL OR i.type = insight_type)
  ORDER BY i.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
