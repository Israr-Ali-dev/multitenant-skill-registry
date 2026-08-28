import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ToolGrant(Base):
    """Org-level capability allowlist. A version *requesting* a tool never
    grants it — only a row here does (see docs/ADR.md ADR-6).
    """

    __tablename__ = "tool_grants"
    __table_args__ = (
        UniqueConstraint("organization_id", "tool_key", name="uq_tool_grants_org_tool"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    tool_key: Mapped[str] = mapped_column(String(100), nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
