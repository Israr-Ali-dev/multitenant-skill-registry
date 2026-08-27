import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Skill(Base):
    """The skill identity/container. Lifecycle status lives here;
    `active_version_id` is the single pointer to "what's live" — activation
    flips this pointer and never writes to a skill_versions row.
    """

    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_skills_org_slug"),
        # Composite unique target for skill_versions' composite FK below.
        UniqueConstraint("id", "organization_id", name="uq_skills_id_org"),
        # Cross-tenant department link is unrepresentable at the DB level.
        ForeignKeyConstraint(
            ["department_id", "organization_id"],
            ["departments.id", "departments.organization_id"],
            name="fk_skills_department_org",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft | active | disabled
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
