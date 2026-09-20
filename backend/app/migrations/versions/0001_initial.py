"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps() -> tuple:
    """The created_at/updated_at columns shared by every table."""
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )


def upgrade() -> None:
    user_role = postgresql.ENUM("admin", "end_user", name="user_role")
    auth_provider = postgresql.ENUM("local", "oidc", "saml", name="auth_provider")
    sync_status = postgresql.ENUM(
        "pending", "syncing", "synced", "failed", name="sync_status"
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default="end_user"),
        sa.Column("provider", auth_provider, nullable=False, server_default="local"),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("provider", "external_id", name="uq_provider_external_id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(140), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("icon", sa.String(60), nullable=False, server_default="folder"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    op.create_table(
        "portals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False, server_default=""),
        sa.Column("icon", sa.String(60), nullable=False, server_default="ticket"),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ado_project", sa.String(200), nullable=True),
        sa.Column("work_item_type", sa.String(100), nullable=False, server_default="Issue"),
        sa.Column("fields", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_portals_slug", "portals", ["slug"], unique=True)
    op.create_index("ix_portals_category_id", "portals", ["category_id"])

    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("portal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitter_email", sa.String(320), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("field_values", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ado_work_item_id", sa.Integer(), nullable=True),
        sa.Column("ado_url", sa.String(1000), nullable=True),
        sa.Column("ado_state", sa.String(120), nullable=True),
        sa.Column("sync_status", sync_status, nullable=False, server_default="pending"),
        sa.Column("sync_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_tickets_portal_id", "tickets", ["portal_id"])
    op.create_index("ix_tickets_submitted_by_id", "tickets", ["submitted_by_id"])
    op.create_index("ix_tickets_submitter_email", "tickets", ["submitter_email"])
    op.create_index("ix_tickets_ado_work_item_id", "tickets", ["ado_work_item_id"])
    op.create_index("ix_tickets_sync_status", "tickets", ["sync_status"])


def downgrade() -> None:
    op.drop_table("tickets")
    op.drop_table("portals")
    op.drop_table("categories")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS sync_status")
    op.execute("DROP TYPE IF EXISTS auth_provider")
    op.execute("DROP TYPE IF EXISTS user_role")
