import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from pipeline.core.downloader import extract_video_id, get_video_metadata, download_audio


def test_extract_video_id_from_watch_url():
    assert extract_video_id("https://www.youtube.com/watch?v=abc123DEF_-") == "abc123DEF_-"


def test_extract_video_id_from_short_url():
    assert extract_video_id("https://youtu.be/abc123DEF_-") == "abc123DEF_-"


def test_extract_video_id_from_bare_id():
    assert extract_video_id("abc123DEF_-") == "abc123DEF_-"


def test_extract_video_id_invalid():
    with pytest.raises(ValueError):
        extract_video_id("")
