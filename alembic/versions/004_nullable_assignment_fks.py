"""Make van_id and driver_id nullable on daily_assignments

Revision ID: 004
Revises: 003
Create Date: 2026-02-08
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("daily_assignments") as batch_op:
        batch_op.alter_column("van_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("driver_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table("daily_assignments") as batch_op:
        batch_op.alter_column("van_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("driver_id", existing_type=sa.Integer(), nullable=False)
