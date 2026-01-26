from sqlalchemy import text
from app.db import SessionLocal
from app.prowlarr_client import search_by_query
from app.notifier import send_message
from datetime import datetime

def run():
    db = SessionLocal()
    items = db.execute(
        text("SELECT imdb_id, title FROM imdb_watchlist WHERE enabled = true")
    ).fetchall()

    for imdb_id, title in items:
        # Используем название для поиска, если оно есть, иначе IMDb ID
        search_query = title if title else imdb_id
        if not search_query:
            continue
            
        for r in search_by_query(search_query):
            try:
                db.execute(
                    text("""INSERT INTO torrent_releases
                    (imdb_id, title, info_hash, quality, size, seeders, tracker, published_at)
                    VALUES (:imdb, :title, :hash, :quality, :size, :seeders, :tracker, :pub)"""),
                    {
                        "imdb": imdb_id,
                        "title": r.get("title"),
                        "hash": r.get("infoHash"),
                        "quality": r.get("quality", {}).get("resolution"),
                        "size": r.get("size"),
                        "seeders": r.get("seeders"),
                        "tracker": r.get("indexer"),
                        "pub": datetime.utcnow()
                    }
                )
                send_message(f"🌙 NightWatcher\n🎬 {title}\n{r.get('title')}")
                db.commit()
            except Exception:
                db.rollback()

    db.close()
