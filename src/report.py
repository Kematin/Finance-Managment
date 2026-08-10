"""
Агрегация записей из таблицы в отчёт (доходы, расходы, остаток) и его форматирование.

Модуль чистый: не ходит в сеть, работает со списком Entry из sheets.py.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sheets import Entry, TYPE_EXPENSE, TYPE_INCOME

MONTH_NAMES = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

# period key -> подпись для кнопки и заголовка отчёта
PERIODS: dict[str, str] = {
    "month": "Текущий месяц",
    "prev_month": "Прошлый месяц",
    "year": "Текущий год",
    "all": "Всё время",
}


@dataclass
class Report:
    title: str
    income: float = 0.0
    expense: float = 0.0
    expense_by_category: dict[str, float] = field(default_factory=dict)
    income_by_category: dict[str, float] = field(default_factory=dict)
    entries_count: int = 0

    @property
    def balance(self) -> float:
        """Остаток на счету за период: доходы минус расходы."""
        return self.income - self.expense

    @property
    def balance_ratio(self) -> float | None:
        """Остаток в процентах от доходов. None, если доходов за период не было."""
        if self.income <= 0:
            return None
        return self.balance / self.income * 100

    @property
    def spent_ratio(self) -> float | None:
        """Сколько процентов доходов потрачено. Может быть больше 100 при перерасходе."""
        if self.income <= 0:
            return None
        return self.expense / self.income * 100


def period_bounds(period: str, today: date) -> tuple[date | None, date | None]:
    """Границы периода [начало, конец] включительно. None означает "без границы"."""
    if period == "month":
        return today.replace(day=1), None
    if period == "prev_month":
        current_start = today.replace(day=1)
        prev_end = current_start - timedelta(days=1)
        return prev_end.replace(day=1), prev_end
    if period == "year":
        return today.replace(month=1, day=1), None
    return None, None


def period_title(period: str, today: date) -> str:
    if period == "month":
        return f"{MONTH_NAMES[today.month - 1].capitalize()} {today.year}"
    if period == "prev_month":
        prev_end = today.replace(day=1) - timedelta(days=1)
        return f"{MONTH_NAMES[prev_end.month - 1].capitalize()} {prev_end.year}"
    if period == "year":
        return f"{today.year} год"
    return "Всё время"


def build_report(entries: list[Entry], period: str, today: date | None = None) -> Report:
    today = today or date.today()
    start, end = period_bounds(period, today)
    report = Report(title=period_title(period, today))

    for entry in entries:
        if start is not None and entry.day < start:
            continue
        if end is not None and entry.day > end:
            continue

        report.entries_count += 1
        if entry.entry_type == TYPE_INCOME:
            report.income += entry.amount
            report.income_by_category[entry.category] = (
                report.income_by_category.get(entry.category, 0.0) + entry.amount
            )
        elif entry.entry_type == TYPE_EXPENSE:
            report.expense += entry.amount
            report.expense_by_category[entry.category] = (
                report.expense_by_category.get(entry.category, 0.0) + entry.amount
            )

    return report


def format_amount(amount: float) -> str:
    if amount == int(amount):
        return f"{amount:,.0f}".replace(",", " ")
    return f"{amount:,.2f}".replace(",", " ")


BAR_WIDTH = 20
BAR_FILLED = "█"
BAR_EMPTY = "░"


def render_bar(percent: float, width: int = BAR_WIDTH) -> str:
    """Полоска расходов к доходам. Заполнение обрезается по 100%, само число — нет."""
    clamped = max(0.0, min(percent, 100.0))
    filled = round(clamped / 100 * width)
    return BAR_FILLED * filled + BAR_EMPTY * (width - filled)


def _bar_lines(report: Report) -> list[str]:
    spent = report.spent_ratio
    if spent is None:
        if report.expense <= 0:
            return []
        return [render_bar(100), "Доходов за период нет — потрачено из остатка."]

    line = f"{render_bar(spent)} {spent:.0f}%"
    if spent > 100:
        line += f" — перерасход {format_amount(report.expense - report.income)}"
    return [line]


def format_report(report: Report) -> str:
    lines = [f"📊 Отчёт — {report.title}", ""]

    if report.entries_count == 0:
        lines.append("За этот период записей нет.")
        return "\n".join(lines)

    ratio = report.balance_ratio
    ratio_text = f" ({ratio:.0f}% от доходов)" if ratio is not None else ""

    lines += [
        f"Доходы:  {format_amount(report.income)}",
        f"Расходы: {format_amount(report.expense)}",
        f"Остаток: {format_amount(report.balance)}{ratio_text}",
    ]

    bar = _bar_lines(report)
    if bar:
        lines += [""] + bar

    if report.expense_by_category:
        lines += ["", "Расходы по категориям:"]
        lines += _category_lines(report.expense_by_category, report.expense)

    if report.income_by_category:
        lines += ["", "Доходы по категориям:"]
        lines += _category_lines(report.income_by_category, report.income)

    return "\n".join(lines)


def _category_lines(by_category: dict[str, float], total: float) -> list[str]:
    lines = []
    for category, amount in sorted(by_category.items(), key=lambda item: item[1], reverse=True):
        share = f" — {amount / total * 100:.0f}%" if total > 0 else ""
        lines.append(f"• {category}: {format_amount(amount)}{share}")
    return lines
