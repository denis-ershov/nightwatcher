#!/bin/bash

# Скрипт запуска NightWatcher в фоновом режиме на Linux
# Использование: ./start_background.sh [start|stop|status|restart]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/nightwatcher.pid"
LOG_FILE="$SCRIPT_DIR/nightwatcher.log"

cd "$SCRIPT_DIR"

function start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "⚠️  NightWatcher уже запущен (PID: $PID)"
            return 1
        else
            rm -f "$PID_FILE"
        fi
    fi

    echo "🚀 Запуск NightWatcher в фоновом режиме..."
    
    if [ ! -d "venv" ]; then
        echo "❌ Виртуальное окружение не найдено!"
        exit 1
    fi

    source venv/bin/activate
    
    if [ ! -f ".env" ]; then
        echo "❌ Файл .env не найден!"
        exit 1
    fi

    nohup python run.py > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    
    sleep 2
    
    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "✅ NightWatcher запущен (PID: $(cat "$PID_FILE"))"
        echo "📋 Логи: $LOG_FILE"
    else
        echo "❌ Ошибка запуска. Проверьте логи: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

function stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "⚠️  NightWatcher не запущен"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "⚠️  Процесс не найден. Удаляю PID файл..."
        rm -f "$PID_FILE"
        return 1
    fi

    echo "🛑 Остановка NightWatcher (PID: $PID)..."
    kill "$PID"
    
    # Ждем завершения
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "⚠️  Принудительное завершение..."
        kill -9 "$PID"
    fi
    
    rm -f "$PID_FILE"
    echo "✅ NightWatcher остановлен"
}

function status() {
    if [ ! -f "$PID_FILE" ]; then
        echo "❌ NightWatcher не запущен"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ NightWatcher запущен (PID: $PID)"
        echo "📋 Логи: $LOG_FILE"
        return 0
    else
        echo "❌ Процесс не найден (PID файл устарел)"
        rm -f "$PID_FILE"
        return 1
    fi
}

function restart() {
    stop
    sleep 2
    start
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    restart)
        restart
        ;;
    *)
        echo "Использование: $0 {start|stop|status|restart}"
        exit 1
        ;;
esac
