"""add area_path to portals

Revision ID: 0002_portal_area_path
Revises: 0001_initial
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_portal_area_path"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portals", sa.Column("area_path", sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column("portals", "area_path")
