-- 008_pipeline_columns.sql
-- New columns for pipeline stages

-- Stage 1: intro detection
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS intro_end_position INT;

-- Stage 2: clean text
ALTER TABLE segments ADD COLUMN IF NOT EXISTS clean_text TEXT;
ALTER TABLE segments ADD COLUMN IF NOT EXISTS text_confidence FLOAT;
ALTER TABLE segments ADD COLUMN IF NOT EXISTS person_id UUID REFERENCES people(id);
CREATE INDEX IF NOT EXISTS idx_segments_person ON segments(person_id);

-- Stage 2: quality tracking
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS quality_issues JSONB;

-- Stage 3: processing tracking
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS knowledge_processed_at TIMESTAMP;
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS needs_reprocessing BOOLEAN DEFAULT false;

-- Stage 3h: persona
ALTER TABLE people ADD COLUMN IF NOT EXISTS persona_json JSONB;

-- Segment corrections table (review UI + public flags)
CREATE TABLE IF NOT EXISTS segment_corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    segment_id UUID REFERENCES segments(id) ON DELETE CASCADE,
    episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    original_text TEXT,
    suggested_text TEXT,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_corrections_episode ON segment_corrections(episode_id);
CREATE INDEX IF NOT EXISTS idx_corrections_status ON segment_corrections(status);
