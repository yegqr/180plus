from sqlalchemy import BIGINT, TIMESTAMP, VARCHAR, BOOLEAN, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TableNameMixin


class UserActionLog(Base, TableNameMixin):
    """
    Log of every user answer in Random or Simulation mode.
    """
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT)
    question_id: Mapped[int] = mapped_column(BIGINT)
    answer: Mapped[str] = mapped_column(VARCHAR(500), nullable=True) # User's answer text
    is_correct: Mapped[bool] = mapped_column(BOOLEAN, default=False)
    mode: Mapped[str] = mapped_column(VARCHAR(50), default="random") # random / simulation
    session_id: Mapped[str] = mapped_column(VARCHAR(100), nullable=True) # e.g. "math_2024_main" for sim
    created_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP, server_default=func.now()
    )

    def __repr__(self):
        return f"<Log user={self.user_id} q={self.question_id} correct={self.is_correct}>"
