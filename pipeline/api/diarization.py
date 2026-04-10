from fastapi import APIRouter, Depends, HTTPException, Query
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
    diarizer: str = "pyannote",
) -> list[Segment]:
    """Store diarization segments in the database, scoped by diarizer."""
    db.query(Segment).filter(
        Segment.episode_id == episode_id,
        Segment.diarizer == diarizer,
    ).delete()

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
            diarizer=diarizer,
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
    diarizer: str

    model_config = {"from_attributes": True}


class BenchmarkResponse(BaseModel):
    id: int
    diarizer: str
    duration_s: float | None
    wer: float | None
    der: float | None
    notes: str | None

    model_config = {"from_attributes": True}


@router.get("/segments", response_model=list[SegmentResponse])
def get_segments(
    episode_id: int,
    diarizer: str | None = Query(None),
    db: Session = Depends(get_db),
):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(404, "Episode not found")
    query = db.query(Segment).filter(Segment.episode_id == episode_id)
    if diarizer:
        query = query.filter(Segment.diarizer == diarizer)
    return query.order_by(Segment.start_time).all()


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


def get_benchmarks_for_episode(db: Session, episode_id: int) -> list[Benchmark]:
    return db.query(Benchmark).filter(
        Benchmark.episode_id == episode_id
    ).order_by(Benchmark.created_at).all()


@router.get("/benchmarks", response_model=list[BenchmarkResponse])
def get_benchmarks(episode_id: int, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(404, "Episode not found")
    return get_benchmarks_for_episode(db, episode_id)
