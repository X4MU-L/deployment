from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BaseMixin


class AuditEvent(Base, BaseMixin):
    __tablename__ = "audit_events"

    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=True, index=True
    )
    actor_service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True, index=True
    )
    build_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("builds.id"), nullable=True, index=True
    )
    release_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("releases.id"), nullable=True, index=True
    )
    route_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("routes.id"), nullable=True, index=True
    )
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
