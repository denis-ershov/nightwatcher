"""
Модуль для валидации входных данных с использованием Pydantic.
"""
import re
from typing import Optional
from pydantic import BaseModel, field_validator, Field
from app.logger import get_logger

logger = get_logger(__name__)

class AddItemRequest(BaseModel):
    """Модель для добавления элемента в watchlist"""
    imdb_id: str = Field(..., min_length=9, max_length=20)
    
    @field_validator('imdb_id')
    @classmethod
    def validate_imdb_id(cls, v):
        """Валидация формата IMDb ID"""
        # Извлекаем IMDb ID из строки (может содержать дополнительный текст)
        imdb_match = re.search(r'(tt\d+)', v)
        if not imdb_match:
            raise ValueError('Invalid IMDb ID format. Expected format: tt1234567')
        return imdb_match.group(1)
    
    class Config:
        extra = "forbid"

class EditItemRequest(BaseModel):
    """Модель для редактирования элемента"""
    title: str = Field(..., min_length=1, max_length=500)
    type: str = Field(..., pattern="^(movie|tv)$")
    target_season: Optional[int] = Field(None, ge=1, le=100)
    preferred_quality: Optional[str] = Field(None, max_length=100)
    preferred_audio: Optional[str] = Field(None, max_length=100)
    min_releases_count: Optional[int] = Field(None, ge=1, le=1000)
    
    @field_validator('preferred_quality')
    @classmethod
    def validate_quality(cls, v):
        """Валидация качества"""
        if v:
            valid_qualities = ['1080p', '2160p', '720p', '480p', '4K', 'UHD', 'HD', 'SD']
            qualities = [q.strip().lower() for q in v.split(',')]
            for q in qualities:
                if not any(vq in q for vq in valid_qualities):
                    logger.warning(f"Unknown quality format: {q}")
        return v
    
    class Config:
        extra = "forbid"

class SearchRequest(BaseModel):
    """Модель для поиска и фильтрации"""
    page: int = Field(1, ge=1, le=1000)
    per_page: int = Field(20, ge=1, le=100)
    search: Optional[str] = Field(None, max_length=200)
    type_filter: Optional[str] = Field(None, pattern="^(movie|tv|all)$")
    enabled_filter: Optional[bool] = None
    year_filter: Optional[int] = Field(None, ge=1900, le=2100)
    sort_by: str = Field("created_at", pattern="^(created_at|title|year|last_checked)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")
    
    class Config:
        extra = "forbid"

class ReleaseFilterRequest(BaseModel):
    """Модель для фильтрации релизов"""
    quality: Optional[str] = None
    tracker: Optional[str] = None
    min_seeders: Optional[int] = Field(None, ge=0)
    max_size_gb: Optional[float] = Field(None, ge=0)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    sort_by: str = Field("created_at", pattern="^(created_at|size|seeders|quality)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")
    
    class Config:
        extra = "forbid"
