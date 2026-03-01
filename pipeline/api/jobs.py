from fastapi import APIRouter, Depends, Query
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
    error: str | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[JobResponse])
def list_jobs(
    status: str | None = Query(None),
    episode_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if status is not None:
        query = query.filter(Job.status == status)
    if episode_id is not None:
        query = query.filter(Job.episode_id == episode_id)
    return query.order_by(Job.id.desc()).all()
