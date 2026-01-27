"""
Асинхронный скрипт для проверки подключений к внешним сервисам.
"""
import asyncio
import sys
from sqlalchemy import text

async def check_db():
    """Проверка подключения к БД"""
    try:
        from app.db import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        print("✅ База данных: подключение успешно")
        return True
    except Exception as e:
        print(f"❌ База данных: ошибка подключения - {e}")
        return False

async def check_prowlarr():
    """Проверка подключения к Prowlarr"""
    try:
        from app.prowlarr_client import search_by_query
        # Тестовый запрос по названию
        result = await search_by_query('The Shawshank Redemption')
        print("✅ Prowlarr: подключение успешно")
        return True
    except Exception as e:
        print(f"❌ Prowlarr: ошибка подключения - {e}")
        return False

async def check_telegram():
    """Проверка отправки сообщения в Telegram"""
    try:
        from app.notifier import send_message
        await send_message("🔍 NightWatcher: проверка подключения")
        print("✅ Telegram: сообщение отправлено")
        return True
    except Exception as e:
        print(f"❌ Telegram: ошибка отправки - {e}")
        return False

async def main():
    """Основная функция проверки"""
    print("Проверка подключений NightWatcher...\n")
    
    results = await asyncio.gather(
        check_db(),
        check_prowlarr(),
        check_telegram()
    )
    
    print("\n" + "="*50)
    if all(results):
        print("✅ Все подключения работают корректно")
        sys.exit(0)
    else:
        print("❌ Некоторые подключения не работают")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПроверка прервана")
        sys.exit(1)
