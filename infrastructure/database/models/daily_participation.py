import datetime

from sqlalchemy import BIGINT, TIMESTAMP, VARCHAR, BOOLEAN, Date, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TableNameMixin


class DailyParticipation(Base, TableNameMixin):
    """
    Tracks daily challenge delivery and answer per user per day.
    One record per (user_id, date) — unique constraint enforced.
    """

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT, index=True)
    question_id: Mapped[int] = mapped_column(BIGINT)
    subject: Mapped[str] = mapped_column(VARCHAR(50))
    date: Mapped[datetime.date] = mapped_column(Date, index=True)

    sent_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now())
    answered_at: Mapped[TIMESTAMP | None] = mapped_column(TIMESTAMP, nullable=True)
    answer: Mapped[str | None] = mapped_column(VARCHAR(500), nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(BOOLEAN, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_daily_participation_user_date"),
    )

    def __repr__(self) -> str:
        return f"<DailyParticipation user={self.user_id} date={self.date} answered={self.answered_at is not None}>"
