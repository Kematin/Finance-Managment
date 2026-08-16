from dataclasses import dataclass
from datetime import date, datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SPREADSHEET_ID

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

DB_SHEET = "БД"
HEADER_ROW = ["Дата", "Описание", "Сумма", "Категория", "Тип"]

# Служебный лист с парами ключ-значение: состояние бота, которое должно пережить
# перезапуск контейнера (у него нет своего тома).
STATE_SHEET = "Состояние"
STATE_HEADER = ["Ключ", "Значение"]

TYPE_EXPENSE = "Расход"
TYPE_INCOME = "Доход"

# Google Sheets/Excel serial date epoch.
SHEETS_DATE_EPOCH = date(1899, 12, 30)


def _to_sheets_serial_date(d: date) -> int:
    return (d - SHEETS_DATE_EPOCH).days


def _from_sheets_serial_date(value) -> date | None:
    """Дата из ячейки. Числа читаем как serial date, строки — как dd.mm.yyyy."""
    if isinstance(value, (int, float)):
        return SHEETS_DATE_EPOCH + timedelta(days=int(value))
    if isinstance(value, str):
        for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), pattern).date()
            except ValueError:
                continue
    return None


@dataclass(frozen=True)
class Entry:
    day: date
    description: str
    amount: float
    category: str
    entry_type: str


class SheetsClient:
    def __init__(self):
        creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDENTIALS_PATH, scopes=SCOPES)
        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(GOOGLE_SPREADSHEET_ID)
        self._sheet = self._get_or_create_sheet(DB_SHEET, HEADER_ROW, rows=1000)

        # Числовой формат колонок задаём отдельно от записи строк (не через
        # value_input_option="USER_ENTERED" на всю строку) — иначе Sheets
        # начинает "по-умному" интерпретировать и текстовые колонки тоже
        # (категория, тип), что и сломало категории в прошлый раз.
        self._sheet.format("A2:A1000", {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}})
        self._sheet.format("C2:C1000", {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.##"}})

    def _get_or_create_sheet(self, title: str, header: list[str], rows: int) -> gspread.Worksheet:
        try:
            return self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            sheet = self._spreadsheet.add_worksheet(title=title, rows=rows, cols=len(header))
            sheet.append_row(header)
            return sheet

    def _add_row(self, description: str, amount: float, category: str, entry_type: str) -> None:
        row_date = _to_sheets_serial_date(date.today())
        self._sheet.append_row([row_date, description, amount, category, entry_type])

    def add_expense(self, description: str, amount: float, category: str) -> None:
        self._add_row(description, amount, category, TYPE_EXPENSE)

    def add_income(self, description: str, amount: float, category: str) -> None:
        self._add_row(description, amount, category, TYPE_INCOME)

    def fetch_entries(self) -> list[Entry]:
        """Все записи листа. Значения читаем сырыми, иначе суммы приходят строками
        с разделителями разрядов, а дата — уже отформатированным текстом."""
        rows = self._sheet.get_values(value_render_option="UNFORMATTED_VALUE")

        entries = []
        for row in rows[1:]:
            if len(row) < len(HEADER_ROW):
                continue

            day = _from_sheets_serial_date(row[0])
            if day is None:
                continue
            try:
                amount = float(row[2])
            except (TypeError, ValueError):
                continue

            entries.append(
                Entry(
                    day=day,
                    description=str(row[1]),
                    amount=abs(amount),
                    category=str(row[3]),
                    entry_type=str(row[4]),
                )
            )
        return entries

    def get_state(self) -> dict[str, str]:
        """Служебные пары ключ-значение. Лист создаётся лениво, поэтому его
        отсутствие — не ошибка, а просто пустое состояние."""
        try:
            sheet = self._spreadsheet.worksheet(STATE_SHEET)
        except gspread.WorksheetNotFound:
            return {}

        rows = sheet.get_values()
        return {str(row[0]): str(row[1]) for row in rows[1:] if len(row) >= 2 and row[0]}

    def save_state(self, values: dict[str, str]) -> None:
        """Перезаписывает служебный лист целиком: состояние маленькое и всегда
        пишется полным набором ключей."""
        sheet = self._get_or_create_sheet(STATE_SHEET, STATE_HEADER, rows=10)
        sheet.clear()
        sheet.update([STATE_HEADER] + [[key, value] for key, value in values.items()])
