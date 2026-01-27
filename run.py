"""
Единый скрипт запуска для API сервера и Watcher.
Запускает оба процесса параллельно.
"""
import asyncio
import multiprocessing
import signal
import sys
import time

def run_api():
    """Запуск FastAPI сервера"""
    import uvicorn
    from app.api import app
    
    print("🚀 Запуск API сервера на http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

async def run_watcher_loop():
    """Запуск Watcher в цикле"""
    from app.watcher import run
    from app.db import close_db
    from app.prowlarr_client import close_client
    from app.notifier import close_bot
    
    interval = 1800  # 30 минут
    
    print("🌙 Запуск Watcher")
    print(f"Интервал проверки: {interval // 60} минут\n")
    
    try:
        while True:
            try:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Запуск проверки...")
                found = await run()
                print(f"Проверка завершена. Найдено новых релизов: {found}\n")
            except Exception as e:
                print(f"Ошибка при проверке: {e}\n")
            
            await asyncio.sleep(interval)
    finally:
        await close_db()
        await close_client()
        await close_bot()

def run_watcher():
    """Обертка для запуска watcher в отдельном процессе"""
    asyncio.run(run_watcher_loop())

def main():
    """Главная функция запуска обоих процессов"""
    print("=" * 60)
    print("🌙 NightWatcher - Запуск всех сервисов")
    print("=" * 60)
    print()
    
    # Создаем процессы
    api_process = multiprocessing.Process(target=run_api, name="API-Server")
    watcher_process = multiprocessing.Process(target=run_watcher, name="Watcher")
    
    # Обработчик сигналов для корректного завершения
    def signal_handler(sig, frame):
        print("\n\n🛑 Получен сигнал остановки...")
        api_process.terminate()
        watcher_process.terminate()
        api_process.join(timeout=5)
        watcher_process.join(timeout=5)
        if api_process.is_alive():
            api_process.kill()
        if watcher_process.is_alive():
            watcher_process.kill()
        print("✅ Все процессы остановлены")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Запускаем процессы
        api_process.start()
        watcher_process.start()
        
        print("✅ API сервер запущен (PID: {})".format(api_process.pid))
        print("✅ Watcher запущен (PID: {})".format(watcher_process.pid))
        print("\nНажмите Ctrl+C для остановки\n")
        
        # Ждем завершения процессов
        api_process.join()
        watcher_process.join()
        
    except KeyboardInterrupt:
        signal_handler(None, None)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        signal_handler(None, None)

if __name__ == "__main__":
    main()
