"""Add operational_status column to vans

Revision ID: 003
Revises: 002
Create Date: 2026-02-08
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("vans", sa.Column("operational_status", sa.String(30), nullable=True))


def downgrade():
    op.drop_column("vans", "operational_status")
