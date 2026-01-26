@echo off
echo Запуск NightWatcher веб-сервера...
echo.
echo Сервер будет доступен по адресу:
echo   http://localhost:8000
echo   http://127.0.0.1:8000
echo.
echo Нажмите Ctrl+C для остановки
echo.
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
pause
