"""Initial tenant-scoped schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-27

Composite foreign keys (child_id, organization_id) -> (parent_id,
organization_id) make it structurally impossible for a row to reference a
parent in a different organization — this is enforced by Postgres itself,
independent of any application code (see docs/ADR.md ADR-3).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role in ('owner','admin','member')", name="ck_users_role"),
        sa.UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    op.create_table(
        "departments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "slug", name="uq_departments_org_slug"),
        sa.UniqueConstraint("id", "organization_id", name="uq_departments_id_org"),
    )
    op.create_index("ix_departments_organization_id", "departments", ["organization_id"])

    op.create_table(
        "skills",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("department_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.String(150), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("active_version_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("status in ('draft','active','disabled')", name="ck_skills_status"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_skills_org_slug"),
        sa.UniqueConstraint("id", "organization_id", name="uq_skills_id_org"),
        sa.ForeignKeyConstraint(
            ["department_id", "organization_id"],
            ["departments.id", "departments.organization_id"],
            name="fk_skills_department_org",
        ),
    )
    op.create_index("ix_skills_organization_id", "skills", ["organization_id"])

    op.create_table(
        "skill_versions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("skill_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("instructions", sa.Text, nullable=False),
        sa.Column("model_params", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("requested_tools", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("review_state", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "review_state in ('draft','in_review','approved','rejected')",
            name="ck_skill_versions_review_state",
        ),
        sa.UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_number"),
        sa.UniqueConstraint("id", "organization_id", name="uq_skill_versions_id_org"),
        sa.ForeignKeyConstraint(
            ["skill_id", "organization_id"],
            ["skills.id", "skills.organization_id"],
            name="fk_skill_versions_skill_org",
        ),
    )
    op.create_index("ix_skill_versions_organization_id", "skill_versions", ["organization_id"])
    op.create_index("ix_skill_versions_skill_id", "skill_versions", ["skill_id"])

    # active_version_id must point at a version of THIS skill, in THIS org —
    # added after skill_versions exists, via a composite FK against
    # (id, skill_id, organization_id) on skill_versions.
    op.create_unique_constraint(
        "uq_skill_versions_id_skill_org", "skill_versions", ["id", "skill_id", "organization_id"]
    )
    op.create_foreign_key(
        "fk_skills_active_version",
        "skills",
        "skill_versions",
        ["active_version_id", "id", "organization_id"],
        ["id", "skill_id", "organization_id"],
    )

    op.create_table(
        "tool_grants",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_key", sa.String(100), nullable=False),
        sa.Column("granted_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "tool_key", name="uq_tool_grants_org_tool"),
    )
    op.create_index("ix_tool_grants_organization_id", "tool_grants", ["organization_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(20), nullable=False),
        sa.Column("event", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("version_number", sa.Integer, nullable=True),
        sa.Column("detail", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_skill_id", "audit_logs", ["skill_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("tool_grants")
    op.drop_constraint("fk_skills_active_version", "skills", type_="foreignkey")
    op.drop_constraint("uq_skill_versions_id_skill_org", "skill_versions", type_="unique")
    op.drop_table("skill_versions")
    op.drop_table("skills")
    op.drop_table("departments")
    op.drop_table("users")
    op.drop_table("organizations")
