from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.schemas import RegisterPasswordRequest, SocialProviderLoginRequest
from app.auth.user_auth_service import UserAuthService
from app.auth.user_repository import (
    InMemoryUserAuthRepository,
    UserAccountRecord,
    UserAuthRepository,
)
from app.core.exceptions import BadRequestError, ConflictError


@pytest.mark.asyncio
async def test_register_invalid_email_raises_bad_request():
    svc = UserAuthService(repository=InMemoryUserAuthRepository())
    with pytest.raises(BadRequestError):
        await svc.register_password(
            RegisterPasswordRequest(email="not-an-email", password="pw123456")
        )


@pytest.mark.asyncio
async def test_register_integrity_error_translated_to_conflict():
    repo = MagicMock(spec=UserAuthRepository)
    repo.get_user_by_email = AsyncMock(return_value=None)
    # Simulate DB unique-constraint race during create
    repo.create_user = AsyncMock(
        side_effect=IntegrityError("dup", None, Exception("duplicate key"))
    )

    svc = UserAuthService(repository=repo)
    with pytest.raises(ConflictError):
        await svc.register_password(
            RegisterPasswordRequest(email="dup2@example.com", password="password123")
        )


@pytest.mark.asyncio
async def test_social_login_integrity_error_uses_existing():
    repo = MagicMock(spec=UserAuthRepository)
    # no existing social link
    repo.get_user_by_social = AsyncMock(return_value=None)
    # create_user fails with IntegrityError (concurrent insert)
    repo.create_user = AsyncMock(
        side_effect=IntegrityError("dup", None, Exception("duplicate key"))
    )
    # but get_user_by_email returns an existing user
    import uuid

    existing = UserAccountRecord(
        user_id=str(uuid.uuid4()), email="social@example.com", password_hash=None
    )
    repo.get_user_by_email = AsyncMock(return_value=existing)
    # ensure downstream calls return coherent data
    repo.get_user_by_id = AsyncMock(return_value=existing)
    repo.list_social_providers = AsyncMock(return_value=["github"])
    repo.link_social_identity = AsyncMock()

    svc = UserAuthService(repository=repo)
    session = await svc.social_login(
        SocialProviderLoginRequest(
            provider="github",
            provider_user_id="prov-99",
            email="social@example.com",
            email_verified=True,
        )
    )
    assert session.user.user_id == existing.user_id


@pytest.mark.asyncio
async def test_social_login_integrity_error_no_existing_raises_conflict():
    repo = MagicMock(spec=UserAuthRepository)
    repo.get_user_by_social = AsyncMock(return_value=None)
    repo.create_user = AsyncMock(
        side_effect=IntegrityError("dup", None, Exception("duplicate key"))
    )
    # get_user_by_email returns None meaning no race winner
    repo.get_user_by_email = AsyncMock(return_value=None)

    svc = UserAuthService(repository=repo)
    with pytest.raises(ConflictError):
        await svc.social_login(
            SocialProviderLoginRequest(
                provider="github",
                provider_user_id="prov-100",
                email="noone@example.com",
                email_verified=True,
            )
        )
