import asyncio
from datetime import date, datetime, time

import pytest
from aiogram.exceptions import TelegramBadRequest

import pinned
from pinned import STATE_MESSAGE_ID, STATE_PERIOD, ensure_pinned, period_key, seconds_until
from sheets import TYPE_EXPENSE, TYPE_INCOME, Entry

CHAT_ID = 42


class FakeMessage:
    def __init__(self, message_id: int):
        self.message_id = message_id


class FakeBot:
    """Минимальный дублёр Bot: запоминает вызовы, ничего не отправляет."""

    def __init__(self, edit_error: Exception | None = None):
        self.sent: list[tuple[int, str, bool]] = []
        self.edited: list[tuple[int, int, str]] = []
        self.pinned: list[tuple[int, int, bool]] = []
        self.unpinned: list[tuple[int, int]] = []
        self._edit_error = edit_error
        self._next_id = 100

    async def send_message(self, chat_id, text, disable_notification=False):
        self._next_id += 1
        self.sent.append((chat_id, text, disable_notification))
        return FakeMessage(self._next_id)

    async def edit_message_text(self, text, chat_id, message_id):
        if self._edit_error is not None:
            raise self._edit_error
        self.edited.append((chat_id, message_id, text))

    async def pin_chat_message(self, chat_id, message_id, disable_notification=False):
        self.pinned.append((chat_id, message_id, disable_notification))

    async def unpin_chat_message(self, chat_id, message_id):
        self.unpinned.append((chat_id, message_id))


class FakeSheets:
    def __init__(self, entries: list[Entry] | None = None, state: dict[str, str] | None = None):
        self._entries = entries or []
        self.state = dict(state or {})

    def fetch_entries(self) -> list[Entry]:
        return list(self._entries)

    def get_state(self) -> dict[str, str]:
        return dict(self.state)

    def save_state(self, values: dict[str, str]) -> None:
        self.state = dict(values)


def bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=None, message=message)


def entries_for(day: date) -> list[Entry]:
    return [
        Entry(day=day, description="зарплата", amount=100.0, category="Зарплата", entry_type=TYPE_INCOME),
        Entry(day=day, description="кофе", amount=30.0, category="Еда", entry_type=TYPE_EXPENSE),
    ]


def test_period_key_is_year_and_month():
    assert period_key(date(2026, 8, 16)) == "2026-08"
    assert period_key(date(2026, 1, 1)) == "2026-01"


def test_seconds_until_later_today():
    now = datetime(2026, 8, 16, 7, 0)
    assert seconds_until(now, time(9, 0)) == 2 * 3600


def test_seconds_until_wraps_to_tomorrow():
    now = datetime(2026, 8, 16, 9, 0, 1)
    assert seconds_until(now, time(9, 0)) == 24 * 3600 - 1


def test_first_run_sends_and_pins():
    today = date(2026, 8, 16)
    bot = FakeBot()
    sheets = FakeSheets(entries=entries_for(today))

    asyncio.run(ensure_pinned(bot, sheets, CHAT_ID, today))

    assert len(bot.sent) == 1
    assert "Август 2026" in bot.sent[0][1]
    # Ни отправка, ни закрепление не должны слать пуш.
    assert bot.sent[0][2] is True
    assert bot.pinned == [(CHAT_ID, 101, True)]
    assert bot.unpinned == []
    assert sheets.state == {STATE_MESSAGE_ID: "101", STATE_PERIOD: "2026-08"}


def test_same_month_edits_existing_message():
    today = date(2026, 8, 16)
    bot = FakeBot()
    sheets = FakeSheets(
        entries=entries_for(today),
        state={STATE_MESSAGE_ID: "77", STATE_PERIOD: "2026-08"},
    )

    asyncio.run(ensure_pinned(bot, sheets, CHAT_ID, today))

    assert bot.sent == []
    assert bot.pinned == []
    assert len(bot.edited) == 1
    assert bot.edited[0][1] == 77
    assert sheets.state == {STATE_MESSAGE_ID: "77", STATE_PERIOD: "2026-08"}


def test_new_month_unpins_old_and_pins_new():
    today = date(2026, 9, 1)
    bot = FakeBot()
    sheets = FakeSheets(
        entries=entries_for(today),
        state={STATE_MESSAGE_ID: "77", STATE_PERIOD: "2026-08"},
    )

    asyncio.run(ensure_pinned(bot, sheets, CHAT_ID, today))

    assert bot.edited == []
    assert bot.unpinned == [(CHAT_ID, 77)]
    assert len(bot.sent) == 1
    assert "Сентябрь 2026" in bot.sent[0][1]
    assert sheets.state == {STATE_MESSAGE_ID: "101", STATE_PERIOD: "2026-09"}


def test_deleted_message_is_replaced():
    today = date(2026, 8, 16)
    bot = FakeBot(edit_error=bad_request("message to edit not found"))
    sheets = FakeSheets(
        entries=entries_for(today),
        state={STATE_MESSAGE_ID: "77", STATE_PERIOD: "2026-08"},
    )

    asyncio.run(ensure_pinned(bot, sheets, CHAT_ID, today))

    assert len(bot.sent) == 1
    assert bot.pinned == [(CHAT_ID, 101, True)]
    assert sheets.state == {STATE_MESSAGE_ID: "101", STATE_PERIOD: "2026-08"}


def test_unchanged_text_is_not_an_error():
    today = date(2026, 8, 16)
    bot = FakeBot(edit_error=bad_request("Bad Request: message is not modified"))
    sheets = FakeSheets(
        entries=entries_for(today),
        state={STATE_MESSAGE_ID: "77", STATE_PERIOD: "2026-08"},
    )

    asyncio.run(ensure_pinned(bot, sheets, CHAT_ID, today))

    assert bot.sent == []
    assert bot.pinned == []
    assert sheets.state == {STATE_MESSAGE_ID: "77", STATE_PERIOD: "2026-08"}


def test_other_edit_errors_do_not_create_second_pin():
    """Сообщение живо и закреплено — второй закреп на каждой неудаче хуже, чем ошибка."""
    today = date(2026, 8, 16)
    bot = FakeBot(edit_error=bad_request("Bad Request: message can't be edited"))
    sheets = FakeSheets(
        entries=entries_for(today),
        state={STATE_MESSAGE_ID: "77", STATE_PERIOD: "2026-08"},
    )

    with pytest.raises(TelegramBadRequest):
        asyncio.run(ensure_pinned(bot, sheets, CHAT_ID, today))

    assert bot.sent == []
    assert bot.pinned == []
    assert sheets.state == {STATE_MESSAGE_ID: "77", STATE_PERIOD: "2026-08"}


def test_broken_state_is_recovered():
    today = date(2026, 8, 16)
    bot = FakeBot()
    sheets = FakeSheets(
        entries=entries_for(today),
        state={STATE_MESSAGE_ID: "мусор", STATE_PERIOD: "2026-08"},
    )

    asyncio.run(ensure_pinned(bot, sheets, CHAT_ID, today))

    assert len(bot.sent) == 1
    assert bot.unpinned == []
    assert sheets.state == {STATE_MESSAGE_ID: "101", STATE_PERIOD: "2026-08"}


def test_refresh_swallows_errors():
    class ExplodingSheets(FakeSheets):
        def fetch_entries(self):
            raise RuntimeError("Sheets недоступны")

    asyncio.run(pinned.refresh_pinned(FakeBot(), ExplodingSheets(), CHAT_ID))
