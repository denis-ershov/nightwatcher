"""
Entrypoint для Vercel deployment.
Импортирует FastAPI приложение из app.api
"""
from app.api import app

# Экспортируем app для Vercel
__all__ = ["app"]
