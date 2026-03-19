from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import Question


class QuestionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _update_question_fields(
        existing: Question,
        image_file_ids: list[str],
        q_type: str,
        correct_answer: dict,
        weight: int,
    ) -> None:
        """Merges new image IDs into the existing question and refreshes metadata."""
        current: list[str] = list(existing.images) if existing.images else []
        for img_id in image_file_ids:
            if img_id and img_id not in current:
                current.append(img_id)
        existing.images = current
        if not existing.image_file_id:
            existing.image_file_id = current[0] if current else None
        existing.q_type = q_type
        existing.correct_answer = correct_answer
        existing.weight = weight

    async def upsert_question(
        self,
        subject: str,
        year: int,
        session: str,
        q_number: int,
        image_file_ids: list[str],
        q_type: str,
        correct_answer: dict,
        weight: int,
        **kwargs,
    ) -> None:
        """Insert or update a question. image_file_ids: list of file_ids to attach."""
        result = await self.session.execute(
            select(Question)
            .where(
                Question.year == year,
                Question.session == session,
                Question.q_number == q_number,
                Question.subject == subject,
            )
            .with_for_update()
        )
        existing = result.scalar_one_or_none()

        if existing:
            self._update_question_fields(existing, image_file_ids, q_type, correct_answer, weight)
        else:
            self.session.add(
                Question(
                    subject=subject,
                    year=year,
                    session=session,
                    q_number=q_number,
                    image_file_id=image_file_ids[0] if image_file_ids else None,
                    images=image_file_ids if image_file_ids else [],
                    q_type=q_type,
                    correct_answer=correct_answer,
                    weight=weight,
                    explanation=kwargs.get("explanation"),
                    categories=kwargs.get("categories"),
                )
            )
        await self.session.commit()

    async def update_explanation(self, question_id: int, text: str) -> None:
        stmt = select(Question).where(Question.id == question_id)
        result = await self.session.execute(stmt)
        question = result.scalar_one_or_none()
        if question:
            question.explanation = text
            await self.session.commit()

    async def update_categories(self, question_id: int, categories: list[str]) -> None:
        stmt = select(Question).where(Question.id == question_id)
        result = await self.session.execute(stmt)
        question = result.scalar_one_or_none()
        if question:
            question.categories = categories
            await self.session.commit()

    async def get_questions_ids_by_subject(self, subject: str) -> list[int]:
        """Returns question IDs for a subject, ordered by year/session/number."""
        stmt = (
            select(Question.id)
            .where(Question.subject == subject)
            .order_by(Question.year, Question.session, Question.q_number)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_question_by_id(self, question_id: int) -> Question | None:
        stmt = select(Question).where(Question.id == question_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unique_years(self, subject: str) -> list[int]:
        stmt = (
            select(Question.year)
            .where(Question.subject == subject)
            .distinct()
            .order_by(Question.year.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_unique_sessions(self, subject: str, year: int) -> list[str]:
        stmt = (
            select(Question.session)
            .where(Question.subject == subject, Question.year == year)
            .group_by(Question.session)
            .order_by(func.min(Question.id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_questions_by_criteria(
        self, subject: str, year: int, session: str
    ) -> list[Question]:
        stmt = (
            select(Question)
            .where(
                Question.subject == subject,
                Question.year == year,
                Question.session == session,
            )
            .order_by(Question.q_number)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_question(self, question_id: int) -> None:
        question = await self.get_question_by_id(question_id)
        if question:
            await self.session.delete(question)
            await self.session.commit()

    async def delete_questions_by_session(
        self, subject: str, year: int, session: str
    ) -> None:
        stmt = delete(Question).where(
            Question.subject == subject,
            Question.year == year,
            Question.session == session,
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def update_session_metadata(
        self,
        old_subject: str,
        old_year: int,
        old_session: str,
        new_year: int | None = None,
        new_session: str | None = None,
    ) -> None:
        """Updates year/session name for all questions in a session."""
        values: dict = {}
        if new_year is not None:
            values["year"] = new_year
        if new_session is not None:
            values["session"] = new_session
        if not values:
            return
        stmt = (
            update(Question)
            .where(
                Question.subject == old_subject,
                Question.year == old_year,
                Question.session == old_session,
            )
            .values(**values)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_random_question(
        self, subjects: list[str], q_type: str | None = "choice"
    ) -> Question | None:
        """Returns a random question from given subjects, filtered by type."""
        stmt = select(Question).where(Question.subject.in_(subjects))
        if q_type:
            stmt = stmt.where(Question.q_type == q_type)
        stmt = stmt.order_by(func.random()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
