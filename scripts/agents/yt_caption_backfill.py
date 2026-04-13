"""Backfill segments.youtube_text by fetching YouTube auto-captions via
yt-dlp and word-aligning them to existing ASR segments.

Usage:
  python -m scripts.agents.yt_caption_backfill [--limit N] [--channel SLUG]
      [--force] [--youtube-id ID ...]

Skips episodes that already have youtube_text populated unless --force.
Caches the raw json3 files under data/yt_captions/ so re-runs are free.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from scripts.agents.config import DOAC_CHANNEL_SLUG
from scripts.agents.db import execute_many, fetch_all, fetch_one, get_channel_id

CACHE_DIR = Path("data/yt_captions")
WORD_BUCKET_MS = 100  # dedup granularity for rolling-caption artifacts


def fetch_json3(youtube_id: str, cache_dir: Path) -> Path | None:
    """Download YouTube auto-captions as json3. Returns path or None if unavailable."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_path = cache_dir / f"{youtube_id}.en.json3"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    cmd = [
        "yt-dlp", "--skip-download", "--write-auto-sub",
        "--sub-lang", "en", "--sub-format", "json3",
        "--output", f"{cache_dir}/%(id)s.%(ext)s",
        f"https://www.youtube.com/watch?v={youtube_id}",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as e:
        print(f"    yt-dlp failed: {e.stderr.decode()[:200]}")
        return None
    except subprocess.TimeoutExpired:
        print("    yt-dlp timed out")
        return None
    return out_path if out_path.exists() else None


def parse_json3_to_words(path: Path) -> list[tuple[int, str]]:
    """Flatten json3 events into (time_ms, word) pairs, deduped by bucket.

    Auto-captions emit rolling frames where the same phrase appears in multiple
    consecutive events. Bucketing by (time_ms//100, lowercased word) collapses
    those repeats while preserving legit repeated words (different timestamps).
    """
    with path.open() as f:
        data = json.load(f)
    seen: set[tuple[int, str]] = set()
    words: list[tuple[int, str]] = []
    for e in data.get("events", []):
        if "segs" not in e:
            continue
        t_start = e.get("tStartMs", 0)
        for s in e["segs"]:
            txt = s.get("utf8", "")
            if not txt or txt.isspace():
                continue
            t_ms = t_start + s.get("tOffsetMs", 0)
            key = (t_ms // WORD_BUCKET_MS, txt.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            words.append((t_ms, txt.strip()))
    return words


def align_words_to_segments(
    words: list[tuple[int, str]],
    segments: list[dict],
) -> list[tuple[str, str]]:
    """For each segment, collect YT words falling within [start_time, end_time).
    Returns (segment_id, yt_text) pairs for batch UPDATE.
    """
    # Sort words by time_ms for efficient range scan
    words_sorted = sorted(words, key=lambda x: x[0])
    times = [w[0] for w in words_sorted]
    import bisect

    rows: list[tuple[str, str]] = []
    for seg in segments:
        start_ms = int(seg["start_time"] * 1000)
        end_ms = int(seg["end_time"] * 1000)
        lo = bisect.bisect_left(times, start_ms)
        hi = bisect.bisect_left(times, end_ms)
        text = " ".join(w for _, w in words_sorted[lo:hi]).strip()
        rows.append((text, seg["id"]))
    return rows


def backfill_episode(ep: dict, cache_dir: Path, force: bool) -> dict:
    """Backfill one episode. Returns stats dict."""
    youtube_id = ep["youtube_id"]
    print(f"  {youtube_id}: ", end="", flush=True)

    if not force:
        existing = fetch_one(
            "SELECT COUNT(youtube_text) AS c FROM segments WHERE episode_id = %s",
            (ep["id"],),
        )
        if existing and existing["c"] > 0:
            print(f"SKIP (already has {existing['c']} rows)")
            return {"skipped": True}

    t0 = time.monotonic()
    json_path = fetch_json3(youtube_id, cache_dir)
    if not json_path:
        print("no captions available")
        return {"no_captions": True}

    words = parse_json3_to_words(json_path)
    if not words:
        print("empty captions")
        return {"empty": True}

    segments = fetch_all(
        "SELECT id, start_time, end_time FROM segments WHERE episode_id = %s ORDER BY position",
        (ep["id"],),
    )
    if not segments:
        print("no ASR segments")
        return {"no_segments": True}

    rows = align_words_to_segments(words, segments)
    matched = sum(1 for yt_text, _ in rows if yt_text)
    execute_many(
        "UPDATE segments SET youtube_text = %s WHERE id = %s",
        rows,
    )
    elapsed = time.monotonic() - t0
    print(
        f"{len(words)} YT words → {matched}/{len(segments)} segs aligned "
        f"({elapsed:.1f}s)"
    )
    return {"words": len(words), "matched": matched, "total": len(segments)}


def get_target_episodes(
    channel_slug: str,
    limit: int,
    youtube_ids: list[str] | None,
) -> list[dict]:
    if youtube_ids:
        return fetch_all(
            "SELECT id, youtube_id FROM episodes WHERE youtube_id = ANY(%s)",
            (list(youtube_ids),),
        )
    try:
        channel_id = get_channel_id(channel_slug)
    except ValueError as exc:
        sys.exit(str(exc))
    query = """
        SELECT id, youtube_id FROM episodes
        WHERE channel_id = %s
        ORDER BY published_at NULLS LAST
    """
    params: list = [channel_id]
    if limit > 0:
        query += " LIMIT %s"
        params.append(limit)
    return fetch_all(query, tuple(params))


def main():
    parser = argparse.ArgumentParser(description="Backfill YouTube captions into segments.youtube_text")
    parser.add_argument("--channel", default=DOAC_CHANNEL_SLUG)
    parser.add_argument("--limit", type=int, default=0, help="0 = all episodes")
    parser.add_argument("--force", action="store_true",
                        help="reprocess even if youtube_text already populated")
    parser.add_argument("--youtube-id", action="append", default=[],
                        help="specific episode IDs (repeatable)")
    parser.add_argument("--cache-dir", default=str(CACHE_DIR))
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    episodes = get_target_episodes(args.channel, args.limit, args.youtube_id or None)
    print(f"target episodes: {len(episodes)}  cache: {cache_dir}")

    totals = {"done": 0, "skipped": 0, "failed": 0,
              "total_words": 0, "total_segs": 0}
    for i, ep in enumerate(episodes, 1):
        print(f"[{i}/{len(episodes)}]", end=" ")
        try:
            stats = backfill_episode(ep, cache_dir, args.force)
        except Exception as e:
            print(f"ERROR: {e}")
            totals["failed"] += 1
            continue
        if stats.get("skipped"):
            totals["skipped"] += 1
        elif stats.get("no_captions") or stats.get("empty") or stats.get("no_segments"):
            totals["failed"] += 1
        else:
            totals["done"] += 1
            totals["total_words"] += stats.get("words", 0)
            totals["total_segs"] += stats.get("matched", 0)

    print("\n" + "=" * 50)
    print(f"done: {totals['done']}  skipped: {totals['skipped']}  failed: {totals['failed']}")
    print(f"total YT words: {totals['total_words']:,}  aligned segs: {totals['total_segs']:,}")


if __name__ == "__main__":
    main()
