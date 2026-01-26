import requests
from app.config import PROWLARR_URL, PROWLARR_API_KEY

def search_by_imdb(imdb_id):
    """Поиск по IMDb ID (для обратной совместимости)"""
    r = requests.get(
        f"{PROWLARR_URL}/api/v1/search",
        params={"imdbId": imdb_id, "apikey": PROWLARR_API_KEY},
        timeout=30
    )
    r.raise_for_status()
    return r.json()

def search_by_query(query):
    """Поиск по названию (query)"""
    r = requests.get(
        f"{PROWLARR_URL}/api/v1/search",
        params={"query": query, "apikey": PROWLARR_API_KEY},
        timeout=30
    )
    r.raise_for_status()
    return r.json()
