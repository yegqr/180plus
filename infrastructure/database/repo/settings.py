from typing import Optional
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from infrastructure.database.models import Setting
from infrastructure.database.repo.base import BaseRepo


class SettingsRepo(BaseRepo):
    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        stmt = select(Setting.value).where(Setting.key == key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() or default

    async def set_setting(self, key: str, value: str):
        stmt = insert(Setting).values(key=key, value=value)
        update_stmt = stmt.on_conflict_do_update(
            index_elements=[Setting.key],
            set_=dict(value=value)
        )
        await self.session.execute(update_stmt)
        await self.session.commit()
