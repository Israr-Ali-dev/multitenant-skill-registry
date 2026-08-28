from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User


async def get_by_email_in_org(db: AsyncSession, organization_id: UUID, email: str) -> User | None:
    """Explicitly org-scoped at the application layer too (defense in depth) —
    even though RLS already restricts the session to this org.
    """
    result = await db.execute(
        select(User).where(User.organization_id == organization_id, User.email == email)
    )
    return result.scalar_one_or_none()
