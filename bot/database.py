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
    UniqueConstraint,
    create_engine,
    func,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from bot.config import settings
from bot.models import SOURCE_KGB_ASSEMBLY


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
    __table_args__ = (UniqueConstraint("source", "entry_id", name="uq_processed_source_entry"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False, default=SOURCE_KGB_ASSEMBLY, index=True)
    entry_id = Column(Integer, nullable=False, index=True)
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
    __table_args__ = (UniqueConstraint("source", "source_entry_id", name="uq_blog_source_entry"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False, default=SOURCE_KGB_ASSEMBLY, index=True)
    source_entry_id = Column(Integer, nullable=False, index=True)
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
    migrate_db()


def migrate_db() -> None:
    """Add multi-source columns to existing deployments."""
    inspector = inspect(engine)
    if not inspector.has_table("processed_documents"):
        return

    processed_columns = {column["name"] for column in inspector.get_columns("processed_documents")}
    blog_columns = {column["name"] for column in inspector.get_columns("blog_posts")}

    with engine.begin() as conn:
        if "source" not in processed_columns:
            conn.execute(
                text(
                    "ALTER TABLE processed_documents "
                    "ADD COLUMN source VARCHAR(64) DEFAULT 'kgb_assembly' NOT NULL"
                )
            )
        if "source" not in blog_columns:
            conn.execute(
                text(
                    "ALTER TABLE blog_posts "
                    "ADD COLUMN source VARCHAR(64) DEFAULT 'kgb_assembly' NOT NULL"
                )
            )


def get_session() -> Session:
    return SessionLocal()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
