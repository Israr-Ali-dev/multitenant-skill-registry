from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tool_grant import ToolGrant


async def list_granted_keys(db: AsyncSession, organization_id: UUID) -> set[str]:
    result = await db.execute(
        select(ToolGrant.tool_key).where(ToolGrant.organization_id == organization_id)
    )
    return set(result.scalars().all())
