@echo off
echo ============================================================
echo NightWatcher - Запуск всех сервисов
echo ============================================================
echo.

REM Проверяем наличие виртуального окружения
if exist venv\Scripts\activate.bat (
    echo Активация виртуального окружения...
    call venv\Scripts\activate.bat
)

REM Запускаем единый скрипт
python run.py

pause
