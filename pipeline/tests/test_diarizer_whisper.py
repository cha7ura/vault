import json
import tempfile
from pathlib import Path

from pipeline.core.diarizer_whisper import (
    parse_whisper_diarization_output,
    parse_whisper_diarization_json,
)


def test_parse_whisper_diarization_output():
    raw_output = """[0.00s - 5.20s] Speaker 0: Hello and welcome to the show.
[5.20s - 12.50s] Speaker 1: Thank you for having me, it's great to be here.
[12.50s - 18.00s] Speaker 0: Let's dive right in."""

    result = parse_whisper_diarization_output(raw_output)
    assert len(result.segments) == 3
    assert result.segments[0].speaker == "Speaker 0"
    assert result.segments[0].text == "Hello and welcome to the show."
    assert result.segments[0].start == 0.0
    assert result.segments[1].speaker == "Speaker 1"
    assert len(result.speakers) == 2


def test_parse_empty_output():
    result = parse_whisper_diarization_output("")
    assert len(result.segments) == 0
    assert result.speakers == []


def test_parse_whisper_diarization_json():
    data = [
        {
            "speaker": "Speaker 0",
            "start": 0.54,
            "end": 6.3,
            "text": "Hello world",
            "words": [
                {"text": "Hello", "start": 0.54, "end": 0.72, "score": 0.98},
                {"text": "world", "start": 0.72, "end": 1.1, "score": 0.42},
            ],
        },
        {
            "speaker": "Speaker 1",
            "start": 6.5,
            "end": 10.0,
            "text": "Thanks",
            "words": [
                {"text": "Thanks", "start": 6.5, "end": 7.0, "score": 0.95},
            ],
        },
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp_path = Path(f.name)

    try:
        result = parse_whisper_diarization_json(tmp_path)
        assert len(result.segments) == 2
        assert result.segments[0].speaker == "Speaker 0"
        assert result.segments[0].text == "Hello world"
        assert len(result.segments[0].words) == 2
        assert result.segments[0].words[0].text == "Hello"
        assert result.segments[0].words[0].score == 0.98
        assert result.segments[0].words[1].score == 0.42
        assert result.segments[1].words[0].text == "Thanks"
        assert len(result.speakers) == 2
    finally:
        tmp_path.unlink()
