import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pipeline.db import Base
from pipeline.models import Channel, Episode, Segment, Job, Benchmark


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_channel(db):
    channel = Channel(name="Diary of a CEO", slug="doac", youtube_id="@TheDiaryOfACEO")
    db.add(channel)
    db.commit()
    assert channel.id is not None
    assert channel.slug == "doac"


def test_create_episode_with_channel(db):
    channel = Channel(name="DOAC", slug="doac", youtube_id="@TheDiaryOfACEO")
    db.add(channel)
    db.commit()

    episode = Episode(
        channel_id=channel.id,
        youtube_id="abc123",
        title="Test Episode",
        status="pending",
    )
    db.add(episode)
    db.commit()
    assert episode.id is not None
    assert episode.channel_id == channel.id


def test_create_segments(db):
    channel = Channel(name="DOAC", slug="doac", youtube_id="@TheDiaryOfACEO")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="abc123", title="Test", status="diarizing")
    db.add(episode)
    db.commit()

    seg = Segment(
        episode_id=episode.id,
        start_time=10.5,
        end_time=15.2,
        text="Hello world",
        speaker="Speaker 0",
        tag="content",
    )
    db.add(seg)
    db.commit()
    assert seg.id is not None
    assert seg.tag == "content"


def test_create_job(db):
    channel = Channel(name="DOAC", slug="doac", youtube_id="@TheDiaryOfACEO")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="abc123", title="Test", status="pending")
    db.add(episode)
    db.commit()

    job = Job(episode_id=episode.id, stage="download", status="pending")
    db.add(job)
    db.commit()
    assert job.id is not None
    assert job.progress == 0.0


def test_create_benchmark(db):
    channel = Channel(name="DOAC", slug="doac", youtube_id="@TheDiaryOfACEO")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="abc123", title="Test", status="done")
    db.add(episode)
    db.commit()

    bench = Benchmark(episode_id=episode.id, diarizer="whisper-diarization", duration_s=120.5)
    db.add(bench)
    db.commit()
    assert bench.id is not None
    assert bench.diarizer == "whisper-diarization"
