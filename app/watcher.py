"""
Асинхронный модуль мониторинга новых релизов.
Оптимизирован для параллельной обработки и предотвращения утечек памяти.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal
from app.prowlarr_client import search_by_query, search_by_imdb, get_download_link, get_client
from app.notifier import send_message, format_new_release_notification, send_error_notification
from app.season_parser import extract_season_from_title
from app.logger import get_logger
from app.retry import retry
from datetime import datetime
from typing import List, Dict, Any, Optional
import asyncio
import re
import hashlib
import bencode
import urllib.parse

logger = get_logger(__name__)

async def torrent_to_magnet(torrent_url: str) -> Optional[str]:
    """
    Скачать torrent файл по URL и конвертировать его в magnet-ссылку.
    
    Args:
        torrent_url: URL для скачивания torrent файла
    
    Returns:
        Magnet-ссылка или None в случае ошибки
    """
    try:
        client = await get_client()
        # Скачиваем torrent файл
        response = await client.get(torrent_url)
        response.raise_for_status()
        
        # Парсим torrent файл
        torrent_data = bencode.bdecode(response.content)
        
        # Извлекаем секцию "info" и вычисляем SHA1 хеш
        info = torrent_data.get(b'info')
        if not info:
            return None
        
        # Кодируем секцию info обратно в bencode и вычисляем SHA1
        info_encoded = bencode.bencode(info)
        info_hash = hashlib.sha1(info_encoded).digest()
        
        # Конвертируем в hex строку (40 символов)
        info_hash_hex = info_hash.hex()
        
        # Формируем magnet-ссылку
        magnet_url = f"magnet:?xt=urn:btih:{info_hash_hex}"
        
        # Опционально добавляем имя файла/торрента, если оно есть
        if b'name' in info:
            name = info[b'name']
            if isinstance(name, bytes):
                try:
                    name_str = name.decode('utf-8')
                    magnet_url += f"&dn={urllib.parse.quote(name_str)}"
                except UnicodeDecodeError:
                    pass
        
        return magnet_url
        
    except Exception:
        # Тихая ошибка - возвращаем None
        return None

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
    min_releases_count: Optional[int] = None,
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
    
    # Добавляем год к поисковому запросу для более точного поиска
    if year:
        search_query = f"{search_query} {year}"
    
    # Для сериалов добавляем номер сезона в поисковый запрос, если указан
    if item_type == "tv" and target_season:
        # Добавляем номер сезона в разных форматах для лучшего поиска
        season_formats = [
            f"{search_query} S{target_season:02d}",  # "Stranger Things 2016 S04"
            f"{search_query} Season {target_season}",  # "Stranger Things 2016 Season 4"
            f"{search_query} {target_season}",  # "Stranger Things 2016 4"
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
        imdb_results = await search_by_imdb(imdb_id)
        
        # Проверяем, действительно ли результаты соответствуют IMDb ID
        # Если индексер не поддерживает IMDb ID, все результаты будут иметь imdbId: 0
        # или не совпадать с запрашиваемым IMDb ID
        if imdb_results:
            # Проверяем, есть ли хотя бы один результат с правильным IMDb ID
            has_valid_imdb_match = any(
                str(r.get("imdbId", "")).lower().strip() == imdb_id.lower().strip() 
                for r in imdb_results
            )
            
            if has_valid_imdb_match:
                # Есть результаты с правильным IMDb ID - используем их
                results = imdb_results
            else:
                # Все результаты имеют imdbId: 0 или не совпадают - индексер не поддерживает IMDb ID
                logger.info(f"Indexer doesn't support IMDb ID search (all results have imdbId: 0), trying search by query: {search_query}")
                results = await search_by_query(search_query)
        else:
            # Если поиск по IMDb не дал результатов, ищем по названию
            logger.info(f"No results by IMDb {imdb_id}, trying search by query: {search_query}")
            results = await search_by_query(search_query)
    except Exception as e:
        # Если поиск по IMDb не поддерживается или ошибка, ищем по названию
        logger.warning(f"IMDb search failed, trying query search: {e}", exc_info=True)
        try:
            results = await search_by_query(search_query)
        except Exception as e2:
            logger.error(f"Search error for {search_query}: {e2}", exc_info=True)
            return 0
    
    # Фильтруем результаты по соответствию IMDb ID или названию
    results = filter_results_by_imdb_or_title(results, imdb_id, title, original_title)
    
    # Фильтруем результаты по качеству и озвучке, если указаны предпочтения
    filtered_results = filter_releases_by_preferences(results, preferred_quality, preferred_audio)
    
    # Проверяем минимальное количество раздач перед отправкой уведомлений
    if min_releases_count and min_releases_count > 0:
        # Подсчитываем количество уникальных раздач
        existing_count_result = await db.execute(
            text("SELECT COUNT(*) FROM torrent_releases WHERE imdb_id = :imdb"),
            {"imdb": imdb_id}
        )
        existing_count = existing_count_result.scalar() or 0
        
        # Если текущее количество раздач меньше минимального, не отправляем уведомления
        if existing_count + len(filtered_results) < min_releases_count:
            logger.info(
                f"Item {item_id} ({imdb_id}): Found {len(filtered_results)} releases, "
                f"but min_releases_count is {min_releases_count} (current: {existing_count}). "
                f"Skipping notifications."
            )
            # Все равно сохраняем релизы в БД, но не отправляем уведомления
            should_notify = False
        else:
            should_notify = True
            logger.info(
                f"Item {item_id} ({imdb_id}): Found {len(filtered_results)} releases, "
                f"total will be {existing_count + len(filtered_results)} >= {min_releases_count}. "
                f"Sending notifications."
            )
    else:
        should_notify = True
    
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
        
        # Используем downloadUrl из ответа Prowlarr, если он есть (это уже готовая ссылка)
        download_url_from_api = r.get("downloadUrl")
        if download_url_from_api and download_url_from_api.startswith("http"):
            # Если downloadUrl уже есть в ответе, используем его (приоритет над формированием вручную)
            download_url = download_url_from_api
        
        # Формируем magnet-link из различных источников
        magnet_url = (
            r.get("magnetUrl") or 
            r.get("magnet") or 
            r.get("magnetLink")
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
        
        # Если magnet-ссылка все еще не найдена, но есть downloadUrl (torrent файл), конвертируем его в magnet
        if not magnet_url and download_url and download_url.startswith("http"):
            try:
                # Пытаемся конвертировать torrent файл в magnet-ссылку
                converted_magnet = await torrent_to_magnet(download_url)
                if converted_magnet:
                    magnet_url = converted_magnet
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
            
            # Отправляем уведомление только если разрешено
            if should_notify:
                # Отправляем уведомление асинхронно (не блокируем обработку)
                change_type = detect_change_type(release_data["title"], item_type)
                notification = format_new_release_notification(item_data, release_data, change_type)
                
                # Создаем задачу для отправки уведомления (не ждем завершения)
                asyncio.create_task(send_message(notification, poster_url, imdb_id=imdb_id))
            
            found_count += 1
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error processing release: {e}", exc_info=True)
    
    # Обновляем время последней проверки
    try:
        await db.execute(
            text("UPDATE imdb_watchlist SET last_checked = :now WHERE id = :id"),
            {"now": datetime.utcnow(), "id": item_id}
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating last_checked: {e}", exc_info=True)
    
    return found_count

async def run() -> int:
    """
    Основная функция мониторинга.
    Обрабатывает все элементы watchlist параллельно.
    
    Returns:
        Общее количество найденных новых релизов
    """
    if not AsyncSessionLocal:
        logger.error("Database not configured")
        return 0
    
    # Получаем список элементов в отдельной сессии
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                text("""SELECT id, imdb_id, title, original_title, type, poster_url, year, genre, rating, runtime, target_season, preferred_quality, preferred_audio, min_releases_count, check_interval
                        FROM imdb_watchlist WHERE enabled = true""")
            )
            items = result.fetchall()
        except Exception as e:
            logger.error(f"Error fetching items: {e}", exc_info=True)
            await send_error_notification(
                "Database Error",
                f"Ошибка при получении списка элементов: {str(e)}",
                {"function": "run"}
            )
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
                        item[13],  # min_releases_count
                    )
                except Exception as e:
                    logger.error(f"Error processing item {item[0]}: {e}", exc_info=True)
                    return 0
    
    # Запускаем параллельную обработку
    try:
        tasks = [process_with_semaphore(item) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Подсчитываем успешно найденные релизы
        found_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error processing item: {result}", exc_info=True)
            else:
                found_count += result
        
        logger.info(f"Watcher completed. Found {found_count} new releases")
        return found_count
    except Exception as e:
        logger.error(f"Watcher error: {e}", exc_info=True)
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
    
    # Слова, которые не должны использоваться как ключевые (слишком общие)
    common_words = {
        'the', 'a', 'an', 'и', 'в', 'на', 'с', 'для', 'of', 'to', 'in', 'on', 'at',
        'rip', 'web', 'bd', 'dvd', 'hd', 'uhd', '4k', '1080p', '720p', '2160p',
        'h264', 'h265', 'hevc', 'x264', 'x265', 'av1', 'raw', 'rus', 'eng', 'multi',
        'season', 'seasons', 'episode', 'episodes', 'сезон', 'сезоны', 'эп', 'эпизод',
        'movie', 'tv', 'ova', 'mv', 'фильм', 'сериал', 'webrip', 'web-dl', 'bdrip',
        'remux', 'bluray', 'blu-ray', 'dvdrip', 'uhdtv', 'uhd', 'sdr', 'hdr', 'hdr10',
        'dolby', 'vision', 'profile', 'bit', '10-bit', '8-bit'
    }
    
    # Нормализуем названия - убираем лишние символы и слова
    def normalize_title(t: str) -> str:
        # Убираем артикли, служебные слова и технические термины
        words = [w for w in t.split() if w.lower() not in common_words and len(w) > 1]
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
    
    # Для коротких названий (1-2 слова) требуем более строгое совпадение
    is_short_title = len(all_keywords) <= 2
    
    for r in results:
        release_title = (r.get("title") or "").lower()
        release_imdb = r.get("imdbId") or r.get("imdb_id") or ""
        
        # Проверка по IMDb ID (наиболее точная)
        if release_imdb and imdb_id:
            release_imdb_str = str(release_imdb).strip()
            imdb_id_str = str(imdb_id).strip()
            # Проверяем, что imdbId не равен 0 и совпадает с запрашиваемым
            if release_imdb_str and release_imdb_str != "0" and release_imdb_str.lower() == imdb_id_str.lower():
                filtered.append(r)
                continue
        
        # Проверка по названию - должны совпадать ключевые слова
        release_normalized = normalize_title(release_title)
        
        # Подсчитываем совпадения ключевых слов
        matches = sum(1 for word in all_keywords if word in release_normalized)
        
        # Для коротких названий требуем совпадение всех или почти всех ключевых слов
        if is_short_title:
            # Для коротких названий (например, "The Rip") требуем совпадение всех ключевых слов
            if matches >= len(all_keywords):
                filtered.append(r)
        else:
            # Для длинных названий требуем совпадение хотя бы 50% ключевых слов или длинных слов (>=5 символов)
            min_matches = max(2, len(all_keywords) // 2)  # Минимум 2 или половина ключевых слов
            long_word_match = any(len(word) >= 5 and word in release_normalized for word in all_keywords)
            
            if matches >= min_matches or long_word_match:
                filtered.append(r)
    
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
