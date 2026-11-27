"""admin roles: super_admin / admin / portal_admin, plus portal assignments

Existing ``admin`` users become ``super_admin``: before this revision an admin
could do everything (including granting admin), which is exactly what a super
admin can do now, and it keeps at least one account able to manage the rest.

Revision ID: 0005_admin_roles
Revises: 0004_ado_connection
Create Date: 2026-10-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_admin_roles"
down_revision = "0004_ado_connection"
branch_labels = None
depends_on = None


def _swap_role_enum(values: tuple[str, ...], mapping: str) -> None:
    """Replace the user_role enum with ``values``, converting rows via the SQL
    CASE expression ``mapping`` (over ``role::text``).

    A new type is created instead of ``ALTER TYPE ... ADD VALUE`` so the whole
    thing runs (and rolls back) inside the migration's transaction.
    """
    op.execute("ALTER TYPE user_role RENAME TO user_role_old")
    postgresql.ENUM(*values, name="user_role").create(op.get_bind())
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute(f"ALTER TABLE users ALTER COLUMN role TYPE user_role USING ({mapping})::user_role")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'end_user'")
    op.execute("DROP TYPE user_role_old")


def upgrade() -> None:
    _swap_role_enum(
        ("super_admin", "admin", "portal_admin", "end_user"),
        "CASE role::text WHEN 'admin' THEN 'super_admin' ELSE role::text END",
    )
    op.create_table(
        "portal_admins",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("portal_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("portals.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_portal_admins_portal_id", "portal_admins", ["portal_id"])


def downgrade() -> None:
    op.drop_index("ix_portal_admins_portal_id", table_name="portal_admins")
    op.drop_table("portal_admins")
    # Both admin tiers collapse back to admin; portal admins lose admin access.
    _swap_role_enum(
        ("admin", "end_user"),
        "CASE role::text WHEN 'super_admin' THEN 'admin' WHEN 'admin' THEN 'admin' "
        "ELSE 'end_user' END",
    )
