from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    organization_id: UUID
    actor_user_id: UUID
    actor_role: str
    event: str
    resource_type: str
    resource_id: UUID
    skill_id: UUID | None
    version_number: int | None
    detail: dict
    created_at: datetime

    model_config = {"from_attributes": True}
