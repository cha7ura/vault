# Podcast Vault — Data Pipeline Design Spec

## Overview

A 3-stage batch pipeline that processes diarized podcast transcripts into a knowledge graph and enriched person profiles. Takes raw Whisper+NeMo segments from Supabase, cleans them against YouTube captions with human review, extracts structured knowledge via Graphiti into Neo4j, and enriches entities via web search.

Target: 484 Diary of a CEO (DOAC) episodes. Designed to scale to additional channels (Modern Wisdom, Lex Fridman, Huberman Lab).

## Stack

| Component | Technology | Where |
|---|---|---|
| LLM | Gemma 4 E4B-it (Q4_K_M) | Local, Ollama |
| Knowledge graph | Neo4j AuraDB Free | Cloud |
| Graph framework | Graphiti (forked) | Git submodule at `vendor/graphiti/` |
| Primary storage | Supabase (Postgres) | Cloud |
| Web search | SearXNG | Local, Docker |
| Review UI | Next.js dashboard app | Local, port 3001 |
| Pipeline runner | Python scripts | Local |

### LLM Model Selection

Gemma 4 E4B-it at Q4_K_M quantization. 8B total params, 4.5B effective (dense, not MoE). Fits in 6GB VRAM (GTX 1660 Ti). 128K context window enables 15-20 min transcript chunks instead of 5 min. Optional high-quality mode: Gemma 4 26B-A4B-it (MoE, 3.8B active) with CPU offload for slower but better extraction.

### Why Neo4j over FalkorDB

Both are supported by Graphiti. Neo4j AuraDB Free has no idle deletion policy (FalkorDB deletes after 7 days idle). Neo4j has built-in Bloom visualization for graph exploration. Most tested Graphiti backend. Cloud-hosted for multi-device access.

### Why SearXNG over DuckDuckGo

Self-hosted, no rate limits. Aggregates 250+ search engines including PubMed and Google Scholar in one query. DDG is an unofficial scraper that can break. SearXNG runs as a single Docker container (~100MB RAM).

### Why Not LangGraph

The pipeline is a batch DAG, not a multi-turn agent with reasoning loops. LangGraph's value is in cycles, tool-calling agents, and complex conditional routing. The data quality steps (intro detection, YT caption cross-referencing, speaker mapping) involve simple branching, not agent-style routing. Graphiti IS the knowledge agent. Existing `scripts/agents/` pipeline already has a 4-stage runner with checkpointing.

---

## Data Flow

```
Supabase segments (Whisper+NeMo) + YT captions (yt_segments)
    │
    ▼
STAGE 1 — PREP
    Detect intro │ Identify people │ Map speakers
    │
    ▼
STAGE 2 — CLEAN
    Merge text │ Assign names │ Validate │ Human review UI
    │
    ▼
STAGE 3 — EXTRACT + ENRICH
    Triage │ Chunk │ Graphiti ingest → Neo4j
    Show notes │ Web search │ Profile hydration │ Persona extraction
```

---

## Stage 1 — PREP

Per-episode. No LLM required for most episodes.

### 1a. Detect Intro End-Point

DOAC episodes follow: intro music → subscribe prompt → actual conversation.

**Heuristic first:** Scan first 60 segments for anchor phrases: "subscribe", "welcome to", "my guest today", "let's get into it", "tell me about". Last anchor position = intro end.

**LLM fallback:** If no anchors found, send first 5 minutes to Gemma 4: "Where does the actual interview begin? Return the segment position number."

Store `intro_end_position` on the episode row.

### 1b. Identify People

Sources: `episode_guests` table, YouTube description text, transcript speaker count.

1. Parse guest name from description (regex + LLM if ambiguous)
2. Cross-reference with `guests`/`people` tables
3. `get_or_create_person()` for new guests (already implemented in `map_speakers.py`)

### 1c. Map Speakers

Map SPEAKER_00/01/etc to real names using voice fingerprinting.

Uses existing pipeline: `extract_embeddings.py` (TitaNet 192-dim embeddings) + `map_speakers.py` (cosine similarity against host anchor). Host anchor refreshes every 10 mapped episodes.

For 2-speaker episodes with 1 known guest: other speaker = guest. Multi-speaker: cosine similarity ranking.

**Output:**
```python
PrepResult = {
    "episode_id": str,
    "intro_end_position": int,
    "speakers": {
        "SPEAKER_00": {"person_id": str, "name": str, "role": "host"|"guest"},
        "SPEAKER_01": {"person_id": str, "name": str, "role": "host"|"guest"},
    }
}
```

---

## Stage 2 — CLEAN

Per-episode. Produces named, accurate transcript segments.

### 2a. Text Accuracy — Whisper + YT Caption Merge

Both sources already time-aligned in Supabase (`segments` and `yt_segments` tables, sliced to same time windows by `fetch_yt_captions.py`).

Per segment:
1. Word-level diff between Whisper text and YT caption text
2. Resolution rules (no LLM):
   - Proper nouns (detected via capitalization diff or NER mismatch): prefer YT captions (YouTube has entity recognition in ASR)
   - Filler words / timing: prefer Whisper (better word-level timestamps)
   - Similar words (e.g., "neuroplasticity" vs "neuro plasticity"): keep Whisper
   - Completely different words at same timestamp: keep Whisper (had actual audio)
3. Output: `clean_text` + `text_confidence` score per segment

### 2b. Speaker Assignment

Apply speaker map from Stage 1. Set `person_id` FK on each segment. Trim segments before `intro_end_position`.

### 2c. Dialogue Validation

Sanity checks (no LLM):
- Speaker turn ratio: flag if one speaker > 95% of turns
- Empty segments: flag after merge
- Speaker continuity: flag if same speaker has 20+ consecutive turns

Store `quality_issues` JSON array on episode if validation fails.

### 2d. Review UI

Dashboard app (`/review/{youtube_id}`) for human review of flagged segments.

**Internal review (pre-publish):**
- Side-by-side diff: Whisper vs YT caption with word-level highlighting
- Editable merged text field
- YouTube player synced to segment for listening
- Keyboard shortcuts: Enter=accept, arrows=navigate
- Only surfaces segments where `text_confidence < 0.85`
- Bulk "accept all auto-merge" for high-confidence segments

**Public flagging (post-publish):**
- "Flag error" button on frontend transcript views
- Creates entry in `segment_corrections` table
- Admin review queue in dashboard

**Data model:**
```sql
segment_corrections (
    id UUID PRIMARY KEY,
    segment_id UUID REFERENCES segments(id),
    episode_id UUID REFERENCES episodes(id),
    source TEXT,            -- 'auto_merge_review', 'public_flag', 'admin'
    original_text TEXT,
    suggested_text TEXT,    -- nullable for public flags
    reason TEXT,            -- nullable
    status TEXT,            -- 'pending', 'accepted', 'rejected'
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
)
```

When a correction is accepted: update `segments.clean_text`, mark episode `needs_reprocessing`, re-run Stage 3 for that episode only.

**Output:** Clean segments in Supabase with `clean_text`, `person_id`, `text_confidence`.

---

## Stage 3 — EXTRACT + ENRICH

Two phases: per-episode extraction, then batch enrichment.

### Phase A: Per-Episode Extraction

#### 3a. Triage Filler

Two-pass filter:
1. Heuristic: skip turns <=5 words matching filler phrases. Free.
2. LLM: for ambiguous 6-15 word turns, ask Gemma 4: "SUBSTANTIVE or FILLER?" Turns >15 words always substantive.

#### 3b. Chunk Transcript

15-20 minute windows with 2 minute overlap. ~6-8 chunks per episode. Leverages Gemma 4 E4B's 128K context for broader topic awareness.

Uses `podcast_vault/extract.py` `chunk_transcript()` with updated parameters.

#### 3c. Graphiti Ingestion

Each chunk's substantive turns feed into Graphiti `add_episode()`. Graphiti handles:

- **Entity extraction**: Guest, Topic, Study, Book, Product, Protocol (from `podcast_vault/entity_types.py`)
- **Edge extraction**: MakesClaim, DescribesProtocol, ReferencesStudy, RecommendsBook, RecommendsProduct, AppearsOn, RelatesTo, SupportsProtocol (from `podcast_vault/edge_types.py`)
- **Entity resolution**: same guest/topic across episodes merged
- **Contradiction detection**: superseded claims get `expired_at`
- **Temporal tracking**: edge versioning shows belief evolution

Custom extraction instructions from `podcast_vault/ingest.py` guide the LLM on entity/relationship rules.

#### 3d. Show Notes URL Parsing

Parse YouTube description using `podcast_vault/show_notes.py`. Classify URLs:
- `study`: pubmed, doi.org, nature.com, etc. → fetch metadata via CrossRef/PubMed APIs
- `product`: amazon, sponsor links → attach to Product nodes
- `guest_bio`: wikipedia, socials → feed into profile hydration
- `book`: amazon book ASINs → fetch book metadata

#### 3e. Checkpoint

After each episode: set `episode.knowledge_processed_at = NOW()`. Pipeline skips on resume.

### Phase B: Batch Enrichment (after all episodes)

#### 3f. Web Search Enrichment

Query Neo4j for unenriched entities (using `enrich.py` Cypher queries). For each:

1. SearXNG search with engine selection:
   - Studies: `engines=pubmed,google_scholar,semantic_scholar`
   - Books: `engines=google,goodreads`
   - Guests: `engines=google,wikipedia`
2. Fetch top result page
3. Gemma 4 E4B extracts structured fields
4. Update Neo4j node attributes

Priority order: guests (most visible) → studies → books → protocols.

#### 3g. Profile Hydration

Per person in `people` table:
1. Web search → extract bio, photo, socials, credentials, Wikipedia summary
2. Write to `people` table in Supabase (frontend display)
3. Update Guest node in Neo4j (graph queries)
4. Set `people.hydrated_at = NOW()`

Structured output:
```python
{
    "name": str,
    "bio": str,
    "credentials": str,
    "photo_url": str,
    "socials": {"twitter": str, "instagram": str, "youtube": str, "website": str},
    "books_authored": list,
    "companies": list,
    "wikipedia_summary": str,
    "expertise_domains": list,
}
```

#### 3h. Persona Extraction (periodic)

Lightweight LLM pass every ~10 episodes per person. Extracts:
- Communication style: tone, formality, signature phrases, speech patterns
- Personality traits: Big Five dimensions

Stored as `persona_json` column on `people` table. Not per-turn — a periodic summary that evolves as more episodes are processed.

Used for future "chat with X" feature system prompt alongside Graphiti knowledge queries.

---

## Re-processing Flow

When a segment correction is accepted (from review UI or public flag):

1. Update `segments.clean_text`
2. Set `episode.needs_reprocessing = true`
3. Re-run Stage 3 for affected episode only:
   - Graphiti: update/replace episodes for that podcast episode
   - Enrichment: only if new entities were extracted
4. Clear `needs_reprocessing` flag

---

## Estimated Throughput

| Step | Per episode | 484 episodes |
|---|---|---|
| Stage 1 (prep) | ~5s (mostly heuristic) | ~40 min |
| Stage 2 (clean) | ~10s (word diff, no LLM) | ~80 min |
| Stage 2 review | Manual — ~50 flagged segments/ep | Ongoing |
| Stage 3a triage | ~30s | ~4 hours |
| Stage 3b-c extraction + Graphiti | ~5 min (6-8 chunks × ~3s LLM + ingest) | ~40 hours |
| Stage 3f-h enrichment | ~3000 entities × ~5s each | ~4 hours |
| Persona extraction | ~500 people × ~30s | ~4 hours |

Total automated: ~50 hours. Designed to run overnight across multiple nights, with checkpoint/resume.

---

## File Structure

```
scripts/agents/
    config.py              # Shared config (Supabase, Ollama, thresholds)
    prompts.py             # LLM prompt templates
    run_pipeline.py        # Orchestrator (updated for 3 stages)
    stage1_prep.py         # Intro detection, people ID, speaker mapping
    stage2_clean.py        # Text merge, speaker assignment, validation
    stage3_extract.py      # Triage, chunking, Graphiti ingest, enrichment

vendor/graphiti/           # Git submodule (forked repo)
    podcast_vault/
        entity_types.py    # 7 Pydantic entity models
        edge_types.py      # 8 edge models + EDGE_TYPE_MAP
        extract.py         # Transcript chunking + extraction prompt
        show_notes.py      # URL extraction and classification
        ingest.py          # Graphiti ingestion config
        enrich.py          # Research enrichment data structures
        queries.py         # 6 Cypher query functions

dashboard/
    app/review/[episodeId]/page.tsx    # Review UI
    app/api/corrections/route.ts        # Public flag endpoint
```

---

## Schema Changes Required

New columns on existing tables:
```sql
ALTER TABLE segments ADD COLUMN clean_text TEXT;
ALTER TABLE segments ADD COLUMN text_confidence FLOAT;
ALTER TABLE segments ADD COLUMN person_id UUID REFERENCES people(id);

ALTER TABLE episodes ADD COLUMN intro_end_position INT;
ALTER TABLE episodes ADD COLUMN knowledge_processed_at TIMESTAMP;
ALTER TABLE episodes ADD COLUMN needs_reprocessing BOOLEAN DEFAULT false;

ALTER TABLE people ADD COLUMN persona_json JSONB;
```

New table:
```sql
CREATE TABLE segment_corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    segment_id UUID REFERENCES segments(id),
    episode_id UUID REFERENCES episodes(id),
    source TEXT NOT NULL,
    original_text TEXT,
    suggested_text TEXT,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Dependencies

Python packages (add to pipeline requirements):
```
graphiti-core          # from vendor submodule
duckduckgo-search      # fallback if SearXNG unavailable
neo4j                  # Neo4j Python driver
numpy                  # embeddings math
requests               # SearXNG API, structured API calls
python-dotenv          # env config
supabase               # Supabase client
```

Infrastructure:
```
ollama                 # Local LLM server (gemma4:e4b-it-q4)
docker                 # SearXNG container
```

External services:
```
Neo4j AuraDB Free      # Knowledge graph (cloud)
Supabase               # Primary storage (cloud)
```
