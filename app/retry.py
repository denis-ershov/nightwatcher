"""
Модуль для retry логики и circuit breaker паттерна.
"""
import asyncio
import time
import logging
from typing import Callable, Any, Optional, TypeVar, Coroutine
from functools import wraps
from app.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')

class CircuitBreaker:
    """Circuit Breaker для защиты от каскадных сбоев"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        """
        Args:
            failure_threshold: Количество ошибок до открытия circuit
            recovery_timeout: Время в секундах до попытки восстановления
            expected_exception: Тип исключения для отслеживания
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Выполнить функцию через circuit breaker"""
        if self.state == "OPEN":
            if time.time() - (self.last_failure_time or 0) < self.recovery_timeout:
                raise Exception("Circuit breaker is OPEN")
            else:
                self.state = "HALF_OPEN"
        
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")
            
            raise
    
    async def call_async(self, func: Callable[..., Coroutine[Any, Any, T]], *args, **kwargs) -> T:
        """Асинхронная версия call"""
        if self.state == "OPEN":
            if time.time() - (self.last_failure_time or 0) < self.recovery_timeout:
                raise Exception("Circuit breaker is OPEN")
            else:
                self.state = "HALF_OPEN"
        
        try:
            result = await func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")
            
            raise

def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    logger_instance: Optional[logging.Logger] = None
):
    """
    Декоратор для retry логики с exponential backoff.
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Начальная задержка между попытками
        backoff: Множитель для задержки
        exceptions: Кортеж исключений для перехвата
        logger_instance: Logger для логирования (опционально)
    """
    log = logger_instance or logger
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                last_exception = None
                current_delay = delay
                
                for attempt in range(max_attempts):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < max_attempts - 1:
                            log.warning(
                                f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                                f"Retrying in {current_delay}s..."
                            )
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            log.error(
                                f"All {max_attempts} attempts failed for {func.__name__}: {e}"
                            )
                
                raise last_exception
            
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                last_exception = None
                current_delay = delay
                
                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < max_attempts - 1:
                            log.warning(
                                f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                                f"Retrying in {current_delay}s..."
                            )
                            time.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            log.error(
                                f"All {max_attempts} attempts failed for {func.__name__}: {e}"
                            )
                
                raise last_exception
            
            return sync_wrapper
        
        return wrapper
    
    return decorator
