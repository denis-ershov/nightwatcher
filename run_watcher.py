"""
Скрипт для периодического запуска watcher.
Проверяет новые релизы каждые 30 минут.
"""
import time
import sys
from app.watcher import run

if __name__ == "__main__":
    interval = 1800  # 30 минут в секундах
    
    print("🌙 NightWatcher запущен")
    print(f"Интервал проверки: {interval // 60} минут")
    print("Нажмите Ctrl+C для остановки\n")
    
    while True:
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Запуск проверки...")
            run()
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Проверка завершена\n")
        except KeyboardInterrupt:
            print("\n\nОстановка NightWatcher...")
            sys.exit(0)
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ошибка: {e}\n")
        
        time.sleep(interval)
