"""add completion_date to tasks, accesses to clients

Revision ID: 20260526_add_completion_date_and_accesses
Revises: 20240615_add_sort_order_column
Create Date: 2026-05-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260526_add_completion_date_and_accesses'
down_revision = '20240615_add_sort_order_column'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('completion_date', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_tasks_completion_date', 'tasks', ['completion_date'])
    op.add_column('clients', sa.Column('accesses', sa.JSON(), nullable=True))


def downgrade():
    op.drop_index('ix_tasks_completion_date', table_name='tasks')
    op.drop_column('tasks', 'completion_date')
    op.drop_column('clients', 'accesses')
