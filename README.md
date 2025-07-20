# Maniac Info Telegram Bot

## 🚀 Деплой на Railway

1. **Форкни или залей репозиторий на GitHub.**
2. **Зайди на [Railway](https://railway.app/), создай новый проект и выбери свой репозиторий.**
3. **Добавь переменные окружения:**
   - `TELEGRAM_TOKEN` — токен Telegram-бота
   - `TELEGRAM_API_ID` — API ID Telegram
   - `TELEGRAM_API_HASH` — API HASH Telegram
   - `CRYPTO_TOKEN` — токен CryptoPay
4. **Procfile** уже настроен: Railway сам запустит `python bot.py`.
5. **requirements.txt** должен содержать все зависимости (если что-то не хватает — добавь).
6. **session_string.txt** — файл с session string для Telethon (загрузи вручную через файловый менеджер Railway).

## Пример .env

```
TELEGRAM_TOKEN=your_telegram_token_here
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here
CRYPTO_TOKEN=your_crypto_token_here
```

## Локальный запуск

```bash
pip install -r requirements.txt
python bot.py
```

---

**Внимание:**
- Не храни реальные токены в коде!
- Для Telethon нужен файл `session_string.txt` (создай через `create_session.py`). 