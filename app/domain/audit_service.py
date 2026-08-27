"""Audit writes always share the caller's transaction (see docs/ADR.md ADR-7):
this module never opens its own session or commits — it only stages a row on
the AsyncSession the caller already holds, so an audit entry for an action
that then fails/rolls back can never exist, and an action that succeeds
without one is equally impossible.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_log import AuditLog
from app.repositories import audit_logs as audit_repo
from app.security.principal import Principal


def record(
    db: AsyncSession,
    *,
    principal: Principal,
    event: str,
    resource_type: str,
    resource_id: UUID,
    skill_id: UUID | None = None,
    version_number: int | None = None,
    detail: dict | None = None,
    request_id: str | None = None,
) -> None:
    entry = AuditLog(
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        event=event,
        resource_type=resource_type,
        resource_id=resource_id,
        skill_id=skill_id,
        version_number=version_number,
        detail=detail or {},
        request_id=request_id,
    )
    audit_repo.add(db, entry)
