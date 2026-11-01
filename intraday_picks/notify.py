"""Telegram delivery through the plain Bot API (HTML parse mode, 4096-char splitting)."""
from __future__ import annotations

import time

import requests

from . import config
from .util import log

logger = log("notify")

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000


def configured() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def get_me() -> dict | None:
    if not config.TELEGRAM_BOT_TOKEN:
        return None
    try:
        r = requests.get(API.format(token=config.TELEGRAM_BOT_TOKEN, method="getMe"), timeout=15)
        data = r.json()
        return data.get("result") if data.get("ok") else None
    except (requests.RequestException, ValueError) as exc:
        logger.warning("telegram getMe failed: %s", exc)
        return None


def _split(text: str) -> list[str]:
    if len(text) <= MAX_LEN:
        return [text]
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_LEN and current:
            parts.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        parts.append(current)
    return parts


def send(text: str, reply_to: int | None = None, dry_run: bool = False) -> int | None:
    """Send an HTML message; returns the first message id (for later replies)."""
    if dry_run or not configured():
        reason = "dry-run" if dry_run else "telegram not configured"
        print(f"\n----- telegram message ({reason}) -----\n{text}\n----- end -----\n")
        return None
    first_id: int | None = None
    for i, part in enumerate(_split(text)):
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_to and i == 0:
            payload["reply_to_message_id"] = reply_to
            payload["allow_sending_without_reply"] = True
        for attempt in range(3):
            try:
                r = requests.post(API.format(token=config.TELEGRAM_BOT_TOKEN, method="sendMessage"), json=payload, timeout=20)
                data = r.json()
                if data.get("ok"):
                    if first_id is None:
                        first_id = int(data["result"]["message_id"])
                    break
                desc = data.get("description", "")
                logger.warning("telegram send failed: %s", desc)
                if "parse" in desc.lower() or "entity" in desc.lower():
                    payload.pop("parse_mode", None)       # fall back to plain text rather than lose the message
                elif r.status_code == 429:
                    time.sleep(float(data.get("parameters", {}).get("retry_after", 3)))
                else:
                    time.sleep(2)
            except (requests.RequestException, ValueError) as exc:
                logger.warning("telegram send error: %s", exc)
                time.sleep(2)
    return first_id
