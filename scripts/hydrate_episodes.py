#!/usr/bin/env python3
"""
Hydrate episode metadata from YouTube — backfills title, description,
thumbnail_url, and published_at for all episodes in the DB.

Usage:
    python scripts/hydrate_episodes.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env.local")

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_yt_metadata(video_id: str) -> dict | None:
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-download",
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"    yt-dlp error: {result.stderr[:200]}")
        return None
    return json.loads(result.stdout)


def hydrate():
    rows = sb.table("episodes").select("id, youtube_id, title, description, thumbnail_url, published_at").execute()
    episodes = rows.data
    print(f"Found {len(episodes)} episodes")

    needs_hydration = [
        ep for ep in episodes
        if not ep.get("published_at") or not ep.get("description") or not ep.get("thumbnail_url")
    ]
    # Process oldest-inserted first
    print(f"{len(needs_hydration)} need metadata hydration\n")

    for i, ep in enumerate(needs_hydration, 1):
        vid = ep["youtube_id"]
        print(f"[{i}/{len(needs_hydration)}] {vid} — {ep['title'][:60]}")

        meta = fetch_yt_metadata(vid)
        if not meta:
            print("    Skipped (fetch failed)")
            continue

        upload_date = meta.get("upload_date")  # YYYYMMDD
        published_at = None
        if upload_date:
            published_at = datetime.strptime(upload_date, "%Y%m%d").isoformat()

        update = {}
        if not ep.get("published_at") and published_at:
            update["published_at"] = published_at
        if not ep.get("description") and meta.get("description"):
            update["description"] = meta["description"]
        if not ep.get("thumbnail_url") and meta.get("thumbnail"):
            update["thumbnail_url"] = meta["thumbnail"]

        # Always fix placeholder titles (title == youtube_id)
        if ep["title"] == vid and meta.get("title"):
            update["title"] = meta["title"]

        # Backfill duration if missing
        if meta.get("duration"):
            update["duration_seconds"] = int(meta["duration"])

        if update:
            sb.table("episodes").update(update).eq("id", ep["id"]).execute()
            print(f"    Updated: {', '.join(update.keys())}")
        else:
            print(f"    Already complete")


if __name__ == "__main__":
    hydrate()
