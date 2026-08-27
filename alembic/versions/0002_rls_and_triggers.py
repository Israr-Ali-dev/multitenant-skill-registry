"""Row-Level Security + immutability/append-only triggers.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-27

Two independent mechanisms enforced entirely inside Postgres, so they hold
even against a bug in the application layer (see docs/ADR.md ADR-3, ADR-5,
ADR-7):

1. `app_role` — a non-superuser, non-table-owner login role — is the ONLY
   role the API ever connects as. RLS policies below apply to it fully;
   Postgres exempts the owner/superuser regardless of policy, which is
   exactly why the app never connects as either.
2. Triggers block (a) mutating the content columns of an existing
   skill_versions row, and (b) any UPDATE/DELETE on audit_logs at all.

Fail-closed by construction: `current_setting('app.current_org_id', true)`
returns NULL when unset, and `organization_id = NULL` is never true — a
session that forgets to set the org context sees zero rows, not everyone's.
"""

import os
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_DB_USER = os.environ.get("APP_DB_USER", "app_role")
APP_DB_PASSWORD = os.environ.get("APP_DB_PASSWORD", "app_role")

TENANT_TABLES = [
    "users",
    "departments",
    "skills",
    "skill_versions",
    "tool_grants",
    "audit_logs",
]


def _quoted_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    conn = op.get_bind()

    # --- 1. Non-owner application role -------------------------------------
    role_exists = conn.execute(
        text(f"SELECT 1 FROM pg_roles WHERE rolname = {_quoted_literal(APP_DB_USER)}")
    ).scalar()
    if not role_exists:
        op.execute(
            f"CREATE ROLE {APP_DB_USER} LOGIN PASSWORD {_quoted_literal(APP_DB_PASSWORD)}"
        )
    else:
        op.execute(f"ALTER ROLE {APP_DB_USER} LOGIN PASSWORD {_quoted_literal(APP_DB_PASSWORD)}")

    db_name = conn.execute(text("SELECT current_database()")).scalar()
    op.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO {APP_DB_USER}')
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_DB_USER}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {APP_DB_USER}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_DB_USER}")
    # audit_logs is append-only at the privilege level too, not just via trigger.
    op.execute(f"REVOKE UPDATE, DELETE ON audit_logs FROM {APP_DB_USER}")
    # organizations is the tenant root; never deleted/updated by the app in this slice.
    op.execute(f"REVOKE UPDATE, DELETE ON organizations FROM {APP_DB_USER}")

    # --- 2. Row-Level Security on every tenant-owned table ------------------
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            """
        )

    # --- 3. skill_versions content is write-once -----------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_skill_version_content_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.instructions     IS DISTINCT FROM OLD.instructions
            OR NEW.model_params     IS DISTINCT FROM OLD.model_params
            OR NEW.requested_tools  IS DISTINCT FROM OLD.requested_tools
            OR NEW.content_hash     IS DISTINCT FROM OLD.content_hash
            OR NEW.version_number   IS DISTINCT FROM OLD.version_number
            OR NEW.skill_id         IS DISTINCT FROM OLD.skill_id
            OR NEW.organization_id  IS DISTINCT FROM OLD.organization_id
            OR NEW.created_by       IS DISTINCT FROM OLD.created_by
            OR NEW.created_at       IS DISTINCT FROM OLD.created_at
            THEN
                RAISE EXCEPTION
                    'skill_versions content is immutable; only review_state/reviewed_by/reviewed_at may change (id=%)',
                    OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_skill_versions_immutable
        BEFORE UPDATE ON skill_versions
        FOR EACH ROW EXECUTE FUNCTION prevent_skill_version_content_mutation();
        """
    )

    # --- 4. audit_logs is append-only, full stop -----------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only; % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_no_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_no_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")
    op.execute("DROP TRIGGER IF EXISTS trg_skill_versions_immutable ON skill_versions")
    op.execute("DROP FUNCTION IF EXISTS prevent_skill_version_content_mutation()")

    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute(f"REASSIGN OWNED BY {APP_DB_USER} TO CURRENT_USER")
    op.execute(f"DROP OWNED BY {APP_DB_USER}")
    op.execute(f"DROP ROLE IF EXISTS {APP_DB_USER}")
