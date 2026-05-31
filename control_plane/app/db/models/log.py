from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BaseMixin


class LogLine(Base, BaseMixin):
    __tablename__ = "log_lines"

    build_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("builds.id"), nullable=True, index=True
    )
    deployment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("deployments.id"), nullable=True, index=True
    )
    stream: Mapped[str] = mapped_column(String(16), default="stdout")  # stdout | stderr
    content: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(nullable=False)  # monotonic sequence within the entity