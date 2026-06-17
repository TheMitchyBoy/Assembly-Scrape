"""Extract text from borough OCR pages and city council PDF minutes."""

from __future__ import annotations

import logging
import re

import fitz
import requests
from bs4 import BeautifulSoup

from bot.city_council_scraper import CityCouncilScraper
from bot.models import SOURCE_CITY_COUNCIL, MeetingDocument
from bot.scraper import WebLinkScraper

logger = logging.getLogger(__name__)


class TextExtractor:
    """Pull text from Laserfiche OCR pages or downloaded PDF minutes."""

    def __init__(
        self,
        weblink_scraper: WebLinkScraper | None = None,
        city_scraper: CityCouncilScraper | None = None,
    ) -> None:
        self.weblink_scraper = weblink_scraper or WebLinkScraper()
        self.city_scraper = city_scraper or CityCouncilScraper()

    def extract_document_text(self, document: MeetingDocument) -> tuple[str, str]:
        if document.source == SOURCE_CITY_COUNCIL:
            pdf_bytes = self.city_scraper.download_minutes_pdf(document)
            text = self.extract_from_pdf_bytes(pdf_bytes)
            return text, "city_council_pdf"

        text, method = self.extract_with_pdf_fallback(document.entry_id, document.page_count)
        return text, method

    def extract_weblink_text(self, entry_id: int, page_count: int) -> str:
        pages: list[str] = []
        for page_num in range(1, page_count + 1):
            page_text = self._get_page_text(entry_id, page_num)
            if page_text:
                pages.append(page_text.strip())
        return "\n\n".join(pages).strip()

    def _get_page_text(self, document_id: int, page_num: int) -> str:
        payload = {
            "repoName": self.weblink_scraper.repo_name,
            "documentId": document_id,
            "pageNum": page_num,
            "showAnn": False,
            "searchUuid": None,
        }
        response = self.weblink_scraper.session.post(
            self.weblink_scraper._service_url("DocumentService.aspx/GetTextHtmlForPage"),
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        raw_text = (data.get("data") or {}).get("text", "")
        return self._clean_ocr_text(raw_text)

    @staticmethod
    def _clean_ocr_text(raw_text: str) -> str:
        if not raw_text:
            return ""
        if "<" in raw_text and ">" in raw_text:
            soup = BeautifulSoup(raw_text, "html.parser")
            text = soup.get_text("\n")
        else:
            text = raw_text
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def extract_from_pdf_bytes(self, pdf_bytes: bytes) -> str:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text("text").strip() for page in document]
        document.close()
        return "\n\n".join(page for page in pages if page).strip()

    def try_download_pdf(self, entry_id: int) -> bytes | None:
        export_url = f"{self.weblink_scraper.base_url}/Export.aspx"
        params = {
            "id": entry_id,
            "dbid": 0,
            "repo": self.weblink_scraper.repo_name,
            "format": "pdf",
        }
        try:
            response = self.weblink_scraper.session.get(export_url, params=params, timeout=120)
            content_type = response.headers.get("Content-Type", "")
            if response.ok and "pdf" in content_type.lower():
                return response.content
        except requests.RequestException as exc:
            logger.debug("PDF download failed for entry %s: %s", entry_id, exc)
        return None

    def extract_with_pdf_fallback(self, entry_id: int, page_count: int) -> tuple[str, str]:
        ocr_text = self.extract_weblink_text(entry_id, page_count)
        if len(ocr_text) >= 200:
            return ocr_text, "laserfiche_ocr"

        pdf_bytes = self.try_download_pdf(entry_id)
        if pdf_bytes:
            pdf_text = self.extract_from_pdf_bytes(pdf_bytes)
            if len(pdf_text) > len(ocr_text):
                return pdf_text, "pdf"

        return ocr_text, "laserfiche_ocr"
