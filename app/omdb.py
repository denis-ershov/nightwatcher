import httpx
from app.config import OMDB_API_KEY

async def fetch_movie_info(imdb_id: str) -> dict:
    if not OMDB_API_KEY:
        return {}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://www.omdbapi.com/",
                params={"i": imdb_id, "apikey": OMDB_API_KEY, "plot": "full"},
                timeout=10.0
            )
            data = response.json()
            if data.get("Response") == "True":
                return {
                    "title": data.get("Title"),
                    "year": data.get("Year"),
                    "genre": data.get("Genre"),
                    "plot": data.get("Plot"),
                    "poster_url": data.get("Poster") if data.get("Poster") != "N/A" else None,
                    "rating": data.get("imdbRating"),
                    "runtime": data.get("Runtime"),
                    "type": "tv" if data.get("Type") == "series" else "movie",
                    "total_seasons": int(data.get("totalSeasons")) if data.get("totalSeasons") and data.get("totalSeasons") != "N/A" else None,
                    "actors": data.get("Actors"),
                    "director": data.get("Director"),
                    "country": data.get("Country"),
                }
    except Exception as e:
        print(f"OMDB error: {e}")
    return {}

def fetch_movie_info_sync(imdb_id: str) -> dict:
    import requests
    if not OMDB_API_KEY:
        return {}
    
    try:
        response = requests.get(
            "http://www.omdbapi.com/",
            params={"i": imdb_id, "apikey": OMDB_API_KEY, "plot": "full"},
            timeout=10
        )
        data = response.json()
        if data.get("Response") == "True":
            return {
                "title": data.get("Title"),
                "year": data.get("Year"),
                "genre": data.get("Genre"),
                "plot": data.get("Plot"),
                "poster_url": data.get("Poster") if data.get("Poster") != "N/A" else None,
                "rating": data.get("imdbRating"),
                "runtime": data.get("Runtime"),
                "type": "tv" if data.get("Type") == "series" else "movie",
                "total_seasons": int(data.get("totalSeasons")) if data.get("totalSeasons") and data.get("totalSeasons") != "N/A" else None,
                "actors": data.get("Actors"),
                "director": data.get("Director"),
                "country": data.get("Country"),
            }
    except Exception as e:
        print(f"OMDB error: {e}")
    return {}
