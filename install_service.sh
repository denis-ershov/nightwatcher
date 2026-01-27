#!/usr/bin/env bash

# Скрипт установки systemd service для NightWatcher
# Запустите: sudo bash install_service.sh

set -e

SERVICE_NAME="nightwatcher"
SERVICE_FILE="systemd-nightwatcher.service"
PROJECT_DIR="/home/nightwatcher"
SYSTEMD_DIR="/etc/systemd/system"

echo "============================================================"
echo "🌙 Установка systemd service для NightWatcher"
echo "============================================================"
echo ""

# Проверяем, что скрипт запущен от root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Этот скрипт должен быть запущен с правами root (sudo)"
    exit 1
fi

# Проверяем наличие файла service
if [ ! -f "$SERVICE_FILE" ]; then
    echo "❌ Файл $SERVICE_FILE не найден!"
    echo "Убедитесь, что вы находитесь в директории проекта"
    exit 1
fi

# Проверяем наличие директории проекта
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Директория проекта $PROJECT_DIR не найдена!"
    exit 1
fi

# Проверяем наличие виртуального окружения
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "⚠️  Виртуальное окружение не найдено в $PROJECT_DIR/venv"
    echo "Создайте его командой: python3 -m venv venv"
    exit 1
fi

# Проверяем наличие .env файла
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚠️  Файл .env не найден в $PROJECT_DIR"
    echo "Создайте файл .env с необходимыми переменными окружения"
    exit 1
fi

# Копируем service файл
echo "📋 Копирование service файла..."
cp "$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_NAME.service"

# Перезагружаем systemd
echo "🔄 Перезагрузка systemd daemon..."
systemctl daemon-reload

# Включаем автозапуск
echo "✅ Включение автозапуска..."
systemctl enable "$SERVICE_NAME.service"

echo ""
echo "============================================================"
echo "✅ Service установлен и настроен!"
echo "============================================================"
echo ""
echo "Управление сервисом:"
echo "  Запуск:    sudo systemctl start $SERVICE_NAME"
echo "  Остановка: sudo systemctl stop $SERVICE_NAME"
echo "  Статус:    sudo systemctl status $SERVICE_NAME"
echo "  Логи:      sudo journalctl -u $SERVICE_NAME -f"
echo "  Перезапуск: sudo systemctl restart $SERVICE_NAME"
echo ""
echo "Для запуска сейчас выполните:"
echo "  sudo systemctl start $SERVICE_NAME"
echo ""
