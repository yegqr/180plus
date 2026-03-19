"""add_user_settings

Revision ID: a1b2c3d4e5f6
Revises: 9b5c3d4e5f6a
Create Date: 2026-03-09 20:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9b5c3d4e5f6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    columns = sa.inspect(conn).get_columns('users')
    column_names = [c['name'] for c in columns]
    if 'settings' not in column_names:
        op.add_column('users', sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'settings')
