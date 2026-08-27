from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_log import AuditLog


def add(db: AsyncSession, entry: AuditLog) -> None:
    db.add(entry)


async def list_for_org(
    db: AsyncSession, organization_id: UUID, *, skill_id: UUID | None = None
) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.organization_id == organization_id)
    if skill_id:
        stmt = stmt.where(AuditLog.skill_id == skill_id)
    stmt = stmt.order_by(AuditLog.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())
