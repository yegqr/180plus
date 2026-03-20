from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import func, select

from infrastructure.database.models.events import UserEvent
from infrastructure.database.repo.base import BaseRepo


class EventRepo(BaseRepo):
    async def log_event(
        self,
        user_id: int,
        event_type: str,
        payload: dict | None = None,
    ) -> None:
        """Fire-and-forget: never raises, always swallows exceptions."""
        try:
            from sqlalchemy.dialects.postgresql import insert
            stmt = insert(UserEvent).values(
                user_id=user_id,
                event_type=event_type,
                payload=json.dumps(payload, ensure_ascii=False) if payload else None,
            )
            await self.session.execute(stmt)
        except Exception:
            pass

    async def get_counts_today(self) -> dict[str, int]:
        """Returns count per event_type for today."""
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        today_start = datetime.datetime(now.year, now.month, now.day)
        stmt = (
            select(UserEvent.event_type, func.count(UserEvent.id).label("cnt"))
            .where(UserEvent.created_at >= today_start)
            .group_by(UserEvent.event_type)
        )
        result = await self.session.execute(stmt)
        return {row.event_type: row.cnt for row in result.all()}

    async def get_all_for_export(self) -> list[UserEvent]:
        from sqlalchemy import desc
        stmt = select(UserEvent).order_by(desc(UserEvent.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
