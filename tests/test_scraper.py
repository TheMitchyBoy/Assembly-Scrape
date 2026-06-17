"""Lightweight tests that do not require OpenAI credentials."""

from __future__ import annotations

import unittest

from bot.scraper import WebLinkScraper, parse_meeting_date
from bot.text_extractor import TextExtractor


class ScraperTests(unittest.TestCase):
    def test_parse_meeting_date_from_name(self) -> None:
        self.assertEqual(parse_meeting_date("2026-01-12 SP"), "2026-01-12")
        self.assertEqual(parse_meeting_date("Minutes", "1/12/2026"), "1/12/2026")

    def test_discover_documents(self) -> None:
        scraper = WebLinkScraper()
        documents = scraper.discover_meeting_documents()
        self.assertGreaterEqual(len(documents), 1)
        first = documents[0]
        self.assertGreater(first.entry_id, 0)
        self.assertGreater(first.page_count, 0)

    def test_extract_first_page_text(self) -> None:
        scraper = WebLinkScraper()
        extractor = TextExtractor(scraper)
        documents = scraper.discover_meeting_documents()
        sample = documents[0]
        text = extractor.extract_document_text(sample.entry_id, min(sample.page_count, 1))
        self.assertGreater(len(text), 100)
        self.assertIn("KETCHIKAN", text.upper())


if __name__ == "__main__":
    unittest.main()
