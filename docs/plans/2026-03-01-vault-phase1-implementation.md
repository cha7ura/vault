# Vault Phase 1: Pipeline Core — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a working Python pipeline that downloads YouTube audio, preprocesses it, runs dual speaker diarization (whisper-diarization + PyAnnote), and stores everything in SQLite — all local, no cloud APIs.

**Architecture:** A FastAPI application with SQLAlchemy models backed by SQLite. The pipeline stages (download → preprocess → diarize) are independent Python modules orchestrated by a background worker. Each stage reads from and writes to the database. A minimal FastAPI server exposes REST endpoints for triggering and monitoring jobs.

**Tech Stack:** Python 3.12, uv (package manager), FastAPI, SQLAlchemy 2.0, SQLite, yt-dlp, ffmpeg, faster-whisper, pyannote.audio, whisper-diarization (NeMo), librosa, pytest

**Prerequisites already on system:** Python 3.12, uv, ffmpeg, yt-dlp

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pipeline/pyproject.toml`
- Create: `pipeline/main.py`
- Create: `pipeline/config.py`
- Create: `pipeline/__init__.py`
- Create: `pipeline/models/__init__.py`
- Create: `pipeline/core/__init__.py`
- Create: `pipeline/api/__init__.py`
- Create: `pipeline/workers/__init__.py`
- Create: `pipeline/tests/__init__.py`
- Create: `data/.gitkeep`
- Modify: `.gitignore`
- Create: `Makefile`

**Step 1: Create pyproject.toml with core dependencies**

```toml
[project]
name = "vault-pipeline"
version = "0.1.0"
description = "Local-first YouTube podcast knowledge extraction pipeline"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sqlalchemy>=2.0.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "yt-dlp>=2024.0.0",
    "librosa>=0.10.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
diarize-whisper = [
    "faster-whisper>=1.0.0",
    "ctc-forced-aligner>=0.3.0",
    "nemo-toolkit[asr]>=2.0.0",
    "demucs>=4.0.0",
]
diarize-pyannote = [
    "pyannote.audio>=3.1.0",
    "faster-whisper>=1.0.0",
]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Step 2: Create config.py**

```python
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Paths
    data_dir: Path = Path(__file__).parent.parent / "data"
    db_url: str = ""  # computed in model_post_init

    # LM Studio
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "default"

    # Pipeline defaults
    audio_sample_rate: int = 16000
    default_whisper_model: str = "medium.en"
    default_diarizer: str = "whisper-diarization"

    # HuggingFace (only needed for PyAnnote model download)
    hf_token: str = ""

    model_config = {"env_prefix": "VAULT_", "env_file": ".env"}

    def model_post_init(self, __context) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "audio").mkdir(exist_ok=True)
        (self.data_dir / "transcripts").mkdir(exist_ok=True)
        if not self.db_url:
            self.db_url = f"sqlite:///{self.data_dir / 'vault.db'}"


settings = Settings()
```

**Step 3: Create db.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from pipeline.config import settings

engine = create_engine(settings.db_url, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
```

**Step 4: Create main.py**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pipeline.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Vault Pipeline", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
```

**Step 5: Create all `__init__.py` files (empty)**

Create empty `__init__.py` in: `pipeline/`, `pipeline/models/`, `pipeline/core/`, `pipeline/api/`, `pipeline/workers/`, `pipeline/tests/`

**Step 6: Update .gitignore**

Append to existing `.gitignore`:
```
# Vault pipeline
data/audio/
data/transcripts/
data/*.db
pipeline/__pycache__/
pipeline/**/__pycache__/
.venv/
*.egg-info/
.env
```

**Step 7: Create Makefile**

```makefile
.PHONY: setup dev test

setup:
	cd pipeline && uv venv && uv pip install -e ".[dev]"

dev:
	cd pipeline && uv run uvicorn pipeline.main:app --reload --port 8000

test:
	cd pipeline && uv run pytest -v
```

**Step 8: Install dependencies and verify**

Run: `cd pipeline && uv venv && uv pip install -e ".[dev]"`
Expected: Clean install, no errors

**Step 9: Verify server starts**

Run: `cd pipeline && uv run uvicorn pipeline.main:app --port 8000 &` then `curl http://localhost:8000/health`
Expected: `{"status":"ok"}`

**Step 10: Commit**

```bash
git add pipeline/ data/.gitkeep .gitignore Makefile
git commit -m "feat(pipeline): scaffold project — FastAPI, SQLAlchemy, config, Makefile"
```

---

## Task 2: SQLAlchemy Models

**Files:**
- Create: `pipeline/models/channel.py`
- Create: `pipeline/models/episode.py`
- Create: `pipeline/models/segment.py`
- Create: `pipeline/models/insight.py`
- Create: `pipeline/models/guest.py`
- Create: `pipeline/models/job.py`
- Create: `pipeline/models/benchmark.py`
- Modify: `pipeline/models/__init__.py`
- Create: `pipeline/tests/test_models.py`

**Step 1: Write the failing test**

```python
# pipeline/tests/test_models.py
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
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Channel' from 'pipeline.models'`

**Step 3: Implement all models**

`pipeline/models/channel.py`:
```python
from datetime import datetime
from sqlalchemy import String, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pipeline.db import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    youtube_id: Mapped[str] = mapped_column(String(255), unique=True)
    intro_skip: Mapped[float] = mapped_column(Float, default=0.0)
    config: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    episodes = relationship("Episode", back_populates="channel")
```

`pipeline/models/episode.py`:
```python
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pipeline.db import Base


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    youtube_id: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    intro_end_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    channel = relationship("Channel", back_populates="episodes")
    segments = relationship("Segment", back_populates="episode")
    insights = relationship("Insight", back_populates="episode")
    jobs = relationship("Job", back_populates="episode")
    benchmarks = relationship("Benchmark", back_populates="episode")
```

`pipeline/models/segment.py`:
```python
from datetime import datetime
from sqlalchemy import String, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pipeline.db import Base


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"))
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    speaker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tag: Mapped[str] = mapped_column(String(50), default="content")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    episode = relationship("Episode", back_populates="segments")
```

`pipeline/models/insight.py`:
```python
from datetime import datetime
from sqlalchemy import String, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pipeline.db import Base


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"))
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    start_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    speaker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    episode = relationship("Episode", back_populates="insights")
```

`pipeline/models/guest.py`:
```python
from datetime import datetime
from sqlalchemy import String, Text, Table, Column, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pipeline.db import Base

episode_guests = Table(
    "episode_guests",
    Base.metadata,
    Column("episode_id", Integer, ForeignKey("episodes.id"), primary_key=True),
    Column("guest_id", Integer, ForeignKey("guests.id"), primary_key=True),
)


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    links: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    episodes = relationship("Episode", secondary=episode_guests, backref="guests")
```

`pipeline/models/job.py`:
```python
from datetime import datetime
from sqlalchemy import String, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pipeline.db import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"))
    stage: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    episode = relationship("Episode", back_populates="jobs")
```

`pipeline/models/benchmark.py`:
```python
from datetime import datetime
from sqlalchemy import String, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pipeline.db import Base


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"))
    diarizer: Mapped[str] = mapped_column(String(100))
    config: Mapped[str | None] = mapped_column(Text, nullable=True)
    wer: Mapped[float | None] = mapped_column(Float, nullable=True)
    der: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    episode = relationship("Episode", back_populates="benchmarks")
```

`pipeline/models/__init__.py`:
```python
from pipeline.models.channel import Channel
from pipeline.models.episode import Episode
from pipeline.models.segment import Segment
from pipeline.models.insight import Insight
from pipeline.models.guest import Guest, episode_guests
from pipeline.models.job import Job
from pipeline.models.benchmark import Benchmark

__all__ = [
    "Channel", "Episode", "Segment", "Insight",
    "Guest", "episode_guests", "Job", "Benchmark",
]
```

**Step 4: Run tests to verify they pass**

Run: `cd pipeline && uv run pytest tests/test_models.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add pipeline/models/ pipeline/tests/test_models.py
git commit -m "feat(pipeline): add SQLAlchemy models — channels, episodes, segments, insights, jobs, benchmarks"
```

---

## Task 3: YouTube Downloader

**Files:**
- Create: `pipeline/core/downloader.py`
- Create: `pipeline/tests/test_downloader.py`

**Step 1: Write the failing test**

```python
# pipeline/tests/test_downloader.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from pipeline.core.downloader import extract_video_id, get_video_metadata, download_audio


def test_extract_video_id_from_watch_url():
    assert extract_video_id("https://www.youtube.com/watch?v=abc123") == "abc123"


def test_extract_video_id_from_short_url():
    assert extract_video_id("https://youtu.be/abc123") == "abc123"


def test_extract_video_id_from_bare_id():
    assert extract_video_id("abc123") == "abc123"


def test_extract_video_id_invalid():
    with pytest.raises(ValueError):
        extract_video_id("")


@patch("pipeline.core.downloader.yt_dlp.YoutubeDL")
def test_get_video_metadata(mock_ydl_class):
    mock_ydl = MagicMock()
    mock_ydl_class.return_value.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = {
        "id": "abc123",
        "title": "Test Episode",
        "description": "A test",
        "duration": 3600,
        "upload_date": "20260101",
        "thumbnail": "https://img.youtube.com/vi/abc123/0.jpg",
        "channel_id": "UC123",
        "channel": "Test Channel",
    }

    meta = get_video_metadata("abc123")
    assert meta["youtube_id"] == "abc123"
    assert meta["title"] == "Test Episode"
    assert meta["duration"] == 3600


@patch("pipeline.core.downloader.yt_dlp.YoutubeDL")
def test_download_audio(mock_ydl_class, tmp_path):
    mock_ydl = MagicMock()
    mock_ydl_class.return_value.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)

    # Simulate yt-dlp creating the output file
    output_file = tmp_path / "audio" / "test" / "abc123.wav"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(b"fake audio data")

    mock_ydl.extract_info.return_value = {"id": "abc123"}

    result = download_audio("abc123", tmp_path / "audio" / "test")
    mock_ydl.extract_info.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_downloader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.core.downloader'`

**Step 3: Implement downloader**

```python
# pipeline/core/downloader.py
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yt_dlp


def extract_video_id(url_or_id: str) -> str:
    """Extract YouTube video ID from URL or bare ID."""
    if not url_or_id:
        raise ValueError("Empty URL or video ID")

    # youtube.com/watch?v=ID
    match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url_or_id)
    if match:
        return match.group(1)

    # Bare ID (11 chars, alphanumeric + _ -)
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id

    raise ValueError(f"Cannot extract video ID from: {url_or_id}")


def get_video_metadata(video_id: str) -> dict[str, Any]:
    """Fetch video metadata without downloading."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)

    upload_date = info.get("upload_date")
    published_at = None
    if upload_date:
        published_at = datetime.strptime(upload_date, "%Y%m%d")

    return {
        "youtube_id": info["id"],
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "duration": info.get("duration"),
        "published_at": published_at,
        "thumbnail_url": info.get("thumbnail"),
        "channel_youtube_id": info.get("channel_id"),
        "channel_name": info.get("channel"),
    }


def download_audio(video_id: str, output_dir: Path) -> Path:
    """Download audio from YouTube video as WAV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / f"{video_id}.%(ext)s")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)

    output_path = output_dir / f"{video_id}.wav"
    return output_path


def list_channel_videos(channel_url: str, limit: int | None = None) -> list[dict[str, Any]]:
    """List videos from a YouTube channel."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": limit,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    videos = []
    for entry in info.get("entries", []):
        if entry:
            videos.append({
                "youtube_id": entry.get("id"),
                "title": entry.get("title", ""),
                "duration": entry.get("duration"),
            })

    return videos
```

**Step 4: Run tests to verify they pass**

Run: `cd pipeline && uv run pytest tests/test_downloader.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add pipeline/core/downloader.py pipeline/tests/test_downloader.py
git commit -m "feat(pipeline): add YouTube downloader — yt-dlp video ID extraction, metadata, audio download"
```

---

## Task 4: Audio Preprocessor

**Files:**
- Create: `pipeline/core/preprocessor.py`
- Create: `pipeline/tests/test_preprocessor.py`

**Step 1: Write the failing test**

```python
# pipeline/tests/test_preprocessor.py
import numpy as np
import pytest
import soundfile as sf
from pathlib import Path

from pipeline.core.preprocessor import convert_to_mono_16k, detect_intro_end


@pytest.fixture
def sample_audio(tmp_path) -> Path:
    """Create a synthetic audio file: loud intro (3s) + silence (1s) + speech (6s)."""
    sr = 44100
    duration = 10

    # Loud intro (simulates music)
    intro = np.random.randn(3 * sr).astype(np.float32) * 0.8
    # Silence gap
    silence = np.zeros(1 * sr, dtype=np.float32)
    # Steady speech (lower amplitude, consistent)
    speech = np.random.randn(6 * sr).astype(np.float32) * 0.2

    audio = np.concatenate([intro, silence, speech])
    path = tmp_path / "test_audio.wav"
    sf.write(str(path), audio, sr)
    return path


def test_convert_to_mono_16k(sample_audio, tmp_path):
    output = tmp_path / "converted.wav"
    result = convert_to_mono_16k(sample_audio, output)
    assert result.exists()

    import librosa
    y, sr = librosa.load(str(result), sr=None)
    assert sr == 16000
    assert y.ndim == 1  # mono


def test_detect_intro_end(sample_audio):
    """Intro detection should find the boundary near 3-4 seconds."""
    boundary = detect_intro_end(sample_audio)
    # Should detect the transition from loud intro to speech around 3-4 seconds
    assert 2.0 <= boundary <= 6.0


def test_detect_intro_end_no_intro(tmp_path):
    """Audio with no intro should return 0."""
    sr = 16000
    # Uniform speech-like audio
    audio = np.random.randn(10 * sr).astype(np.float32) * 0.2
    path = tmp_path / "no_intro.wav"
    sf.write(str(path), audio, sr)

    boundary = detect_intro_end(path)
    assert boundary == 0.0
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_preprocessor.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement preprocessor**

Note: Add `soundfile` to pyproject.toml dependencies if not covered by librosa.

```python
# pipeline/core/preprocessor.py
import subprocess
from pathlib import Path

import librosa
import numpy as np


def convert_to_mono_16k(input_path: Path, output_path: Path) -> Path:
    """Convert audio to 16kHz mono WAV using ffmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ac", "1",          # mono
        "-ar", "16000",      # 16kHz
        "-acodec", "pcm_s16le",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def detect_intro_end(audio_path: Path, window_sec: float = 2.0, threshold_ratio: float = 2.0) -> float:
    """Detect where the intro ends by finding a loud→quiet energy transition.

    Looks for a window where RMS energy drops significantly compared to
    the opening, suggesting a transition from intro music/montage to speech.

    Returns the estimated timestamp (seconds) where the interview starts.
    Returns 0.0 if no clear intro is detected.
    """
    y, sr = librosa.load(str(audio_path), sr=16000, mono=True)
    window_samples = int(window_sec * sr)

    # Compute RMS energy in non-overlapping windows
    n_windows = len(y) // window_samples
    if n_windows < 3:
        return 0.0

    rms_values = []
    for i in range(n_windows):
        start = i * window_samples
        end = start + window_samples
        rms = np.sqrt(np.mean(y[start:end] ** 2))
        rms_values.append(rms)

    rms_values = np.array(rms_values)

    # The intro is characterized by high energy (music).
    # Look for first significant energy drop from the opening level.
    opening_rms = rms_values[0]
    if opening_rms < 0.01:
        return 0.0  # No loud intro detected

    for i in range(1, len(rms_values)):
        if rms_values[i] < opening_rms / threshold_ratio:
            # Found the drop — intro ends at this window boundary
            return i * window_sec

    return 0.0  # No clear transition found
```

**Step 4: Run tests to verify they pass**

Run: `cd pipeline && uv run pytest tests/test_preprocessor.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add pipeline/core/preprocessor.py pipeline/tests/test_preprocessor.py
git commit -m "feat(pipeline): add audio preprocessor — ffmpeg mono/16kHz conversion + intro detection"
```

---

## Task 5: PyAnnote Diarizer

**Files:**
- Create: `pipeline/core/diarizer_pyannote.py`
- Create: `pipeline/tests/test_diarizer_pyannote.py`

**Step 1: Write the failing test**

```python
# pipeline/tests/test_diarizer_pyannote.py
import pytest
from unittest.mock import patch, MagicMock

from pipeline.core.diarizer_pyannote import (
    DiarizationSegment,
    TranscriptSegment,
    merge_diarization_with_transcript,
)


def test_merge_diarization_with_transcript():
    """Test merging speaker labels onto transcript segments."""
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
    assert result.segments[0].speaker == "Speaker 0"
    assert result.segments[1].speaker == "Speaker 0"  # midpoint 7.5 > 7.0, so Speaker 1
    assert result.segments[2].speaker == "Speaker 1"
    assert len(result.speakers) == 2


def test_merge_with_no_diarization():
    transcript_segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello"),
    ]

    result = merge_diarization_with_transcript(transcript_segments, [])
    assert len(result.segments) == 1
    assert result.segments[0].speaker is None
    assert result.speakers == []
```

Note: The midpoint of segment 2 (5.0-10.0) is 7.5, which falls in SPEAKER_01's range (7.0-15.0), so it should be Speaker 1. Update the assertion:

```python
    assert result.segments[1].speaker == "Speaker 1"  # midpoint 7.5 > 7.0
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_diarizer_pyannote.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement PyAnnote diarizer**

```python
# pipeline/core/diarizer_pyannote.py
"""Speaker diarization using PyAnnote + faster-whisper.

PyAnnote provides speaker segmentation (who spoke when).
faster-whisper provides transcription (what was said).
This module merges both outputs into speaker-labeled transcript segments.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DiarizationSegment:
    start: float
    end: float
    speaker: str


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass
class DiarizedTranscript:
    segments: list[TranscriptSegment]
    speakers: list[str]
    full_text: str = ""


def merge_diarization_with_transcript(
    transcript_segments: list[TranscriptSegment],
    diarization_segments: list[DiarizationSegment],
) -> DiarizedTranscript:
    """Merge speaker labels onto transcript segments using midpoint overlap."""
    if not diarization_segments:
        return DiarizedTranscript(
            segments=transcript_segments,
            speakers=[],
            full_text=" ".join(s.text for s in transcript_segments),
        )

    # Build speaker label map
    speaker_labels = sorted(set(d.speaker for d in diarization_segments))
    speaker_index = {label: idx for idx, label in enumerate(speaker_labels)}
    speaker_names = [f"Speaker {i}" for i in range(len(speaker_labels))]

    merged = []
    for seg in transcript_segments:
        midpoint = (seg.start + seg.end) / 2
        match = next(
            (d for d in diarization_segments if d.start <= midpoint <= d.end),
            None,
        )
        speaker_name = speaker_names[speaker_index[match.speaker]] if match else None
        merged.append(TranscriptSegment(
            start=seg.start, end=seg.end, text=seg.text, speaker=speaker_name,
        ))

    return DiarizedTranscript(
        segments=merged,
        speakers=speaker_names,
        full_text=" ".join(s.text for s in merged),
    )


def transcribe_with_faster_whisper(
    audio_path: Path,
    model_size: str = "medium.en",
    device: str = "auto",
) -> list[TranscriptSegment]:
    """Transcribe audio using faster-whisper. Returns timestamped segments."""
    from faster_whisper import WhisperModel

    compute_type = "float16" if device == "cuda" else "int8"
    if device == "auto":
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments_iter, info = model.transcribe(str(audio_path), beam_size=5)

    segments = []
    for seg in segments_iter:
        segments.append(TranscriptSegment(
            start=seg.start,
            end=seg.end,
            text=seg.text.strip(),
        ))

    return segments


def diarize_with_pyannote(
    audio_path: Path,
    hf_token: str,
    device: str = "auto",
) -> list[DiarizationSegment]:
    """Run PyAnnote speaker diarization. Returns speaker-labeled time segments."""
    import torch
    from pyannote.audio import Pipeline

    if device == "auto":
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token,
    )
    pipeline.to(torch.device(device))

    diarization = pipeline(str(audio_path))

    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(DiarizationSegment(
            start=round(turn.start, 3),
            end=round(turn.end, 3),
            speaker=speaker,
        ))

    return segments


def run_pyannote_pipeline(
    audio_path: Path,
    hf_token: str,
    whisper_model: str = "medium.en",
    device: str = "auto",
) -> DiarizedTranscript:
    """Full pipeline: transcribe with Whisper, diarize with PyAnnote, merge."""
    transcript_segments = transcribe_with_faster_whisper(audio_path, whisper_model, device)
    diarization_segments = diarize_with_pyannote(audio_path, hf_token, device)
    return merge_diarization_with_transcript(transcript_segments, diarization_segments)
```

**Step 4: Run tests to verify they pass**

Run: `cd pipeline && uv run pytest tests/test_diarizer_pyannote.py -v`
Expected: All 2 tests PASS (only testing the merge logic, not the ML models)

**Step 5: Commit**

```bash
git add pipeline/core/diarizer_pyannote.py pipeline/tests/test_diarizer_pyannote.py
git commit -m "feat(pipeline): add PyAnnote diarizer — faster-whisper STT + PyAnnote speaker labels + merge"
```

---

## Task 6: whisper-diarization Diarizer

**Files:**
- Create: `pipeline/core/diarizer_whisper.py`
- Create: `pipeline/tests/test_diarizer_whisper.py`

**Step 1: Write the failing test**

```python
# pipeline/tests/test_diarizer_whisper.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from pipeline.core.diarizer_whisper import parse_whisper_diarization_output


def test_parse_whisper_diarization_output():
    """Test parsing the SRT/text output from whisper-diarization."""
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
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_diarizer_whisper.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement whisper-diarization wrapper**

```python
# pipeline/core/diarizer_whisper.py
"""Speaker diarization using the whisper-diarization pipeline.

Wraps MahmoudAshraf97/whisper-diarization which combines:
- Demucs for vocal separation
- faster-whisper for STT
- CTC forced aligner for word-level timestamps
- NeMo MarbleNet for VAD + TitaNet for speaker embeddings

This module runs it as a subprocess and parses the output.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass
class DiarizedTranscript:
    segments: list[TranscriptSegment]
    speakers: list[str]
    full_text: str = ""


def parse_whisper_diarization_output(raw_output: str) -> DiarizedTranscript:
    """Parse the text output from whisper-diarization's diarize.py.

    Expected format per line: [0.00s - 5.20s] Speaker 0: Hello and welcome.
    """
    if not raw_output.strip():
        return DiarizedTranscript(segments=[], speakers=[], full_text="")

    pattern = re.compile(
        r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(Speaker\s*\d+):\s*(.*)"
    )

    segments = []
    speakers_set: set[str] = set()

    for line in raw_output.strip().splitlines():
        match = pattern.match(line.strip())
        if match:
            start = float(match.group(1))
            end = float(match.group(2))
            speaker = match.group(3).strip()
            text = match.group(4).strip()

            segments.append(TranscriptSegment(
                start=start, end=end, text=text, speaker=speaker,
            ))
            speakers_set.add(speaker)

    speakers = sorted(speakers_set)

    return DiarizedTranscript(
        segments=segments,
        speakers=speakers,
        full_text=" ".join(s.text for s in segments),
    )


def run_whisper_diarization(
    audio_path: Path,
    whisper_model: str = "medium.en",
    device: str = "cpu",
    no_stem: bool = False,
    batch_size: int = 8,
) -> DiarizedTranscript:
    """Run the whisper-diarization pipeline as a subprocess.

    Requires whisper-diarization to be installed:
        pip install -r requirements.txt  (from whisper-diarization repo)

    The diarize.py script writes a .txt file next to the audio.
    """
    cmd = [
        "python3", "-m", "diarize",
        "-a", str(audio_path),
        "--whisper-model", whisper_model,
        "--device", device,
        "--batch-size", str(batch_size),
    ]
    if no_stem:
        cmd.append("--no-stem")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60 * 60,  # 1 hour timeout for long episodes
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"whisper-diarization failed: {result.stderr}"
        )

    # Read the output .txt file
    output_path = audio_path.with_suffix(".txt")
    if output_path.exists():
        raw_output = output_path.read_text()
        return parse_whisper_diarization_output(raw_output)

    # Fallback: try parsing stdout
    return parse_whisper_diarization_output(result.stdout)
```

**Step 4: Run tests to verify they pass**

Run: `cd pipeline && uv run pytest tests/test_diarizer_whisper.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add pipeline/core/diarizer_whisper.py pipeline/tests/test_diarizer_whisper.py
git commit -m "feat(pipeline): add whisper-diarization wrapper — subprocess runner + output parser"
```

---

## Task 7: Pipeline Worker (Orchestration)

**Files:**
- Create: `pipeline/workers/pipeline_worker.py`
- Create: `pipeline/tests/test_pipeline_worker.py`

**Step 1: Write the failing test**

```python
# pipeline/tests/test_pipeline_worker.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
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
    """Creating ingestion jobs should produce download+preprocess+diarize jobs."""
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
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_pipeline_worker.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement pipeline worker**

```python
# pipeline/workers/pipeline_worker.py
"""Pipeline orchestration — creates and runs jobs for episode processing."""

from datetime import datetime

from sqlalchemy.orm import Session

from pipeline.models import Episode, Job


def create_ingestion_jobs(db: Session, episode_id: int) -> list[Job]:
    """Create the standard pipeline jobs for an episode."""
    stages = ["download", "preprocess", "diarize"]
    jobs = []
    for stage in stages:
        job = Job(episode_id=episode_id, stage=stage, status="pending")
        db.add(job)
        jobs.append(job)
    db.commit()
    return jobs


def update_job_status(
    db: Session,
    job_id: int,
    status: str,
    progress: float | None = None,
    error: str | None = None,
) -> Job:
    """Update a job's status and optional progress/error."""
    job = db.query(Job).filter(Job.id == job_id).one()
    job.status = status
    if progress is not None:
        job.progress = progress
    if error is not None:
        job.error = error
    if status == "running" and job.started_at is None:
        job.started_at = datetime.utcnow()
    if status in ("completed", "failed"):
        job.completed_at = datetime.utcnow()
        if status == "completed":
            job.progress = 1.0
    db.commit()
    return job


def get_next_pending_job(db: Session, episode_id: int) -> Job | None:
    """Get the next pending job for an episode, in stage order."""
    stage_order = ["download", "preprocess", "diarize", "extract"]
    for stage in stage_order:
        job = (
            db.query(Job)
            .filter(Job.episode_id == episode_id, Job.stage == stage, Job.status == "pending")
            .first()
        )
        if job:
            return job
    return None


async def run_pipeline(db: Session, episode_id: int) -> None:
    """Run all pipeline stages for an episode sequentially."""
    from pipeline.core.downloader import download_audio, get_video_metadata
    from pipeline.core.preprocessor import convert_to_mono_16k, detect_intro_end
    from pipeline.config import settings

    episode = db.query(Episode).filter(Episode.id == episode_id).one()

    while True:
        job = get_next_pending_job(db, episode_id)
        if job is None:
            break

        update_job_status(db, job.id, "running")
        episode.status = job.stage.replace("download", "downloading").replace(
            "preprocess", "preprocessing"
        ).replace("diarize", "diarizing")
        db.commit()

        try:
            if job.stage == "download":
                channel = episode.channel
                audio_dir = settings.data_dir / "audio" / channel.slug
                audio_path = download_audio(episode.youtube_id, audio_dir)
                episode.audio_path = str(audio_path)
                db.commit()

            elif job.stage == "preprocess":
                if not episode.audio_path:
                    raise RuntimeError("No audio file — download stage must run first")
                from pathlib import Path
                audio_path = Path(episode.audio_path)
                # Convert to 16kHz mono if needed
                mono_path = audio_path.with_stem(audio_path.stem + "_16k")
                convert_to_mono_16k(audio_path, mono_path)
                # Detect intro
                intro_end = detect_intro_end(mono_path)
                episode.intro_end_at = intro_end
                episode.audio_path = str(mono_path)
                db.commit()

            elif job.stage == "diarize":
                # This stage is run manually via the dashboard for now
                # (user picks which diarizer to use and reviews output)
                pass

            update_job_status(db, job.id, "completed")

        except Exception as e:
            update_job_status(db, job.id, "failed", error=str(e))
            episode.status = "error"
            db.commit()
            break

    # If all jobs completed, set episode to reviewing
    pending = db.query(Job).filter(
        Job.episode_id == episode_id, Job.status.in_(["pending", "running"])
    ).count()
    if pending == 0:
        failed = db.query(Job).filter(
            Job.episode_id == episode_id, Job.status == "failed"
        ).count()
        if failed == 0:
            episode.status = "reviewing"
            db.commit()
```

**Step 4: Run tests to verify they pass**

Run: `cd pipeline && uv run pytest tests/test_pipeline_worker.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add pipeline/workers/pipeline_worker.py pipeline/tests/test_pipeline_worker.py
git commit -m "feat(pipeline): add pipeline worker — job creation, status updates, sequential orchestration"
```

---

## Task 8: FastAPI Routes (Channels + Episodes + Jobs)

**Files:**
- Create: `pipeline/api/channels.py`
- Create: `pipeline/api/episodes.py`
- Create: `pipeline/api/jobs.py`
- Modify: `pipeline/main.py`
- Create: `pipeline/tests/test_api.py`

**Step 1: Write the failing test**

```python
# pipeline/tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pipeline.db import Base, get_db
from pipeline.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:")
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
        "name": "Diary of a CEO",
        "slug": "doac",
        "youtube_id": "@TheDiaryOfACEO",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["slug"] == "doac"
    assert data["id"] is not None


def test_list_channels(client):
    client.post("/api/channels", json={
        "name": "DOAC", "slug": "doac", "youtube_id": "@DOAC",
    })
    r = client.get("/api/channels")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_create_episode_triggers_jobs(client):
    # Create channel first
    client.post("/api/channels", json={
        "name": "DOAC", "slug": "doac", "youtube_id": "@DOAC",
    })

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
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_api.py -v`
Expected: FAIL — route not found (404)

**Step 3: Implement API routes**

`pipeline/api/channels.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.models import Channel

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelCreate(BaseModel):
    name: str
    slug: str
    youtube_id: str
    intro_skip: float = 0.0


class ChannelResponse(BaseModel):
    id: int
    name: str
    slug: str
    youtube_id: str
    intro_skip: float

    model_config = {"from_attributes": True}


@router.post("", status_code=201, response_model=ChannelResponse)
def create_channel(body: ChannelCreate, db: Session = Depends(get_db)):
    existing = db.query(Channel).filter(Channel.slug == body.slug).first()
    if existing:
        raise HTTPException(400, f"Channel with slug '{body.slug}' already exists")
    channel = Channel(**body.model_dump())
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.get("", response_model=list[ChannelResponse])
def list_channels(db: Session = Depends(get_db)):
    return db.query(Channel).all()


@router.get("/{slug}", response_model=ChannelResponse)
def get_channel(slug: str, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.slug == slug).first()
    if not channel:
        raise HTTPException(404, "Channel not found")
    return channel
```

`pipeline/api/episodes.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.models import Channel, Episode
from pipeline.core.downloader import extract_video_id
from pipeline.workers.pipeline_worker import create_ingestion_jobs

router = APIRouter(prefix="/api/episodes", tags=["episodes"])


class IngestRequest(BaseModel):
    channel_slug: str
    youtube_url: str


class EpisodeResponse(BaseModel):
    id: int
    channel_id: int
    youtube_id: str
    title: str
    status: str
    duration: float | None = None
    intro_end_at: float | None = None

    model_config = {"from_attributes": True}


@router.post("/ingest", status_code=201, response_model=EpisodeResponse)
def ingest_episode(body: IngestRequest, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.slug == body.channel_slug).first()
    if not channel:
        raise HTTPException(404, f"Channel '{body.channel_slug}' not found")

    video_id = extract_video_id(body.youtube_url)

    existing = db.query(Episode).filter(Episode.youtube_id == video_id).first()
    if existing:
        raise HTTPException(400, f"Episode '{video_id}' already exists")

    episode = Episode(
        channel_id=channel.id,
        youtube_id=video_id,
        title=f"Pending: {video_id}",
        status="pending",
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)

    create_ingestion_jobs(db, episode.id)

    return episode


@router.get("/{episode_id}", response_model=EpisodeResponse)
def get_episode(episode_id: int, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(404, "Episode not found")
    return episode
```

`pipeline/api/jobs.py`:
```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.models import Job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    id: int
    episode_id: int
    stage: str
    status: str
    progress: float
    error: str | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[JobResponse])
def list_jobs(
    status: str | None = None,
    episode_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    if episode_id:
        query = query.filter(Job.episode_id == episode_id)
    return query.order_by(Job.id.desc()).all()
```

**Step 4: Register routers in main.py**

Update `pipeline/main.py`:
```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pipeline.db import init_db
from pipeline.api.channels import router as channels_router
from pipeline.api.episodes import router as episodes_router
from pipeline.api.jobs import router as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Vault Pipeline", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(channels_router)
app.include_router(episodes_router)
app.include_router(jobs_router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

**Step 5: Run tests to verify they pass**

Run: `cd pipeline && uv run pytest tests/test_api.py -v`
Expected: All 5 tests PASS

**Step 6: Commit**

```bash
git add pipeline/api/ pipeline/main.py pipeline/tests/test_api.py
git commit -m "feat(pipeline): add FastAPI routes — channels CRUD, episode ingestion, job listing"
```

---

## Task 9: Integration Test — End-to-End Download

**Files:**
- Create: `pipeline/tests/test_integration.py`

This test downloads a SHORT real YouTube video (a 30-second test clip) and verifies the full download → preprocess flow. Mark it with `@pytest.mark.integration` so it's skipped by default.

**Step 1: Write the integration test**

```python
# pipeline/tests/test_integration.py
import pytest
from pathlib import Path

from pipeline.core.downloader import extract_video_id, download_audio, get_video_metadata
from pipeline.core.preprocessor import convert_to_mono_16k, detect_intro_end


@pytest.mark.integration
def test_download_and_preprocess(tmp_path):
    """End-to-end: download a short YouTube video and preprocess it.

    Uses a Creative Commons test video. Skip with: pytest -m "not integration"
    """
    # Use a very short CC video for testing
    video_id = "jNQXAC9IVRw"  # "Me at the zoo" — first YouTube video, 19 seconds

    # Download
    audio_dir = tmp_path / "audio"
    audio_path = download_audio(video_id, audio_dir)
    assert audio_path.exists() or (audio_dir / f"{video_id}.wav").exists()

    # Get actual path (yt-dlp may name slightly differently)
    wav_files = list(audio_dir.glob("*.wav"))
    assert len(wav_files) >= 1
    audio_path = wav_files[0]

    # Preprocess
    mono_path = tmp_path / "mono.wav"
    convert_to_mono_16k(audio_path, mono_path)
    assert mono_path.exists()

    # Intro detection (short video — should return 0.0)
    intro_end = detect_intro_end(mono_path)
    assert intro_end >= 0.0


@pytest.mark.integration
def test_get_video_metadata():
    meta = get_video_metadata("jNQXAC9IVRw")
    assert meta["youtube_id"] == "jNQXAC9IVRw"
    assert "zoo" in meta["title"].lower()
    assert meta["duration"] > 0
```

**Step 2: Update pyproject.toml pytest config**

Add to `[tool.pytest.ini_options]`:
```toml
markers = [
    "integration: marks tests that require network access (deselect with '-m not integration')",
]
```

**Step 3: Run unit tests (should skip integration)**

Run: `cd pipeline && uv run pytest -v -m "not integration"`
Expected: All unit tests PASS, integration tests skipped

**Step 4: Run integration test (optional, requires network)**

Run: `cd pipeline && uv run pytest tests/test_integration.py -v -m integration`
Expected: Downloads "Me at the zoo" (19s), converts to mono 16kHz, detects no intro

**Step 5: Commit**

```bash
git add pipeline/tests/test_integration.py pipeline/pyproject.toml
git commit -m "test(pipeline): add integration test — end-to-end download + preprocess with real YouTube video"
```

---

## Task 10: Diarization API Route + Segment Storage

**Files:**
- Create: `pipeline/api/diarization.py`
- Create: `pipeline/tests/test_diarization_api.py`

**Step 1: Write the failing test**

```python
# pipeline/tests/test_diarization_api.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pipeline.db import Base, get_db
from pipeline.models import Channel, Episode, Segment


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
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_diarization_api.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement diarization API + storage**

```python
# pipeline/api/diarization.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.models import Episode, Segment, Benchmark
from pipeline.core.diarizer_pyannote import DiarizedTranscript

router = APIRouter(prefix="/api/episodes/{episode_id}/diarization", tags=["diarization"])


def store_diarization_result(
    db: Session,
    episode_id: int,
    transcript: DiarizedTranscript,
    intro_end_at: float = 0.0,
) -> list[Segment]:
    """Store diarization segments in the database."""
    # Clear existing segments for this episode
    db.query(Segment).filter(Segment.episode_id == episode_id).delete()

    segments = []
    for seg in transcript.segments:
        tag = "intro" if seg.start < intro_end_at else "content"
        db_seg = Segment(
            episode_id=episode_id,
            start_time=seg.start,
            end_time=seg.end,
            text=seg.text,
            speaker=seg.speaker,
            tag=tag,
        )
        db.add(db_seg)
        segments.append(db_seg)

    db.commit()
    return segments


class SegmentResponse(BaseModel):
    id: int
    start_time: float
    end_time: float
    text: str
    speaker: str | None
    tag: str

    model_config = {"from_attributes": True}


@router.get("/segments", response_model=list[SegmentResponse])
def get_segments(episode_id: int, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(404, "Episode not found")
    return db.query(Segment).filter(Segment.episode_id == episode_id).order_by(Segment.start_time).all()


class UpdateSpeakerRequest(BaseModel):
    speaker: str


@router.patch("/segments/{segment_id}", response_model=SegmentResponse)
def update_segment_speaker(
    episode_id: int,
    segment_id: int,
    body: UpdateSpeakerRequest,
    db: Session = Depends(get_db),
):
    segment = db.query(Segment).filter(
        Segment.id == segment_id, Segment.episode_id == episode_id
    ).first()
    if not segment:
        raise HTTPException(404, "Segment not found")
    segment.speaker = body.speaker
    db.commit()
    db.refresh(segment)
    return segment
```

**Step 4: Register router in main.py**

Add to `pipeline/main.py`:
```python
from pipeline.api.diarization import router as diarization_router
# ... after other includes
app.include_router(diarization_router)
```

**Step 5: Run tests to verify they pass**

Run: `cd pipeline && uv run pytest tests/test_diarization_api.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add pipeline/api/diarization.py pipeline/tests/test_diarization_api.py pipeline/main.py
git commit -m "feat(pipeline): add diarization API — segment storage, retrieval, and speaker editing"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Project scaffolding (pyproject.toml, FastAPI, config, Makefile) | Server health check |
| 2 | SQLAlchemy models (7 tables) | 5 model creation tests |
| 3 | YouTube downloader (yt-dlp) | 4 unit tests (mocked) |
| 4 | Audio preprocessor (ffmpeg + intro detection) | 3 tests with synthetic audio |
| 5 | PyAnnote diarizer (merge logic) | 2 unit tests |
| 6 | whisper-diarization wrapper (output parser) | 2 unit tests |
| 7 | Pipeline worker (job orchestration) | 2 unit tests |
| 8 | FastAPI routes (channels, episodes, jobs) | 5 API tests |
| 9 | Integration test (real YouTube download) | 2 integration tests |
| 10 | Diarization API (segment storage + editing) | 1 storage test |

**Total: 10 tasks, ~26 tests, ~15 files to create**

After Phase 1, you will have:
- A working FastAPI server with SQLite
- YouTube audio download via yt-dlp
- Audio preprocessing with intro detection
- Two diarization approaches ready to benchmark
- REST API for managing channels, episodes, jobs, and diarization segments
- All the infrastructure needed for Phase 2 (dashboard) to connect to
