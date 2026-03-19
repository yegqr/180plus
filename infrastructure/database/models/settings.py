from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TableNameMixin


class Setting(Base, TableNameMixin):
    """
    Model for storing bot settings.
    """
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))

    def __repr__(self):
        return f"<Setting {self.key}={self.value}>"
