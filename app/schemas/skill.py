from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class SkillCreateRequest(BaseModel):
    slug: str = Field(
        ..., min_length=1, max_length=150, pattern=SLUG_PATTERN, examples=["weekly-ops-report"]
    )
    name: str = Field(..., min_length=1, max_length=200, examples=["Weekly Ops Report"])
    description: str | None = Field(
        default=None, examples=["Compiles the weekly site status into a structured report."]
    )
    # Matches the department seeded for abc-construction in scripts/seed_fixtures.py
    # (xyz-builders' seeded department is "field-ops").
    department_slug: str | None = Field(default=None, examples=["operations"])
    instructions: str = Field(
        ...,
        min_length=1,
        examples=["Compile the weekly site status into a structured report."],
    )
    model_params: dict = Field(default_factory=dict, examples=[{}])
    requested_tools: list[str] = Field(
        default_factory=list, examples=[["reports.generate", "docs.read"]]
    )

    # Deliberately NOT accepted: organization_id. If a client sends one, Pydantic
    # ignores unknown fields by default; the tenant is always the caller's own
    # (see docs/ADR.md ADR-2). This is exercised by
    # tests/security/test_isolation.py::test_body_organization_id_is_ignored.


class SkillVersionCreateRequest(BaseModel):
    instructions: str = Field(
        ...,
        min_length=1,
        examples=["Compile the weekly site status into a structured report, v2."],
    )
    model_params: dict = Field(default_factory=dict, examples=[{}])
    requested_tools: list[str] = Field(default_factory=list, examples=[["reports.generate"]])


class ReviewRequest(BaseModel):
    decision: Literal["approve", "reject"] = Field(..., examples=["approve"])
    notes: str | None = Field(default=None, examples=["Looks good, approved for activation."])


class SkillVersionOut(BaseModel):
    id: UUID
    version_number: int
    review_state: str
    requested_tools: list[str]
    content_hash: str
    created_by: UUID
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime

    @field_validator("requested_tools", mode="before")
    @classmethod
    def _coerce_tools(cls, v: object) -> object:
        return v or []

    model_config = {"from_attributes": True}


class SkillOut(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    status: str
    department_id: UUID | None
    active_version_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillDetailOut(SkillOut):
    versions: list[SkillVersionOut]


class ActivateResponse(BaseModel):
    skill_id: UUID
    status: str
    active_version_number: int
    idempotent: bool


class ToolResolution(BaseModel):
    tool: str
    granted: bool


class RuntimeSkillOut(BaseModel):
    skill_id: UUID
    slug: str
    name: str
    department_id: UUID | None
    version_number: int
    instructions: str
    model_params: dict
    tools: list[ToolResolution]
