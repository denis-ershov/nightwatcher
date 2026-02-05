"""
Асинхронный FastAPI приложение.
Оптимизировано для производительности и предотвращения утечек памяти.
"""
import os
import json
import csv
import io
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Query, Body
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db, close_db, AsyncSessionLocal
from app.config import ADMIN_PASSWORD, SESSION_SECRET
from app.metadata import fetch_metadata
from app.watcher import run_search
from app.prowlarr_client import close_client
from app.notifier import close_bot
from app.season_parser import extract_season_from_title, clean_title_from_season
from app.validators import AddItemRequest, EditItemRequest, SearchRequest, ReleaseFilterRequest
from app.stats import get_statistics, get_item_statistics
from app.logger import get_logger, setup_logging
from app.cache import get_cache
import re
from typing import List, Optional
from datetime import datetime

logger = get_logger(__name__)

# Инициализация rate limiter
limiter = Limiter(key_func=get_remote_address)

# Lifecycle events для управления ресурсами
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    yield
    # Shutdown - закрываем все соединения
    await close_db()
    await close_client()
    await close_bot()

app = FastAPI(
    title="NightWatcher",
    description="Приложение для мониторинга торрентов через Prowlarr API",
    version="2.0.0",
    lifespan=lifespan
)

# Добавляем rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware, 
    secret_key=SESSION_SECRET,
    session_cookie="nightwatcher_session",
    max_age=86400,
    same_site="lax",
    https_only=os.getenv("HTTPS_ONLY", "false").lower() == "true"  # В продакшене должно быть True
)

# Пути к шаблонам и статическим файлам
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
template_dir = os.path.join(BASE_DIR, "app", "templates")
static_dir = os.path.join(BASE_DIR, "app", "static")

templates = Jinja2Templates(directory=template_dir)

os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Favicon routes (для обратной совместимости с корневыми путями)
@app.get("/favicon.ico")
async def favicon_ico():
    """Favicon ICO"""
    return FileResponse(os.path.join(static_dir, "favicon.ico"))

@app.get("/favicon.svg")
async def favicon_svg():
    """Favicon SVG"""
    return FileResponse(os.path.join(static_dir, "favicon.svg"))

@app.get("/favicon-96x96.png")
async def favicon_png():
    """Favicon PNG"""
    return FileResponse(os.path.join(static_dir, "favicon-96x96.png"))

@app.get("/apple-touch-icon.png")
async def apple_touch_icon():
    """Apple Touch Icon"""
    return FileResponse(os.path.join(static_dir, "apple-touch-icon.png"))

@app.get("/site.webmanifest")
async def site_webmanifest():
    """Web Manifest"""
    return FileResponse(os.path.join(static_dir, "site.webmanifest"))

@app.get("/web-app-manifest-192x192.png")
async def web_app_manifest_192():
    """Web App Manifest Icon 192x192"""
    return FileResponse(os.path.join(static_dir, "web-app-manifest-192x192.png"))

@app.get("/web-app-manifest-512x512.png")
async def web_app_manifest_512():
    """Web App Manifest Icon 512x512"""
    return FileResponse(os.path.join(static_dir, "web-app-manifest-512x512.png"))

def require_auth(request: Request):
    """Проверка аутентификации"""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True

@app.get("/login")
async def login_page(request: Request):
    """Страница входа"""
    if request.session.get("authenticated"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    """Обработка входа"""
    if password == ADMIN_PASSWORD:
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

@app.get("/logout")
async def logout(request: Request):
    """Выход из системы"""
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@app.get("/")
@limiter.limit("30/minute")
async def index(
    request: Request, 
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    type_filter: Optional[str] = Query(None),
    enabled_filter: Optional[bool] = Query(None),
    year_filter: Optional[int] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc")
):
    """Главная страница со списком watchlist с пагинацией и фильтрацией"""
    if not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)
    
    # Построение WHERE условий для фильтров
    where_conditions = ["1=1"]
    params = {}
    
    if search:
        where_conditions.append("(title ILIKE :search OR original_title ILIKE :search OR imdb_id ILIKE :search)")
        params["search"] = f"%{search}%"
    
    if type_filter and type_filter != "all":
        where_conditions.append("type = :type_filter")
        params["type_filter"] = type_filter
    
    if enabled_filter is not None:
        where_conditions.append("enabled = :enabled_filter")
        params["enabled_filter"] = enabled_filter
    
    if year_filter:
        where_conditions.append("year = :year_filter")
        params["year_filter"] = str(year_filter)
    
    where_clause = " AND ".join(where_conditions)
    
    # Получаем общее количество для пагинации (отдельный запрос)
    count_query = f"SELECT COUNT(*) FROM imdb_watchlist WHERE {where_clause}"
    count_result = await db.execute(text(count_query), params)
    total_count = count_result.scalar() or 0
    
    # Сортировка
    valid_sort_fields = ["created_at", "title", "year", "last_checked"]
    if sort_by not in valid_sort_fields:
        sort_by = "created_at"
    sort_order = "DESC" if sort_order.lower() == "desc" else "ASC"
    
    # Основной запрос с данными
    offset = (page - 1) * per_page
    query = f"""
        SELECT id, imdb_id, title, original_title, type, enabled, created_at, updated_at, poster_url, year, genre, plot, rating, runtime, last_checked, total_seasons, target_season, preferred_quality, preferred_audio, min_releases_count, check_interval
        FROM imdb_watchlist 
        WHERE {where_clause}
        ORDER BY {sort_by} {sort_order}
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = per_page
    params["offset"] = offset
    
    result = await db.execute(text(query), params)
    items = result.fetchall()
    
    items_list = []
    for item in items:
        # Получаем количество релизов для каждого элемента
        releases_count_result = await db.execute(
            text("SELECT COUNT(*) FROM torrent_releases WHERE imdb_id = :imdb_id"),
            {"imdb_id": item[1]}
        )
        releases_count = releases_count_result.scalar() or 0
        
        items_list.append({
            "id": item[0],
            "imdb_id": item[1],
            "title": item[2],
            "original_title": item[3],
            "type": item[4],
            "enabled": item[5],
            "created_at": item[6],
            "updated_at": item[7],
            "poster_url": item[8],
            "year": item[9],
            "genre": item[10],
            "plot": item[11],
            "rating": item[12],
            "runtime": item[13],
            "last_checked": item[14],
            "total_seasons": item[15],
            "target_season": item[16],
            "preferred_quality": item[17],
            "preferred_audio": item[18],
            "min_releases_count": item[19],
            "check_interval": item[20],
            "releases_count": releases_count,
        })
    
    # Вычисляем пагинацию
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "items": items_list,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        },
        "filters": {
            "search": search,
            "type_filter": type_filter,
            "enabled_filter": enabled_filter,
            "year_filter": year_filter,
            "sort_by": sort_by,
            "sort_order": sort_order
        }
    })

@app.post("/add")
async def add(request: Request, imdb_id: str = Form(...), db: AsyncSession = Depends(get_db)):
    """Добавить новый элемент в watchlist"""
    if not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)
    
    # Парсим IMDb ID и возможное указание сезона из строки
    input_str = imdb_id.strip()
    
    # Извлекаем IMDb ID (формат: tt1234567 или tt1234567 название сезон)
    imdb_match = re.search(r'(tt\d+)', input_str)
    if not imdb_match:
        raise HTTPException(status_code=400, detail="Invalid IMDb ID format")
    
    actual_imdb_id = imdb_match.group(1)
    
    # Извлекаем номер сезона из всей строки, если указан
    season_from_input = extract_season_from_title(input_str)
    
    movie_info = await fetch_metadata(actual_imdb_id)
    
    # Используем сезон из входной строки или из названия
    title = movie_info.get("title") or actual_imdb_id
    target_season = season_from_input or extract_season_from_title(title)
    
    # Очищаем название от указания сезона для сохранения в БД
    if target_season:
        title = clean_title_from_season(title)
        original_title = clean_title_from_season(movie_info.get("original_title") or title)
    else:
        original_title = movie_info.get("original_title")
    
    try:
        await db.execute(
            text("""
                INSERT INTO imdb_watchlist (imdb_id, title, original_title, type, poster_url, year, genre, plot, rating, runtime, total_seasons, target_season)
                VALUES (:imdb_id, :title, :original_title, :type, :poster_url, :year, :genre, :plot, :rating, :runtime, :total_seasons, :target_season)
                ON CONFLICT (imdb_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    original_title = EXCLUDED.original_title,
                    poster_url = EXCLUDED.poster_url,
                    year = EXCLUDED.year,
                    genre = EXCLUDED.genre,
                    plot = EXCLUDED.plot,
                    rating = EXCLUDED.rating,
                    runtime = EXCLUDED.runtime,
                    total_seasons = EXCLUDED.total_seasons,
                    target_season = COALESCE(EXCLUDED.target_season, imdb_watchlist.target_season),
                    updated_at = now()
            """),
            {
                "imdb_id": actual_imdb_id,
                "title": title,
                "original_title": original_title,
                "type": movie_info.get("type", "movie"),
                "poster_url": movie_info.get("poster_url"),
                "year": movie_info.get("year"),
                "genre": movie_info.get("genre"),
                "plot": movie_info.get("plot"),
                "rating": movie_info.get("rating"),
                "runtime": movie_info.get("runtime"),
                "total_seasons": movie_info.get("total_seasons"),
                "target_season": target_season,
            }
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    
    return RedirectResponse("/", status_code=303)

@app.post("/delete/{item_id}")
async def delete_item(request: Request, item_id: int, db: AsyncSession = Depends(get_db)):
    """Удалить элемент из watchlist"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        await db.execute(text("DELETE FROM imdb_watchlist WHERE id = :id"), {"id": item_id})
        await db.commit()
    except Exception as e:
        await db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)
    
    return JSONResponse({"success": True})

@app.post("/toggle/{item_id}")
async def toggle_item(request: Request, item_id: int, db: AsyncSession = Depends(get_db)):
    """Включить/выключить отслеживание элемента"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        await db.execute(text("UPDATE imdb_watchlist SET enabled = NOT enabled WHERE id = :id"), {"id": item_id})
        await db.commit()
    except Exception as e:
        await db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)
    
    return JSONResponse({"success": True})

@app.post("/edit/{item_id}")
async def edit_item(
    request: Request, 
    item_id: int, 
    title: str = Form(...), 
    type: str = Form(...),
    target_season: str = Form(None),
    preferred_quality: str = Form(None),
    preferred_audio: str = Form(None),
    min_releases_count: str = Form(None),
    check_interval: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Редактировать элемент watchlist"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Парсим сезон из названия или используем переданное значение
    season_from_title = extract_season_from_title(title)
    season_value = None
    
    if target_season and target_season.strip():
        try:
            season_value = int(target_season.strip())
        except ValueError:
            pass
    
    if season_value is None and season_from_title:
        season_value = season_from_title
        title = clean_title_from_season(title)
    
    # Обрабатываем предпочтения качества и озвучки
    quality_value = preferred_quality.strip() if preferred_quality and preferred_quality.strip() else None
    audio_value = preferred_audio.strip() if preferred_audio and preferred_audio.strip() else None
    
    # Обрабатываем минимальное количество раздач
    min_releases_value = None
    if min_releases_count and min_releases_count.strip():
        try:
            min_releases_value = int(min_releases_count.strip())
        except ValueError:
            pass
    
    # Обрабатываем интервал проверки (в минутах)
    check_interval_value = None
    if check_interval and check_interval.strip():
        try:
            check_interval_value = int(check_interval.strip())
            if check_interval_value < 1:
                check_interval_value = None
        except ValueError:
            pass
    
    try:
        await db.execute(
            text("""UPDATE imdb_watchlist 
                    SET title = :title, type = :type, target_season = :target_season, 
                        preferred_quality = :preferred_quality, preferred_audio = :preferred_audio, 
                        min_releases_count = :min_releases_count, check_interval = :check_interval, updated_at = now() 
                    WHERE id = :id"""),
            {
                "id": item_id, 
                "title": title, 
                "type": type, 
                "target_season": season_value,
                "preferred_quality": quality_value,
                "preferred_audio": audio_value,
                "min_releases_count": min_releases_value,
                "check_interval": check_interval_value
            }
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)
    
    return RedirectResponse("/", status_code=303)

@app.post("/refresh/{item_id}")
async def refresh_item(request: Request, item_id: int, db: AsyncSession = Depends(get_db)):
    """Обновить метаданные элемента"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        result = await db.execute(text("SELECT imdb_id FROM imdb_watchlist WHERE id = :id"), {"id": item_id})
        row = result.fetchone()
        
        if row:
            imdb_id = row[0]
            movie_info = await fetch_metadata(imdb_id)
            if movie_info:
                await db.execute(
                    text("""
                        UPDATE imdb_watchlist SET
                            title = :title,
                            original_title = :original_title,
                            poster_url = :poster_url,
                            year = :year,
                            genre = :genre,
                            plot = :plot,
                            rating = :rating,
                            runtime = :runtime,
                            total_seasons = :total_seasons,
                            updated_at = now()
                        WHERE id = :id
                    """),
                    {
                        "id": item_id,
                        "title": movie_info.get("title"),
                        "original_title": movie_info.get("original_title"),
                        "poster_url": movie_info.get("poster_url"),
                        "year": movie_info.get("year"),
                        "genre": movie_info.get("genre"),
                        "plot": movie_info.get("plot"),
                        "rating": movie_info.get("rating"),
                        "runtime": movie_info.get("runtime"),
                        "total_seasons": movie_info.get("total_seasons"),
                    }
                )
                await db.commit()
    except Exception as e:
        await db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)
    
    return JSONResponse({"success": True})

@app.post("/search")
async def manual_search(request: Request):
    """Запустить поиск релизов вручную"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        results = await run_search()
        return JSONResponse({"success": True, "found": results})
    except Exception as e:
        return JSONResponse({"error": str(e), "found": 0}, status_code=500)

@app.get("/api/releases/{imdb_id}")
async def get_releases(request: Request, imdb_id: str, db: AsyncSession = Depends(get_db)):
    """Получить список релизов для IMDb ID"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        result = await db.execute(
            text("SELECT title, quality, size, seeders, tracker, created_at, last_update FROM torrent_releases WHERE imdb_id = :imdb_id ORDER BY created_at DESC LIMIT 20"),
            {"imdb_id": imdb_id}
        )
        releases = result.fetchall()
        
        result_list = []
        for r in releases:
            result_list.append({
                "title": r[0],
                "quality": r[1],
                "size": r[2],
                "seeders": r[3],
                "tracker": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
                "last_update": r[6].isoformat() if r[6] else None
            })
        
        return JSONResponse(result_list)
    except Exception as e:
        logger.error(f"Error getting releases: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

# Новые endpoints для улучшений

@app.get("/api/stats")
@limiter.limit("10/minute")
async def get_stats(request: Request, db: AsyncSession = Depends(get_db)):
    """Получить общую статистику приложения"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        stats = await get_statistics(db)
        return JSONResponse(stats)
    except Exception as e:
        logger.error(f"Error getting statistics: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/stats/{imdb_id}")
@limiter.limit("30/minute")
async def get_item_stats(request: Request, imdb_id: str, db: AsyncSession = Depends(get_db)):
    """Получить статистику для конкретного элемента"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        stats = await get_item_statistics(db, imdb_id)
        return JSONResponse(stats)
    except Exception as e:
        logger.error(f"Error getting item statistics: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/notifications/history")
@limiter.limit("30/minute")
async def get_notifications_history(
    request: Request,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    imdb_id: Optional[str] = Query(None)
):
    """Получить историю уведомлений"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        query = "SELECT id, imdb_id, release_title, notification_text, sent_at, success FROM notifications_history WHERE 1=1"
        params = {}
        
        if imdb_id:
            query += " AND imdb_id = :imdb_id"
            params["imdb_id"] = imdb_id
        
        query += " ORDER BY sent_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = per_page
        params["offset"] = (page - 1) * per_page
        
        result = await db.execute(text(query), params)
        notifications = result.fetchall()
        
        notifications_list = []
        for n in notifications:
            notifications_list.append({
                "id": n[0],
                "imdb_id": n[1],
                "release_title": n[2],
                "notification_text": n[3],
                "sent_at": n[4].isoformat() if n[4] else None,
                "success": n[5]
            })
        
        return JSONResponse(notifications_list)
    except Exception as e:
        logger.error(f"Error getting notifications history: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/batch/toggle")
@limiter.limit("10/minute")
async def batch_toggle(request: Request, item_ids: List[int] = Body(...), enabled: bool = Body(...), db: AsyncSession = Depends(get_db)):
    """Массовое включение/выключение отслеживания"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        await db.execute(
            text("UPDATE imdb_watchlist SET enabled = :enabled WHERE id = ANY(:ids)"),
            {"enabled": enabled, "ids": item_ids}
        )
        await db.commit()
        return JSONResponse({"success": True, "updated": len(item_ids)})
    except Exception as e:
        await db.rollback()
        logger.error(f"Error batch toggle: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/batch/delete")
@limiter.limit("10/minute")
async def batch_delete(request: Request, item_ids: List[int] = Body(...), db: AsyncSession = Depends(get_db)):
    """Массовое удаление элементов"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        await db.execute(
            text("DELETE FROM imdb_watchlist WHERE id = ANY(:ids)"),
            {"ids": item_ids}
        )
        await db.commit()
        return JSONResponse({"success": True, "deleted": len(item_ids)})
    except Exception as e:
        await db.rollback()
        logger.error(f"Error batch delete: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/export/json")
@limiter.limit("5/minute")
async def export_json(request: Request, db: AsyncSession = Depends(get_db)):
    """Экспорт watchlist в JSON"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        result = await db.execute(text("""
            SELECT imdb_id, title, original_title, type, enabled, year, genre, target_season, preferred_quality, preferred_audio, min_releases_count
            FROM imdb_watchlist ORDER BY created_at DESC
        """))
        items = result.fetchall()
        
        items_list = []
        for item in items:
            items_list.append({
                "imdb_id": item[0],
                "title": item[1],
                "original_title": item[2],
                "type": item[3],
                "enabled": item[4],
                "year": item[5],
                "genre": item[6],
                "target_season": item[7],
                "preferred_quality": item[8],
                "preferred_audio": item[9],
                "min_releases_count": item[10]
            })
        
        return JSONResponse(items_list)
    except Exception as e:
        logger.error(f"Error exporting JSON: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/export/csv")
@limiter.limit("5/minute")
async def export_csv(request: Request, db: AsyncSession = Depends(get_db)):
    """Экспорт watchlist в CSV"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        result = await db.execute(text("""
            SELECT imdb_id, title, original_title, type, enabled, year, genre, target_season, preferred_quality, preferred_audio, min_releases_count
            FROM imdb_watchlist ORDER BY created_at DESC
        """))
        items = result.fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["imdb_id", "title", "original_title", "type", "enabled", "year", "genre", "target_season", "preferred_quality", "preferred_audio", "min_releases_count"])
        
        for item in items:
            writer.writerow(item)
        
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=watchlist_{datetime.now().strftime('%Y%m%d')}.csv"}
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/import/json")
@limiter.limit("5/minute")
async def import_json(request: Request, db: AsyncSession = Depends(get_db)):
    """Импорт watchlist из JSON"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        data = await request.json()
        if not isinstance(data, list):
            return JSONResponse({"error": "Invalid format. Expected array"}, status_code=400)
        
        imported = 0
        for item in data:
            try:
                imdb_id = item.get("imdb_id")
                if not imdb_id:
                    continue
                
                # Получаем метаданные если их нет
                if not item.get("title"):
                    metadata = await fetch_metadata(imdb_id)
                    item.update(metadata)
                
                await db.execute(
                    text("""
                        INSERT INTO imdb_watchlist (imdb_id, title, original_title, type, enabled, year, genre, target_season, preferred_quality, preferred_audio, min_releases_count)
                        VALUES (:imdb_id, :title, :original_title, :type, :enabled, :year, :genre, :target_season, :preferred_quality, :preferred_audio, :min_releases_count)
                        ON CONFLICT (imdb_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            original_title = EXCLUDED.original_title,
                            enabled = EXCLUDED.enabled
                    """),
                    {
                        "imdb_id": imdb_id,
                        "title": item.get("title"),
                        "original_title": item.get("original_title"),
                        "type": item.get("type", "movie"),
                        "enabled": item.get("enabled", True),
                        "year": item.get("year"),
                        "genre": item.get("genre"),
                        "target_season": item.get("target_season"),
                        "preferred_quality": item.get("preferred_quality"),
                        "preferred_audio": item.get("preferred_audio"),
                        "min_releases_count": item.get("min_releases_count")
                    }
                )
                imported += 1
            except Exception as e:
                logger.warning(f"Error importing item {item.get('imdb_id')}: {e}")
                continue
        
        await db.commit()
        return JSONResponse({"success": True, "imported": imported})
    except Exception as e:
        await db.rollback()
        logger.error(f"Error importing JSON: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/releases/{imdb_id}/filtered")
@limiter.limit("30/minute")
async def get_filtered_releases(
    request: Request,
    imdb_id: str,
    db: AsyncSession = Depends(get_db),
    quality: Optional[str] = Query(None),
    tracker: Optional[str] = Query(None),
    min_seeders: Optional[int] = Query(None),
    max_size_gb: Optional[float] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc")
):
    """Получить отфильтрованные релизы для IMDb ID"""
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        query = "SELECT title, quality, size, seeders, tracker, created_at, last_update FROM torrent_releases WHERE imdb_id = :imdb_id"
        params = {"imdb_id": imdb_id}
        
        if quality:
            query += " AND quality ILIKE :quality"
            params["quality"] = f"%{quality}%"
        
        if tracker:
            query += " AND tracker ILIKE :tracker"
            params["tracker"] = f"%{tracker}%"
        
        if min_seeders is not None:
            query += " AND seeders >= :min_seeders"
            params["min_seeders"] = min_seeders
        
        if max_size_gb is not None:
            query += " AND size <= :max_size"
            params["max_size"] = int(max_size_gb * 1024 * 1024 * 1024)
        
        # Сортировка
        valid_sort_fields = ["created_at", "size", "seeders", "quality"]
        if sort_by not in valid_sort_fields:
            sort_by = "created_at"
        sort_order = "DESC" if sort_order.lower() == "desc" else "ASC"
        query += f" ORDER BY {sort_by} {sort_order} LIMIT 100"
        
        result = await db.execute(text(query), params)
        releases = result.fetchall()
        
        result_list = []
        for r in releases:
            result_list.append({
                "title": r[0],
                "quality": r[1],
                "size": r[2],
                "seeders": r[3],
                "tracker": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
                "last_update": r[6].isoformat() if r[6] else None
            })
        
        return JSONResponse(result_list)
    except Exception as e:
        logger.error(f"Error getting filtered releases: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)
