"""
Асинхронный клиент для Prowlarr API.
Использует httpx для неблокирующих HTTP запросов.
"""
import httpx
from app.config import PROWLARR_URL, PROWLARR_API_KEY
from typing import List, Dict, Any

# Глобальный HTTP клиент с пулом соединений
_client: httpx.AsyncClient | None = None

async def get_client() -> httpx.AsyncClient:
    """Получить или создать HTTP клиент с пулом соединений"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            follow_redirects=True,
        )
    return _client

async def close_client():
    """Закрыть HTTP клиент при завершении приложения"""
    global _client
    if _client:
        await _client.aclose()
        _client = None

async def search_by_imdb(imdb_id: str) -> List[Dict[Any, Any]]:
    """Поиск по IMDb ID (для обратной совместимости)"""
    client = await get_client()
    try:
        response = await client.get(
            f"{PROWLARR_URL}/api/v1/search",
            params={"imdbId": imdb_id, "apikey": PROWLARR_API_KEY},
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        raise Exception(f"Prowlarr API error: {e}") from e

async def search_by_query(query: str) -> List[Dict[Any, Any]]:
    """Поиск по названию (query)"""
    if not query:
        return []
    
    client = await get_client()
    try:
        response = await client.get(
            f"{PROWLARR_URL}/api/v1/search",
            params={"query": query, "apikey": PROWLARR_API_KEY},
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        raise Exception(f"Prowlarr API error: {e}") from e

async def get_download_link(indexer_id: int, guid: str) -> str | None:
    """
    Получить ссылку на скачивание (magnet или torrent) через Prowlarr API.
    
    Args:
        indexer_id: ID индексера в Prowlarr
        guid: GUID релиза
    
    Returns:
        Magnet-ссылка или ссылка на скачивание, или None
    """
    client = await get_client()
    try:
        # Пытаемся получить ссылку на скачивание через Prowlarr download endpoint
        response = await client.get(
            f"{PROWLARR_URL}/{indexer_id}/download",
            params={"guid": guid, "apikey": PROWLARR_API_KEY},
            follow_redirects=False,  # Не следовать редиректам, чтобы получить конечный URL
        )
        
        # Проверяем заголовок Location для редиректа
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "")
            if location.startswith("magnet:"):
                return location
            return location
        
        # Если ответ содержит magnet в тексте
        content = response.text
        if content.startswith("magnet:"):
            return content.strip()
        
        # Ищем magnet в содержимом
        import re
        magnet_match = re.search(r'magnet:\?[^\s<>"]+', content, re.IGNORECASE)
        if magnet_match:
            return magnet_match.group(0)
            
    except httpx.HTTPError as e:
        # Если не удалось получить через API, возвращаем None
        pass
    return None
