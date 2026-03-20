from sqlalchemy import BIGINT, TIMESTAMP, VARCHAR, TEXT, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TableNameMixin


class AdminAuditLog(Base, TableNameMixin):
    """Audit trail for every admin action."""

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BIGINT, index=True)
    action: Mapped[str] = mapped_column(VARCHAR(100))
    target_id: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    details: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return f"<AdminAuditLog admin={self.admin_id} action={self.action}>"
