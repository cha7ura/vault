"""Stage 3 — EXTRACT: Triage, chunk, wiki extraction."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.agents.config import (
    FILLER_PHRASES,
    FILLER_MAX_WORDS,
    CHUNK_DURATION,
    CHUNK_OVERLAP,
    WIKI_DIR,
)
from scripts.agents.db import fetch_all, fetch_one, execute
from scripts.agents.wiki_extract import extract_chunk_json, write_episode_summary
from scripts.agents.wiki_writer import merge_to_wiki, read_index, load_page


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
    Everything else passes through — wiki extraction naturally
    ignores low-content turns during entity/edge extraction.
    """
    return [
        seg for seg in segments
        if not is_heuristic_filler(seg.get("clean_text") or seg["text"])
    ]


# ---------------------------------------------------------------------------
# 3b. Chunk
# ---------------------------------------------------------------------------

def build_graphiti_episode_body(segments: list[dict]) -> str:
    """Format a chunk of segments for wiki extraction."""
    lines = []
    for seg in segments:
        text = seg.get("clean_text") or seg["text"]
        speaker = seg.get("speaker_name") or seg.get("speaker", "Unknown")
        start = int(seg["start_time"])
        end = int(seg["end_time"])
        lines.append(f"[{start}s-{end}s] {speaker}: {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3c. Wiki Extraction
# ---------------------------------------------------------------------------

def extract_and_write_episode(
    episode_id: str,
    youtube_id: str,
    episode_title: str,
    published_at: str | None,
    segments: list[dict],
    speaker_map: dict[str, dict],
    wiki_dir: Path,
) -> list[Path]:
    """Chunk segments, extract JSON from each chunk via Groq, write to wiki.
    Returns list of touched wiki page paths (used for episode summary).
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "vendor" / "graphiti"))
    from podcast_vault.extract import TranscriptSegment, chunk_transcript

    # Add speaker names to segments
    for seg in segments:
        info = speaker_map.get(seg["speaker"], {})
        seg["speaker_name"] = info.get("name", seg["speaker"])

    # Convert to TranscriptSegments for chunking
    ts_segments = [
        TranscriptSegment(
            text=seg.get("clean_text") or seg["text"],
            start_time=seg["start_time"],
            end_time=seg["end_time"],
        )
        for seg in segments
    ]
    chunks = chunk_transcript(ts_segments, CHUNK_DURATION, CHUNK_OVERLAP)

    all_touched: list[Path] = []

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

        chunk_text = build_graphiti_episode_body(chunk_segs)

        # Read current index for deduplication
        index_content = (wiki_dir / "_index.md").read_text(encoding="utf-8")

        # Extract entities + edges from this chunk
        extraction = extract_chunk_json(chunk_text, index_content)

        # Stamp youtube_id on all edges and observations that lack an episode
        for edge in extraction.get("edges", []):
            edge.setdefault("episode", youtube_id)
        for obs in extraction.get("observations", []):
            obs.setdefault("episode", youtube_id)

        # Write to wiki (deterministic)
        touched = merge_to_wiki(extraction, youtube_id, wiki_dir)
        all_touched.extend(touched)

        print(
            f"    Chunk {chunk_idx + 1}/{len(chunks)} "
            f"({int(chunk_start)}s-{int(chunk_end)}s): "
            f"{len(extraction.get('entities', []))} entities, "
            f"{len(extraction.get('edges', []))} edges"
        )

    return all_touched


# ---------------------------------------------------------------------------
# 3d. Show Notes
# ---------------------------------------------------------------------------

def parse_show_notes(description: str | None) -> dict:
    """Parse show notes URLs from episode description."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "vendor" / "graphiti"))
    from podcast_vault.show_notes import extract_show_note_links

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
    """Run Stage 3 wiki extraction for a single episode."""
    wiki_dir = WIKI_DIR

    # Fetch episode
    episode = fetch_one("SELECT * FROM episodes WHERE id=%s", (episode_id,))
    if not episode:
        raise ValueError(f"Episode not found: {episode_id}")
    youtube_id = episode["youtube_id"]
    title = episode.get("title", "")
    description = episode.get("description", "")
    published_at = episode.get("published_at")
    intro_end = episode.get("intro_end_position") or 0

    # Fetch all segments
    all_segments = fetch_all(
        """
        SELECT id, position, speaker, text, clean_text, start_time, end_time
        FROM segments
        WHERE episode_id=%s
        ORDER BY position
        """,
        (episode_id,),
    )

    # Filter to content (after intro)
    content_segments = [s for s in all_segments if (s["position"] or 0) >= intro_end]

    # 3a. Triage
    substantive = triage_segments(content_segments)
    print(f"    Triage: {len(substantive)}/{len(content_segments)} substantive")

    # 3b + 3c + 3d. Chunk → extract → write to wiki
    touched_paths: list[Path] = []
    if substantive:
        touched_paths = extract_and_write_episode(
            episode_id=episode_id,
            youtube_id=youtube_id,
            episode_title=title,
            published_at=published_at,
            segments=substantive,
            speaker_map=speaker_map,
            wiki_dir=wiki_dir,
        )

    # 3e. Episode summary
    if touched_paths:
        touched_texts = []
        for p in set(touched_paths):  # deduplicate
            if p.exists():
                touched_texts.append(p.read_text(encoding="utf-8"))

        # Determine guest name for summary
        guest_name = ""
        for info in speaker_map.values():
            if info.get("role") == "guest":
                guest_name = info.get("name", "")
                break

        write_episode_summary(
            episode={"youtube_id": youtube_id, "title": title,
                     "published_at": published_at, "guest_name": guest_name},
            touched_page_texts=touched_texts,
            wiki_dir=wiki_dir,
        )

    # 3f. Show notes
    show_notes = parse_show_notes(description)

    # 3g. Checkpoint
    execute(
        "UPDATE episodes SET wiki_processed_at=%s WHERE id=%s",
        (datetime.now(timezone.utc).isoformat(), episode_id),
    )

    return {
        "substantive_turns": len(substantive),
        "total_turns": len(content_segments),
        "show_note_links": sum(len(v) for v in show_notes.values()),
    }
