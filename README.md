# Personal finance bot

Телеграм-бот: пишешь "кофе 300" — бот определяет категорию (словарь по ключевым словам, при
незнакомом слове — просит выбрать категорию кнопкой) и пишет строку в Google Sheets.
Отрицательная сумма считается доходом.

## Установка

```bash
uv sync
cp .env.example .env
```

### Telegram

1. Создать бота через [@BotFather](https://t.me/BotFather), получить токен.
2. Вписать токен в `.env` → `TELEGRAM_BOT_TOKEN`.

### Google Sheets

1. Создать проект в [Google Cloud Console](https://console.cloud.google.com/), включить Google Sheets API.
2. Создать service account, скачать JSON-ключ → сохранить как `credentials.json` в корне проекта.
3. Создать таблицу в Google Sheets, выдать доступ на редактирование email сервис-аккаунта (из JSON-ключа, поле `client_email`).
4. Создать два листа: `Расходы` и `Доходы`, с заголовками `Дата | Описание | Сумма | Категория`.
5. Скопировать ID таблицы (из URL, между `/d/` и `/edit`) в `.env` → `GOOGLE_SPREADSHEET_ID`.

## Запуск

```bash
uv run python bot.py
```

### Через Docker

```bash
make build   # собрать образ
make run     # поднять контейнер (нужны .env и credentials.json в корне проекта)
make stop    # остановить
make rm      # удалить контейнер
```

## Категоризация

Сейчас — словарный классификатор (`categorizer.py`, `categories.py`): подстрока в тексте
матчится на категорию. Незнакомое слово ("кола" и т.п.) не распознаётся — бот спрашивает
категорию кнопкой.

Когда словарь надоест поддерживать вручную — план подключения embeddings-классификатора
(semantic similarity, ловит незнакомые слова автоматически) описан в конце `categorizer.py`.

## Лицензия

MIT, см. [LICENSE](LICENSE).
