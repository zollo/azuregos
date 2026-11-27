"""add oidc_settings / saml_settings (admin-configured single sign-on)

Revision ID: 0006_sso_settings
Revises: 0005_admin_roles
Create Date: 2026-11-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_sso_settings"
down_revision = "0005_admin_roles"
branch_labels = None
depends_on = None


def _common(table: str) -> list:
    return [
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        # Singleton: only one settings row per provider.
        sa.CheckConstraint("id = 1", name=f"ck_{table}_singleton"),
    ]


def upgrade() -> None:
    op.create_table(
        "oidc_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("discovery_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("client_id", sa.String(500), nullable=False, server_default=""),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("redirect_uri", sa.String(500), nullable=False, server_default=""),
        sa.Column("scopes", sa.String(500), nullable=False,
                  server_default="openid email profile"),
        sa.Column("button_label", sa.String(100), nullable=False, server_default=""),
        *_common("oidc_settings"),
    )
    op.create_table(
        "saml_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("metadata_xml", sa.Text(), nullable=False, server_default=""),
        sa.Column("sp_entity_id", sa.String(500), nullable=False, server_default="azuregos"),
        sa.Column("acs_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("sp_x509_cert", sa.Text(), nullable=False, server_default=""),
        sa.Column("sp_private_key_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("email_attribute", sa.String(500), nullable=False, server_default=""),
        sa.Column("name_attribute", sa.String(500), nullable=False, server_default=""),
        sa.Column("button_label", sa.String(100), nullable=False, server_default=""),
        *_common("saml_settings"),
    )


def downgrade() -> None:
    op.drop_table("saml_settings")
    op.drop_table("oidc_settings")
