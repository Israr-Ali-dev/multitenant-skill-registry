from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.skill_version import SkillVersion


async def get_by_number(
    db: AsyncSession, organization_id: UUID, skill_id: UUID, version_number: int
) -> SkillVersion | None:
    result = await db.execute(
        select(SkillVersion).where(
            SkillVersion.organization_id == organization_id,
            SkillVersion.skill_id == skill_id,
            SkillVersion.version_number == version_number,
        )
    )
    return result.scalar_one_or_none()


async def get_by_id(
    db: AsyncSession, organization_id: UUID, version_id: UUID
) -> SkillVersion | None:
    result = await db.execute(
        select(SkillVersion).where(
            SkillVersion.organization_id == organization_id, SkillVersion.id == version_id
        )
    )
    return result.scalar_one_or_none()


async def list_for_skill(
    db: AsyncSession, organization_id: UUID, skill_id: UUID
) -> list[SkillVersion]:
    result = await db.execute(
        select(SkillVersion)
        .where(SkillVersion.organization_id == organization_id, SkillVersion.skill_id == skill_id)
        .order_by(SkillVersion.version_number.asc())
    )
    return list(result.scalars().all())


async def next_version_number(db: AsyncSession, organization_id: UUID, skill_id: UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(SkillVersion.version_number), 0)).where(
            SkillVersion.organization_id == organization_id, SkillVersion.skill_id == skill_id
        )
    )
    return int(result.scalar_one()) + 1


def add(db: AsyncSession, version: SkillVersion) -> None:
    db.add(version)
