import asyncio
import logging
import os

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from downloader import HOST_LABELS, detect_host, get_video_info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web")

app = FastAPI(title="Incandow", version="2.0.0")

_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(_base, "templates"))
static_dir = os.path.join(_base, "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def _run_sync(fn):
    return asyncio.get_running_loop().run_in_executor(None, fn)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, error: str = ""):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "error": error, "hosts": HOST_LABELS},
    )


def _validate(url: str):
    if not detect_host(url):
        raise HTTPException(400, "Неподдерживаемая ссылка")


@app.get("/api/info")
async def api_info(url: str = Query(...), format_id: str = Query(None)):
    """Получить информацию о видео и прямые ссылки."""
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
    """Редирект на прямой URL видео (клиент качает напрямую с CDN)."""
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

    return RedirectResponse(direct_url, status_code=307)


@app.get("/api/proxy")
async def api_proxy(url: str = Query(...)):
    """
    Прокси-стриминг: скачивает файл с CDN и отдаёт клиенту.
    Нужен для Telegram Mini App: WebApp.downloadFile разрешает только
    URL того же origin, поэтому файл качаем через свой бекенд.
    """
    async def _iter():
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=180) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        yield chunk
        except Exception as e:
            logger.error("Proxy streaming error: %s", e)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.index:app", host="0.0.0.0", port=8000, reload=True)