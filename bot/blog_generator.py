"""Generate blog posts from meeting summaries."""

from __future__ import annotations

import json
import logging
import re

from openai import OpenAI
from slugify import slugify

from bot.config import settings
from bot.scraper import MeetingDocument, parse_meeting_date

logger = logging.getLogger(__name__)

BLOG_SYSTEM_PROMPT = """You write accessible blog posts about local government for Ketchikan Gateway Borough residents.
Write in clear, engaging prose. Use markdown headings and bullet lists where helpful.
Be accurate and cite only what appears in the provided summary and minutes.
Include a compelling introduction and a concise conclusion."""


class BlogGenerator:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or settings.openai_api_key
        if not key:
            raise ValueError(
                "OPENAI_API_KEY is required. Set it in your environment or .env file."
            )
        self.client = OpenAI(api_key=key)
        self.model = model or settings.openai_model

    def generate_post(
        self,
        document: MeetingDocument,
        summary: dict[str, str | list[str]],
        raw_text: str,
        source_url: str,
    ) -> dict[str, str]:
        meeting_date = parse_meeting_date(document.name, document.meeting_date)
        title = self._build_title(document, meeting_date)
        user_prompt = f"""Create a public-facing blog post in markdown from this borough assembly meeting.

Meeting name: {document.name}
Meeting date: {meeting_date or "Unknown"}
Meeting type: {document.meeting_type or "Regular"}
Source URL: {source_url}

Structured summary JSON:
{json.dumps(summary, indent=2)}

Excerpt from minutes (for additional detail only):
{raw_text[:25_000]}

Return JSON with:
- "title": blog post headline
- "summary": 1-2 paragraph meta summary
- "content": full markdown blog post body (include ## headings, bullet lists, and a Source link at the end)
"""

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.4,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": BLOG_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Model returned non-JSON blog payload; using fallback")
            parsed = {
                "title": title,
                "summary": str(summary.get("short_summary", "")),
                "content": self._fallback_markdown(document, summary, source_url, meeting_date),
            }

        post_title = str(parsed.get("title") or title).strip()
        post_summary = str(parsed.get("summary") or summary.get("short_summary", "")).strip()
        post_content = str(parsed.get("content") or "").strip()
        if not post_content:
            post_content = self._fallback_markdown(document, summary, source_url, meeting_date)

        slug = self._unique_slug(post_title, document.entry_id)
        return {
            "title": post_title,
            "slug": slug,
            "summary": post_summary,
            "content": post_content,
            "meeting_date": meeting_date or "",
        }

    def _build_title(self, document: MeetingDocument, meeting_date: str | None) -> str:
        if meeting_date:
            return f"Ketchikan Gateway Borough Assembly Meeting – {meeting_date}"
        return f"Ketchikan Gateway Borough Assembly Meeting – {document.name}"

    def _unique_slug(self, title: str, entry_id: int) -> str:
        base = slugify(title) or f"meeting-{entry_id}"
        return f"{base}-{entry_id}"

    def _fallback_markdown(
        self,
        document: MeetingDocument,
        summary: dict[str, str | list[str]],
        source_url: str,
        meeting_date: str | None,
    ) -> str:
        sections = [
            f"# {self._build_title(document, meeting_date)}",
            "",
            str(summary.get("short_summary", "")),
            "",
            "## Key Decisions",
            *_bullet_lines(summary.get("key_decisions")),
            "",
            "## Budget & Finance",
            *_bullet_lines(summary.get("budget_finance")),
            "",
            "## Public Comment",
            *_bullet_lines(summary.get("public_comment")),
            "",
            "## Next Steps",
            *_bullet_lines(summary.get("next_steps")),
            "",
            f"[View official minutes]({source_url})",
        ]
        return "\n".join(sections).strip()


def _bullet_lines(items: object) -> list[str]:
    if not items:
        return ["- _None noted._"]
    if isinstance(items, list):
        return [f"- {item}" for item in items if str(item).strip()]
    return [f"- {items}"]
