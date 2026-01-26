# NightWatcher

A torrent monitoring application that tracks new releases for movies and TV shows from IMDb watchlist and sends Telegram notifications with rich formatting.

## Overview

- **Framework**: FastAPI (Python 3.11)
- **Database**: PostgreSQL (Replit's built-in database)
- **Purpose**: Monitor torrent releases via Prowlarr API, notify via Telegram with images

## Features

- User authentication with password protection
- Beautiful responsive dark theme UI
- Add movies/series by IMDb ID with automatic metadata fetching
- Edit, delete, enable/disable tracking for items
- Manual search trigger from web interface
- OMDB integration for movie info, posters, ratings
- Enhanced Telegram notifications with images and detailed info
- Track last check time for each item

## Project Structure

```
app/
├── api.py              # FastAPI web interface with all routes
├── config.py           # Environment configuration
├── db.py               # Database connection
├── omdb.py             # OMDB API integration for movie info
├── watcher.py          # Release monitoring logic
├── prowlarr_client.py  # Prowlarr API client
├── notifier.py         # Enhanced Telegram notifications
├── static/             # Static assets
└── templates/
    ├── index.html      # Main dashboard
    └── login.html      # Login page
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
- `ADMIN_PASSWORD` - Password for web interface login (default: admin123)
- `SESSION_SECRET` - Session encryption key (auto-configured)
- `OMDB_API_KEY` - OMDB API key for movie metadata (get from omdbapi.com)
- `PROWLARR_URL` - Prowlarr API URL
- `PROWLARR_API_KEY` - Prowlarr API key
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `TELEGRAM_CHAT_ID` - Telegram chat ID for notifications

## API Endpoints

- `GET /` - Main dashboard (requires auth)
- `GET /login` - Login page
- `POST /login` - Authenticate
- `GET /logout` - Logout
- `POST /add` - Add item by IMDb ID
- `POST /delete/{id}` - Delete item
- `POST /toggle/{id}` - Toggle tracking
- `POST /edit/{id}` - Edit item
- `POST /refresh/{id}` - Refresh metadata from OMDB
- `POST /search` - Manual search trigger
- `GET /api/releases/{imdb_id}` - Get releases for item

## Database Tables

- `imdb_watchlist` - Tracked movies/TV shows with metadata
- `torrent_releases` - Found torrent releases
