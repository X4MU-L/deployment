from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BaseMixin


class Release(Base, BaseMixin):
    __tablename__ = "releases"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    environment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("environments.id"), nullable=False, index=True
    )
    build_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("builds.id"), nullable=False, index=True
    )
    deployment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("deployments.id"), nullable=True
    )
    artifact_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    manifest_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class Route(Base, BaseMixin):
    __tablename__ = "routes"

    hostname: Mapped[str] = mapped_column(
        String(512), unique=True, index=True, nullable=False
    )
    release_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("releases.id"), nullable=False, index=True
    )
    invalidation_version: Mapped[int] = mapped_column(default=1)
