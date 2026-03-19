from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TableNameMixin

class SubjectMaterial(Base, TableNameMixin):
    subject: Mapped[str] = mapped_column(String(50), primary_key=True)
    images: Mapped[list] = mapped_column(JSONB, default=list)

    def __repr__(self):
        return f"<SubjectMaterial {self.subject}>"
