"""
Асинхронный модуль мониторинга новых релизов.
Оптимизирован для параллельной обработки и предотвращения утечек памяти.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal
from app.prowlarr_client import search_by_query, search_by_imdb, get_download_link
from app.notifier import send_message, format_new_release_notification
from app.season_parser import extract_season_from_title
from datetime import datetime
from typing import List, Dict, Any, Optional
import asyncio
import re

async def process_item(
    db: AsyncSession,
    item_id: int,
    imdb_id: str,
    title: str,
    original_title: str,
    item_type: str,
    poster_url: str,
    year: str,
    genre: str,
    rating: str,
    runtime: str,
    target_season: Optional[int] = None,
    preferred_quality: Optional[str] = None,
    preferred_audio: Optional[str] = None,
) -> int:
    """
    Обработать один элемент watchlist асинхронно.
    
    Returns:
        Количество найденных новых релизов
    """
    found_count = 0
    
    item_data = {
        "id": item_id,
        "imdb_id": imdb_id,
        "title": title,
        "original_title": original_title,
        "type": item_type,
        "poster_url": poster_url,
        "year": year,
        "genre": genre,
        "rating": rating,
        "runtime": runtime,
    }
    
    # Используем оригинальное название для поиска (приоритетно), если оно есть
    # Это улучшает поиск торрентов, так как большинство раздач на английском
    search_query = original_title if original_title else (title if title else imdb_id)
    if not search_query:
        return 0
    
    # Для сериалов добавляем номер сезона в поисковый запрос, если указан
    if item_type == "tv" and target_season:
        # Добавляем номер сезона в разных форматах для лучшего поиска
        season_formats = [
            f"{search_query} S{target_season:02d}",  # "Stranger Things S04"
            f"{search_query} Season {target_season}",  # "Stranger Things Season 4"
            f"{search_query} {target_season}",  # "Stranger Things 4"
        ]
        # Используем первый формат как основной, остальные как fallback
        search_query = season_formats[0]
    elif item_type == "tv":
        # Если сезон не указан, но есть в названии - извлекаем его
        season_from_title = extract_season_from_title(title) or extract_season_from_title(original_title)
        if season_from_title:
            search_query = f"{search_query} S{season_from_title:02d}"
    
    # Сначала пытаемся искать по IMDb ID (более точный поиск)
    results = []
    try:
        results = await search_by_imdb(imdb_id)
        if not results:
            # Если поиск по IMDb не дал результатов, ищем по названию
            print(f"No results by IMDb {imdb_id}, trying search by query: {search_query}")
            results = await search_by_query(search_query)
    except Exception as e:
        # Если поиск по IMDb не поддерживается или ошибка, ищем по названию
        print(f"IMDb search failed, trying query search: {e}")
        try:
            results = await search_by_query(search_query)
        except Exception as e2:
            print(f"Search error for {search_query}: {e2}")
            return 0
    
    # Фильтруем результаты по соответствию IMDb ID или названию
    results = filter_results_by_imdb_or_title(results, imdb_id, title, original_title)
    
    # Фильтруем результаты по качеству и озвучке, если указаны предпочтения
    filtered_results = filter_releases_by_preferences(results, preferred_quality, preferred_audio)
    
    for r in filtered_results:
        # Извлекаем guid для формирования ссылок на скачивание
        guid = r.get("guid") or r.get("downloadUrl") or r.get("link")
        tracker_name = (r.get("indexer") or "").lower()
        
        # Извлекаем infoHash из различных возможных полей
        # НЕ используем guid как infoHash, если это URL
        info_hash = (
            r.get("infoHash") or 
            r.get("info_hash") or
            (r.get("magnetUrl", "").split("btih:")[1].split("&")[0] if "btih:" in r.get("magnetUrl", "") else None)
        )
        
        # Если infoHash не найден, проверяем guid - возможно это хеш (НЕ URL!)
        if not info_hash and guid:
            guid_str = str(guid)
            # Проверяем, является ли guid хешем (40 символов hex, НЕ URL)
            # ВАЖНО: guid для NNMClub - это URL, а не хеш!
            if not guid_str.startswith("http") and len(guid_str) == 40:
                # Проверяем, что это hex строка
                if all(c in '0123456789abcdefABCDEF' for c in guid_str):
                    info_hash = guid_str
            elif not guid_str.startswith("http") and len(guid_str) >= 32:
                # Возможно, это хеш в другом формате
                # Извлекаем только hex символы
                hex_match = re.search(r'[0-9a-fA-F]{32,40}', guid_str)
                if hex_match:
                    info_hash = hex_match.group(0)
        
        # Если infoHash не найден, используем guid как уникальный идентификатор (но не как хеш для magnet)
        # Для некоторых трекеров guid - это URL, а не хеш
        if not info_hash:
            # Используем guid как info_hash только если это не URL
            if guid and not str(guid).startswith("http"):
                info_hash = str(guid)[:40]  # Используем первые 40 символов как идентификатор
            else:
                # Если guid - это URL, извлекаем из него уникальный идентификатор
                if guid and "id=" in str(guid):
                    # Для NNMClub используем ID из URL как info_hash
                    guid_str = str(guid)
                    tracker_id_from_url = guid_str.split("id=")[1].split("&")[0].split("#")[0]
                    # Используем комбинацию трекера и ID как уникальный идентификатор
                    info_hash = f"{tracker_name}_{tracker_id_from_url}"[:40]
                elif guid:
                    # Используем guid как есть (обрезаем до 40 символов)
                    info_hash = str(guid)[:40]
                else:
                    # Если нет infoHash и guid - пропускаем релиз
                    continue
        
        # Формируем ссылку на скачивание с трекера
        download_url = None
        tracker_id = None
        
        if guid:
            guid_str = str(guid)
            
            # NNMClub
            if "nnmclub" in tracker_name or "nnm" in tracker_name:
                if "id=" in guid_str:
                    tracker_id = guid_str.split("id=")[1].split("&")[0].split("#")[0]
                    download_url = f"https://nnmclub.to/forum/download.php?id={tracker_id}"
                elif guid_str.isdigit():
                    tracker_id = guid_str
                    download_url = f"https://nnmclub.to/forum/download.php?id={tracker_id}"
                elif "download.php" in guid_str or "viewtopic.php" in guid_str:
                    # guid уже содержит ссылку, извлекаем ID
                    if "id=" in guid_str:
                        tracker_id = guid_str.split("id=")[1].split("&")[0].split("#")[0]
                        download_url = f"https://nnmclub.to/forum/download.php?id={tracker_id}"
                    else:
                        # Возможно, guid уже является ссылкой на скачивание
                        download_url = guid_str
            
            # RuTracker
            elif "rutracker" in tracker_name:
                if "viewtopic.php?t=" in guid_str or "t=" in guid_str:
                    tracker_id = guid_str.split("t=")[1].split("&")[0].split("#")[0]
                    download_url = f"https://rutracker.org/forum/dl.php?t={tracker_id}"
                elif guid_str.isdigit():
                    tracker_id = guid_str
                    download_url = f"https://rutracker.org/forum/dl.php?t={tracker_id}"
                elif "dl.php" in guid_str or "viewtopic.php" in guid_str:
                    if "t=" in guid_str:
                        tracker_id = guid_str.split("t=")[1].split("&")[0].split("#")[0]
                        download_url = f"https://rutracker.org/forum/dl.php?t={tracker_id}"
                    else:
                        download_url = guid_str
            
            # Если guid уже является полной ссылкой на скачивание, используем её
            elif guid_str.startswith("http") and ("download" in guid_str or "dl.php" in guid_str):
                download_url = guid_str
                if "id=" in guid_str:
                    tracker_id = guid_str.split("id=")[1].split("&")[0].split("#")[0]
                elif "t=" in guid_str:
                    tracker_id = guid_str.split("t=")[1].split("&")[0].split("#")[0]
        
        # Формируем magnet-link из различных источников
        magnet_url = (
            r.get("magnetUrl") or 
            r.get("magnet") or 
            r.get("magnetLink") or
            r.get("downloadUrl")  # Некоторые трекеры возвращают magnet в downloadUrl
        )
        
        # Проверяем, является ли downloadUrl magnet-ссылкой
        if magnet_url and not magnet_url.startswith("magnet:"):
            # Если это не magnet, проверяем другие поля
            if "magnet:" in str(magnet_url).lower():
                # Извлекаем magnet из строки
                import re
                magnet_match = re.search(r'magnet:\?[^\s<>"]+', str(magnet_url), re.IGNORECASE)
                if magnet_match:
                    magnet_url = magnet_match.group(0)
                else:
                    magnet_url = None
        
        # Формируем magnet-link из infoHash ТОЛЬКО если это валидный hex хеш
        if not magnet_url and info_hash:
            # Проверяем, что info_hash - это hex строка (не URL и не текст)
            info_hash_str = str(info_hash)
            
            # Проверяем, что это не URL
            if info_hash_str.startswith("http"):
                # info_hash содержит URL, не формируем magnet из него
                magnet_url = None
            # Проверяем, что это hex строка длиной 40 символов (стандартный формат)
            elif len(info_hash_str) == 40 and all(c in '0123456789abcdefABCDEF' for c in info_hash_str):
                magnet_url = f"magnet:?xt=urn:btih:{info_hash_str}"
            elif len(info_hash_str) >= 32 and all(c in '0123456789abcdefABCDEF' for c in info_hash_str):
                # Если хеш короче 40 символов, все равно формируем magnet (может быть base32)
                magnet_url = f"magnet:?xt=urn:btih:{info_hash_str}"
            else:
                # Если info_hash не является валидным хешем (например, это текст или URL), не формируем magnet
                magnet_url = None
        
        # Если magnet-ссылка не найдена, но есть guid и indexerId, пытаемся получить через Prowlarr API
        if not magnet_url and guid:
            indexer_id = r.get("indexerId")
            if indexer_id:
                try:
                    api_magnet = await get_download_link(indexer_id, str(guid))
                    if api_magnet:
                        if api_magnet.startswith("magnet:"):
                            magnet_url = api_magnet
                        elif not download_url:
                            # Если получили не magnet, но это ссылка на скачивание, используем её как fallback
                            download_url = api_magnet
                except Exception:
                    # Тихая ошибка - просто продолжаем без magnet
                    pass
        
        release_data = {
            "title": r.get("title"),
            "quality": r.get("quality", {}).get("resolution") if isinstance(r.get("quality"), dict) else r.get("quality"),
            "size": r.get("size"),
            "seeders": r.get("seeders"),
            "tracker": r.get("indexer"),
            "magnet": magnet_url,
            "download_url": download_url,
            "tracker_id": tracker_id,
        }
        
        try:
            # Проверяем существование раздачи
            result = await db.execute(
                text("SELECT id FROM torrent_releases WHERE imdb_id = :imdb AND info_hash = :hash"),
                {"imdb": imdb_id, "hash": info_hash}
            )
            existing = result.fetchone()
            
            if existing:
                # Обновляем last_update для существующей раздачи
                await db.execute(
                    text("UPDATE torrent_releases SET last_update = :now WHERE id = :id"),
                    {"now": datetime.utcnow(), "id": existing[0]}
                )
                await db.commit()
                continue
            
            # Новая раздача - добавляем и отправляем уведомление
            # Сохраняем tracker_id для формирования ссылок на скачивание
            tracker_id_value = release_data.get("tracker_id")
            await db.execute(
                text("""INSERT INTO torrent_releases
                (imdb_id, title, info_hash, quality, size, seeders, tracker, published_at, last_update)
                VALUES (:imdb, :title, :hash, :quality, :size, :seeders, :tracker, :pub, :last_update)"""),
                {
                    "imdb": imdb_id,
                    "title": r.get("title"),
                    "hash": info_hash,
                    "quality": release_data["quality"],
                    "size": r.get("size"),
                    "seeders": r.get("seeders"),
                    "tracker": r.get("indexer"),
                    "pub": datetime.utcnow(),
                    "last_update": datetime.utcnow()
                }
            )
            await db.commit()
            
            # Отправляем уведомление асинхронно (не блокируем обработку)
            change_type = detect_change_type(release_data["title"], item_type)
            notification = format_new_release_notification(item_data, release_data, change_type)
            
            # Создаем задачу для отправки уведомления (не ждем завершения)
            asyncio.create_task(send_message(notification, poster_url))
            
            found_count += 1
            
        except Exception as e:
            await db.rollback()
            print(f"Error processing release: {e}")
    
    # Обновляем время последней проверки
    try:
        await db.execute(
            text("UPDATE imdb_watchlist SET last_checked = :now WHERE id = :id"),
            {"now": datetime.utcnow(), "id": item_id}
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"Error updating last_checked: {e}")
    
    return found_count

async def run() -> int:
    """
    Основная функция мониторинга.
    Обрабатывает все элементы watchlist параллельно.
    
    Returns:
        Общее количество найденных новых релизов
    """
    if not AsyncSessionLocal:
        print("Database not configured")
        return 0
    
            # Получаем список элементов в отдельной сессии
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                text("""SELECT id, imdb_id, title, original_title, type, poster_url, year, genre, rating, runtime, target_season, preferred_quality, preferred_audio
                        FROM imdb_watchlist WHERE enabled = true""")
            )
            items = result.fetchall()
        except Exception as e:
            print(f"Error fetching items: {e}")
            return 0
    
    if not items:
        return 0
    
    # Обрабатываем элементы параллельно (с ограничением concurrency)
    semaphore = asyncio.Semaphore(5)  # Максимум 5 параллельных запросов
    
    async def process_with_semaphore(item):
        """Обработка элемента с собственной сессией БД"""
        async with semaphore:
            # Создаем отдельную сессию для каждого элемента
            async with AsyncSessionLocal() as item_db:
                try:
                    return await process_item(
                        item_db,
                        item[0],  # id
                        item[1],  # imdb_id
                        item[2],  # title
                        item[3],  # original_title
                        item[4],  # type
                        item[5],  # poster_url
                        item[6],  # year
                        item[7],  # genre
                        item[8],  # rating
                        item[9],  # runtime
                        item[10],  # target_season
                        item[11],  # preferred_quality
                        item[12],  # preferred_audio
                    )
                except Exception as e:
                    print(f"Error processing item {item[0]}: {e}")
                    return 0
    
    # Запускаем параллельную обработку
    try:
        tasks = [process_with_semaphore(item) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Подсчитываем успешно найденные релизы
        found_count = 0
        for result in results:
            if isinstance(result, Exception):
                print(f"Error processing item: {result}")
            else:
                found_count += result
        
        return found_count
    except Exception as e:
        print(f"Watcher error: {e}")
        return 0

def filter_results_by_imdb_or_title(
    results: List[Dict[str, Any]],
    imdb_id: str,
    title: str,
    original_title: str
) -> List[Dict[str, Any]]:
    """
    Фильтрует результаты поиска по соответствию IMDb ID или названию.
    Убирает результаты, которые явно не соответствуют искомому фильму/сериалу.
    
    Args:
        results: Список результатов от Prowlarr
        imdb_id: IMDb ID искомого фильма/сериала
        title: Локализованное название
        original_title: Оригинальное название
    
    Returns:
        Отфильтрованный список результатов
    """
    if not results:
        return results
    
    filtered = []
    title_lower = (title or "").lower().strip()
    original_title_lower = (original_title or "").lower().strip()
    
    # Нормализуем названия - убираем лишние символы и слова
    def normalize_title(t: str) -> str:
        # Убираем артикли и служебные слова
        stop_words = {'the', 'a', 'an', 'и', 'в', 'на', 'с', 'для'}
        words = [w for w in t.split() if w.lower() not in stop_words and len(w) > 1]
        return ' '.join(words)
    
    normalized_title = normalize_title(title_lower) if title_lower else ""
    normalized_original = normalize_title(original_title_lower) if original_title_lower else ""
    
    # Извлекаем ключевые слова из названий для сравнения (только значимые слова >=3 символов)
    title_words = set(word for word in normalized_title.split() if len(word) >= 3)
    original_words = set(word for word in normalized_original.split() if len(word) >= 3)
    all_keywords = title_words.union(original_words)
    
    # Если нет ключевых слов, пропускаем фильтрацию
    if not all_keywords:
        return results
    
    for r in results:
        release_title = (r.get("title") or "").lower()
        release_imdb = r.get("imdbId") or r.get("imdb_id") or ""
        
        # Проверка по IMDb ID (наиболее точная)
        if release_imdb and imdb_id:
            if release_imdb.lower().strip() == imdb_id.lower().strip():
                filtered.append(r)
                continue
        
        # Проверка по названию - должны совпадать ключевые слова
        release_normalized = normalize_title(release_title)
        
        # Подсчитываем совпадения ключевых слов
        matches = sum(1 for word in all_keywords if word in release_normalized)
        
        # Проверяем совпадение по основным словам
        # Если совпадает хотя бы 50% ключевых слов или есть совпадение длинных слов (>=5 символов)
        min_matches = max(2, len(all_keywords) // 2)  # Минимум 2 или половина ключевых слов
        long_word_match = any(len(word) >= 5 and word in release_normalized for word in all_keywords)
        
        if matches >= min_matches or long_word_match:
            filtered.append(r)
        else:
            print(f"Filtered out release (no match): '{r.get('title')}' (searching for: {title or original_title}, matches: {matches}/{len(all_keywords)})")
    
    return filtered

def filter_releases_by_preferences(
    results: List[Dict[str, Any]], 
    preferred_quality: Optional[str] = None,
    preferred_audio: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Фильтрует результаты поиска по предпочтениям качества и озвучки.
    
    Args:
        results: Список результатов от Prowlarr
        preferred_quality: Предпочтительное качество (например: "1080p", "2160p", "UHD", "4K")
        preferred_audio: Предпочтительная озвучка (например: "русская", "русский", "dub", "озвучка")
    
    Returns:
        Отфильтрованный список результатов
    """
    if not preferred_quality and not preferred_audio:
        return results
    
    filtered = []
    
    for r in results:
        title = (r.get("title") or "").lower()
        quality = r.get("quality", {})
        if isinstance(quality, dict):
            quality_str = str(quality.get("resolution", "")).lower()
        else:
            quality_str = str(quality).lower()
        
        # Проверка качества (поддержка нескольких вариантов через запятую)
        quality_match = True
        if preferred_quality:
            # Разбиваем строку на отдельные качества (поддерживаем запятую как разделитель)
            quality_list = [q.strip().lower() for q in preferred_quality.split(',') if q.strip()]
            
            # Нормализуем варианты качества
            quality_variants = {
                "1080p": ["1080p", "1080", "full hd", "fhd"],
                "2160p": ["2160p", "2160", "4k", "uhd", "ultra hd"],
                "720p": ["720p", "720", "hd"],
                "480p": ["480p", "480", "sd"],
            }
            
            # Проверяем соответствие любому из указанных качеств
            quality_match = False
            for quality_pref in quality_list:
                # Проверяем через варианты качества
                for variant_key, variants in quality_variants.items():
                    if quality_pref in variant_key.lower() or variant_key.lower() in quality_pref:
                        # Проверяем все варианты этого качества
                        for variant in variants:
                            if variant in quality_str or variant in title:
                                quality_match = True
                                break
                        if quality_match:
                            break
                
                # Если не нашли через варианты, проверяем прямое вхождение
                if not quality_match:
                    quality_match = (
                        quality_pref in quality_str or 
                        quality_pref in title
                    )
                
                # Если нашли соответствие хотя бы одному качеству, выходим
                if quality_match:
                    break
        
        # Проверка озвучки
        audio_match = True
        if preferred_audio:
            audio_lower = preferred_audio.lower()
            # Ключевые слова для русской озвучки
            russian_keywords = ["русск", "russian", "dub", "дубляж", "озвучка", "озвучен", "russkij"]
            original_keywords = ["оригинал", "original", "eng", "english", "sub", "субтитр"]
            
            audio_match = False
            
            # Если запрошена русская озвучка
            if any(kw in audio_lower for kw in ["русск", "dub", "дубляж", "озвучка"]):
                audio_match = any(kw in title for kw in russian_keywords)
            # Если запрошен оригинал
            elif any(kw in audio_lower for kw in ["оригинал", "original", "eng"]):
                audio_match = any(kw in title for kw in original_keywords) or not any(kw in title for kw in russian_keywords)
            else:
                # Общий поиск по ключевому слову
                audio_match = audio_lower in title
        
        # Добавляем результат только если соответствует обоим критериям
        if quality_match and audio_match:
            filtered.append(r)
    
    return filtered

def detect_change_type(release_title: str, item_type: str) -> str:
    """Определяет тип изменения релиза"""
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

async def run_search() -> int:
    """Асинхронная обертка для запуска поиска"""
    return await run()
