from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BaseMixin


class Project(Base, BaseMixin):
    __tablename__ = "projects"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_connection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("github_connections.id"), nullable=True, index=True
    )
    source_provider: Mapped[str] = mapped_column(String(32), default="github")
    source_repository: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    runtime_type: Mapped[str] = mapped_column(String(32), default="static")  # static | container
    build_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
