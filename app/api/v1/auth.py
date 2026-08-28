from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthorizedError
from app.db.models.organization import Organization
from app.db.session import get_db_session, set_rls_org_context
from app.repositories import organizations as orgs_repo
from app.repositories import users as users_repo
from app.schemas.auth import LoginRequest, PrincipalOut, TokenResponse
from app.security.hashing import verify_password
from app.security.jwt import create_access_token
from app.security.principal import Principal, get_current_principal

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, db: AsyncSession = Depends(get_db_session)
) -> TokenResponse:
    """Tenant selection happens explicitly here (organization_slug), before any
    JWT exists. This is the one place a client names an organization at all —
    every other endpoint derives it solely from the token that this issues.
    """
    organization = await orgs_repo.get_by_slug(db, payload.organization_slug)
    if organization is None:
        raise UnauthorizedError("Invalid organization, email, or password.")

    await set_rls_org_context(db, str(organization.id))

    user = await users_repo.get_by_email_in_org(db, organization.id, payload.email)
    password_ok = user is not None and verify_password(payload.password, user.password_hash)
    if user is None or not user.is_active or not password_ok:
        raise UnauthorizedError("Invalid organization, email, or password.")

    token, expires_in = create_access_token(
        user_id=str(user.id), organization_id=str(organization.id), role=user.role
    )
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=PrincipalOut)
async def me(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db_session),
) -> PrincipalOut:
    result = await db.execute(
        select(Organization).where(Organization.id == principal.organization_id)
    )
    organization = result.scalar_one()
    return PrincipalOut(
        user_id=str(principal.user_id),
        organization_id=str(principal.organization_id),
        organization_name=organization.name,
        role=principal.role,
        email=principal.email,
    )
