from scripts.agents.stage1_prep import (
    detect_intro_end,
    identify_host_speaker,
    parse_guest_from_description,
    parse_chapters_from_description,
    find_intro_end_from_chapters,
)


def test_parse_chapters_from_description():
    desc = """0:00 Intro
02:19 What is imposter syndrome?
15:30 The secret to confidence
1:05:20 Final thoughts"""
    chapters = parse_chapters_from_description(desc)
    assert len(chapters) == 4
    assert chapters[0] == {"start_time": 0, "title": "Intro"}
    assert chapters[1] == {"start_time": 139, "title": "What is imposter syndrome?"}
    assert chapters[3] == {"start_time": 3920, "title": "Final thoughts"}


def test_parse_chapters_returns_empty_for_no_chapters():
    assert parse_chapters_from_description("Just a regular description.") == []
    assert parse_chapters_from_description(None) == []


def test_find_intro_end_from_chapters():
    chapters = [
        {"start_time": 0, "title": "Intro"},
        {"start_time": 54, "title": "Where do I focus?"},
        {"start_time": 357, "title": "Character traits"},
    ]
    assert find_intro_end_from_chapters(chapters) == 54


def test_find_intro_end_no_intro_chapter():
    chapters = [
        {"start_time": 0, "title": "Where do I focus?"},
        {"start_time": 357, "title": "Character traits"},
    ]
    assert find_intro_end_from_chapters(chapters) == 0


def test_find_intro_end_empty_chapters():
    assert find_intro_end_from_chapters([]) is None


def test_detect_intro_end_uses_chapters_over_phrases():
    segments = [
        {"position": 0, "text": "Subscribe to the channel", "start_time": 0.0},
        {"position": 1, "text": "Welcome to the show", "start_time": 30.0},
        {"position": 2, "text": "So tell me about your work", "start_time": 55.0},
        {"position": 3, "text": "Well I started in neuroscience", "start_time": 70.0},
    ]
    chapters = [
        {"start_time": 0, "title": "Intro"},
        {"start_time": 54, "title": "Guest interview"},
    ]
    # Should use chapters (position 2, closest to 54s) not anchor phrases
    result = detect_intro_end(segments, chapters=chapters)
    assert result == 2


def test_detect_intro_end_falls_back_to_phrases():
    segments = [
        {"position": 0, "text": "Quick one, the Diary of a CEO", "start_time": 0.0},
        {"position": 1, "text": "please subscribe to the channel", "start_time": 15.0},
        {"position": 2, "text": "My guest today is an incredible person", "start_time": 30.0},
        {"position": 3, "text": "So tell me about your childhood", "start_time": 45.0},
    ]
    # No chapters — falls back to anchor phrases
    result = detect_intro_end(segments)
    assert result == 3  # "tell me about" at position 3


def test_detect_intro_end_returns_zero_when_no_anchors():
    segments = [
        {"position": 0, "text": "So the thing about dopamine is", "start_time": 0.0},
        {"position": 1, "text": "it regulates reward pathways", "start_time": 10.0},
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
