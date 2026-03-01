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
def create_channel(payload: ChannelCreate, db: Session = Depends(get_db)):
    existing = db.query(Channel).filter(Channel.slug == payload.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Channel with slug '{payload.slug}' already exists")
    channel = Channel(
        name=payload.name,
        slug=payload.slug,
        youtube_id=payload.youtube_id,
        intro_skip=payload.intro_skip,
    )
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
        raise HTTPException(status_code=404, detail=f"Channel '{slug}' not found")
    return channel
