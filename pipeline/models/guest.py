from datetime import UTC, datetime
from sqlalchemy import String, Text, Table, Column, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pipeline.db import Base

episode_guests = Table(
    "episode_guests",
    Base.metadata,
    Column("episode_id", Integer, ForeignKey("episodes.id"), primary_key=True),
    Column("guest_id", Integer, ForeignKey("guests.id"), primary_key=True),
)


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    links: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    episodes = relationship("Episode", secondary=episode_guests, backref="guests")
