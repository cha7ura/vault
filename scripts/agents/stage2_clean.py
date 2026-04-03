"""Stage 2 — CLEAN: Text merge, speaker assignment, dialogue validation."""
from __future__ import annotations

from typing import TypedDict

from scripts.agents.config import get_supabase, TEXT_CONFIDENCE_THRESHOLD, BATCH_INSERT_SIZE
from scripts.agents.stage1_prep import PrepResult


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
    return (
        len(yt_word) > 2
        and yt_word[0].isupper()
        and whisper_word[0].islower()
    )


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

    # Fetch all segments (paginated)
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
    for row in updates:
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
