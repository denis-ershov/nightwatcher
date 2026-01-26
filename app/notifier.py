import requests
from app.config import TG_TOKEN, TG_CHAT_ID

def send_message(text: str, photo_url: str = None):
    if not TG_TOKEN or not TG_CHAT_ID:
        print(f"Telegram not configured. Message: {text}")
        return
    
    if photo_url:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        try:
            requests.post(url, json={
                "chat_id": TG_CHAT_ID,
                "photo": photo_url,
                "caption": text,
                "parse_mode": "HTML"
            }, timeout=10)
            return
        except Exception as e:
            print(f"Failed to send photo: {e}")
    
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }, timeout=10)
    except Exception as e:
        print(f"Failed to send message: {e}")

def format_new_release_notification(item: dict, release: dict, change_type: str = "new_release") -> str:
    title = item.get("title", "Unknown")
    year = item.get("year", "")
    rating = item.get("rating", "")
    genre = item.get("genre", "")
    imdb_id = item.get("imdb_id", "")
    item_type = item.get("type", "movie")
    
    type_emoji = "📺" if item_type == "tv" else "🎬"
    
    header = f"🌙 <b>NightWatcher</b>\n\n"
    
    if change_type == "new_episode":
        header += f"🆕 <b>Новый эпизод!</b>\n\n"
    elif change_type == "new_dub":
        header += f"🎙 <b>Новая озвучка!</b>\n\n"
    else:
        header += f"✨ <b>Новый релиз!</b>\n\n"
    
    info = f"{type_emoji} <b>{title}</b>"
    if year:
        info += f" ({year})"
    info += "\n"
    
    if rating:
        info += f"⭐ IMDb: {rating}\n"
    if genre:
        info += f"🎭 {genre}\n"
    
    info += f"\n📥 <b>Релиз:</b>\n"
    info += f"📝 {release.get('title', 'N/A')}\n"
    
    if release.get('quality'):
        info += f"📺 Качество: {release.get('quality')}\n"
    if release.get('size'):
        size_gb = release.get('size', 0) / (1024 * 1024 * 1024)
        info += f"💾 Размер: {size_gb:.2f} GB\n"
    if release.get('seeders'):
        info += f"🌱 Сидеры: {release.get('seeders')}\n"
    if release.get('tracker'):
        info += f"🔗 Трекер: {release.get('tracker')}\n"
    
    info += f"\n🔗 <a href='https://www.imdb.com/title/{imdb_id}'>IMDb</a>"
    
    return header + info
