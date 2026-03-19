"""add_daily_sub

Revision ID: 9b5c3d4e5f6a
Revises: 8a4b2c3d4e5f
Create Date: 2026-01-31 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b5c3d4e5f6a'
down_revision: Union[str, None] = '8a4b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    columns = sa.inspect(conn).get_columns('users')
    column_names = [c['name'] for c in columns]
    if 'daily_sub' not in column_names:
        op.add_column('users', sa.Column('daily_sub', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'daily_sub')
