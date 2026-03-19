import datetime
from typing import List, Dict, Any

from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert

from infrastructure.database.models import JoinStat, Question
from infrastructure.database.repo.base import BaseRepo


class StatsRepo(BaseRepo):
    async def add_join_stat(self, user_id: int, source: str):
        stmt = insert(JoinStat).values(user_id=user_id, source=source)
        # We don't really care about conflicts here, just log everything? 
        # Actually user might join multiple times (leave/join), so we just insert.
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_weekly_stats(self, week_offset: int = 0) -> List[Dict[str, Any]]:
        """
        Returns stats for a specific week.
        week_offset=0 -> Current week
        week_offset=1 -> Last week
        """
        # Calculate start and end of the target week
        today = datetime.datetime.utcnow()
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

    async def get_content_stats(self) -> List[Dict[str, Any]]:
        """
        Returns breakdown of tests (questions) per subject.
        Using Session+Subject as a 'Test' usually, but user asked for "Tests eng".
        If "Test" means "Session", we count unique sessions.
        If "Test" means "Question", we count questions.
        User said "Заголом тестів - тестів eng ...". 
        I'll return count of QUESTIONS per subject for now as a proxy.
        Or better: Count of unique (Year, Session, Subject) tuples?
        Let's give both: Total Questions.
        """
        stmt = (
            select(Question.subject, func.count(Question.id).label("count"))
            .group_by(Question.subject)
        )
        result = await self.session.execute(stmt)
        return [{"subject": row.subject, "count": row.count} for row in result.all()]

    async def get_daily_activity_stats(self) -> Dict[str, Any]:
        """
        Returns stats for simulations and random questions for TODAY.
        """
        from infrastructure.database.models import ExamResult, RandomResult
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        
        # 1. Simulations today
        sim_stmt = (
            select(ExamResult.subject, func.count(ExamResult.id).label("count"))
            .where(ExamResult.created_at >= today_start)
            .group_by(ExamResult.subject)
        )
        sim_result = await self.session.execute(sim_stmt)
        sim_stats = {row.subject: row.count for row in sim_result.all()}
        
        # 2. Random questions today
        rand_stmt = (
            select(RandomResult.subject, func.count(RandomResult.id).label("count"))
            .where(RandomResult.created_at >= today_start)
            .group_by(RandomResult.subject)
        )
        rand_result = await self.session.execute(rand_stmt)
        rand_stats = {row.subject: row.count for row in rand_result.all()}
        
        return {
            "simulations": sim_stats,
            "random": rand_stats,
            "total_sims": sum(sim_stats.values()),
            "total_rand": sum(rand_stats.values())
        }
