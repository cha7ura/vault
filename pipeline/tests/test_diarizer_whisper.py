from pipeline.core.diarizer_whisper import parse_whisper_diarization_output


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
