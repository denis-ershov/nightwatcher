import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from datetime import datetime
from app.db import SessionLocal
from app.config import ADMIN_PASSWORD, SESSION_SECRET
from app.omdb import fetch_movie_info

app = FastAPI(title="NightWatcher")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET or "fallback-secret")

templates = Jinja2Templates(directory="app/templates")

os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_auth(request: Request):
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True

@app.get("/login")
def login_page(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@app.get("/")
def index(request: Request):
    if not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)
    
    db = SessionLocal()
    items = db.execute(text("""
        SELECT id, imdb_id, title, type, enabled, created_at, poster_url, year, genre, plot, rating, runtime, last_checked, total_seasons
        FROM imdb_watchlist ORDER BY created_at DESC
    """)).fetchall()
    db.close()
    
    items_list = []
    for item in items:
        items_list.append({
            "id": item[0],
            "imdb_id": item[1],
            "title": item[2],
            "type": item[3],
            "enabled": item[4],
            "created_at": item[5],
            "poster_url": item[6],
            "year": item[7],
            "genre": item[8],
            "plot": item[9],
            "rating": item[10],
            "runtime": item[11],
            "last_checked": item[12],
            "total_seasons": item[13],
        })
    
    return templates.TemplateResponse("index.html", {"request": request, "items": items_list})

@app.post("/add")
async def add(request: Request, imdb_id: str = Form(...)):
    if not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)
    
    imdb_id = imdb_id.strip()
    if not imdb_id.startswith("tt"):
        imdb_id = "tt" + imdb_id
    
    movie_info = await fetch_movie_info(imdb_id)
    
    db = SessionLocal()
    try:
        db.execute(
            text("""
                INSERT INTO imdb_watchlist (imdb_id, title, type, poster_url, year, genre, plot, rating, runtime, total_seasons)
                VALUES (:imdb_id, :title, :type, :poster_url, :year, :genre, :plot, :rating, :runtime, :total_seasons)
                ON CONFLICT (imdb_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    poster_url = EXCLUDED.poster_url,
                    year = EXCLUDED.year,
                    genre = EXCLUDED.genre,
                    plot = EXCLUDED.plot,
                    rating = EXCLUDED.rating,
                    runtime = EXCLUDED.runtime,
                    total_seasons = EXCLUDED.total_seasons
            """),
            {
                "imdb_id": imdb_id,
                "title": movie_info.get("title") or imdb_id,
                "type": movie_info.get("type", "movie"),
                "poster_url": movie_info.get("poster_url"),
                "year": movie_info.get("year"),
                "genre": movie_info.get("genre"),
                "plot": movie_info.get("plot"),
                "rating": movie_info.get("rating"),
                "runtime": movie_info.get("runtime"),
                "total_seasons": movie_info.get("total_seasons"),
            }
        )
        db.commit()
    finally:
        db.close()
    
    return RedirectResponse("/", status_code=303)

@app.post("/delete/{item_id}")
def delete_item(request: Request, item_id: int):
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    db = SessionLocal()
    db.execute(text("DELETE FROM imdb_watchlist WHERE id = :id"), {"id": item_id})
    db.commit()
    db.close()
    return JSONResponse({"success": True})

@app.post("/toggle/{item_id}")
def toggle_item(request: Request, item_id: int):
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    db = SessionLocal()
    db.execute(text("UPDATE imdb_watchlist SET enabled = NOT enabled WHERE id = :id"), {"id": item_id})
    db.commit()
    db.close()
    return JSONResponse({"success": True})

@app.post("/edit/{item_id}")
def edit_item(request: Request, item_id: int, title: str = Form(...), type: str = Form(...)):
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    db = SessionLocal()
    db.execute(
        text("UPDATE imdb_watchlist SET title = :title, type = :type WHERE id = :id"),
        {"id": item_id, "title": title, "type": type}
    )
    db.commit()
    db.close()
    return RedirectResponse("/", status_code=303)

@app.post("/refresh/{item_id}")
async def refresh_item(request: Request, item_id: int):
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    db = SessionLocal()
    result = db.execute(text("SELECT imdb_id FROM imdb_watchlist WHERE id = :id"), {"id": item_id}).fetchone()
    if result:
        imdb_id = result[0]
        movie_info = await fetch_movie_info(imdb_id)
        if movie_info:
            db.execute(
                text("""
                    UPDATE imdb_watchlist SET
                        title = :title,
                        poster_url = :poster_url,
                        year = :year,
                        genre = :genre,
                        plot = :plot,
                        rating = :rating,
                        runtime = :runtime,
                        total_seasons = :total_seasons
                    WHERE id = :id
                """),
                {
                    "id": item_id,
                    "title": movie_info.get("title"),
                    "poster_url": movie_info.get("poster_url"),
                    "year": movie_info.get("year"),
                    "genre": movie_info.get("genre"),
                    "plot": movie_info.get("plot"),
                    "rating": movie_info.get("rating"),
                    "runtime": movie_info.get("runtime"),
                    "total_seasons": movie_info.get("total_seasons"),
                }
            )
            db.commit()
    db.close()
    return JSONResponse({"success": True})

@app.post("/search")
def manual_search(request: Request):
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    from app.watcher import run_search
    results = run_search()
    return JSONResponse({"success": True, "found": results})

@app.get("/api/releases/{imdb_id}")
def get_releases(request: Request, imdb_id: str):
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    db = SessionLocal()
    releases = db.execute(
        text("SELECT title, quality, size, seeders, tracker, created_at FROM torrent_releases WHERE imdb_id = :imdb_id ORDER BY created_at DESC LIMIT 20"),
        {"imdb_id": imdb_id}
    ).fetchall()
    db.close()
    
    result = []
    for r in releases:
        result.append({
            "title": r[0],
            "quality": r[1],
            "size": r[2],
            "seeders": r[3],
            "tracker": r[4],
            "created_at": r[5].isoformat() if r[5] else None
        })
    
    return JSONResponse(result)
