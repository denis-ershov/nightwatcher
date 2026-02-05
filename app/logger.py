"""
Модуль для настройки логирования приложения.
Поддерживает структурированное логирование и ротацию логов.
"""
import logging
import logging.handlers
import os
import json
from datetime import datetime
from pathlib import Path

# Создаем директорию для логов если её нет
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Формат логирования
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# JSON формат для структурированного логирования
class JSONFormatter(logging.Formatter):
    """Форматтер для JSON логирования"""
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Добавляем информацию об исключении если есть
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Добавляем дополнительные поля
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        
        return json.dumps(log_entry, ensure_ascii=False)

def setup_logging(log_level: str = None, json_format: bool = False):
    """
    Настройка логирования для приложения.
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Использовать JSON формат (для продакшена)
    """
    # Определяем уровень логирования из переменной окружения или используем INFO по умолчанию
    level = getattr(logging, (log_level or os.getenv("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    
    # Создаем root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Удаляем существующие handlers
    root_logger.handlers.clear()
    
    # Форматтер
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler с ротацией
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "nightwatcher.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler (только ошибки)
    error_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "nightwatcher_errors.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # Настраиваем логирование для внешних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    
    return root_logger

# Инициализация логирования при импорте модуля
setup_logging()

def get_logger(name: str) -> logging.Logger:
    """Получить logger для модуля"""
    return logging.getLogger(name)
