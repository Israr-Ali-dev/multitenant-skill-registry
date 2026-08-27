import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SkillVersion(Base):
    """Write-once content. No route or service method ever updates the content
    columns of an existing row (instructions/model_params/requested_tools/
    content_hash) — enforced additionally by a DB trigger (see migration 0002)
    that only tolerates changes to review_state/reviewed_by/reviewed_at.
    """

    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_number"),
        UniqueConstraint("id", "organization_id", name="uq_skill_versions_id_org"),
        ForeignKeyConstraint(
            ["skill_id", "organization_id"],
            ["skills.id", "skills.organization_id"],
            name="fk_skill_versions_skill_org",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    model_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    requested_tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft | in_review | approved | rejected
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
