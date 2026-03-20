from __future__ import annotations

from sqlalchemy import desc, select

from infrastructure.database.models.audit import AdminAuditLog
from infrastructure.database.repo.base import BaseRepo


class AuditRepo(BaseRepo):
    async def log_action(
        self,
        admin_id: int,
        action: str,
        target_id: str | None = None,
        details: str | None = None,
    ) -> None:
        """Fire-and-forget: records an admin action. Never raises — swallows exceptions."""
        try:
            from sqlalchemy.dialects.postgresql import insert
            stmt = insert(AdminAuditLog).values(
                admin_id=admin_id,
                action=action,
                target_id=str(target_id) if target_id is not None else None,
                details=details,
            )
            await self.session.execute(stmt)
        except Exception:
            pass  # audit must never break normal flow

    async def get_recent_logs(self, limit: int = 50) -> list[AdminAuditLog]:
        stmt = (
            select(AdminAuditLog)
            .order_by(desc(AdminAuditLog.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_for_export(self) -> list[AdminAuditLog]:
        stmt = select(AdminAuditLog).order_by(desc(AdminAuditLog.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
