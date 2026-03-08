-- People & Agent Memories: global identity, voice fingerprinting, and persona agent state

-- People table (global identity, not channel-scoped)
CREATE TABLE people (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE,
  photo_url TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Agent memories table (1:1 with people — persona agent state)
CREATE TABLE agent_memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  memory JSONB NOT NULL DEFAULT '{}',
  memory_version INT DEFAULT 0,
  turns_processed INT DEFAULT 0,
  last_episode_id UUID REFERENCES episodes(id),
  last_position INT,
  updated_at TIMESTAMP DEFAULT NOW(),
  created_at TIMESTAMP DEFAULT NOW(),
  CONSTRAINT agent_memories_person_unique UNIQUE (person_id)
);

CREATE INDEX idx_agent_memories_person ON agent_memories(person_id);

-- Speaker embeddings table (voice fingerprinting via NeMo TitaNet)
CREATE TABLE speaker_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  speaker_label TEXT NOT NULL,
  embedding VECTOR(192),          -- NeMo TitaNet produces 192-dim embeddings
  person_id UUID REFERENCES people(id) ON DELETE SET NULL,
  mapped_confidence FLOAT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_speaker_embeddings_episode ON speaker_embeddings(episode_id);
CREATE INDEX idx_speaker_embeddings_person ON speaker_embeddings(person_id);
CREATE UNIQUE INDEX idx_speaker_embeddings_episode_speaker ON speaker_embeddings(episode_id, speaker_label);

-- Link guests to global people identity
ALTER TABLE guests ADD COLUMN person_id UUID REFERENCES people(id) ON DELETE SET NULL;
CREATE INDEX idx_guests_person ON guests(person_id);
