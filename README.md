# YT → Audio

Минималистичный веб‑сервис: вставляешь ссылку на YouTube и получаешь аудио в выбранном формате (MP3, M4A, Opus, AAC, OGG Vorbis, WAV, FLAC).

- **Backend**: FastAPI + [yt-dlp](https://github.com/yt-dlp/yt-dlp) + `ffmpeg`. Код — в [`backend/`](./backend).
- **Frontend**: статический HTML/CSS/JS. Код — в [`frontend/`](./frontend).

## Локальный запуск

Backend:

```bash
cd backend
pip install -e .
uvicorn app.main:app --reload --port 8080
```

Нужен установленный `ffmpeg` (на Ubuntu: `sudo apt install ffmpeg`).

Frontend — просто открой `frontend/index.html` в браузере, указав в `frontend/config.js` адрес API (например, `http://localhost:8080`).

## Эндпоинты API

- `GET /healthz`
- `GET /api/formats`
- `GET /api/info?url=<youtube-url>`
- `GET /api/download?url=<youtube-url>&fmt=mp3|m4a|opus|aac|vorbis|wav|flac`

## Лицензия

Скачивайте только контент, на который у вас есть права.
