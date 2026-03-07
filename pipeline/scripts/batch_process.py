"""Batch download, diarize, and import DOAC episodes into vault.db.

Reads video IDs from a text file (one per line), downloads audio via yt-dlp,
runs whisper-diarization, and imports the resulting JSON segments into the DB.

Usage:
    cd pipeline
    python -m pipeline.scripts.batch_process --videos ../videos.txt
    python -m pipeline.scripts.batch_process --videos ../videos.txt --whisper-model large-v3 --device cuda
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import sqlite3

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
AUDIO_DIR = DATA_DIR / "audio"
DB_PATH = DATA_DIR / "vault.db"
DIARIZE_SCRIPT = REPO_ROOT / "vendor" / "whisper-diarization" / "diarize.py"

CHANNEL_NAME = "The Diary Of A CEO"
CHANNEL_SLUG = "doac"
CHANNEL_YT_ID = "UC7yZ6keOGsvERMp2HaEbbXQ"


def ensure_channel(conn: sqlite3.Connection) -> int:
    """Ensure DOAC channel exists in DB, return channel_id."""
    row = conn.execute(
        "SELECT id FROM channels WHERE slug = ?", (CHANNEL_SLUG,)
    ).fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO channels (name, slug, youtube_id, intro_skip, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (CHANNEL_NAME, CHANNEL_SLUG, CHANNEL_YT_ID, 0.0),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM channels WHERE slug = ?", (CHANNEL_SLUG,)
    ).fetchone()[0]


def ensure_episode(conn: sqlite3.Connection, channel_id: int, video_id: str, title: str) -> tuple[int, str]:
    """Ensure episode exists in DB, return (episode_id, status)."""
    row = conn.execute(
        "SELECT id, status, title FROM episodes WHERE youtube_id = ?", (video_id,)
    ).fetchone()
    if row:
        # Update title if it was stored as just the video ID
        if row[2] == video_id and title != video_id:
            conn.execute("UPDATE episodes SET title = ? WHERE id = ?", (title, row[0]))
            conn.commit()
        return row[0], row[1]
    conn.execute(
        "INSERT INTO episodes (channel_id, youtube_id, title, status, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (channel_id, video_id, title, "processing"),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM episodes WHERE youtube_id = ?", (video_id,)
    ).fetchone()[0], "processing"


def download_audio(video_id: str) -> Path:
    """Download audio as WAV via yt-dlp. Returns path to WAV file."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = AUDIO_DIR / f"{video_id}.wav"
    if wav_path.exists():
        print(f"  Audio already exists: {wav_path.name}")
        return wav_path

    print(f"  Downloading audio for {video_id}...")
    subprocess.run(
        [
            "yt-dlp", "-x", "--audio-format", "wav",
            "-o", str(AUDIO_DIR / f"{video_id}.%(ext)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        check=True,
    )
    return wav_path


def get_video_title(video_id: str) -> str:
    """Get video title via yt-dlp."""
    result = subprocess.run(
        ["yt-dlp", "--print", "%(title)s", "--no-download",
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() or video_id


def run_diarization(wav_path: Path, whisper_model: str, device: str, batch_size: int) -> Path:
    """Run whisper-diarization on audio file. Returns path to output JSON."""
    json_path = wav_path.with_suffix(".json")
    if json_path.exists():
        print(f"  Diarization JSON already exists: {json_path.name}")
        return json_path

    print(f"  Running diarization ({whisper_model} on {device})...")
    t0 = time.time()
    subprocess.run(
        [
            sys.executable, str(DIARIZE_SCRIPT),
            "-a", str(wav_path),
            "--whisper-model", whisper_model,
            "--batch-size", str(batch_size),
            "--no-stem",
            "--device", device,
            "--language", "en",
        ],
        cwd=str(DIARIZE_SCRIPT.parent),
        check=True,
        stderr=subprocess.STDOUT,
    )
    print(f"  Diarization done in {time.time() - t0:.0f}s")
    return json_path


def import_segments(conn: sqlite3.Connection, episode_id: int, json_path: Path):
    """Import diarization JSON segments into the DB."""
    # Check if segments already exist for this episode
    existing = conn.execute(
        "SELECT COUNT(*) FROM segments WHERE episode_id = ? AND diarizer = 'whisper-diarization'",
        (episode_id,),
    ).fetchone()[0]
    if existing > 0:
        print(f"  Removing {existing} existing segments for re-import...")
        conn.execute(
            "DELETE FROM segments WHERE episode_id = ? AND diarizer = 'whisper-diarization'",
            (episode_id,),
        )

    segments = json.loads(json_path.read_text(encoding="utf-8"))
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
    conn.commit()
    print(f"  Imported {len(segments)} segments into DB.")


def update_episode_status(conn: sqlite3.Connection, episode_id: int, status: str, duration: float | None = None):
    """Update episode status and optionally duration."""
    if duration is not None:
        conn.execute(
            "UPDATE episodes SET status = ?, duration = ? WHERE id = ?",
            (status, duration, episode_id),
        )
    else:
        conn.execute(
            "UPDATE episodes SET status = ? WHERE id = ?",
            (status, episode_id),
        )
    conn.commit()


def process_video(conn: sqlite3.Connection, channel_id: int, video_id: str, args):
    """Full pipeline for a single video: download -> diarize -> import."""
    print(f"\n{'='*60}")
    print(f"Processing: {video_id}")
    print(f"{'='*60}")

    title = get_video_title(video_id)
    print(f"  Title: {title}")

    episode_id, status = ensure_episode(conn, channel_id, video_id, title)

    if status == "complete":
        print(f"  Already complete (episode {episode_id}), skipping.")
        return

    try:
        wav_path = download_audio(video_id)
        json_path = run_diarization(wav_path, args.whisper_model, args.device, args.batch_size)
        import_segments(conn, episode_id, json_path)

        # Get duration from last segment
        segments = json.loads(json_path.read_text(encoding="utf-8"))
        duration = segments[-1]["end"] if segments else None
        update_episode_status(conn, episode_id, "complete", duration)
        print(f"  Done! Episode {episode_id} marked complete.")

        if args.cleanup and wav_path.exists():
            size_mb = wav_path.stat().st_size / (1024 * 1024)
            wav_path.unlink()
            print(f"  Cleaned up {wav_path.name} ({size_mb:.0f} MB freed)")
    except Exception as e:
        print(f"  ERROR: {e}")
        update_episode_status(conn, episode_id, "failed")
        raise


def main():
    parser = argparse.ArgumentParser(description="Batch process DOAC episodes")
    parser.add_argument(
        "--videos", type=str, required=True,
        help="Path to text file with YouTube video IDs (one per line)",
    )
    parser.add_argument("--whisper-model", default="large-v3", help="Whisper model name")
    parser.add_argument("--device", default="cuda", help="Device: cuda or cpu")
    parser.add_argument("--batch-size", type=int, default=4, help="Whisper batch size")
    parser.add_argument("--cleanup", action="store_true", help="Delete WAV audio after each successful video")
    args = parser.parse_args()

    videos_file = Path(args.videos)
    if not videos_file.exists():
        print(f"Videos file not found: {videos_file}")
        sys.exit(1)

    video_ids = [
        line.strip() for line in videos_file.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    print(f"Found {len(video_ids)} video(s) to process.")

    conn = sqlite3.connect(DB_PATH)
    channel_id = ensure_channel(conn)

    total = len(video_ids)
    success = 0
    failed = 0

    for i, video_id in enumerate(video_ids, 1):
        print(f"\n[{i}/{total}] {video_id}")
        try:
            process_video(conn, channel_id, video_id, args)
            success += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1
            continue

    conn.close()
    print(f"\n{'='*60}")
    print(f"Batch complete: {success} success, {failed} failed, {total} total")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
