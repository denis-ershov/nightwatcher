# NightWatcher

A torrent monitoring application that tracks new releases for movies and TV shows from IMDb watchlist and sends Telegram notifications.

## Overview

- **Framework**: FastAPI (Python 3.11)
- **Database**: PostgreSQL (Replit's built-in database)
- **Purpose**: Monitor torrent releases via Prowlarr API, notify via Telegram

## Project Structure

```
app/
├── api.py              # FastAPI web interface
├── config.py           # Environment configuration
├── db.py               # Database connection
├── watcher.py          # Release monitoring logic
├── prowlarr_client.py  # Prowlarr API client
├── notifier.py         # Telegram notifications
└── templates/
    └── index.html      # Web interface
migrations/
└── init.sql            # Database schema
```

## Running the Application

The app runs on port 5000 using uvicorn:
```bash
uvicorn app.api:app --host 0.0.0.0 --port 5000
```

## Environment Variables

Required secrets (configure in Secrets tab):
- `DATABASE_URL` - PostgreSQL connection string (auto-configured)
- `PROWLARR_URL` - Prowlarr API URL
- `PROWLARR_API_KEY` - Prowlarr API key
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `TELEGRAM_CHAT_ID` - Telegram chat ID for notifications

## API Endpoints

- `GET /` - Main page with watchlist
- `POST /add` - Add item to watchlist (imdb_id, title, type)

## Database Tables

- `imdb_watchlist` - Tracked movies/TV shows
- `torrent_releases` - Found torrent releases
