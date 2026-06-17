"""Shared data models for meeting documents."""

from __future__ import annotations

import re
from dataclasses import dataclass

SOURCE_KGB_ASSEMBLY = "kgb_assembly"
SOURCE_CITY_COUNCIL = "city_council"


@dataclass
class MeetingDocument:
    source: str
    entry_id: int
    name: str
    page_count: int = 0
    meeting_date: str | None = None
    meeting_type: str | None = None
    body: str | None = None
    source_path: str | None = None
    parent_folder_id: int | None = None
    minutes_url: str | None = None
    compiled_file_id: int | None = None

    @property
    def governing_body(self) -> str:
        if self.source == SOURCE_CITY_COUNCIL:
            return "Ketchikan City Council"
        return "Ketchikan Gateway Borough Assembly"

    @property
    def source_key(self) -> str:
        return f"{self.source}:{self.entry_id}"


def parse_meeting_date(name: str, metadata_date: str | None = None) -> str | None:
    if metadata_date:
        return metadata_date
    match = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if match:
        return match.group(1)
    match = re.search(r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", name)
    return match.group(1) if match else None
