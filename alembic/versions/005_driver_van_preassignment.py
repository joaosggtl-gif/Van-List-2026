"""Add driver_van_preassignments table

Revision ID: 005
Revises: 004
Create Date: 2026-02-08
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "driver_van_preassignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("van_id", sa.Integer(), sa.ForeignKey("vans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("driver_id", name="uq_preassign_driver"),
    )


def downgrade():
    op.drop_table("driver_van_preassignments")
