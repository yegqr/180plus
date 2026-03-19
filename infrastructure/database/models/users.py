from typing import Optional
from datetime import datetime

from sqlalchemy import String, TIMESTAMP, func
from sqlalchemy import text, BIGINT, Boolean, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, TableNameMixin


class User(Base, TimestampMixin, TableNameMixin):
    """
    This class represents a User in the application.
    If you want to learn more about SQLAlchemy and Alembic, you can check out the following link to my course:
    https://www.udemy.com/course/sqlalchemy-alembic-bootcamp/?referralCode=E9099C5B5109EB747126

    Attributes:
        user_id (Mapped[int]): The unique identifier of the user.
        username (Mapped[Optional[str]]): The username of the user.
        full_name (Mapped[str]): The full name of the user.
        active (Mapped[bool]): Indicates whether the user is active or not.
        language (Mapped[str]): The language preference of the user.

    Methods:
        __repr__(): Returns a string representation of the User object.

    Inherited Attributes:
        Inherits from Base, TimestampMixin, and TableNameMixin classes, which provide additional attributes and functionality.

    Inherited Methods:
        Inherits methods from Base, TimestampMixin, and TableNameMixin classes, which provide additional functionality.

    """
    user_id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(128))
    full_name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    language: Mapped[str] = mapped_column(String(10), server_default=text("'en'"))
    selected_subject: Mapped[str] = mapped_column(String(50), server_default=text("'math'"))
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    daily_sub: Mapped[bool] = mapped_column(Boolean, server_default=true())
    settings: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<User {self.user_id} {self.username} {self.full_name}>"
