from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from app.db import SessionLocal

app = FastAPI(title="NightWatcher")
templates = Jinja2Templates(directory="app/templates")

@app.get("/")
def index(request: Request):
    db = SessionLocal()
    items = db.execute(text("SELECT * FROM imdb_watchlist ORDER BY created_at DESC")).fetchall()
    db.close()
    return templates.TemplateResponse("index.html", {"request": request, "items": items})

@app.post("/add")
def add(imdb_id: str = Form(...), title: str = Form(None), type: str = Form("movie")):
    db = SessionLocal()
    db.execute(
        text("INSERT INTO imdb_watchlist (imdb_id, title, type) VALUES (:i, :t, :ty) ON CONFLICT DO NOTHING"),
        {"i": imdb_id, "t": title, "ty": type}
    )
    db.commit()
    db.close()
    return RedirectResponse("/", status_code=303)
