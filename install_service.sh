#!/usr/bin/env bash

set -e

SERVICE_NAME="nightwatcher"
SERVICE_FILE="systemd-nightwatcher.service"
PROJECT_DIR="/home/nightwatcher"
SYSTEMD_DIR="/etc/systemd/system"

echo "============================================================"
echo "🌙 Установка systemd service для NightWatcher"
echo "============================================================"
echo ""

if [ "$EUID" -ne 0 ]; then 
    echo "❌ Этот скрипт должен быть запущен с правами root (sudo)"
    exit 1
fi

if [ ! -f "$SERVICE_FILE" ]; then
    echo "❌ Файл $SERVICE_FILE не найден!"
    exit 1
fi

if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Директория проекта $PROJECT_DIR не найдена!"
    exit 1
fi

if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "⚠️  Виртуальное окружение не найдено"
    exit 1
fi

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚠️  Файл .env не найден"
    exit 1
fi

echo "📋 Копирование service файла..."
cp "$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_NAME.service"

echo "🔄 Перезагрузка systemd daemon..."
systemctl daemon-reload

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
echo ""