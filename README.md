# Meeting Minutes Bot

Automatically scrapes **Ketchikan Gateway Borough Assembly** and **Ketchikan City Council** meeting minutes, extracts text, summarizes them with AI in a journalistic tone, and saves blog posts to a database.

## Features

- **Borough Assembly** — Laserfiche WebLink API + OCR page text
- **City Council** — PrimeGov portal API + PDF minutes (from [current agendas](https://www.ketchikan.gov/current-agendas-and-meetings))
- Editorial AI triage that separates newsworthy decisions from routine procedure
- Journalistic markdown blog posts stored in SQLite or PostgreSQL
- One-off or scheduled automatic runs

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
| `WEBLINK_FOLDER_ID` | `37030` | Borough root folder ID (2026 minutes) |
| `ENABLE_KGB_ASSEMBLY` | `true` | Scrape borough assembly minutes |
| `ENABLE_CITY_COUNCIL` | `true` | Scrape city council minutes |
| `CITY_PRIMEGOV_URL` | `https://ketchikan.primegov.com` | PrimeGov API for current council minutes |
| `CITY_MIN_YEAR` | `2020` | Oldest council meeting year to process |
| `CITY_SCRAPE_ARCHIVE` | `false` | Also scrape archived HTML PDF tables |
| `SCRAPE_INTERVAL_HOURS` | `24` | Default schedule interval |

## Database Schema

- **processed_documents** — scraped entry metadata and raw extracted text (`source` + `entry_id`)
- **blog_posts** — AI-generated titles, slugs, summaries, and markdown content (`source` + `source_entry_id`)

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
