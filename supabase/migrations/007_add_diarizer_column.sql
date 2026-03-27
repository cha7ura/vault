-- Add diarizer column to segments for multi-diarizer comparison
ALTER TABLE segments ADD COLUMN IF NOT EXISTS diarizer TEXT NOT NULL DEFAULT 'whisper-diarization';

CREATE INDEX idx_segments_diarizer ON segments(episode_id, diarizer);
