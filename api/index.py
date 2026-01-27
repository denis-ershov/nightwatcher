"""
Entrypoint для Vercel deployment.
Импортирует FastAPI приложение из app.api
"""
import sys
import os

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api import app

# Экспортируем app для Vercel
__all__ = ["app"]
