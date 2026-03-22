# People Agents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a pipeline that creates living persona agents from podcast transcripts, with a Character Memory Page to visualize each person's synthesized worldview.

**Architecture:** Four discrete Python pipeline stages (extract embeddings → map speakers → build memory → export) writing to Supabase, plus a Next.js frontend page rendering agent memory as a public profile. Each stage is idempotent and resumable.

**Tech Stack:** Python 3.11+ (supabase-py, numpy, dotenv), GLM 4.7 via Ollama (local LLM), NeMo speaker embeddings, Next.js 15 / React 19 / Tailwind v4, Supabase PostgreSQL with pgvector.

**Design doc:** `docs/plans/2026-03-08-people-agents-design.md`

---

## Task 1: Database Migration — New Tables

**Files:**
- Create: `supabase/migrations/006_people_agents.sql`

**Step 1: Write the migration**

```sql
-- Global identity table (not channel-scoped)
CREATE TABLE people (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE,
  photo_url TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Agent memory (1:1 with people)
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

-- Speaker embeddings for voice fingerprinting
CREATE TABLE speaker_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  speaker_label TEXT NOT NULL,
  embedding VECTOR(192),
  person_id UUID REFERENCES people(id) ON DELETE SET NULL,
  mapped_confidence FLOAT,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_speaker_embeddings_episode ON speaker_embeddings(episode_id);
CREATE INDEX idx_speaker_embeddings_person ON speaker_embeddings(person_id);
CREATE UNIQUE INDEX idx_speaker_embeddings_unique ON speaker_embeddings(episode_id, speaker_label);

-- Link guests to global people identity
ALTER TABLE guests ADD COLUMN person_id UUID REFERENCES people(id) ON DELETE SET NULL;
CREATE INDEX idx_guests_person ON guests(person_id);
```

**Step 2: Run migration against local Supabase**

Run: `psql $DATABASE_URL -f supabase/migrations/006_people_agents.sql`
Expected: Tables created, no errors.

**Step 3: Verify schema**

Run: `psql $DATABASE_URL -c "\dt people; \dt agent_memories; \dt speaker_embeddings;"`
Expected: All three tables listed.

**Step 4: Commit**

```bash
git add supabase/migrations/006_people_agents.sql
git commit -m "feat: add people, agent_memories, speaker_embeddings tables for persona agents"
```

---

## Task 2: Pipeline Shared Utilities

**Files:**
- Create: `scripts/agents/__init__.py`
- Create: `scripts/agents/config.py`

**Step 1: Create the agents package directory**

```bash
mkdir -p scripts/agents
```

**Step 2: Write config.py**

```python
#!/usr/bin/env python3
"""Shared configuration for people agents pipeline."""

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
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "glm4:latest")

# Pipeline config
HOST_SIMILARITY_THRESHOLD = 0.7
FILLER_MAX_WORDS = 5
CONTEXT_WINDOW_TURNS = 5
BATCH_INSERT_SIZE = 200

# Filler phrases to skip without LLM call
FILLER_PHRASES = {
    "yeah", "yes", "no", "right", "exactly", "sure", "okay", "ok",
    "mm-hmm", "mhm", "uh-huh", "hmm", "um", "uh", "ah",
}


def get_supabase() -> Client:
    """Create a Supabase client."""
    return create_client(SUPABASE_URL, SUPABASE_KEY)
```

**Step 3: Write empty __init__.py**

```python
# scripts/agents/__init__.py
```

**Step 4: Verify imports work**

Run: `cd /path/to/vault && python -c "from scripts.agents.config import get_supabase, OLLAMA_MODEL; print('OK:', OLLAMA_MODEL)"`
Expected: `OK: glm4:latest`

**Step 5: Commit**

```bash
git add scripts/agents/
git commit -m "feat: add shared config for people agents pipeline"
```

---

## Task 3: Stage 1 — Extract Speaker Embeddings

**Files:**
- Create: `scripts/agents/extract_embeddings.py`

This script reads NeMo's intermediate embedding files from diarization output and stores them in the `speaker_embeddings` table.

**Step 1: Write extract_embeddings.py**

```python
#!/usr/bin/env python3
"""
Stage 1: Extract speaker embeddings from NeMo diarization output.

NeMo's diarization pipeline computes TitaNet speaker embeddings (192-dim)
as intermediate outputs. This script reads those embeddings and stores
them in the speaker_embeddings table for later speaker-to-person mapping.

Usage:
    python -m scripts.agents.extract_embeddings --nemo-dir /path/to/nemo/output
    python -m scripts.agents.extract_embeddings --nemo-dir /path/to/nemo/output --episode-id <uuid>
"""

import argparse
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np

from scripts.agents.config import get_supabase


def find_embedding_files(nemo_dir: str) -> list[Path]:
    """Find NeMo speaker embedding pickle/npy files in the output directory."""
    nemo_path = Path(nemo_dir)
    # NeMo stores embeddings in speaker_outputs/embeddings/
    embed_dir = nemo_path / "speaker_outputs" / "embeddings"
    if not embed_dir.exists():
        # Fallback: check for subsegments_scale*_cluster.label files
        # which contain per-speaker cluster centers
        embed_dir = nemo_path

    files = []
    for pattern in ["*.npy", "*.pkl", "*.pickle"]:
        files.extend(embed_dir.glob(pattern))
    return sorted(files)


def extract_speaker_embeddings_from_rttm(nemo_dir: str) -> dict[str, list[float]]:
    """
    Extract average speaker embeddings from NeMo's output.

    NeMo stores per-subsegment embeddings during clustering. We load
    the embedding matrix and cluster labels to compute per-speaker
    average embeddings (centroids).

    Returns: {"Speaker 0": [192-dim list], "Speaker 1": [192-dim list]}
    """
    nemo_path = Path(nemo_dir)

    # Look for the embedding and label files NeMo creates
    # Scale-specific embeddings: subsegments_scale{N}_cluster.label
    # and corresponding embedding matrices
    embed_dict = {}

    # Strategy 1: Load from pickle if saved during diarization
    pkl_path = nemo_path / "speaker_outputs" / "embeddings" / "speaker_embeddings.pkl"
    if pkl_path.exists():
        with open(pkl_path, "rb") as f:
            data = pickle.load(f)
        # data is typically {speaker_id: np.ndarray(192,)}
        for spk_id, emb in data.items():
            label = f"Speaker {spk_id}" if isinstance(spk_id, int) else str(spk_id)
            embed_dict[label] = emb.tolist() if isinstance(emb, np.ndarray) else list(emb)
        return embed_dict

    # Strategy 2: Load from numpy arrays + cluster labels
    for scale_dir in sorted(nemo_path.glob("speaker_outputs/embeddings/scale*")):
        emb_file = scale_dir / "embeddings.npy"
        label_file = scale_dir / "labels.npy"
        if emb_file.exists() and label_file.exists():
            embeddings = np.load(emb_file)  # (N_subsegments, 192)
            labels = np.load(label_file)     # (N_subsegments,)

            unique_speakers = np.unique(labels)
            for spk_id in unique_speakers:
                mask = labels == spk_id
                centroid = embeddings[mask].mean(axis=0)
                label = f"Speaker {int(spk_id)}"
                embed_dict[label] = centroid.tolist()

            if embed_dict:
                return embed_dict

    # Strategy 3: Check for unscaled embeddings
    emb_file = nemo_path / "speaker_outputs" / "embeddings.npy"
    lbl_file = nemo_path / "speaker_outputs" / "labels.npy"
    if emb_file.exists() and lbl_file.exists():
        embeddings = np.load(emb_file)
        labels = np.load(lbl_file)
        unique_speakers = np.unique(labels)
        for spk_id in unique_speakers:
            mask = labels == spk_id
            centroid = embeddings[mask].mean(axis=0)
            label = f"Speaker {int(spk_id)}"
            embed_dict[label] = centroid.tolist()
        return embed_dict

    print(f"  WARNING: No embedding files found in {nemo_dir}")
    print(f"  Searched: speaker_outputs/embeddings/")
    return {}


def store_embeddings(episode_id: str, embeddings: dict[str, list[float]]):
    """Store speaker embeddings in Supabase. Idempotent via upsert."""
    sb = get_supabase()

    for speaker_label, embedding in embeddings.items():
        # Check if already exists
        existing = (
            sb.table("speaker_embeddings")
            .select("id")
            .eq("episode_id", episode_id)
            .eq("speaker_label", speaker_label)
            .execute()
        )

        if existing.data:
            print(f"    {speaker_label}: already stored, skipping")
            continue

        sb.table("speaker_embeddings").insert({
            "episode_id": episode_id,
            "speaker_label": speaker_label,
            "embedding": embedding,
        }).execute()
        print(f"    {speaker_label}: stored ({len(embedding)}-dim)")


def main():
    parser = argparse.ArgumentParser(description="Extract speaker embeddings from NeMo output")
    parser.add_argument("--nemo-dir", required=True, help="Path to NeMo diarization output directory")
    parser.add_argument("--episode-id", help="Episode UUID (if processing single episode)")
    parser.add_argument("--channel", help="Channel slug (process all episodes with NeMo output)")
    args = parser.parse_args()

    if args.episode_id:
        print(f"Extracting embeddings for episode {args.episode_id}")
        embeddings = extract_speaker_embeddings_from_rttm(args.nemo_dir)
        if embeddings:
            store_embeddings(args.episode_id, embeddings)
            print(f"  Stored {len(embeddings)} speaker embeddings")
        else:
            print("  No embeddings found")
    else:
        print("Batch mode: scan NeMo output directories for all episodes")
        # Walk the nemo output directory looking for per-episode subdirectories
        nemo_path = Path(args.nemo_dir)
        sb = get_supabase()

        for episode_dir in sorted(nemo_path.iterdir()):
            if not episode_dir.is_dir():
                continue

            # Try to match directory name to youtube_id
            youtube_id = episode_dir.name
            result = sb.table("episodes").select("id").eq("youtube_id", youtube_id).execute()
            if not result.data:
                continue

            ep_id = result.data[0]["id"]
            print(f"\n[{youtube_id}]")
            embeddings = extract_speaker_embeddings_from_rttm(str(episode_dir))
            if embeddings:
                store_embeddings(ep_id, embeddings)


if __name__ == "__main__":
    main()
```

**Step 2: Verify the script loads without errors**

Run: `cd /path/to/vault && python -c "from scripts.agents.extract_embeddings import extract_speaker_embeddings_from_rttm; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/agents/extract_embeddings.py
git commit -m "feat: add Stage 1 — extract speaker embeddings from NeMo output"
```

---

## Task 4: Stage 2 — Map Speakers to People

**Files:**
- Create: `scripts/agents/map_speakers.py`

**Step 1: Write map_speakers.py**

```python
#!/usr/bin/env python3
"""
Stage 2: Map speaker embeddings to people identities.

Uses cosine similarity against a host anchor embedding to identify the
host speaker in each episode. The remaining speaker is matched to the
guest via the episode_guests junction table.

First run requires --bootstrap to manually confirm which speaker is the
host in the first episode.

Usage:
    python -m scripts.agents.map_speakers --channel diary-of-a-ceo --bootstrap
    python -m scripts.agents.map_speakers --channel diary-of-a-ceo
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone

import numpy as np

from scripts.agents.config import get_supabase, HOST_SIMILARITY_THRESHOLD


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug.strip("-")


def get_or_create_person(sb, name: str, photo_url: str = None) -> str:
    """Get or create a person in the global people table. Returns person_id."""
    slug = slugify(name)

    # Check by slug first
    result = sb.table("people").select("id").eq("slug", slug).execute()
    if result.data:
        return result.data[0]["id"]

    # Create new person
    row = sb.table("people").insert({
        "name": name,
        "slug": slug,
        "photo_url": photo_url,
    }).execute()

    person_id = row.data[0]["id"]
    print(f"  Created person: {name} ({person_id[:8]}...)")
    return person_id


def get_host_anchor(sb, channel_id: str) -> tuple[str, list[float]] | None:
    """
    Get the host's average embedding from already-mapped episodes.
    Returns (person_id, average_embedding) or None if no host mapped yet.
    """
    # Find the channel's host — the person who appears as host in the most episodes
    # We identify the host as the speaker_embedding with person_id that has the most entries
    result = sb.rpc("get_host_anchor", {"p_channel_id": channel_id}).execute()

    # Fallback: query manually
    # Get all mapped speaker embeddings for this channel's episodes
    episodes = (
        sb.table("episodes")
        .select("id")
        .eq("channel_id", channel_id)
        .not_.is_("processed_at", "null")
        .execute()
    )
    if not episodes.data:
        return None

    episode_ids = [ep["id"] for ep in episodes.data]

    # Get all mapped embeddings
    mapped = (
        sb.table("speaker_embeddings")
        .select("person_id, embedding")
        .not_.is_("person_id", "null")
        .in_("episode_id", episode_ids)
        .execute()
    )
    if not mapped.data:
        return None

    # Count occurrences per person — host appears most
    from collections import Counter
    person_counts = Counter(row["person_id"] for row in mapped.data)
    host_person_id = person_counts.most_common(1)[0][0]

    # Average the host's embeddings
    host_embeddings = [
        row["embedding"] for row in mapped.data
        if row["person_id"] == host_person_id
    ]

    avg_embedding = np.mean([np.array(e) for e in host_embeddings], axis=0).tolist()
    return host_person_id, avg_embedding


def bootstrap_host(sb, channel_id: str, channel_name: str) -> tuple[str, list[float]]:
    """
    Interactive bootstrap: show speaker embeddings from earliest episode,
    ask user to confirm which is the host.
    """
    # Get earliest processed episode with embeddings
    episodes = (
        sb.table("episodes")
        .select("id, youtube_id, title, published_at")
        .eq("channel_id", channel_id)
        .not_.is_("processed_at", "null")
        .order("published_at", desc=False)
        .execute()
    )

    for ep in episodes.data:
        embeddings = (
            sb.table("speaker_embeddings")
            .select("id, speaker_label, embedding")
            .eq("episode_id", ep["id"])
            .is_("person_id", "null")
            .execute()
        )
        if embeddings.data and len(embeddings.data) >= 2:
            break
    else:
        print("ERROR: No episodes with unmapped speaker embeddings found.")
        print("Run extract_embeddings.py first.")
        sys.exit(1)

    print(f"\nBootstrap: Identifying host for channel '{channel_name}'")
    print(f"Episode: {ep['title'][:80]}")
    print(f"YouTube: https://youtube.com/watch?v={ep['youtube_id']}")
    print()

    # Show first few segments to help identify speakers
    segments = (
        sb.table("segments")
        .select("speaker, text")
        .eq("episode_id", ep["id"])
        .order("position")
        .limit(10)
        .execute()
    )

    print("First 10 transcript turns:")
    for seg in segments.data:
        print(f"  [{seg['speaker']}] {seg['text'][:100]}")
    print()

    for i, emb in enumerate(embeddings.data):
        print(f"  {i}: {emb['speaker_label']}")

    choice = input(f"\nWhich speaker is the host? (0-{len(embeddings.data)-1}): ").strip()
    host_idx = int(choice)
    host_emb_row = embeddings.data[host_idx]

    # Get or ask for host name
    host_name = input(f"Host name (for '{channel_name}'): ").strip()

    # Create person and map
    host_person_id = get_or_create_person(sb, host_name)

    # Map the host embedding
    sb.table("speaker_embeddings").update({
        "person_id": host_person_id,
        "mapped_confidence": 1.0,
    }).eq("id", host_emb_row["id"]).execute()

    # Map the guest too if episode_guests has exactly one guest
    guest_embs = [e for e in embeddings.data if e["id"] != host_emb_row["id"]]
    ep_guests = (
        sb.table("episode_guests")
        .select("guest_id, guests(id, name, photo_url)")
        .eq("episode_id", ep["id"])
        .execute()
    )

    if len(guest_embs) == 1 and len(ep_guests.data) == 1:
        guest_data = ep_guests.data[0]["guests"]
        guest_person_id = get_or_create_person(
            sb, guest_data["name"], guest_data.get("photo_url")
        )
        sb.table("speaker_embeddings").update({
            "person_id": guest_person_id,
            "mapped_confidence": 1.0,
        }).eq("id", guest_embs[0]["id"]).execute()

        # Link guest to person
        sb.table("guests").update({
            "person_id": guest_person_id,
        }).eq("id", guest_data["id"]).execute()

        print(f"  Mapped guest: {guest_data['name']}")

    print(f"\nHost anchor set: {host_name}")
    return host_person_id, host_emb_row["embedding"]


def auto_map_episode(
    sb,
    episode_id: str,
    host_person_id: str,
    host_anchor: list[float],
    channel_id: str,
):
    """Auto-map speakers in an episode using host anchor similarity."""
    embeddings = (
        sb.table("speaker_embeddings")
        .select("id, speaker_label, embedding")
        .eq("episode_id", episode_id)
        .is_("person_id", "null")
        .execute()
    )

    if not embeddings.data:
        return  # Already mapped or no embeddings

    # Find which speaker is most similar to host
    best_sim = -1
    best_host_emb = None
    guest_embs = []

    for emb_row in embeddings.data:
        sim = cosine_similarity(host_anchor, emb_row["embedding"])
        if sim > best_sim:
            if best_host_emb:
                guest_embs.append(best_host_emb)
            best_sim = sim
            best_host_emb = emb_row
        else:
            guest_embs.append(emb_row)

    # Check confidence threshold
    if best_sim < HOST_SIMILARITY_THRESHOLD:
        print(f"    LOW CONFIDENCE: host similarity={best_sim:.3f} (threshold={HOST_SIMILARITY_THRESHOLD})")
        print(f"    Skipping — flag for manual review")
        return

    # Map host
    sb.table("speaker_embeddings").update({
        "person_id": host_person_id,
        "mapped_confidence": best_sim,
    }).eq("id", best_host_emb["id"]).execute()
    print(f"    Host: {best_host_emb['speaker_label']} (sim={best_sim:.3f})")

    # Map guest(s) via episode_guests
    ep_guests = (
        sb.table("episode_guests")
        .select("guest_id, guests(id, name, photo_url)")
        .eq("episode_id", episode_id)
        .execute()
    )

    if len(guest_embs) == 1 and len(ep_guests.data) == 1:
        guest_data = ep_guests.data[0]["guests"]
        guest_person_id = get_or_create_person(
            sb, guest_data["name"], guest_data.get("photo_url")
        )

        sb.table("speaker_embeddings").update({
            "person_id": guest_person_id,
            "mapped_confidence": 1.0,
        }).eq("id", guest_embs[0]["id"]).execute()

        # Link guest to person
        sb.table("guests").update({
            "person_id": guest_person_id,
        }).eq("id", guest_data["id"]).execute()

        print(f"    Guest: {guest_data['name']}")
    elif len(guest_embs) > 1:
        print(f"    WARNING: {len(guest_embs)} non-host speakers, {len(ep_guests.data)} known guests")
        print(f"    Multi-guest mapping not yet implemented — skipping guests")


def main():
    parser = argparse.ArgumentParser(description="Map speaker embeddings to people")
    parser.add_argument("--channel", required=True, help="Channel slug")
    parser.add_argument("--bootstrap", action="store_true", help="Interactive first-run host identification")
    args = parser.parse_args()

    sb = get_supabase()

    # Get channel
    channel = sb.table("channels").select("id, name").eq("slug", args.channel).execute()
    if not channel.data:
        print(f"ERROR: Channel '{args.channel}' not found")
        sys.exit(1)

    channel_id = channel.data[0]["id"]
    channel_name = channel.data[0]["name"]
    print(f"Channel: {channel_name} ({channel_id[:8]}...)")

    # Get or bootstrap host anchor
    if args.bootstrap:
        host_person_id, host_anchor = bootstrap_host(sb, channel_id, channel_name)
    else:
        result = get_host_anchor(sb, channel_id)
        if result is None:
            print("ERROR: No host anchor found. Run with --bootstrap first.")
            sys.exit(1)
        host_person_id, host_anchor = result

    # Process all episodes chronologically
    episodes = (
        sb.table("episodes")
        .select("id, youtube_id, title, published_at")
        .eq("channel_id", channel_id)
        .not_.is_("processed_at", "null")
        .order("published_at", desc=False)
        .execute()
    )

    total = len(episodes.data)
    mapped = 0

    for i, ep in enumerate(episodes.data, 1):
        print(f"\n[{i}/{total}] {ep['youtube_id']} — {ep['title'][:60]}")
        auto_map_episode(sb, ep["id"], host_person_id, host_anchor, channel_id)
        mapped += 1

    print(f"\nDone. Processed {mapped} episodes.")


if __name__ == "__main__":
    main()
```

**Step 2: Verify imports**

Run: `cd /path/to/vault && python -c "from scripts.agents.map_speakers import cosine_similarity; print(cosine_similarity([1,0,0], [1,0,0]))"`
Expected: `1.0`

**Step 3: Commit**

```bash
git add scripts/agents/map_speakers.py
git commit -m "feat: add Stage 2 — map speaker embeddings to people via voice fingerprinting"
```

---

## Task 5: Stage 3 — Build Agent Memory

**Files:**
- Create: `scripts/agents/build_memory.py`
- Create: `scripts/agents/prompts.py`

**Step 1: Write prompts.py — LLM prompt templates**

```python
#!/usr/bin/env python3
"""LLM prompt templates for agent memory synthesis."""

EMPTY_MEMORY = {
    "persona": {
        "communication_style": {
            "tone": "",
            "formality": "",
            "storytelling_tendency": "",
            "signature_phrases": [],
            "speech_patterns": [],
        },
        "personality_traits": {
            "openness": "",
            "conscientiousness": "",
            "extraversion": "",
            "agreeableness": "",
            "emotional_stability": "",
        },
        "expertise_domains": [],
    },
    "semantic_memory": {
        "beliefs": {},
        "frameworks": [],
        "recurring_themes": [],
        "references": [],
        "relationships": [],
    },
    "episodic_memory": [],
    "reflections": [],
    "contradictions": [],
    "growth_log": [],
}


TRIAGE_PROMPT = """You are evaluating a transcript turn from a podcast conversation.

Determine if this turn contains substantive content worth remembering about the speaker, or if it is filler/backchannel that adds no insight about who this person is.

Substantive: expresses an opinion, shares knowledge, tells a story, reveals a belief, describes an experience, makes an argument, shares a framework.
Filler: agreement sounds ("yeah", "exactly"), simple acknowledgments, very short reactions without content, repetitions of what the other person said.

Turn:
"{text}"

Respond with ONLY one word: SUBSTANTIVE or FILLER"""


MEMORY_MERGE_PROMPT = """You are building a living memory profile for {person_name} based on their podcast appearances. You are processing their conversations chronologically.

CURRENT MEMORY (what you know so far):
```json
{current_memory}
```

CONVERSATION CONTEXT (recent turns for context):
{context_turns}

NEW TURN BY {person_name}:
"{new_turn}"

EPISODE INFO:
- Episode ID: {episode_id}
- Date: {episode_date}
- Role: {role}

INSTRUCTIONS:
Update the memory JSON by MERGING insights from this new turn into the existing memory. Follow these rules:
1. MERGE, don't append blindly. If a belief already exists, update its confidence and last_reinforced.
2. Add new beliefs, frameworks, references, or relationships only if genuinely new.
3. Update communication_style and personality_traits based on cumulative evidence, not single turns.
4. Note contradictions if this turn contradicts a previously recorded belief.
5. Add to growth_log only if a meaningful shift is detected.
6. Keep signature_phrases and speech_patterns that are truly distinctive, not generic.
7. Do NOT add episodic_memory entries here — those are added separately per episode.
8. For reflections, only add high-importance cross-cutting insights (importance > 0.7).

Return ONLY the updated memory JSON. No explanation, no markdown fencing."""


EPISODE_SUMMARY_PROMPT = """Summarize {person_name}'s contribution to this podcast episode in 2-3 sentences. Focus on what they discussed, any key arguments or stories they shared, and notable moments.

Episode: {episode_title}
Date: {episode_date}
Role: {role}

Their turns (selected substantive ones):
{turns_text}

Also identify:
1. Up to 3 key moments (notable quotes or insights) as short strings
2. Up to 2 emotional peaks (topics where they showed strong feeling)

Respond as JSON:
{{"summary": "...", "key_moments": ["...", "..."], "emotional_peaks": [{{"topic": "...", "reaction": "..."}}]}}"""
```

**Step 2: Write build_memory.py**

```python
#!/usr/bin/env python3
"""
Stage 3: Build agent memory by replaying transcript turns chronologically.

For each person, processes their segments across all episodes (oldest first),
triaging filler vs substantive turns, then using an LLM to merge new
information into the person's structured memory.

Usage:
    python -m scripts.agents.build_memory --channel diary-of-a-ceo
    python -m scripts.agents.build_memory --channel diary-of-a-ceo --person-slug steven-bartlett
    python -m scripts.agents.build_memory --channel diary-of-a-ceo --resume
"""

import argparse
import copy
import json
import sys
import time
from datetime import datetime, timezone

import requests

from scripts.agents.config import (
    get_supabase,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    FILLER_MAX_WORDS,
    FILLER_PHRASES,
    CONTEXT_WINDOW_TURNS,
)
from scripts.agents.prompts import (
    EMPTY_MEMORY,
    TRIAGE_PROMPT,
    MEMORY_MERGE_PROMPT,
    EPISODE_SUMMARY_PROMPT,
)


def llm_call(prompt: str, temperature: float = 0.3) -> str:
    """Call local Ollama LLM. Returns raw text response."""
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


def is_filler_fast(text: str) -> bool:
    """Quick heuristic filler check — no LLM needed."""
    words = text.strip().split()
    if len(words) <= FILLER_MAX_WORDS:
        cleaned = text.strip().lower().rstrip(".!?,")
        if cleaned in FILLER_PHRASES:
            return True
    return False


def is_filler_llm(text: str) -> bool:
    """LLM-based filler triage for turns that pass the fast check."""
    prompt = TRIAGE_PROMPT.format(text=text[:500])
    result = llm_call(prompt, temperature=0.1)
    return "FILLER" in result.upper()


def merge_memory(
    person_name: str,
    current_memory: dict,
    context_turns: list[dict],
    new_turn: str,
    episode_id: str,
    episode_date: str,
    role: str,
) -> dict:
    """Call LLM to merge a new turn into existing memory."""
    # Format context turns
    context_text = ""
    for turn in context_turns[-CONTEXT_WINDOW_TURNS:]:
        speaker = turn.get("speaker", "Unknown")
        context_text += f"[{speaker}]: {turn['text'][:200]}\n"

    prompt = MEMORY_MERGE_PROMPT.format(
        person_name=person_name,
        current_memory=json.dumps(current_memory, indent=2),
        context_turns=context_text if context_text else "(start of episode)",
        new_turn=new_turn,
        episode_id=episode_id,
        episode_date=episode_date or "unknown",
        role=role,
    )

    response = llm_call(prompt, temperature=0.3)

    # Parse JSON response
    try:
        # Strip any markdown fencing the LLM might add despite instructions
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        clean = clean.strip()

        updated = json.loads(clean)
        return updated
    except json.JSONDecodeError:
        print(f"    WARNING: LLM returned invalid JSON, keeping previous memory")
        return current_memory


def generate_episode_summary(
    person_name: str,
    episode_title: str,
    episode_date: str,
    role: str,
    substantive_turns: list[str],
) -> dict:
    """Generate episodic memory entry for a completed episode."""
    turns_text = "\n".join(f"- {t[:200]}" for t in substantive_turns[:20])

    prompt = EPISODE_SUMMARY_PROMPT.format(
        person_name=person_name,
        episode_title=episode_title,
        episode_date=episode_date or "unknown",
        role=role,
        turns_text=turns_text,
    )

    response = llm_call(prompt, temperature=0.3)

    try:
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        return json.loads(clean.strip())
    except json.JSONDecodeError:
        return {
            "summary": f"Appeared on {episode_title}",
            "key_moments": [],
            "emotional_peaks": [],
        }


def process_person(sb, person_id: str, person_name: str, channel_id: str, resume: bool = False):
    """Process all episodes for a single person, building their memory."""

    # Load or create agent memory
    mem_row = (
        sb.table("agent_memories")
        .select("*")
        .eq("person_id", person_id)
        .execute()
    )

    if mem_row.data:
        memory = mem_row.data[0]["memory"]
        last_episode_id = mem_row.data[0].get("last_episode_id")
        last_position = mem_row.data[0].get("last_position")
        turns_processed = mem_row.data[0].get("turns_processed", 0)
        memory_version = mem_row.data[0].get("memory_version", 0)
    else:
        memory = copy.deepcopy(EMPTY_MEMORY)
        last_episode_id = None
        last_position = None
        turns_processed = 0
        memory_version = 0

        sb.table("agent_memories").insert({
            "person_id": person_id,
            "memory": memory,
        }).execute()

    # Get all episodes where this person has mapped speaker embeddings, chronologically
    mapped_episodes = (
        sb.table("speaker_embeddings")
        .select("episode_id, speaker_label, episodes(id, youtube_id, title, published_at)")
        .eq("person_id", person_id)
        .execute()
    )

    if not mapped_episodes.data:
        print(f"  No mapped episodes for {person_name}")
        return

    # Build episode list sorted by published_at
    ep_map = {}
    for row in mapped_episodes.data:
        ep = row["episodes"]
        ep_map[ep["id"]] = {
            "id": ep["id"],
            "youtube_id": ep["youtube_id"],
            "title": ep["title"],
            "published_at": ep["published_at"],
            "speaker_label": row["speaker_label"],
        }

    episodes = sorted(ep_map.values(), key=lambda x: x["published_at"] or "")

    # If resuming, skip to the right episode
    start_from = 0
    resume_position = None
    if resume and last_episode_id:
        for i, ep in enumerate(episodes):
            if ep["id"] == last_episode_id:
                start_from = i
                resume_position = last_position
                break

    # Determine role (host = appears in most episodes for this channel)
    is_host = len(episodes) > 1  # Simple heuristic; host has many episodes

    total_eps = len(episodes)
    for ep_idx, ep in enumerate(episodes[start_from:], start_from + 1):
        print(f"\n  [{ep_idx}/{total_eps}] {ep['youtube_id']} — {ep['title'][:50]}")

        role = "host" if is_host and len(episodes) > 3 else "guest"

        # Load segments for this episode, filtered to this person's speaker label
        segments = (
            sb.table("segments")
            .select("position, speaker, text")
            .eq("episode_id", ep["id"])
            .order("position")
            .execute()
        )

        if not segments.data:
            print(f"    No segments found")
            continue

        # Filter to person's turns and build context window
        person_turns = []
        context_window = []
        substantive_turns = []

        start_pos = resume_position + 1 if (ep["id"] == last_episode_id and resume_position) else 0

        for seg in segments.data:
            if seg["position"] < start_pos:
                context_window.append(seg)
                context_window = context_window[-CONTEXT_WINDOW_TURNS:]
                continue

            # Always add to context regardless of speaker
            context_window.append(seg)
            context_window = context_window[-CONTEXT_WINDOW_TURNS:]

            # Only process this person's turns
            if seg["speaker"] != ep["speaker_label"]:
                continue

            text = seg["text"].strip()
            if not text:
                continue

            # Triage: fast check first, then LLM if needed
            if is_filler_fast(text):
                continue

            if len(text.split()) <= 10 and is_filler_llm(text):
                continue

            # Substantive turn — merge into memory
            t_start = time.time()
            memory = merge_memory(
                person_name=person_name,
                current_memory=memory,
                context_turns=context_window[:-1],
                new_turn=text,
                episode_id=ep["id"],
                episode_date=ep["published_at"],
                role=role,
            )
            elapsed = time.time() - t_start

            turns_processed += 1
            memory_version += 1
            substantive_turns.append(text)

            # Save checkpoint every 10 turns
            if turns_processed % 10 == 0:
                sb.table("agent_memories").update({
                    "memory": memory,
                    "memory_version": memory_version,
                    "turns_processed": turns_processed,
                    "last_episode_id": ep["id"],
                    "last_position": seg["position"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("person_id", person_id).execute()

            if turns_processed % 50 == 0:
                print(f"    Checkpoint: {turns_processed} turns processed ({elapsed:.1f}s/turn)")

        # Episode complete — generate episode summary and add to episodic memory
        if substantive_turns:
            ep_summary = generate_episode_summary(
                person_name=person_name,
                episode_title=ep["title"],
                episode_date=ep["published_at"],
                role=role,
                substantive_turns=substantive_turns,
            )

            episodic_entry = {
                "episode_id": ep["id"],
                "date": ep["published_at"],
                "role": role,
                **ep_summary,
            }

            if "episodic_memory" not in memory:
                memory["episodic_memory"] = []
            memory["episodic_memory"].append(episodic_entry)

        # Save after each episode
        sb.table("agent_memories").update({
            "memory": memory,
            "memory_version": memory_version,
            "turns_processed": turns_processed,
            "last_episode_id": ep["id"],
            "last_position": segments.data[-1]["position"] if segments.data else 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("person_id", person_id).execute()

        print(f"    Done: {len(substantive_turns)} substantive turns, version {memory_version}")

    print(f"\n  Total: {turns_processed} turns across {total_eps} episodes")


def main():
    parser = argparse.ArgumentParser(description="Build agent memory from transcripts")
    parser.add_argument("--channel", required=True, help="Channel slug")
    parser.add_argument("--person-slug", help="Process single person by slug")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    args = parser.parse_args()

    sb = get_supabase()

    # Get channel
    channel = sb.table("channels").select("id, name").eq("slug", args.channel).execute()
    if not channel.data:
        print(f"ERROR: Channel '{args.channel}' not found")
        sys.exit(1)

    channel_id = channel.data[0]["id"]
    print(f"Channel: {channel.data[0]['name']}")

    # Check Ollama is running
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        if not any(OLLAMA_MODEL.split(":")[0] in m for m in models):
            print(f"WARNING: Model '{OLLAMA_MODEL}' not found in Ollama. Available: {models}")
            print(f"Run: ollama pull {OLLAMA_MODEL}")
            sys.exit(1)
    except requests.ConnectionError:
        print(f"ERROR: Cannot connect to Ollama at {OLLAMA_BASE_URL}")
        print("Start Ollama first: ollama serve")
        sys.exit(1)

    # Get people to process
    if args.person_slug:
        people = sb.table("people").select("id, name, slug").eq("slug", args.person_slug).execute()
    else:
        # All people who have mapped speaker embeddings in this channel's episodes
        episode_ids_result = (
            sb.table("episodes")
            .select("id")
            .eq("channel_id", channel_id)
            .execute()
        )
        episode_ids = [ep["id"] for ep in episode_ids_result.data]

        if not episode_ids:
            print("No episodes found for this channel")
            sys.exit(0)

        mapped = (
            sb.table("speaker_embeddings")
            .select("person_id")
            .not_.is_("person_id", "null")
            .in_("episode_id", episode_ids)
            .execute()
        )

        person_ids = list(set(row["person_id"] for row in mapped.data))
        if not person_ids:
            print("No mapped speakers found. Run map_speakers.py first.")
            sys.exit(1)

        people = sb.table("people").select("id, name, slug").in_("id", person_ids).execute()

    if not people.data:
        print("No people found to process")
        sys.exit(1)

    print(f"Processing {len(people.data)} people\n")

    for person in people.data:
        print(f"\n{'='*60}")
        print(f"Person: {person['name']} ({person['slug']})")
        print(f"{'='*60}")

        try:
            process_person(sb, person["id"], person["name"], channel_id, resume=args.resume)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            continue


if __name__ == "__main__":
    main()
```

**Step 3: Verify imports**

Run: `cd /path/to/vault && python -c "from scripts.agents.build_memory import is_filler_fast; print(is_filler_fast('yeah'))"`
Expected: `True`

**Step 4: Commit**

```bash
git add scripts/agents/prompts.py scripts/agents/build_memory.py
git commit -m "feat: add Stage 3 — build agent memory with LLM-based merge and triage"
```

---

## Task 6: Stage 4 — Export Memory & Runner

**Files:**
- Create: `scripts/agents/export_memory.py`
- Create: `scripts/agents/run_pipeline.py`

**Step 1: Write export_memory.py**

```python
#!/usr/bin/env python3
"""
Stage 4: Export agent memories to JSON files for inspection and debugging.

Usage:
    python -m scripts.agents.export_memory --channel diary-of-a-ceo
    python -m scripts.agents.export_memory --person-slug steven-bartlett
"""

import argparse
import json
import sys
from pathlib import Path

from scripts.agents.config import get_supabase, ROOT_DIR


def export_person(sb, person_id: str, person_name: str, person_slug: str, output_dir: Path):
    """Export a single person's agent memory to JSON."""
    mem = (
        sb.table("agent_memories")
        .select("memory, memory_version, turns_processed, updated_at")
        .eq("person_id", person_id)
        .execute()
    )

    if not mem.data:
        print(f"  {person_name}: no memory found, skipping")
        return

    row = mem.data[0]
    export = {
        "person_id": person_id,
        "name": person_name,
        "slug": person_slug,
        "memory_version": row["memory_version"],
        "turns_processed": row["turns_processed"],
        "updated_at": row["updated_at"],
        "memory": row["memory"],
    }

    output_file = output_dir / f"{person_slug}.json"
    with open(output_file, "w") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    print(f"  {person_name}: exported (v{row['memory_version']}, {row['turns_processed']} turns)")


def main():
    parser = argparse.ArgumentParser(description="Export agent memories to JSON")
    parser.add_argument("--channel", help="Channel slug (export all people)")
    parser.add_argument("--person-slug", help="Export single person")
    parser.add_argument("--output-dir", help="Output directory", default="data/agents")
    args = parser.parse_args()

    sb = get_supabase()
    output_dir = ROOT_DIR / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.person_slug:
        person = sb.table("people").select("id, name, slug").eq("slug", args.person_slug).execute()
        if not person.data:
            print(f"Person '{args.person_slug}' not found")
            sys.exit(1)
        people = person.data
    elif args.channel:
        # Get all people with memories
        all_memories = sb.table("agent_memories").select("person_id, people(id, name, slug)").execute()
        people = [row["people"] for row in all_memories.data if row.get("people")]
    else:
        print("Provide --channel or --person-slug")
        sys.exit(1)

    print(f"Exporting {len(people)} agent memories to {output_dir}/\n")

    for person in people:
        export_person(sb, person["id"], person["name"], person["slug"], output_dir)

    print(f"\nDone.")


if __name__ == "__main__":
    main()
```

**Step 2: Write run_pipeline.py**

```python
#!/usr/bin/env python3
"""
People Agents Pipeline Runner.

Orchestrates the four pipeline stages in sequence.

Usage:
    python -m scripts.agents.run_pipeline --channel diary-of-a-ceo --nemo-dir /path/to/output
    python -m scripts.agents.run_pipeline --channel diary-of-a-ceo --stage build_memory
    python -m scripts.agents.run_pipeline --channel diary-of-a-ceo --stage build_memory --resume
"""

import argparse
import subprocess
import sys
import time


def run_stage(stage_module: str, args: list[str]):
    """Run a pipeline stage as a subprocess."""
    cmd = [sys.executable, "-m", stage_module] + args
    print(f"\n{'='*60}")
    print(f"Stage: {stage_module}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    t_start = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - t_start

    if result.returncode != 0:
        print(f"\nERROR: {stage_module} exited with code {result.returncode}")
        print(f"Elapsed: {elapsed:.1f}s")
        sys.exit(result.returncode)

    print(f"\nCompleted {stage_module} in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="People Agents Pipeline Runner")
    parser.add_argument("--channel", required=True, help="Channel slug")
    parser.add_argument("--nemo-dir", help="NeMo output directory (required for extract stage)")
    parser.add_argument("--stage", choices=["extract", "map", "build", "export", "all"], default="all")
    parser.add_argument("--bootstrap", action="store_true", help="Bootstrap host identification")
    parser.add_argument("--resume", action="store_true", help="Resume build_memory from checkpoint")
    parser.add_argument("--person-slug", help="Process single person (for build/export)")
    args = parser.parse_args()

    stages = {
        "extract": ("scripts.agents.extract_embeddings", ["--nemo-dir", args.nemo_dir or ""]),
        "map": ("scripts.agents.map_speakers", ["--channel", args.channel] + (["--bootstrap"] if args.bootstrap else [])),
        "build": ("scripts.agents.build_memory", ["--channel", args.channel] + (["--resume"] if args.resume else []) + (["--person-slug", args.person_slug] if args.person_slug else [])),
        "export": ("scripts.agents.export_memory", ["--channel", args.channel]),
    }

    if args.stage == "all":
        if not args.nemo_dir:
            print("ERROR: --nemo-dir required when running all stages")
            sys.exit(1)
        for stage_name in ["extract", "map", "build", "export"]:
            run_stage(*stages[stage_name])
    else:
        if args.stage == "extract" and not args.nemo_dir:
            print("ERROR: --nemo-dir required for extract stage")
            sys.exit(1)
        module, stage_args = stages[args.stage]
        run_stage(module, stage_args)


if __name__ == "__main__":
    main()
```

**Step 3: Commit**

```bash
git add scripts/agents/export_memory.py scripts/agents/run_pipeline.py
git commit -m "feat: add Stage 4 export and pipeline runner for people agents"
```

---

## Task 7: Frontend — People List Page

**Files:**
- Modify: `app/[channel]/people/page.tsx`

**Step 1: Read the current people page**

Read: `app/[channel]/people/page.tsx`
Understand existing placeholder structure.

**Step 2: Replace with functional people list**

```tsx
import { createServerClient } from '@/lib/supabase';
import Link from 'next/link';
import Image from 'next/image';

export default async function PeoplePage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const supabase = createServerClient();

  // Get channel
  const { data: channelData } = await supabase
    .from('channels')
    .select('id, name')
    .eq('slug', channel)
    .single();

  if (!channelData) {
    return <div className="p-8 text-center text-neutral-500">Channel not found</div>;
  }

  // Get guests with linked people who have agent memories
  const { data: guests } = await supabase
    .from('guests')
    .select(`
      id, name, slug, bio, photo_url, person_id,
      people!guests_person_id_fkey(id, name, slug,
        agent_memories(memory_version, turns_processed, updated_at)
      )
    `)
    .eq('channel_id', channelData.id)
    .not('person_id', 'is', null)
    .order('name');

  // Also get the host (person who appears in most speaker_embeddings)
  const { data: allPeople } = await supabase
    .from('people')
    .select(`
      id, name, slug, photo_url,
      agent_memories(memory_version, turns_processed, updated_at)
    `)
    .not('slug', 'is', null);

  // Merge: guests with memory + any people not in guests (like host)
  const peopleWithMemory = (allPeople || []).filter(
    (p: any) => p.agent_memories && p.agent_memories.length > 0
  );

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">People</h1>
      <p className="text-neutral-500 mb-8">
        AI-generated persona profiles built from podcast transcripts
      </p>

      {peopleWithMemory.length === 0 ? (
        <div className="text-center py-16 text-neutral-500">
          <p className="text-lg mb-2">No agent profiles yet</p>
          <p className="text-sm">
            Run the people agents pipeline to build persona profiles from transcripts.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {peopleWithMemory.map((person: any) => {
            const mem = person.agent_memories?.[0];
            const memory = mem ? JSON.parse(typeof mem === 'string' ? mem : JSON.stringify(mem)) : null;
            return (
              <Link
                key={person.id}
                href={`/${channel}/people/${person.slug}`}
                className="border border-neutral-200 dark:border-neutral-800 rounded-xl p-5 hover:border-neutral-400 dark:hover:border-neutral-600 transition-colors"
              >
                <div className="flex items-center gap-4 mb-3">
                  {person.photo_url ? (
                    <Image
                      src={person.photo_url}
                      alt={person.name}
                      width={48}
                      height={48}
                      className="rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-lg font-semibold">
                      {person.name.charAt(0)}
                    </div>
                  )}
                  <div>
                    <h3 className="font-semibold">{person.name}</h3>
                    <p className="text-xs text-neutral-500">
                      {mem?.turns_processed || 0} turns processed
                    </p>
                  </div>
                </div>
                {mem && (
                  <p className="text-sm text-neutral-600 dark:text-neutral-400">
                    v{mem.memory_version} &middot; Updated{' '}
                    {mem.updated_at
                      ? new Date(mem.updated_at).toLocaleDateString()
                      : 'never'}
                  </p>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

**Step 3: Verify page renders**

Run: `npm run dev` and navigate to `http://localhost:3000/{channel-slug}/people`
Expected: Shows "No agent profiles yet" or list of people with memories.

**Step 4: Commit**

```bash
git add app/[channel]/people/page.tsx
git commit -m "feat: replace people page placeholder with agent profile grid"
```

---

## Task 8: Frontend — Character Memory Page

**Files:**
- Create: `app/[channel]/people/[slug]/page.tsx`

**Step 1: Write the Character Memory Page**

```tsx
import { createServerClient } from '@/lib/supabase';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';

interface MemorySchema {
  persona?: {
    communication_style?: {
      tone?: string;
      formality?: string;
      storytelling_tendency?: string;
      signature_phrases?: string[];
      speech_patterns?: string[];
    };
    personality_traits?: Record<string, string>;
    expertise_domains?: { domain: string; depth: string }[];
  };
  semantic_memory?: {
    beliefs?: Record<string, { stance: string; confidence: string }>;
    frameworks?: { name: string; description: string; source_episode?: string }[];
    recurring_themes?: string[];
    references?: { type: string; name: string; sentiment?: string; context?: string }[];
    relationships?: { person: string; nature: string; context?: string }[];
  };
  episodic_memory?: {
    episode_id: string;
    date?: string;
    role: string;
    summary: string;
    key_moments?: string[];
    emotional_peaks?: { topic: string; reaction: string }[];
  }[];
  reflections?: {
    insight: string;
    importance: number;
    expert_lens?: string;
    derived_from?: string[];
  }[];
  contradictions?: {
    topic: string;
    earlier_stance: string;
    later_stance: string;
    resolution?: string;
  }[];
  growth_log?: {
    dimension: string;
    description: string;
    from_episode?: string;
    to_episode?: string;
  }[];
}

function Badge({ children, variant = 'default' }: { children: React.ReactNode; variant?: string }) {
  const colors: Record<string, string> = {
    default: 'bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300',
    high: 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300',
    medium: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300',
    low: 'bg-neutral-100 dark:bg-neutral-800 text-neutral-500',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colors[variant] || colors.default}`}>
      {children}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold mb-4 border-b border-neutral-200 dark:border-neutral-800 pb-2">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default async function PersonPage({
  params,
}: {
  params: Promise<{ channel: string; slug: string }>;
}) {
  const { channel, slug } = await params;
  const supabase = createServerClient();

  // Get person
  const { data: person } = await supabase
    .from('people')
    .select('id, name, slug, photo_url')
    .eq('slug', slug)
    .single();

  if (!person) return notFound();

  // Get agent memory
  const { data: memRow } = await supabase
    .from('agent_memories')
    .select('memory, memory_version, turns_processed, updated_at')
    .eq('person_id', person.id)
    .single();

  if (!memRow) {
    return (
      <div className="p-8 text-center text-neutral-500">
        <h1 className="text-2xl font-bold mb-4">{person.name}</h1>
        <p>No agent memory built yet. Run the pipeline first.</p>
      </div>
    );
  }

  const memory: MemorySchema = memRow.memory;
  const persona = memory.persona;
  const semantic = memory.semantic_memory;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-5 mb-8">
        {person.photo_url ? (
          <Image
            src={person.photo_url}
            alt={person.name}
            width={80}
            height={80}
            className="rounded-full object-cover"
          />
        ) : (
          <div className="w-20 h-20 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-2xl font-bold">
            {person.name.charAt(0)}
          </div>
        )}
        <div>
          <h1 className="text-3xl font-bold">{person.name}</h1>
          <p className="text-sm text-neutral-500 mt-1">
            {memRow.turns_processed} turns processed &middot; v{memRow.memory_version}
            &middot; {memory.episodic_memory?.length || 0} episodes
          </p>
        </div>
      </div>

      {/* Persona */}
      {persona && (
        <Section title="Persona">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Communication Style */}
            {persona.communication_style && (
              <div>
                <h3 className="text-sm font-semibold text-neutral-500 mb-2">Communication Style</h3>
                <div className="space-y-1 text-sm">
                  {persona.communication_style.tone && (
                    <p>Tone: <Badge>{persona.communication_style.tone}</Badge></p>
                  )}
                  {persona.communication_style.formality && (
                    <p>Formality: <Badge>{persona.communication_style.formality}</Badge></p>
                  )}
                  {persona.communication_style.storytelling_tendency && (
                    <p>Storytelling: <Badge>{persona.communication_style.storytelling_tendency}</Badge></p>
                  )}
                </div>
                {persona.communication_style.signature_phrases?.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs text-neutral-500 mb-1">Signature Phrases</p>
                    <div className="flex flex-wrap gap-1">
                      {persona.communication_style.signature_phrases.map((p, i) => (
                        <Badge key={i}>&ldquo;{p}&rdquo;</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Personality Traits */}
            {persona.personality_traits && (
              <div>
                <h3 className="text-sm font-semibold text-neutral-500 mb-2">Personality Traits (Big Five)</h3>
                <div className="space-y-1 text-sm">
                  {Object.entries(persona.personality_traits).map(([trait, level]) => (
                    level && (
                      <p key={trait} className="capitalize">
                        {trait.replace(/_/g, ' ')}: <Badge variant={level}>{level}</Badge>
                      </p>
                    )
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Expertise */}
          {persona.expertise_domains && persona.expertise_domains.length > 0 && (
            <div className="mt-4">
              <h3 className="text-sm font-semibold text-neutral-500 mb-2">Expertise</h3>
              <div className="flex flex-wrap gap-2">
                {persona.expertise_domains.map((d, i) => (
                  <Badge key={i} variant={d.depth === 'deep' ? 'high' : d.depth === 'moderate' ? 'medium' : 'low'}>
                    {d.domain} ({d.depth})
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </Section>
      )}

      {/* Beliefs & Frameworks */}
      {semantic && (
        <Section title="Beliefs & Frameworks">
          {semantic.beliefs && Object.keys(semantic.beliefs).length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-semibold text-neutral-500 mb-2">Beliefs</h3>
              <div className="space-y-2">
                {Object.entries(semantic.beliefs).map(([topic, belief]) => (
                  <div key={topic} className="border border-neutral-200 dark:border-neutral-800 rounded-lg p-3">
                    <p className="font-medium text-sm capitalize">{topic.replace(/_/g, ' ')}</p>
                    <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{belief.stance}</p>
                    {belief.confidence && (
                      <Badge variant={belief.confidence}>{belief.confidence} confidence</Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {semantic.frameworks && semantic.frameworks.length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-semibold text-neutral-500 mb-2">Frameworks</h3>
              <div className="space-y-2">
                {semantic.frameworks.map((fw, i) => (
                  <div key={i} className="border border-neutral-200 dark:border-neutral-800 rounded-lg p-3">
                    <p className="font-medium text-sm">{fw.name}</p>
                    <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{fw.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {semantic.recurring_themes && semantic.recurring_themes.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-neutral-500 mb-2">Recurring Themes</h3>
              <div className="flex flex-wrap gap-2">
                {semantic.recurring_themes.map((theme, i) => (
                  <Badge key={i}>{theme}</Badge>
                ))}
              </div>
            </div>
          )}
        </Section>
      )}

      {/* Reflections */}
      {memory.reflections && memory.reflections.length > 0 && (
        <Section title="Key Reflections">
          <div className="space-y-3">
            {memory.reflections
              .sort((a, b) => (b.importance || 0) - (a.importance || 0))
              .slice(0, 10)
              .map((ref, i) => (
                <div key={i} className="border-l-2 border-blue-400 pl-3 py-1">
                  <p className="text-sm">{ref.insight}</p>
                  <div className="flex gap-2 mt-1">
                    {ref.expert_lens && <Badge>{ref.expert_lens}</Badge>}
                    <span className="text-xs text-neutral-500">
                      importance: {(ref.importance * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
          </div>
        </Section>
      )}

      {/* Contradictions */}
      {memory.contradictions && memory.contradictions.length > 0 && (
        <Section title="Contradictions & Evolution">
          <div className="space-y-3">
            {memory.contradictions.map((c, i) => (
              <div key={i} className="border border-amber-200 dark:border-amber-800 rounded-lg p-3 bg-amber-50/50 dark:bg-amber-900/10">
                <p className="font-medium text-sm">{c.topic}</p>
                <div className="grid grid-cols-2 gap-4 mt-2 text-sm">
                  <div>
                    <p className="text-xs text-neutral-500">Earlier</p>
                    <p className="text-neutral-600 dark:text-neutral-400">{c.earlier_stance}</p>
                  </div>
                  <div>
                    <p className="text-xs text-neutral-500">Later</p>
                    <p className="text-neutral-600 dark:text-neutral-400">{c.later_stance}</p>
                  </div>
                </div>
                {c.resolution && <Badge variant={c.resolution === 'evolved' ? 'high' : 'medium'}>{c.resolution}</Badge>}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Growth Timeline */}
      {memory.growth_log && memory.growth_log.length > 0 && (
        <Section title="Growth Timeline">
          <div className="border-l-2 border-neutral-300 dark:border-neutral-700 ml-2 space-y-4">
            {memory.growth_log.map((entry, i) => (
              <div key={i} className="pl-4 relative">
                <div className="absolute -left-[9px] top-1 w-4 h-4 rounded-full bg-blue-500 border-2 border-white dark:border-neutral-900" />
                <p className="text-sm font-medium capitalize">{entry.dimension.replace(/_/g, ' ')}</p>
                <p className="text-sm text-neutral-600 dark:text-neutral-400">{entry.description}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Episode Appearances */}
      {memory.episodic_memory && memory.episodic_memory.length > 0 && (
        <Section title="Episode Appearances">
          <div className="space-y-3">
            {memory.episodic_memory.map((ep, i) => (
              <div key={i} className="border border-neutral-200 dark:border-neutral-800 rounded-lg p-3">
                <div className="flex justify-between items-start">
                  <p className="text-sm font-medium">{ep.summary}</p>
                  <Badge>{ep.role}</Badge>
                </div>
                <p className="text-xs text-neutral-500 mt-1">
                  {ep.date ? new Date(ep.date).toLocaleDateString() : 'Date unknown'}
                </p>
                {ep.key_moments && ep.key_moments.length > 0 && (
                  <div className="mt-2">
                    {ep.key_moments.map((m, j) => (
                      <p key={j} className="text-xs text-neutral-600 dark:text-neutral-400 italic">
                        &ldquo;{m}&rdquo;
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Back link */}
      <div className="mt-8 pt-4 border-t border-neutral-200 dark:border-neutral-800">
        <Link href={`/${channel}/people`} className="text-sm text-blue-500 hover:underline">
          &larr; All People
        </Link>
      </div>
    </div>
  );
}
```

**Step 2: Verify page renders**

Run: `npm run dev` and navigate to `http://localhost:3000/{channel-slug}/people/{person-slug}`
Expected: Shows person profile with memory sections, or "No agent memory built yet" if not processed.

**Step 3: Commit**

```bash
git add app/[channel]/people/[slug]/page.tsx
git commit -m "feat: add Character Memory Page rendering agent persona from JSONB"
```

---

## Task 9: Update .gitignore and Add Data Directory

**Files:**
- Modify: `.gitignore`

**Step 1: Add agent data export directory to gitignore**

Add to `.gitignore`:
```
data/agents/
```

**Step 2: Create the data directory with a .gitkeep**

```bash
mkdir -p data/agents
touch data/agents/.gitkeep
```

**Step 3: Commit**

```bash
git add .gitignore data/agents/.gitkeep
git commit -m "chore: add data/agents directory for exported agent memories"
```

---

## Task 10: End-to-End Smoke Test

**Step 1: Run the migration**

Run: `psql $DATABASE_URL -f supabase/migrations/006_people_agents.sql`
Expected: All tables created successfully.

**Step 2: Verify the pipeline scripts load**

Run:
```bash
python -m scripts.agents.extract_embeddings --help
python -m scripts.agents.map_speakers --help
python -m scripts.agents.build_memory --help
python -m scripts.agents.export_memory --help
python -m scripts.agents.run_pipeline --help
```
Expected: All show help text without errors.

**Step 3: Verify frontend pages compile**

Run: `npm run build`
Expected: Build succeeds with no TypeScript errors.

**Step 4: Manual integration test**

If NeMo output and Ollama with GLM 4.7 are available:
```bash
# Stage 1: Extract embeddings from a single episode
python -m scripts.agents.extract_embeddings --nemo-dir /path/to/nemo/output --episode-id <uuid>

# Stage 2: Bootstrap host identification
python -m scripts.agents.map_speakers --channel diary-of-a-ceo --bootstrap

# Stage 3: Build memory for one person (limit to 1 episode for testing)
python -m scripts.agents.build_memory --channel diary-of-a-ceo --person-slug <slug>

# Stage 4: Export and inspect
python -m scripts.agents.export_memory --person-slug <slug>
cat data/agents/<slug>.json | python -m json.tool | head -50
```

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete people agents pipeline and character memory page"
```

---

Plan complete and saved to `docs/plans/2026-03-08-people-agents-implementation.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open new session with executing-plans, batch execution with checkpoints

Which approach?