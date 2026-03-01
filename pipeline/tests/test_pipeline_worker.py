import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pipeline.db import Base
from pipeline.models import Channel, Episode, Job
from pipeline.workers.pipeline_worker import create_ingestion_jobs, update_job_status


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_ingestion_jobs(db):
    channel = Channel(name="DOAC", slug="doac", youtube_id="@DOAC")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="abc123", title="Test", status="pending")
    db.add(episode)
    db.commit()
    jobs = create_ingestion_jobs(db, episode.id)
    assert len(jobs) == 3
    assert jobs[0].stage == "download"
    assert jobs[1].stage == "preprocess"
    assert jobs[2].stage == "diarize"
    assert all(j.status == "pending" for j in jobs)


def test_update_job_status(db):
    channel = Channel(name="DOAC", slug="doac", youtube_id="@DOAC")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="abc123", title="Test", status="pending")
    db.add(episode)
    db.commit()
    job = Job(episode_id=episode.id, stage="download", status="pending")
    db.add(job)
    db.commit()
    update_job_status(db, job.id, "running", progress=0.5)
    db.refresh(job)
    assert job.status == "running"
    assert job.progress == 0.5
