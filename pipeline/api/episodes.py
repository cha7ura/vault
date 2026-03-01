from fastapi import APIRouter, Depends, HTTPException
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
    duration: float | None
    intro_end_at: float | None

    model_config = {"from_attributes": True}


@router.post("/ingest", status_code=201, response_model=EpisodeResponse)
def ingest_episode(payload: IngestRequest, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.slug == payload.channel_slug).first()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{payload.channel_slug}' not found")

    video_id = extract_video_id(payload.youtube_url)

    existing = db.query(Episode).filter(Episode.youtube_id == video_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Episode '{video_id}' already exists")

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
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
    return episode
