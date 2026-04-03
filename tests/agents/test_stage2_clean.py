from scripts.agents.stage2_clean import (
    merge_segment_text,
    detect_time_gaps,
    validate_dialogue,
    compute_text_confidence,
)


def test_merge_when_both_agree():
    result = merge_segment_text(
        whisper_text="Cold exposure activates brown fat",
        yt_text="Cold exposure activates brown fat",
    )
    assert result == "Cold exposure activates brown fat"


def test_merge_prefers_yt_for_proper_nouns():
    result = merge_segment_text(
        whisper_text="doctor andrew huberman said",
        yt_text="Dr. Andrew Huberman said",
    )
    assert "Dr." in result
    assert "Andrew" in result
    assert "Huberman" in result


def test_merge_keeps_whisper_when_completely_different():
    result = merge_segment_text(
        whisper_text="neuroplasticity is key",
        yt_text="your class to ski",  # bad YT caption
    )
    assert result == "neuroplasticity is key"


def test_merge_keeps_whisper_when_no_yt():
    result = merge_segment_text(
        whisper_text="hello world",
        yt_text="",
    )
    assert result == "hello world"


def test_detect_time_gaps_finds_yt_missing():
    whisper_segs = [
        {"position": 0, "text": "Hello there"},
        {"position": 1, "text": "Let me explain"},
    ]
    yt_segs = [
        {"position": 0, "text": "Hello there"},
        {"position": 1, "text": ""},
    ]
    gaps = detect_time_gaps(whisper_segs, yt_segs)
    assert len(gaps) == 1
    assert gaps[0]["type"] == "yt_missing"
    assert gaps[0]["position"] == 1


def test_detect_time_gaps_finds_whisper_missing():
    whisper_segs = [
        {"position": 0, "text": ""},
    ]
    yt_segs = [
        {"position": 0, "text": "Actually I think"},
    ]
    gaps = detect_time_gaps(whisper_segs, yt_segs)
    assert len(gaps) == 1
    assert gaps[0]["type"] == "whisper_missing"


def test_validate_dialogue_flags_imbalanced_speakers():
    segments = [{"speaker": "Speaker 0"}] * 98 + [{"speaker": "Speaker 1"}] * 2
    issues = validate_dialogue(segments)
    assert any("ratio" in i["type"] for i in issues)


def test_validate_dialogue_flags_long_consecutive_run():
    segments = [{"speaker": "Speaker 0"}] * 25 + [{"speaker": "Speaker 1"}] * 5
    issues = validate_dialogue(segments)
    assert any("consecutive" in i["type"] for i in issues)


def test_validate_dialogue_clean_episode():
    segments = []
    for i in range(50):
        segments.append({"speaker": "Speaker 0" if i % 2 == 0 else "Speaker 1"})
    issues = validate_dialogue(segments)
    assert issues == []


def test_compute_text_confidence_identical():
    score = compute_text_confidence("hello world", "hello world")
    assert score == 1.0


def test_compute_text_confidence_partial_match():
    score = compute_text_confidence(
        "the quick brown fox jumps",
        "the quick brown box jumps",
    )
    assert 0.5 < score < 1.0


def test_compute_text_confidence_no_yt_text():
    score = compute_text_confidence("hello world", "")
    assert score == 0.5  # can't verify, moderate confidence
