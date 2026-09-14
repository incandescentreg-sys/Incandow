# Incandow — Telegram Mini App + Vercel

Веб-приложение для скачивания видео из YouTube, TikTok, Instagram, VK, Twitter/X, Rutube.
Развёрнуто на Vercel как serverless-функция (FastAPI + yt-dlp).

**Заточено под Telegram Mini App:**
- Telegram Web App SDK (темы, haptics, expand)
- `tg.openLink()` для скачивания (редирект на прямую CDN-ссылку)
- Mobile-first дизайн, `safe-area-inset`, адаптивный интерфейс

## Как это работает

Vercel — бессерверная платформа: **нельзя хранить файлы на диске**.
Поэтому используется подход **yt-dlp с `download=False`**:
1. Пользователь вставляет ссылку
2. Сервер через yt-dlp получает метаданные и **прямой URL** на видеофайл
3. Браузер делает редирект на прямой URL и скачивает видео **напрямую с CDN** (YouTube/TikTok и т.д.)

Файлы не проходят через наш сервер — это быстро и дёшево.

## Структура

```
video-downloader/
├── api/
│   ├── index.py        # FastAPI app (entrypoint для Vercel)
│   └── downloader.py   # yt-dlp: извлечение метаданных и прямых ссылок
├── templates/
│   └── index.html      # веб-интерфейс
├── requirements.txt
├── vercel.json         # maxDuration 300s, excludeFiles
└── README.md
```

## Локальный запуск

```bash
cd video-downloader
pip install -r requirements.txt
uvicorn api.index:app --reload --port 8000
# http://localhost:8000
```

## Деплой на Vercel

### Вариант 1: Vercel CLI (быстро)
```bash
npm i -g vercel
cd video-downloader
vercel          # первый раз — логин и настройка
vercel --prod   # прод
```

### Вариант 2: Git + GitHub
1. Залей проект на GitHub
2. На [vercel.com](https://vercel.com) → *Add New Project* → импортируй репозиторий
3. Vercel автоматически определит Python + FastAPI
4. Deploy

### Вариант 3: Dashboard
Перетащи папку `video-downloader` на [vercel.com/new](https://vercel.com/new) — CLI зальёт.

## Подключение к Telegram (Mini App)

1. Напиши [@BotFather](https://t.me/BotFather) → создай бота
2. Команда `/newapp` → выбери бота → укажи URL твоего Vercel-деплоя (например `https://video-downloader.vercel.app`)
3. Готово — бот в чате получит кнопку Mini App (иконка снизу, рядом с клавиатурой)
4. Открываешь Mini App — приложение грузится внутри Telegram с темой, haptics и `openLink`

## API

| Метод | Путь | Описание |
|---|---|---|
| GET | `/` | Веб-интерфейс (Mobile-first) |
| GET | `/api/info?url=...&format_id=...` | Метаданные + список форматов + прямые URL |
| GET | `/api/download?url=...&format_id=...` | Редирект (307) на прямой URL |
| GET | `/api/supported` | Список поддерживаемых платформ |

## Ограничения Vercel

- **Таймаут**: Hobby — до 300 с (5 мин), Pro — до 800 с. Поднять можно в `vercel.json` (`maxDuration`).
- **Размер бандла**: до 500 MB (Hobby). yt-dlp + зависимости — меньше 100 MB, ок.
- **Простой**: на Hobby 100 GB/мес трафика — для личного использования хватает.
- Каждый запрос — отдельный serverless-инстанс, но `extract_info` быстрый (секунды).

## Примечания

- Instagram и Twitter могут требовать cookies (вход в аккаунт) — тогда `extract_info` вернёт ошибку. Для надёжности можно добавить `cookiefile` в `_ydl_opts`.
- `tg.openLink()` открывает URL в нативном браузере Telegram (или системном на iOS) — пользователь скачивает файл там, Mini App остаётся в фоне.
- Для TikTok иногда нужен User-Agent (уже добавлен).