from __future__ import annotations

import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from infrastructure.database.models import PendingJoinRequest
from infrastructure.database.repo.base import BaseRepo


class JoinRequestsRepo(BaseRepo):
    async def add_request(self, user_id: int, chat_id: int) -> None:
        stmt = insert(PendingJoinRequest).values(
            user_id=user_id, chat_id=chat_id
        ).on_conflict_do_nothing()
        await self.session.execute(stmt)

    async def get_all_requests(self) -> list[tuple[int, int]]:
        stmt = select(PendingJoinRequest.user_id, PendingJoinRequest.chat_id)
        result = await self.session.execute(stmt)
        return list(result.all())

    async def delete_request(self, user_id: int, chat_id: int) -> None:
        stmt = delete(PendingJoinRequest).where(
            PendingJoinRequest.user_id == user_id,
            PendingJoinRequest.chat_id == chat_id,
        )
        await self.session.execute(stmt)

    async def clear_all(self) -> None:
        stmt = delete(PendingJoinRequest)
        await self.session.execute(stmt)

    async def get_old_requests(self, minutes: int = 3) -> list[tuple[int, int]]:
        """Returns (user_id, chat_id) for requests older than `minutes`."""
        cutoff = func.now() - datetime.timedelta(minutes=minutes)
        stmt = select(PendingJoinRequest.user_id, PendingJoinRequest.chat_id).where(
            PendingJoinRequest.created_at < cutoff
        )
        result = await self.session.execute(stmt)
        return list(result.all())
