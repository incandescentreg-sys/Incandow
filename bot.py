import asyncio
import logging
import os

import httpx

from downloader import detect_host, get_video_info

logger = logging.getLogger("bot")

TOKEN = os.getenv("BOT_TOKEN", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
}


def api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TOKEN}/{method}"


async def send_message(chat_id, text: str):
    if not TOKEN:
        return
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                api_url("sendMessage"),
                json={"chat_id": chat_id, "text": text[:4000]},
            )
    except Exception as e:
        logger.error("sendMessage error: %s", e)


async def send_video_by_url(chat_id, video_url: str, caption: str) -> bool:
    """Просим Telegram скачать видео сам — быстро, без 403 (у Telegram свои headers)."""
    if not TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                api_url("sendVideo"),
                json={
                    "chat_id": chat_id,
                    "video": video_url,
                    "caption": (caption or "")[:1024],
                    "supports_streaming": True,
                },
            )
            if r.status_code == 200:
                return True
            logger.warning("sendVideo by URL failed: %s", r.text[:300])
            return False
    except Exception as e:
        logger.error("sendVideo by URL error: %s", e)
        return False


async def download_and_send(chat_id, direct_url: str, title: str):
    """Запасной путь: скачиваем файл и загружаем в Telegram (до 50 МБ)."""
    if not TOKEN:
        return
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=280, headers=HEADERS) as client:
            r = await client.get(direct_url)
            r.raise_for_status()
    except Exception as e:
        await send_message(chat_id, f"❌ Не удалось скачать видео: {str(e)[:200]}")
        return

    data = r.content
    if len(data) > 49_500_000:
        await send_message(
            chat_id,
            "⚠️ Файл больше 50 МБ — Telegram не может его принять.\nСкачай напрямую: " + direct_url,
        )
        return

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            files = {"video": ("video.mp4", data, "video/mp4")}
            r = await client.post(
                api_url("sendVideo"),
                data={"chat_id": chat_id, "caption": (title or "")[:1024]},
                files=files,
            )
        if r.status_code != 200:
            logger.error("upload sendVideo: %s", r.text[:300])
            await send_message(chat_id, "❌ Не удалось отправить видео. Прямая ссылка: " + direct_url)
    except Exception as e:
        logger.error("upload sendVideo error: %s", e)
        await send_message(chat_id, "❌ Ошибка отправки. Прямая ссылка: " + direct_url)


async def handle_update(update: dict):
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return

    if text in ("/start", "/help"):
        await send_message(
            chat_id,
            "Привет! Я Incandow 🤖\n\n"
            "Отправь ссылку на видео из YouTube, TikTok, Instagram, VK, Twitter/X или Rutube —\n"
            "и я пришлю видео прямо сюда.",
        )
        return

    if not detect_host(text):
        await send_message(
            chat_id,
            "❌ Это не похоже на поддерживаемую ссылку.\n"
            "Поддерживаются: YouTube, TikTok, Instagram, VK, Twitter/X, Rutube.",
        )
        return

    await send_message(chat_id, "⏳ Скачиваю видео…")

    try:
        info = await asyncio.get_running_loop().run_in_executor(
            None, lambda: get_video_info(text)
        )
    except Exception as e:
        await send_message(chat_id, f"❌ Ошибка: {str(e)[:300]}")
        return

    direct = info.get("direct_url") or (
        info["formats"][0]["url"] if info.get("formats") else ""
    )
    if not direct:
        await send_message(chat_id, "❌ Не удалось найти ссылку на видео.")
        return

    caption = info.get("title", "")
    ok = await send_video_by_url(chat_id, direct, caption)
    if not ok:
        await send_message(chat_id, "🔄 Сервер Telegram не смог скачать напрямую — загружаю файл…")
        await download_and_send(chat_id, direct, caption)


async def set_webhook(url: str) -> dict:
    if not TOKEN:
        return {"ok": False, "error": "BOT_TOKEN not set"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(api_url("setWebhook"), json={"url": url})
    return r.json()