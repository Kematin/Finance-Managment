import os

# Ставим до импорта config: он читает окружение на импорте, а load_dotenv
# существующие переменные не перетирает. Тесты в сеть не ходят и реальные
# значения из .env им не нужны.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_USER_ID", "1")
os.environ.setdefault("GOOGLE_SPREADSHEET_ID", "test-spreadsheet")
