"""Stage 3 — EXTRACT: Triage, chunk, Graphiti ingest."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.agents.config import (
    get_supabase,
    FILLER_PHRASES,
    FILLER_MAX_WORDS,
    CHUNK_DURATION,
    CHUNK_OVERLAP,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    NEO4J_DATABASE,
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL,
)
from scripts.agents.llm import llm_call
from scripts.agents.prompts import TRIAGE_PROMPT

# Add vendor/graphiti to path for podcast_vault imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "vendor" / "graphiti"))

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
from podcast_vault.show_notes import extract_show_note_links


# ---------------------------------------------------------------------------
# Seed: pre-create host + podcast entities
# ---------------------------------------------------------------------------

async def seed_host_and_podcast(
    host_name: str,
    host_bio: str,
    podcast_name: str,
    podcast_description: str,
    first_episode_date: str | None,
):
    """Pre-create host and podcast entities so episodes link to them correctly."""
    import time as _time
    from graphiti_core import Graphiti
    from graphiti_core.llm_client import OpenAIClient, LLMConfig
    from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    llm_config = LLMConfig(
        api_key=LLM_API_KEY, base_url=LLM_BASE_URL,
        model=LLM_MODEL, small_model=LLM_MODEL,
    )
    llm_client = OpenAIClient(llm_config)
    embedder = OpenAIEmbedder(OpenAIEmbedderConfig(
        api_key=LLM_API_KEY, base_url=LLM_BASE_URL,
    ))
    graph_driver = Neo4jDriver(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, database=NEO4J_DATABASE)

    graphiti = Graphiti(llm_client=llm_client, embedder=embedder, graph_driver=graph_driver)

    ref_time = datetime.fromisoformat(first_episode_date) if first_episode_date else datetime.now(timezone.utc)

    seed_body = f"""{host_name} is a person who hosts {podcast_name}. {host_bio}

{podcast_name}: {podcast_description}

{host_name} hosts {podcast_name}."""

    try:
        t0 = _time.time()
        await graphiti.add_episode(
            name=f"seed-{podcast_name.lower().replace(' ', '-')}",
            episode_body=seed_body,
            source_description=f"Seed profile for {podcast_name} hosted by {host_name}",
            group_id=build_group_id(podcast_name),
            entity_types=ENTITY_TYPES,
            edge_types=EDGE_TYPES,
            edge_type_map=EDGE_TYPE_MAP,
            custom_extraction_instructions=GRAPHITI_EXTRACTION_INSTRUCTIONS,
            reference_time=ref_time,
        )
        print(f"    Seeded host + podcast in {_time.time() - t0:.1f}s")
    finally:
        await graphiti.close()


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
    """Filter out filler turns. Heuristic only — no LLM calls.

    Removes obvious filler (<=5 words, all filler phrases).
    Everything else passes through — Graphiti extraction naturally
    ignores low-content turns during entity/edge extraction.
    """
    return [
        seg for seg in segments
        if not is_heuristic_filler(seg.get("clean_text") or seg["text"])
    ]


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
    from graphiti_core.llm_client import OpenAIClient, LLMConfig
    from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.driver.neo4j_driver import Neo4jDriver

    llm_config = LLMConfig(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        small_model=LLM_MODEL,
    )
    llm_client = OpenAIClient(llm_config)

    embedder_config = OpenAIEmbedderConfig(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
    )
    embedder = OpenAIEmbedder(embedder_config)

    graph_driver = Neo4jDriver(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, database=NEO4J_DATABASE)

    graphiti = Graphiti(
        llm_client=llm_client,
        embedder=embedder,
        graph_driver=graph_driver,
    )

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
                entity_types=ENTITY_TYPES,
                edge_types=EDGE_TYPES,
                edge_type_map=EDGE_TYPE_MAP,
                custom_extraction_instructions=GRAPHITI_EXTRACTION_INSTRUCTIONS,
                reference_time=datetime.fromisoformat(published_at) if published_at else datetime.now(timezone.utc),
            )

            print(f"    Chunk {chunk_idx + 1}/{len(chunks)} ingested "
                  f"({format_timestamp(chunk_start)}-{format_timestamp(chunk_end)})")

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
