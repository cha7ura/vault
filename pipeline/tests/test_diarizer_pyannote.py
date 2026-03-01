from pipeline.core.diarizer_pyannote import (
    DiarizationSegment, TranscriptSegment, merge_diarization_with_transcript,
)


def test_merge_diarization_with_transcript():
    transcript_segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello there"),
        TranscriptSegment(start=5.0, end=10.0, text="How are you"),
        TranscriptSegment(start=10.0, end=15.0, text="I am fine"),
    ]
    diarization_segments = [
        DiarizationSegment(start=0.0, end=7.0, speaker="SPEAKER_00"),
        DiarizationSegment(start=7.0, end=15.0, speaker="SPEAKER_01"),
    ]
    result = merge_diarization_with_transcript(transcript_segments, diarization_segments)
    assert len(result.segments) == 3
    assert result.segments[0].speaker == "Speaker 0"  # midpoint 2.5, in SPEAKER_00
    assert result.segments[1].speaker == "Speaker 1"  # midpoint 7.5, in SPEAKER_01
    assert result.segments[2].speaker == "Speaker 1"  # midpoint 12.5, in SPEAKER_01
    assert len(result.speakers) == 2


def test_merge_with_no_diarization():
    transcript_segments = [TranscriptSegment(start=0.0, end=5.0, text="Hello")]
    result = merge_diarization_with_transcript(transcript_segments, [])
    assert len(result.segments) == 1
    assert result.segments[0].speaker is None
    assert result.speakers == []
