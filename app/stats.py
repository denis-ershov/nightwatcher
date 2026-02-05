"""
Модуль для сбора и предоставления статистики.
"""
from sqlalchemy import text, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import Dict, Any, List
from app.logger import get_logger

logger = get_logger(__name__)

async def get_statistics(db: AsyncSession) -> Dict[str, Any]:
    """
    Получить общую статистику приложения.
    
    Returns:
        Словарь со статистикой
    """
    stats = {}
    
    try:
        # Всего элементов в watchlist
        result = await db.execute(
            text("SELECT COUNT(*) FROM imdb_watchlist")
        )
        stats["total_items"] = result.scalar() or 0
        
        # Активных элементов
        result = await db.execute(
            text("SELECT COUNT(*) FROM imdb_watchlist WHERE enabled = true")
        )
        stats["active_items"] = result.scalar() or 0
        
        # Всего релизов
        result = await db.execute(
            text("SELECT COUNT(*) FROM torrent_releases")
        )
        stats["total_releases"] = result.scalar() or 0
        
        # Релизов за последние 24 часа
        result = await db.execute(
            text("""
                SELECT COUNT(*) FROM torrent_releases 
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """)
        )
        stats["releases_24h"] = result.scalar() or 0
        
        # Релизов за последнюю неделю
        result = await db.execute(
            text("""
                SELECT COUNT(*) FROM torrent_releases 
                WHERE created_at >= NOW() - INTERVAL '7 days'
            """)
        )
        stats["releases_7d"] = result.scalar() or 0
        
        # Релизов за последний месяц
        result = await db.execute(
            text("""
                SELECT COUNT(*) FROM torrent_releases 
                WHERE created_at >= NOW() - INTERVAL '30 days'
            """)
        )
        stats["releases_30d"] = result.scalar() or 0
        
        # Топ трекеров
        result = await db.execute(
            text("""
                SELECT tracker, COUNT(*) as count 
                FROM torrent_releases 
                WHERE tracker IS NOT NULL
                GROUP BY tracker 
                ORDER BY count DESC 
                LIMIT 10
            """)
        )
        stats["top_trackers"] = [
            {"tracker": row[0], "count": row[1]}
            for row in result.fetchall()
        ]
        
        # Распределение по типам
        result = await db.execute(
            text("""
                SELECT type, COUNT(*) as count 
                FROM imdb_watchlist 
                GROUP BY type
            """)
        )
        stats["items_by_type"] = {
            row[0]: row[1]
            for row in result.fetchall()
        }
        
        # Статистика по релизам за последние 30 дней (для графика)
        result = await db.execute(
            text("""
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM torrent_releases
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY DATE(created_at)
                ORDER BY date ASC
            """)
        )
        stats["releases_chart"] = [
            {"date": row[0].isoformat() if row[0] else None, "count": row[1]}
            for row in result.fetchall()
        ]
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}", exc_info=True)
        stats["error"] = str(e)
    
    return stats

async def get_item_statistics(db: AsyncSession, imdb_id: str) -> Dict[str, Any]:
    """
    Получить статистику для конкретного элемента.
    
    Args:
        imdb_id: IMDb ID элемента
        
    Returns:
        Словарь со статистикой элемента
    """
    stats = {}
    
    try:
        # Общее количество релизов
        result = await db.execute(
            text("SELECT COUNT(*) FROM torrent_releases WHERE imdb_id = :imdb_id"),
            {"imdb_id": imdb_id}
        )
        stats["total_releases"] = result.scalar() or 0
        
        # Последний релиз
        result = await db.execute(
            text("""
                SELECT title, quality, created_at 
                FROM torrent_releases 
                WHERE imdb_id = :imdb_id 
                ORDER BY created_at DESC 
                LIMIT 1
            """),
            {"imdb_id": imdb_id}
        )
        last_release = result.fetchone()
        if last_release:
            stats["last_release"] = {
                "title": last_release[0],
                "quality": last_release[1],
                "created_at": last_release[2].isoformat() if last_release[2] else None
            }
        
        # Распределение по качеству
        result = await db.execute(
            text("""
                SELECT quality, COUNT(*) as count 
                FROM torrent_releases 
                WHERE imdb_id = :imdb_id AND quality IS NOT NULL
                GROUP BY quality
            """),
            {"imdb_id": imdb_id}
        )
        stats["releases_by_quality"] = {
            row[0]: row[1]
            for row in result.fetchall()
        }
        
    except Exception as e:
        logger.error(f"Error getting item statistics: {e}", exc_info=True)
        stats["error"] = str(e)
    
    return stats
