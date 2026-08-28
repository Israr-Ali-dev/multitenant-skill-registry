"""Test fixtures.

Tests run against a real Postgres instance (no mocks, no SQLite) — see
docs/ADR.md ADR-1. Fixture organizations/users are seeded via `admin_session`
(the table-owning connection, same as scripts/seed_fixtures.py), then all
requests made through `client` flow through the exact same
`app.db.session.get_db_session` dependency production uses — meaning they go
over the RLS-restricted `app_role` connection, so these tests genuinely
exercise Row-Level Security, not just application-level filtering.

Isolation between tests: every tenant table is truncated after each test.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.models import Department, Organization, User
from app.main import app
from app.security.hashing import hash_password


@pytest.fixture(scope="session")
def event_loop():
    """One event loop for the whole test session.

    Both the production engine (app/db/session.py, an asyncpg connection
    pool created once when `app.main` is first imported) and the admin
    engine below are module-level objects reused across every test.
    pytest-asyncio's default of a fresh event loop per test function would
    bind their pooled connections to whichever test happened to run first,
    then break every test after it ("attached to a different loop"). A
    single session-scoped loop keeps that binding valid throughout.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

ADMIN_DATABASE_URL = os.environ.get(
    "ADMIN_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/skill_registry",
)

FIXTURE_PASSWORD = "TestFixturePass123!"

TENANT_TABLES = [
    "audit_logs",
    "tool_grants",
    "skill_versions",
    "skills",
    "departments",
    "users",
    "organizations",
]

_admin_engine = create_async_engine(ADMIN_DATABASE_URL)


@pytest_asyncio.fixture(autouse=True)
async def _clean_db() -> AsyncGenerator[None, None]:
    yield
    async with _admin_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TENANT_TABLES)} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def admin_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(_admin_engine, expire_on_commit=False) as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
        yield ac


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class OrgFixture:
    def __init__(self, org: Organization, department: Department, users: dict[str, User]):
        self.org = org
        self.department = department
        self.users = users  # role -> User

    def email(self, role: str) -> str:
        return self.users[role].email


@pytest_asyncio.fixture
async def two_orgs(admin_session: AsyncSession) -> tuple[OrgFixture, OrgFixture]:
    """Seeds ABC Construction and XYZ Builders (unique slugs per test run),
    each with owner/admin/member users and one department.
    """

    async def _make_org(name: str, slug_prefix: str, dept_name: str) -> OrgFixture:
        org = Organization(name=name, slug=_unique(slug_prefix))
        admin_session.add(org)
        await admin_session.flush()

        department = Department(organization_id=org.id, name=dept_name, slug=_unique("dept"))
        admin_session.add(department)

        users = {}
        for role in ("owner", "admin", "member"):
            user = User(
                organization_id=org.id,
                email=f"{role}-{uuid.uuid4().hex[:8]}@{slug_prefix}.test",
                password_hash=hash_password(FIXTURE_PASSWORD),
                role=role,
                is_active=True,
            )
            admin_session.add(user)
            users[role] = user

        await admin_session.flush()
        return OrgFixture(org=org, department=department, users=users)

    org_a = await _make_org("ABC Construction", "abc", "Operations")
    org_b = await _make_org("XYZ Builders", "xyz", "Field Ops")
    await admin_session.commit()
    return org_a, org_b


async def login(client: AsyncClient, org: OrgFixture, role: str) -> str:
    resp = await client.post(
        "/auth/login",
        json={
            "organization_slug": org.org.slug,
            "email": org.email(role),
            "password": FIXTURE_PASSWORD,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_draft_skill(
    client: AsyncClient,
    token: str,
    *,
    slug: str | None = None,
    requested_tools: list[str] | None = None,
    department_slug: str | None = None,
) -> dict:
    resp = await client.post(
        "/skills",
        headers=auth_headers(token),
        json={
            "slug": slug or _unique("skill"),
            "name": "Weekly Ops Report",
            "description": "Summarizes weekly site progress.",
            "department_slug": department_slug,
            "instructions": "Compile the weekly site status into a structured report.",
            "model_params": {"temperature": 0.2},
            "requested_tools": requested_tools if requested_tools is not None else ["docs.read"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
