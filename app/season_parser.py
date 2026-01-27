"""
Модуль для парсинга номера сезона из названия сериала.
"""
import re
from typing import Optional

def extract_season_from_title(title: str) -> Optional[int]:
    """
    Извлекает номер сезона из названия.
    
    Примеры:
    - "Stranger Things 4 сезон" -> 4
    - "Game of Thrones Season 3" -> 3
    - "Breaking Bad S02" -> 2
    - "The Office S5" -> 5
    
    Args:
        title: Название сериала с возможным указанием сезона
    
    Returns:
        Номер сезона или None, если не найден
    """
    if not title:
        return None
    
    # Паттерны для поиска номера сезона
    patterns = [
        r'\b(\d+)\s*(?:сезон|season|s)\b',  # "4 сезон", "4 season", "4 s"
        r'\bs(?:eason)?\s*(\d+)\b',  # "s4", "season 4", "s 4"
        r'\bсезон\s*(\d+)\b',  # "сезон 4"
        r'\b(\d+)\s*сезон\b',  # "4 сезон"
    ]
    
    title_lower = title.lower()
    
    for pattern in patterns:
        match = re.search(pattern, title_lower, re.IGNORECASE)
        if match:
            try:
                season_num = int(match.group(1))
                if 1 <= season_num <= 100:  # Разумные пределы
                    return season_num
            except (ValueError, IndexError):
                continue
    
    return None

def clean_title_from_season(title: str) -> str:
    """
    Удаляет указание сезона из названия.
    
    Примеры:
    - "Stranger Things 4 сезон" -> "Stranger Things"
    - "Game of Thrones Season 3" -> "Game of Thrones"
    
    Args:
        title: Название с возможным указанием сезона
    
    Returns:
        Очищенное название без указания сезона
    """
    if not title:
        return title
    
    # Паттерны для удаления
    patterns = [
        r'\s*\d+\s*(?:сезон|season|s)\b',
        r'\bs(?:eason)?\s*\d+\b',
        r'\bсезон\s*\d+\b',
    ]
    
    cleaned = title
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()
