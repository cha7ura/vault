import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pipeline.db import Base, get_db
import pipeline.models  # noqa: F401 — ensure all models register with Base
from pipeline.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_channel(client):
    r = client.post("/api/channels", json={
        "name": "Diary of a CEO", "slug": "doac", "youtube_id": "@TheDiaryOfACEO",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["slug"] == "doac"
    assert data["id"] is not None


def test_list_channels(client):
    client.post("/api/channels", json={"name": "DOAC", "slug": "doac", "youtube_id": "@DOAC"})
    r = client.get("/api/channels")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_create_episode_triggers_jobs(client):
    client.post("/api/channels", json={"name": "DOAC", "slug": "doac", "youtube_id": "@DOAC"})
    r = client.post("/api/episodes/ingest", json={
        "channel_slug": "doac",
        "youtube_url": "https://www.youtube.com/watch?v=test12345ab",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "pending"
    assert "id" in data


def test_list_jobs(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
