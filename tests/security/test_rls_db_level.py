"""Proves Row-Level Security itself — independent of any application code —
by connecting as the exact runtime role (`app_role`, non-owner) the API uses,
issuing raw SQL, and checking what Postgres itself will and won't return.

This is the RLS layer of docs/ADR.md ADR-3's defense-in-depth; the HTTP-level
isolation tests in tests/security/test_isolation.py already exercise this
same enforcement indirectly (they run over the same app_role connection —
see tests/conftest.py), but this file makes the DB-level guarantee explicit
and would still catch a regression even if a future service-layer change
accidentally dropped an application-level org filter.
"""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://app_role:app_role@localhost:5432/skill_registry",
)
ADMIN_DATABASE_URL = os.environ.get(
    "ADMIN_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/skill_registry",
)


async def _set_org(conn, org_id) -> None:
    await conn.execute(
        text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": str(org_id)}
    )


async def test_rls_blocks_cross_org_select_at_the_database_level(admin_session, two_orgs):
    org_a, org_b = two_orgs

    from app.db.models import Skill

    skill_a = Skill(
        organization_id=org_a.org.id,
        slug="rls-proof-a",
        name="RLS Proof A",
        status="draft",
        created_by=org_a.users["owner"].id,
    )
    skill_b = Skill(
        organization_id=org_b.org.id,
        slug="rls-proof-b",
        name="RLS Proof B",
        status="draft",
        created_by=org_b.users["owner"].id,
    )
    admin_session.add_all([skill_a, skill_b])
    await admin_session.commit()

    app_engine = create_async_engine(DATABASE_URL)
    try:
        async with app_engine.connect() as conn:
            await _set_org(conn, org_a.org.id)
            result = await conn.execute(text("SELECT slug FROM skills"))
            slugs = {row[0] for row in result.fetchall()}
            assert "rls-proof-a" in slugs
            assert "rls-proof-b" not in slugs
    finally:
        await app_engine.dispose()


async def test_rls_fails_closed_with_no_org_context_set(admin_session, two_orgs):
    """A session that never sets app.current_org_id sees zero rows — not
    everyone's — because current_setting(...) returns NULL and
    `organization_id = NULL` is never true."""
    org_a, _org_b = two_orgs

    from app.db.models import Skill

    admin_session.add(
        Skill(
            organization_id=org_a.org.id,
            slug="rls-proof-unset",
            name="RLS Proof Unset",
            status="draft",
            created_by=org_a.users["owner"].id,
        )
    )
    await admin_session.commit()

    app_engine = create_async_engine(DATABASE_URL)
    try:
        async with app_engine.connect() as conn:
            result = await conn.execute(text("SELECT slug FROM skills"))
            assert result.fetchall() == []
    finally:
        await app_engine.dispose()


async def test_rls_blocks_cross_org_insert_at_the_database_level(two_orgs):
    org_a, org_b = two_orgs

    app_engine = create_async_engine(DATABASE_URL)
    try:
        async with app_engine.connect() as conn:
            await _set_org(conn, org_a.org.id)
            # Any exception is a pass here: the point is that Postgres's RLS
            # WITH CHECK clause rejects this INSERT outright — the specific
            # driver-level exception class is an implementation detail.
            with pytest.raises(Exception):  # noqa: B017
                async with conn.begin():
                    await conn.execute(
                        text(
                            "INSERT INTO skills "
                            "(id, organization_id, slug, name, status, created_by) "
                            "VALUES (:id, :org_id, 'sneaky', 'Sneaky', 'draft', :creator)"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            # Writing into org B's data while scoped to org A.
                            "org_id": str(org_b.org.id),
                            "creator": str(org_a.users["owner"].id),
                        },
                    )
    finally:
        await app_engine.dispose()


async def test_audit_logs_reject_update_and_delete(admin_session, two_orgs):
    """Append-only at the database level: even the table owner's UPDATE/DELETE
    is blocked by trigger (app_role additionally lacks the privilege at all).
    """
    org_a, _org_b = two_orgs
    from app.db.models import AuditLog

    entry = AuditLog(
        organization_id=org_a.org.id,
        actor_user_id=org_a.users["owner"].id,
        actor_role="owner",
        event="test.event",
        resource_type="skill",
        resource_id=org_a.org.id,
        detail={},
    )
    admin_session.add(entry)
    await admin_session.commit()

    # Each statement gets its own short-lived connection: a Postgres error
    # aborts the whole surrounding transaction, so re-using one connection
    # across two expected failures would corrupt the second attempt.
    admin_engine = create_async_engine(ADMIN_DATABASE_URL)
    try:
        with pytest.raises(Exception, match="append-only"):
            async with admin_engine.begin() as conn:
                await conn.execute(
                    text("UPDATE audit_logs SET event = 'tampered' WHERE id = :id"),
                    {"id": entry.id},
                )

        with pytest.raises(Exception, match="append-only"):
            async with admin_engine.begin() as conn:
                await conn.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": entry.id})
    finally:
        await admin_engine.dispose()
