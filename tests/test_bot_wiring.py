"""Проверяем, что запись в таблицу тянет за собой обновление закрепа.

Об этом легко забыть при добавлении нового пути записи, а тесты pinned.py такую
забывчивость не увидят: там бот вызывается напрямую.
"""

import asyncio
import sys
import types

import pytest

import sheets as sheets_module


@pytest.fixture
def bot_module(monkeypatch):
    """bot.py создаёт SheetsClient на импорте, поэтому подменяем клиент до импорта."""
    monkeypatch.setattr(
        sheets_module,
        "SheetsClient",
        lambda: types.SimpleNamespace(
            added=[],
            add_expense=lambda *args: None,
            add_income=lambda *args: None,
        ),
    )
    monkeypatch.delitem(sys.modules, "bot", raising=False)

    import bot

    monkeypatch.setattr(bot.categorizer, "classify", lambda description: "Еда")
    return bot


class RecordingBot:
    pass


class FakeUser:
    id = 1


class FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.from_user = FakeUser()
        self.answers: list[str] = []

    async def answer(self, text, reply_markup=None):
        self.answers.append(text)


def test_expense_refreshes_pinned_report(bot_module, monkeypatch):
    refreshed: list[int] = []

    async def fake_refresh(bot, storage, chat_id):
        refreshed.append(chat_id)

    monkeypatch.setattr(bot_module, "refresh_pinned", fake_refresh)

    message = FakeMessage("кофе 300")
    asyncio.run(bot_module.handle_message(message, RecordingBot()))

    assert message.answers, "пользователь должен получить подтверждение"
    assert refreshed == [bot_module.TELEGRAM_USER_ID]
