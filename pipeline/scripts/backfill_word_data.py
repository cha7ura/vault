"""Backfill word-level timestamps and confidence scores for existing segments.

Runs faster-whisper on the existing audio file with word_timestamps=True,
then maps each word to the closest DB segment by time overlap and updates
the segment's `words` JSON column.

Usage:
    PYTHONPATH=. pipeline/.venv/bin/python -m pipeline.scripts.backfill_word_data
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

AUDIO_PATH = Path(__file__).resolve().parents[2] / "data" / "audio" / "doac" / "jDG1m_b5Ih0_16k.wav"
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "vault.db"
WHISPER_MODEL = "medium.en"
BATCH_SIZE = 8


def get_word_timestamps(audio_path: Path) -> list[dict]:
    """Run faster-whisper transcription and return word-level data."""
    import faster_whisper

    print(f"Loading whisper model '{WHISPER_MODEL}'...")
    model = faster_whisper.WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    pipeline = faster_whisper.BatchedInferencePipeline(model)

    print(f"Transcribing {audio_path.name} with word timestamps...")
    audio = faster_whisper.decode_audio(str(audio_path))
    segments, _ = pipeline.transcribe(
        audio, "en", batch_size=BATCH_SIZE, word_timestamps=True
    )

    words = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                words.append({
                    "text": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "score": round(w.probability, 4) if w.probability is not None else None,
                })

    print(f"Got {len(words)} words from whisper.")
    return words


def backfill(words: list[dict]):
    """Map whisper words to DB segments by time overlap, update words column."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all segments ordered by start_time
    cursor.execute(
        "SELECT id, start_time, end_time FROM segments "
        "WHERE diarizer = 'whisper-diarization' ORDER BY start_time"
    )
    segments = cursor.fetchall()
    print(f"Found {len(segments)} segments in DB.")

    if not segments:
        print("No segments found, nothing to backfill.")
        conn.close()
        return

    # Map words to segments: a word belongs to a segment if its midpoint
    # falls within [seg.start, seg.end]
    seg_words: dict[int, list[dict]] = {seg_id: [] for seg_id, _, _ in segments}
    seg_idx = 0

    for word in words:
        word_mid = (word["start"] + word["end"]) / 2

        # Advance segment index until we find one that could contain this word
        while seg_idx < len(segments) - 1 and word_mid > segments[seg_idx][2]:
            seg_idx += 1

        seg_id, seg_start, seg_end = segments[seg_idx]

        # Check if word midpoint falls within this segment (with small tolerance)
        if word_mid >= seg_start - 0.1 and word_mid <= seg_end + 0.1:
            seg_words[seg_id].append(word)
        elif seg_idx > 0:
            # Word might belong to previous segment if it's closer
            prev_id, prev_start, prev_end = segments[seg_idx - 1]
            if word_mid >= prev_start - 0.1 and word_mid <= prev_end + 0.1:
                seg_words[prev_id].append(word)

    # Update segments
    updated = 0
    for seg_id, words_list in seg_words.items():
        if words_list:
            cursor.execute(
                "UPDATE segments SET words = ? WHERE id = ?",
                (json.dumps(words_list), seg_id),
            )
            updated += 1

    conn.commit()
    conn.close()
    print(f"Updated {updated} segments with word-level data.")


def main():
    if not AUDIO_PATH.exists():
        print(f"Audio file not found: {AUDIO_PATH}")
        print("Skipping whisper transcription. You can run this after placing the audio file.")
        return

    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return

    words = get_word_timestamps(AUDIO_PATH)
    backfill(words)
    print("Backfill complete!")


if __name__ == "__main__":
    main()
