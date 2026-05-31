from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class SocialIdentity(Base):
    """Maps a (provider, provider_user_id) pair to a fasttunnel user."""

    __tablename__ = "social_identities"

    provider: Mapped[str] = mapped_column(String, primary_key=True)
    provider_user_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id"), nullable=False, index=True
    )

    user: Mapped[User] = relationship("User", back_populates="social_identities")

    def __repr__(self) -> str:
        return f"<SocialIdentity provider={self.provider!r} uid={self.provider_user_id!r}>"
