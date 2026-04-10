import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yt_dlp


def extract_video_id(url_or_id: str) -> str:
    """Extract YouTube video ID from various URL formats or bare ID.

    Supports:
    - Standard watch URLs: https://www.youtube.com/watch?v=VIDEO_ID
    - Short URLs: https://youtu.be/VIDEO_ID
    - Bare 11-character video IDs

    Raises:
        ValueError: If input is empty or video ID cannot be extracted.
    """
    if not url_or_id:
        raise ValueError("Empty URL or video ID")
    match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url_or_id)
    if match:
        return match.group(1)
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id
    raise ValueError(f"Cannot extract video ID from: {url_or_id}")


def get_video_metadata(video_id: str) -> dict[str, Any]:
    """Fetch video metadata using yt-dlp without downloading.

    Returns a dict with keys: youtube_id, title, description, duration,
    published_at, thumbnail_url, channel_youtube_id, channel_name.
    """
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=False
        )
    upload_date = info.get("upload_date")
    published_at = datetime.strptime(upload_date, "%Y%m%d") if upload_date else None
    return {
        "youtube_id": info["id"],
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "duration": info.get("duration"),
        "published_at": published_at,
        "thumbnail_url": info.get("thumbnail"),
        "channel_youtube_id": info.get("channel_id"),
        "channel_name": info.get("channel"),
    }


def download_audio(video_id: str, output_dir: Path) -> Path:
    """Download audio as WAV using yt-dlp with ffmpeg post-processing.

    Creates output_dir if it doesn't exist. Returns the path to the
    downloaded WAV file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / f"{video_id}.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "wav"}
        ],
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=True
        )
    return output_dir / f"{video_id}.wav"


def list_channel_videos(
    channel_url: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """List videos from a YouTube channel using yt-dlp extract_flat.

    Args:
        channel_url: Full URL to the YouTube channel.
        limit: Maximum number of videos to return. None for all.

    Returns:
        List of dicts with keys: youtube_id, title, duration.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": limit,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    videos = []
    for entry in info.get("entries", []):
        if entry:
            videos.append(
                {
                    "youtube_id": entry.get("id"),
                    "title": entry.get("title", ""),
                    "duration": entry.get("duration"),
                }
            )
    return videos
