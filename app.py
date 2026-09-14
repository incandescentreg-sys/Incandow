import asyncio
import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from downloader import HOST_LABELS, detect_host, get_video_info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web")

# Telegram Bot webhook
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_WEBHOOK_PATH = os.getenv("BOT_WEBHOOK_PATH", "/webhook")

app = FastAPI(title="Incandow", version="2.2.0")

_base = Path(__file__).parent

static_dir = _base / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

_index_html: str | None = None


def _load_html() -> str:
    global _index_html
    if _index_html is None:
        _index_html = (_base / "templates" / "index.html").read_text("utf-8")
    return _index_html


def _run_sync(fn):
    return asyncio.get_running_loop().run_in_executor(None, fn)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(_load_html())


def _validate(url: str):
    if not detect_host(url):
        raise HTTPException(400, "Неподдерживаемая ссылка")


@app.get("/api/info")
async def api_info(url: str = Query(...), format_id: str = Query(None)):
    _validate(url)
    try:
        info = await _run_sync(lambda: get_video_info(url, format_id))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))

    if not info["direct_url"] and not info["formats"]:
        raise HTTPException(500, "Не удалось найти прямые ссылки")

    return info


@app.get("/api/download")
async def api_download(url: str = Query(...), format_id: str = Query(None)):
    _validate(url)
    try:
        info = await _run_sync(lambda: get_video_info(url, format_id))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))

    direct_url = info.get("direct_url") or (
        info["formats"][0]["url"] if info.get("formats") else ""
    )
    if not direct_url:
        raise HTTPException(500, "Не удалось найти прямую ссылку")

    return {"url": direct_url, "title": info.get("title", "video.mp4")}


@app.get("/api/proxy")
async def api_proxy(url: str = Query(...)):
    host = next((h for h in HOST_LABELS if h in url), None)
    referer = f"https://{host}/" if host else "https://youtube.com/"

    async def _iter():
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": referer,
                "Accept": "*/*",
            }
            async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        yield chunk
        except Exception as e:
            logger.error("Proxy error: %s", e)

    return StreamingResponse(
        _iter(),
        media_type="video/mp4",
        headers={
            "Content-Disposition": 'attachment; filename="video.mp4"',
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/supported")
async def api_supported():
    return {
        "hosts": list(dict.fromkeys(HOST_LABELS.values())),
        "hosts_map": {h: lbl for h, lbl in HOST_LABELS.items()},
    }


# === Telegram Bot Webhook ===
if BOT_TOKEN:

    from bot import handle_update

    @app.post("/" + BOT_WEBHOOK_PATH.lstrip("/"))
    async def telegram_webhook(request: Request):
        update = await request.json()
        logger.info("Bot update: chat_id=%s",
                    (update.get("message") or {}).get("chat", {}).get("id"))
        asyncio.create_task(handle_update(update))
        return {"ok": True}

    @app.get("/api/bot/setup")
    async def bot_setup():
        from bot import set_webhook
        vercel_url = os.getenv("VERCEL_URL", "")
        if not vercel_url:
            return {"ok": False, "error": "VERCEL_URL not set"}
        webhook_url = f"https://{vercel_url}/{BOT_WEBHOOK_PATH.lstrip('/')}"
        result = await set_webhook(webhook_url)
        return result

    @app.get("/api/bot/info")
    async def bot_info():
        from bot import TOKEN
        if not TOKEN:
            return {"ok": False, "error": "BOT_TOKEN not set"}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
            )
            return r.json()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)