import uuid
from sqlalchemy import String, Integer, ForeignKey, Interval
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, TableNameMixin

class ExamResult(Base, TimestampMixin, TableNameMixin):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    subject: Mapped[str] = mapped_column(String(50))
    year: Mapped[int] = mapped_column(Integer)
    session: Mapped[str] = mapped_column(String(50))
    raw_score: Mapped[int] = mapped_column(Integer)
    nmt_score: Mapped[int] = mapped_column(Integer)
    duration: Mapped[int] = mapped_column(Integer) # in seconds

    def __repr__(self):
        return f"<ExamResult {self.id} User:{self.user_id}>"
