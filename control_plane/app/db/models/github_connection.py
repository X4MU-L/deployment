from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, BaseMixin

if TYPE_CHECKING:
    from .github_repository import GithubRepository


class GithubConnection(Base, BaseMixin):
    __tablename__ = "github_connections"

    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=True, index=True
    )
    account_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    account_login: Mapped[str] = mapped_column(String(255), index=True)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    installation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    selection_mode: Mapped[str] = mapped_column(String(16), default="all")
    selected_repository_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    repositories: Mapped[list[GithubRepository]] = relationship(
        "GithubRepository", back_populates="connection", cascade="all, delete-orphan"
    )
