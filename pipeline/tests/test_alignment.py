from pipeline.core.alignment import align_words, build_segment_youtube_text


def test_align_words_basic():
    whisper = [
        {"text": "Hello", "start": 0.5, "end": 0.8},
        {"text": "world", "start": 0.9, "end": 1.3},
    ]
    youtube = [
        {"text": "Hello", "start": 0.4, "end": 0.9},
        {"text": "world", "start": 0.9, "end": 1.4},
    ]

    aligned = align_words(whisper, youtube)
    assert len(aligned) == 2
    assert aligned[0].whisper_text == "Hello"
    assert aligned[0].youtube_text == "Hello"
    assert aligned[1].youtube_text == "world"


def test_align_words_mismatch():
    """YouTube has different text for the same time range."""
    whisper = [
        {"text": "their", "start": 1.0, "end": 1.3},
    ]
    youtube = [
        {"text": "there", "start": 0.9, "end": 1.4},
    ]

    aligned = align_words(whisper, youtube)
    assert aligned[0].whisper_text == "their"
    assert aligned[0].youtube_text == "there"


def test_align_words_empty_youtube():
    whisper = [
        {"text": "Hello", "start": 0.5, "end": 0.8},
    ]

    aligned = align_words(whisper, [])
    assert len(aligned) == 1
    assert aligned[0].youtube_text is None


def test_build_segment_youtube_text():
    from pipeline.core.alignment import AlignedWord

    aligned = [
        AlignedWord(whisper_text="Hello", whisper_start=0.5, whisper_end=0.8, youtube_text="Hello"),
        AlignedWord(whisper_text="wrld", whisper_start=0.9, whisper_end=1.3, youtube_text="world"),
        AlignedWord(whisper_text="foo", whisper_start=5.0, whisper_end=5.5, youtube_text="bar"),
    ]

    # Only words within segment range
    result = build_segment_youtube_text([], aligned, seg_start=0.4, seg_end=1.5)
    assert result == "Hello world"

    # Words outside range
    result2 = build_segment_youtube_text([], aligned, seg_start=4.0, seg_end=6.0)
    assert result2 == "bar"
