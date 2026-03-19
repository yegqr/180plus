from sqlalchemy import String, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TableNameMixin

class Question(Base, TableNameMixin):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(50))
    year: Mapped[int] = mapped_column(Integer)
    session: Mapped[str] = mapped_column(String(50))
    q_number: Mapped[int] = mapped_column(Integer)
    image_file_id: Mapped[str] = mapped_column(String(255), nullable=True)
    q_type: Mapped[str] = mapped_column(String(50))
    correct_answer: Mapped[dict] = mapped_column(JSONB)
    weight: Mapped[int] = mapped_column(Integer)
    images: Mapped[list] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=True)
    categories: Mapped[list] = mapped_column(JSONB, nullable=True) # List of category slugs

    def __repr__(self):
        return f"<Question {self.id} {self.subject} {self.year}>"
