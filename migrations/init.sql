CREATE TABLE IF NOT EXISTS imdb_watchlist (
    id SERIAL PRIMARY KEY,
    imdb_id TEXT UNIQUE NOT NULL,
    title TEXT,
    type TEXT CHECK (type IN ('movie', 'tv')),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    poster_url TEXT,
    year TEXT,
    genre TEXT,
    plot TEXT,
    rating TEXT,
    runtime TEXT,
    last_checked TIMESTAMP,
    total_seasons INTEGER,
    last_notified_season INTEGER DEFAULT 0,
    last_notified_episode INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS torrent_releases (
    id SERIAL PRIMARY KEY,
    imdb_id TEXT NOT NULL,
    title TEXT,
    info_hash TEXT NOT NULL,
    quality TEXT,
    size BIGINT,
    seeders INT,
    tracker TEXT,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE (imdb_id, info_hash)
);
