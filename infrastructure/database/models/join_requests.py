from sqlalchemy import BIGINT, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TableNameMixin


class PendingJoinRequest(Base, TableNameMixin):
    """
    Model for tracking pending channel join requests.
    """
    user_id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP, server_default=func.now()
    )

    def __repr__(self):
        return f"<PendingJoinRequest user={self.user_id} chat={self.chat_id}>"
