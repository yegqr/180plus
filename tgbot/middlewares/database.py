from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.repo.requests import RequestsRepo


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker) -> None:
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_pool() as session:
            repo = RequestsRepo(session)
            user = await repo.users.get_or_create_user(
                event.from_user.id,
                event.from_user.full_name,
                event.from_user.language_code,
                is_admin=event.from_user.id in data["config"].tg_bot.admin_ids,
                username=event.from_user.username,
            )
            data["session"] = session
            data["repo"] = repo
            data["user"] = user
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
