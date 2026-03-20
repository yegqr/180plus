from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import func, select, update

from infrastructure.database.models.daily_participation import DailyParticipation
from infrastructure.database.repo.base import BaseRepo


class DailyParticipationRepo(BaseRepo):
    async def record_sent(
        self,
        user_id: int,
        question_id: int,
        subject: str,
        date: datetime.date,
    ) -> None:
        """
        Records that the daily challenge was sent to a user.
        Uses ON CONFLICT DO NOTHING so re-sends on the same day are idempotent.
        """
        from sqlalchemy.dialects.postgresql import insert
        stmt = (
            insert(DailyParticipation)
            .values(
                user_id=user_id,
                question_id=question_id,
                subject=subject,
                date=date,
            )
            .on_conflict_do_nothing(constraint="uq_daily_participation_user_date")
        )
        await self.session.execute(stmt)

    async def record_answer(
        self,
        user_id: int,
        question_id: int,
        answer: str,
        is_correct: bool,
    ) -> None:
        """Fills in the answer fields for today's participation record."""
        today = datetime.date.today()
        stmt = (
            update(DailyParticipation)
            .where(
                DailyParticipation.user_id == user_id,
                DailyParticipation.question_id == question_id,
                DailyParticipation.date == today,
                DailyParticipation.answered_at.is_(None),
            )
            .values(
                answered_at=func.now(),
                answer=str(answer),
                is_correct=is_correct,
            )
        )
        await self.session.execute(stmt)

    async def get_stats_for_date(self, date: datetime.date) -> dict[str, Any]:
        """Returns sent/answered/correct counts for a specific date."""
        sent = (
            await self.session.execute(
                select(func.count(DailyParticipation.id)).where(
                    DailyParticipation.date == date
                )
            )
        ).scalar() or 0

        answered = (
            await self.session.execute(
                select(func.count(DailyParticipation.id)).where(
                    DailyParticipation.date == date,
                    DailyParticipation.answered_at.is_not(None),
                )
            )
        ).scalar() or 0

        correct = (
            await self.session.execute(
                select(func.count(DailyParticipation.id)).where(
                    DailyParticipation.date == date,
                    DailyParticipation.is_correct.is_(True),
                )
            )
        ).scalar() or 0

        rate = round(answered / sent * 100) if sent else 0
        return {
            "sent": sent,
            "answered": answered,
            "correct": correct,
            "rate": rate,
        }

    async def get_all_for_export(self) -> list[DailyParticipation]:
        from sqlalchemy import desc
        stmt = select(DailyParticipation).order_by(desc(DailyParticipation.sent_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
