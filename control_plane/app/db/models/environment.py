from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BaseMixin


class Environment(Base, BaseMixin):
    __tablename__ = "environments"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # production, preview, staging
    env_vars: Mapped[dict | None] = mapped_column(JSON, nullable=True)
