from datetime import UTC, datetime
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
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    episode = relationship("Episode", back_populates="benchmarks")
