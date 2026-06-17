"""AI-powered editorial summarization using OpenAI."""

from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from bot.config import settings
from bot.prompts import EDITORIAL_SYSTEM_PROMPT, SUMMARY_USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or settings.openai_api_key
        if not key:
            raise ValueError(
                "OPENAI_API_KEY is required. Set it in your environment or .env file."
            )
        self.client = OpenAI(api_key=key)
        self.model = model or settings.openai_model

    def summarize_meeting(
        self,
        *,
        governing_body: str,
        title: str,
        meeting_date: str | None,
        raw_text: str,
        document_kind: str = "minutes",
    ) -> dict[str, str | list[str]]:
        """Return editorial analysis separating newsworthy content from routine procedure."""
        clipped_text = raw_text[:120_000]
        source_note = (
            "approved meeting minutes"
            if document_kind == "minutes"
            else "meeting agenda packet (meeting may not have occurred yet or minutes are unavailable)"
        )
        user_prompt = SUMMARY_USER_PROMPT_TEMPLATE.format(
            governing_body=governing_body,
            title=title,
            meeting_date=meeting_date or "Unknown",
            source_note=source_note,
            raw_text=clipped_text,
        )

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": EDITORIAL_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Model returned non-JSON summary; using fallback parsing")
            parsed = {
                "lede": content[:200],
                "short_summary": content[:500],
                "newsworthy": [],
                "key_decisions": [],
                "budget_finance": [],
                "community_impact": [],
                "notable_quotes_or_testimony": [],
                "excluded_routine": [],
                "next_steps": [],
            }

        return {
            "lede": str(parsed.get("lede", "")).strip(),
            "short_summary": str(parsed.get("short_summary", "")).strip(),
            "newsworthy": _as_string_list(parsed.get("newsworthy")),
            "key_decisions": _as_string_list(parsed.get("key_decisions")),
            "budget_finance": _as_string_list(parsed.get("budget_finance")),
            "community_impact": _as_string_list(parsed.get("community_impact")),
            "notable_quotes_or_testimony": _as_string_list(
                parsed.get("notable_quotes_or_testimony")
            ),
            "excluded_routine": _as_string_list(parsed.get("excluded_routine")),
            "next_steps": _as_string_list(parsed.get("next_steps")),
        }


def _as_string_list(value: object) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def truncate_for_log(text: str, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."
