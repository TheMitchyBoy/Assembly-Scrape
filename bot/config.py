"""Configuration for the meeting minutes bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    database_url: str
    weblink_base_url: str
    weblink_repo_name: str
    weblink_folder_id: int
    scrape_interval_hours: int
    bot_command: str
    process_limit: int | None
    min_year: int
    enable_kgb_assembly: bool
    enable_city_council: bool
    city_agenda_url: str
    city_primegov_url: str
    city_scrape_agenda_page: bool
    city_use_primegov: bool

    @classmethod
    def from_env(cls) -> Settings:
        limit_raw = os.getenv("PROCESS_LIMIT", "").strip()
        process_limit = int(limit_raw) if limit_raw else None
        min_year = int(os.getenv("MIN_YEAR", os.getenv("CITY_MIN_YEAR", "2026")))
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            database_url=os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'meeting_minutes.db'}"),
            weblink_base_url=os.getenv(
                "WEBLINK_BASE_URL",
                "https://kgb-lf-weblink.kgbak.us/WebLink",
            ).rstrip("/"),
            weblink_repo_name=os.getenv("WEBLINK_REPO_NAME", "KGBPUBLIC"),
            weblink_folder_id=int(os.getenv("WEBLINK_FOLDER_ID", "37030")),
            scrape_interval_hours=int(os.getenv("SCRAPE_INTERVAL_HOURS", "24")),
            bot_command=os.getenv("BOT_COMMAND", "run"),
            process_limit=process_limit,
            min_year=min_year,
            enable_kgb_assembly=os.getenv("ENABLE_KGB_ASSEMBLY", "true").lower() == "true",
            enable_city_council=os.getenv("ENABLE_CITY_COUNCIL", "true").lower() == "true",
            city_agenda_url=os.getenv(
                "CITY_AGENDA_URL",
                "https://www.ketchikan.gov/council-agendas-and-meetings",
            ),
            city_primegov_url=os.getenv(
                "CITY_PRIMEGOV_URL",
                "https://ketchikan.primegov.com",
            ).rstrip("/"),
            city_scrape_agenda_page=os.getenv("CITY_SCRAPE_AGENDA_PAGE", "true").lower() == "true",
            city_use_primegov=os.getenv("CITY_USE_PRIMEGOV", "true").lower() == "true",
        )


settings = Settings.from_env()
