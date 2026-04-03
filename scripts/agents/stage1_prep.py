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
