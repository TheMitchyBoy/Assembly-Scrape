"""CLI entry point for the meeting minutes bot."""

from __future__ import annotations

import argparse
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from bot.config import settings
from bot.database import BlogPost, ProcessedDocument, get_session, init_db
from bot.pipeline import MeetingMinutesBot
from bot.scraper import WebLinkScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("meeting_minutes_bot")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape KGB Assembly meeting minutes, summarize with AI, and save blog posts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the scraper pipeline once")
    run_parser.add_argument("--force", action="store_true", help="Reprocess documents that already have blog posts")
    run_parser.add_argument("--limit", type=int, default=None, help="Process only the first N documents")

    subparsers.add_parser("list", help="List discovered meeting documents from WebLink")

    subparsers.add_parser("status", help="Show database processing status")

    schedule_parser = subparsers.add_parser("schedule", help="Run the bot on an interval")
    schedule_parser.add_argument(
        "--hours",
        type=int,
        default=settings.scrape_interval_hours,
        help="Hours between scheduled runs",
    )
    schedule_parser.add_argument("--limit", type=int, default=None, help="Process only the first N documents per run")

    return parser


def cmd_run(force: bool, limit: int | None) -> int:
    bot = MeetingMinutesBot()
    stats = bot.run(force=force, limit=limit)
    logger.info(
        "Run complete: discovered=%s processed=%s skipped=%s failed=%s blog_posts_created=%s",
        stats["discovered"],
        stats["processed"],
        stats["skipped"],
        stats["failed"],
        stats["blog_posts_created"],
    )
    return 0 if stats["failed"] == 0 else 1


def cmd_list() -> int:
    scraper = WebLinkScraper()
    documents = scraper.discover_meeting_documents()
    print(f"Found {len(documents)} meeting documents under folder {settings.weblink_folder_id}:")
    for doc in documents:
        print(
            f"  - {doc.name} (id={doc.entry_id}, pages={doc.page_count}, date={doc.meeting_date or 'n/a'})"
        )
    return 0


def cmd_status() -> int:
    init_db()
    session = get_session()
    try:
        docs = session.query(ProcessedDocument).count()
        completed = session.query(ProcessedDocument).filter_by(status="completed").count()
        failed = session.query(ProcessedDocument).filter_by(status="failed").count()
        posts = session.query(BlogPost).count()
        published = session.query(BlogPost).filter_by(published=True).count()
        print(f"Processed documents: {completed}/{docs} completed, {failed} failed")
        print(f"Blog posts: {published}/{posts} published")
        recent = session.query(BlogPost).order_by(BlogPost.created_at.desc()).limit(5).all()
        if recent:
            print("\nRecent posts:")
            for post in recent:
                print(f"  - {post.title} ({post.slug})")
    finally:
        session.close()
    return 0


def cmd_schedule(hours: int, limit: int | None) -> int:
    scheduler = BlockingScheduler()

    def job() -> None:
        logger.info("Starting scheduled meeting minutes run")
        cmd_run(force=False, limit=limit)

    scheduler.add_job(job, IntervalTrigger(hours=hours), id="meeting_minutes_scrape", max_instances=1)
    logger.info("Scheduler started; running every %s hour(s). Press Ctrl+C to stop.", hours)
    job()
    scheduler.start()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return cmd_run(force=args.force, limit=args.limit)
    if args.command == "list":
        return cmd_list()
    if args.command == "status":
        return cmd_status()
    if args.command == "schedule":
        return cmd_schedule(hours=args.hours, limit=args.limit)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
