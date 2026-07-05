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
    op.alter_column("daily_assignments", "van_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("daily_assignments", "driver_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.alter_column("daily_assignments", "van_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("daily_assignments", "driver_id", existing_type=sa.Integer(), nullable=False)
