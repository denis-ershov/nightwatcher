"""
Асинхронный FastAPI приложение.
Оптимизировано для производительности и предотвращения утечек памяти.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db, close_db, AsyncSessionLocal
from app.config import ADMIN_PASSWORD, SESSION_SECRET
from app.metadata import fetch_metadata
from app.watcher import run_search
from app.prowlarr_client import close_client
from app.notifier import close_bot
from app.season_parser import extract_season_from_title, clean_title_from_season
import re

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

app = FastAPI(title="NightWatcher", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware, 
    secret_key=SESSION_SECRET,
    session_cookie="nightwatcher_session",
    max_age=86400,
    same_site="lax",
    https_only=False
)

templates = Jinja2Templates(directory="app/templates")

os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

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
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    """Главная страница со списком watchlist"""
    if not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)
    
    result = await db.execute(text("""
        SELECT id, imdb_id, title, original_title, type, enabled, created_at, updated_at, poster_url, year, genre, plot, rating, runtime, last_checked, total_seasons, target_season, preferred_quality, preferred_audio
        FROM imdb_watchlist ORDER BY created_at DESC
    """))
    items = result.fetchall()
    
    items_list = []
    for item in items:
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
        })
    
    return templates.TemplateResponse("index.html", {"request": request, "items": items_list})

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
    
    try:
        await db.execute(
            text("""UPDATE imdb_watchlist 
                    SET title = :title, type = :type, target_season = :target_season, 
                        preferred_quality = :preferred_quality, preferred_audio = :preferred_audio, 
                        updated_at = now() 
                    WHERE id = :id"""),
            {
                "id": item_id, 
                "title": title, 
                "type": type, 
                "target_season": season_value,
                "preferred_quality": quality_value,
                "preferred_audio": audio_value
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
        return JSONResponse({"error": str(e)}, status_code=500)
