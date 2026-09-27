"""widen category/portal descriptions to Text (markdown)

Revision ID: 0003_markdown_descriptions
Revises: 0002_portal_area_path
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_markdown_descriptions"
down_revision = "0002_portal_area_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("categories", "description", type_=sa.Text(), existing_nullable=False)
    op.alter_column("portals", "description", type_=sa.Text(), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("categories", "description", type_=sa.String(500), existing_nullable=False)
    op.alter_column("portals", "description", type_=sa.String(1000), existing_nullable=False)
