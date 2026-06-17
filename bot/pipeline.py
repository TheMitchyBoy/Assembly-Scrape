"""Orchestrates scraping, extraction, summarization, and persistence."""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.orm import Session

from bot.blog_generator import BlogGenerator
from bot.database import BlogPost, ProcessedDocument, get_session, init_db
from bot.scraper import MeetingDocument, WebLinkScraper, parse_meeting_date
from bot.summarizer import Summarizer, truncate_for_log
from bot.text_extractor import TextExtractor

logger = logging.getLogger(__name__)


class MeetingMinutesBot:
    def __init__(
        self,
        scraper: WebLinkScraper | None = None,
        extractor: TextExtractor | None = None,
        summarizer: Summarizer | None = None,
        blog_generator: BlogGenerator | None = None,
        session: Session | None = None,
    ) -> None:
        self.scraper = scraper or WebLinkScraper()
        self.extractor = extractor or TextExtractor(self.scraper)
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
            documents = self.scraper.discover_meeting_documents()
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
                except Exception as exc:
                    stats["failed"] += 1
                    logger.exception("Failed to process %s (%s): %s", document.name, document.entry_id, exc)
                    self._mark_failed(session, document, str(exc))
            session.commit()
        finally:
            if close_session:
                session.close()

        return stats

    def _process_document(
        self,
        session: Session,
        document: MeetingDocument,
        *,
        force: bool,
    ) -> bool | None:
        existing_post = session.query(BlogPost).filter_by(source_entry_id=document.entry_id).first()
        if existing_post and not force:
            logger.info("Skipping already processed entry %s (%s)", document.entry_id, document.name)
            return None

        logger.info("Processing %s (entry %s, %s pages)", document.name, document.entry_id, document.page_count)
        text, method = self.extractor.extract_with_pdf_fallback(document.entry_id, document.page_count)
        if len(text) < 100:
            raise RuntimeError(f"Extracted text too short ({len(text)} chars) via {method}")

        logger.info(
            "Extracted %s characters via %s for %s",
            len(text),
            method,
            truncate_for_log(document.name),
        )

        summary = self.summarizer.summarize_meeting(
            title=document.name,
            meeting_date=parse_meeting_date(document.name, document.meeting_date),
            raw_text=text,
        )
        source_url = self.scraper.document_view_url(document.entry_id)
        post_payload = self.blog_generator.generate_post(document, summary, text, source_url)

        self._upsert_processed_document(session, document, text)
        self._upsert_blog_post(session, document, post_payload, source_url)
        return True

    def _upsert_processed_document(
        self,
        session: Session,
        document: MeetingDocument,
        text: str,
    ) -> None:
        record = session.query(ProcessedDocument).filter_by(entry_id=document.entry_id).first()
        if record is None:
            record = ProcessedDocument(entry_id=document.entry_id, name=document.name)
            session.add(record)

        record.name = document.name
        record.meeting_date = parse_meeting_date(document.name, document.meeting_date)
        record.page_count = document.page_count
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
        post = session.query(BlogPost).filter_by(source_entry_id=document.entry_id).first()
        if post is None:
            post = BlogPost(source_entry_id=document.entry_id, title=payload["title"], slug=payload["slug"], content=payload["content"])
            session.add(post)

        post.title = payload["title"]
        post.slug = payload["slug"]
        post.summary = payload["summary"]
        post.content = payload["content"]
        post.meeting_date = payload.get("meeting_date") or parse_meeting_date(document.name, document.meeting_date)
        post.source_url = source_url
        post.published = True

    def _mark_failed(self, session: Session, document: MeetingDocument, error: str) -> None:
        record = session.query(ProcessedDocument).filter_by(entry_id=document.entry_id).first()
        if record is None:
            record = ProcessedDocument(entry_id=document.entry_id, name=document.name)
            session.add(record)
        record.status = "failed"
        record.error_message = error[:4000]
        session.commit()

    def list_unprocessed(self) -> Iterable[MeetingDocument]:
        init_db()
        session = self._session or get_session()
        close_session = self._session is None
        try:
            processed_ids = {
                row[0]
                for row in session.query(ProcessedDocument.entry_id)
                .filter(ProcessedDocument.status == "completed")
                .all()
            }
            for document in self.scraper.discover_meeting_documents():
                if document.entry_id not in processed_ids:
                    yield document
        finally:
            if close_session:
                session.close()
