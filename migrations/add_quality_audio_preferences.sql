-- Миграция для добавления полей предпочтений качества и озвучки
ALTER TABLE imdb_watchlist ADD COLUMN IF NOT EXISTS preferred_quality TEXT;
ALTER TABLE imdb_watchlist ADD COLUMN IF NOT EXISTS preferred_audio TEXT;

-- Комментарии для документации
COMMENT ON COLUMN imdb_watchlist.preferred_quality IS 'Предпочтительное качество видео (например: 1080p, 2160p, UHD, 4K, 720p)';
COMMENT ON COLUMN imdb_watchlist.preferred_audio IS 'Предпочтительная озвучка (например: русская, русский, dub, озвучка, оригинал)';
