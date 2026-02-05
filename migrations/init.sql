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
    min_releases_count INTEGER DEFAULT NULL,  -- Минимальное количество раздач для отслеживания
    check_interval INTEGER DEFAULT NULL  -- Интервал проверки в минутах (NULL = использовать значение по умолчанию)
    
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

-- Таблица истории уведомлений
CREATE TABLE IF NOT EXISTS notifications_history (
    id SERIAL PRIMARY KEY,
    imdb_id TEXT NOT NULL,
    release_title TEXT,
    notification_text TEXT,
    sent_at TIMESTAMP DEFAULT now(),
    success BOOLEAN DEFAULT TRUE
);

-- Индексы для оптимизации производительности
CREATE INDEX IF NOT EXISTS idx_watchlist_enabled ON imdb_watchlist(enabled);
CREATE INDEX IF NOT EXISTS idx_watchlist_imdb_id ON imdb_watchlist(imdb_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_type ON imdb_watchlist(type);
CREATE INDEX IF NOT EXISTS idx_watchlist_created_at ON imdb_watchlist(created_at);
CREATE INDEX IF NOT EXISTS idx_releases_imdb_created ON torrent_releases(imdb_id, created_at);
CREATE INDEX IF NOT EXISTS idx_releases_tracker ON torrent_releases(tracker);
CREATE INDEX IF NOT EXISTS idx_releases_created_at ON torrent_releases(created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_imdb ON notifications_history(imdb_id);
CREATE INDEX IF NOT EXISTS idx_notifications_sent_at ON notifications_history(sent_at);

-- Комментарии к полям
COMMENT ON COLUMN imdb_watchlist.min_releases_count IS 'Минимальное количество раздач для отслеживания (NULL = отслеживать все раздачи)';
COMMENT ON COLUMN imdb_watchlist.check_interval IS 'Интервал проверки в минутах (NULL = использовать значение по умолчанию)';
