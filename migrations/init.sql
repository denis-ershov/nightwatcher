CREATE TABLE IF NOT EXISTS imdb_watchlist (
    id SERIAL PRIMARY KEY,
    imdb_id TEXT UNIQUE NOT NULL,
    title TEXT,
    type TEXT CHECK (type IN ('movie', 'tv')),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now()
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
