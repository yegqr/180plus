from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import func, select, text

from infrastructure.database.models import JoinStat, Question
from infrastructure.database.repo.base import BaseRepo


class StatsRepo(BaseRepo):
    async def add_join_stat(self, user_id: int, source: str) -> None:
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(JoinStat).values(user_id=user_id, source=source)
        await self.session.execute(stmt)

    async def get_weekly_stats(self, week_offset: int = 0) -> list[dict[str, Any]]:
        """
        Returns UTM stats for a specific week.
        week_offset=0 → current week, week_offset=1 → last week.
        """
        today = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        start_of_week = today - datetime.timedelta(days=today.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        target_start = start_of_week - datetime.timedelta(weeks=week_offset)
        target_end = target_start + datetime.timedelta(days=7)

        stmt = (
            select(JoinStat.source, func.count(JoinStat.id).label("count"))
            .where(JoinStat.created_at >= target_start, JoinStat.created_at < target_end)
            .group_by(JoinStat.source)
            .order_by(text("count DESC"))
        )
        result = await self.session.execute(stmt)
        return [{"source": row.source, "count": row.count} for row in result.all()]

    async def get_content_stats(self) -> list[dict[str, Any]]:
        """Returns question count per subject."""
        stmt = (
            select(Question.subject, func.count(Question.id).label("count"))
            .group_by(Question.subject)
        )
        result = await self.session.execute(stmt)
        return [{"subject": row.subject, "count": row.count} for row in result.all()]

    async def get_daily_activity_stats(self) -> dict[str, Any]:
        """Returns today's simulation and random-question counts per subject."""
        from infrastructure.database.models import ExamResult, RandomResult

        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        today_start = datetime.datetime(now.year, now.month, now.day)

        sim_result = await self.session.execute(
            select(ExamResult.subject, func.count(ExamResult.id).label("count"))
            .where(ExamResult.created_at >= today_start)
            .group_by(ExamResult.subject)
        )
        sim_stats: dict[str, int] = {row.subject: row.count for row in sim_result.all()}

        rand_result = await self.session.execute(
            select(RandomResult.subject, func.count(RandomResult.id).label("count"))
            .where(RandomResult.created_at >= today_start)
            .group_by(RandomResult.subject)
        )
        rand_stats: dict[str, int] = {row.subject: row.count for row in rand_result.all()}

        return {
            "simulations": sim_stats,
            "random":      rand_stats,
            "total_sims":  sum(sim_stats.values()),
            "total_rand":  sum(rand_stats.values()),
        }

    async def get_abandoned_stats(self) -> dict[str, int]:
        """
        Approximates abandoned simulations.
        Started  = distinct (user_id, session_id) pairs in UserActionLog with mode=simulation today.
        Completed = ExamResult count today.
        Abandoned = max(0, started - completed).
        """
        from infrastructure.database.models import UserActionLog, ExamResult

        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        today_start = datetime.datetime(now.year, now.month, now.day)

        started_rows = await self.session.execute(
            select(UserActionLog.user_id, UserActionLog.session_id)
            .where(
                UserActionLog.mode == "simulation",
                UserActionLog.session_id.is_not(None),
                UserActionLog.created_at >= today_start,
            )
            .distinct()
        )
        started = len(started_rows.all())

        completed = (
            await self.session.execute(
                select(func.count(ExamResult.id)).where(ExamResult.created_at >= today_start)
            )
        ).scalar() or 0

        return {
            "started": started,
            "completed": int(completed),
            "abandoned": max(0, started - int(completed)),
        }
