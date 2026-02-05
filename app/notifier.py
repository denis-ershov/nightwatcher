"""
Асинхронный модуль для отправки уведомлений в Telegram через aiogram 3.24.0.
Оптимизирован для предотвращения утечек памяти.
"""
from aiogram import Bot
from aiogram.types import BufferedInputFile, URLInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from app.config import TG_TOKEN, TG_CHAT_ID
from app.logger import get_logger
from app.retry import retry
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal
import httpx
from typing import Optional
import asyncio
from datetime import datetime

logger = get_logger(__name__)

# Глобальный экземпляр бота
_bot: Bot | None = None

def get_bot() -> Bot:
    """Получить или создать экземпляр бота"""
    global _bot
    if not TG_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not configured")
    
    if _bot is None:
        _bot = Bot(token=TG_TOKEN)
    return _bot

async def close_bot():
    """Закрыть сессию бота при завершении приложения"""
    global _bot
    if _bot:
        await _bot.session.close()
        _bot = None

@retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(TelegramNetworkError,))
async def send_message(text: str, photo_url: Optional[str] = None, retries: int = 3, imdb_id: Optional[str] = None) -> bool:
    """
    Отправить сообщение в Telegram через aiogram.
    
    Args:
        text: Текст сообщения (HTML форматирование)
        photo_url: URL изображения (опционально)
        retries: Количество попыток при ошибке
    
    Returns:
        True если сообщение отправлено успешно, False иначе
    """
    if not TG_TOKEN or not TG_CHAT_ID:
        logger.warning(f"Telegram not configured. Message: {text[:100]}...")
        return False
    
    bot = get_bot()
    
    # Преобразуем chat_id в int, если это числовой ID
    try:
        chat_id = int(TG_CHAT_ID) if TG_CHAT_ID.lstrip('-').isdigit() else TG_CHAT_ID
    except (ValueError, AttributeError):
        chat_id = TG_CHAT_ID
    
    for attempt in range(retries):
        try:
            if photo_url:
                # Отправка с фото
                try:
                    # Вариант 1: Используем URL напрямую (предпочтительно)
                    try:
                        photo_file = URLInputFile(photo_url)
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_file,
                            caption=text,
                            parse_mode="HTML"
                        )
                    except Exception:
                        # Вариант 2: Скачиваем и отправляем как BufferedInputFile
                        async with httpx.AsyncClient() as client:
                            photo_response = await client.get(photo_url, timeout=10.0)
                            photo_response.raise_for_status()
                            photo_data = photo_response.content
                        
                        # Создаем BufferedInputFile из байтов
                        photo_file = BufferedInputFile(
                            file=photo_data,
                            filename="poster.jpg"
                        )
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_file,
                            caption=text,
                            parse_mode="HTML"
                        )
                except (httpx.HTTPError, TelegramBadRequest) as e:
                    # Если не удалось отправить с фото, отправляем только текст
                    error_msg = str(e)
                    if "chat not found" in error_msg.lower():
                        logger.error(f"Telegram error: Chat ID '{chat_id}' not found. Please check TELEGRAM_CHAT_ID in .env file.")
                        logger.error("Make sure the bot has been started and you've sent a message to it first.")
                        return False
                    logger.warning(f"Failed to send photo, trying text only: {error_msg}")
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=text,
                            parse_mode="HTML",
                            disable_web_page_preview=False
                        )
                    except TelegramBadRequest as e2:
                        if "chat not found" in str(e2).lower():
                            logger.error(f"Telegram error: Chat ID '{chat_id}' not found. Please check TELEGRAM_CHAT_ID in .env file.")
                            return False
                        raise
            else:
                # Отправка только текста
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=False
                )
            
            # Сохраняем в историю уведомлений
            if imdb_id:
                try:
                    async with AsyncSessionLocal() as db:
                        await db.execute(
                            text("""
                                INSERT INTO notifications_history (imdb_id, notification_text, sent_at, success)
                                VALUES (:imdb_id, :text, NOW(), TRUE)
                            """),
                            {"imdb_id": imdb_id, "text": text[:1000]}  # Ограничиваем длину
                        )
                        await db.commit()
                except Exception as e:
                    logger.warning(f"Failed to save notification history: {e}")
            
            return True
            
        except TelegramBadRequest as e:
            error_msg = str(e)
            if "chat not found" in error_msg.lower():
                logger.error(f"Telegram error: Chat ID '{chat_id}' not found. Please check TELEGRAM_CHAT_ID in .env file.")
                logger.error("Make sure the bot has been started and you've sent a message to it first.")
                return False
            logger.error(f"Telegram Bad Request: {error_msg}")
            return False
        except TelegramNetworkError as e:
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            logger.error(f"Failed to send Telegram message after {retries} attempts: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}", exc_info=True)
            return False
    
    return False

def format_new_release_notification(item: dict, release: dict, change_type: str = "new_release") -> str:
    """
    Форматирует уведомление о новом релизе в HTML для Telegram.
    
    Args:
        item: Данные о фильме/сериале из watchlist
        release: Данные о релизе
        change_type: Тип изменения (new_release, new_dub, new_episode)
    
    Returns:
        Отформатированная строка HTML
    """
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
    
    # Добавляем magnet-ссылку (приоритет)
    magnet = release.get('magnet')
    download_url = release.get('download_url')
    
    # Приоритет: magnet-ссылка, затем ссылка на скачивание с трекера
    if magnet:
        # HTML ссылка на magnet
        magnet_link_html = f'<a href="{magnet}">🧲 Magnet Link</a>'
        info += f'\n{magnet_link_html}\n'
    elif download_url:
        # Fallback: ссылка на скачивание с трекера, если нет magnet
        info += f'\n📥 <a href="{download_url}">Скачать с трекера</a>\n'
    
    return header + info

async def send_error_notification(error_type: str, error_message: str, context: Optional[dict] = None) -> bool:
    """
    Отправить уведомление об ошибке в Telegram.
    
    Args:
        error_type: Тип ошибки (например, "Database Error", "API Error", "Watcher Error")
        error_message: Сообщение об ошибке
        context: Дополнительный контекст (опционально)
    
    Returns:
        True если сообщение отправлено успешно, False иначе
    """
    if not TG_TOKEN or not TG_CHAT_ID:
        logger.warning(f"Telegram not configured. Error notification skipped: {error_type}")
        return False
    
    error_text = f"🚨 <b>Ошибка NightWatcher</b>\n\n"
    error_text += f"<b>Тип:</b> {error_type}\n"
    error_text += f"<b>Сообщение:</b> {error_message}\n"
    
    if context:
        error_text += "\n<b>Контекст:</b>\n"
        for key, value in context.items():
            error_text += f"• {key}: {value}\n"
    
    error_text += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    return await send_message(error_text, imdb_id=None)
