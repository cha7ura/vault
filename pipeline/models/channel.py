from datetime import UTC, datetime
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
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    episodes = relationship("Episode", back_populates="channel")
