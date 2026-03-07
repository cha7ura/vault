-- Segments table for storing diarized transcript segments per episode
CREATE TABLE segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  position INT NOT NULL,             -- ordering within the episode
  speaker TEXT NOT NULL,             -- e.g., "Speaker 0"
  start_time FLOAT NOT NULL,        -- seconds from start
  end_time FLOAT NOT NULL,          -- seconds from start
  text TEXT NOT NULL,
  words JSONB,                       -- per-word timestamps [{text, start, end, score}]
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_segments_episode ON segments(episode_id);
CREATE INDEX idx_segments_position ON segments(episode_id, position);
