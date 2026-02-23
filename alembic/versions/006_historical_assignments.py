"""Add historical_assignments table for imported spreadsheet data

Revision ID: 006
Revises: 005
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "historical_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("assignment_date", sa.Date(), nullable=False),
        sa.Column("van_reg", sa.String(50), nullable=False),
        sa.Column("driver_name", sa.String(200), nullable=True),
        sa.Column("is_vor", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("assignment_date", "van_reg", name="uq_hist_date_van"),
        sa.Index("ix_hist_date", "assignment_date"),
    )


def downgrade():
    op.drop_table("historical_assignments")
