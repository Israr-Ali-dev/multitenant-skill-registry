"""Skill lifecycle: draft -> active -> disabled, and the write-once version chain.

Every function here is org-scoped through `principal.organization_id` and is
unit-testable without any HTTP machinery. Role checks are enforced here too
(not only at the router/dependency layer) so the invariant "only an owner can
activate" holds even if a route were wired incorrectly — defense in depth,
matching docs/ADR.md ADR-3.
"""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationDomainError
from app.db.models.skill import Skill
from app.db.models.skill_version import SkillVersion
from app.domain import audit_service
from app.domain.tool_catalog import validate_requested_tools
from app.repositories import departments as departments_repo
from app.repositories import skill_versions as versions_repo
from app.repositories import skills as skills_repo
from app.repositories import tool_grants as tool_grants_repo
from app.security.principal import Principal

ACTIVATABLE_REVIEW_STATE = "approved"


def _content_hash(instructions: str, model_params: dict, requested_tools: list[str]) -> str:
    canonical = json.dumps(
        {
            "instructions": instructions,
            "model_params": model_params,
            "requested_tools": sorted(requested_tools),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _resolve_department_id(
    db: AsyncSession, organization_id: UUID, department_slug: str | None
) -> UUID | None:
    if not department_slug:
        return None
    department = await departments_repo.get_by_slug(db, organization_id, department_slug)
    if department is None:
        raise ValidationDomainError(
            f"Department '{department_slug}' does not exist for this organization.",
            error_code="unknown-department",
        )
    return department.id


async def create_skill_draft(
    db: AsyncSession,
    principal: Principal,
    *,
    slug: str,
    name: str,
    description: str | None,
    department_slug: str | None,
    instructions: str,
    model_params: dict,
    requested_tools: list[str],
    request_id: str | None,
) -> Skill:
    existing = await skills_repo.get_by_slug(db, principal.organization_id, slug)
    if existing is not None:
        raise ConflictError(f"A skill with slug '{slug}' already exists in this organization.")

    department_id = await _resolve_department_id(db, principal.organization_id, department_slug)
    clean_tools = validate_requested_tools(requested_tools)

    skill = Skill(
        organization_id=principal.organization_id,
        department_id=department_id,
        slug=slug,
        name=name,
        description=description,
        status="draft",
        created_by=principal.user_id,
    )
    skills_repo.add(db, skill)
    await db.flush()  # assign skill.id

    version = SkillVersion(
        organization_id=principal.organization_id,
        skill_id=skill.id,
        version_number=1,
        instructions=instructions,
        model_params=model_params,
        requested_tools=clean_tools,
        content_hash=_content_hash(instructions, model_params, clean_tools),
        review_state="draft",
        created_by=principal.user_id,
    )
    versions_repo.add(db, version)
    await db.flush()

    audit_service.record(
        db,
        principal=principal,
        event="skill.created",
        resource_type="skill",
        resource_id=skill.id,
        skill_id=skill.id,
        version_number=version.version_number,
        detail={"slug": skill.slug},
        request_id=request_id,
    )
    audit_service.record(
        db,
        principal=principal,
        event="skill.version.created",
        resource_type="skill_version",
        resource_id=version.id,
        skill_id=skill.id,
        version_number=version.version_number,
        detail={"content_hash": version.content_hash},
        request_id=request_id,
    )
    return skill


async def get_skill(db: AsyncSession, principal: Principal, skill_id: UUID) -> Skill:
    skill = await skills_repo.get_by_id(db, principal.organization_id, skill_id)
    if skill is None:
        raise NotFoundError(f"Skill {skill_id} was not found.")
    return skill


async def list_skills(
    db: AsyncSession,
    principal: Principal,
    *,
    status_filter: str | None,
    department_slug: str | None,
) -> list[Skill]:
    department_id = None
    if department_slug:
        department_id = await _resolve_department_id(
            db, principal.organization_id, department_slug
        )
    return await skills_repo.list_for_org(
        db, principal.organization_id, status_filter=status_filter, department_id=department_id
    )


async def list_versions(
    db: AsyncSession, principal: Principal, skill_id: UUID
) -> list[SkillVersion]:
    await get_skill(db, principal, skill_id)  # 404s if cross-org
    return await versions_repo.list_for_skill(db, principal.organization_id, skill_id)


async def create_version(
    db: AsyncSession,
    principal: Principal,
    skill_id: UUID,
    *,
    instructions: str,
    model_params: dict,
    requested_tools: list[str],
    request_id: str | None,
) -> SkillVersion:
    skill = await get_skill(db, principal, skill_id)

    if skill.status == "disabled":
        raise ConflictError("Cannot create a new version on a disabled skill.")

    clean_tools = validate_requested_tools(requested_tools)
    next_number = await versions_repo.next_version_number(db, principal.organization_id, skill_id)

    version = SkillVersion(
        organization_id=principal.organization_id,
        skill_id=skill.id,
        version_number=next_number,
        instructions=instructions,
        model_params=model_params,
        requested_tools=clean_tools,
        content_hash=_content_hash(instructions, model_params, clean_tools),
        review_state="draft",
        created_by=principal.user_id,
    )
    versions_repo.add(db, version)
    await db.flush()

    audit_service.record(
        db,
        principal=principal,
        event="skill.version.created",
        resource_type="skill_version",
        resource_id=version.id,
        skill_id=skill.id,
        version_number=version.version_number,
        detail={"content_hash": version.content_hash},
        request_id=request_id,
    )
    return version


async def review_version(
    db: AsyncSession,
    principal: Principal,
    skill_id: UUID,
    version_number: int,
    *,
    decision: str,
    notes: str | None,
    request_id: str | None,
) -> SkillVersion:
    if principal.role not in ("admin", "owner"):
        raise ForbiddenError("Only an admin or owner may review a skill version.")

    skill = await get_skill(db, principal, skill_id)
    version = await versions_repo.get_by_number(
        db, principal.organization_id, skill.id, version_number
    )
    if version is None:
        raise NotFoundError(f"Version {version_number} of skill {skill_id} was not found.")

    if version.review_state not in ("draft", "in_review"):
        raise ConflictError(
            f"Version {version_number} has already been reviewed "
            f"(state='{version.review_state}')."
        )

    new_state = "approved" if decision == "approve" else "rejected"
    version.review_state = new_state
    version.reviewed_by = principal.user_id
    version.reviewed_at = datetime.now(UTC)
    await db.flush()

    audit_service.record(
        db,
        principal=principal,
        event=f"skill.version.{new_state}",
        resource_type="skill_version",
        resource_id=version.id,
        skill_id=skill.id,
        version_number=version.version_number,
        detail={"notes": notes} if notes else {},
        request_id=request_id,
    )
    return version


async def activate_version(
    db: AsyncSession,
    principal: Principal,
    skill_id: UUID,
    version_number: int,
    *,
    request_id: str | None,
) -> tuple[Skill, bool]:
    """Returns (skill, was_idempotent_noop)."""
    if principal.role != "owner":
        raise ForbiddenError("Only an organization owner may activate a skill version.")

    skill = await get_skill(db, principal, skill_id)
    version = await versions_repo.get_by_number(
        db, principal.organization_id, skill.id, version_number
    )
    if version is None:
        raise NotFoundError(f"Version {version_number} of skill {skill_id} was not found.")

    if skill.status == "disabled":
        raise ConflictError("Cannot activate a version on a disabled skill.")

    if version.review_state != ACTIVATABLE_REVIEW_STATE:
        raise ConflictError(
            f"Version {version_number} must be approved before activation "
            f"(current state='{version.review_state}')."
        )

    # Row-level lock so two concurrent activations of the same skill serialize
    # instead of racing; the loser observes the winner's committed state.
    locked = await db.execute(
        select(Skill).where(Skill.id == skill.id).with_for_update()
    )
    skill = locked.scalar_one()

    if skill.active_version_id == version.id and skill.status == "active":
        audit_service.record(
            db,
            principal=principal,
            event="skill.activate.noop",
            resource_type="skill_version",
            resource_id=version.id,
            skill_id=skill.id,
            version_number=version.version_number,
            detail={"reason": "already active"},
            request_id=request_id,
        )
        return skill, True

    skill.active_version_id = version.id
    skill.status = "active"
    await db.flush()

    audit_service.record(
        db,
        principal=principal,
        event="skill.activated",
        resource_type="skill_version",
        resource_id=version.id,
        skill_id=skill.id,
        version_number=version.version_number,
        detail={},
        request_id=request_id,
    )
    return skill, False


async def disable_skill(
    db: AsyncSession, principal: Principal, skill_id: UUID, *, request_id: str | None
) -> Skill:
    if principal.role != "owner":
        raise ForbiddenError("Only an organization owner may disable a skill.")

    skill = await get_skill(db, principal, skill_id)

    if skill.status == "disabled":
        return skill  # idempotent no-op, no duplicate audit entry

    skill.status = "disabled"
    await db.flush()
    # `updated_at` is server-computed (onupdate=func.now()); after a flush
    # that doesn't re-SELECT the row, SQLAlchemy leaves it expired. Refresh
    # explicitly so the later synchronous Pydantic serialization doesn't try
    # to lazy-load it outside the async context (MissingGreenlet).
    await db.refresh(skill)

    audit_service.record(
        db,
        principal=principal,
        event="skill.disabled",
        resource_type="skill",
        resource_id=skill.id,
        skill_id=skill.id,
        detail={},
        request_id=request_id,
    )
    return skill


async def runtime_active_skills(
    db: AsyncSession, principal: Principal, *, department_slug: str | None
) -> list[dict]:
    """Active skills only, with requested tools resolved against org grants.
    A tool is only ever `granted: true` here if an explicit tool_grants row
    exists — requesting a tool never implies capability (ADR-6).
    """
    skills = await list_skills(
        db, principal, status_filter="active", department_slug=department_slug
    )
    granted_keys = await tool_grants_repo.list_granted_keys(db, principal.organization_id)

    out = []
    for skill in skills:
        if skill.active_version_id is None:
            continue
        version = await versions_repo.get_by_id(
            db, principal.organization_id, skill.active_version_id
        )
        if version is None:
            continue
        out.append(
            {
                "skill_id": skill.id,
                "slug": skill.slug,
                "name": skill.name,
                "department_id": skill.department_id,
                "version_number": version.version_number,
                "instructions": version.instructions,
                "model_params": version.model_params,
                "tools": [
                    {"tool": tool, "granted": tool in granted_keys}
                    for tool in version.requested_tools
                ],
            }
        )
    return out
