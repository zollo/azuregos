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

    # Icons: empty now means "inherit/default". Normalize the pre-feature default
    # values ('folder'/'ticket') to empty so existing portals inherit their
    # category icon, and flip the column server defaults to ''.
    op.execute("UPDATE categories SET icon = '' WHERE icon = 'folder'")
    op.execute("UPDATE portals SET icon = '' WHERE icon = 'ticket'")
    op.alter_column("categories", "icon", server_default="", existing_type=sa.String(60),
                    existing_nullable=False)
    op.alter_column("portals", "icon", server_default="", existing_type=sa.String(60),
                    existing_nullable=False)


def downgrade() -> None:
    op.alter_column("portals", "icon", server_default="ticket", existing_type=sa.String(60),
                    existing_nullable=False)
    op.alter_column("categories", "icon", server_default="folder", existing_type=sa.String(60),
                    existing_nullable=False)
    op.alter_column("categories", "description", type_=sa.String(500), existing_nullable=False)
    op.alter_column("portals", "description", type_=sa.String(1000), existing_nullable=False)
