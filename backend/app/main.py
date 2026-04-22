from __future__ import annotations

import logging
import os
import re
import shutil
import shutil as _shutil
import tempfile
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

logger = logging.getLogger("yt_audio")
logging.basicConfig(level=logging.INFO)


def _ensure_ffmpeg() -> str | None:
    """Return path to an ffmpeg binary, installing a static build if needed."""
    if _shutil.which("ffmpeg"):
        return None  # already on PATH
    try:
        import static_ffmpeg  # type: ignore

        static_ffmpeg.add_paths()  # downloads on first run, cached afterwards
    except Exception:  # noqa: BLE001
        logger.exception("failed to set up static ffmpeg")
        return None
    return _shutil.which("ffmpeg")


FFMPEG_PATH = _ensure_ffmpeg()
if FFMPEG_PATH:
    logger.info("using ffmpeg at %s", FFMPEG_PATH)

AudioFormat = Literal["mp3", "m4a", "opus", "wav", "flac", "aac", "vorbis"]
ALLOWED_FORMATS: set[str] = {"mp3", "m4a", "opus", "wav", "flac", "aac", "vorbis"}
EXT_BY_FORMAT: dict[str, str] = {
    "mp3": "mp3",
    "m4a": "m4a",
    "opus": "opus",
    "wav": "wav",
    "flac": "flac",
    "aac": "m4a",
    "vorbis": "ogg",
}
MIME_BY_EXT: dict[str, str] = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "opus": "audio/ogg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
}

YT_URL_RE = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/",
    re.IGNORECASE,
)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "*",
).split(",")

YT_COOKIES_FILE = os.getenv("YT_COOKIES_FILE") or None
YT_PROXY = os.getenv("YT_PROXY") or None
YT_USER_AGENT = os.getenv(
    "YT_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)


def _common_ydl_opts() -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "http_headers": {"User-Agent": YT_USER_AGENT},
        "extractor_args": {
            "youtube": {"player_client": ["ios", "web_safari", "web"]}
        },
    }
    if FFMPEG_PATH:
        opts["ffmpeg_location"] = FFMPEG_PATH
    if YT_COOKIES_FILE and Path(YT_COOKIES_FILE).exists():
        opts["cookiefile"] = YT_COOKIES_FILE
    if YT_PROXY:
        opts["proxy"] = YT_PROXY
    return opts

app = FastAPI(title="YouTube Audio Downloader", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class InfoResponse(BaseModel):
    id: str
    title: str
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    webpage_url: str | None = None


def _validate_url(url: str) -> None:
    if not url or not YT_URL_RE.match(url.strip()):
        raise HTTPException(status_code=400, detail="URL must be a YouTube link")


def _safe_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r"[\x00-\x1f/\\:*?\"<>|]+", "_", name).strip(" ._")
    if not name:
        name = "audio"
    return name[:max_len]


def _cleanup(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # noqa: BLE001
        logger.exception("cleanup failed for %s", path)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/formats")
def list_formats() -> dict[str, list[dict[str, str]]]:
    return {
        "formats": [
            {"value": "mp3", "label": "MP3 (192 kbps)"},
            {"value": "m4a", "label": "M4A (AAC, original quality)"},
            {"value": "opus", "label": "Opus (original quality)"},
            {"value": "aac", "label": "AAC"},
            {"value": "vorbis", "label": "OGG Vorbis"},
            {"value": "wav", "label": "WAV (lossless, large)"},
            {"value": "flac", "label": "FLAC (lossless)"},
        ]
    }


@app.get("/api/info", response_model=InfoResponse)
def info(url: str = Query(..., description="YouTube video URL")) -> InfoResponse:
    _validate_url(url)
    try:
        opts = _common_ydl_opts() | {"skip_download": True}
        with YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch video info: {e}") from e

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Unexpected response from YouTube")

    return InfoResponse(
        id=str(data.get("id", "")),
        title=str(data.get("title", "video")),
        uploader=data.get("uploader"),
        duration=data.get("duration"),
        thumbnail=data.get("thumbnail"),
        webpage_url=data.get("webpage_url") or url,
    )


@app.get("/api/download")
def download(
    background: BackgroundTasks,
    url: str = Query(..., description="YouTube video URL"),
    fmt: AudioFormat = Query("mp3", description="Target audio format"),
) -> FileResponse:
    _validate_url(url)
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported format")

    work_dir = Path(tempfile.mkdtemp(prefix="ytdl_", dir=os.getenv("YT_WORKDIR") or None))
    out_template = str(work_dir / f"{uuid.uuid4().hex}.%(ext)s")

    postprocessors: list[dict] = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": fmt,
            "preferredquality": "192" if fmt == "mp3" else "0",
        }
    ]

    ydl_opts = _common_ydl_opts() | {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": postprocessors,
        "concurrent_fragment_downloads": 4,
        "restrictfilenames": False,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
    except DownloadError as e:
        _cleanup(work_dir)
        raise HTTPException(status_code=400, detail=f"Download failed: {e}") from e
    except Exception as e:  # noqa: BLE001
        _cleanup(work_dir)
        logger.exception("unexpected error during download")
        raise HTTPException(status_code=500, detail="Internal error during download") from e

    expected_ext = EXT_BY_FORMAT[fmt]
    candidates = sorted(work_dir.glob(f"*.{expected_ext}"))
    if not candidates:
        candidates = sorted(p for p in work_dir.iterdir() if p.is_file())
    if not candidates:
        _cleanup(work_dir)
        raise HTTPException(status_code=500, detail="Conversion produced no output file")

    file_path = candidates[0]
    title = (info_dict or {}).get("title") or "audio"
    download_name = f"{_safe_filename(str(title))}.{expected_ext}"
    media_type = MIME_BY_EXT.get(expected_ext, "application/octet-stream")

    background.add_task(_cleanup, work_dir)

    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{_safe_filename(str(title))}.{expected_ext}\"; "
            f"filename*=UTF-8''{quote(download_name)}"
        )
    }
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=download_name,
        headers=headers,
    )


@app.exception_handler(HTTPException)
async def http_exc_handler(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
