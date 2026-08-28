"""Session/engine wiring.

The engine here connects as ``app_role`` (see docs/ADR.md ADR-3): a
non-superuser, non-table-owner Postgres role. That is what makes Postgres
Row-Level Security actually apply to every query the API issues — RLS is
bypassed for superusers and table owners regardless of policy, by design of
Postgres. Alembic migrations connect separately as the owning/admin role
(``ADMIN_DATABASE_URL``) because creating roles, enabling RLS, and defining
triggers requires elevated privileges that the runtime API must never hold.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields one AsyncSession per request, wrapped in a single transaction.

    Any ``SET LOCAL`` issued during the request (see
    ``app.security.principal.set_rls_org_context``) is scoped to this exact
    transaction and is discarded on commit/rollback, so it can never leak
    into a pooled connection reused by a later, differently-scoped request.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session


async def set_rls_org_context(session: AsyncSession, organization_id: str) -> None:
    """Sets the Postgres session variable that every RLS policy filters on."""
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
