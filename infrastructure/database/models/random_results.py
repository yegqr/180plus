import uuid
from sqlalchemy import String, Integer, ForeignKey, BIGINT, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, TableNameMixin

class RandomResult(Base, TimestampMixin, TableNameMixin):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.user_id"))
    subject: Mapped[str] = mapped_column(String(50))
    question_id: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer, server_default=text("1"))

    def __repr__(self):
        return f"<RandomResult {self.id} User:{self.user_id} Q:{self.question_id}>"
