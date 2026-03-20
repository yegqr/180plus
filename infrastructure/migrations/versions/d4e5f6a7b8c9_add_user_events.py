"""add_user_events

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-20 01:00:00.000000

Adds userevents table for generic user interaction tracking:
  - calculator_opened, calc_spec_selected, kse_question_sent
  - explanation_viewed, subject_changed, stats_viewed
  - daily_text_answered
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "userevents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.VARCHAR(50), nullable=False),
        sa.Column("payload", sa.TEXT(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_userevents_user_id", "userevents", ["user_id"])
    op.create_index("ix_userevents_event_type", "userevents", ["event_type"])
    op.create_index("ix_userevents_created_at", "userevents", ["created_at"])


def downgrade() -> None:
    op.drop_table("userevents")
