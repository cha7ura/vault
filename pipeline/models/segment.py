from datetime import UTC, datetime
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
    diarizer: Mapped[str] = mapped_column(String(100), default="pyannote")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    episode = relationship("Episode", back_populates="segments")
