import re
import logging
from typing import Optional

import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("downloader")

SUPPORTED_HOSTS = [
    "youtube.com", "youtu.be",
    "tiktok.com", "vm.tiktok.com",
    "instagram.com",
    "vk.com",
    "twitter.com", "x.com",
    "rutube.ru",
]

HOST_LABELS = {
    "youtube.com": "YouTube", "youtu.be": "YouTube",
    "tiktok.com": "TikTok", "vm.tiktok.com": "TikTok",
    "instagram.com": "Instagram",
    "vk.com": "VK",
    "twitter.com": "Twitter/X", "x.com": "Twitter/X",
    "rutube.ru": "Rutube",
}

_ydl_opts = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "socket_timeout": 30,
    "retries": 2,
    "extract_flat": False,
}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    return url


def detect_host(url: str) -> Optional[str]:
    url = normalize_url(url)
    for host in SUPPORTED_HOSTS:
        if host in url:
            return host
    return None


def _pick_best_format(formats: list[dict]) -> Optional[dict]:
    """Лучший одиночный файл с видео+аудио (progressive), по убыванию качества."""
    progressive = [
        f for f in formats
        if f.get("url")
        and f.get("ext") not in ("mhtml", "json")
        and f.get("vcodec") and f.get("vcodec") != "none"
        and f.get("acodec") and f.get("acodec") != "none"
    ]
    if not progressive:
        progressive = [
            f for f in formats
            if f.get("url") and f.get("ext") not in ("mhtml", "json")
        ]
    if not progressive:
        return None

    def height(f):
        h = f.get("height") or 0
        return h or 0

    progressive.sort(key=height, reverse=True)
    return progressive[0]


def get_video_info(url: str, format_id: Optional[str] = None) -> dict:
    url = normalize_url(url)
    host = detect_host(url)
    if host is None:
        raise ValueError(
            "Неподдерживаемая ссылка. Поддерживаются: YouTube, TikTok, Instagram, VK, Twitter/X, Rutube."
        )

    opts = {**_ydl_opts}
    if "tiktok" in host:
        opts["http_headers"] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            raise RuntimeError(f"Не удалось получить информацию: {e}")

        if info is None:
            raise RuntimeError("Не удалось получить информацию о видео.")

        title = info.get("title", "Untitled")
        uploader = info.get("uploader") or info.get("channel") or info.get("creator") or ""
        duration = info.get("duration") or 0
        thumbnail = info.get("thumbnail") or ""

        formats = info.get("formats") or []

        selected = None
        if format_id:
            selected = next((f for f in formats if f.get("format_id") == format_id and f.get("url")), None)
        if selected is None:
            selected = _pick_best_format(formats)

        direct_url = selected.get("url", "") if selected else (info.get("url") or "")

        return {
            "title": title,
            "uploader": uploader,
            "duration": duration,
            "thumbnail": thumbnail,
            "host": host,
            "host_label": HOST_LABELS.get(host, host),
            "direct_url": direct_url,
            "selected_format": (
                {
                    "format_id": selected.get("format_id", ""),
                    "ext": selected.get("ext", ""),
                    "resolution": (
                        f"{selected.get('width', '?')}x{selected.get('height', '?')}"
                    ),
                    "filesize": (
                        selected.get("filesize") or selected.get("filesize_approx") or 0
                    ),
                }
                if selected else None
            ),
            "formats": [
                {
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "resolution": f"{f.get('width', '?')}x{f.get('height', '?')}",
                    "filesize": f.get("filesize") or f.get("filesize_approx") or 0,
                    "note": f.get("format_note") or "",
                    "vcodec": f.get("vcodec", ""),
                    "acodec": f.get("acodec", ""),
                    "url": f.get("url", ""),
                }
                for f in formats
                if f.get("url") and f.get("ext") not in ("mhtml", "json")
            ],
        }