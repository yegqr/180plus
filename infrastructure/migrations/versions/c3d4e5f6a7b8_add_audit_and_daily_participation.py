"""add_audit_and_daily_participation

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-20 00:00:00.000000

Adds two new tables:
  - adminauditlogs  — audit trail for all admin actions
  - dailyparticipations — per-user daily challenge delivery and answer tracking
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- adminauditlogs ---
    op.create_table(
        "adminauditlogs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.VARCHAR(100), nullable=False),
        sa.Column("target_id", sa.VARCHAR(255), nullable=True),
        sa.Column("details", sa.TEXT(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_adminauditlogs_admin_id", "adminauditlogs", ["admin_id"])
    op.create_index("ix_adminauditlogs_created_desc", "adminauditlogs", ["created_at"])

    # --- dailyparticipations ---
    op.create_table(
        "dailyparticipations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("subject", sa.VARCHAR(50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "sent_at",
            sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("answer", sa.VARCHAR(500), nullable=True),
        sa.Column("is_correct", sa.BOOLEAN(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_daily_participation_user_date"),
    )
    op.create_index("ix_dailyparticipations_user_id", "dailyparticipations", ["user_id"])
    op.create_index("ix_dailyparticipations_date", "dailyparticipations", ["date"])


def downgrade() -> None:
    op.drop_table("dailyparticipations")
    op.drop_table("adminauditlogs")
