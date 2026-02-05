import httpx
from app.config import TMDB_API_KEY
from app.logger import get_logger
from app.cache import cached
from app.retry import retry

logger = get_logger(__name__)

TVMAZE_BASE = "https://api.tvmaze.com"
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


@retry(max_attempts=3, delay=1.0, backoff=2.0)
@cached(ttl=86400, key_prefix="tvmaze")
async def fetch_from_tvmaze(imdb_id: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{TVMAZE_BASE}/lookup/shows", params={"imdb": imdb_id})
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            premiered = data.get("premiered", "")
            year = premiered[:4] if premiered else None
            
            genres = data.get("genres", [])
            
            image = data.get("image", {})
            poster_url = image.get("original") or image.get("medium") if image else None
            
            rating_obj = data.get("rating", {})
            rating = str(rating_obj.get("average")) if rating_obj and rating_obj.get("average") else None
            
            summary = data.get("summary", "")
            if summary:
                import re
                summary = re.sub(r'<[^>]+>', '', summary)
            
            return {
                "title": data.get("name"),
                "original_title": data.get("name"),  # TVMaze обычно возвращает оригинальное название в "name"
                "year": year,
                "genre": ", ".join(genres) if genres else None,
                "plot": summary,
                "poster_url": poster_url,
                "rating": rating,
                "runtime": str(data.get("averageRuntime") or data.get("runtime", "")) + " min" if data.get("averageRuntime") or data.get("runtime") else None,
                "type": "tv",
                "total_seasons": None,
                "status": data.get("status"),
                "network": data.get("network", {}).get("name") if data.get("network") else None,
                "language": data.get("language"),
                "country": data.get("network", {}).get("country", {}).get("name") if data.get("network") else None,
                "official_site": data.get("officialSite"),
                "schedule": f"{', '.join(data.get('schedule', {}).get('days', []))} at {data.get('schedule', {}).get('time', '')}" if data.get("schedule", {}).get("days") else None,
            }
    except Exception as e:
        logger.error(f"TVMaze error: {e}", exc_info=True)
    return None


@retry(max_attempts=3, delay=1.0, backoff=2.0)
@cached(ttl=86400, key_prefix="tmdb")
async def fetch_from_tmdb(imdb_id: str) -> dict | None:
    if not TMDB_API_KEY:
        logger.warning("TMDB_API_KEY not configured")
        return None
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            find_response = await client.get(
                f"{TMDB_BASE}/find/{imdb_id}",
                params={"api_key": TMDB_API_KEY, "external_source": "imdb_id"}
            )
            if find_response.status_code != 200:
                return None
            
            find_data = find_response.json()
            
            movie_results = find_data.get("movie_results", [])
            tv_results = find_data.get("tv_results", [])
            
            if movie_results:
                movie = movie_results[0]
                movie_id = movie["id"]
                
                details_response = await client.get(
                    f"{TMDB_BASE}/movie/{movie_id}",
                    params={"api_key": TMDB_API_KEY, "language": "ru-RU"}
                )
                if details_response.status_code != 200:
                    return None
                
                data = details_response.json()
                
                genres = [g["name"] for g in data.get("genres", [])]
                
                credits_response = await client.get(
                    f"{TMDB_BASE}/movie/{movie_id}/credits",
                    params={"api_key": TMDB_API_KEY}
                )
                credits = credits_response.json() if credits_response.status_code == 200 else {}
                
                cast = credits.get("cast", [])[:5]
                actors = ", ".join([a["name"] for a in cast]) if cast else None
                
                crew = credits.get("crew", [])
                directors = [c["name"] for c in crew if c.get("job") == "Director"]
                director = ", ".join(directors) if directors else None
                
                countries = [c["name"] for c in data.get("production_countries", [])]
                
                return {
                    "title": data.get("title") or data.get("original_title"),
                    "year": data.get("release_date", "")[:4] if data.get("release_date") else None,
                    "genre": ", ".join(genres) if genres else None,
                    "plot": data.get("overview"),
                    "poster_url": f"{TMDB_IMAGE_BASE}{data.get('poster_path')}" if data.get("poster_path") else None,
                    "rating": str(data.get("vote_average")) if data.get("vote_average") else None,
                    "runtime": f"{data.get('runtime')} min" if data.get("runtime") else None,
                    "type": "movie",
                    "total_seasons": None,
                    "status": data.get("status"),
                    "budget": f"${data.get('budget'):,}" if data.get("budget") else None,
                    "revenue": f"${data.get('revenue'):,}" if data.get("revenue") else None,
                    "actors": actors,
                    "director": director,
                    "country": ", ".join(countries) if countries else None,
                    "tagline": data.get("tagline"),
                    "original_title": data.get("original_title"),
                    "original_language": data.get("original_language"),
                }
            
            elif tv_results:
                tv = tv_results[0]
                tv_id = tv["id"]
                
                details_response = await client.get(
                    f"{TMDB_BASE}/tv/{tv_id}",
                    params={"api_key": TMDB_API_KEY, "language": "ru-RU"}
                )
                if details_response.status_code != 200:
                    return None
                
                data = details_response.json()
                
                genres = [g["name"] for g in data.get("genres", [])]
                countries = [c["name"] for c in data.get("production_countries", [])]
                networks = [n["name"] for n in data.get("networks", [])]
                creators = [c["name"] for c in data.get("created_by", [])]
                
                return {
                    "title": data.get("name") or data.get("original_name"),
                    "year": data.get("first_air_date", "")[:4] if data.get("first_air_date") else None,
                    "genre": ", ".join(genres) if genres else None,
                    "plot": data.get("overview"),
                    "poster_url": f"{TMDB_IMAGE_BASE}{data.get('poster_path')}" if data.get("poster_path") else None,
                    "rating": str(data.get("vote_average")) if data.get("vote_average") else None,
                    "runtime": f"{data.get('episode_run_time', [0])[0]} min" if data.get("episode_run_time") else None,
                    "type": "tv",
                    "total_seasons": data.get("number_of_seasons"),
                    "total_episodes": data.get("number_of_episodes"),
                    "status": data.get("status"),
                    "network": ", ".join(networks) if networks else None,
                    "country": ", ".join(countries) if countries else None,
                    "creators": ", ".join(creators) if creators else None,
                    "original_title": data.get("original_name"),
                    "original_language": data.get("original_language"),
                    "last_air_date": data.get("last_air_date"),
                    "in_production": data.get("in_production"),
                }
    
    except Exception as e:
        logger.error(f"TMDB error: {e}", exc_info=True)
    return None


async def fetch_metadata(imdb_id: str) -> dict:
    tvmaze_data = await fetch_from_tvmaze(imdb_id)
    if tvmaze_data:
        return tvmaze_data
    
    tmdb_data = await fetch_from_tmdb(imdb_id)
    if tmdb_data:
        return tmdb_data
    
    return {"title": imdb_id, "type": "movie"}
