"""Parse YouTube JSON3 subtitle format into word-level data.

YouTube's JSON3 format structure::

    {
      "events": [
        {
          "tStartMs": 1234,
          "dDurationMs": 5000,
          "segs": [
            {"utf8": "Hello", "tOffsetMs": 0, "acAsrConf": 230},
            {"utf8": " world", "tOffsetMs": 500, "acAsrConf": 180}
          ]
        }
      ]
    }

``acAsrConf`` is ASR confidence on a 0–255 scale (higher = more confident).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class YouTubeWord:
    """A single word from YouTube auto-captions."""
    text: str
    start: float          # seconds
    end: float            # seconds
    confidence: float     # 0.0–1.0


def parse_json3(json3_path: str | Path) -> list[YouTubeWord]:
    """Parse a YouTube JSON3 subtitle file into a list of YouTubeWord objects.

    Normalizes confidence from 0–255 integer to 0.0–1.0 float.
    Strips whitespace from word text and skips empty/newline-only segments.
    """
    data = json.loads(Path(json3_path).read_text(encoding="utf-8"))

    words: list[YouTubeWord] = []

    for event in data.get("events", []):
        event_start_ms = event.get("tStartMs", 0)
        event_duration_ms = event.get("dDurationMs", 0)
        segs = event.get("segs")

        if not segs:
            continue

        for i, seg in enumerate(segs):
            raw_text = seg.get("utf8", "")
            text = raw_text.strip()

            # Skip empty segments and newlines
            if not text or text == "\n":
                continue

            offset_ms = seg.get("tOffsetMs", 0)
            start_ms = event_start_ms + offset_ms

            # End time: use next segment's offset, or event end
            if i + 1 < len(segs):
                next_offset = segs[i + 1].get("tOffsetMs", offset_ms)
                end_ms = event_start_ms + next_offset
            else:
                end_ms = event_start_ms + event_duration_ms

            # Normalize confidence from 0-255 to 0.0-1.0
            raw_conf = seg.get("acAsrConf")
            confidence = raw_conf / 255.0 if raw_conf is not None else 1.0

            words.append(YouTubeWord(
                text=text,
                start=round(start_ms / 1000.0, 3),
                end=round(end_ms / 1000.0, 3),
                confidence=round(confidence, 4),
            ))

    return words
