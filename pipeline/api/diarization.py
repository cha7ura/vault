from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.models import Episode, Segment, Benchmark
from pipeline.core.diarizer_whisper import DiarizedTranscript

router = APIRouter(prefix="/api/episodes/{episode_id}/diarization", tags=["diarization"])


def store_diarization_result(
    db: Session,
    episode_id: int,
    transcript: DiarizedTranscript,
    intro_end_at: float = 0.0,
    diarizer: str = "whisper-diarization",
) -> list[Segment]:
    """Store diarization segments in the database, scoped by diarizer."""
    db.query(Segment).filter(
        Segment.episode_id == episode_id,
        Segment.diarizer == diarizer,
    ).delete()

    segments = []
    for seg in transcript.segments:
        tag = "intro" if seg.start < intro_end_at else "content"
        words_json = None
        if seg.words:
            words_json = [
                {"text": w.text, "start": w.start, "end": w.end, "score": w.score}
                for w in seg.words
            ]
        db_seg = Segment(
            episode_id=episode_id,
            start_time=seg.start,
            end_time=seg.end,
            text=seg.text,
            speaker=seg.speaker,
            tag=tag,
            words=words_json,
            diarizer=diarizer,
        )
        db.add(db_seg)
        segments.append(db_seg)

    db.commit()
    return segments


class WordTimingResponse(BaseModel):
    text: str
    start: float
    end: float
    score: float | None = None


class SegmentResponse(BaseModel):
    id: int
    start_time: float
    end_time: float
    text: str
    speaker: str | None
    tag: str
    words: list[WordTimingResponse] | None = None
    youtube_text: str | None = None
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


class YouTubeSubsResponse(BaseModel):
    updated_segments: int
    message: str


@router.post("/youtube-subs", response_model=YouTubeSubsResponse)
def fetch_youtube_subs(
    episode_id: int,
    db: Session = Depends(get_db),
):
    """Download YouTube auto-captions, align with whisper words, store youtube_text."""
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(404, "Episode not found")

    from pipeline.core.downloader import download_youtube_subs
    from pipeline.core.youtube_subs import parse_json3
    from pipeline.core.alignment import align_words, build_segment_youtube_text

    # Download subs to a temp-ish location next to data
    subs_dir = Path(__file__).resolve().parents[1].parent / "data" / "subs"
    sub_path = download_youtube_subs(episode.youtube_id, subs_dir)
    if not sub_path:
        raise HTTPException(404, "No auto-captions available for this video")

    # Parse YouTube JSON3
    yt_words = parse_json3(sub_path)
    yt_word_dicts = [
        {"text": w.text, "start": w.start, "end": w.end}
        for w in yt_words
    ]

    # Get segments with word data
    segments = (
        db.query(Segment)
        .filter(
            Segment.episode_id == episode_id,
            Segment.diarizer == "whisper-diarization",
        )
        .order_by(Segment.start_time)
        .all()
    )

    # Collect all whisper words across segments for alignment
    all_whisper_words: list[dict] = []
    for seg in segments:
        if seg.words:
            all_whisper_words.extend(seg.words)

    if not all_whisper_words:
        raise HTTPException(
            400,
            "No word-level data on segments. Run backfill_word_data first.",
        )

    # Align
    aligned = align_words(all_whisper_words, yt_word_dicts)

    # Update each segment's youtube_text
    updated = 0
    for seg in segments:
        yt_text = build_segment_youtube_text(
            seg.words or [], aligned, seg.start_time, seg.end_time
        )
        if yt_text:
            seg.youtube_text = yt_text
            updated += 1

    db.commit()
    return YouTubeSubsResponse(
        updated_segments=updated,
        message=f"Aligned {len(yt_words)} YouTube words with {len(all_whisper_words)} whisper words",
    )
