"""add ado_connection (admin-configured Azure DevOps connection)

Revision ID: 0004_ado_connection
Revises: 0003_markdown_descriptions
Create Date: 2026-10-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_ado_connection"
down_revision = "0003_markdown_descriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ado_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_url", sa.String(500), nullable=False),
        sa.Column("pat_encrypted", sa.Text(), nullable=False),
        sa.Column("default_project", sa.String(200), nullable=False, server_default=""),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        # Singleton: only one connection row may exist.
        sa.CheckConstraint("id = 1", name="ck_ado_connection_singleton"),
    )


def downgrade() -> None:
    op.drop_table("ado_connection")
