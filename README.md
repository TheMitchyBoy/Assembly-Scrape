# Meeting Minutes Bot

Automatically scrapes Ketchikan Gateway Borough Assembly meeting minutes from the [Laserfiche WebLink public portal](https://kgb-lf-weblink.kgbak.us/WebLink/Browse.aspx?id=37030&dbid=0&repo=KGBPUBLIC), extracts text from scanned minute documents, summarizes them with AI, and saves blog posts to a database.

## Features

- Discovers meeting minute documents via the Laserfiche WebLink API
- Extracts OCR text from each scanned page (with optional PDF parsing fallback)
- Uses OpenAI to triage newsworthy content vs. routine procedure, then writes journalistic blog posts
- Stores raw text, processing status, and published posts in SQLite (or any SQLAlchemy-supported database)
- Supports one-off runs or scheduled automatic scraping

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
```

### List available meetings

```bash
python -m bot.main list
```

### Process new meetings

```bash
python -m bot.main run
```

### Run on a schedule (every 24 hours by default)

```bash
python -m bot.main schedule --hours 24
```

### Check database status

```bash
python -m bot.main status
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | _(required)_ | OpenAI API key for summarization |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for summaries and blog posts |
| `DATABASE_URL` | `sqlite:///./data/meeting_minutes.db` | SQLAlchemy database URL |
| `WEBLINK_BASE_URL` | KGB public WebLink URL | Laserfiche portal base URL |
| `WEBLINK_REPO_NAME` | `KGBPUBLIC` | Repository name |
| `WEBLINK_FOLDER_ID` | `37030` | Root folder ID (2026 minutes) |
| `SCRAPE_INTERVAL_HOURS` | `24` | Default schedule interval |

## Database Schema

- **processed_documents** — scraped entry metadata and raw extracted text
- **blog_posts** — AI-generated titles, slugs, summaries, and markdown content

## Commands

```bash
python -m bot.main run [--force] [--limit N]
python -m bot.main list
python -m bot.main status
python -m bot.main schedule [--hours N] [--limit N]
```

Use `--force` to regenerate blog posts for meetings that were already processed.

## Deployment (Railway / containers)

Set these environment variables on your host:

| Variable | Required | Notes |
|----------|----------|-------|
| `OPENAI_API_KEY` | Yes | Without this the bot exits immediately |
| `DATABASE_URL` | Yes (production) | Railway/Postgres URL, e.g. `postgresql://...` |
| `BOT_COMMAND` | No | Defaults to `run` on startup |
| `PROCESS_LIMIT` | No | Process only N meetings per run (testing) |

The container start command should be:

```bash
python -m bot.main run
```

Or rely on the default (`BOT_COMMAND=run`) with:

```bash
python -m bot.main
```

For recurring scrapes, use `BOT_COMMAND=schedule` or:

```bash
python -m bot.main schedule --hours 24
```

After deploy, check logs for `Saved to database` and run `python -m bot.main status`.

## How It Works

1. **Scrape** — Authenticates with the WebLink portal (session cookies) and lists documents under the configured folder.
2. **Extract** — Pulls OCR text from each page via `DocumentService.aspx/GetTextHtmlForPage`.
3. **Summarize** — Sends the full scanned text to OpenAI for editorial triage (votes, budget, community impact vs. routine procedure).
4. **Publish** — Generates a journalistic markdown article and upserts it into the database.

## Notes

- Meeting documents on this portal are scanned images stored in Laserfiche; text is extracted from the portal's OCR layer rather than native PDF files.
- Respect the borough's terms of use and rate limits when running scheduled jobs.
- Set `DATABASE_URL` to PostgreSQL for production deployments, e.g. `postgresql://user:pass@localhost/meeting_minutes`.

## License

Apache 2.0 — see [LICENSE](LICENSE).
