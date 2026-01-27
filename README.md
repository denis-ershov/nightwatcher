# NightWatcher

Приложение для мониторинга торрентов через Prowlarr API. Отслеживает новые релизы для фильмов и сериалов из IMDb watchlist и отправляет уведомления в Telegram с magnet-ссылками.

## Архитектура

- **FastAPI** - асинхронный веб-интерфейс для управления watchlist
- **PostgreSQL** - база данных (удаленная, через asyncpg)
- **Prowlarr** - агрегатор торрент-трекеров (удаленный)
- **Telegram Bot (aiogram 3.24.0)** - асинхронные уведомления о новых релизах с magnet-ссылками
- **TVMaze/TMDB APIs** - получение метаданных фильмов и сериалов

## Особенности

- ✅ **Асинхронная архитектура** - оптимизирована для производительности и предотвращения утечек памяти
- ✅ **Поиск по оригинальному названию** - улучшает поиск торрентов на английском языке
- ✅ **Поддержка сезонов** - отслеживание конкретных сезонов сериалов (например, "Stranger Things 4 сезон")
- ✅ **Magnet-ссылки** - автоматическое добавление magnet-ссылок в уведомления Telegram
- ✅ **Параллельная обработка** - одновременная проверка нескольких элементов watchlist
- ✅ **Расширенные метаданные** - поддержка актеров, режиссеров, бюджетов и других полей

## Требования

- Python 3.8+
- Доступ к удаленной PostgreSQL базе данных
- Доступ к удаленному Prowlarr API
- Telegram Bot Token и Chat ID
- TMDB API Key (для метаданных фильмов)

## Установка и запуск

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка окружения

Файл `.env` уже настроен и содержит:
- `DATABASE_URL` - подключение к удаленной PostgreSQL (формат: `postgresql://user:password@host:port/dbname`)
- `PROWLARR_URL` - URL удаленного Prowlarr (например, `http://prowlarr.example.com:9696`)
- `PROWLARR_API_KEY` - API ключ Prowlarr
- `TELEGRAM_BOT_TOKEN` - токен Telegram бота (получить у @BotFather)
- `TELEGRAM_CHAT_ID` - ID чата для уведомлений (числовой ID или username для групп)
- `TMDB_API_KEY` - API ключ TMDB (для метаданных фильмов, получить на https://www.themoviedb.org/settings/api)
- `ADMIN_PASSWORD` - пароль для доступа к веб-интерфейсу
- `SESSION_SECRET` - секретный ключ для сессий (любая случайная строка)

**Важно:** Для получения `TELEGRAM_CHAT_ID`:
1. Напишите боту в Telegram (если это личный чат) или добавьте бота в группу
2. Откройте: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Найдите `"chat":{"id":...}` - это ваш Chat ID (может быть отрицательным для групп)

### 3. Инициализация базы данных

Убедитесь, что таблицы созданы в удаленной БД. Если нужно, выполните миграции:

```bash
# Подключитесь к удаленной БД и выполните:
psql -h 79.137.184.79 -U postgres -d nightwatcher -f migrations/init.sql
```

Или вручную выполните SQL из `migrations/init.sql` в вашей БД.

### 4. Запуск веб-сервера (FastAPI)

```bash
# Для локального доступа (только с этого компьютера)
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000 --workers 1

# Или для доступа из сети (с других устройств)
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000 --workers 1
```

**Важно:** В браузере используйте `http://localhost:8000` или `http://127.0.0.1:8000`, а не `http://0.0.0.0:8000`!

Сервер будет доступен по адресу: `http://localhost:8000`

Веб-интерфейс позволяет:
- Просматривать список отслеживаемых фильмов/сериалов с оригинальными названиями
- Добавлять новые элементы по IMDb ID (можно указать сезон: `tt4574334 Stranger Things 4 сезон`)
- Редактировать элементы (включая указание целевого сезона для сериалов)
- Включать/выключать отслеживание элементов
- Обновлять метаданные из внешних API
- Просматривать найденные релизы с информацией о последнем обновлении
- Запускать ручной поиск релизов

### 5. Запуск watcher (мониторинг новых релизов)

Watcher работает асинхронно и оптимизирован для параллельной обработки. Можно запустить несколькими способами:

#### Вариант A: Однократный запуск

```bash
python -c "import asyncio; from app.watcher import run_search; asyncio.run(run_search())"
```

#### Вариант B: Периодический запуск через cron (Linux/Mac)

Добавьте в crontab:
```bash
# Запуск каждые 30 минут
*/30 * * * * cd /path/to/nightwatcher && /path/to/python -c "import asyncio; from app.watcher import run_search; asyncio.run(run_search())"
```

#### Вариант C: Периодический запуск через Task Scheduler (Windows)

1. Откройте Task Scheduler
2. Создайте новую задачу
3. Установите триггер (например, каждые 30 минут)
4. В действии укажите:
   - Программа: `python`
   - Аргументы: `run_watcher.py`
   - Рабочая папка: `E:\DEV\Project\nightwatcher`

#### Вариант D: Запуск через встроенный скрипт (рекомендуется)

Используйте готовый скрипт `run_watcher.py`, который включает правильное управление ресурсами:

```bash
python run_watcher.py
```

Скрипт автоматически:
- Запускает проверку каждые 30 минут
- Корректно закрывает все соединения при остановке (Ctrl+C)
- Обрабатывает ошибки без остановки работы

## Структура проекта

```
nightwatcher/
├── app/
│   ├── api.py              # FastAPI приложение (асинхронный веб-интерфейс)
│   ├── config.py           # Загрузка конфигурации из .env
│   ├── db.py               # Асинхронное подключение к БД (asyncpg)
│   ├── watcher.py          # Асинхронная логика мониторинга релизов
│   ├── prowlarr_client.py  # Асинхронный клиент для Prowlarr API (httpx)
│   ├── notifier.py         # Асинхронная отправка уведомлений в Telegram (aiogram)
│   ├── metadata.py         # Получение метаданных из TVMaze/TMDB APIs
│   ├── season_parser.py    # Парсинг номеров сезонов из названий
│   └── templates/
│       ├── index.html      # Веб-интерфейс watchlist
│       └── login.html      # Страница входа
├── migrations/
│   ├── init.sql            # SQL миграции (создание таблиц)
│   └── add_target_season.sql  # Миграция для добавления поля target_season
├── run_watcher.py          # Скрипт для периодического запуска watcher
├── run_server.bat          # Batch скрипт для запуска сервера (Windows)
├── check_connections.py    # Скрипт для проверки подключений
├── .env                    # Конфигурация (уже настроен)
├── requirements.txt        # Python зависимости
└── README.md               # Этот файл
```

## Проверка подключений

Используйте готовый скрипт для проверки всех подключений:

```bash
python check_connections.py
```

Или проверьте вручную:

### Проверка подключения к БД

```bash
python -c "import asyncio; from app.db import AsyncSessionLocal; from sqlalchemy import text; async def check(): async with AsyncSessionLocal() as db: await db.execute(text('SELECT 1')); print('DB OK'); asyncio.run(check())"
```

### Проверка подключения к Prowlarr

```bash
python -c "import asyncio; from app.prowlarr_client import search_by_query; async def check(): result = await search_by_query('test'); print('Prowlarr OK' if result is not None else 'Prowlarr FAIL'); asyncio.run(check())"
```

### Проверка Telegram бота

```bash
python -c "import asyncio; from app.notifier import send_message; asyncio.run(send_message('Test message'))"
```

**Примечание:** Убедитесь, что `TELEGRAM_CHAT_ID` настроен правильно. Если получаете ошибку "chat not found", проверьте:
1. Бот запущен и добавлен в чат/группу
2. Вы отправили боту хотя бы одно сообщение (для личных чатов)
3. Chat ID указан правильно (может быть отрицательным для групп)

## API Endpoints

### Веб-интерфейс

- `GET /` - Главная страница со списком watchlist (требует аутентификации)
- `GET /login` - Страница входа
- `POST /login` - Аутентификация (параметр: `password`)
- `GET /logout` - Выход из системы

### Управление watchlist

- `POST /add` - Добавить новый элемент в watchlist
  - Параметры: `imdb_id` (обязательно, можно указать сезон: `tt4574334 Stranger Things 4 сезон`)
  - Автоматически получает метаданные из TVMaze/TMDB
  - Извлекает номер сезона из входной строки, если указан

- `POST /delete/{item_id}` - Удалить элемент из watchlist
- `POST /toggle/{item_id}` - Включить/выключить отслеживание элемента
- `POST /edit/{item_id}` - Редактировать элемент
  - Параметры: `title`, `type` (movie/tv), `target_season` (опционально, для сериалов)
- `POST /refresh/{item_id}` - Обновить метаданные элемента из внешних API
- `POST /search` - Запустить ручной поиск релизов для всех включенных элементов

### API для получения данных

- `GET /api/releases/{imdb_id}` - Получить список релизов для IMDb ID
  - Возвращает JSON с информацией о релизах, включая `last_update`

## База данных

### Таблица `imdb_watchlist`

Основные поля:
- `imdb_id` - уникальный идентификатор IMDb
- `title` - локализованное название
- `original_title` - оригинальное название (используется для поиска)
- `type` - тип (movie/tv)
- `target_season` - целевой сезон для отслеживания (для сериалов)
- `enabled` - включено ли отслеживание
- `created_at`, `updated_at` - временные метки

Расширенные метаданные:
- `poster_url`, `year`, `genre`, `plot`, `rating`, `runtime`
- `total_seasons`, `total_episodes`
- `status`, `network`, `country`, `language`, `official_site`
- `actors`, `director`, `creators`, `tagline`
- `budget`, `revenue`, `last_air_date`, `in_production`

### Таблица `torrent_releases`

- `imdb_id` - связь с watchlist
- `title` - название релиза
- `info_hash` - хеш торрента (UNIQUE вместе с imdb_id)
- `quality`, `size`, `seeders`, `tracker`
- `created_at`, `last_update` - временные метки

## Особенности работы

### Поиск торрентов

- Используется **оригинальное название** (`original_title`) для поиска, так как большинство раздач на английском
- Для сериалов автоматически добавляется номер сезона в формате `SXX` (например, `Stranger Things S04`)
- Если сезон указан в названии при добавлении, он извлекается и сохраняется в `target_season`

### Уведомления Telegram

- Отправляются асинхронно через aiogram 3.24.0
- Включают постер фильма/сериала (если доступен)
- Содержат информацию о релизе: название, качество, размер, сидеры, трекер
- **Включают кликабельную magnet-ссылку** для быстрого скачивания
- Ссылка на IMDb страницу

### Производительность

- Параллельная обработка до 5 элементов watchlist одновременно
- Асинхронные операции для всех внешних запросов (БД, Prowlarr, Telegram, метаданные)
- Connection pooling для БД и HTTP клиентов
- Корректное закрытие всех соединений при остановке

## Примечания

- База данных и Prowlarr настроены как удаленные сервисы
- Watcher должен запускаться периодически для проверки новых релизов (рекомендуется каждые 30 минут)
- При обнаружении нового релиза отправляется уведомление в Telegram с magnet-ссылкой
- Дубликаты релизов автоматически игнорируются (UNIQUE constraint по `imdb_id` + `info_hash`)
- Существующие релизы обновляют поле `last_update` при повторном обнаружении
- Для сериалов можно указать конкретный сезон для отслеживания при добавлении или редактировании
