"""Resolves the authenticated Principal for a request and — critically —
sets the Postgres RLS session variable from the verified token claim before
any other query on that same session/transaction can run.

This is the seam described in docs/ADR.md ADR-2/ADR-3: `organization_id`
never arrives from a path, query, or request body. It arrives exactly once,
from a JWT claim that was itself only ever written server-side at login.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthorizedError
from app.db.models.user import User
from app.db.session import get_db_session, set_rls_org_context
from app.security.jwt import TokenError, decode_access_token


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    role: str
    email: str


async def get_current_principal(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_access_token(token)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired access token.") from exc

    try:
        user_id = UUID(claims["sub"])
        organization_id = UUID(claims["org_id"])
        token_role = claims["role"]
    except (KeyError, ValueError, TypeError) as exc:
        raise UnauthorizedError("Access token is malformed.") from exc

    # Set RLS context BEFORE the user lookup, so the lookup itself is already
    # tenant-scoped at the database layer (defense in depth, not just belt).
    await set_rls_org_context(db, str(organization_id))

    result = await db.execute(
        select(User).where(User.id == user_id, User.organization_id == organization_id)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise UnauthorizedError("User is inactive or no longer exists.")

    if user.role != token_role:
        # Role was changed server-side since the token was issued; don't trust the stale claim.
        raise UnauthorizedError("Token role no longer matches the current user record.")

    return Principal(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role,
        email=user.email,
    )
