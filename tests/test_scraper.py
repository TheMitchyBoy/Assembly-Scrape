"""Lightweight tests that do not require OpenAI credentials."""

from __future__ import annotations

import unittest

from bot.city_council_scraper import CityCouncilScraper
from bot.config import settings
from bot.models import (
    SOURCE_CITY_COUNCIL,
    SOURCE_KGB_ASSEMBLY,
    MeetingDocument,
    meeting_year,
)
from bot.pipeline import MeetingMinutesBot
from bot.scraper import WebLinkScraper, parse_meeting_date
from bot.text_extractor import TextExtractor


class ScraperTests(unittest.TestCase):
    def test_parse_meeting_date_from_name(self) -> None:
        self.assertEqual(parse_meeting_date("2026-01-12 SP"), "2026-01-12")
        self.assertEqual(parse_meeting_date("Minutes", "1/12/2026"), "1/12/2026")

    def test_discover_kgb_documents(self) -> None:
        scraper = WebLinkScraper()
        documents = scraper.discover_meeting_documents()
        self.assertGreaterEqual(len(documents), 1)
        first = documents[0]
        self.assertEqual(first.source, SOURCE_KGB_ASSEMBLY)
        self.assertGreater(first.entry_id, 0)
        self.assertGreater(first.page_count, 0)

    def test_discover_city_council_documents(self) -> None:
        scraper = CityCouncilScraper()
        documents = scraper.discover_meeting_documents()
        self.assertGreaterEqual(len(documents), 1)
        first = documents[0]
        self.assertEqual(first.source, SOURCE_CITY_COUNCIL)
        self.assertTrue(first.compiled_file_id or first.minutes_url)
        year = meeting_year(first)
        self.assertIsNotNone(year)
        self.assertGreaterEqual(year, settings.min_year)

    def test_extract_kgb_first_page_text(self) -> None:
        scraper = WebLinkScraper()
        extractor = TextExtractor(weblink_scraper=scraper)
        documents = scraper.discover_meeting_documents()
        sample = documents[0]
        text, method = extractor.extract_document_text(sample)
        self.assertGreater(len(text), 100)
        self.assertIn("KETCHIKAN", text.upper())
        self.assertIn(method, {"laserfiche_ocr", "pdf"})

    def test_meeting_year_filter(self) -> None:
        bot = MeetingMinutesBot()
        documents = bot.discover_all_documents()
        self.assertGreater(len(documents), 0)
        for doc in documents:
            year = meeting_year(doc)
            self.assertIsNotNone(year)
            self.assertGreaterEqual(year, settings.min_year)

    def test_discover_agenda_page_respects_min_year(self) -> None:
        scraper = CityCouncilScraper()
        documents = scraper._discover_agenda_page_pdfs()
        if settings.min_year > 2015:
            self.assertEqual(len(documents), 0)
        else:
            self.assertGreater(len(documents), 0)

    def test_extract_agenda_page_pdf_text(self) -> None:
        scraper = CityCouncilScraper()
        extractor = TextExtractor(city_scraper=scraper)
        sample = MeetingDocument(
            source=SOURCE_CITY_COUNCIL,
            entry_id=2_000_001_897,
            name="June 18, 2015",
            meeting_date="June 18, 2015",
            minutes_url="https://evogov.s3.amazonaws.com/media/16/media/1897.pdf",
            pdf_kind="minutes",
        )
        text, method = extractor.extract_document_text(sample)
        self.assertEqual(method, "city_council_pdf")
        self.assertGreater(len(text), 500)
        self.assertIn("COUNCIL", text.upper())


if __name__ == "__main__":
    unittest.main()
