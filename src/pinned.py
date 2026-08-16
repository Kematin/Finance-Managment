"""
Закреплённый в чате отчёт за текущий месяц.

Обновляется из двух мест — по дневному тику и после каждой записи — но всегда через
ensure_pinned: только она знает, редактировать существующее сообщение или закрепить
новое. Состояние (id сообщения и его месяц) живёт в таблице, потому что у контейнера
нет своего тома и рестарт стирает всё локальное.

Подробности решения: docs/adr/0001-zakreplyonnyy-otchyot.md
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from report import build_report, format_report
from sheets import Entry

logger = logging.getLogger(__name__)

STATE_MESSAGE_ID = "pinned_message_id"
STATE_PERIOD = "pinned_period"

# Время дневного обновления по локальному времени контейнера (TZ из docker-compose).
UPDATE_AT = time(9, 0)

# Ключ периода из PERIODS: закреп всегда показывает текущий календарный месяц.
REPORT_PERIOD = "month"

# Две записи подряд не должны редактировать одно сообщение параллельно.
_lock = asyncio.Lock()


class Storage(Protocol):
    """То, что pinned требует от хранилища. SheetsClient это удовлетворяет."""

    def fetch_entries(self) -> list[Entry]: ...

    def get_state(self) -> dict[str, str]: ...

    def save_state(self, values: dict[str, str]) -> None: ...


def period_key(today: date) -> str:
    """Месяц, к которому относится закреплённый отчёт."""
    return f"{today.year:04d}-{today.month:02d}"


def seconds_until(now: datetime, at: time) -> float:
    """Секунды до ближайшего наступления времени at (сегодня или завтра)."""
    target = datetime.combine(now.date(), at)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _stored_message_id(state: dict[str, str]) -> int | None:
    raw = state.get(STATE_MESSAGE_ID)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("В состоянии лежит нечисловой message_id: %r", raw)
        return None


async def ensure_pinned(
    bot: Bot,
    storage: Storage,
    chat_id: int,
    today: date | None = None,
) -> None:
    """Приводит закреплённое сообщение в соответствие с текущим месяцем.

    Тот же месяц — редактируем существующее сообщение. Другой месяц, пустое состояние
    или удалённое сообщение — отправляем и закрепляем новое, старое открепляем.
    """
    today = today or date.today()
    current_period = period_key(today)

    async with _lock:
        entries = await asyncio.to_thread(storage.fetch_entries)
        state = await asyncio.to_thread(storage.get_state)
        text = format_report(build_report(entries, REPORT_PERIOD, today))

        message_id = _stored_message_id(state)
        same_period = state.get(STATE_PERIOD) == current_period

        if message_id is not None and same_period and await _edit(bot, chat_id, message_id, text):
            return

        # Открепляем только чужой месяц: если сообщение того же месяца пропало,
        # откреплять уже нечего.
        outdated_message_id = message_id if not same_period else None
        await _repin(bot, storage, chat_id, outdated_message_id, text, current_period)


async def refresh_pinned(bot: Bot, storage: Storage, chat_id: int) -> None:
    """ensure_pinned для вызова из обработчиков: упавший закреп не должен ломать
    подтверждение записи."""
    try:
        await ensure_pinned(bot, storage, chat_id)
    except Exception:
        logger.exception("Не удалось обновить закреплённый отчёт")


async def run_daily_updates(
    bot: Bot,
    storage: Storage,
    chat_id: int,
    at: time = UPDATE_AT,
) -> None:
    """Обновляет закреп при старте и дальше каждый день в заданное время."""
    await refresh_pinned(bot, storage, chat_id)
    while True:
        await asyncio.sleep(seconds_until(datetime.now(), at))
        await refresh_pinned(bot, storage, chat_id)


async def _edit(bot: Bot, chat_id: int, message_id: int, text: str) -> bool:
    """True — сообщение на месте и актуально, False — сообщения больше нет.

    Остальные ошибки Telegram пробрасываем: сообщение при них живо и всё ещё закреплено,
    так что отправлять второе — значит плодить закрепы на каждой неудачной попытке.
    """
    try:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest as error:
        # Текст не изменился с прошлого раза — Telegram считает это ошибкой, мы нет.
        if "message is not modified" in str(error):
            return True
        if "message to edit not found" in str(error):
            logger.info("Закреп %s удалён, отправляем новый", message_id)
            return False
        raise
    return True


async def _repin(
    bot: Bot,
    storage: Storage,
    chat_id: int,
    outdated_message_id: int | None,
    text: str,
    period: str,
) -> None:
    if outdated_message_id is not None:
        try:
            await bot.unpin_chat_message(chat_id=chat_id, message_id=outdated_message_id)
        except TelegramBadRequest as error:
            logger.warning("Старый закреп %s не открепился: %s", outdated_message_id, error)

    # Молчим и на отправке, и на закреплении: иначе 1-го числа прилетает пуш.
    message = await bot.send_message(chat_id=chat_id, text=text, disable_notification=True)
    await bot.pin_chat_message(
        chat_id=chat_id,
        message_id=message.message_id,
        disable_notification=True,
    )
    await asyncio.to_thread(
        storage.save_state,
        {STATE_MESSAGE_ID: str(message.message_id), STATE_PERIOD: period},
    )
