"""Laserfiche WebLink scraper for KGB Assembly meeting minutes."""

from __future__ import annotations

import logging
from typing import Any

import requests

from bot.config import settings
from bot.models import SOURCE_KGB_ASSEMBLY, MeetingDocument, parse_meeting_date

logger = logging.getLogger(__name__)

ENTRY_TYPE_FOLDER = 0
ENTRY_TYPE_DOCUMENT = -2

__all__ = ["MeetingDocument", "WebLinkScraper", "parse_meeting_date"]


class WebLinkScraper:
    """Client for the Laserfiche WebLink public portal API."""

    def __init__(
        self,
        base_url: str | None = None,
        repo_name: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or settings.weblink_base_url).rstrip("/")
        self.repo_name = repo_name or settings.weblink_repo_name
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; KGBMeetingMinutesBot/1.0; "
                    "+https://github.com/meeting-minutes-bot)"
                ),
                "Content-Type": "application/json; charset=UTF-8",
            }
        )
        self._ensure_session()

    def _service_url(self, endpoint: str) -> str:
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(self._service_url(endpoint), json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    def _ensure_session(self) -> None:
        """Visit the browse page so the portal sets required session cookies."""
        browse_url = (
            f"{self.base_url}/Browse.aspx"
            f"?id={settings.weblink_folder_id}&dbid=0&repo={self.repo_name}"
        )
        response = self.session.get(browse_url, timeout=60)
        response.raise_for_status()

    def list_folder_entries(
        self,
        folder_id: int,
        *,
        start: int = 0,
        end: int = 200,
    ) -> list[dict[str, Any]]:
        payload = {
            "repoName": self.repo_name,
            "folderId": folder_id,
            "getNewListing": True,
            "start": start,
            "end": end,
            "sortColumn": None,
            "sortAscending": False,
        }
        data = self._post("FolderListingService.aspx/GetFolderListing2", payload)
        folder_data = data.get("data") or {}
        if folder_data.get("failed"):
            message = folder_data.get("errMsg", "Unknown folder listing error")
            raise RuntimeError(f"Folder listing failed for {folder_id}: {message}")
        return folder_data.get("results") or []

    def get_document_info(self, entry_id: int) -> dict[str, Any]:
        payload = {"repoName": self.repo_name, "entryId": entry_id}
        data = self._post("DocumentService.aspx/GetBasicDocumentInfo", payload)
        return data.get("data") or {}

    def discover_meeting_documents(self, root_folder_id: int | None = None) -> list[MeetingDocument]:
        """Recursively discover meeting minute documents under the configured folder."""
        root_id = root_folder_id or settings.weblink_folder_id
        documents: list[MeetingDocument] = []
        self._walk_folder(root_id, documents)
        documents.sort(key=lambda doc: doc.name)
        return documents

    def _walk_folder(self, folder_id: int, documents: list[MeetingDocument]) -> None:
        entries = self.list_folder_entries(folder_id)
        for entry in entries:
            entry_id = entry["entryId"]
            entry_type = entry.get("type")
            name = entry.get("name", "")
            page_count = 0
            if entry.get("data") and len(entry["data"]) > 1:
                page_count = int(entry["data"][1] or 0)

            if entry_type == ENTRY_TYPE_FOLDER:
                self._walk_folder(entry_id, documents)
                continue

            if entry_type == ENTRY_TYPE_DOCUMENT and page_count > 0:
                metadata = self._extract_metadata(entry_id)
                documents.append(
                    MeetingDocument(
                        source=SOURCE_KGB_ASSEMBLY,
                        entry_id=entry_id,
                        name=name,
                        page_count=page_count,
                        meeting_date=metadata.get("date"),
                        meeting_type=metadata.get("meeting_type"),
                        body=metadata.get("body"),
                        source_path=metadata.get("path"),
                        parent_folder_id=folder_id,
                    )
                )

    def _extract_metadata(self, entry_id: int) -> dict[str, str | None]:
        info = self.get_document_info(entry_id)
        metadata = info.get("metadata") or {}
        fields = {item.get("name"): item.get("values", [None])[0] for item in metadata.get("fInfo", [])}
        return {
            "date": fields.get("Date"),
            "meeting_type": fields.get("Meeting Type"),
            "body": fields.get("Body"),
            "path": metadata.get("path"),
        }

    def document_view_url(self, entry_id: int) -> str:
        return (
            f"{self.base_url}/DocView.aspx"
            f"?id={entry_id}&page=1&dbid=0&repo={self.repo_name}"
        )

    def browse_url(self, folder_id: int | None = None) -> str:
        folder = folder_id or settings.weblink_folder_id
        return f"{self.base_url}/Browse.aspx?id={folder}&dbid=0&repo={self.repo_name}"


# parse_meeting_date re-exported from bot.models via __all__
