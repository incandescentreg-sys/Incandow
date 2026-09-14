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

app = FastAPI(title="Incandow", version="2.1.0")

_base = Path(__file__).parent

# Serve static files
static_dir = _base / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Cache HTML in memory
_index_html: str | None = None


def _load_html() -> str:
    global _index_html
    if _index_html is None:
        path = _base / "templates" / "index.html"
        _index_html = path.read_text("utf-8")
    return _index_html


def _run_sync(fn):
    return asyncio.get_running_loop().run_in_executor(None, fn)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, error: str = ""):
    html = _load_html()
    html = html.replace('__INITIAL_ERROR__', error.replace('"', '&quot;'))
    return HTMLResponse(html)


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

    return RedirectResponse(direct_url, status_code=307)


@app.get("/api/supported")
async def api_supported():
    return {
        "hosts": list(dict.fromkeys(HOST_LABELS.values())),
        "hosts_map": {h: lbl for h, lbl in HOST_LABELS.items()},
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)