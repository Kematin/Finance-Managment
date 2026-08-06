import asyncio
import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from categorizer import get_categorizer
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID
from sheets import SheetsClient

categorizer = get_categorizer()
sheets = SheetsClient()
dp = Dispatcher()
dp.message.filter(F.from_user.id == TELEGRAM_USER_ID)
dp.callback_query.filter(F.from_user.id == TELEGRAM_USER_ID)

AMOUNT_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(тысяч[аи]?|тыс\.?|к|k)?", re.IGNORECASE)

AMOUNT_MULTIPLIERS = {
    "к": 1000,
    "k": 1000,
    "тыс": 1000,
    "тыс.": 1000,
    "тысяча": 1000,
    "тысячи": 1000,
}

# user_id -> {"description": str, "amount": float, "is_income": bool}
pending: dict[int, dict] = {}


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "Пиши трату или доход в формате: <описание> <сумма>\n"
        "Например: кофе 300\n"
        "Отрицательная сумма считается доходом."
    )


def parse_entry(text: str) -> tuple[str, float] | None:
    match = AMOUNT_RE.search(text)
    if not match:
        return None
    amount = float(match.group(1).replace(",", "."))
    suffix = (match.group(2) or "").lower().rstrip(".")
    amount *= AMOUNT_MULTIPLIERS.get(suffix, 1)
    description = (text[: match.start()] + text[match.end() :]).strip()
    if not description:
        return None
    return description, amount


def format_amount(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ") if amount == int(amount) else f"{amount:,.2f}".replace(",", " ")


def build_category_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in options:
        builder.button(text=category, callback_data=category)
    builder.adjust(1)
    return builder.as_markup()


@dp.message(F.text)
async def handle_message(message: Message) -> None:
    parsed = parse_entry(message.text)
    if parsed is None:
        await message.answer("Не понял. Формат: <описание> <сумма>, например: кофе 300")
        return

    description, amount = parsed
    is_income = amount < 0
    amount = abs(amount)

    if is_income:
        await ask_category(message, description, amount, INCOME_CATEGORIES, is_income=True)
        return

    category = categorizer.classify(description)
    if category is None:
        await ask_category(message, description, amount, EXPENSE_CATEGORIES, is_income=False)
        return

    sheets.add_expense(description, amount, category)
    await message.answer(f"Записал: {description} — {format_amount(amount)} — {category}")


async def ask_category(
    message: Message,
    description: str,
    amount: float,
    options: list[str],
    is_income: bool,
) -> None:
    pending[message.from_user.id] = {
        "description": description,
        "amount": amount,
        "is_income": is_income,
    }
    await message.answer(
        f"{description} — {format_amount(amount)}. Выбери категорию:",
        reply_markup=build_category_keyboard(options),
    )


@dp.callback_query()
async def handle_category_choice(callback: CallbackQuery) -> None:
    await callback.answer()

    entry = pending.get(callback.from_user.id)
    if entry is None:
        await callback.message.edit_text("Эта запись уже устарела, начни заново.")
        return

    category = callback.data
    if entry["is_income"]:
        sheets.add_income(entry["description"], entry["amount"], category)
    else:
        sheets.add_expense(entry["description"], entry["amount"], category)

    await callback.message.edit_text(
        f"Записал: {entry['description']} — {format_amount(entry['amount'])} — {category}"
    )
    pending.pop(callback.from_user.id, None)


async def main() -> None:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
