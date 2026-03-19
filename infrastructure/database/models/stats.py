from sqlalchemy import BIGINT, TIMESTAMP, VARCHAR, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TableNameMixin


class JoinStat(Base, TableNameMixin):
    """
    Model for tracking join request sources (UTM).
    """
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT)
    source: Mapped[str] = mapped_column(VARCHAR(255), default="unknown")
    created_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP, server_default=func.now()
    )

    def __repr__(self):
        return f"<JoinStat user={self.user_id} source={self.source}>"
