from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.skill import Skill


async def get_by_id(db: AsyncSession, organization_id: UUID, skill_id: UUID) -> Skill | None:
    """Org-scoped lookup. A skill belonging to another org simply does not
    match this WHERE clause — the caller gets back None, which the service
    layer turns into a 404 (see docs/ADR.md ADR-4), never a 403.
    """
    result = await db.execute(
        select(Skill).where(Skill.id == skill_id, Skill.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def get_by_slug(db: AsyncSession, organization_id: UUID, slug: str) -> Skill | None:
    result = await db.execute(
        select(Skill).where(Skill.organization_id == organization_id, Skill.slug == slug)
    )
    return result.scalar_one_or_none()


async def list_for_org(
    db: AsyncSession,
    organization_id: UUID,
    *,
    status_filter: str | None = None,
    department_id: UUID | None = None,
) -> list[Skill]:
    stmt = select(Skill).where(Skill.organization_id == organization_id)
    if status_filter:
        stmt = stmt.where(Skill.status == status_filter)
    if department_id:
        stmt = stmt.where(Skill.department_id == department_id)
    stmt = stmt.order_by(Skill.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


def add(db: AsyncSession, skill: Skill) -> None:
    db.add(skill)
