from datetime import datetime, UTC
from sqlalchemy.orm import Session
from pipeline.models import Episode, Job


def create_ingestion_jobs(db: Session, episode_id: int) -> list[Job]:
    stages = ["download", "preprocess", "diarize"]
    jobs = []
    for stage in stages:
        job = Job(episode_id=episode_id, stage=stage, status="pending")
        db.add(job)
        jobs.append(job)
    db.commit()
    return jobs


def update_job_status(db: Session, job_id: int, status: str, progress: float | None = None, error: str | None = None) -> Job:
    job = db.query(Job).filter(Job.id == job_id).one()
    job.status = status
    if progress is not None:
        job.progress = progress
    if error is not None:
        job.error = error
    if status == "running" and job.started_at is None:
        job.started_at = datetime.now(UTC)
    if status in ("completed", "failed"):
        job.completed_at = datetime.now(UTC)
        if status == "completed":
            job.progress = 1.0
    db.commit()
    return job


def get_next_pending_job(db: Session, episode_id: int) -> Job | None:
    stage_order = ["download", "preprocess", "diarize", "extract"]
    for stage in stage_order:
        job = db.query(Job).filter(
            Job.episode_id == episode_id, Job.stage == stage, Job.status == "pending"
        ).first()
        if job:
            return job
    return None


async def run_pipeline(db: Session, episode_id: int) -> None:
    from pipeline.core.downloader import download_audio
    from pipeline.core.preprocessor import convert_to_mono_16k, detect_intro_end
    from pipeline.config import settings

    episode = db.query(Episode).filter(Episode.id == episode_id).one()

    while True:
        job = get_next_pending_job(db, episode_id)
        if job is None:
            break

        update_job_status(db, job.id, "running")
        episode.status = {"download": "downloading", "preprocess": "preprocessing", "diarize": "diarizing"}.get(job.stage, job.stage)
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
                mono_path = audio_path.with_stem(audio_path.stem + "_16k")
                convert_to_mono_16k(audio_path, mono_path)
                intro_end = detect_intro_end(mono_path)
                episode.intro_end_at = intro_end
                episode.audio_path = str(mono_path)
                db.commit()
            elif job.stage == "diarize":
                pass  # Run manually via dashboard
            update_job_status(db, job.id, "completed")
        except Exception as e:
            update_job_status(db, job.id, "failed", error=str(e))
            episode.status = "error"
            db.commit()
            break

    pending = db.query(Job).filter(Job.episode_id == episode_id, Job.status.in_(["pending", "running"])).count()
    if pending == 0:
        failed = db.query(Job).filter(Job.episode_id == episode_id, Job.status == "failed").count()
        if failed == 0:
            episode.status = "reviewing"
            db.commit()
