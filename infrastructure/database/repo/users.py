from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert

from infrastructure.database.models import User
from infrastructure.database.repo.base import BaseRepo


class UserRepo(BaseRepo):
    async def get_or_create_user(
        self,
        user_id: int,
        full_name: str,
        language: str,
        is_admin: bool = False,
        username: str | None = None,
    ) -> User:
        """Creates or updates a user and returns the User object."""
        stmt = insert(User).values(
            user_id=user_id,
            username=username,
            full_name=full_name,
            language=language,
            is_admin=is_admin,
        )
        insert_stmt = stmt.on_conflict_do_update(
            index_elements=[User.user_id],
            set_=dict(
                username=username,
                full_name=full_name,
                is_admin=stmt.excluded.is_admin if is_admin else User.is_admin,
                updated_at=func.now(),
            ),
        ).returning(User)

        result = await self.session.execute(insert_stmt)
        return result.scalar_one()

    async def update_subject(self, user_id: int, subject: str) -> None:
        stmt = update(User).where(User.user_id == user_id).values(selected_subject=subject)
        await self.session.execute(stmt)

    async def promote_admin(self, user_id: int) -> None:
        stmt = update(User).where(User.user_id == user_id).values(is_admin=True)
        await self.session.execute(stmt)

    async def demote_admin(self, user_id: int) -> None:
        stmt = update(User).where(User.user_id == user_id).values(is_admin=False)
        await self.session.execute(stmt)

    async def get_admins(self) -> Sequence[User]:
        stmt = select(User).where(User.is_admin == True)  # noqa: E712
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_user_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_stats(self) -> dict[str, int]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        today_start = datetime(now.year, now.month, now.day)
        week_start = today_start - timedelta(days=7)

        total = (await self.session.execute(select(func.count(User.user_id)))).scalar() or 0
        today = (
            await self.session.execute(
                select(func.count(User.user_id)).where(User.updated_at >= today_start)
            )
        ).scalar() or 0
        week = (
            await self.session.execute(
                select(func.count(User.user_id)).where(User.updated_at >= week_start)
            )
        ).scalar() or 0

        return {"total": total, "today": today, "week": week}

    async def update_user_settings(self, user_id: int, settings: dict[str, Any]) -> None:
        stmt = update(User).where(User.user_id == user_id).values(settings=settings)
        await self.session.execute(stmt)

    async def get_users_with_settings(self, user_ids: list[int]) -> Sequence[User]:
        """Returns full User objects for the given IDs (includes settings for per-thread broadcasts)."""
        if not user_ids:
            return []
        stmt = select(User).where(User.user_id.in_(user_ids))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_users_for_broadcast(self, filter_type: str) -> list[int]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        today_start = datetime(now.year, now.month, now.day)

        stmt = select(User.user_id)

        if filter_type == "all":
            stmt = stmt.where(User.active == True)  # noqa: E712
        elif filter_type == "active_today":
            stmt = stmt.where(User.updated_at >= today_start, User.active == True)  # noqa: E712
        elif filter_type == "active_week":
            week_start = today_start - timedelta(days=7)
            stmt = stmt.where(User.updated_at >= week_start, User.active == True)  # noqa: E712
        elif filter_type == "active_month":
            month_start = today_start - timedelta(days=30)
            stmt = stmt.where(User.updated_at >= month_start, User.active == True)  # noqa: E712
        else:
            ranges: dict[str, tuple[int, int]] = {
                "inactive_1_2":   (1,  2),
                "inactive_3_6":   (3,  6),
                "inactive_7_13":  (7,  13),
                "inactive_14_20": (14, 20),
                "inactive_21_27": (21, 27),
            }
            if filter_type in ranges:
                start_days, end_days = ranges[filter_type]
                upper_bound = today_start - timedelta(days=start_days) + timedelta(days=1)
                lower_bound = today_start - timedelta(days=end_days)
                stmt = stmt.where(
                    and_(User.updated_at < upper_bound, User.updated_at >= lower_bound)
                )
            elif filter_type == "inactive_28_plus":
                threshold = today_start - timedelta(days=28)
                stmt = stmt.where(User.updated_at < threshold)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
