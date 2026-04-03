from unittest.mock import patch
from scripts.agents.stage3_extract import (
    is_heuristic_filler,
    triage_segments,
    build_graphiti_episode_body,
)


def test_is_heuristic_filler_catches_short_fillers():
    assert is_heuristic_filler("yeah") is True
    assert is_heuristic_filler("mm-hmm") is True
    assert is_heuristic_filler("right exactly") is True


def test_is_heuristic_filler_passes_substantive():
    assert is_heuristic_filler("Cold exposure activates brown fat") is False
    assert is_heuristic_filler("That's a really interesting point about dopamine") is False


def test_is_heuristic_filler_passes_medium_length():
    # 6-15 words — not caught by heuristic, needs LLM
    assert is_heuristic_filler("yeah that makes a lot of sense") is False


def test_triage_segments_filters_obvious_fillers():
    segments = [
        {"text": "yeah", "clean_text": None, "speaker": "Speaker 0", "position": 0},
        {"text": "Cold exposure activates brown fat tissue", "clean_text": None, "speaker": "Speaker 1", "position": 1},
        {"text": "mm-hmm", "clean_text": None, "speaker": "Speaker 0", "position": 2},
        {"text": "The Soberg principle states you should end on cold", "clean_text": None, "speaker": "Speaker 1", "position": 3},
    ]
    with patch("scripts.agents.stage3_extract.llm_call", return_value="SUBSTANTIVE"):
        result = triage_segments(segments)

    assert len(result) == 2
    assert result[0]["position"] == 1
    assert result[1]["position"] == 3


def test_build_graphiti_episode_body():
    segments = [
        {"speaker": "Speaker 1", "speaker_name": "Dr. Huberman", "text": "Cold exposure activates brown fat", "clean_text": None, "start_time": 100.0, "end_time": 115.0},
        {"speaker": "Speaker 0", "speaker_name": "Steven Bartlett", "text": "How long should you stay in?", "clean_text": None, "start_time": 115.0, "end_time": 120.0},
    ]
    body = build_graphiti_episode_body(segments)
    assert "Dr. Huberman" in body
    assert "Cold exposure" in body
    assert "[100s-115s]" in body
