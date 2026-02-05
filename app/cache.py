"""
Модуль для кэширования метаданных.
Использует in-memory cache с TTL.
"""
import time
from typing import Optional, Dict, Any
from functools import wraps
from app.logger import get_logger

logger = get_logger(__name__)

class SimpleCache:
    """Простой in-memory кэш с TTL"""
    
    def __init__(self, default_ttl: int = 86400):  # 24 часа по умолчанию
        """
        Args:
            default_ttl: Время жизни кэша в секундах
        """
        self._cache: Dict[str, tuple[Any, float]] = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Получить значение из кэша"""
        if key not in self._cache:
            return None
        
        value, expiry = self._cache[key]
        
        if time.time() > expiry:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Сохранить значение в кэш"""
        ttl = ttl or self.default_ttl
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)
        logger.debug(f"Cached value for key: {key}, TTL: {ttl}s")
    
    def delete(self, key: str) -> None:
        """Удалить значение из кэша"""
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Deleted cache key: {key}")
    
    def clear(self) -> None:
        """Очистить весь кэш"""
        self._cache.clear()
        logger.info("Cache cleared")
    
    def cleanup(self) -> None:
        """Очистить истекшие записи"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if current_time > expiry
        ]
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

# Глобальный экземпляр кэша
_metadata_cache = SimpleCache(default_ttl=86400)  # 24 часа

def get_cache() -> SimpleCache:
    """Получить глобальный экземпляр кэша"""
    return _metadata_cache

def cached(ttl: int = 86400, key_prefix: str = ""):
    """
    Декоратор для кэширования результатов функции.
    
    Args:
        ttl: Время жизни кэша в секундах
        key_prefix: Префикс для ключа кэша
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Формируем ключ кэша
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # Пытаемся получить из кэша
            cached_value = _metadata_cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_value
            
            # Выполняем функцию
            result = await func(*args, **kwargs)
            
            # Сохраняем в кэш
            if result is not None:
                _metadata_cache.set(cache_key, result, ttl)
            
            return result
        
        return async_wrapper
    
    return decorator
