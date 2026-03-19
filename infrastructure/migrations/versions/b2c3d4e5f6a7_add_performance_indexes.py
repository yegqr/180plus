"""add_performance_indexes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-19 00:00:00.000000

Adds indexes for the most frequent query patterns:
  - useractionlogs(user_id, question_id) — failure count / history lookups
  - useractionlogs(session_id)           — per-session log queries
  - examresults(user_id, subject)        — stats / prediction queries
  - questions(subject, year, session)    — session selection / criteria filter
  - randomresults(user_id, subject)      — random stats aggregation
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_useractionlogs_user_question",
        "useractionlogs",
        ["user_id", "question_id"],
        unique=False,
    )
    op.create_index(
        "ix_useractionlogs_session_id",
        "useractionlogs",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_examresults_user_subject",
        "examresults",
        ["user_id", "subject"],
        unique=False,
    )
    op.create_index(
        "ix_questions_subject_year_session",
        "questions",
        ["subject", "year", "session"],
        unique=False,
    )
    op.create_index(
        "ix_randomresults_user_subject",
        "randomresults",
        ["user_id", "subject"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_randomresults_user_subject", table_name="randomresults")
    op.drop_index("ix_questions_subject_year_session", table_name="questions")
    op.drop_index("ix_examresults_user_subject", table_name="examresults")
    op.drop_index("ix_useractionlogs_session_id", table_name="useractionlogs")
    op.drop_index("ix_useractionlogs_user_question", table_name="useractionlogs")
