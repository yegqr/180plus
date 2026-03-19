from typing import List, Tuple
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from infrastructure.database.models import PendingJoinRequest
from infrastructure.database.repo.base import BaseRepo


class JoinRequestsRepo(BaseRepo):
    async def add_request(self, user_id: int, chat_id: int):
        stmt = insert(PendingJoinRequest).values(user_id=user_id, chat_id=chat_id)
        update_stmt = stmt.on_conflict_do_nothing()
        await self.session.execute(update_stmt)
        await self.session.commit()

    async def get_all_requests(self) -> List[Tuple[int, int]]:
        stmt = select(PendingJoinRequest.user_id, PendingJoinRequest.chat_id)
        result = await self.session.execute(stmt)
        return result.all()

    async def delete_request(self, user_id: int, chat_id: int):
        stmt = delete(PendingJoinRequest).where(
            PendingJoinRequest.user_id == user_id,
            PendingJoinRequest.chat_id == chat_id
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def clear_all(self):
        stmt = delete(PendingJoinRequest)
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_old_requests(self, minutes: int = 3) -> List[Tuple[int, int]]:
        """
        Returns (user_id, chat_id) for requests older than `minutes`.
        """
        import datetime
        from sqlalchemy import func
        
        # Use DB time to avoid timezone mismatch between Python and Postgres
        cutoff = func.now() - datetime.timedelta(minutes=minutes)
        
        stmt = select(PendingJoinRequest.user_id, PendingJoinRequest.chat_id).where(
            PendingJoinRequest.created_at < cutoff
        )
        result = await self.session.execute(stmt)
        return result.all()
