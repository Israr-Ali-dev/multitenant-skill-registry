from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.domain import skill_service
from app.schemas.skill import RuntimeSkillOut
from app.security.principal import Principal, get_current_principal

router = APIRouter()


@router.get("/skills", response_model=list[RuntimeSkillOut])
async def runtime_skills(
    department: str | None = None,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db_session),
) -> list[RuntimeSkillOut]:
    """Active skills only (see docs/ADR.md ADR-5) with requested tools resolved
    against the org's actual tool_grants — never the reverse.
    """
    rows = await skill_service.runtime_active_skills(db, principal, department_slug=department)
    return [RuntimeSkillOut(**row) for row in rows]
