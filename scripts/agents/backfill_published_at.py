"""Backfill published_at for all episodes using yt-dlp per-video metadata."""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from scripts.agents.config import DOAC_CHANNEL_SLUG
from scripts.agents.db import execute, fetch_all, get_channel_id


def fetch_upload_date(youtube_id: str) -> tuple[str, str | None]:
    """Fetch upload_date for a single video. Returns (youtube_id, "YYYY-MM-DD" or None)."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--skip-download", "--no-warnings",
             f"https://www.youtube.com/watch?v={youtube_id}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return youtube_id, None
        meta = json.loads(result.stdout)
        upload_date = meta.get("upload_date")  # YYYYMMDD
        if upload_date:
            dt = datetime.strptime(upload_date, "%Y%m%d")
            return youtube_id, dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return youtube_id, None


def backfill():
    try:
        channel_id = get_channel_id(DOAC_CHANNEL_SLUG)
    except ValueError as exc:
        print(exc)
        return

    episodes = fetch_all(
        """
        SELECT id, youtube_id, published_at
        FROM episodes
        WHERE channel_id=%s AND published_at IS NULL
        """,
        (channel_id,),
    )

    if not episodes:
        print("All episodes already have published_at — nothing to backfill")
        return

    print(f"Episodes missing published_at: {len(episodes)}")
    print(f"Fetching upload dates via yt-dlp (8 threads, ~60-90s for {len(episodes)} videos)...")

    # Fetch dates in parallel
    dates: dict[str, str] = {}
    yt_ids = [ep["youtube_id"] for ep in episodes]

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_upload_date, yt_id): yt_id for yt_id in yt_ids}
        done = 0
        for future in as_completed(futures):
            yt_id, date_str = future.result()
            if date_str:
                dates[yt_id] = date_str
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(yt_ids)} fetched ({len(dates)} with dates)")

    print(f"  {len(dates)}/{len(yt_ids)} videos have upload dates")

    updated = 0
    for ep in episodes:
        pub_date = dates.get(ep["youtube_id"])
        if pub_date:
            execute(
                "UPDATE episodes SET published_at=%s WHERE id=%s",
                (pub_date, ep["id"]),
            )
            updated += 1

    not_found = len(episodes) - updated
    print(f"\nBackfill complete: {updated} updated, {not_found} not found")

    first_5 = fetch_all(
        """
        SELECT youtube_id, title, published_at
        FROM episodes
        ORDER BY published_at NULLS LAST
        LIMIT 10
        """
    )
    print("\nFirst 10 episodes by published_at:")
    for i, e in enumerate(first_5, 1):
        print(f"  {i}. {e['published_at']}  {e['youtube_id']}  {(e.get('title') or '')[:50]}")


if __name__ == "__main__":
    backfill()
