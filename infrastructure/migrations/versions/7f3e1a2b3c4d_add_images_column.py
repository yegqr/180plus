"""add images column

Revision ID: 7f3e1a2b3c4d
Revises: 6de8e23ae988
Create Date: 2026-01-25 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '7f3e1a2b3c4d'
down_revision = '6de8e23ae988'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Add 'images' column if it doesn't exist
    conn = op.get_bind()
    columns = sa.inspect(conn).get_columns('questions')
    column_names = [c['name'] for c in columns]
    if 'images' not in column_names:
        op.add_column('questions', sa.Column('images', JSONB, nullable=True))
    
    # 2. Migrate existing data: images = [image_file_id]
    # We use raw SQL for this data migration
    op.execute("UPDATE questions SET images = jsonb_build_array(image_file_id) WHERE image_file_id IS NOT NULL")

def downgrade() -> None:
    op.drop_column('questions', 'images')
