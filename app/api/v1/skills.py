from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_or_owner, require_owner
from app.db.session import get_db_session
from app.domain import skill_service
from app.schemas.skill import (
    ActivateResponse,
    ReviewRequest,
    SkillCreateRequest,
    SkillDetailOut,
    SkillOut,
    SkillVersionCreateRequest,
    SkillVersionOut,
)
from app.security.principal import Principal, get_current_principal

router = APIRouter()


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: SkillCreateRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db_session),
) -> SkillOut:
    skill = await skill_service.create_skill_draft(
        db,
        principal,
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        department_slug=payload.department_slug,
        instructions=payload.instructions,
        model_params=payload.model_params,
        requested_tools=payload.requested_tools,
        request_id=_request_id(request),
    )
    return SkillOut.model_validate(skill)


@router.get("", response_model=list[SkillOut])
async def list_skills(
    status_filter: str | None = Query(default=None, examples=["draft"]),
    department: str | None = Query(default=None, examples=["operations"]),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db_session),
) -> list[SkillOut]:
    skills = await skill_service.list_skills(
        db, principal, status_filter=status_filter, department_slug=department
    )
    return [SkillOut.model_validate(s) for s in skills]


@router.get("/{skill_id}", response_model=SkillDetailOut)
async def get_skill(
    skill_id: UUID,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db_session),
) -> SkillDetailOut:
    skill = await skill_service.get_skill(db, principal, skill_id)
    versions = await skill_service.list_versions(db, principal, skill_id)
    return SkillDetailOut(
        **SkillOut.model_validate(skill).model_dump(),
        versions=[SkillVersionOut.model_validate(v) for v in versions],
    )


@router.post(
    "/{skill_id}/versions", response_model=SkillVersionOut, status_code=status.HTTP_201_CREATED
)
async def create_version(
    skill_id: UUID,
    payload: SkillVersionCreateRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db_session),
) -> SkillVersionOut:
    version = await skill_service.create_version(
        db,
        principal,
        skill_id,
        instructions=payload.instructions,
        model_params=payload.model_params,
        requested_tools=payload.requested_tools,
        request_id=_request_id(request),
    )
    return SkillVersionOut.model_validate(version)


@router.post("/{skill_id}/versions/{version_number}/review", response_model=SkillVersionOut)
async def review_version(
    skill_id: UUID,
    version_number: int,
    payload: ReviewRequest,
    request: Request,
    principal: Principal = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db_session),
) -> SkillVersionOut:
    version = await skill_service.review_version(
        db,
        principal,
        skill_id,
        version_number,
        decision=payload.decision,
        notes=payload.notes,
        request_id=_request_id(request),
    )
    return SkillVersionOut.model_validate(version)


@router.post("/{skill_id}/versions/{version_number}/activate", response_model=ActivateResponse)
async def activate_version(
    skill_id: UUID,
    version_number: int,
    request: Request,
    principal: Principal = Depends(require_owner),
    db: AsyncSession = Depends(get_db_session),
) -> ActivateResponse:
    skill, idempotent = await skill_service.activate_version(
        db, principal, skill_id, version_number, request_id=_request_id(request)
    )
    return ActivateResponse(
        skill_id=skill.id,
        status=skill.status,
        active_version_number=version_number,
        idempotent=idempotent,
    )


@router.post("/{skill_id}/disable", response_model=SkillOut)
async def disable_skill(
    skill_id: UUID,
    request: Request,
    principal: Principal = Depends(require_owner),
    db: AsyncSession = Depends(get_db_session),
) -> SkillOut:
    skill = await skill_service.disable_skill(
        db, principal, skill_id, request_id=_request_id(request)
    )
    return SkillOut.model_validate(skill)
