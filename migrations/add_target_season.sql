-- Миграция для добавления поля target_season (целевой сезон для отслеживания)
ALTER TABLE imdb_watchlist ADD COLUMN IF NOT EXISTS target_season INTEGER;
