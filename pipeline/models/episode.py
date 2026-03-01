from datetime import UTC, datetime
from sqlalchemy import String, Text, Float, ForeignKey
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
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    channel = relationship("Channel", back_populates="episodes")
    segments = relationship("Segment", back_populates="episode")
    insights = relationship("Insight", back_populates="episode")
    jobs = relationship("Job", back_populates="episode")
    benchmarks = relationship("Benchmark", back_populates="episode")
