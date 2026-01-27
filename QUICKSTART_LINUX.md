# Быстрый старт на Linux

## 1. Клонирование и установка

```bash
# Клонируем репозиторий
git clone https://github.com/denis-ershov/nightwatcher.git
cd nightwatcher

# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```bash
nano .env
```

Добавьте необходимые переменные (см. пример в `.env.example` или README.md):

```env
DATABASE_URL=postgresql://user:password@host:port/dbname
ADMIN_PASSWORD=your_password
SESSION_SECRET=your_secret_key
TMDB_API_KEY=your_tmdb_key
PROWLARR_URL=http://your-prowlarr:9696
PROWLARR_API_KEY=your_prowlarr_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 3. Запуск

### Вариант A: Простой запуск (для тестирования)

```bash
# Делаем скрипт исполняемым
chmod +x start.sh

# Запускаем
./start.sh
```

Или напрямую:
```bash
python run.py
```

### Вариант B: Запуск в фоновом режиме (для production)

```bash
# Делаем скрипт исполняемым
chmod +x start_background.sh

# Запуск
./start_background.sh start

# Проверка статуса
./start_background.sh status

# Остановка
./start_background.sh stop

# Перезапуск
./start_background.sh restart
```

### Вариант C: Через systemd (рекомендуется для production)

**Автоматическая установка:**
```bash
# Делаем скрипт исполняемым
chmod +x install_service.sh

# Устанавливаем service (требует sudo)
sudo bash install_service.sh

# Запускаем
sudo systemctl start nightwatcher

# Проверка статуса
sudo systemctl status nightwatcher
```

**Ручная установка:**
```bash
# Копируем сервисный файл
sudo cp systemd-nightwatcher.service /etc/systemd/system/nightwatcher.service

# Пути уже настроены для /home/nightwatcher/
# Если нужно изменить пользователя, отредактируйте файл:
sudo nano /etc/systemd/system/nightwatcher.service

# Включаем автозапуск
sudo systemctl daemon-reload
sudo systemctl enable nightwatcher
sudo systemctl start nightwatcher

# Проверка статуса
sudo systemctl status nightwatcher

# Просмотр логов
sudo journalctl -u nightwatcher -f
```

## 4. Проверка работы

После запуска откройте в браузере:
- **API сервер (локально):** http://localhost:8000
- **API сервер (извне):** http://<SERVER_IP>:8000 (где <SERVER_IP> - IP адрес вашего сервера)
- **Watcher:** работает в фоне, проверяет релизы каждые 30 минут

### Настройка Firewall (если нужно)

Если сервер недоступен извне, откройте порт 8000:

```bash
# UFW (Ubuntu)
sudo ufw allow 8000/tcp

# firewalld (CentOS/RHEL)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload

# iptables (универсальный)
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
```

## 5. Остановка

### Если запущено через start.sh:
Нажмите `Ctrl+C`

### Если запущено в фоне:
```bash
./start_background.sh stop
```

### Если запущено через systemd:
```bash
sudo systemctl stop nightwatcher
```

## Устранение проблем

### Порт 8000 занят
```bash
# Найдите процесс
sudo lsof -i :8000
# Или
sudo netstat -tulpn | grep 8000

# Остановите процесс или измените порт в run.py
```

### Ошибки подключения к БД
- Проверьте `DATABASE_URL` в `.env`
- Убедитесь, что PostgreSQL доступен
- Проверьте firewall правила

### Ошибки импорта модулей
```bash
# Убедитесь, что виртуальное окружение активировано
source venv/bin/activate

# Переустановите зависимости
pip install -r requirements.txt
```

## Логи

- **Простой запуск:** логи выводятся в консоль
- **Фоновый режим:** логи в `nightwatcher.log`
- **Systemd:** логи через `journalctl -u nightwatcher`
