"""Stage 1 — PREP: Intro detection, people identification, speaker mapping."""
from __future__ import annotations

import re
from typing import TypedDict

from scripts.agents.config import HOST_ANCHOR_PHRASES, DOAC_HOST_NAME
from scripts.agents.db import fetch_all, fetch_one, execute, execute_returning


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
    """Find the segment index closest to target_time."""
    best_idx = 0
    best_diff = float("inf")
    for idx, seg in enumerate(segments):
        start = seg.get("start_time") or 0
        diff = abs(start - target_time)
        if diff < best_diff:
            best_diff = diff
            best_idx = idx
    return best_idx


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
    last_anchor_idx = 0
    for idx, seg in enumerate(segments[:max_scan]):
        text_lower = seg["text"].lower()
        for phrase in HOST_ANCHOR_PHRASES:
            if phrase in text_lower:
                last_anchor_idx = idx
                break
    return last_anchor_idx


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


def get_or_create_person(name: str, photo_url: str | None = None) -> dict:
    """Find a person by name slug, or create one. Returns the person row."""
    slug = slugify(name)

    existing = fetch_one("SELECT * FROM people WHERE slug=%s LIMIT 1", (slug,))
    if existing:
        return existing

    if photo_url:
        return execute_returning(
            "INSERT INTO people (name, slug, photo_url) VALUES (%s, %s, %s) RETURNING *",
            (name, slug, photo_url),
        )
    return execute_returning(
        "INSERT INTO people (name, slug) VALUES (%s, %s) RETURNING *",
        (name, slug),
    )


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
    episode = fetch_one("SELECT * FROM episodes WHERE id=%s", (episode_id,))
    if not episode:
        raise ValueError(f"Episode not found: {episode_id}")

    segments = fetch_all(
        """
        SELECT position, speaker, text, start_time, end_time
        FROM segments
        WHERE episode_id=%s
        ORDER BY position
        LIMIT 60
        """,
        (episode_id,),
    )

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
        execute(
            "UPDATE episodes SET chapters=%s WHERE id=%s",
            (chapters, episode_id),
        )

    intro_end = detect_intro_end(segments, chapters=chapters)

    # 1b. Identify guest — use Stage 0 audit data first
    guest_names = episode.get("guest_names") or []
    episode_type = episode.get("episode_type")
    guest_name = guest_names[0] if guest_names else None

    # Fallback chain if Stage 0 audit didn't populate
    if not guest_name and episode_type != "solo":
        # Try episode_guests table
        guest_rows = fetch_all(
            """
            SELECT g.name AS name, g.photo_url AS photo_url
            FROM episode_guests eg
            JOIN guests g ON g.id = eg.guest_id
            WHERE eg.episode_id=%s
            """,
            (episode_id,),
        )
        if guest_rows:
            guest_name = guest_rows[0]["name"]

        # Fallback to description parsing
        if not guest_name:
            guest_name = parse_guest_from_description(episode.get("description"))

    # 1c. Map speakers — filter out phantom speakers (< 5 segments)
    host_label = identify_host_speaker(segments)
    speaker_counts: dict[str, int] = {}
    for seg in segments:
        speaker_counts[seg["speaker"]] = speaker_counts.get(seg["speaker"], 0) + 1
    # Only consider speakers with at least 5 segments as real
    real_speakers = sorted(s for s, c in speaker_counts.items() if c >= 5)
    if host_label not in real_speakers:
        real_speakers.append(host_label)
    guest_labels = [s for s in real_speakers if s != host_label]

    # Create/find people
    host_person = get_or_create_person(DOAC_HOST_NAME)
    speakers: dict[str, SpeakerInfo] = {
        host_label: SpeakerInfo(
            person_id=host_person["id"], name=DOAC_HOST_NAME, role="host"
        ),
    }

    # Map phantom speakers (below threshold) to host
    for label, count in speaker_counts.items():
        if label != host_label and count < 5:
            speakers[label] = SpeakerInfo(
                person_id=host_person["id"], name=DOAC_HOST_NAME, role="host"
            )

    if guest_labels and guest_names and len(guest_names) > 0:
        # Multi-guest: assign names round-robin if more guests than names
        for idx, label in enumerate(guest_labels):
            name = guest_names[idx] if idx < len(guest_names) else guest_names[0]
            guest_person = get_or_create_person(name)
            speakers[label] = SpeakerInfo(
                person_id=guest_person["id"], name=name, role="guest"
            )
    elif guest_labels and guest_name:
        guest_person = get_or_create_person(guest_name)
        for label in guest_labels:
            speakers[label] = SpeakerInfo(
                person_id=guest_person["id"], name=guest_name, role="guest"
            )
    elif guest_labels:
        # No guest name found — map to host (likely solo episode with diarizer splits)
        for label in guest_labels:
            speakers[label] = SpeakerInfo(
                person_id=host_person["id"], name=DOAC_HOST_NAME, role="host"
            )

    # Save intro_end_position and speaker_map to episode
    execute(
        "UPDATE episodes SET intro_end_position=%s, speaker_map=%s WHERE id=%s",
        (intro_end, {k: dict(v) for k, v in speakers.items()}, episode_id),
    )

    return PrepResult(
        episode_id=episode_id,
        intro_end_position=intro_end,
        speakers=speakers,
    )
