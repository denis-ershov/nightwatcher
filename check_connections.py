"""
Скрипт для проверки подключений к внешним сервисам.
"""
import sys

def check_db():
    """Проверка подключения к БД"""
    try:
        from sqlalchemy import text
        from app.db import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ База данных: подключение успешно")
        return True
    except Exception as e:
        print(f"❌ База данных: ошибка подключения - {e}")
        return False

def check_prowlarr():
    """Проверка подключения к Prowlarr"""
    try:
        from app.prowlarr_client import search_by_query
        # Тестовый запрос по названию
        result = search_by_query('The Shawshank Redemption')
        print("✅ Prowlarr: подключение успешно")
        return True
    except Exception as e:
        print(f"❌ Prowlarr: ошибка подключения - {e}")
        return False

def check_telegram():
    """Проверка отправки сообщения в Telegram"""
    try:
        from app.notifier import send_message
        send_message("🔍 NightWatcher: проверка подключения")
        print("✅ Telegram: сообщение отправлено")
        return True
    except Exception as e:
        print(f"❌ Telegram: ошибка отправки - {e}")
        return False

if __name__ == "__main__":
    print("Проверка подключений NightWatcher...\n")
    
    results = [
        check_db(),
        check_prowlarr(),
        check_telegram()
    ]
    
    print("\n" + "="*50)
    if all(results):
        print("✅ Все подключения работают корректно")
        sys.exit(0)
    else:
        print("❌ Некоторые подключения не работают")
        sys.exit(1)
