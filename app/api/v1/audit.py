from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_or_owner
from app.db.session import get_db_session
from app.repositories import audit_logs as audit_repo
from app.schemas.audit import AuditLogOut
from app.security.principal import Principal

router = APIRouter()


@router.get("", response_model=list[AuditLogOut])
async def list_audit_logs(
    skill_id: UUID | None = None,
    principal: Principal = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db_session),
) -> list[AuditLogOut]:
    entries = await audit_repo.list_for_org(db, principal.organization_id, skill_id=skill_id)
    return [AuditLogOut.model_validate(e) for e in entries]
