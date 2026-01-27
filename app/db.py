"""
Асинхронное подключение к базе данных с пулом соединений.
Оптимизировано для предотвращения утечек памяти.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import DATABASE_URL
import re

# Конвертируем синхронный DATABASE_URL в асинхронный
def get_async_database_url(url: str) -> str:
    """Конвертирует postgresql:// в postgresql+asyncpg://"""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    return url

# Создаем асинхронный engine с пулом соединений
if DATABASE_URL:
    async_database_url = get_async_database_url(DATABASE_URL)
    
    # Настройки пула для оптимизации производительности
    engine = create_async_engine(
        async_database_url,
        pool_size=10,  # Размер пула соединений
        max_overflow=20,  # Максимальное количество дополнительных соединений
        pool_pre_ping=True,  # Проверка соединений перед использованием
        pool_recycle=3600,  # Переиспользование соединений каждый час
        echo=False,  # Отключить SQL логирование в продакшене
        future=True,
    )
    
    # Создаем фабрику сессий
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
else:
    engine = None
    AsyncSessionLocal = None

Base = declarative_base()

async def get_db() -> AsyncSession:
    """
    Dependency для получения асинхронной сессии БД.
    Автоматически закрывает соединение после использования.
    """
    if not AsyncSessionLocal:
        raise RuntimeError("Database not configured")
    
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def close_db():
    """Закрывает все соединения с БД при завершении приложения"""
    if engine:
        await engine.dispose()
