#!/usr/bin/env python3
"""
Fetch YouTube auto-generated captions and store them in the yt_segments table,
aligned to existing segment time boundaries.

Usage:
    python scripts/fetch_yt_captions.py --youtube-id <VIDEO_ID>
    python scripts/fetch_yt_captions.py --all
    python scripts/fetch_yt_captions.py --all --force
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env.local")

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

BATCH_INSERT_SIZE = 500


def fetch_yt_caption_json3(video_id: str) -> list[dict] | None:
    """Fetch YouTube auto-generated captions in json3 format via dump-json + direct URL download."""
    import urllib.request

    # Step 1: Get video metadata with subtitle URLs
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--skip-download", "--no-warnings",
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        print(f"    yt-dlp error: {result.stderr[:300]}")
        return None

    meta = json.loads(result.stdout)
    auto_subs = meta.get("automatic_captions", {})
    en_subs = auto_subs.get("en", [])

    # Find json3 format URL
    json3_url = None
    for sub in en_subs:
        if sub.get("ext") == "json3":
            json3_url = sub["url"]
            break

    if not json3_url:
        print(f"    Warning: no auto-captions found for {video_id}")
        return None

    # Step 2: Download json3 directly
    try:
        with urllib.request.urlopen(json3_url, timeout=30) as resp:
            data = json.loads(resp.read())
        return data.get("events", [])
    except Exception as e:
        print(f"    Failed to download captions: {e}")
        return None


def extract_words(events: list[dict]) -> list[dict]:
    """Extract word-level data from json3 events.

    Each event has tStartMs and may have segs (segments/words).
    Returns list of {text, start, end} where times are in seconds.
    """
    words = []

    for event in events:
        t_start_ms = event.get("tStartMs", 0)
        segs = event.get("segs")
        if not segs:
            continue

        for seg in segs:
            utf8 = seg.get("utf8", "").strip()
            if not utf8 or utf8 == "\n":
                continue

            offset_ms = seg.get("tOffsetMs", 0)
            word_start_ms = t_start_ms + offset_ms
            word_start = word_start_ms / 1000.0

            words.append({
                "text": utf8,
                "start": round(word_start, 3),
                "end": None,  # will be estimated below
            })

    # Estimate end times from next word's start time
    for i in range(len(words) - 1):
        words[i]["end"] = words[i + 1]["start"]

    # Last word: estimate ~0.5s duration
    if words:
        words[-1]["end"] = round(words[-1]["start"] + 0.5, 3)

    return words


def slice_words_to_segments(
    words: list[dict], segments: list[dict]
) -> list[dict]:
    """Slice YT caption words into matching segment time windows.

    Returns list of dicts ready for yt_segments insertion.
    """
    if not words or not segments:
        return []

    results = []
    word_idx = 0

    for pos, seg in enumerate(segments):
        seg_start = seg["start_time"]
        seg_end = seg["end_time"]
        seg_words = []

        # Collect words whose midpoint falls within this segment's time window
        while word_idx < len(words):
            w = words[word_idx]
            word_mid = (w["start"] + w["end"]) / 2

            if word_mid < seg_start:
                # Word is before this segment — advance
                word_idx += 1
                continue
            elif word_mid > seg_end:
                # Word is past this segment — move to next segment
                break
            else:
                seg_words.append(w)
                word_idx += 1

        text = " ".join(w["text"] for w in seg_words)

        results.append({
            "episode_id": seg["episode_id"],
            "position": pos,
            "start_time": seg_start,
            "end_time": seg_end,
            "text": text,
            "words": json.dumps(seg_words),
        })

    return results


def get_segments_for_episode(episode_id: str) -> list[dict]:
    """Fetch segments for an episode, ordered by position."""
    rows = (
        sb.table("segments")
        .select("episode_id, start_time, end_time")
        .eq("episode_id", episode_id)
        .order("start_time")
        .execute()
    )
    return rows.data


def episode_has_yt_segments(episode_id: str) -> bool:
    """Check if yt_segments already exist for this episode."""
    rows = (
        sb.table("yt_segments")
        .select("id", count="exact")
        .eq("episode_id", episode_id)
        .limit(1)
        .execute()
    )
    return (rows.count or 0) > 0


def batch_insert_yt_segments(records: list[dict]):
    """Insert yt_segment records in chunks of BATCH_INSERT_SIZE."""
    for i in range(0, len(records), BATCH_INSERT_SIZE):
        chunk = records[i : i + BATCH_INSERT_SIZE]
        sb.table("yt_segments").insert(chunk).execute()
        print(f"    Inserted {len(chunk)} yt_segments (batch {i // BATCH_INSERT_SIZE + 1})")


def process_episode(episode_id: str, youtube_id: str, force: bool = False) -> bool:
    """Process a single episode. Returns True if successful."""
    if not force and episode_has_yt_segments(episode_id):
        print(f"    Already has yt_segments, skipping (use --force to overwrite)")
        return False

    # If forcing, delete existing yt_segments first
    if force:
        sb.table("yt_segments").delete().eq("episode_id", episode_id).execute()

    # Fetch segments for time boundaries
    segments = get_segments_for_episode(episode_id)
    if not segments:
        print(f"    No segments found for episode, skipping")
        return False

    # Fetch YT captions
    events = fetch_yt_caption_json3(youtube_id)
    if events is None:
        return False

    words = extract_words(events)
    if not words:
        print(f"    Warning: no words extracted from captions, skipping")
        return False

    print(f"    Extracted {len(words)} words from YT captions")

    # Slice words to segment boundaries
    yt_seg_records = slice_words_to_segments(words, segments)
    non_empty = sum(1 for r in yt_seg_records if r["text"].strip())
    print(f"    Mapped to {len(yt_seg_records)} segments ({non_empty} non-empty)")

    # Insert
    batch_insert_yt_segments(yt_seg_records)
    return True


def run_single(youtube_id: str, force: bool):
    """Process a single episode by YouTube video ID."""
    rows = (
        sb.table("episodes")
        .select("id, youtube_id")
        .eq("youtube_id", youtube_id)
        .execute()
    )
    if not rows.data:
        print(f"Episode with youtube_id={youtube_id} not found in database")
        sys.exit(1)

    ep = rows.data[0]
    print(f"Processing {youtube_id} (episode {ep['id']})")
    success = process_episode(ep["id"], youtube_id, force=force)
    if success:
        print("Done!")
    else:
        print("Skipped or failed.")


def run_all(force: bool):
    """Process all episodes missing YT captions."""
    rows = sb.table("episodes").select("id, youtube_id, title").execute()
    episodes = rows.data
    print(f"Found {len(episodes)} episodes")

    to_process = []
    for ep in episodes:
        if not ep.get("youtube_id"):
            continue
        if not force and episode_has_yt_segments(ep["id"]):
            continue
        to_process.append(ep)

    print(f"{len(to_process)} episodes to process\n")

    for i, ep in enumerate(to_process, 1):
        title = (ep.get("title") or ep["youtube_id"])[:60]
        print(f"[{i}/{len(to_process)}] {ep['youtube_id']} — {title}")
        process_episode(ep["id"], ep["youtube_id"], force=force)
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Fetch YouTube auto-generated captions into yt_segments"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--youtube-id", help="Process a single video by YouTube ID")
    group.add_argument("--all", action="store_true", help="Process all episodes missing YT captions")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if yt_segments already exist")

    args = parser.parse_args()

    if args.youtube_id:
        run_single(args.youtube_id, force=args.force)
    else:
        run_all(force=args.force)


if __name__ == "__main__":
    main()
