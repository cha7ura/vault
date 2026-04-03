# Podcast Vault Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-stage batch pipeline that processes 246 diarized DOAC episodes into a Graphiti knowledge graph (Neo4j) with clean, speaker-attributed transcripts and enriched person profiles.

**Architecture:** Python batch scripts in `scripts/agents/` process episodes through PREP → CLEAN → EXTRACT+ENRICH. Stage 1 uses heuristics to detect intros and map speakers. Stage 2 merges Whisper text with YouTube captions and flags disagreements for human review via a dashboard UI. Stage 3 triages filler, chunks transcripts, ingests into Graphiti/Neo4j, and enriches entities via SearXNG web search.

**Tech Stack:** Python 3.11+, Gemma 4 E4B-it via Ollama, Neo4j AuraDB Free, Graphiti (git submodule), Supabase, SearXNG (Docker), Next.js 15 dashboard.

**Spec:** `docs/superpowers/specs/2026-04-03-pipeline-design.md`

---

## File Map

### New files to create

```
scripts/agents/stage1_prep.py          # Intro detection, people ID, speaker mapping
scripts/agents/stage2_clean.py         # Text merge, speaker assignment, validation
scripts/agents/stage3_extract.py       # Triage, chunking, Graphiti ingest
scripts/agents/stage3_enrich.py        # Web search enrichment, profile hydration, persona
scripts/agents/llm.py                  # Shared Ollama LLM client
scripts/agents/search.py              # SearXNG search client
tests/agents/__init__.py
tests/agents/test_stage1_prep.py
tests/agents/test_stage2_clean.py
tests/agents/test_stage3_extract.py
tests/agents/test_stage3_enrich.py
tests/agents/test_llm.py
tests/agents/test_search.py
supabase/migrations/008_pipeline_columns.sql
dashboard/app/review/[episodeId]/page.tsx
dashboard/app/api/corrections/route.ts
dashboard/app/api/review/[episodeId]/route.ts
dashboard/components/review-segment.tsx
docker-compose.yml                     # SearXNG service (vault root)
requirements-pipeline.txt              # Python deps for pipeline
```

### Existing files to modify

```
scripts/agents/config.py               # Add Neo4j, SearXNG, Ollama model config
scripts/agents/prompts.py              # Add intro detection, triage, persona prompts
scripts/agents/run_pipeline.py         # Rewrite for 3-stage architecture
```

### Vendor submodule (existing, already built)

```
vendor/graphiti/                        # Git submodule pointing to cha7ura/graphiti fork
  podcast_vault/entity_types.py        # 7 entity models (no changes)
  podcast_vault/edge_types.py          # 8 edge models (no changes)
  podcast_vault/extract.py             # chunk_transcript (update chunk_duration param)
  podcast_vault/ingest.py              # Graphiti config (no changes)
  podcast_vault/show_notes.py          # URL parser (no changes)
  podcast_vault/enrich.py              # Enrichment structures (no changes)
  podcast_vault/queries.py             # Cypher queries (no changes)
```

---

## Task 1: Database Migration + Python Dependencies

**Files:**
- Create: `supabase/migrations/008_pipeline_columns.sql`
- Create: `requirements-pipeline.txt`

- [ ] **Step 1: Write the migration**

```sql
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
```

- [ ] **Step 2: Apply the migration**

Run: `psql "$DATABASE_URL" -f supabase/migrations/008_pipeline_columns.sql`

Or via Supabase dashboard SQL editor — paste the SQL and execute.

- [ ] **Step 3: Create requirements-pipeline.txt**

```
# Pipeline dependencies
graphiti-core @ file:vendor/graphiti
neo4j>=5.0
numpy>=1.24
requests>=2.28
python-dotenv>=1.0
supabase>=2.0
duckduckgo-search>=6.0
```

- [ ] **Step 4: Install dependencies**

Run: `pip install -r requirements-pipeline.txt`

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/008_pipeline_columns.sql requirements-pipeline.txt
git commit -m "feat: add pipeline migration and Python dependencies"
```

---

## Task 2: Add Graphiti as Git Submodule

**Files:**
- Create: `vendor/graphiti/` (submodule)

- [ ] **Step 1: Add the submodule**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
git submodule add https://github.com/cha7ura/graphiti.git vendor/graphiti
cd vendor/graphiti
git checkout main  # or the branch with podcast_vault/
cd ../..
```

- [ ] **Step 2: Verify podcast_vault module is accessible**

```bash
python3 -c "
import sys; sys.path.insert(0, 'vendor/graphiti')
from podcast_vault.entity_types import ENTITY_TYPES
from podcast_vault.edge_types import EDGE_TYPES, EDGE_TYPE_MAP
from podcast_vault.extract import chunk_transcript, EpisodeTranscript
from podcast_vault.ingest import GRAPHITI_EXTRACTION_INSTRUCTIONS
print(f'Entity types: {list(ENTITY_TYPES.keys())}')
print(f'Edge types: {list(EDGE_TYPES.keys())}')
print('All imports OK')
"
```

Expected: prints entity types (Guest, Podcast, Topic, Study, Book, Product, Protocol), edge types, "All imports OK"

- [ ] **Step 3: Commit**

```bash
git add .gitmodules vendor/graphiti
git commit -m "feat: add graphiti fork as git submodule"
```

---

## Task 3: Update Config + Shared LLM Client

**Files:**
- Modify: `scripts/agents/config.py`
- Create: `scripts/agents/llm.py`
- Create: `scripts/agents/search.py`
- Create: `tests/agents/__init__.py`
- Create: `tests/agents/test_llm.py`
- Create: `tests/agents/test_search.py`

- [ ] **Step 1: Write test for LLM client**

```python
# tests/agents/test_llm.py
import json
from unittest.mock import patch, MagicMock
from scripts.agents.llm import llm_call, llm_json_call


def test_llm_call_returns_response_text():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "  SUBSTANTIVE  "}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp) as mock_post:
        result = llm_call("Is this filler?")

    assert result == "SUBSTANTIVE"
    call_args = mock_post.call_args
    assert "api/generate" in call_args[0][0]


def test_llm_json_call_strips_markdown_fencing():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": '```json\n{"key": "value"}\n```'}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp):
        result = llm_json_call("Extract JSON")

    assert result == {"key": "value"}


def test_llm_json_call_returns_none_on_bad_json():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "not json at all"}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp):
        result = llm_json_call("Extract JSON")

    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_llm.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.agents.llm'`

- [ ] **Step 3: Create `tests/agents/__init__.py`**

```python
# empty
```

- [ ] **Step 4: Implement LLM client**

```python
# scripts/agents/llm.py
"""Shared Ollama LLM client for pipeline stages."""
import json
import re

import requests

from scripts.agents.config import OLLAMA_BASE_URL, OLLAMA_MODEL


def llm_call(prompt: str, temperature: float = 0.3) -> str:
    """Send a prompt to Ollama and return the response text."""
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


def llm_json_call(prompt: str, temperature: float = 0.1) -> dict | None:
    """Send a prompt and parse the response as JSON."""
    text = llm_call(prompt, temperature=temperature)
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/agents/test_llm.py -v`

Expected: 3 passed

- [ ] **Step 6: Write test for SearXNG search client**

```python
# tests/agents/test_search.py
from unittest.mock import patch, MagicMock
from scripts.agents.search import searxng_search


def test_searxng_search_returns_results():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"title": "Dr. Huberman", "url": "https://example.com", "content": "Neuroscientist"},
            {"title": "Huberman Lab", "url": "https://example2.com", "content": "Podcast"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.search.requests.get", return_value=mock_resp):
        results = searxng_search("Andrew Huberman", engines="google,wikipedia")

    assert len(results) == 2
    assert results[0]["title"] == "Dr. Huberman"


def test_searxng_search_returns_empty_on_failure():
    with patch("scripts.agents.search.requests.get", side_effect=Exception("timeout")):
        results = searxng_search("anything")

    assert results == []
```

- [ ] **Step 7: Implement SearXNG search client**

```python
# scripts/agents/search.py
"""SearXNG search client for entity enrichment."""
import requests

from scripts.agents.config import SEARXNG_URL


def searxng_search(
    query: str,
    engines: str = "google",
    max_results: int = 5,
) -> list[dict]:
    """Search via local SearXNG instance. Returns list of {title, url, content}."""
    try:
        resp = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "engines": engines,
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[:max_results]
    except Exception:
        return []
```

- [ ] **Step 8: Run test to verify it passes**

Run: `python -m pytest tests/agents/test_search.py -v`

Expected: 2 passed

- [ ] **Step 9: Update config.py**

```python
# scripts/agents/config.py
"""Shared configuration for pipeline."""
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env.local")

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# LLM config
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")

# Neo4j config
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

# SearXNG config
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")

# Pipeline config
FILLER_MAX_WORDS = 5
CONTEXT_WINDOW_TURNS = 5
BATCH_INSERT_SIZE = 200
TEXT_CONFIDENCE_THRESHOLD = 0.85
CHUNK_DURATION = 1200.0  # 20 minutes in seconds
CHUNK_OVERLAP = 120.0    # 2 minutes overlap
PERSONA_EVERY_N_EPISODES = 10

# Host detection
DOAC_HOST_NAME = "Steven Bartlett"
DOAC_CHANNEL_SLUG = "the-diary-of-a-ceo"
HOST_ANCHOR_PHRASES = [
    "subscribe", "welcome to", "diary of a ceo", "my guest today",
    "let's get into it", "tell me about", "without further ado",
]

FILLER_PHRASES = {
    "yeah", "yes", "no", "right", "exactly", "sure", "okay", "ok",
    "mm-hmm", "mhm", "uh-huh", "hmm", "um", "uh", "ah",
}


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)
```

- [ ] **Step 10: Commit**

```bash
git add scripts/agents/config.py scripts/agents/llm.py scripts/agents/search.py \
       tests/agents/__init__.py tests/agents/test_llm.py tests/agents/test_search.py
git commit -m "feat: add LLM client, SearXNG client, and updated config"
```

---

## Task 4: Stage 1 — PREP (Intro Detection + People ID + Speaker Mapping)

**Files:**
- Create: `scripts/agents/stage1_prep.py`
- Create: `tests/agents/test_stage1_prep.py`
- Modify: `scripts/agents/prompts.py`

- [ ] **Step 1: Write tests for Stage 1**

```python
# tests/agents/test_stage1_prep.py
from scripts.agents.stage1_prep import (
    detect_intro_end,
    identify_host_speaker,
    parse_guest_from_description,
)


def test_detect_intro_end_finds_subscribe():
    segments = [
        {"position": 0, "text": "Quick one, the Diary of a CEO"},
        {"position": 1, "text": "please subscribe to the channel"},
        {"position": 2, "text": "My guest today is an incredible person"},
        {"position": 3, "text": "So tell me about your childhood"},
    ]
    result = detect_intro_end(segments)
    assert result == 2  # last anchor phrase at position 2


def test_detect_intro_end_returns_zero_when_no_anchors():
    segments = [
        {"position": 0, "text": "So the thing about dopamine is"},
        {"position": 1, "text": "it regulates reward pathways"},
    ]
    result = detect_intro_end(segments)
    assert result == 0


def test_identify_host_speaker_by_anchor_phrases():
    segments = [
        {"position": 0, "speaker": "Speaker 0", "text": "Welcome to the diary of a CEO"},
        {"position": 1, "speaker": "Speaker 1", "text": "Thanks for having me"},
        {"position": 2, "speaker": "Speaker 0", "text": "Please subscribe"},
    ]
    host_label = identify_host_speaker(segments)
    assert host_label == "Speaker 0"


def test_identify_host_speaker_falls_back_to_first_speaker():
    segments = [
        {"position": 0, "speaker": "Speaker 0", "text": "Let's talk about health"},
        {"position": 1, "speaker": "Speaker 1", "text": "Sure thing"},
    ]
    host_label = identify_host_speaker(segments)
    assert host_label == "Speaker 0"


def test_parse_guest_from_description_finds_name():
    desc = "My guest today is Dr. Andrew Huberman, a neuroscientist at Stanford."
    result = parse_guest_from_description(desc)
    assert result is not None
    assert "Huberman" in result


def test_parse_guest_from_description_returns_none_for_empty():
    assert parse_guest_from_description("") is None
    assert parse_guest_from_description(None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_stage1_prep.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Add prompts**

Add to `scripts/agents/prompts.py`:

```python
INTRO_DETECTION_PROMPT = """You are analyzing the start of a podcast episode transcript. Determine where the actual interview/conversation begins (after any intro music, sponsor reads, subscribe prompts).

Transcript (first segments):
{segments_text}

Return ONLY the position number (integer) of the first segment where the real conversation starts. If the conversation starts from the very beginning, return 0."""

GUEST_EXTRACTION_PROMPT = """Extract the guest's full name from this podcast episode description. Return ONLY the name, nothing else. If you cannot determine the guest name, return "UNKNOWN".

Description:
{description}"""
```

- [ ] **Step 4: Implement stage1_prep.py**

```python
# scripts/agents/stage1_prep.py
"""Stage 1 — PREP: Intro detection, people identification, speaker mapping."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    get_supabase,
    HOST_ANCHOR_PHRASES,
    DOAC_HOST_NAME,
)


class SpeakerInfo(TypedDict):
    person_id: str | None
    name: str
    role: str  # "host" or "guest"


class PrepResult(TypedDict):
    episode_id: str
    intro_end_position: int
    speakers: dict[str, SpeakerInfo]


# ---------------------------------------------------------------------------
# 1a. Intro Detection
# ---------------------------------------------------------------------------

def detect_intro_end(segments: list[dict], max_scan: int = 60) -> int:
    """Find the segment position where the real conversation starts.

    Scans the first *max_scan* segments for anchor phrases.
    Returns the position of the last anchor phrase found, or 0 if none.
    """
    last_anchor_pos = 0
    for seg in segments[:max_scan]:
        text_lower = seg["text"].lower()
        for phrase in HOST_ANCHOR_PHRASES:
            if phrase in text_lower:
                last_anchor_pos = seg["position"]
                break
    return last_anchor_pos


# ---------------------------------------------------------------------------
# 1b. Identify People
# ---------------------------------------------------------------------------

GUEST_PATTERNS = [
    r"(?:my guest (?:today )?is|today(?:'s| is) guest[: ]+)(.+?)(?:\.|,|\n|$)",
    r"(?:joined by|speaking with|talking to|interviewing)\s+(.+?)(?:\.|,|\n|$)",
    r"(?:Guest|Featuring)[:\s]+(.+?)(?:\.|,|\n|$)",
]


def parse_guest_from_description(description: str | None) -> str | None:
    """Extract guest name from YouTube episode description using regex."""
    if not description:
        return None

    for pattern in GUEST_PATTERNS:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Clean up: remove trailing titles/roles after comma
            name = re.split(r",\s*(?:a |the |an )", name, maxsplit=1)[0].strip()
            if 2 <= len(name.split()) <= 5:  # reasonable name length
                return name

    return None


def get_or_create_person(sb, name: str, photo_url: str | None = None) -> dict:
    """Find a person by name slug, or create one. Returns the person row."""
    slug = re.sub(r"[^\w\s-]", "", name.lower().strip())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")

    rows = sb.table("people").select("*").eq("slug", slug).limit(1).execute().data
    if rows:
        return rows[0]

    insert_data = {"name": name, "slug": slug}
    if photo_url:
        insert_data["photo_url"] = photo_url

    result = sb.table("people").insert(insert_data).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# 1c. Speaker Mapping
# ---------------------------------------------------------------------------

def identify_host_speaker(segments: list[dict], max_scan: int = 30) -> str:
    """Identify which speaker label is the host using anchor phrases.

    Falls back to the first speaker if no anchors found.
    """
    anchor_counts: dict[str, int] = {}

    for seg in segments[:max_scan]:
        text_lower = seg["text"].lower()
        speaker = seg["speaker"]
        for phrase in HOST_ANCHOR_PHRASES:
            if phrase in text_lower:
                anchor_counts[speaker] = anchor_counts.get(speaker, 0) + 1

    if anchor_counts:
        return max(anchor_counts, key=anchor_counts.get)

    # Fallback: first speaker in the transcript
    if segments:
        return segments[0]["speaker"]
    return "Speaker 0"


# ---------------------------------------------------------------------------
# Main: process one episode
# ---------------------------------------------------------------------------

def prep_episode(episode_id: str) -> PrepResult:
    """Run Stage 1 for a single episode. Returns PrepResult."""
    sb = get_supabase()

    # Fetch episode metadata
    episode = sb.table("episodes").select("*").eq("id", episode_id).single().execute().data

    # Fetch first 60 segments ordered by position
    segments = (
        sb.table("segments")
        .select("position, speaker, text, start_time, end_time")
        .eq("episode_id", episode_id)
        .order("position")
        .limit(60)
        .execute()
    ).data

    if not segments:
        return PrepResult(
            episode_id=episode_id,
            intro_end_position=0,
            speakers={},
        )

    # 1a. Detect intro
    intro_end = detect_intro_end(segments)

    # 1b. Identify guest
    guest_name = None

    # Try episode_guests table first
    guest_rows = (
        sb.table("episode_guests")
        .select("guest_id, guests(name, photo_url)")
        .eq("episode_id", episode_id)
        .execute()
    ).data
    if guest_rows:
        guest_name = guest_rows[0]["guests"]["name"]

    # Fallback to description parsing
    if not guest_name:
        guest_name = parse_guest_from_description(episode.get("description"))

    # 1c. Map speakers
    host_label = identify_host_speaker(segments)
    all_speakers = sorted(set(seg["speaker"] for seg in segments))
    guest_labels = [s for s in all_speakers if s != host_label]

    # Create/find people
    host_person = get_or_create_person(sb, DOAC_HOST_NAME)
    speakers: dict[str, SpeakerInfo] = {
        host_label: SpeakerInfo(
            person_id=host_person["id"], name=DOAC_HOST_NAME, role="host"
        ),
    }

    if guest_labels and guest_name:
        guest_person = get_or_create_person(sb, guest_name)
        for label in guest_labels:
            speakers[label] = SpeakerInfo(
                person_id=guest_person["id"], name=guest_name, role="guest"
            )
    elif guest_labels:
        for label in guest_labels:
            speakers[label] = SpeakerInfo(
                person_id=None, name="Unknown Guest", role="guest"
            )

    # Save intro_end_position to episode
    sb.table("episodes").update(
        {"intro_end_position": intro_end}
    ).eq("id", episode_id).execute()

    return PrepResult(
        episode_id=episode_id,
        intro_end_position=intro_end,
        speakers=speakers,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/agents/test_stage1_prep.py -v`

Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/agents/stage1_prep.py scripts/agents/prompts.py \
       tests/agents/test_stage1_prep.py
git commit -m "feat: implement Stage 1 PREP — intro detection, people ID, speaker mapping"
```

---

## Task 5: Stage 2 — CLEAN (Text Merge + Speaker Assignment + Validation)

**Files:**
- Create: `scripts/agents/stage2_clean.py`
- Create: `tests/agents/test_stage2_clean.py`

- [ ] **Step 1: Write tests for text merge and validation**

```python
# tests/agents/test_stage2_clean.py
from scripts.agents.stage2_clean import (
    merge_segment_text,
    detect_time_gaps,
    validate_dialogue,
    compute_text_confidence,
)


def test_merge_when_both_agree():
    result = merge_segment_text(
        whisper_text="Cold exposure activates brown fat",
        yt_text="Cold exposure activates brown fat",
    )
    assert result == "Cold exposure activates brown fat"


def test_merge_prefers_yt_for_proper_nouns():
    result = merge_segment_text(
        whisper_text="doctor andrew huberman said",
        yt_text="Dr. Andrew Huberman said",
    )
    assert "Dr. Andrew Huberman" in result


def test_merge_keeps_whisper_when_completely_different():
    result = merge_segment_text(
        whisper_text="neuroplasticity is key",
        yt_text="your class to ski",  # bad YT caption
    )
    assert result == "neuroplasticity is key"


def test_detect_time_gaps_finds_yt_missing():
    whisper_segs = [
        {"position": 0, "text": "Hello there"},
        {"position": 1, "text": "Let me explain"},
    ]
    yt_segs = [
        {"position": 0, "text": "Hello there"},
        {"position": 1, "text": ""},
    ]
    gaps = detect_time_gaps(whisper_segs, yt_segs)
    assert len(gaps) == 1
    assert gaps[0]["type"] == "yt_missing"
    assert gaps[0]["position"] == 1


def test_detect_time_gaps_finds_whisper_missing():
    whisper_segs = [
        {"position": 0, "text": ""},
    ]
    yt_segs = [
        {"position": 0, "text": "Actually I think"},
    ]
    gaps = detect_time_gaps(whisper_segs, yt_segs)
    assert len(gaps) == 1
    assert gaps[0]["type"] == "whisper_missing"


def test_validate_dialogue_flags_imbalanced_speakers():
    segments = [{"speaker": "Speaker 0"}] * 98 + [{"speaker": "Speaker 1"}] * 2
    issues = validate_dialogue(segments)
    assert any("ratio" in i["type"] for i in issues)


def test_validate_dialogue_flags_long_consecutive_run():
    segments = [{"speaker": "Speaker 0"}] * 25 + [{"speaker": "Speaker 1"}] * 5
    issues = validate_dialogue(segments)
    assert any("consecutive" in i["type"] for i in issues)


def test_validate_dialogue_clean_episode():
    segments = []
    for i in range(50):
        segments.append({"speaker": "Speaker 0" if i % 2 == 0 else "Speaker 1"})
    issues = validate_dialogue(segments)
    assert issues == []


def test_compute_text_confidence_identical():
    score = compute_text_confidence("hello world", "hello world")
    assert score == 1.0


def test_compute_text_confidence_partial_match():
    score = compute_text_confidence(
        "the quick brown fox jumps",
        "the quick brown box jumps",
    )
    assert 0.5 < score < 1.0


def test_compute_text_confidence_no_yt_text():
    score = compute_text_confidence("hello world", "")
    assert score == 0.5  # can't verify, moderate confidence
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_stage2_clean.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement stage2_clean.py**

```python
# scripts/agents/stage2_clean.py
"""Stage 2 — CLEAN: Text merge, speaker assignment, dialogue validation."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_supabase, TEXT_CONFIDENCE_THRESHOLD, BATCH_INSERT_SIZE
from stage1_prep import PrepResult


class TimeGap(TypedDict):
    position: int
    type: str  # "yt_missing" or "whisper_missing"
    text: str  # the text from the source that has it


class QualityIssue(TypedDict):
    type: str
    detail: str


# ---------------------------------------------------------------------------
# 2a. Text Merge
# ---------------------------------------------------------------------------

def compute_text_confidence(whisper_text: str, yt_text: str) -> float:
    """Compute confidence score for merged text based on agreement between sources."""
    if not yt_text or not yt_text.strip():
        return 0.5  # no YT data to verify against

    w_words = whisper_text.lower().split()
    y_words = yt_text.lower().split()

    if not w_words and not y_words:
        return 1.0
    if not w_words or not y_words:
        return 0.5

    # Word-level agreement ratio
    matches = sum(1 for w in w_words if w in y_words)
    total = max(len(w_words), len(y_words))
    return round(matches / total, 3)


def _is_proper_noun_candidate(whisper_word: str, yt_word: str) -> bool:
    """Check if the YT version looks like a proper noun correction."""
    # YT is capitalized, Whisper is not
    return yt_word[0].isupper() and whisper_word[0].islower() and len(yt_word) > 2


def merge_segment_text(whisper_text: str, yt_text: str) -> str:
    """Merge Whisper transcription with YT caption text.

    Rules:
    - Proper nouns: prefer YT (has entity recognition)
    - Similar words: keep Whisper
    - Completely different: keep Whisper (had actual audio)
    """
    if not yt_text or not yt_text.strip():
        return whisper_text

    w_words = whisper_text.split()
    y_words = yt_text.split()

    if not w_words:
        return yt_text
    if not y_words:
        return whisper_text

    # If lengths differ significantly, keep Whisper
    if abs(len(w_words) - len(y_words)) > max(len(w_words), len(y_words)) * 0.5:
        return whisper_text

    # Word-by-word merge for similar-length texts
    merged = []
    for i, w_word in enumerate(w_words):
        if i >= len(y_words):
            merged.append(w_word)
            continue

        y_word = y_words[i]
        if w_word.lower() == y_word.lower():
            # Agree — prefer YT casing (better at proper nouns)
            merged.append(y_word)
        elif _is_proper_noun_candidate(w_word, y_word):
            merged.append(y_word)
        else:
            # Disagree — keep Whisper
            merged.append(w_word)

    return " ".join(merged)


def detect_time_gaps(
    whisper_segs: list[dict],
    yt_segs: list[dict],
) -> list[TimeGap]:
    """Find segments where one source has text but the other doesn't."""
    gaps: list[TimeGap] = []

    for w_seg, y_seg in zip(whisper_segs, yt_segs):
        w_has = bool(w_seg["text"].strip())
        y_has = bool(y_seg["text"].strip())

        if w_has and not y_has:
            gaps.append(TimeGap(
                position=w_seg["position"], type="yt_missing", text=w_seg["text"],
            ))
        elif y_has and not w_has:
            gaps.append(TimeGap(
                position=y_seg["position"], type="whisper_missing", text=y_seg["text"],
            ))

    return gaps


# ---------------------------------------------------------------------------
# 2c. Dialogue Validation
# ---------------------------------------------------------------------------

def validate_dialogue(segments: list[dict]) -> list[QualityIssue]:
    """Run sanity checks on speaker assignments."""
    issues: list[QualityIssue] = []
    if not segments:
        return issues

    # Speaker turn ratio
    speaker_counts: dict[str, int] = {}
    for seg in segments:
        s = seg["speaker"]
        speaker_counts[s] = speaker_counts.get(s, 0) + 1

    total = len(segments)
    for speaker, count in speaker_counts.items():
        ratio = count / total
        if ratio > 0.95:
            issues.append(QualityIssue(
                type="speaker_ratio",
                detail=f"{speaker} has {ratio:.0%} of turns ({count}/{total})",
            ))

    # Consecutive same speaker
    max_run = 0
    current_run = 1
    for i in range(1, len(segments)):
        if segments[i]["speaker"] == segments[i - 1]["speaker"]:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1

    if max_run >= 20:
        issues.append(QualityIssue(
            type="consecutive_speaker",
            detail=f"Same speaker for {max_run} consecutive turns",
        ))

    return issues


# ---------------------------------------------------------------------------
# Main: process one episode
# ---------------------------------------------------------------------------

def clean_episode(episode_id: str, prep: PrepResult) -> dict:
    """Run Stage 2 for a single episode. Returns summary stats."""
    sb = get_supabase()

    # Fetch all segments
    all_segments = []
    offset = 0
    while True:
        batch = (
            sb.table("segments")
            .select("id, position, speaker, text, start_time, end_time")
            .eq("episode_id", episode_id)
            .order("position")
            .range(offset, offset + 999)
            .execute()
        ).data
        if not batch:
            break
        all_segments.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    # Fetch YT segments (may be empty if fetch_yt_captions.py hasn't run)
    all_yt = []
    offset = 0
    while True:
        batch = (
            sb.table("yt_segments")
            .select("position, text")
            .eq("episode_id", episode_id)
            .order("position")
            .range(offset, offset + 999)
            .execute()
        ).data
        if not batch:
            break
        all_yt.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    # Build YT lookup by position
    yt_by_pos = {seg["position"]: seg for seg in all_yt}

    # Filter out intro segments
    intro_end = prep["intro_end_position"]
    content_segments = [s for s in all_segments if s["position"] >= intro_end]

    # 2a + 2b: Merge text, assign speakers, compute confidence
    updates = []
    flagged_count = 0

    for seg in content_segments:
        yt_seg = yt_by_pos.get(seg["position"])
        yt_text = yt_seg["text"] if yt_seg else ""

        clean_text = merge_segment_text(seg["text"], yt_text)
        confidence = compute_text_confidence(seg["text"], yt_text)

        speaker_info = prep["speakers"].get(seg["speaker"])
        person_id = speaker_info["person_id"] if speaker_info else None

        updates.append({
            "id": seg["id"],
            "clean_text": clean_text,
            "text_confidence": confidence,
            "person_id": person_id,
        })

        if confidence < TEXT_CONFIDENCE_THRESHOLD:
            flagged_count += 1

    # Batch update segments
    for i in range(0, len(updates), BATCH_INSERT_SIZE):
        batch = updates[i:i + BATCH_INSERT_SIZE]
        for row in batch:
            sb.table("segments").update({
                "clean_text": row["clean_text"],
                "text_confidence": row["text_confidence"],
                "person_id": row["person_id"],
            }).eq("id", row["id"]).execute()

    # 2c: Validate dialogue
    issues = validate_dialogue(content_segments)

    # Detect time gaps
    if all_yt:
        whisper_for_gap = [s for s in all_segments if s["position"] in yt_by_pos]
        yt_for_gap = [yt_by_pos[s["position"]] for s in whisper_for_gap]
        gaps = detect_time_gaps(whisper_for_gap, yt_for_gap)
        if gaps:
            issues.append(QualityIssue(
                type="time_gaps",
                detail=f"{len(gaps)} segments with text in only one source",
            ))

    # Save quality issues to episode
    if issues:
        sb.table("episodes").update({
            "quality_issues": [dict(i) for i in issues],
        }).eq("id", episode_id).execute()

    return {
        "total_segments": len(content_segments),
        "flagged_for_review": flagged_count,
        "quality_issues": len(issues),
        "yt_segments_available": len(all_yt) > 0,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/agents/test_stage2_clean.py -v`

Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/agents/stage2_clean.py tests/agents/test_stage2_clean.py
git commit -m "feat: implement Stage 2 CLEAN — text merge, speaker assignment, validation"
```

---

## Task 6: Stage 3 — EXTRACT (Triage + Chunk + Graphiti Ingest)

**Files:**
- Create: `scripts/agents/stage3_extract.py`
- Create: `tests/agents/test_stage3_extract.py`

- [ ] **Step 1: Write tests for triage and chunking**

```python
# tests/agents/test_stage3_extract.py
from unittest.mock import patch, MagicMock
from scripts.agents.stage3_extract import (
    is_heuristic_filler,
    triage_segments,
    build_graphiti_episode_body,
)


def test_is_heuristic_filler_catches_short_fillers():
    assert is_heuristic_filler("yeah") is True
    assert is_heuristic_filler("mm-hmm") is True
    assert is_heuristic_filler("right exactly") is True


def test_is_heuristic_filler_passes_substantive():
    assert is_heuristic_filler("Cold exposure activates brown fat") is False
    assert is_heuristic_filler("That's a really interesting point about dopamine") is False


def test_is_heuristic_filler_passes_medium_length():
    # 6-15 words — not caught by heuristic, needs LLM
    assert is_heuristic_filler("yeah that makes a lot of sense") is False


def test_triage_segments_filters_obvious_fillers():
    segments = [
        {"text": "yeah", "speaker": "Speaker 0", "position": 0},
        {"text": "Cold exposure activates brown fat tissue", "speaker": "Speaker 1", "position": 1},
        {"text": "mm-hmm", "speaker": "Speaker 0", "position": 2},
        {"text": "The Soberg principle states you should end on cold", "speaker": "Speaker 1", "position": 3},
    ]
    # Mock LLM to avoid real calls
    with patch("scripts.agents.stage3_extract.llm_call", return_value="SUBSTANTIVE"):
        result = triage_segments(segments)

    assert len(result) == 2  # only the substantive ones
    assert result[0]["position"] == 1
    assert result[1]["position"] == 3


def test_build_graphiti_episode_body():
    segments = [
        {"speaker": "Dr. Huberman", "text": "Cold exposure activates brown fat", "start_time": 100.0, "end_time": 115.0},
        {"speaker": "Steven Bartlett", "text": "How long should you stay in?", "start_time": 115.0, "end_time": 120.0},
    ]
    body = build_graphiti_episode_body(segments)
    assert "Dr. Huberman" in body
    assert "Cold exposure" in body
    assert "[100s-115s]" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_stage3_extract.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement stage3_extract.py**

```python
# scripts/agents/stage3_extract.py
"""Stage 3 — EXTRACT: Triage, chunk, Graphiti ingest."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "vendor" / "graphiti"))

from config import (
    get_supabase,
    FILLER_PHRASES,
    FILLER_MAX_WORDS,
    CHUNK_DURATION,
    CHUNK_OVERLAP,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
)
from llm import llm_call
from prompts import TRIAGE_PROMPT

from podcast_vault.extract import TranscriptSegment, chunk_transcript
from podcast_vault.ingest import (
    ENTITY_TYPES,
    EDGE_TYPES,
    EDGE_TYPE_MAP,
    GRAPHITI_EXTRACTION_INSTRUCTIONS,
    build_episode_name,
    build_source_description,
    build_youtube_url,
    format_timestamp,
    build_group_id,
)
from podcast_vault.show_notes import extract_show_note_links, get_study_links


# ---------------------------------------------------------------------------
# 3a. Triage
# ---------------------------------------------------------------------------

def is_heuristic_filler(text: str) -> bool:
    """Check if a turn is obvious filler based on word count and phrases."""
    words = text.strip().lower().split()
    if len(words) > FILLER_MAX_WORDS:
        return False
    return all(w in FILLER_PHRASES for w in words)


def triage_segments(segments: list[dict]) -> list[dict]:
    """Filter out filler turns. Returns only substantive segments."""
    substantive = []

    for seg in segments:
        text = seg.get("clean_text") or seg["text"]
        word_count = len(text.split())

        # Obvious filler — skip
        if is_heuristic_filler(text):
            continue

        # Long turns — always substantive
        if word_count > 15:
            substantive.append(seg)
            continue

        # Medium turns (6-15 words) — ask LLM
        response = llm_call(TRIAGE_PROMPT.format(text=text))
        if "SUBSTANTIVE" in response.upper():
            substantive.append(seg)

    return substantive


# ---------------------------------------------------------------------------
# 3b. Chunk
# ---------------------------------------------------------------------------

def segments_to_transcript_segments(segments: list[dict]) -> list[TranscriptSegment]:
    """Convert DB segments to podcast_vault TranscriptSegment objects."""
    return [
        TranscriptSegment(
            text=seg.get("clean_text") or seg["text"],
            start_time=seg["start_time"],
            end_time=seg["end_time"],
        )
        for seg in segments
    ]


def build_graphiti_episode_body(segments: list[dict]) -> str:
    """Format a chunk of segments for Graphiti ingestion."""
    lines = []
    for seg in segments:
        text = seg.get("clean_text") or seg["text"]
        speaker = seg.get("speaker_name") or seg.get("speaker", "Unknown")
        start = int(seg["start_time"])
        end = int(seg["end_time"])
        lines.append(f"[{start}s-{end}s] {speaker}: {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3c. Graphiti Ingest
# ---------------------------------------------------------------------------

async def ingest_episode(
    episode_id: str,
    youtube_id: str,
    episode_title: str,
    podcast_name: str,
    published_at: str | None,
    segments: list[dict],
    speaker_map: dict[str, dict],
):
    """Chunk segments and ingest into Graphiti."""
    from graphiti_core import Graphiti

    graphiti = Graphiti(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Add speaker names to segments
        for seg in segments:
            info = speaker_map.get(seg["speaker"], {})
            seg["speaker_name"] = info.get("name", seg["speaker"])

        # Convert to TranscriptSegments for chunking
        ts_segments = segments_to_transcript_segments(segments)
        chunks = chunk_transcript(ts_segments, CHUNK_DURATION, CHUNK_OVERLAP)

        # Map chunk indices back to original segments for speaker info
        for chunk_idx, chunk in enumerate(chunks):
            chunk_start = chunk[0].start_time
            chunk_end = chunk[-1].end_time

            # Find matching original segments for this time window
            chunk_segs = [
                s for s in segments
                if s["start_time"] < chunk_end and s["end_time"] > chunk_start
            ]

            if not chunk_segs:
                continue

            body = build_graphiti_episode_body(chunk_segs)
            start_seconds = int(chunk_start)

            # Determine primary guest for this chunk
            guest_name = "Unknown"
            for seg in chunk_segs:
                info = speaker_map.get(seg["speaker"], {})
                if info.get("role") == "guest":
                    guest_name = info.get("name", "Unknown")
                    break

            await graphiti.add_episode(
                name=build_episode_name(podcast_name, youtube_id, start_seconds),
                episode_body=body,
                source_description=build_source_description(
                    episode_title=episode_title,
                    podcast_name=podcast_name,
                    guest=guest_name,
                    start_time=format_timestamp(chunk_start),
                    end_time=format_timestamp(chunk_end),
                    youtube_url=build_youtube_url(youtube_id, start_seconds),
                ),
                group_id=build_group_id(podcast_name),
                entity_types=list(ENTITY_TYPES.values()),
                edge_types=list(EDGE_TYPES.values()),
                edge_type_map=EDGE_TYPE_MAP,
                custom_extraction_instructions=GRAPHITI_EXTRACTION_INSTRUCTIONS,
                reference_time=datetime.fromisoformat(published_at) if published_at else datetime.now(timezone.utc),
            )

            print(f"    Chunk {chunk_idx + 1}/{len(chunks)} ingested ({format_timestamp(chunk_start)}-{format_timestamp(chunk_end)})")

    finally:
        await graphiti.close()


# ---------------------------------------------------------------------------
# 3d. Show Notes
# ---------------------------------------------------------------------------

def parse_show_notes(description: str | None) -> dict:
    """Parse show notes URLs from episode description."""
    if not description:
        return {"studies": [], "products": [], "guest_bio": [], "other": []}

    links = extract_show_note_links(description)
    return {
        "studies": [l for l in links if l.link_type == "study"],
        "products": [l for l in links if l.link_type == "product"],
        "guest_bio": [l for l in links if l.link_type == "guest_bio"],
        "other": [l for l in links if l.link_type == "other"],
    }


# ---------------------------------------------------------------------------
# Main: process one episode
# ---------------------------------------------------------------------------

async def extract_episode(episode_id: str, speaker_map: dict[str, dict]) -> dict:
    """Run Stage 3 extraction for a single episode."""
    sb = get_supabase()

    # Fetch episode
    episode = sb.table("episodes").select("*").eq("id", episode_id).single().execute().data
    youtube_id = episode["youtube_id"]
    title = episode.get("title", "")
    description = episode.get("description", "")
    published_at = episode.get("published_at")
    intro_end = episode.get("intro_end_position", 0)

    # Fetch all segments (paginated)
    all_segments = []
    offset = 0
    while True:
        batch = (
            sb.table("segments")
            .select("id, position, speaker, text, clean_text, start_time, end_time")
            .eq("episode_id", episode_id)
            .order("position")
            .range(offset, offset + 999)
            .execute()
        ).data
        if not batch:
            break
        all_segments.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    # Filter to content (after intro)
    content_segments = [s for s in all_segments if s["position"] >= intro_end]

    # 3a. Triage
    substantive = triage_segments(content_segments)
    print(f"    Triage: {len(substantive)}/{len(content_segments)} substantive")

    # 3b + 3c. Chunk and ingest
    if substantive:
        await ingest_episode(
            episode_id=episode_id,
            youtube_id=youtube_id,
            episode_title=title,
            podcast_name="Diary of a CEO",
            published_at=published_at,
            segments=substantive,
            speaker_map=speaker_map,
        )

    # 3d. Show notes
    show_notes = parse_show_notes(description)

    # 3e. Checkpoint
    sb.table("episodes").update({
        "knowledge_processed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", episode_id).execute()

    return {
        "substantive_turns": len(substantive),
        "total_turns": len(content_segments),
        "show_note_links": sum(len(v) for v in show_notes.values()),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/agents/test_stage3_extract.py -v`

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/agents/stage3_extract.py tests/agents/test_stage3_extract.py
git commit -m "feat: implement Stage 3 EXTRACT — triage, chunk, Graphiti ingest"
```

---

## Task 7: Stage 3 — ENRICH (Web Search + Profile Hydration + Persona)

**Files:**
- Create: `scripts/agents/stage3_enrich.py`
- Create: `tests/agents/test_stage3_enrich.py`
- Modify: `scripts/agents/prompts.py`

- [ ] **Step 1: Write tests for enrichment**

```python
# tests/agents/test_stage3_enrich.py
from unittest.mock import patch, MagicMock
from scripts.agents.stage3_enrich import (
    build_person_search_query,
    build_study_search_query,
    extract_profile_from_search,
)


def test_build_person_search_query():
    q = build_person_search_query("Dr. Andrew Huberman", "neuroscience")
    assert "Andrew Huberman" in q
    assert "neuroscience" in q


def test_build_study_search_query():
    q = build_study_search_query("Sramek et al.", "cold exposure brown fat")
    assert "Sramek" in q
    assert "cold exposure" in q


def test_extract_profile_from_search():
    search_results = [
        {"title": "Andrew Huberman - Wikipedia", "url": "https://en.wikipedia.org/wiki/Andrew_Huberman", "content": "Andrew D. Huberman is an American neuroscientist and tenured professor at Stanford School of Medicine."},
        {"title": "Huberman Lab", "url": "https://hubermanlab.com", "content": "Podcast about science and health."},
    ]

    with patch("scripts.agents.stage3_enrich.llm_json_call") as mock_llm:
        mock_llm.return_value = {
            "bio": "American neuroscientist at Stanford",
            "credentials": "PhD, Stanford Professor",
            "expertise_domains": ["neuroscience"],
        }
        result = extract_profile_from_search("Dr. Andrew Huberman", search_results)

    assert result["bio"] == "American neuroscientist at Stanford"
    assert "neuroscience" in result["expertise_domains"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_stage3_enrich.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Add enrichment prompts to prompts.py**

Add to `scripts/agents/prompts.py`:

```python
PROFILE_EXTRACTION_PROMPT = """Extract a structured profile from these search results about {name}.

Search results:
{results_text}

Return a JSON object with these fields (use null if not found):
- "bio": one-sentence biography
- "credentials": degrees, titles, positions
- "photo_url": URL to a profile photo if found
- "socials": {{"twitter": url, "instagram": url, "youtube": url, "website": url}}
- "books_authored": list of book titles
- "companies": list of {{"name": str, "role": str}}
- "wikipedia_summary": first paragraph from Wikipedia if available
- "expertise_domains": list of topic areas

Return ONLY valid JSON."""

PERSONA_EXTRACTION_PROMPT = """Analyze these transcript turns by {name} and describe their communication style and personality.

Turns:
{turns_text}

Return a JSON object with:
- "communication_style": {{"tone": str, "formality": str, "storytelling_tendency": str, "signature_phrases": list, "speech_patterns": list}}
- "personality_traits": {{"openness": str, "conscientiousness": str, "extraversion": str, "agreeableness": str, "emotional_stability": str}}

Use brief descriptors (1-3 words each). Return ONLY valid JSON."""
```

- [ ] **Step 4: Implement stage3_enrich.py**

```python
# scripts/agents/stage3_enrich.py
"""Stage 3 — ENRICH: Web search, profile hydration, persona extraction."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_supabase, PERSONA_EVERY_N_EPISODES
from llm import llm_json_call
from search import searxng_search
from prompts import PROFILE_EXTRACTION_PROMPT, PERSONA_EXTRACTION_PROMPT


# ---------------------------------------------------------------------------
# Search query builders
# ---------------------------------------------------------------------------

def build_person_search_query(name: str, expertise: str | None = None) -> str:
    """Build a search query for a person."""
    query = f'"{name}"'
    if expertise:
        query += f" {expertise}"
    return query


def build_study_search_query(authors: str, topic: str) -> str:
    """Build a search query for a study."""
    return f'"{authors}" {topic} site:pubmed.ncbi.nlm.nih.gov OR site:scholar.google.com'


def build_book_search_query(title: str, author: str | None = None) -> str:
    """Build a search query for a book."""
    query = f'"{title}"'
    if author:
        query += f' "{author}"'
    query += " site:goodreads.com OR site:amazon.com"
    return query


# ---------------------------------------------------------------------------
# Profile extraction
# ---------------------------------------------------------------------------

def extract_profile_from_search(name: str, search_results: list[dict]) -> dict:
    """Use LLM to extract structured profile from search results."""
    results_text = "\n\n".join(
        f"Title: {r['title']}\nURL: {r['url']}\nContent: {r.get('content', '')}"
        for r in search_results
    )

    prompt = PROFILE_EXTRACTION_PROMPT.format(
        name=name, results_text=results_text,
    )
    result = llm_json_call(prompt)
    return result or {}


# ---------------------------------------------------------------------------
# 3g. Profile Hydration
# ---------------------------------------------------------------------------

def hydrate_person(person_id: str, name: str) -> dict | None:
    """Search for a person and update their profile in Supabase."""
    sb = get_supabase()

    results = searxng_search(
        build_person_search_query(name),
        engines="google,wikipedia",
        max_results=5,
    )

    if not results:
        return None

    profile = extract_profile_from_search(name, results)
    if not profile:
        return None

    update = {"hydrated_at": datetime.now(timezone.utc).isoformat()}
    if profile.get("bio"):
        update["bio"] = profile["bio"]
    if profile.get("photo_url"):
        update["photo_url"] = profile["photo_url"]

    sb.table("people").update(update).eq("id", person_id).execute()
    return profile


# ---------------------------------------------------------------------------
# 3h. Persona Extraction
# ---------------------------------------------------------------------------

def extract_persona(person_id: str, name: str) -> dict | None:
    """Build a persona JSON from a person's recent substantive turns."""
    sb = get_supabase()

    # Get recent substantive segments for this person
    segments = (
        sb.table("segments")
        .select("clean_text, text")
        .eq("person_id", person_id)
        .not_.is_("clean_text", "null")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    ).data

    if not segments or len(segments) < 10:
        return None

    turns_text = "\n".join(
        f"- {seg.get('clean_text') or seg['text']}"
        for seg in segments[:50]
    )

    prompt = PERSONA_EXTRACTION_PROMPT.format(name=name, turns_text=turns_text)
    persona = llm_json_call(prompt)

    if persona:
        sb.table("people").update({
            "persona_json": persona,
        }).eq("id", person_id).execute()

    return persona


# ---------------------------------------------------------------------------
# Batch enrichment runner
# ---------------------------------------------------------------------------

def run_enrichment():
    """Run batch enrichment for all unenriched people."""
    sb = get_supabase()

    # Find people without hydration
    people = (
        sb.table("people")
        .select("id, name")
        .is_("hydrated_at", "null")
        .execute()
    ).data

    print(f"Found {len(people)} people to hydrate")

    for i, person in enumerate(people, 1):
        print(f"[{i}/{len(people)}] Hydrating {person['name']}...")
        profile = hydrate_person(person["id"], person["name"])
        if profile:
            print(f"    Bio: {profile.get('bio', 'N/A')[:80]}")
        else:
            print(f"    No results found")
        time.sleep(2)  # Rate limit SearXNG

    # Persona extraction for people with enough data
    people_with_data = (
        sb.table("people")
        .select("id, name, persona_json")
        .is_("persona_json", "null")
        .execute()
    ).data

    print(f"\nFound {len(people_with_data)} people for persona extraction")

    for i, person in enumerate(people_with_data, 1):
        print(f"[{i}/{len(people_with_data)}] Persona: {person['name']}...")
        persona = extract_persona(person["id"], person["name"])
        if persona:
            print(f"    Style: {persona.get('communication_style', {}).get('tone', 'N/A')}")
        else:
            print(f"    Not enough data")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/agents/test_stage3_enrich.py -v`

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/agents/stage3_enrich.py scripts/agents/prompts.py \
       tests/agents/test_stage3_enrich.py
git commit -m "feat: implement Stage 3 ENRICH — web search, profile hydration, persona"
```

---

## Task 8: Pipeline Runner

**Files:**
- Modify: `scripts/agents/run_pipeline.py`

- [ ] **Step 1: Rewrite run_pipeline.py for 3-stage architecture**

```python
# scripts/agents/run_pipeline.py
"""Pipeline runner — orchestrates PREP → CLEAN → EXTRACT+ENRICH."""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_supabase, DOAC_CHANNEL_SLUG
from stage1_prep import prep_episode
from stage2_clean import clean_episode
from stage3_extract import extract_episode
from stage3_enrich import run_enrichment


def get_episodes(channel_slug: str, stage: str) -> list[dict]:
    """Fetch episodes to process based on the stage."""
    sb = get_supabase()

    # Get channel
    channel = (
        sb.table("channels")
        .select("id")
        .eq("slug", channel_slug)
        .single()
        .execute()
    ).data

    # Get episodes with segments (processed by diarization)
    episodes = (
        sb.table("episodes")
        .select("id, youtube_id, title, published_at, intro_end_position, knowledge_processed_at")
        .eq("channel_id", channel["id"])
        .order("duration_seconds")
        .execute()
    ).data

    # Filter based on stage
    if stage == "extract":
        return [e for e in episodes if not e.get("knowledge_processed_at")]
    return episodes


def run_stage1(episodes: list[dict]):
    """Run Stage 1 PREP for all episodes."""
    print(f"\n{'='*60}")
    print(f"STAGE 1 — PREP ({len(episodes)} episodes)")
    print(f"{'='*60}\n")

    results = {}
    for idx, ep in enumerate(episodes, 1):
        print(f"[{idx}/{len(episodes)}] {ep['youtube_id']} — {ep.get('title', '')[:50]}")
        t_start = time.time()
        result = prep_episode(ep["id"])
        elapsed = time.time() - t_start
        results[ep["id"]] = result
        speakers = ", ".join(
            f"{v['name']} ({v['role']})" for v in result["speakers"].values()
        )
        print(f"    Intro ends at segment {result['intro_end_position']}, speakers: {speakers} ({elapsed:.1f}s)")

    return results


def run_stage2(episodes: list[dict], prep_results: dict):
    """Run Stage 2 CLEAN for all episodes."""
    print(f"\n{'='*60}")
    print(f"STAGE 2 — CLEAN ({len(episodes)} episodes)")
    print(f"{'='*60}\n")

    for idx, ep in enumerate(episodes, 1):
        print(f"[{idx}/{len(episodes)}] {ep['youtube_id']} — {ep.get('title', '')[:50]}")
        prep = prep_results.get(ep["id"])
        if not prep:
            print(f"    SKIP — no prep result")
            continue
        t_start = time.time()
        stats = clean_episode(ep["id"], prep)
        elapsed = time.time() - t_start
        print(f"    {stats['total_segments']} segments, {stats['flagged_for_review']} flagged, "
              f"{stats['quality_issues']} issues ({elapsed:.1f}s)")


def run_stage3(episodes: list[dict], prep_results: dict):
    """Run Stage 3 EXTRACT for all episodes."""
    print(f"\n{'='*60}")
    print(f"STAGE 3 — EXTRACT ({len(episodes)} episodes)")
    print(f"{'='*60}\n")

    for idx, ep in enumerate(episodes, 1):
        if ep.get("knowledge_processed_at"):
            print(f"[{idx}/{len(episodes)}] SKIP — already processed")
            continue

        print(f"[{idx}/{len(episodes)}] {ep['youtube_id']} — {ep.get('title', '')[:50]}")
        prep = prep_results.get(ep["id"])
        speaker_map = prep["speakers"] if prep else {}

        t_start = time.time()
        stats = asyncio.run(extract_episode(ep["id"], speaker_map))
        elapsed = time.time() - t_start
        print(f"    {stats['substantive_turns']}/{stats['total_turns']} substantive, "
              f"{stats['show_note_links']} links ({elapsed:.1f}s)")


def main():
    parser = argparse.ArgumentParser(description="Podcast Vault Pipeline Runner")
    parser.add_argument(
        "--channel", default=DOAC_CHANNEL_SLUG,
        help=f"Channel slug (default: {DOAC_CHANNEL_SLUG})",
    )
    parser.add_argument(
        "--stage",
        choices=["prep", "clean", "extract", "enrich", "all"],
        default="all",
        help="Which stage to run (default: all)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limit number of episodes to process (0 = all)",
    )
    args = parser.parse_args()

    episodes = get_episodes(args.channel, args.stage)
    if args.limit > 0:
        episodes = episodes[:args.limit]

    print(f"Pipeline: {args.stage} | Channel: {args.channel} | Episodes: {len(episodes)}")

    if args.stage in ("prep", "all"):
        prep_results = run_stage1(episodes)
    else:
        prep_results = {}

    if args.stage in ("clean", "all"):
        if not prep_results:
            # Load prep results from DB (intro_end_position already saved)
            print("Loading prep results from DB...")
            for ep in episodes:
                prep_results[ep["id"]] = {
                    "episode_id": ep["id"],
                    "intro_end_position": ep.get("intro_end_position", 0),
                    "speakers": {},
                }
        run_stage2(episodes, prep_results)

    if args.stage in ("extract", "all"):
        run_stage3(episodes, prep_results)

    if args.stage in ("enrich", "all"):
        run_enrichment()

    print(f"\n{'='*60}")
    print("Pipeline complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test with dry run (1 episode)**

Run: `python -m scripts.agents.run_pipeline --stage prep --limit 1`

Expected: processes 1 episode through Stage 1, prints intro position and speakers.

- [ ] **Step 3: Commit**

```bash
git add scripts/agents/run_pipeline.py
git commit -m "feat: rewrite pipeline runner for 3-stage architecture"
```

---

## Task 9: Review UI — Dashboard Page

**Files:**
- Create: `dashboard/app/review/[episodeId]/page.tsx`
- Create: `dashboard/app/api/review/[episodeId]/route.ts`
- Create: `dashboard/app/api/corrections/route.ts`
- Create: `dashboard/components/review-segment.tsx`

- [ ] **Step 1: Create the API route for fetching flagged segments**

```typescript
// dashboard/app/api/review/[episodeId]/route.ts
import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ episodeId: string }> }
) {
  const { episodeId } = await params;

  // Resolve by youtube_id or UUID
  let episodeFilter = "id";
  if (episodeId.length < 36) {
    episodeFilter = "youtube_id";
  }

  const { data: episode } = await supabase
    .from("episodes")
    .select("id, youtube_id, title, intro_end_position, quality_issues")
    .eq(episodeFilter, episodeId)
    .single();

  if (!episode) {
    return NextResponse.json({ error: "Episode not found" }, { status: 404 });
  }

  // Fetch flagged segments (low confidence)
  const { data: segments } = await supabase
    .from("segments")
    .select("id, position, speaker, text, clean_text, text_confidence, start_time, end_time, person_id")
    .eq("episode_id", episode.id)
    .lt("text_confidence", 0.85)
    .order("position");

  // Fetch matching YT segments
  const positions = (segments || []).map((s) => s.position);
  const { data: ytSegments } = await supabase
    .from("yt_segments")
    .select("position, text")
    .eq("episode_id", episode.id)
    .in("position", positions);

  const ytByPos = Object.fromEntries(
    (ytSegments || []).map((s) => [s.position, s.text])
  );

  return NextResponse.json({
    episode,
    segments: (segments || []).map((s) => ({
      ...s,
      yt_text: ytByPos[s.position] || "",
    })),
  });
}
```

- [ ] **Step 2: Create the corrections API route**

```typescript
// dashboard/app/api/corrections/route.ts
import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { segment_id, episode_id, source, original_text, suggested_text, reason } = body;

  const { data, error } = await supabase.from("segment_corrections").insert({
    segment_id,
    episode_id,
    source: source || "auto_merge_review",
    original_text,
    suggested_text,
    reason,
  }).select().single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // If this is an accepted correction, update the segment directly
  if (suggested_text && source === "auto_merge_review") {
    await supabase
      .from("segments")
      .update({ clean_text: suggested_text })
      .eq("id", segment_id);

    await supabase
      .from("segment_corrections")
      .update({ status: "accepted", reviewed_at: new Date().toISOString() })
      .eq("id", data.id);
  }

  return NextResponse.json({ correction: data });
}
```

- [ ] **Step 3: Create the ReviewSegment component**

```tsx
// dashboard/components/review-segment.tsx
"use client";

import { useState } from "react";

interface Segment {
  id: string;
  position: number;
  speaker: string;
  text: string;
  clean_text: string | null;
  yt_text: string;
  text_confidence: number;
  start_time: number;
  end_time: number;
}

interface ReviewSegmentProps {
  segment: Segment;
  onAccept: (id: string, text: string) => void;
  onSkip: (id: string) => void;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function ReviewSegment({ segment, onAccept, onSkip }: ReviewSegmentProps) {
  const [editedText, setEditedText] = useState(
    segment.clean_text || segment.text
  );

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex justify-between items-center text-sm text-gray-500">
        <span>
          Segment #{segment.position} [{formatTime(segment.start_time)} -{" "}
          {formatTime(segment.end_time)}]
        </span>
        <span>
          Speaker: {segment.speaker} | Confidence:{" "}
          {(segment.text_confidence * 100).toFixed(0)}%
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-medium text-gray-400 mb-1">Whisper</div>
          <div className="bg-gray-900 p-3 rounded text-sm">{segment.text}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-gray-400 mb-1">
            YT Caption
          </div>
          <div className="bg-gray-900 p-3 rounded text-sm">
            {segment.yt_text || <span className="text-gray-600">No YT data</span>}
          </div>
        </div>
      </div>

      <div>
        <div className="text-xs font-medium text-gray-400 mb-1">
          Merged (editable)
        </div>
        <textarea
          className="w-full bg-gray-800 border border-gray-700 rounded p-3 text-sm"
          rows={2}
          value={editedText}
          onChange={(e) => setEditedText(e.target.value)}
        />
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => onAccept(segment.id, editedText)}
          className="px-4 py-1.5 bg-green-700 hover:bg-green-600 rounded text-sm"
        >
          Accept
        </button>
        <button
          onClick={() => onSkip(segment.id)}
          className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm"
        >
          Skip
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create the review page**

```tsx
// dashboard/app/review/[episodeId]/page.tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { ReviewSegment } from "@/components/review-segment";

interface Segment {
  id: string;
  position: number;
  speaker: string;
  text: string;
  clean_text: string | null;
  yt_text: string;
  text_confidence: number;
  start_time: number;
  end_time: number;
}

interface EpisodeData {
  episode: {
    id: string;
    youtube_id: string;
    title: string;
    quality_issues: any[] | null;
  };
  segments: Segment[];
}

export default function ReviewPage() {
  const params = useParams();
  const episodeId = params.episodeId as string;
  const [data, setData] = useState<EpisodeData | null>(null);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [reviewed, setReviewed] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetch(`/api/review/${episodeId}`)
      .then((r) => r.json())
      .then(setData);
  }, [episodeId]);

  const handleAccept = useCallback(
    async (segmentId: string, text: string) => {
      if (!data) return;
      const seg = data.segments.find((s) => s.id === segmentId);
      if (!seg) return;

      await fetch("/api/corrections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segment_id: segmentId,
          episode_id: data.episode.id,
          source: "auto_merge_review",
          original_text: seg.text,
          suggested_text: text,
        }),
      });

      setReviewed((prev) => new Set(prev).add(segmentId));
      setCurrentIdx((prev) => Math.min(prev + 1, data.segments.length - 1));
    },
    [data]
  );

  const handleSkip = useCallback(
    (segmentId: string) => {
      if (!data) return;
      setReviewed((prev) => new Set(prev).add(segmentId));
      setCurrentIdx((prev) => Math.min(prev + 1, data.segments.length - 1));
    },
    [data]
  );

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (!data) return;
      if (e.key === "ArrowRight") {
        setCurrentIdx((prev) => Math.min(prev + 1, data.segments.length - 1));
      } else if (e.key === "ArrowLeft") {
        setCurrentIdx((prev) => Math.max(prev - 1, 0));
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [data]);

  if (!data) return <div className="p-8">Loading...</div>;

  const remaining = data.segments.filter((s) => !reviewed.has(s.id));
  const current = data.segments[currentIdx];

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-6">
      <div>
        <h1 className="text-xl font-bold">{data.episode.title}</h1>
        <p className="text-sm text-gray-400">
          {data.segments.length} segments to review | {reviewed.size} reviewed |{" "}
          {remaining.length} remaining
        </p>
        {data.episode.quality_issues && (
          <div className="mt-2 text-yellow-500 text-sm">
            Quality issues:{" "}
            {data.episode.quality_issues.map((i: any) => i.detail).join(", ")}
          </div>
        )}
      </div>

      {current && (
        <ReviewSegment
          key={current.id}
          segment={current}
          onAccept={handleAccept}
          onSkip={handleSkip}
        />
      )}

      <div className="flex justify-between text-sm text-gray-500">
        <span>← → to navigate | {currentIdx + 1} / {data.segments.length}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Test the review UI**

Run: `cd dashboard && npm run dev`

Navigate to `http://localhost:3001/review/{youtube_id}` for an episode that has been through Stage 2.

Expected: shows flagged segments with side-by-side diff, accept/skip buttons work.

- [ ] **Step 6: Commit**

```bash
git add dashboard/app/review/ dashboard/app/api/review/ \
       dashboard/app/api/corrections/ dashboard/components/review-segment.tsx
git commit -m "feat: add review UI for transcript merge disagreements"
```

---

## Task 10: SearXNG Docker Setup

**Files:**
- Create: `docker-compose.yml` (vault root)

- [ ] **Step 1: Create docker-compose.yml**

```yaml
# docker-compose.yml
services:
  searxng:
    image: searxng/searxng:latest
    ports:
      - "8888:8080"
    environment:
      - SEARXNG_BASE_URL=http://localhost:8888
    volumes:
      - searxng_data:/etc/searxng
    restart: unless-stopped

volumes:
  searxng_data:
```

- [ ] **Step 2: Start and verify**

```bash
docker compose up -d searxng
# Wait ~10s for startup
curl -s "http://localhost:8888/search?q=test&format=json" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Results: {len(d.get(\"results\",[]))}')"
```

Expected: `Results: 10` (or similar non-zero count)

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add SearXNG docker-compose for web search enrichment"
```

---

## Task 11: Prerequisite — Populate YT Captions

This is not new code — it runs the existing `fetch_yt_captions.py` to populate the empty `yt_segments` table.

- [ ] **Step 1: Run YT caption fetcher for all episodes**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
python scripts/fetch_yt_captions.py --all
```

Expected: processes episodes, prints "Extracted N words from YT captions" and "Inserted N yt_segments" per episode. This takes a while (~2s per episode × 246 = ~8 minutes).

- [ ] **Step 2: Verify data**

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv('.env.local')
import os; from supabase import create_client
sb = create_client(os.environ['NEXT_PUBLIC_SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
r = sb.table('yt_segments').select('id', count='exact').limit(1).execute()
print(f'yt_segments count: {r.count}')
"
```

Expected: non-zero count (should be similar to segments count ~288K).

---

## Task 12: End-to-End Test — 1 Episode

- [ ] **Step 1: Run full pipeline on 1 episode**

```bash
python -m scripts.agents.run_pipeline --stage all --limit 1
```

Expected output:
```
Pipeline: all | Channel: the-diary-of-a-ceo | Episodes: 1

============================================================
STAGE 1 — PREP (1 episodes)
============================================================

[1/1] <youtube_id> — <title>
    Intro ends at segment N, speakers: Steven Bartlett (host), <guest> (guest)

============================================================
STAGE 2 — CLEAN (1 episodes)
============================================================

[1/1] <youtube_id> — <title>
    N segments, M flagged, K issues

============================================================
STAGE 3 — EXTRACT (1 episodes)
============================================================

[1/1] <youtube_id> — <title>
    Triage: N/M substantive
    Chunk 1/K ingested (0:00-20:00)
    ...

Pipeline complete!
```

- [ ] **Step 2: Verify Neo4j has data**

Log into Neo4j AuraDB console → Query tab → run:
```cypher
MATCH (n) RETURN labels(n) AS type, count(n) AS count ORDER BY count DESC
```

Expected: Guest, Topic, Protocol, Study, Book nodes created.

- [ ] **Step 3: Verify Supabase has clean data**

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv('.env.local')
import os; from supabase import create_client
sb = create_client(os.environ['NEXT_PUBLIC_SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
r = sb.table('segments').select('id, clean_text, text_confidence, person_id').not_.is_('clean_text','null').limit(3).execute()
for row in r.data:
    print(f'confidence={row[\"text_confidence\"]}, person={row[\"person_id\"]}, text={row[\"clean_text\"][:80]}')
"
```

Expected: segments with clean_text, text_confidence scores, and person_id populated.

- [ ] **Step 4: Commit any fixes from the E2E test**

```bash
git add -u
git commit -m "fix: adjustments from end-to-end pipeline test"
```
