import json
import tempfile
from pathlib import Path

from pipeline.core.youtube_subs import parse_json3


def test_parse_json3_basic():
    """Parse a minimal JSON3 structure with word-level data."""
    data = {
        "events": [
            {
                "tStartMs": 1000,
                "dDurationMs": 3000,
                "segs": [
                    {"utf8": "Hello", "tOffsetMs": 0, "acAsrConf": 255},
                    {"utf8": " world", "tOffsetMs": 500, "acAsrConf": 128},
                ],
            },
            {
                "tStartMs": 5000,
                "dDurationMs": 2000,
                "segs": [
                    {"utf8": "test", "tOffsetMs": 0, "acAsrConf": 200},
                ],
            },
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json3", delete=False) as f:
        json.dump(data, f)
        tmp_path = Path(f.name)

    try:
        words = parse_json3(tmp_path)
        assert len(words) == 3

        assert words[0].text == "Hello"
        assert words[0].start == 1.0
        assert words[0].end == 1.5  # next seg offset
        assert words[0].confidence == 1.0  # 255/255

        assert words[1].text == "world"
        assert words[1].start == 1.5
        assert words[1].end == 4.0  # event end
        assert round(words[1].confidence, 2) == 0.50  # 128/255

        assert words[2].text == "test"
        assert words[2].start == 5.0
    finally:
        tmp_path.unlink()


def test_parse_json3_skips_empty_and_newlines():
    """Empty text and newline-only segments should be skipped."""
    data = {
        "events": [
            {
                "tStartMs": 0,
                "dDurationMs": 1000,
                "segs": [
                    {"utf8": "\n", "tOffsetMs": 0},
                    {"utf8": "", "tOffsetMs": 100},
                    {"utf8": "real", "tOffsetMs": 200, "acAsrConf": 200},
                ],
            },
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json3", delete=False) as f:
        json.dump(data, f)
        tmp_path = Path(f.name)

    try:
        words = parse_json3(tmp_path)
        assert len(words) == 1
        assert words[0].text == "real"
    finally:
        tmp_path.unlink()


def test_parse_json3_no_confidence():
    """Missing acAsrConf defaults to 1.0."""
    data = {
        "events": [
            {
                "tStartMs": 0,
                "dDurationMs": 1000,
                "segs": [{"utf8": "word", "tOffsetMs": 0}],
            },
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json3", delete=False) as f:
        json.dump(data, f)
        tmp_path = Path(f.name)

    try:
        words = parse_json3(tmp_path)
        assert len(words) == 1
        assert words[0].confidence == 1.0
    finally:
        tmp_path.unlink()
