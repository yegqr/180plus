from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from infrastructure.database.models import SubjectMaterial
from infrastructure.database.repo.base import BaseRepo


class MaterialRepo(BaseRepo):
    async def get_by_subject(self, subject: str) -> SubjectMaterial | None:
        stmt = select(SubjectMaterial).where(SubjectMaterial.subject == subject)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_materials(self, subject: str, images: list[str]) -> None:
        stmt = (
            insert(SubjectMaterial)
            .values(subject=subject, images=images)
            .on_conflict_do_update(
                index_elements=[SubjectMaterial.subject],
                set_=dict(images=images),
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def clear_materials(self, subject: str) -> None:
        stmt = (
            update(SubjectMaterial)
            .where(SubjectMaterial.subject == subject)
            .values(images=[])
        )
        await self.session.execute(stmt)
        await self.session.commit()
