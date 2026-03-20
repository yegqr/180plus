from sqlalchemy import BIGINT, TIMESTAMP, VARCHAR, TEXT, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TableNameMixin


class UserEvent(Base, TableNameMixin):
    """
    Generic event log for tracking user interactions that don't fit existing tables.
    payload is a JSON string with event-specific context.
    """

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT, index=True)
    event_type: Mapped[str] = mapped_column(VARCHAR(50), index=True)
    payload: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return f"<UserEvent user={self.user_id} type={self.event_type}>"
