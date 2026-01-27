import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
PROWLARR_URL = os.getenv("PROWLARR_URL")
PROWLARR_API_KEY = os.getenv("PROWLARR_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
SESSION_SECRET = os.getenv("SESSION_SECRET")

if not ADMIN_PASSWORD:
    raise ValueError("ADMIN_PASSWORD environment variable is required")
if not SESSION_SECRET:
    raise ValueError("SESSION_SECRET environment variable is required")
