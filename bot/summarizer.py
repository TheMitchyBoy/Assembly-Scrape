"""AI-powered summarization using OpenAI."""

from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from bot.config import settings

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPT = """You are an expert municipal government analyst covering the Ketchikan Gateway Borough, Alaska.
Summarize assembly meeting minutes clearly and accurately for residents.
Focus on decisions, votes, ordinances, resolutions, budget items, and notable public comments.
Use neutral, factual language. Do not invent details that are not in the source text."""


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
        title: str,
        meeting_date: str | None,
        raw_text: str,
    ) -> dict[str, str | list[str]]:
        """Return structured summary fields for a meeting."""
        clipped_text = raw_text[:120_000]
        user_prompt = f"""Analyze these Ketchikan Gateway Borough Assembly meeting minutes.

Meeting title: {title}
Meeting date: {meeting_date or "Unknown"}

Return JSON with these keys:
- "short_summary": 2-3 sentence overview for social previews
- "key_decisions": array of bullet strings for major votes and actions
- "budget_finance": array of bullet strings (empty array if none)
- "public_comment": array of bullet strings (empty array if none)
- "next_steps": array of bullet strings for follow-up items

Minutes text:
{clipped_text}
"""

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Model returned non-JSON summary; using fallback parsing")
            parsed = {
                "short_summary": content[:500],
                "key_decisions": [],
                "budget_finance": [],
                "public_comment": [],
                "next_steps": [],
            }

        return {
            "short_summary": str(parsed.get("short_summary", "")).strip(),
            "key_decisions": _as_string_list(parsed.get("key_decisions")),
            "budget_finance": _as_string_list(parsed.get("budget_finance")),
            "public_comment": _as_string_list(parsed.get("public_comment")),
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
