"""Two-pointer time-based word alignment between Whisper and YouTube words.

Aligns whisper ASR words to YouTube auto-caption words by finding the
YouTube word with the greatest time overlap for each whisper word.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AlignedWord:
    """A whisper word paired with its YouTube counterpart (if any)."""
    whisper_text: str
    whisper_start: float
    whisper_end: float
    youtube_text: str | None = None


def _overlap(s1: float, e1: float, s2: float, e2: float) -> float:
    """Compute overlap duration between two time intervals."""
    return max(0.0, min(e1, e2) - max(s1, s2))


def align_words(
    whisper_words: list[dict],
    youtube_words: list[dict],
) -> list[AlignedWord]:
    """Align whisper words to YouTube words by time overlap.

    Args:
        whisper_words: List of dicts with keys: text, start, end
        youtube_words: List of dicts with keys: text, start, end

    Returns:
        List of AlignedWord, one per whisper word, with the best-matching
        YouTube word text (or None if no overlap found).
    """
    if not whisper_words or not youtube_words:
        return [
            AlignedWord(
                whisper_text=w["text"],
                whisper_start=w["start"],
                whisper_end=w["end"],
            )
            for w in whisper_words
        ]

    result: list[AlignedWord] = []
    yt_idx = 0

    for w in whisper_words:
        w_start, w_end = w["start"], w["end"]
        best_overlap = 0.0
        best_yt_text: str | None = None

        # Advance yt_idx to the first YouTube word that could overlap
        while yt_idx > 0 and youtube_words[yt_idx]["start"] > w_start:
            yt_idx -= 1

        # Search forward for the best overlapping YouTube word
        j = yt_idx
        while j < len(youtube_words):
            yt = youtube_words[j]
            if yt["start"] > w_end + 1.0:
                break  # no more possible overlaps

            ovl = _overlap(w_start, w_end, yt["start"], yt["end"])
            if ovl > best_overlap:
                best_overlap = ovl
                best_yt_text = yt["text"]
                yt_idx = j  # advance pointer for next whisper word

            j += 1

        result.append(AlignedWord(
            whisper_text=w["text"],
            whisper_start=w_start,
            whisper_end=w_end,
            youtube_text=best_yt_text,
        ))

    return result


def build_segment_youtube_text(
    segment_words: list[dict],
    aligned: list[AlignedWord],
    seg_start: float,
    seg_end: float,
) -> str | None:
    """Build the YouTube text string for a segment from aligned words.

    Collects aligned YouTube words that fall within the segment time range,
    joins them with spaces. Returns None if no YouTube words were matched.
    """
    yt_words = []
    for aw in aligned:
        mid = (aw.whisper_start + aw.whisper_end) / 2
        if mid >= seg_start - 0.1 and mid <= seg_end + 0.1 and aw.youtube_text:
            yt_words.append(aw.youtube_text)

    return " ".join(yt_words) if yt_words else None
