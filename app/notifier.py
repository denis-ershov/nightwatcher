import requests
from app.config import TG_TOKEN, TG_CHAT_ID

def send_message(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TG_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    })
