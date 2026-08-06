import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_USER_ID = int(os.environ["TELEGRAM_USER_ID"])
GOOGLE_SHEETS_CREDENTIALS_PATH = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")
GOOGLE_SPREADSHEET_ID = os.environ["GOOGLE_SPREADSHEET_ID"]
