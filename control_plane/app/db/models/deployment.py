from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BaseMixin


class Deployment(Base, BaseMixin):
    __tablename__ = "deployments"

    build_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("builds.id"), nullable=False, index=True
    )
    environment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("environments.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending | provisioning | healthy | unhealthy | promoted
    replicas: Mapped[int] = mapped_column(default=1)
    error_message: Mapped[str | None] = mapped_column(String(4096), nullable=True)