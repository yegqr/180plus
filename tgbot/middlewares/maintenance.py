from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from infrastructure.database.repo.requests import RequestsRepo

logger = logging.getLogger(__name__)

_CACHE_TTL = 30.0  # seconds — how long to cache the maintenance_mode setting


class MaintenanceMiddleware(BaseMiddleware):
    """
    Blocks non-admin users when maintenance_mode is enabled.

    The maintenance_mode DB setting is cached for _CACHE_TTL seconds to avoid
    a DB round-trip on every incoming event.
    """

    def __init__(self) -> None:
        self._cached_mode: bool = False
        self._cache_ts: float = 0.0

    async def _get_maintenance_mode(self, repo: RequestsRepo) -> bool:
        now = time.monotonic()
        if now - self._cache_ts > _CACHE_TTL:
            value = await repo.settings.get_setting("maintenance_mode", "false")
            self._cached_mode = (value or "false").lower() == "true"
            self._cache_ts = now
        return self._cached_mode

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        repo: RequestsRepo = data.get("repo")
        if not repo:
            return await handler(event, data)

        if not await self._get_maintenance_mode(repo):
            return await handler(event, data)

        # data["user"] is the SQLAlchemy User object injected by DatabaseMiddleware
        db_user = data.get("user")
        if not db_user:
            return await handler(event, data)

        config = data.get("config")
        is_admin = db_user.user_id in config.tg_bot.admin_ids or db_user.is_admin
        if is_admin:
            return await handler(event, data)

        m_msg = await repo.settings.get_setting("maintenance_message") or (
            "⛔️ <b>Вибачте, в нас технічні роботи в боті.</b>\n"
            "Найближчим часом запустимо бота з оновленнями!"
        )

        if isinstance(event, Message):
            await event.answer(m_msg)
        elif isinstance(event, CallbackQuery):
            await event.answer(m_msg, show_alert=True)

        return  # stop propagation
