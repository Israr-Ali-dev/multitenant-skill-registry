from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.department import Department


async def get_by_slug(db: AsyncSession, organization_id: UUID, slug: str) -> Department | None:
    result = await db.execute(
        select(Department).where(
            Department.organization_id == organization_id, Department.slug == slug
        )
    )
    return result.scalar_one_or_none()


async def list_for_org(db: AsyncSession, organization_id: UUID) -> list[Department]:
    result = await db.execute(
        select(Department).where(Department.organization_id == organization_id)
    )
    return list(result.scalars().all())
