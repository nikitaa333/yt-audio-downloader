# Backend — YouTube Audio Downloader

FastAPI service that takes a YouTube URL and returns the audio track in the requested format (MP3, M4A, Opus, WAV, FLAC, AAC, OGG Vorbis). Uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for extraction and `ffmpeg` for transcoding.

## Local run

```bash
cd backend
pip install -e .
uvicorn app.main:app --reload --port 8080
```

Requires `ffmpeg` to be installed on the host.

## Endpoints

- `GET /healthz` — health check.
- `GET /api/formats` — list of supported audio formats.
- `GET /api/info?url=...` — video metadata (title, uploader, duration, thumbnail).
- `GET /api/download?url=...&fmt=mp3` — download the audio file.

## Config

- `ALLOWED_ORIGINS` — comma-separated CORS origins (default `*`).
- `YT_WORKDIR` — base directory for temp downloads (default system temp).
