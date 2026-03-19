"""add explanation column

Revision ID: 8a4b2c3d4e5f
Revises: 7f3e1a2b3c4d
Create Date: 2026-01-26 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TEXT

# revision identifiers, used by Alembic.
revision = '8a4b2c3d4e5f'
down_revision = '7f3e1a2b3c4d'
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    columns = sa.inspect(conn).get_columns('questions')
    column_names = [c['name'] for c in columns]
    if 'explanation' not in column_names:
        op.add_column('questions', sa.Column('explanation', sa.TEXT(), nullable=True))

def downgrade() -> None:
    op.drop_column('questions', 'explanation')
