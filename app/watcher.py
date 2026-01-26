from sqlalchemy import text
from app.db import SessionLocal
from app.prowlarr_client import search_by_query
from app.notifier import send_message, format_new_release_notification
from app.omdb import fetch_movie_info_sync
from datetime import datetime

def run():
    if not SessionLocal:
        print("Database not configured")
        return 0
    
    db = SessionLocal()
    found_count = 0
    
    try:
        items = db.execute(
            text("""SELECT id, imdb_id, title, type, poster_url, year, genre, rating, runtime
                    FROM imdb_watchlist WHERE enabled = true""")
        ).fetchall()

        for row in items:
            item_id = row[0]
            imdb_id = row[1]
            title = row[2]
            item_type = row[3]
            poster_url = row[4]
            year = row[5]
            genre = row[6]
            rating = row[7]
            runtime = row[8]
            
            item_data = {
                "id": item_id,
                "imdb_id": imdb_id,
                "title": title,
                "type": item_type,
                "poster_url": poster_url,
                "year": year,
                "genre": genre,
                "rating": rating,
                "runtime": runtime,
            }
            
            search_query = title if title else imdb_id
            if not search_query:
                continue
            
            try:
                results = search_by_query(search_query)
            except Exception as e:
                print(f"Search error for {search_query}: {e}")
                continue
                
            for r in results:
                info_hash = r.get("infoHash") or r.get("guid", "")[:40]
                if not info_hash:
                    continue
                
                release_data = {
                    "title": r.get("title"),
                    "quality": r.get("quality", {}).get("resolution") if isinstance(r.get("quality"), dict) else r.get("quality"),
                    "size": r.get("size"),
                    "seeders": r.get("seeders"),
                    "tracker": r.get("indexer"),
                }
                
                try:
                    result = db.execute(
                        text("SELECT id FROM torrent_releases WHERE imdb_id = :imdb AND info_hash = :hash"),
                        {"imdb": imdb_id, "hash": info_hash}
                    ).fetchone()
                    
                    if result:
                        continue
                    
                    db.execute(
                        text("""INSERT INTO torrent_releases
                        (imdb_id, title, info_hash, quality, size, seeders, tracker, published_at)
                        VALUES (:imdb, :title, :hash, :quality, :size, :seeders, :tracker, :pub)"""),
                        {
                            "imdb": imdb_id,
                            "title": r.get("title"),
                            "hash": info_hash,
                            "quality": release_data["quality"],
                            "size": r.get("size"),
                            "seeders": r.get("seeders"),
                            "tracker": r.get("indexer"),
                            "pub": datetime.utcnow()
                        }
                    )
                    db.commit()
                    
                    change_type = detect_change_type(release_data["title"], item_type)
                    notification = format_new_release_notification(item_data, release_data, change_type)
                    send_message(notification, poster_url)
                    
                    found_count += 1
                    
                except Exception as e:
                    db.rollback()
                    print(f"Error processing release: {e}")
            
            db.execute(
                text("UPDATE imdb_watchlist SET last_checked = :now WHERE id = :id"),
                {"now": datetime.utcnow(), "id": item_id}
            )
            db.commit()
    
    except Exception as e:
        print(f"Watcher error: {e}")
    finally:
        db.close()
    
    return found_count

def detect_change_type(release_title: str, item_type: str) -> str:
    if not release_title:
        return "new_release"
    
    title_lower = release_title.lower()
    
    dub_keywords = ["dub", "озвучка", "дубляж", "voice", "localization", "russian", "русская"]
    if any(kw in title_lower for kw in dub_keywords):
        return "new_dub"
    
    episode_keywords = ["s0", "s1", "s2", "s3", "e0", "e1", "episode", "серия", "сезон"]
    if item_type == "tv" and any(kw in title_lower for kw in episode_keywords):
        return "new_episode"
    
    return "new_release"

def run_search():
    return run()
