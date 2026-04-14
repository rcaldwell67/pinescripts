"""
Utility for sending Telegram notifications from backend scripts.

Usage:
    from telegram_notify import send_telegram_message
    send_telegram_message("Test message")

Set the following environment variables:
    TELEGRAM_BOT_TOKEN: Bot token from BotFather
    TELEGRAM_CHAT_ID: Chat or group/channel ID to send messages to
"""
import os
import requests

def send_telegram_message(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        resp = requests.post(url, data=payload, timeout=10)
        return resp.ok
    except Exception:
        return False
