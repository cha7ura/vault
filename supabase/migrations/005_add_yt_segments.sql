-- YouTube auto-generated caption segments, aligned to our segment time boundaries
CREATE TABLE yt_segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  position INT NOT NULL,
  start_time FLOAT NOT NULL,
  end_time FLOAT NOT NULL,
  text TEXT NOT NULL,
  words JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_yt_segments_episode ON yt_segments(episode_id);
CREATE INDEX idx_yt_segments_position ON yt_segments(episode_id, position);
