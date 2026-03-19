from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, text, desc
from sqlalchemy.dialects.postgresql import insert

from infrastructure.database.models import UserActionLog
from infrastructure.database.repo.base import BaseRepo


class LogsRepo(BaseRepo):
    async def add_log(self, user_id: int, question_id: int, answer: str, is_correct: bool, mode: str, session_id: str = None):
        stmt = insert(UserActionLog).values(
            user_id=user_id,
            question_id=question_id,
            answer=str(answer),
            is_correct=is_correct,
            mode=mode,
            session_id=session_id
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def add_logs_batch(self, logs: List[Dict]):
        if not logs: return
        stmt = insert(UserActionLog).values(logs)
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_question_history(self, user_id: int, question_id: int, limit: int = 5) -> List[str]:
        """Returns list of past answers for this user/question."""
        stmt = (
            select(UserActionLog.answer)
            .where(UserActionLog.user_id == user_id, UserActionLog.question_id == question_id)
            .order_by(desc(UserActionLog.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [row.answer for row in result.all()]

    async def get_question_failures_count(self, user_id: int, question_id: int) -> int:
        """Returns number of times user failed this question."""
        stmt = (
            select(func.count(UserActionLog.id))
            .where(
                UserActionLog.user_id == user_id, 
                UserActionLog.question_id == question_id,
                UserActionLog.is_correct == False
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_failed_questions_in_last_sim(self, user_id: int, session_id: str) -> List[int]:
        """
        Returns list of Question IDs that were failed in the LAST run of this session_id.
        Since we don't have a 'run_id', we assume 'last run' means logs created within a short window 
        of the most recent log for this session? Or we just check all failures?
        
        Better: Find the most recent timestamp for this session, then find failures around that time.
        Or: Just return ALL distinct question IDs failed in this session ever? The user said "Previous time ... you failed in 1, 2".
        If they ran it 10 times, listing all failures is too much.
        Let's try to identify the 'last run'. 
        
        Alternative: Group logs by created_at (minute precision) and take the last group?
        
        Simplification: We will store the full list of errors in `DialogData` during the run.
        But for persistent advice "You failed Q2 last time", we need DB.
        
        Let's just take the last 50 logs for this session_id and user, 
        sorted by time desc. Filter those that belong to the "latest cluster" (e.g. within 60 mins of the very last log).
        Then check which were incorrect.
        """
    async def get_failed_questions_in_last_sim(self, user_id: int, session_id: str) -> List[int]:
        """
        Returns list of Question IDs that are CURRENTLY considered 'failed' for this session.
        Logic: For each question in the session, look at the LATEST log entry.
        If the latest entry is Incorrect -> It's a failure.
        If the latest entry is Correct -> It's resolved.
        If no entry -> Not a failure.
        """
        stmt = (
            select(UserActionLog.question_id, UserActionLog.is_correct)
            .distinct(UserActionLog.question_id)
            .where(
                UserActionLog.user_id == user_id, 
                UserActionLog.session_id == session_id,
                # Ignore skips/empty answers (they shouldn't count as failures)
                UserActionLog.answer != None,
                UserActionLog.answer != "",
                UserActionLog.answer != "None",
                UserActionLog.answer != "немає"
            )
            .order_by(UserActionLog.question_id, desc(UserActionLog.created_at))
        )
        
        result = await self.session.execute(stmt)
        # Filter only those where is_correct is False
        failed_ids = [row.question_id for row in result.all() if not row.is_correct]
        return failed_ids

    async def get_all_logs(self):
        stmt = select(UserActionLog).order_by(desc(UserActionLog.created_at))
        result = await self.session.execute(stmt)
        return result.scalars().all()
