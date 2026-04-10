import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pipeline.db import Base, get_db
from pipeline.models import Channel, Episode, Segment, Benchmark


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_store_diarization_segments(db):
    """Verify segments are stored correctly from diarization output."""
    channel = Channel(name="DOAC", slug="doac", youtube_id="@DOAC")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="abc123", title="Test", status="diarizing")
    db.add(episode)
    db.commit()

    from pipeline.core.diarizer_pyannote import TranscriptSegment, DiarizedTranscript

    transcript = DiarizedTranscript(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Speaker 0"),
            TranscriptSegment(start=5.0, end=10.0, text="World", speaker="Speaker 1"),
        ],
        speakers=["Speaker 0", "Speaker 1"],
        full_text="Hello World",
    )

    from pipeline.api.diarization import store_diarization_result
    store_diarization_result(db, episode.id, transcript)

    segments = db.query(Segment).filter(Segment.episode_id == episode.id).all()
    assert len(segments) == 2
    assert segments[0].text == "Hello"
    assert segments[0].speaker == "Speaker 0"
    assert segments[1].speaker == "Speaker 1"


def test_store_segments_per_diarizer(db):
    """Verify segments are stored and scoped independently per diarizer."""
    channel = Channel(name="DOAC", slug="doac", youtube_id="@DOAC")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="abc123", title="Test", status="diarizing")
    db.add(episode)
    db.commit()

    from pipeline.core.diarizer_pyannote import TranscriptSegment, DiarizedTranscript
    from pipeline.api.diarization import store_diarization_result

    pyannote_transcript = DiarizedTranscript(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Hello from pyannote", speaker="Speaker 0"),
            TranscriptSegment(start=5.0, end=10.0, text="World from pyannote", speaker="Speaker 1"),
        ],
        speakers=["Speaker 0", "Speaker 1"],
        full_text="Hello from pyannote World from pyannote",
    )

    whisper_transcript = DiarizedTranscript(
        segments=[
            TranscriptSegment(start=0.0, end=4.0, text="Hello from whisper", speaker="SPEAKER_00"),
            TranscriptSegment(start=4.0, end=9.0, text="World from whisper", speaker="SPEAKER_01"),
            TranscriptSegment(start=9.0, end=12.0, text="Extra from whisper", speaker="SPEAKER_00"),
        ],
        speakers=["SPEAKER_00", "SPEAKER_01"],
        full_text="Hello from whisper World from whisper Extra from whisper",
    )

    # Store pyannote segments
    store_diarization_result(db, episode.id, pyannote_transcript, diarizer="pyannote")
    # Store whisper segments
    store_diarization_result(db, episode.id, whisper_transcript, diarizer="whisper")

    # Both sets should coexist
    all_segments = db.query(Segment).filter(Segment.episode_id == episode.id).all()
    assert len(all_segments) == 5  # 2 pyannote + 3 whisper

    pyannote_segs = db.query(Segment).filter(
        Segment.episode_id == episode.id, Segment.diarizer == "pyannote"
    ).all()
    assert len(pyannote_segs) == 2
    assert pyannote_segs[0].text == "Hello from pyannote"

    whisper_segs = db.query(Segment).filter(
        Segment.episode_id == episode.id, Segment.diarizer == "whisper"
    ).all()
    assert len(whisper_segs) == 3
    assert whisper_segs[0].text == "Hello from whisper"

    # Re-storing pyannote should only replace pyannote segments, not whisper
    pyannote_transcript_v2 = DiarizedTranscript(
        segments=[
            TranscriptSegment(start=0.0, end=6.0, text="Updated pyannote", speaker="Speaker 0"),
        ],
        speakers=["Speaker 0"],
        full_text="Updated pyannote",
    )
    store_diarization_result(db, episode.id, pyannote_transcript_v2, diarizer="pyannote")

    all_segments = db.query(Segment).filter(Segment.episode_id == episode.id).all()
    assert len(all_segments) == 4  # 1 pyannote + 3 whisper

    pyannote_segs = db.query(Segment).filter(
        Segment.episode_id == episode.id, Segment.diarizer == "pyannote"
    ).all()
    assert len(pyannote_segs) == 1
    assert pyannote_segs[0].text == "Updated pyannote"

    # Whisper segments should be untouched
    whisper_segs = db.query(Segment).filter(
        Segment.episode_id == episode.id, Segment.diarizer == "whisper"
    ).all()
    assert len(whisper_segs) == 3


def test_get_benchmarks(db):
    """Verify benchmarks endpoint returns diarizer run metadata."""
    channel = Channel(name="DOAC", slug="doac", youtube_id="@DOAC")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="bench1", title="Test", status="done")
    db.add(episode)
    db.commit()

    db.add(Benchmark(episode_id=episode.id, diarizer="pyannote", duration_s=12.3))
    db.add(Benchmark(episode_id=episode.id, diarizer="whisper-diarization", duration_s=45.1))
    db.commit()

    from pipeline.api.diarization import get_benchmarks_for_episode
    results = get_benchmarks_for_episode(db, episode.id)
    assert len(results) == 2
    assert results[0].diarizer == "pyannote"
    assert results[1].diarizer == "whisper-diarization"
