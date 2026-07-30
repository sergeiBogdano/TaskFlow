"""add sort_order column to tasks

Revision ID: 20240615_add_sort_order_column
Revises: 
Create Date: 2024-06-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20240615_add_sort_order_column'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add sort_order column to tasks table
    op.add_column('tasks', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
    # Create index on sort_order
    op.create_index('ix_tasks_sort_order', 'tasks', ['sort_order'])


def downgrade():
    # Drop index
    op.drop_index('ix_tasks_sort_order', table_name='tasks')
    # Drop sort_order column
    op.drop_column('tasks', 'sort_order')