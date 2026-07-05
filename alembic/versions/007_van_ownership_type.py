"""Add ownership_type column to vans table

Revision ID: 007
Revises: 006
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("vans", sa.Column("ownership_type", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("vans", "ownership_type")
