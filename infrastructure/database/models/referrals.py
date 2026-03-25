from sqlalchemy import BIGINT, BOOLEAN, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ReferralLink(Base, TimestampMixin):
    __tablename__ = "referral_links"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(VARCHAR(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(VARCHAR(255))
    owner_user_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True, index=True)
    created_by: Mapped[int] = mapped_column(BIGINT)
    is_active: Mapped[bool] = mapped_column(BOOLEAN, default=True, server_default="true")

    def __repr__(self) -> str:
        return f"<ReferralLink code={self.code!r} owner={self.owner_user_id}>"
