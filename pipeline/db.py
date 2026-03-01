from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from pipeline.config import settings

engine = create_engine(settings.db_url, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
