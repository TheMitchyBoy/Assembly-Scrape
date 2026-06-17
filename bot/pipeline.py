"""Orchestrates scraping, extraction, summarization, and persistence."""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.orm import Session

from bot.blog_generator import BlogGenerator
from bot.city_council_scraper import CityCouncilScraper
from bot.config import settings
from bot.database import BlogPost, ProcessedDocument, get_session, init_db
from bot.models import MeetingDocument, parse_meeting_date
from bot.scraper import WebLinkScraper
from bot.summarizer import Summarizer, truncate_for_log
from bot.text_extractor import TextExtractor

logger = logging.getLogger(__name__)


class MeetingMinutesBot:
    def __init__(
        self,
        kgb_scraper: WebLinkScraper | None = None,
        city_scraper: CityCouncilScraper | None = None,
        extractor: TextExtractor | None = None,
        summarizer: Summarizer | None = None,
        blog_generator: BlogGenerator | None = None,
        session: Session | None = None,
    ) -> None:
        self.kgb_scraper = kgb_scraper or WebLinkScraper()
        self.city_scraper = city_scraper or CityCouncilScraper()
        self.extractor = extractor or TextExtractor(self.kgb_scraper, self.city_scraper)
        self.summarizer = summarizer or Summarizer()
        self.blog_generator = blog_generator or BlogGenerator()
        self._session = session

    def run(self, *, force: bool = False, limit: int | None = None) -> dict[str, int]:
        init_db()
        session = self._session or get_session()
        close_session = self._session is None

        stats = {
            "discovered": 0,
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "blog_posts_created": 0,
        }

        try:
            documents = self.discover_all_documents()
            stats["discovered"] = len(documents)
            if limit is not None:
                documents = documents[:limit]

            for document in documents:
                try:
                    created = self._process_document(session, document, force=force)
                    if created is None:
                        stats["skipped"] += 1
                    else:
                        stats["processed"] += 1
                        if created:
                            stats["blog_posts_created"] += 1
                        session.commit()
                        logger.info(
                            "Saved to database: [%s] %s (entry %s)",
                            document.source,
                            document.name,
                            document.entry_id,
                        )
                except Exception as exc:
                    stats["failed"] += 1
                    logger.exception(
                        "Failed to process [%s] %s (%s): %s",
                        document.source,
                        document.name,
                        document.entry_id,
                        exc,
                    )
                    self._mark_failed(session, document, str(exc))
            session.commit()
        finally:
            if close_session:
                session.close()

        return stats

    def discover_all_documents(self) -> list[MeetingDocument]:
        documents: list[MeetingDocument] = []
        if settings.enable_kgb_assembly:
            documents.extend(self.kgb_scraper.discover_meeting_documents())
        if settings.enable_city_council:
            documents.extend(self.city_scraper.discover_meeting_documents())
        documents.sort(key=lambda doc: (doc.source, doc.meeting_date or "", doc.name))
        return documents

    def _process_document(
        self,
        session: Session,
        document: MeetingDocument,
        *,
        force: bool,
    ) -> bool | None:
        existing_post = (
            session.query(BlogPost)
            .filter_by(source=document.source, source_entry_id=document.entry_id)
            .first()
        )
        if existing_post and not force:
            logger.info(
                "Skipping already processed [%s] entry %s (%s)",
                document.source,
                document.entry_id,
                document.name,
            )
            return None

        logger.info(
            "Processing [%s] %s (entry %s, %s pages)",
            document.source,
            document.name,
            document.entry_id,
            document.page_count or "pdf",
        )
        text, method = self.extractor.extract_document_text(document)
        if len(text) < 100:
            raise RuntimeError(f"Extracted text too short ({len(text)} chars) via {method}")

        logger.info(
            "Extracted %s characters via %s for %s",
            len(text),
            method,
            truncate_for_log(document.name),
        )

        summary = self.summarizer.summarize_meeting(
            governing_body=document.governing_body,
            title=document.name,
            meeting_date=parse_meeting_date(document.name, document.meeting_date),
            raw_text=text,
        )
        source_url = self._document_view_url(document)
        post_payload = self.blog_generator.generate_post(document, summary, text, source_url)

        self._upsert_processed_document(session, document, text)
        self._upsert_blog_post(session, document, post_payload, source_url)
        return True

    def _document_view_url(self, document: MeetingDocument) -> str:
        if document.source == "city_council":
            return self.city_scraper.document_view_url(document)
        return self.kgb_scraper.document_view_url(document.entry_id)

    def _upsert_processed_document(
        self,
        session: Session,
        document: MeetingDocument,
        text: str,
    ) -> None:
        record = (
            session.query(ProcessedDocument)
            .filter_by(source=document.source, entry_id=document.entry_id)
            .first()
        )
        if record is None:
            record = ProcessedDocument(
                source=document.source,
                entry_id=document.entry_id,
                name=document.name,
            )
            session.add(record)

        record.name = document.name
        record.meeting_date = parse_meeting_date(document.name, document.meeting_date)
        record.page_count = document.page_count or None
        record.source_path = document.source_path
        record.raw_text = text
        record.status = "completed"
        record.error_message = None

    def _upsert_blog_post(
        self,
        session: Session,
        document: MeetingDocument,
        payload: dict[str, str],
        source_url: str,
    ) -> None:
        post = (
            session.query(BlogPost)
            .filter_by(source=document.source, source_entry_id=document.entry_id)
            .first()
        )
        if post is None:
            post = BlogPost(
                source=document.source,
                source_entry_id=document.entry_id,
                title=payload["title"],
                slug=payload["slug"],
                content=payload["content"],
            )
            session.add(post)

        post.title = payload["title"]
        post.slug = payload["slug"]
        post.summary = payload["summary"]
        post.content = payload["content"]
        post.meeting_date = payload.get("meeting_date") or parse_meeting_date(
            document.name, document.meeting_date
        )
        post.source_url = source_url
        post.published = True

    def _mark_failed(self, session: Session, document: MeetingDocument, error: str) -> None:
        record = (
            session.query(ProcessedDocument)
            .filter_by(source=document.source, entry_id=document.entry_id)
            .first()
        )
        if record is None:
            record = ProcessedDocument(
                source=document.source,
                entry_id=document.entry_id,
                name=document.name,
            )
            session.add(record)
        record.status = "failed"
        record.error_message = error[:4000]
        session.commit()

    def list_unprocessed(self) -> Iterable[MeetingDocument]:
        init_db()
        session = self._session or get_session()
        close_session = self._session is None
        try:
            processed_keys = {
                (row[0], row[1])
                for row in session.query(ProcessedDocument.source, ProcessedDocument.entry_id)
                .filter(ProcessedDocument.status == "completed")
                .all()
            }
            for document in self.discover_all_documents():
                if (document.source, document.entry_id) not in processed_keys:
                    yield document
        finally:
            if close_session:
                session.close()
