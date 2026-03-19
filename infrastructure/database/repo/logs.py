from __future__ import annotations

from typing import Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert

from infrastructure.database.models import UserActionLog
from infrastructure.database.repo.base import BaseRepo


class LogsRepo(BaseRepo):
    async def add_log(
        self,
        user_id: int,
        question_id: int,
        answer: str,
        is_correct: bool,
        mode: str,
        session_id: str | None = None,
    ) -> None:
        stmt = insert(UserActionLog).values(
            user_id=user_id,
            question_id=question_id,
            answer=str(answer),
            is_correct=is_correct,
            mode=mode,
            session_id=session_id,
        )
        await self.session.execute(stmt)

    async def add_logs_batch(self, logs: list[dict]) -> None:
        if not logs:
            return
        stmt = insert(UserActionLog).values(logs)
        await self.session.execute(stmt)

    async def get_question_history(
        self, user_id: int, question_id: int, limit: int = 5
    ) -> list[str]:
        """Returns list of past answers for this user/question (newest first)."""
        stmt = (
            select(UserActionLog.answer)
            .where(UserActionLog.user_id == user_id, UserActionLog.question_id == question_id)
            .order_by(desc(UserActionLog.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [row.answer for row in result.all()]

    async def get_question_failures_count(self, user_id: int, question_id: int) -> int:
        """Returns number of times user answered this question incorrectly."""
        stmt = select(func.count(UserActionLog.id)).where(
            UserActionLog.user_id == user_id,
            UserActionLog.question_id == question_id,
            UserActionLog.is_correct == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_failed_questions_in_last_sim(
        self, user_id: int, session_id: str
    ) -> list[int]:
        """
        Returns question IDs that are currently 'failed' for this session.
        For each question, looks at the LATEST log entry:
          - Latest Incorrect → failure
          - Latest Correct   → resolved
          - No entry         → not a failure
        """
        stmt = (
            select(UserActionLog.question_id, UserActionLog.is_correct)
            .distinct(UserActionLog.question_id)
            .where(
                UserActionLog.user_id == user_id,
                UserActionLog.session_id == session_id,
                UserActionLog.answer != None,  # noqa: E711
                UserActionLog.answer != "",
                UserActionLog.answer != "None",
                UserActionLog.answer != "немає",
            )
            .order_by(UserActionLog.question_id, desc(UserActionLog.created_at))
        )
        result = await self.session.execute(stmt)
        return [row.question_id for row in result.all() if not row.is_correct]

    async def get_all_logs(self) -> Sequence[UserActionLog]:
        stmt = select(UserActionLog).order_by(desc(UserActionLog.created_at))
        result = await self.session.execute(stmt)
        return result.scalars().all()
