from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, BaseMixin

if TYPE_CHECKING:
    from .github_connection import GithubConnection


class GithubRepository(Base, BaseMixin):
    __tablename__ = "github_repositories"

    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("github_connections.id"), nullable=False, index=True
    )
    repository_id: Mapped[str] = mapped_column(String(128), index=True)
    full_name: Mapped[str] = mapped_column(String(512), index=True)
    owner_login: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    html_url: Mapped[str] = mapped_column(String(1024))
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    private: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    connection: Mapped[GithubConnection] = relationship(
        "GithubConnection", back_populates="repositories"
    )
