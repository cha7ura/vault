from scripts.agents.stage1_prep import (
    detect_intro_end,
    identify_host_speaker,
    parse_guest_from_description,
)


def test_detect_intro_end_finds_subscribe():
    segments = [
        {"position": 0, "text": "Quick one, the Diary of a CEO"},
        {"position": 1, "text": "please subscribe to the channel"},
        {"position": 2, "text": "My guest today is an incredible person"},
        {"position": 3, "text": "So tell me about your childhood"},
    ]
    result = detect_intro_end(segments)
    assert result == 3  # "tell me about" at position 3


def test_detect_intro_end_returns_zero_when_no_anchors():
    segments = [
        {"position": 0, "text": "So the thing about dopamine is"},
        {"position": 1, "text": "it regulates reward pathways"},
    ]
    result = detect_intro_end(segments)
    assert result == 0


def test_identify_host_speaker_by_anchor_phrases():
    segments = [
        {"position": 0, "speaker": "Speaker 0", "text": "Welcome to the diary of a CEO"},
        {"position": 1, "speaker": "Speaker 1", "text": "Thanks for having me"},
        {"position": 2, "speaker": "Speaker 0", "text": "Please subscribe"},
    ]
    host_label = identify_host_speaker(segments)
    assert host_label == "Speaker 0"


def test_identify_host_speaker_falls_back_to_first_speaker():
    segments = [
        {"position": 0, "speaker": "Speaker 0", "text": "Let's talk about health"},
        {"position": 1, "speaker": "Speaker 1", "text": "Sure thing"},
    ]
    host_label = identify_host_speaker(segments)
    assert host_label == "Speaker 0"


def test_parse_guest_from_description_finds_name():
    desc = "My guest today is Dr. Andrew Huberman, a neuroscientist at Stanford."
    result = parse_guest_from_description(desc)
    assert result is not None
    assert "Huberman" in result


def test_parse_guest_from_description_returns_none_for_empty():
    assert parse_guest_from_description("") is None
    assert parse_guest_from_description(None) is None
