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

    from pipeline.core.diarizer_whisper import TranscriptSegment, DiarizedTranscript

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
    assert segments[0].diarizer == "whisper-diarization"
    assert segments[1].speaker == "Speaker 1"


def test_store_segments_replaces_existing(db):
    """Verify re-storing replaces existing segments for the same diarizer."""
    channel = Channel(name="DOAC", slug="doac", youtube_id="@DOAC")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="abc123", title="Test", status="diarizing")
    db.add(episode)
    db.commit()

    from pipeline.core.diarizer_whisper import TranscriptSegment, DiarizedTranscript
    from pipeline.api.diarization import store_diarization_result

    transcript_v1 = DiarizedTranscript(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Hello v1", speaker="Speaker 0"),
            TranscriptSegment(start=5.0, end=10.0, text="World v1", speaker="Speaker 1"),
        ],
        speakers=["Speaker 0", "Speaker 1"],
        full_text="Hello v1 World v1",
    )

    store_diarization_result(db, episode.id, transcript_v1)
    assert db.query(Segment).filter(Segment.episode_id == episode.id).count() == 2

    transcript_v2 = DiarizedTranscript(
        segments=[
            TranscriptSegment(start=0.0, end=6.0, text="Updated", speaker="Speaker 0"),
        ],
        speakers=["Speaker 0"],
        full_text="Updated",
    )

    store_diarization_result(db, episode.id, transcript_v2)
    segments = db.query(Segment).filter(Segment.episode_id == episode.id).all()
    assert len(segments) == 1
    assert segments[0].text == "Updated"


def test_get_benchmarks(db):
    """Verify benchmarks endpoint returns diarizer run metadata."""
    channel = Channel(name="DOAC", slug="doac", youtube_id="@DOAC")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="bench1", title="Test", status="done")
    db.add(episode)
    db.commit()

    db.add(Benchmark(episode_id=episode.id, diarizer="whisper-diarization", duration_s=45.1))
    db.commit()

    from pipeline.api.diarization import get_benchmarks_for_episode
    results = get_benchmarks_for_episode(db, episode.id)
    assert len(results) == 1
    assert results[0].diarizer == "whisper-diarization"
