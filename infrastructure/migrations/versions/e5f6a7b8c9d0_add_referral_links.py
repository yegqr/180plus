"""add_referral_links

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-25 00:00:00.000000

Adds referral_links table for tracking user acquisition via referral deep links.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.VARCHAR(100), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_referral_links_code"),
    )
    op.create_index("ix_referral_links_code", "referral_links", ["code"])
    op.create_index("ix_referral_links_owner_user_id", "referral_links", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_referral_links_owner_user_id", table_name="referral_links")
    op.drop_index("ix_referral_links_code", table_name="referral_links")
    op.drop_table("referral_links")
