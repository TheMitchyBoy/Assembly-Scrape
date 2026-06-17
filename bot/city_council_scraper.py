"""Scrape Ketchikan City Council PDFs from the public agenda page and PrimeGov."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from bot.config import settings
from bot.models import SOURCE_CITY_COUNCIL, MeetingDocument

logger = logging.getLogger(__name__)

COUNCIL_COMMITTEE_KEYWORDS = (
    "city council",
    "council meeting",
    "special city council",
    "special council meeting",
)


class CityCouncilScraper:
    """Discover City Council PDFs from the agenda page and recent PrimeGov minutes."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.agenda_url = settings.city_agenda_url
        self.base_url = settings.city_primegov_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; KGBMeetingMinutesBot/1.0; "
                    "+https://github.com/meeting-minutes-bot)"
                )
            }
        )
        self._committee_ids: set[int] | None = None

    def discover_meeting_documents(self) -> list[MeetingDocument]:
        documents: list[MeetingDocument] = []
        if settings.city_scrape_agenda_page:
            agenda_docs = self._discover_agenda_page_pdfs()
            logger.info("Found %s PDFs on city agenda page", len(agenda_docs))
            documents.extend(agenda_docs)
        if settings.city_use_primegov:
            primegov_docs = self._discover_primegov_minutes()
            logger.info("Found %s PrimeGov city council minute PDFs", len(primegov_docs))
            documents.extend(primegov_docs)
        documents.sort(key=lambda doc: (doc.meeting_date or "", doc.name))
        return self._dedupe_documents(documents)

    def _discover_agenda_page_pdfs(self) -> list[MeetingDocument]:
        """Scrape Minutes and Agenda PDF links from the council agendas HTML page."""
        response = self.session.get(self.agenda_url, timeout=60)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        documents: list[MeetingDocument] = []

        for table in soup.find_all("table"):
            current_year: int | None = None
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if not cells:
                    continue

                row_text = cells[0].get_text(" ", strip=True)
                year_match = re.fullmatch(r"(20\d{2}|19\d{2})", row_text)
                if year_match:
                    current_year = int(year_match.group(1))
                    continue
                if current_year is None or current_year < settings.city_min_year:
                    continue

                links = self._extract_row_pdf_links(row)
                pdf_url = links.get("minutes") or links.get("agenda")
                if not pdf_url:
                    continue

                pdf_kind = "minutes" if links.get("minutes") else "agenda"
                meeting_label = row_text
                meeting_date = self._parse_archive_date(meeting_label, current_year)
                entry_id = self._archive_entry_id(meeting_date, pdf_url)
                name = meeting_label
                if pdf_kind == "agenda" and "agenda" not in name.lower():
                    name = f"{meeting_label} (Agenda)"

                documents.append(
                    MeetingDocument(
                        source=SOURCE_CITY_COUNCIL,
                        entry_id=entry_id,
                        name=name,
                        page_count=0,
                        meeting_date=meeting_date,
                        meeting_type=self._infer_meeting_type(meeting_label),
                        body="City Council",
                        source_path=self.agenda_url,
                        minutes_url=pdf_url,
                        pdf_kind=pdf_kind,
                    )
                )
        return documents

    @staticmethod
    def _extract_row_pdf_links(row) -> dict[str, str]:
        links: dict[str, str] = {}
        for link in row.find_all("a", href=True):
            label = link.get_text(" ", strip=True).lower()
            href = link["href"]
            if label not in {"minutes", "agenda"}:
                continue
            if ".pdf" not in href.lower() and "evogov" not in href.lower():
                continue
            if label == "n/a":
                continue
            links[label] = href
        return links

    def _discover_primegov_minutes(self) -> list[MeetingDocument]:
        documents: list[MeetingDocument] = []
        committee_ids = self._get_city_council_committee_ids()
        years = self._get_archived_years()
        for year in years:
            if year < settings.city_min_year:
                continue
            meetings = self._get_json(f"/api/v2/PublicPortal/ListArchivedMeetings?year={year}")
            if isinstance(meetings, list):
                documents.extend(self._meetings_to_documents(meetings, committee_ids))

        upcoming = self._get_json("/api/v2/PublicPortal/ListUpcomingMeetings")
        if isinstance(upcoming, list):
            documents.extend(self._meetings_to_documents(upcoming, committee_ids))
        return documents

    def _meetings_to_documents(
        self,
        meetings: list[dict[str, Any]],
        committee_ids: set[int],
    ) -> list[MeetingDocument]:
        documents: list[MeetingDocument] = []
        for meeting in meetings:
            if meeting.get("committeeId") not in committee_ids:
                continue
            minutes_doc = self._find_minutes_document(meeting.get("documentList") or [])
            if minutes_doc is None:
                continue
            meeting_id = int(meeting["id"])
            compiled_id = int(minutes_doc["id"])
            documents.append(
                MeetingDocument(
                    source=SOURCE_CITY_COUNCIL,
                    entry_id=meeting_id,
                    name=self._build_meeting_name(meeting),
                    page_count=0,
                    meeting_date=meeting.get("date"),
                    meeting_type=meeting.get("title"),
                    body="City Council",
                    source_path=self.agenda_url,
                    minutes_url=self.minutes_preview_url(compiled_id),
                    compiled_file_id=compiled_id,
                    pdf_kind="minutes",
                )
            )
        return documents

    def _get_city_council_committee_ids(self) -> set[int]:
        if self._committee_ids is not None:
            return self._committee_ids
        committees = self._get_json(
            "/api/committee/GetCommitteeesListByShowInPublicPortal?showInactive=true"
        )
        ids: set[int] = set()
        if isinstance(committees, list):
            for committee in committees:
                name = str(committee.get("name", ""))
                if self._is_city_council_committee(name):
                    ids.add(int(committee["id"]))
        self._committee_ids = ids
        logger.info("City Council committee IDs: %s", sorted(ids))
        return ids

    @staticmethod
    def _is_city_council_committee(name: str) -> bool:
        lowered = name.lower().strip()
        if any(keyword in lowered for keyword in COUNCIL_COMMITTEE_KEYWORDS):
            return True
        if lowered in {"city council", "council meeting", "special council meeting"}:
            return True
        return lowered.startswith("city council")

    @staticmethod
    def _find_minutes_document(document_list: list[dict[str, Any]]) -> dict[str, Any] | None:
        for document in document_list:
            template_name = str(document.get("templateName", "")).lower()
            if template_name == "minutes" or template_name.endswith(" minutes"):
                return document
        return None

    def _build_meeting_name(self, meeting: dict[str, Any]) -> str:
        title = str(meeting.get("title") or "City Council Meeting").strip()
        date = str(meeting.get("date") or "").strip()
        if date and date not in title:
            return f"{date} - {title}"
        return title or f"City Council Meeting {meeting.get('id')}"

    def _get_archived_years(self) -> list[int]:
        years = self._get_json("/api/v2/PublicPortal/GetArchivedMeetingYears")
        if isinstance(years, list):
            return sorted((int(year) for year in years), reverse=True)
        return [settings.city_min_year]

    def _get_json(self, path: str) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        return response.json()

    def download_minutes_pdf(self, document: MeetingDocument) -> bytes:
        if document.compiled_file_id is not None:
            return self._download_primegov_pdf(document.compiled_file_id)
        if document.minutes_url:
            return self._download_url(document.minutes_url)
        raise RuntimeError(f"No PDF download path for {document.source_key}")

    def _download_primegov_pdf(self, compiled_file_id: int) -> bytes:
        response = self.session.get(
            f"{self.base_url}/api/Meeting/getcompiledfiledownloadurl",
            params={"compiledFileId": compiled_file_id},
            timeout=60,
        )
        response.raise_for_status()
        download_url = response.json()
        if not isinstance(download_url, str):
            raise RuntimeError(f"Unexpected PrimeGov download response for file {compiled_file_id}")
        pdf_response = self.session.get(download_url, timeout=120)
        pdf_response.raise_for_status()
        content_type = pdf_response.headers.get("Content-Type", "")
        content = pdf_response.content
        if content[:4] != b"%PDF" and "pdf" not in content_type.lower():
            raise RuntimeError(f"Expected PDF for compiled file {compiled_file_id}")
        return content

    def _download_url(self, url: str) -> bytes:
        full_url = url if url.startswith("http") else urljoin(self.agenda_url, url)
        response = self.session.get(full_url, timeout=120)
        response.raise_for_status()
        content = response.content
        if content[:4] != b"%PDF":
            raise RuntimeError(f"Download did not return a PDF: {full_url}")
        return content

    def minutes_preview_url(self, compiled_file_id: int) -> str:
        return (
            f"{self.base_url}/Portal/MeetingPreview"
            f"?compiledMeetingDocumentFileId={compiled_file_id}"
        )

    def document_view_url(self, document: MeetingDocument) -> str:
        if document.minutes_url and document.minutes_url.startswith("http"):
            return document.minutes_url
        if document.compiled_file_id is not None:
            return self.minutes_preview_url(document.compiled_file_id)
        return self.agenda_url

    @staticmethod
    def _parse_archive_date(label: str, year: int) -> str:
        cleaned = label.replace("\xa0", " ")
        match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+(\d{1,2})(?:,?\s*(\d{4}))?",
            cleaned,
            re.I,
        )
        if match:
            month = match.group(1)
            day = match.group(2)
            parsed_year = match.group(3) or str(year)
            return f"{month} {day}, {parsed_year}"
        return f"{label} ({year})"

    @staticmethod
    def _infer_meeting_type(label: str) -> str | None:
        lowered = label.lower()
        if "special" in lowered:
            return "Special"
        if "budget" in lowered:
            return "Budget"
        if "work session" in lowered:
            return "Work Session"
        return "Regular"

    @staticmethod
    def _archive_entry_id(meeting_date: str, pdf_url: str) -> int:
        file_id = re.search(r"/media/(\d+)\.pdf", pdf_url, re.I)
        if file_id:
            return 2_000_000_000 + int(file_id.group(1))
        digest = abs(hash(f"{meeting_date}|{pdf_url}")) % 1_000_000_000
        return 2_000_000_000 + digest

    @staticmethod
    def _dedupe_documents(documents: list[MeetingDocument]) -> list[MeetingDocument]:
        seen: set[str] = set()
        unique: list[MeetingDocument] = []
        for document in documents:
            key = f"{document.source}:{document.minutes_url or document.source_key}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(document)
        return unique
