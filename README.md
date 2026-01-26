# NightWatcher

Приложение для мониторинга торрентов через Prowlarr API. Отслеживает новые релизы для фильмов и сериалов из IMDb watchlist и отправляет уведомления в Telegram.

## Архитектура

- **FastAPI** - веб-интерфейс для управления watchlist
- **PostgreSQL** - база данных (удаленная)
- **Prowlarr** - агрегатор торрент-трекеров (удаленный)
- **Telegram Bot** - уведомления о новых релизах

## Требования

- Python 3.8+
- Доступ к удаленной PostgreSQL базе данных
- Доступ к удаленному Prowlarr API
- Telegram Bot Token и Chat ID

## Установка и запуск

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка окружения

Файл `.env` уже настроен и содержит:
- `DATABASE_URL` - подключение к удаленной PostgreSQL
- `PROWLARR_URL` - URL удаленного Prowlarr
- `PROWLARR_API_KEY` - API ключ Prowlarr
- `TELEGRAM_BOT_TOKEN` - токен Telegram бота
- `TELEGRAM_CHAT_ID` - ID чата для уведомлений

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
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000

# Или для доступа из сети (с других устройств)
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

**Важно:** В браузере используйте `http://localhost:8000` или `http://127.0.0.1:8000`, а не `http://0.0.0.0:8000`!

Сервер будет доступен по адресу: `http://localhost:8000`

Веб-интерфейс позволяет:
- Просматривать список отслеживаемых фильмов/сериалов
- Добавлять новые элементы по IMDb ID

### 5. Запуск watcher (мониторинг новых релизов)

Watcher можно запустить несколькими способами:

#### Вариант A: Однократный запуск

```bash
python -c "from app.watcher import run; run()"
```

#### Вариант B: Периодический запуск через cron (Linux/Mac)

Добавьте в crontab:
```bash
# Запуск каждые 30 минут
*/30 * * * * cd /path/to/nightwatcher && /path/to/python -c "from app.watcher import run; run()"
```

#### Вариант C: Периодический запуск через Task Scheduler (Windows)

1. Откройте Task Scheduler
2. Создайте новую задачу
3. Установите триггер (например, каждые 30 минут)
4. В действии укажите:
   - Программа: `python`
   - Аргументы: `-c "from app.watcher import run; run()"`
   - Рабочая папка: `E:\DEV\Project\nightwatcher`

#### Вариант D: Запуск через отдельный Python скрипт с циклом

Создайте файл `run_watcher.py`:

```python
import time
from app.watcher import run

if __name__ == "__main__":
    while True:
        try:
            run()
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(1800)  # 30 минут
```

Запуск:
```bash
python run_watcher.py
```

## Структура проекта

```
nightwatcher/
├── app/
│   ├── api.py              # FastAPI приложение (веб-интерфейс)
│   ├── config.py           # Загрузка конфигурации из .env
│   ├── db.py               # Подключение к БД
│   ├── watcher.py          # Логика мониторинга релизов
│   ├── prowlarr_client.py  # Клиент для Prowlarr API
│   ├── notifier.py         # Отправка уведомлений в Telegram
│   └── templates/
│       └── index.html      # Веб-интерфейс
├── migrations/
│   └── init.sql            # SQL миграции (создание таблиц)
├── .env                    # Конфигурация (уже настроен)
├── requirements.txt        # Python зависимости
└── README.md              # Этот файл
```

## Проверка подключений

### Проверка подключения к БД

```bash
python -c "from app.db import engine; print('DB OK' if engine.connect() else 'DB FAIL')"
```

### Проверка подключения к Prowlarr

```bash
python -c "from app.prowlarr_client import search_by_imdb; print('Prowlarr OK' if search_by_imdb('tt0111161') else 'Prowlarr FAIL')"
```

### Проверка Telegram бота

```bash
python -c "from app.notifier import send_message; send_message('Test message')"
```

## API Endpoints

- `GET /` - Главная страница со списком watchlist
- `POST /add` - Добавить новый элемент в watchlist
  - Параметры: `imdb_id` (обязательно), `title` (опционально), `type` (movie/tv)

## Примечания

- База данных и Prowlarr уже настроены как удаленные сервисы
- Watcher должен запускаться периодически для проверки новых релизов
- При обнаружении нового релиза отправляется уведомление в Telegram
- Дубликаты релизов автоматически игнорируются (UNIQUE constraint)
