"""
User auth repository — user accounts and social identity links.

Tokens are stateless JWTs; no principal/session table needed here.
All user_ids are UUID strings (str(uuid.uuid4())).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.social_identity import SocialIdentity as SocialIdentityModel
from app.db.models.user import User as UserModel

# ── Domain records ─────────────────────────────────────────────────────────────


@dataclass
class UserAccountRecord:
    """User account with optional password credentials.

    user_id: UUID string (e.g. "550e8400-e29b-41d4-a716-446655440000").
    email: normalised to lowercase; None for social-only accounts without email.
    password_hash: None if the account was created via social login only.
    """

    user_id: str
    email: str | None
    password_hash: str | None


# ── Interface ──────────────────────────────────────────────────────────────────


class UserAuthRepository(ABC):
    """Persistence interface for user accounts and social identity links."""

    @abstractmethod
    async def create_user(self, email: str | None, password_hash: str | None) -> UserAccountRecord:
        """Insert a new user row and return it."""
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> UserAccountRecord | None:
        """Look up a user by their UUID."""
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_email(self, email: str) -> UserAccountRecord | None:
        """Look up a user by email address (case-normalised)."""
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_social(
        self, provider: str, provider_user_id: str
    ) -> UserAccountRecord | None:
        """Find the user linked to a (provider, provider_user_id) pair."""
        raise NotImplementedError

    @abstractmethod
    async def link_social_identity(
        self, user_id: str, provider: str, provider_user_id: str
    ) -> None:
        """Associate a social identity with an existing user account."""
        raise NotImplementedError

    @abstractmethod
    async def list_social_providers(self, user_id: str) -> list[str]:
        """Return a sorted list of provider names linked to a user."""
        raise NotImplementedError


# ── SQLAlchemy implementation ──────────────────────────────────────────────────


class SqlUserAuthRepository(UserAuthRepository):
    """Session-scoped SQLAlchemy implementation.

    Receives a per-request :class:`Session`; no connection lifecycle owned here.
    Uses ORM for single-table operations.
    Uses a JOIN query for ``get_user_by_social`` to retrieve both tables
    in one round-trip and avoid N+1.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_user(self, email: str | None, password_hash: str | None) -> UserAccountRecord:
        user = UserModel(
            user_id=str(uuid.uuid4()),
            email=email,
            password_hash=password_hash,
        )
        self._s.add(user)
        await self._s.flush()
        return UserAccountRecord(
            user_id=user.user_id, email=user.email, password_hash=user.password_hash
        )

    async def get_user_by_id(self, user_id: str) -> UserAccountRecord | None:
        row = await self._s.get(UserModel, str(user_id))
        if row is None:
            return None
        return UserAccountRecord(
            user_id=row.user_id, email=row.email, password_hash=row.password_hash
        )

    async def get_user_by_email(self, email: str) -> UserAccountRecord | None:
        row = await self._s.execute(select(UserModel).where(UserModel.email == email))
        row = row.scalar_one_or_none()
        if row is None:
            return None
        return UserAccountRecord(
            user_id=row.user_id, email=row.email, password_hash=row.password_hash
        )

    async def get_user_by_social(
        self, provider: str, provider_user_id: str
    ) -> UserAccountRecord | None:
        # JOIN social_identities → users in one query — avoids two round-trips
        row = await self._s.execute(
            select(UserModel)
            .join(SocialIdentityModel, SocialIdentityModel.user_id == UserModel.user_id)
            .where(SocialIdentityModel.provider == provider)
            .where(SocialIdentityModel.provider_user_id == provider_user_id)
        )
        row = row.scalar_one_or_none()
        if row is None:
            return None
        return UserAccountRecord(
            user_id=row.user_id, email=row.email, password_hash=row.password_hash
        )

    async def link_social_identity(
        self, user_id: str, provider: str, provider_user_id: str
    ) -> None:
        existing = await self._s.get(SocialIdentityModel, (provider, provider_user_id))
        if existing is None:
            self._s.add(
                SocialIdentityModel(
                    provider=provider, provider_user_id=provider_user_id, user_id=user_id
                )
            )
            await self._s.flush()

    async def list_social_providers(self, user_id: str) -> list[str]:
        rows = await self._s.execute(
            select(SocialIdentityModel.provider).where(SocialIdentityModel.user_id == user_id)
        )
        rows = rows.scalars().all()
        return sorted(set(rows))


# ── In-memory implementation (unit tests only) ─────────────────────────────────


class InMemoryUserAuthRepository(UserAuthRepository):
    """Pure-Python in-memory repository — zero external dependencies, ideal for unit tests."""

    def __init__(self) -> None:
        self._users: dict[str, UserAccountRecord] = {}
        self._users_by_email: dict[str, str] = {}
        self._social_index: dict[tuple[str, str], str] = {}

    async def create_user(self, email: str | None, password_hash: str | None) -> UserAccountRecord:
        user_id = str(uuid.uuid4())
        normalized = email.strip().lower() if email else None
        user = UserAccountRecord(user_id=user_id, email=normalized, password_hash=password_hash)
        self._users[user_id] = user
        if normalized:
            self._users_by_email[normalized] = user_id
        return user

    async def get_user_by_id(self, user_id: str) -> UserAccountRecord | None:
        return self._users.get(user_id)

    async def get_user_by_email(self, email: str) -> UserAccountRecord | None:
        uid = self._users_by_email.get(email.strip().lower())
        return self._users.get(uid) if uid else None

    async def get_user_by_social(
        self, provider: str, provider_user_id: str
    ) -> UserAccountRecord | None:
        uid = self._social_index.get((provider, provider_user_id))
        return self._users.get(uid) if uid else None

    async def link_social_identity(
        self, user_id: str, provider: str, provider_user_id: str
    ) -> None:
        self._social_index[(provider, provider_user_id)] = user_id

    async def list_social_providers(self, user_id: str) -> list[str]:
        return sorted({p for (p, _), uid in self._social_index.items() if uid == user_id})


# ── Factory ────────────────────────────────────────────────────────────────────
