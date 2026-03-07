"""Import Colab-generated JSON files into vault.db.

Usage:
    python pipeline/scripts/import_colab_json.py data/colab_outputs/
    python pipeline/scripts/import_colab_json.py data/colab_outputs/twbDKFN1cz0.json
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "vault.db"

CHANNEL_NAME = "The Diary Of A CEO"
CHANNEL_SLUG = "doac"
CHANNEL_YT_ID = "UC7yZ6keOGsvERMp2HaEbbXQ"


def ensure_channel(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM channels WHERE slug = ?", (CHANNEL_SLUG,)).fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO channels (name, slug, youtube_id, intro_skip, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (CHANNEL_NAME, CHANNEL_SLUG, CHANNEL_YT_ID, 0.0),
    )
    conn.commit()
    return conn.execute("SELECT id FROM channels WHERE slug = ?", (CHANNEL_SLUG,)).fetchone()[0]


def import_json(conn: sqlite3.Connection, channel_id: int, json_path: Path):
    data = json.loads(json_path.read_text(encoding="utf-8"))

    video_id = data["video_id"]
    title = data.get("title", video_id)
    duration = data.get("duration")
    segments = data.get("segments", [])

    if not segments:
        print(f"  {video_id}: no segments, skipping.")
        return

    # Ensure episode exists
    row = conn.execute("SELECT id, status FROM episodes WHERE youtube_id = ?", (video_id,)).fetchone()
    if row:
        episode_id, status = row
        if status == "complete":
            print(f"  {video_id}: already complete (episode {episode_id}), skipping.")
            return
        # Update title if needed
        conn.execute("UPDATE episodes SET title = ? WHERE id = ? AND title = ?", (title, episode_id, video_id))
    else:
        conn.execute(
            "INSERT INTO episodes (channel_id, youtube_id, title, status, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (channel_id, video_id, title, "processing"),
        )
        conn.commit()
        episode_id = conn.execute("SELECT id FROM episodes WHERE youtube_id = ?", (video_id,)).fetchone()[0]

    # Delete existing segments for this episode/diarizer
    conn.execute(
        "DELETE FROM segments WHERE episode_id = ? AND diarizer = 'whisper-diarization'",
        (episode_id,),
    )

    # Insert segments
    for seg in segments:
        words_json = json.dumps(seg.get("words", []))
        conn.execute(
            "INSERT INTO segments (episode_id, start_time, end_time, text, speaker, words, tag, diarizer, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (
                episode_id,
                seg["start"],
                seg["end"],
                seg["text"],
                seg.get("speaker", "SPEAKER_00"),
                words_json,
                "speech",
                "whisper-diarization",
            ),
        )

    # Mark complete
    conn.execute(
        "UPDATE episodes SET status = 'complete', duration = ? WHERE id = ?",
        (duration, episode_id),
    )
    conn.commit()
    print(f"  {video_id}: imported {len(segments)} segments (episode {episode_id})")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <json_file_or_directory>")
        sys.exit(1)

    target = Path(sys.argv[1])
    if target.is_file():
        json_files = [target]
    elif target.is_dir():
        json_files = sorted(target.glob("*.json"))
    else:
        print(f"Not found: {target}")
        sys.exit(1)

    if not json_files:
        print("No JSON files found.")
        sys.exit(1)

    print(f"Importing {len(json_files)} file(s) into {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    channel_id = ensure_channel(conn)

    for jf in json_files:
        import_json(conn, channel_id, jf)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
