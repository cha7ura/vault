"""Stage 1 — PREP: Intro detection, people identification, speaker mapping."""
from __future__ import annotations

import re
from typing import TypedDict

from scripts.agents.config import (
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
# 1a. Intro Detection + Chapter Parsing
# ---------------------------------------------------------------------------

CHAPTER_TIMESTAMP_RE = re.compile(r"(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)")
INTRO_TITLES = {"intro", "introduction", "start", "opening"}


def parse_chapters_from_description(description: str | None) -> list[dict]:
    """Extract chapters from YouTube description timestamps.
    Returns list of {"start_time": float, "title": str}.
    """
    if not description:
        return []
    chapters = []
    for match in CHAPTER_TIMESTAMP_RE.finditer(description):
        ts_str, title = match.group(1), match.group(2).strip()
        parts = ts_str.split(":")
        if len(parts) == 3:
            seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            seconds = int(parts[0]) * 60 + int(parts[1])
        chapters.append({"start_time": seconds, "title": title})
    return chapters


def find_intro_end_from_chapters(chapters: list[dict]) -> float | None:
    """Find where intro ends using chapter titles.
    Returns start_time of the first non-intro chapter, or None if no chapters.
    """
    if not chapters:
        return None
    # If first chapter is "Intro", the second chapter is where content starts
    if chapters[0]["title"].lower().strip().rstrip(".!") in INTRO_TITLES:
        if len(chapters) > 1:
            return chapters[1]["start_time"]
    # If no "Intro" chapter, content starts from the beginning
    return 0


def find_segment_at_time(segments: list[dict], target_time: float) -> int:
    """Find the segment position closest to target_time."""
    best_pos = 0
    best_diff = float("inf")
    for seg in segments:
        diff = abs(seg["start_time"] - target_time)
        if diff < best_diff:
            best_diff = diff
            best_pos = seg["position"]
    return best_pos


def detect_intro_end(
    segments: list[dict],
    chapters: list[dict] | None = None,
    max_scan: int = 60,
) -> int:
    """Find the segment position where the real conversation starts.

    Priority: chapters > anchor phrases > 0.
    """
    # 1. Try chapters (most reliable)
    if chapters:
        intro_time = find_intro_end_from_chapters(chapters)
        if intro_time is not None and intro_time > 0:
            return find_segment_at_time(segments, intro_time)

    # 2. Fallback: anchor phrase scan
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
    r"(?:my guest today is|today's guest is)\s+(.+?)(?:,\s*(?:a |the |an |who )|\n|$)",
    r"(?:joined by|speaking with|talking to|interviewing)\s+(.+?)(?:,\s*(?:a |the |an |who )|\.\s|\n|$)",
    r"(?:Guest|Featuring)[:\s]+(.+?)(?:,|\.\s|\n|$)",
]


def parse_guest_from_description(description: str | None) -> str | None:
    """Extract guest name from YouTube episode description using regex."""
    if not description:
        return None

    for pattern in GUEST_PATTERNS:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            name = match.group(1).strip().rstrip(".")
            if 2 <= len(name.split()) <= 5:  # reasonable name length
                return name

    return None


def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", name.lower().strip())
    slug = re.sub(r"[\s_]+", "-", slug)
    return re.sub(r"-+", "-", slug).strip("-")


def get_or_create_person(sb, name: str, photo_url: str | None = None) -> dict:
    """Find a person by name slug, or create one. Returns the person row."""
    slug = slugify(name)

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

    # 1a. Parse chapters + detect intro
    chapters = parse_chapters_from_description(episode.get("description"))

    # Save chapters to episode
    if chapters:
        sb.table("episodes").update(
            {"chapters": chapters}
        ).eq("id", episode_id).execute()

    intro_end = detect_intro_end(segments, chapters=chapters)

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

    # Fallback to LLM extraction from description
    if not guest_name and episode.get("description"):
        from scripts.agents.llm import llm_call
        from scripts.agents.prompts import GUEST_EXTRACTION_PROMPT
        response = llm_call(GUEST_EXTRACTION_PROMPT.format(description=episode["description"][:500]))
        if response and response != "UNKNOWN" and 2 <= len(response.split()) <= 5:
            guest_name = response.strip().strip('"')

    # Fallback to title parsing (DOAC titles often have "Name: Topic")
    if not guest_name and episode.get("title"):
        title = episode["title"]
        # Pattern: "Name: rest of title" or "Name | rest"
        import re
        match = re.match(r"^([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*[:|]", title)
        if match:
            guest_name = match.group(1)

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
