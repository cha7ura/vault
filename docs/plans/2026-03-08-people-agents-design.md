# People Agents — Design Document

**Date:** 2026-03-08
**Status:** Approved

## Overview

Build living persona agents from podcast transcripts. Each speaker (host + guests) gets their own agent whose memory is built incrementally by replaying diarized conversations chronologically — oldest episode to latest. The system uses voice fingerprinting for automatic speaker identification and a structured memory schema informed by recent research in generative agent simulation.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Speaker-to-guest mapping | Voice fingerprinting (NeMo embeddings) | NeMo already computes speaker embeddings during diarization — reuse existing infrastructure |
| Host identification | Single host per channel, cosine similarity anchor | Host voice is the constant across episodes; other speaker = guest |
| Memory storage | Separate `agent_memories` table (1:1 with `people`) | Clean separation from profile data, enables processing state tracking |
| Identity model | Global `people` table + channel-scoped `guests` | Same person across channels shares one unified memory |
| LLM for pipeline | GLM 4.7 (local) | Zero cost for batch processing (~400 calls/episode) |
| LLM for chat (future) | OpenRouter (free model or BYOK) | Quality matters more for user-facing chat; fewer calls |
| Pipeline architecture | Discrete stages with runner script | Idempotent, resumable, each stage testable independently |
| Priority | Character Memory Page first | Validates pipeline quality before building chat |

## Data Model

### New Tables

#### `people` (global identity)

```sql
CREATE TABLE people (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE,
  photo_url TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

Deliberately thin — profile richness stays on `guests` (channel-specific bios, socials, books). `people` is the identity anchor.

#### `agent_memories` (1:1 with people)

```sql
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
```

#### `speaker_embeddings` (for voice fingerprinting)

```sql
CREATE TABLE speaker_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  speaker_label TEXT NOT NULL,
  embedding VECTOR(192),
  person_id UUID REFERENCES people(id) ON DELETE SET NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_speaker_embeddings_episode ON speaker_embeddings(episode_id);
CREATE INDEX idx_speaker_embeddings_person ON speaker_embeddings(person_id);
CREATE UNIQUE INDEX idx_speaker_embeddings_unique ON speaker_embeddings(episode_id, speaker_label);
```

### Modified Tables

#### `guests` — add column

```sql
ALTER TABLE guests ADD COLUMN person_id UUID REFERENCES people(id) ON DELETE SET NULL;
CREATE INDEX idx_guests_person ON guests(person_id);
```

### Relationships

```
people (global)  <── agent_memories (1:1)
  |
  v
guests (channel-scoped, person_id FK)
  |
  v
episode_guests (unchanged)
```

## Memory Schema (JSONB)

Informed by research from:
- Stanford GenAgents 1000 (expert reflections, importance scoring)
- A-MEM (Zettelkasten-style linked memory evolution)
- Evolving Agents (character growth tracking, emotion module)
- CoALA (episodic/semantic/procedural memory split)

```json
{
  "persona": {
    "communication_style": {
      "tone": "analytical|conversational|passionate|measured",
      "formality": "casual|moderate|formal",
      "storytelling_tendency": "high|medium|low",
      "signature_phrases": ["phrase1", "phrase2"],
      "speech_patterns": ["uses analogies frequently", "tends to quantify claims"]
    },
    "personality_traits": {
      "openness": "high|medium|low",
      "conscientiousness": "high|medium|low",
      "extraversion": "high|medium|low",
      "agreeableness": "high|medium|low",
      "emotional_stability": "high|medium|low"
    },
    "expertise_domains": [
      {"domain": "", "depth": "deep|moderate|surface"}
    ]
  },

  "semantic_memory": {
    "beliefs": {
      "topic_key": {
        "stance": "",
        "confidence": "high|medium|low",
        "first_expressed": "episode_id",
        "last_reinforced": "episode_id"
      }
    },
    "frameworks": [
      {"name": "", "description": "", "source_episode": ""}
    ],
    "recurring_themes": ["theme1", "theme2"],
    "references": [
      {"type": "book|person|concept|study", "name": "", "sentiment": "positive|neutral|critical", "context": ""}
    ],
    "relationships": [
      {"person": "", "nature": "admires|disagrees_with|mentors|collaborates|references", "context": ""}
    ]
  },

  "episodic_memory": [
    {
      "episode_id": "",
      "date": "",
      "role": "host|guest",
      "summary": "",
      "key_moments": ["notable quote or insight"],
      "emotional_peaks": [{"topic": "", "reaction": ""}]
    }
  ],

  "reflections": [
    {
      "insight": "",
      "importance": 0.85,
      "derived_from": ["episode_id1", "episode_id2"],
      "expert_lens": "psychologist|domain_expert|communication_analyst|philosopher",
      "created_at": ""
    }
  ],

  "contradictions": [
    {
      "topic": "",
      "earlier_stance": "",
      "later_stance": "",
      "episodes": [],
      "resolution": "evolved|context_dependent|unresolved"
    }
  ],

  "growth_log": [
    {
      "dimension": "belief|communication_style|expertise|emotional_pattern",
      "description": "what changed",
      "from_episode": "",
      "to_episode": "",
      "detected_at": ""
    }
  ]
}
```

### Design rationale for schema fields

| Field | Source Paper | Why It Matters |
|-------|-------------|----------------|
| `persona.communication_style` | Stanford GenAgents 1000 | Linguistic features improve agent accuracy — captures *how* they talk |
| `persona.personality_traits` | Big Five (validated by Stanford paper) | Gives the LLM a personality anchor for Chat with X |
| `semantic_memory.beliefs.confidence` | GenAgents importance scoring | Not all beliefs are held equally — core convictions vs passing mentions |
| `semantic_memory.beliefs.last_reinforced` | A-MEM memory evolution | Recency tracking — a belief reinforced across 50 episodes is more central |
| `semantic_memory.relationships` | GenAgents observation nodes | Who they admire, reference, disagree with — intellectual network mapping |
| `episodic_memory.emotional_peaks` | Evolving Agents emotion module | Captures *how* someone reacts, not just their position |
| `reflections.expert_lens` | Stanford GenAgents 1000 expert reflection | Different expert perspectives extract different insights from same content |
| `reflections.importance` | GenAgents (Smallville) tri-scoring | Enables ranked retrieval for future Chat with X |
| `contradictions.resolution` | Original design | Distinguishes genuine mind-changes from context-dependent views |
| `growth_log` | Evolving Agents character growth | Tracks worldview evolution — key benefit of chronological replay |

### What was deliberately excluded

- **Embedding vectors per memory node** — Belong at DB column level (pgvector), not inside JSONB
- **Demographic data** — Already in the `guests` table
- **Procedural memory** — Not relevant for podcast persona agents (they don't take actions)
- **Short-term/sensory memory** — Only relevant for interactive chat sessions, not stored persona

## Pipeline Architecture

Four discrete scripts, each idempotent and resumable.

### Stage 1: `extract_embeddings.py`

**Input:** Processed episodes with diarized segments
**Output:** Rows in `speaker_embeddings` table

- Reads NeMo's intermediate output files (speaker embeddings computed during diarization)
- Extracts per-speaker embeddings from `speaker_outputs/embeddings/`
- Stores one embedding per speaker per episode
- Skips episodes already extracted (idempotent check on `episode_id + speaker_label`)

### Stage 2: `map_speakers.py`

**Input:** `speaker_embeddings` table + `episode_guests` junction
**Output:** `speaker_embeddings.person_id` populated, `people` rows created

- **Bootstrap:** First run — user manually confirms which speaker is the host in the first episode. That embedding becomes the host anchor.
- **Auto-map:** Cosine similarity against host anchor identifies the host in subsequent episodes. Remaining speaker matched to guest via `episode_guests`.
- **Confidence threshold:** Below 0.7 similarity → flag for manual review.
- **Anchor refinement:** Average host embeddings across confirmed episodes to improve anchor over time.
- Creates `people` rows and links to `guests.person_id` as needed.

### Stage 3: `build_memory.py`

**Input:** Mapped segments + existing `agent_memories`
**Output:** Updated `agent_memories` rows

- Queries episodes chronologically (`published_at ASC`) for a channel
- For each episode, loads segments in position order
- For each segment:
  1. **Triage** — GLM 4.7 call: "Is this substantive or filler?" Skip filler (<5 words, "yeah", "exactly", etc.)
  2. **Context window** — Assemble: person's current memory + last 5 turns of conversation context + current turn
  3. **Synthesize** — GLM 4.7 merges new turn into existing memory JSON (merge, not append)
  4. **Save** — Write updated memory, increment `memory_version`, update `last_episode_id` and `last_position`
- **Resumption:** Reads `last_episode_id` + `last_position` on restart
- **Rate:** ~200 substantive turns per 1hr episode x 2 LLM calls (triage + merge) = ~400 calls/episode

### Stage 4: `export_memory.py` (optional)

- Dumps `agent_memories` to JSON files in `data/agents/{person_slug}.json`
- For inspection, debugging, and version control

### Runner

```bash
python run_pipeline.py --channel diary-of-a-ceo
python run_pipeline.py --channel diary-of-a-ceo --stage build_memory
python run_pipeline.py --channel diary-of-a-ceo --resume
```

## Frontend — Character Memory Page

Route: `/{channel}/people/{slug}`

### Layout

- **Header** — Photo, name, role (host/guest), episode count. Data from `guests` + `people`.
- **Persona Card** — Communication style, personality traits, expertise domains. Visual badges/tags.
- **Beliefs & Frameworks** — Grouped by topic, showing confidence and source episode. Expandable cards.
- **Reflections** — Top insights ranked by importance. Tagged with expert lens. Linked to source episodes.
- **Growth Timeline** — Vertical timeline of belief/style evolution from `growth_log`. Each node links to the episode.
- **Contradictions** — Earlier vs. later stance with resolution status.
- **Episode Appearances** — Per-episode summaries from `episodic_memory`.

All server-rendered from `agent_memories.memory` JSONB. No client-side LLM calls.

## Error Handling & Edge Cases

| Scenario | Mitigation |
|----------|-----------|
| Filler triage false positives | Err on processing — only skip turns <5 words or clear filler |
| Memory corruption from bad LLM merge | `memory_version` counter + snapshot previous state before merge |
| Speaker mapping errors | Confidence threshold (0.7). Below threshold → manual review flag |
| Multi-guest episodes (3+ speakers) | Fall back to embedding-based matching against all known guests |
| Missing NeMo embeddings for old episodes | Re-run diarization or separate embedding extraction pass |

## Testing Strategy

- **Memory merge quality** — Pipeline on 5 episodes for one person, manually inspect memory JSON
- **Speaker mapping accuracy** — Extract embeddings for 10 episodes, verify host identification
- **Idempotency** — Run `build_memory.py` twice on same episodes, verify identical output
- **Resumption** — Run on 3 episodes, kill mid-way, restart. Verify checkpoint recovery without duplication

## Future Work (Not In Scope)

- **Chat with X** — Interactive conversation using agent memory + RAG over segments. OpenRouter BYOK.
- **Agent-to-Agent conversations** — Simulate discussions between two people on topics they never directly discussed.
- **MeiliSearch integration** — Index agent memories for full-text search across people.

## References

- [Generative Agent Simulations of 1,000 People](https://arxiv.org/abs/2411.10109) — Expert reflections, interview-based persona construction
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) — Zettelkasten-style linked memory evolution
- [Evolving Agents](https://arxiv.org/html/2404.02718v1) — Character growth tracking, emotion module, Big Five personality
- [Cognitive Memory in LLMs](https://arxiv.org/html/2504.02441v1) — Episodic/semantic/procedural memory taxonomy
- [Generative Agents: Interactive Simulacra](https://arxiv.org/abs/2304.03442) — Memory stream, reflection, tri-scoring retrieval
- [CoALA: Cognitive Architectures for Language Agents](https://arxiv.org/pdf/2309.02427) — Formal memory type taxonomy
