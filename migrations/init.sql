CREATE TABLE IF NOT EXISTS imdb_watchlist (
    -- Основные поля
    id SERIAL PRIMARY KEY,
    imdb_id TEXT UNIQUE NOT NULL,
    title TEXT,
    original_title TEXT,
    type TEXT CHECK (type IN ('movie', 'tv')),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    
    -- Метаданные (основные)
    poster_url TEXT,
    year TEXT,
    genre TEXT,
    plot TEXT,
    rating TEXT,
    runtime TEXT,
    
    -- Отслеживание
    last_checked TIMESTAMP,
    total_seasons INTEGER,
    total_episodes INTEGER,
    last_notified_season INTEGER DEFAULT 0,
    last_notified_episode INTEGER DEFAULT 0,
    target_season INTEGER,  -- Конкретный сезон для отслеживания (опционально)
    preferred_quality TEXT,  -- Предпочтительное качество видео (например: 1080p, 2160p, UHD, 4K)
    preferred_audio TEXT,  -- Предпочтительная озвучка (например: русская, русский, dub, озвучка)
    
    -- Метаданные (расширенные - для сериалов)
    status TEXT,
    network TEXT,
    country TEXT,
    language TEXT,
    official_site TEXT,
    schedule TEXT,
    last_air_date TEXT,
    in_production BOOLEAN,
    
    -- Метаданные (расширенные - для фильмов/сериалов)
    actors TEXT,
    director TEXT,
    creators TEXT,
    tagline TEXT,
    original_language TEXT,
    budget TEXT,
    revenue TEXT
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
    last_update TIMESTAMP DEFAULT now(),
    UNIQUE (imdb_id, info_hash)
);
