from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BaseMixin


class Build(Base, BaseMixin):
    __tablename__ = "builds"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    correlation_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )  # shared across retries
    attempt: Mapped[int] = mapped_column(default=1)
    job_type: Mapped[str] = mapped_column(String(32), default="build")
    status: Mapped[str] = mapped_column(
        String(32), default="queued"
    )  # queued | running | succeeded | failed | canceled
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    build_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    env_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )  # R2 prefix or image reference
    error_message: Mapped[str | None] = mapped_column(String(4096), nullable=True)
