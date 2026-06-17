"""SQLAlchemy models and database helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from bot.config import settings


def _normalize_database_url(url: str) -> str:
    """Use psycopg3 for PostgreSQL (works on Python 3.13+ in containers)."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


class Base(DeclarativeBase):
    pass


class ProcessedDocument(Base):
    __tablename__ = "processed_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    meeting_date = Column(String(64))
    page_count = Column(Integer)
    source_path = Column(Text)
    raw_text = Column(Text)
    status = Column(String(32), default="pending", nullable=False)
    error_message = Column(Text)
    scraped_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_entry_id = Column(Integer, unique=True, nullable=False, index=True)
    title = Column(String(512), nullable=False)
    slug = Column(String(512), unique=True, nullable=False, index=True)
    summary = Column(Text)
    content = Column(Text, nullable=False)
    meeting_date = Column(String(64))
    source_url = Column(Text)
    published = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


engine = create_engine(_normalize_database_url(settings.database_url), echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return SessionLocal()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
