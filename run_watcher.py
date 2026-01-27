"""
Асинхронный скрипт для периодического запуска watcher.
Оптимизирован для предотвращения утечек памяти.
"""
import asyncio
import sys
from app.watcher import run
from app.db import close_db
from app.prowlarr_client import close_client
from app.notifier import close_bot

async def main():
    """Основная функция с правильным управлением ресурсами"""
    interval = 1800  # 30 минут в секундах
    
    print("🌙 NightWatcher запущен")
    print(f"Интервал проверки: {interval // 60} минут")
    print("Нажмите Ctrl+C для остановки\n")
    
    try:
        while True:
            try:
                print(f"[{asyncio.get_event_loop().time()}] Запуск проверки...")
                found = await run()
                print(f"Проверка завершена. Найдено новых релизов: {found}\n")
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Ошибка при проверке: {e}\n")
            
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        print("\n\nОстановка NightWatcher...")
    finally:
        # Закрываем все соединения
        await close_db()
        await close_client()
        await close_bot()
        print("Ресурсы освобождены")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем")
        sys.exit(0)
