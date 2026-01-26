import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
PROWLARR_URL = os.getenv("PROWLARR_URL")
PROWLARR_API_KEY = os.getenv("PROWLARR_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
SESSION_SECRET = os.getenv("SESSION_SECRET", "nightwatcher-secret-key-change-me")
