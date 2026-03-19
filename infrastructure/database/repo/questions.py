from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import Question

class QuestionRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_question(self, subject: str, year: int, session: str, q_number: int,
                              image_file_ids: list[str], q_type: str, correct_answer: dict, weight: int, **kwargs):
        """
        Insert or update a question.
        image_file_ids: List of file_ids to be attached.
        """

        # Verify existing question
        existing_stmt = select(Question).where(
            Question.year == year,
            Question.session == session,
            Question.q_number == q_number,
            Question.subject == subject
        ).with_for_update()
        result = await self.session.execute(existing_stmt)
        existing = result.scalar_one_or_none()
        
        # Determine primary image (first one)
        primary_image_id = image_file_ids[0] if image_file_ids else None

        if existing:
            # Append new images if provided and not already present
            current_images = list(existing.images) if existing.images else []
            
            # Add all new unique images
            for img_id in image_file_ids:
                if img_id and img_id not in current_images:
                    current_images.append(img_id)
            
            existing.images = current_images
            
            # If we didn't have a primary image before, set it now
            if not existing.image_file_id and primary_image_id:
                existing.image_file_id = primary_image_id
            # Optionally update primary image to the latest uploaded? 
            # Let's keep existing behavior: preserve original unless empty?
            # Or if we want to support "editing" the main image, we might need more logic.
            # For now, let's say if we upload new stuff, we append.
            # If existing.image_file_id is strangely missing but we have images, fix it.
            if current_images and not existing.image_file_id:
                existing.image_file_id = current_images[0]

            existing.q_type = q_type
            existing.correct_answer = correct_answer
            existing.weight = weight
        else:
            self.session.add(Question(
                subject=subject,
                year=year,
                session=session,
                q_number=q_number,
                image_file_id=primary_image_id,
                images=image_file_ids if image_file_ids else [],
                q_type=q_type,
                correct_answer=correct_answer,
                weight=weight,
                explanation=kwargs.get("explanation"),
                categories=kwargs.get("categories")
            ))
        await self.session.commit()

    async def update_explanation(self, question_id: int, text: str):
        stmt = select(Question).where(Question.id == question_id)
        result = await self.session.execute(stmt)
        question = result.scalar_one_or_none()
        if question:
            question.explanation = text
            await self.session.commit()

    async def update_categories(self, question_id: int, categories: list[str]):
        stmt = select(Question).where(Question.id == question_id)
        result = await self.session.execute(stmt)
        question = result.scalar_one_or_none()
        if question:
            question.categories = categories
            await self.session.commit()

    async def get_questions_ids_by_subject(self, subject: str) -> list[int]:
        """
        Returns a list of question IDs for a given subject, ordered by year, session, number.
        """
        stmt = select(Question.id).where(Question.subject == subject).order_by(
            Question.year, Question.session, Question.q_number
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_question_by_id(self, question_id: int) -> Question:
        """
        Returns a full Question object by ID.
        """
        stmt = select(Question).where(Question.id == question_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unique_years(self, subject: str) -> list[int]:
        stmt = select(Question.year).where(Question.subject == subject).distinct().order_by(Question.year.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_unique_sessions(self, subject: str, year: int) -> list[str]:
        # Sort by creation order effectively (min ID of the session)
        # We want Oldest -> Newest (Ascending order of creation)
        stmt = select(Question.session).where(
            Question.subject == subject,
            Question.year == year
        ).group_by(Question.session).order_by(func.min(Question.id))
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_questions_by_criteria(self, subject: str, year: int, session: str) -> list[Question]:
        stmt = select(Question).where(
            Question.subject == subject,
            Question.year == year,
            Question.session == session
        ).order_by(Question.q_number)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_question(self, question_id: int):
        question = await self.get_question_by_id(question_id)
        if question:
            await self.session.delete(question)
            await self.session.commit()

    async def delete_questions_by_session(self, subject: str, year: int, session: str):
        """
        Deletes all questions for a specific session.
        """
        from sqlalchemy import delete
        stmt = delete(Question).where(
            Question.subject == subject,
            Question.year == year,
            Question.session == session
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def update_session_metadata(self, old_subject: str, old_year: int, old_session: str, 
                                     new_year: int = None, new_session: str = None):
        """
        Updates metadata (year/session name) for all questions in a session.
        """
        from sqlalchemy import update
        stmt = update(Question).where(
            Question.subject == old_subject,
            Question.year == old_year,
            Question.session == old_session
        )
        values = {}
        if new_year is not None:
            values["year"] = new_year
        if new_session is not None:
            values["session"] = new_session
            
        if values:
            stmt = stmt.values(**values)
            await self.session.execute(stmt)
            await self.session.commit()

    async def get_random_question(self, subjects: list[str], q_type: str = "choice") -> Question | None:
        """
        Returns a random question from given subjects, filtered by type (default: 'choice').
        To allow all types, pass q_type=None.
        """
        stmt = select(Question).where(Question.subject.in_(subjects))
        if q_type:
             stmt = stmt.where(Question.q_type == q_type)
             
        stmt = stmt.order_by(func.random()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
