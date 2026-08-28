"""Seeds the two fixture organizations required by the evaluation brief.

Deliberately connects with ADMIN_DATABASE_URL (the table-owning role), not
the RLS-restricted app_role: bootstrapping tenants is an ops/migration-time
action, not a request the runtime API ever serves, so it is exempt from RLS
by design rather than by accident (see docs/ADR.md). No real company or
customer data — these are the two fictional organizations named in the
evaluation brief, with throwaway fixture passwords printed below.
"""

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.models import Department, Organization, ToolGrant, User
from app.security.hashing import hash_password

ADMIN_DATABASE_URL = os.environ.get(
    "ADMIN_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/skill_registry",
)

FIXTURE_PASSWORD = "FixtureDemoPass123!"

ORGS = [
    {
        "name": "ABC Construction",
        "slug": "abc-construction",
        "department": {"name": "Operations", "slug": "operations"},
        "tool_grants": ["reports.generate", "docs.read", "docs.write"],
        "users": [
            ("owner@abc-construction.test", "owner"),
            ("admin@abc-construction.test", "admin"),
            ("member@abc-construction.test", "member"),
        ],
    },
    {
        "name": "XYZ Builders",
        "slug": "xyz-builders",
        "department": {"name": "Field Ops", "slug": "field-ops"},
        "tool_grants": ["calendar.read", "tasks.create"],
        "users": [
            ("owner@xyz-builders.test", "owner"),
            ("admin@xyz-builders.test", "admin"),
            ("member@xyz-builders.test", "member"),
        ],
    },
]


async def seed() -> None:
    engine = create_async_engine(ADMIN_DATABASE_URL)
    password_hash = hash_password(FIXTURE_PASSWORD)

    async with AsyncSession(engine) as session:
        for org_spec in ORGS:
            result = await session.execute(
                select(Organization).where(Organization.slug == org_spec["slug"])
            )
            org = result.scalar_one_or_none()
            if org is not None:
                print(f"[seed] {org_spec['slug']} already exists, skipping.")
                continue

            org = Organization(name=org_spec["name"], slug=org_spec["slug"])
            session.add(org)
            await session.flush()

            department = Department(
                organization_id=org.id,
                name=org_spec["department"]["name"],
                slug=org_spec["department"]["slug"],
            )
            session.add(department)

            first_user_id = None
            for email, role in org_spec["users"]:
                user = User(
                    organization_id=org.id,
                    email=email,
                    password_hash=password_hash,
                    role=role,
                    is_active=True,
                )
                session.add(user)
                await session.flush()
                if role == "owner":
                    first_user_id = user.id

            for tool_key in org_spec["tool_grants"]:
                session.add(
                    ToolGrant(organization_id=org.id, tool_key=tool_key, granted_by=first_user_id)
                )

            await session.commit()
            print(f"[seed] created organization '{org_spec['slug']}' with 3 users + 1 department.")

    await engine.dispose()
    print(f"[seed] fixture password for every seeded user: {FIXTURE_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
