"""Generate journalistic blog posts from meeting summaries."""

from __future__ import annotations

import json
import logging

from openai import OpenAI
from slugify import slugify

from bot.config import settings
from bot.models import MeetingDocument, parse_meeting_date
from bot.prompts import BLOG_SYSTEM_PROMPT, BLOG_USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


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
        governing_body = document.governing_body
        user_prompt = BLOG_USER_PROMPT_TEMPLATE.format(
            governing_body=governing_body,
            meeting_name=document.name,
            meeting_date=meeting_date or "Unknown",
            meeting_type=document.meeting_type or "Regular",
            source_url=source_url,
            summary_json=json.dumps(summary, indent=2),
            raw_text=raw_text[:80_000],
        )
        system_prompt = BLOG_SYSTEM_PROMPT.format(
            governing_body=governing_body,
            source_url=source_url,
        )

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.35,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
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

        slug = self._unique_slug(post_title, document)
        return {
            "title": post_title,
            "slug": slug,
            "summary": post_summary,
            "content": post_content,
            "meeting_date": meeting_date or "",
        }

    def _build_title(self, document: MeetingDocument, meeting_date: str | None) -> str:
        label = "City Council" if document.source == "city_council" else "Borough Assembly"
        if meeting_date:
            return f"Ketchikan {label} Meeting Recap: {meeting_date}"
        return f"Ketchikan {label} Meeting Recap: {document.name}"

    def _unique_slug(self, title: str, document: MeetingDocument) -> str:
        base = slugify(title) or f"meeting-{document.entry_id}"
        return f"{document.source}-{base}-{document.entry_id}"

    def _fallback_markdown(
        self,
        document: MeetingDocument,
        summary: dict[str, str | list[str]],
        source_url: str,
        meeting_date: str | None,
    ) -> str:
        lede = str(summary.get("lede") or summary.get("short_summary", "")).strip()
        paragraphs = [lede, ""]

        if summary.get("newsworthy"):
            paragraphs.extend(["## Key developments", ""])
            paragraphs.extend(f"- {item}" for item in summary["newsworthy"])
            paragraphs.append("")

        if summary.get("key_decisions"):
            paragraphs.extend(["## Decisions", ""])
            paragraphs.extend(f"- {item}" for item in summary["key_decisions"])
            paragraphs.append("")

        if summary.get("community_impact"):
            paragraphs.extend(["## Community impact", ""])
            paragraphs.extend(f"- {item}" for item in summary["community_impact"])
            paragraphs.append("")

        if summary.get("next_steps"):
            paragraphs.extend(["## What's next", ""])
            paragraphs.extend(f"- {item}" for item in summary["next_steps"])
            paragraphs.append("")

        paragraphs.append(f"[Read the official minutes]({source_url})")
        return "\n".join(paragraphs).strip()
