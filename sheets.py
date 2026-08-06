from datetime import date

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SPREADSHEET_ID

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

DB_SHEET = "БД"
HEADER_ROW = ["Дата", "Описание", "Сумма", "Категория", "Тип"]

TYPE_EXPENSE = "Расход"
TYPE_INCOME = "Доход"

# Google Sheets/Excel serial date epoch.
SHEETS_DATE_EPOCH = date(1899, 12, 30)


def _to_sheets_serial_date(d: date) -> int:
    return (d - SHEETS_DATE_EPOCH).days


class SheetsClient:
    def __init__(self):
        creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDENTIALS_PATH, scopes=SCOPES)
        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(GOOGLE_SPREADSHEET_ID)
        self._sheet = self._get_or_create_sheet(DB_SHEET)

    def _get_or_create_sheet(self, title: str) -> gspread.Worksheet:
        try:
            sheet = self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            sheet = self._spreadsheet.add_worksheet(title=title, rows=1000, cols=len(HEADER_ROW))
            sheet.append_row(HEADER_ROW)

        # Числовой формат колонок задаём отдельно от записи строк (не через
        # value_input_option="USER_ENTERED" на всю строку) — иначе Sheets
        # начинает "по-умному" интерпретировать и текстовые колонки тоже
        # (категория, тип), что и сломало категории в прошлый раз.
        sheet.format("A2:A1000", {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}})
        sheet.format("C2:C1000", {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.##"}})
        return sheet

    def _add_row(self, description: str, amount: float, category: str, entry_type: str) -> None:
        row_date = _to_sheets_serial_date(date.today())
        self._sheet.append_row([row_date, description, amount, category, entry_type])

    def add_expense(self, description: str, amount: float, category: str) -> None:
        self._add_row(description, amount, category, TYPE_EXPENSE)

    def add_income(self, description: str, amount: float, category: str) -> None:
        self._add_row(description, amount, category, TYPE_INCOME)
